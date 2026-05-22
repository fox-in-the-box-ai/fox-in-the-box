"""Fox webui patch: streaming.py — FITB#9 local-fallback plumbing.

Adds the Fox local-fallback plumbing inside ``_run_agent_streaming``:
if Settings → Providers "Local fallback" is ON AND the bundled
llama-server is healthy, plumb it through as ``_fallback_resolved``
(preempts any config-driven fallback).

Self-checks: ``inspect.signature`` on ``_run_agent_streaming`` (catches
drift outside the anchor; v0.51.84 added ``goal_related=False``); anchor
exactly-once via ``substitute_function``; per-patch sentinel +
apply-level idempotency guard.

**Missing in this patch (intentional, dropped in Phase 8 #241):**
FITB#89 mid-stream-break label and #129b silent auto-failover. They
were 5 of the original 6 hunks and became structurally unmappable when
upstream refactored to ``_classify_provider_error()`` +
``_attempt_credential_self_heal()`` in v0.51.84. Tracked for v0.7.5+
rebuild (see #303 symptom 3). See git history for the original hunks.
"""
import inspect
import logging

from ._helpers import substitute_function

_log = logging.getLogger("fox_overlay.webui_patches.streaming")

_RUN_AGENT_STREAMING_SENTINEL = "_fox_patched_run_agent_streaming"

# Expected upstream signature for _run_agent_streaming.
# v0.51.84 added `goal_related=False`. Refresh both this and any anchors
# when upstream renames a parameter.
_EXPECTED_RUN_AGENT_STREAMING_SIG = (
    "(session_id, msg_text, model, workspace, stream_id, attachments=None, "
    "*, ephemeral=False, model_provider=None, goal_related=False)"
)


def _check_signature(callable_obj, expected: str, label: str) -> None:
    actual = str(inspect.signature(callable_obj))
    if actual != expected:
        raise AssertionError(
            "[fox-overlay] streaming patch: %s signature drift.\n"
            "  expected: %s\n"
            "  actual:   %s\n"
            "Refresh both the expected signature and the substitution "
            "anchors in fox_overlay/webui_patches/streaming.py." % (label, expected, actual)
        )


def apply() -> None:
    from api import streaming as _u

    # Apply-level idempotency.
    if getattr(_u._run_agent_streaming, _RUN_AGENT_STREAMING_SENTINEL, False):
        return

    _check_signature(_u._run_agent_streaming, _EXPECTED_RUN_AGENT_STREAMING_SIG,
                     "_run_agent_streaming")

    # ── Substitute _run_agent_streaming with 1 anchored edit ────────────
    # (Hunks 2-6 from the original Phase 6 patch dropped in Phase 8 follow-
    # up #241 — see module docstring for rationale.)
    substitute_function(
        upstream_module=_u,
        function_name="_run_agent_streaming",
        substitutions=[
            # FITB#9 local-fallback plumbing. Insert the local-fallback block
            # right BEFORE "Build kwargs defensively". Anchor includes 3 lines
            # of context to remain unique within the function.
            (
                "                    }\n"
                "\n"
                "            # Build kwargs defensively — guard newer params so the WebUI\n",

                "                    }\n"
                "\n"
                "            # FITB local AI fallback (issue #9) — opt-in toggle takes\n"
                "            # precedence over any config-driven fallback_model.\n"
                "            try:\n"
                "                from api.local_fallback import get_fallback_endpoint as _fitb_local_fallback\n"
                "                _fitb_endpoint = _fitb_local_fallback()\n"
                "            except Exception:\n"
                "                _fitb_endpoint = None\n"
                "            if _fitb_endpoint:\n"
                "                _fallback_resolved = {\n"
                "                    'model': _fitb_endpoint['model'],\n"
                "                    'provider': _fitb_endpoint['provider'],\n"
                "                    'base_url': _fitb_endpoint['base_url'],\n"
                "                }\n"
                "\n"
                "            # Build kwargs defensively — guard newer params so the WebUI\n",
            ),
        ],
        sentinel=_RUN_AGENT_STREAMING_SENTINEL,
    )
