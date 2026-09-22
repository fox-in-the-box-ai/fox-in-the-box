"""Agent-side monkey-patch regression tests.

Refreshed for hermes-agent v2026.9.21 (#849). The cron diagnostics patches
moved from text-anchor substitution to the function-WRAP idiom; the two
auxiliary_client patches remain text-anchor substitutions. This suite
verifies, after ``register()`` runs:

* text-anchor patches (substitute_function) carry their sentinel on the
  recompiled FUNCTION object, and their target is still defined exactly
  once in upstream (an ``ast`` guard against upstream rename/duplication —
  which is what silently breaks a text anchor);
* wrap patches carry their sentinel on the MODULE;
* the ``_format_job`` wrap actually reaches the tool-API surface
  (``tools.cronjob_tools``), which re-imports ``_format_job`` by value at
  its own module load — the regression guard against a silently-inert wrap;
* the failure-history redaction chokepoint and the FAILED-doc diagnostics
  block behave as specified.

Requires hermes-agent installed (so upstream modules are importable). The
container CI/QA smoke environment satisfies this; a local dev venv usually
does not — those runs skip via ``pytest.importorskip``.

Anti-regression Rule 3: this file is the agent-side regression seed.
"""

import ast
import inspect

import pytest

# Skip the whole module if hermes-agent isn't installed (local dev without
# the full stack). Container CI/QA invokes this with hermes-agent present.
pytest.importorskip("agent.auxiliary_client")
pytest.importorskip("cron.jobs")
pytest.importorskip("cron.scheduler")
pytest.importorskip("tools.cronjob_job_args")
# Imported BEFORE register() runs (below): cronjob_tools re-imports _format_job
# by value at load, so this ordering is exactly what would expose a
# silently-inert definition-module-only wrap.
pytest.importorskip("tools.cronjob_tools")

from agent import auxiliary_client  # noqa: E402
from cron import jobs, scheduler  # noqa: E402
from tools import cronjob_job_args, cronjob_tools  # noqa: E402

from fox_overlay.agent_plugins import register  # noqa: E402


# substitute_function (text-anchor) patches — sentinel on the FUNCTION object.
FUNCTION_SENTINELS = [
    (
        auxiliary_client,
        "_resolve_task_provider_model",
        "_fox_patched_provider_auto_fallback",
    ),
    (
        auxiliary_client,
        "_get_auxiliary_task_config",
        "_fox_patched_auxiliary_default_fallback",
    ),
    (scheduler, "run_job", "_fox_patched_run_job_diagnostics"),
]

# WRAP patches — sentinel on the MODULE.
MODULE_SENTINELS = [
    (jobs, "_fox_patched_record_run_outcome_history"),
    (cronjob_job_args, "_fox_patched_format_job_failure_history"),
]

# Text-anchor targets that must stay defined exactly once at module scope.
AST_EXACTLY_ONCE = [
    (auxiliary_client, "_resolve_task_provider_model"),
    (auxiliary_client, "_get_auxiliary_task_config"),
]


@pytest.fixture(scope="module", autouse=True)
def _apply_patches():
    """Invoke fox-overlay register() once for the whole module run."""
    register(None)


@pytest.mark.parametrize(
    "module, function_name, sentinel",
    FUNCTION_SENTINELS,
    ids=[f"{m.__name__}.{fn}" for m, fn, _ in FUNCTION_SENTINELS],
)
def test_function_sentinel_set(module, function_name, sentinel):
    """Each text-anchor patch sets its sentinel on the recompiled function."""
    fn = getattr(module, function_name)
    assert getattr(fn, sentinel, False) is True, (
        f"{module.__name__}.{function_name} missing {sentinel} — patch did not "
        "apply (anchor may have drifted in upstream)"
    )


@pytest.mark.parametrize(
    "module, sentinel",
    MODULE_SENTINELS,
    ids=[f"{m.__name__}:{s}" for m, s in MODULE_SENTINELS],
)
def test_module_sentinel_set(module, sentinel):
    """Each wrap patch sets its sentinel on the live module."""
    assert getattr(module, sentinel, False) is True, (
        f"{module.__name__} missing {sentinel} — wrap did not apply"
    )


@pytest.mark.parametrize(
    "module, function_name",
    AST_EXACTLY_ONCE,
    ids=[f"{m.__name__}.{fn}" for m, fn in AST_EXACTLY_ONCE],
)
def test_text_anchor_target_defined_exactly_once(module, function_name):
    """The substitute_function targets must be defined exactly once at module
    scope; a rename or duplicate upstream is what silently breaks a text
    anchor, so guard it explicitly rather than only via apply()."""
    tree = ast.parse(inspect.getsource(module))
    count = sum(
        1
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == function_name
    )
    assert count == 1, (
        f"{module.__name__}.{function_name} defined {count}x at module scope "
        "(expected exactly 1)"
    )


def test_format_job_wrap_reaches_tool_api_surface():
    """The tool-API path resolves ``_format_job`` through ``cronjob_tools``'s
    own module-global binding, which was imported by value before register()
    ran. The wrap must reach THAT binding or the failure fields are silently
    inert on the surface users actually hit. This is the #849 regression guard.
    """
    assert cronjob_tools._format_job is cronjob_job_args._format_job
    assert (
        getattr(
            cronjob_tools._format_job, "_fox_patched_format_job_failure_history", False
        )
        is True
    )


def test_record_run_outcome_history_and_redaction():
    """Failures accrue a redacted, capped-at-5 history; success clears it and
    the native failure_streak stays authoritative."""
    secret = "SuperSecretPW123"
    job = {"id": "t", "failure_streak": 0}
    jobs._record_run_outcome(
        job,
        success=False,
        error=f"boom https://u:{secret}@h/x",
        delivery_error=None,
        status=None,
        now="n0",
    )
    assert job["failure_streak"] == 1  # upstream native streak preserved
    assert len(job["fox_failure_history"]) == 1
    assert set(job["fox_failure_history"][0]) == {"at", "error"}
    # The single redaction chokepoint: raw secret never reaches the history.
    assert secret not in job["fox_failure_history"][0]["error"]

    for i in range(6):
        jobs._record_run_outcome(
            job,
            success=False,
            error=f"e{i}",
            delivery_error=None,
            status=None,
            now=f"n{i}",
        )
    assert len(job["fox_failure_history"]) == 5  # capped at last 5
    assert job["fox_failure_history"][-1]["error"] == "e5"

    jobs._record_run_outcome(
        job,
        success=True,
        error=None,
        delivery_error=None,
        status=None,
        now="ok",
    )
    assert job["fox_failure_history"] == []  # mirrors native streak reset
    assert job["failure_streak"] == 0


def test_format_job_surfaces_fields_only_on_failure():
    """Healthy jobs stay clean; failing jobs surface failure_history +
    consecutive_failures. Upstream's redacted last_error is not overwritten."""
    healthy = cronjob_tools._format_job({"id": "j", "prompt": "p"})
    assert "failure_history" not in healthy
    assert "consecutive_failures" not in healthy

    failing = cronjob_tools._format_job(
        {
            "id": "j",
            "prompt": "p",
            "last_status": "error",
            "failure_streak": 2,
            "fox_failure_history": [{"at": "t", "error": "x"}],
        }
    )
    assert failing["failure_history"] == [{"at": "t", "error": "x"}]
    assert failing["consecutive_failures"] == 2


def test_cron_diag_block_has_diagnostics_but_no_traceback():
    """The FAILED-doc block adds agent diagnostics + a session-log pointer and
    deliberately emits NO traceback (upstream format_run_error already does,
    redacted)."""
    from fox_overlay.agent_plugins.fox_overlay_plugin.monkey_patches import (
        cron_diagnostics as cd,
    )

    class _Agent:
        def get_activity_summary(self):
            return {
                "api_call_count": 5,
                "max_iterations": 20,
                "last_activity_desc": "calling tool",
                "seconds_since_activity": 12.4,
                "current_tool": "web_search",
            }

    block = cd._fox_cron_diag_block(_Agent(), "cron_j1_20260922")
    assert "## Agent Diagnostics" in block
    assert (
        "**Session log:** `~/.hermes/sessions/session_cron_j1_20260922.json`" in block
    )
    assert "**Iterations:** 5/20" in block
    assert "**Stuck on tool:** `web_search`" in block
    assert "## Traceback" not in block
    assert "Traceback (most recent call last)" not in block

    # Tolerates a missing agent (e.g. failure before the agent was constructed).
    none_block = cd._fox_cron_diag_block(None, "sid")
    assert "## Agent Diagnostics" in none_block
    assert "**Session log:** `~/.hermes/sessions/session_sid.json`" in none_block


def test_register_is_idempotent():
    """Repeat register() calls are safe — sentinels short-circuit each apply()."""
    register(None)
    register(None)
    for module, function_name, sentinel in FUNCTION_SENTINELS:
        assert getattr(getattr(module, function_name), sentinel, False) is True
    for module, sentinel in MODULE_SENTINELS:
        assert getattr(module, sentinel, False) is True
