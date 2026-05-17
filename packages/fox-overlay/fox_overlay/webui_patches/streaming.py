"""Fox webui patch: streaming.py — FITB#9 local-fallback plumbing only.

## Phase 8 refresh history (#241)

Original Fox streaming patch (Phase 6 module 4/5, PR #231) contained
6 substitutions in ``_run_agent_streaming``:

1. FITB#9 local-fallback plumbing (preempt config-driven fallback)
2. FITB#89 token_sent gate change (mid-stream breaks fire apperror)
3. FITB#89 mid-stream-break ``elif _token_sent`` branch
4. FITB#129b silent failover before apperror (success path)
5. FITB#89+129b persistence wrap + partial-text preservation
6. FITB#129b exception-path apperror gating

Phase 8 ATOMIC re-pointed webui at v0.51.84. Upstream's error/self-heal
flow was extensively refactored in the v0.5x line:

* `_classify_provider_error()` — dispatcher replaces Fox's if/elif chain
* `_attempt_credential_self_heal()` — automatic 401 retry (Fox didn't have)
* `_materialize_pending_user_turn_before_error()` — Fox didn't have
* `_provider_error_payload()` — dedicated payload builder
* `_self_healed` state tracking

Hunks 2-6 of Fox's original patch CAN'T be expressed as substitutions
against this new flow — the surrounding context (err_label cascade
+ apperror emission + persistence) is structurally different.

**Phase 8 follow-up #241 decision (per Dennis 2026-05-17 "we do not
care if the product itself is broken at this stage"):** keep ONLY
hunk 1 (FITB#9 local-fallback plumbing — applies cleanly). Hunks 2-6
(FITB#89 mid-stream-break label + #129b silent failover) are
DROPPED. Those features ARE LOST in v0.6.0 — they can be
re-implemented later against upstream's new flow if Fox needs them
back (likely as a different design, since upstream's credential
self-heal already covers part of the #89 use case).

## What this patch still does

* Add FITB local-fallback plumbing inside ``_run_agent_streaming``
  so that if the user has the Settings → Providers "Local fallback"
  toggle ON AND the bundled llama-server is healthy, plumb it
  through as ``_fallback_resolved`` (preempts any config-driven
  fallback).

## What it NO LONGER does (regressions in v0.6.0 vs v0.5.x)

* FITB#89 mid-stream break detection — provider drops connection
  mid-stream → Fox previously emitted ``Stream interrupted`` label
  with partial-text preservation. Now: upstream's classification
  applies (no special label).
* FITB#129b silent failover to local on auth/quota errors — Fox
  previously swapped the gateway's active model to local when
  errors hit AND local was ready. Now: upstream's apperror surfaces
  to the user; user must manually switch in Settings.

## Self-checks

* ``inspect.signature`` self-check on ``_run_agent_streaming``
  (catches drift outside anchor; v0.51.84 adds ``goal_related=False``)
* Anchor self-check via ``substitute_function`` (each anchor MUST
  appear exactly once)
* Per-patch sentinel + apply-level idempotency guard
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
