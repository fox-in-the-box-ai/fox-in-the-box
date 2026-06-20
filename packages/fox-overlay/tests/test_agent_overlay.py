"""Phase 3 monkey-patch regression tests.

Each test verifies that the corresponding upstream symbol carries its
fox-overlay sentinel attribute after ``register()`` runs. Anchor drift
in upstream → ``substitute_function`` raises AssertionError at register
time → fixture fails → these tests fail loudly with the offending
target named in the traceback.

Requires hermes-agent installed (so upstream modules are importable).
The container CI/QA smoke environment satisfies this; the local
development venv typically does not — those runs are skipped via
``pytest.importorskip``.

Anti-regression Rule 3: this file is the seed of the agent-side
regression suite for Phase 3. Phases 4-6 add webui-side tests
alongside.
"""
import pytest

# Skip the whole module if hermes-agent isn't installed (local dev without
# the full stack). Container CI/QA invokes this with hermes-agent present.
pytest.importorskip("hermes_cli.runtime_provider")
pytest.importorskip("agent.auxiliary_client")
pytest.importorskip("cron.jobs")
pytest.importorskip("cron.scheduler")
pytest.importorskip("tools.cronjob_tools")

from agent import auxiliary_client  # noqa: E402
from cron import jobs, scheduler  # noqa: E402
from hermes_cli import runtime_provider  # noqa: E402
from tools import cronjob_tools  # noqa: E402

from fox_overlay.agent_plugins import register  # noqa: E402


SENTINELS = [
    (runtime_provider, "resolve_runtime_provider", "_fox_patched_target_model"),
    (auxiliary_client, "_resolve_task_provider_model", "_fox_patched_provider_auto_fallback"),
    (auxiliary_client, "_get_auxiliary_task_config", "_fox_patched_auxiliary_default_fallback"),
    (jobs, "create_job", "_fox_patched_create_job_failure_history"),
    (jobs, "mark_job_run", "_fox_patched_mark_job_run_failure_history"),
    (scheduler, "run_job", "_fox_patched_run_job_diagnostics"),
    (scheduler, "run_one_job", "_fox_patched_run_one_job_structured_failure"),
    (cronjob_tools, "_format_job", "_fox_patched_format_job_failure_history"),
]


@pytest.fixture(scope="module", autouse=True)
def _apply_patches():
    """Invoke fox-overlay register() once for the whole module run."""
    register(None)


@pytest.mark.parametrize(
    "module, function_name, sentinel",
    SENTINELS,
    ids=[f"{m.__name__}.{fn}" for m, fn, _ in SENTINELS],
)
def test_monkey_patch_sentinel_set(module, function_name, sentinel):
    """Each monkey-patch sets its sentinel attribute on the upstream symbol."""
    fn = getattr(module, function_name)
    assert getattr(fn, sentinel, False) is True, (
        f"{module.__name__}.{function_name} missing {sentinel} sentinel — "
        "monkey-patch did not apply (anchor may have drifted in upstream)"
    )


def test_register_is_idempotent():
    """Repeat register() calls are safe — sentinel short-circuits each apply()."""
    register(None)
    register(None)
    for module, function_name, sentinel in SENTINELS:
        fn = getattr(module, function_name)
        assert getattr(fn, sentinel, False) is True
