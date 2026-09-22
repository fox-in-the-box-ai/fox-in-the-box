"""Fox cron failure-diagnostics overlay for hermes-agent.

Re-implemented for hermes-agent v2026.9.21 (#849). The upstream v2026.9.7
cron refactor broke the text-anchor substitutions this module used to rely
on. Rather than retire the enriched diagnostics, the behavior is
re-expressed with the FUNCTION-WRAP idiom (see
``fox_overlay/aws_bedrock_auth.py``): capture the original, call it FIRST,
add Fox behavior after, then set a module sentinel LAST. Wraps depend only
on a function's signature and return shape, so they survive the internal
churn that broke the old anchors. Composition — never clobber: upstream's
native ``failure_streak``, redacted ``last_error`` and redacted
``format_run_error`` traceback all still emit; Fox adds only net-new.

Three behaviors, all ADDITIVE:

1. Rolling failure history — WRAP ``cron.jobs._record_run_outcome``.
   Upstream runs first (stamps status + native ``failure_streak``); Fox
   then keeps a redacted last-5 ``fox_failure_history`` on the job dict.
   On success it clears the list, mirroring the native streak reset so the
   two never disagree. This is the SINGLE redaction chokepoint for cron
   failure text.

2. Enriched FAILED run-doc — minimal composing splice in
   ``cron.scheduler.run_job``. ``agent`` and ``_cron_session_id`` are
   run_job locals not passed to any wrappable helper, so this one text
   anchor is irreducible (accepted per the architect design). Upstream's
   ``output = _run_doc_header(...) + format_run_error(e)`` is kept verbatim;
   Fox appends ONLY a ``## Agent Diagnostics`` section + a session-log
   pointer via ``_fox_cron_diag_block`` (injected through ``extra_globals``).
   Upstream's ``format_run_error`` already emits the redacted traceback
   under ``## Error``, so Fox emits NO traceback and NO raw error string —
   re-emitting either would double-print and reintroduce an un-redacted
   leak.

3. Surface failure fields — WRAP ``tools.cronjob_job_args._format_job``
   (relocated upstream from ``cronjob_tools.py``, re-imported there). Adds
   ``failure_history`` + ``consecutive_failures`` only when failures exist.
   Upstream already emits a redacted ``last_error``; Fox does not touch it.

``fox_failure_history`` piggybacks on the job dict: it inherits the job's
persistence, cleanup and locking for free, is ``fox_``-namespaced (so the
overlay stays removable), and reaches the tool API only through the
explicit ``_format_job`` wrap (``_FORMAT_JOB_OPTIONAL_KEYS`` whitelists the
keys upstream echoes, so an un-whitelisted ``fox_`` key never leaks on its
own).
"""

import logging
import sys

from agent.redact import redact_sensitive_text
from cron import jobs as _u_jobs
from cron import scheduler as _u_scheduler
from tools import cronjob_job_args as _u_cronjob_job_args

from ._helpers import substitute_function

_log = logging.getLogger("fox_overlay.cron_diagnostics")

_RECORD_OUTCOME_SENTINEL = "_fox_patched_record_run_outcome_history"
_RUN_JOB_SENTINEL = "_fox_patched_run_job_diagnostics"
_FORMAT_JOB_SENTINEL = "_fox_patched_format_job_failure_history"

# Keep the last N failures; truncate each stored error to N chars.
_MAX_FAILURE_HISTORY = 5
_ERROR_FIELD_MAX = 200


def _fox_cron_diag_block(agent, session_id) -> str:
    """Net-new FAILED-doc section: agent activity summary + session-log pointer.

    Contains NO traceback and NO raw error string — upstream's
    ``format_run_error`` already emits the redacted traceback under
    ``## Error``. Re-emitting a traceback here would double-print, and
    re-emitting the raw error would reintroduce the un-redacted leak this
    refresh removes.
    """
    lines: list[str] = []
    if agent is not None and hasattr(agent, "get_activity_summary"):
        try:
            act = agent.get_activity_summary() or {}
            api_calls = act.get("api_call_count", "?")
            max_iter = act.get("max_iterations", "?")
            last_act = act.get("last_activity_desc", "unknown")
            idle = act.get("seconds_since_activity") or 0
            lines.append(f"**Iterations:** {api_calls}/{max_iter}")
            lines.append(f"**Last activity:** {last_act} ({int(idle)}s ago)")
            if act.get("current_tool"):
                lines.append(f"**Stuck on tool:** `{act['current_tool']}`")
        except Exception:
            # Diagnostics are best-effort on an already-failing path; never let
            # them mask the real failure. (Cancellation/KeyboardInterrupt are
            # BaseException and propagate past this narrow Exception catch.)
            _log.debug("fox cron diag: activity summary unavailable", exc_info=True)
    diag = ("\n".join(lines) + "\n\n") if lines else ""
    return (
        "\n## Agent Diagnostics\n\n"
        f"{diag}"
        f"**Session log:** `~/.hermes/sessions/session_{session_id}.json`\n"
    )


def _apply_record_run_outcome_wrap() -> None:
    """WRAP ``cron.jobs._record_run_outcome`` to maintain ``fox_failure_history``."""
    if getattr(_u_jobs, _RECORD_OUTCOME_SENTINEL, False):
        return

    _orig = _u_jobs._record_run_outcome

    def _record_run_outcome(job, success, error, delivery_error, status, now):
        # Upstream first: stamps last_status/last_error/failure_streak/claims.
        _orig(job, success, error, delivery_error, status, now)
        if success:
            # Mirror the native failure_streak reset (set to 0 above) so the
            # rolling history and the streak counter never disagree.
            job["fox_failure_history"] = []
            return
        redacted = redact_sensitive_text(
            error or "unknown",
            force=True,
            redact_url_credentials=True,
        )[:_ERROR_FIELD_MAX]
        history = list(job.get("fox_failure_history") or [])
        history.append({"at": now, "error": redacted})
        job["fox_failure_history"] = history[-_MAX_FAILURE_HISTORY:]

    _record_run_outcome.__name__ = _orig.__name__
    _record_run_outcome.__doc__ = _orig.__doc__
    setattr(_record_run_outcome, _RECORD_OUTCOME_SENTINEL, True)
    _u_jobs._record_run_outcome = _record_run_outcome
    setattr(_u_jobs, _RECORD_OUTCOME_SENTINEL, True)
    _log.info(
        "[fox-overlay] cron.jobs._record_run_outcome failure-history wrap enabled"
    )


def _apply_run_job_splice() -> None:
    """Splice the ``## Agent Diagnostics`` block into ``cron.scheduler.run_job``.

    ``agent`` and ``_cron_session_id`` are run_job locals, so this behavior
    cannot be expressed as a wrap — it is the one irreducible text anchor.
    Upstream's ``output = ...`` expression is kept verbatim and the Fox block
    is appended before the return; ``substitute_function`` fails loudly at
    apply() if the anchor is missing or non-unique.
    """
    substitute_function(
        upstream_module=_u_scheduler,
        function_name="run_job",
        substitutions=[
            (
                "        output = (\n"
                '            _run_doc_header(job, f"{job_name} (FAILED)", job_id, prompt)\n'
                "            + format_run_error(e)\n"
                "        )\n"
                '        return False, output, "", error_msg\n',
                "        output = (\n"
                '            _run_doc_header(job, f"{job_name} (FAILED)", job_id, prompt)\n'
                "            + format_run_error(e)\n"
                "        )\n"
                "        output = output + _fox_cron_diag_block(agent, _cron_session_id)\n"
                '        return False, output, "", error_msg\n',
            ),
        ],
        sentinel=_RUN_JOB_SENTINEL,
        extra_globals={"_fox_cron_diag_block": _fox_cron_diag_block},
    )


def _apply_format_job_wrap() -> None:
    """WRAP ``tools.cronjob_job_args._format_job`` to surface failure fields."""
    if getattr(_u_cronjob_job_args, _FORMAT_JOB_SENTINEL, False):
        return

    _orig = _u_cronjob_job_args._format_job

    def _format_job(job):
        result = _orig(job)
        # Surface failure fields only when the job actually has failures, so
        # healthy-job listings stay clean. Upstream already emits a redacted
        # ``last_error`` — deliberately not overwritten here.
        if isinstance(result, dict) and (
            job.get("fox_failure_history") or job.get("failure_streak")
        ):
            result["failure_history"] = job.get("fox_failure_history") or []
            result["consecutive_failures"] = job.get("failure_streak") or 0
        return result

    _format_job.__name__ = _orig.__name__
    _format_job.__doc__ = _orig.__doc__
    setattr(_format_job, _FORMAT_JOB_SENTINEL, True)
    _u_cronjob_job_args._format_job = _format_job
    # cronjob_tools re-imports _format_job by value at its own module load
    # (``from tools.cronjob_job_args import _format_job``); every cron tool
    # and CLI call resolves THAT module-global binding, not this definition.
    # If cronjob_tools was already imported before this wrap ran, rebinding
    # only the definition module would leave the tool-API surface silently
    # inert — the exact failure class this overlay refresh exists to prevent.
    # Rebind the already-imported copy to the SAME wrapper (shared sentinel)
    # so the wrap is effective regardless of import order.
    _ct = sys.modules.get("tools.cronjob_tools")
    if _ct is not None and hasattr(_ct, "_format_job"):
        _ct._format_job = _format_job
    setattr(_u_cronjob_job_args, _FORMAT_JOB_SENTINEL, True)
    _log.info(
        "[fox-overlay] tools.cronjob_job_args._format_job failure-fields wrap enabled"
    )


def apply() -> None:
    _apply_record_run_outcome_wrap()
    _apply_run_job_splice()
    _apply_format_job_wrap()
