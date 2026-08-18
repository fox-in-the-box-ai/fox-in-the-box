"""Fox cron failure-diagnostics patches across 3 upstream modules.

Restores the Fox edit from hermes-agent fork commit edb16600b that
relocated to this overlay during the v0.6.0 upstream-separation
migration (Phase 3). Five substitutions across three modules:

* ``cron.jobs.create_job`` — add ``failure_history`` to the job dict.
* ``cron.jobs.mark_job_run`` — maintain rolling last-5 failure entries.
* ``cron.scheduler.run_job`` — enrich the FAILED output with agent
  diagnostics + traceback + session-log pointer.
* ``cron.scheduler.run_one_job`` — augment failure delivery with
  consecutive failure count + session log path (upstream handles error
  formatting via ``_summarize_cron_failure_for_delivery``).
* ``tools.cronjob_tools._format_job`` — surface ``last_error`` +
  ``failure_history`` + ``consecutive_failures`` to the tool API when
  the job has failures.

The scheduler patches need ``traceback`` (not imported upstream); it's
injected into the patched function's ``__globals__`` via the helper's
``extra_globals`` mechanism — does NOT pollute upstream namespaces.

Phase 0 PR campaign candidate; if upstream accepts the PR, this
monkey-patch becomes dead code and is removed in Phase 10 cleanup.
"""
import traceback

from cron import jobs as _u_jobs
from cron import scheduler as _u_scheduler
from tools import cronjob_tools as _u_cronjob_tools

from ._helpers import substitute_function


def apply() -> None:
    # 1) cron.jobs.create_job — add failure_history to dict
    substitute_function(
        upstream_module=_u_jobs,
        function_name="create_job",
        substitutions=[
            (
                '        "last_delivery_error": None,\n',
                '        "last_delivery_error": None,\n'
                '        "failure_history": [],  # Rolling last-5 failures: [{at, error, session_id}]\n',
            ),
        ],
        sentinel="_fox_patched_create_job_failure_history",
    )

    # 2) cron.jobs.mark_job_run — maintain rolling failure history
    # v2026.6.19 added cross-process file locking via _jobs_lock and
    # fire-claim clearing between the delivery_error and completed-count lines.
    # v2026.8.16.2 split mark_job_run into a locking wrapper +
    # _mark_job_run_locked (body) and inserted a run_claim clearing block
    # (#59229) inside our old anchor span. Target the locked body with the
    # minimal unique anchor and insert the history block right after it.
    substitute_function(
        upstream_module=_u_jobs,
        function_name="_mark_job_run_locked",
        substitutions=[
            (
                '                job["last_delivery_error"] = delivery_error\n',
                '                job["last_delivery_error"] = delivery_error\n'
                '\n'
                '                # Maintain rolling failure history (last 5 entries).\n'
                '                # On success, clear it so the counter resets.\n'
                '                if not success:\n'
                '                    _entry = {"at": now, "error": (error or "unknown")[:200]}\n'
                '                    _hist = list(job.get("failure_history") or [])\n'
                '                    _hist.append(_entry)\n'
                '                    job["failure_history"] = _hist[-5:]  # keep last 5\n'
                '                else:\n'
                '                    job["failure_history"] = []\n',
            ),
        ],
        sentinel="_fox_patched_mark_job_run_failure_history",
    )

    # 3) cron.scheduler.run_job — enrich FAILED output with diagnostics + traceback
    # v2026.6.5 split run_job into wrapper + _run_job_impl; v2026.6.19
    # folded it back into a single run_job. Target run_job directly.
    substitute_function(
        upstream_module=_u_scheduler,
        function_name="run_job",
        substitutions=[
            (
                # v2026.8.16.2 inserted an audit-record write between the
                # except header and the output template; anchor on the intact
                # template block only (verified unique in run_job).
                '        output = f"""# Cron Job: {job_name} (FAILED)\n'
                '\n'
                '**Job ID:** {job_id}\n'
                '**Run Time:** {_hermes_now().strftime(\'%Y-%m-%d %H:%M:%S\')}\n'
                '**Schedule:** {job.get(\'schedule_display\', \'N/A\')}\n'
                '\n'
                '## Prompt\n'
                '\n'
                '{prompt}\n'
                '\n'
                '## Error\n'
                '\n'
                '```\n'
                '{error_msg}\n'
                '```\n'
                '"""\n'
                '        return False, output, "", error_msg\n',
                '        # Collect agent activity diagnostics if available\n'
                '        _diag_lines: list[str] = []\n'
                '        if agent is not None:\n'
                '            try:\n'
                '                _act = agent.get_activity_summary() if hasattr(agent, "get_activity_summary") else {}\n'
                '                _api_calls = _act.get("api_call_count", "?")\n'
                '                _max_iter = _act.get("max_iterations", "?")\n'
                '                _last_act = _act.get("last_activity_desc", "unknown")\n'
                '                _idle = _act.get("seconds_since_activity", 0)\n'
                '                _diag_lines.append(f"**Iterations:** {_api_calls}/{_max_iter}")\n'
                '                _diag_lines.append(f"**Last activity:** {_last_act} ({int(_idle)}s ago)")\n'
                '                if _act.get("current_tool"):\n'
                '                    _diag_lines.append(f"**Stuck on tool:** `{_act[\'current_tool\']}`")\n'
                '            except Exception:\n'
                '                pass\n'
                '\n'
                '        _tb = traceback.format_exc()\n'
                '        _diag_block = ("\\n".join(_diag_lines) + "\\n\\n") if _diag_lines else ""\n'
                '\n'
                '        output = f"""# Cron Job: {job_name} (FAILED)\n'
                '\n'
                '**Job ID:** {job_id}\n'
                '**Session:** `{_cron_session_id}`\n'
                '**Run Time:** {_hermes_now().strftime(\'%Y-%m-%d %H:%M:%S\')}\n'
                '**Schedule:** {job.get(\'schedule_display\', \'N/A\')}\n'
                '\n'
                '## Error\n'
                '\n'
                '```\n'
                '{error_msg}\n'
                '```\n'
                '\n'
                '## Agent Diagnostics\n'
                '\n'
                '{_diag_block}**Session log:** `~/.hermes/sessions/session_{_cron_session_id}.json`\n'
                '\n'
                '## Traceback\n'
                '\n'
                '```\n'
                '{_tb}\n'
                '```\n'
                '\n'
                '## Prompt\n'
                '\n'
                '{prompt}\n'
                '"""\n'
                '        return False, output, "", error_msg\n',
            ),
        ],
        sentinel="_fox_patched_run_job_diagnostics",
        extra_globals={"traceback": traceback},
    )

    # 4) run_one_job delivery-enrichment substitution REMOVED 2026-08-17:
    # upstream v2026.8.16.2 refactored run_one_job into _run_one_job_body
    # and ships native failure-streak nudging (_failure_streak_nudge +
    # persisted failure_streak) superseding our consecutive-failures line;
    # the session-log pointer already reaches users via the patched
    # run_job FAILED template.

    # 5) tools.cronjob_tools._format_job — surface failure history when present
    substitute_function(
        upstream_module=_u_cronjob_tools,
        function_name="_format_job",
        substitutions=[
            (
                '        "paused_at": job.get("paused_at"),\n'
                '        "paused_reason": job.get("paused_reason"),\n'
                '    }\n'
                '    if job.get("script"):\n',
                '        "paused_at": job.get("paused_at"),\n'
                '        "paused_reason": job.get("paused_reason"),\n'
                '    }\n'
                '    # Surface failure history and last error only when there are failures —\n'
                '    # keeps the list output clean for healthy jobs.\n'
                '    if job.get("last_status") == "error" or job.get("failure_history"):\n'
                '        result["last_error"] = job.get("last_error")\n'
                '        _hist = job.get("failure_history") or []\n'
                '        if _hist:\n'
                '            result["failure_history"] = _hist\n'
                '            result["consecutive_failures"] = len(_hist)\n'
                '    if job.get("script"):\n',
            ),
        ],
        sentinel="_fox_patched_format_job_failure_history",
    )
