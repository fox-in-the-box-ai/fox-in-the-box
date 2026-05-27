"""Fox webui patch: streaming.py — FITB#9 local-fallback plumbing + #303
silent failover engine (v0.7.6 rebuild) + #278 keyless local-server
fallback (v0.7.43).

Four substitutions inside ``_run_agent_streaming``:

0. **FITB#278 keyless local-server fallback.** After
   ``_resolve_custom_provider_runtime_overrides``, supply a keyless
   placeholder API key when the provider is a known local server
   (Ollama, LM Studio, etc.) with a ``base_url`` but no ``api_key``.
   Prevents "no API key found" errors for keyless daemons.
1. **FITB#9 local-fallback plumbing.** If Settings → Providers
   "Local fallback" is ON AND the bundled llama-server is healthy,
   plumb it through as ``_fallback_resolved`` (preempts any
   config-driven fallback).
2. **FITB#303 silent failover — success path.** When upstream's
   classification reports a failover-eligible error (per Fox's
   ``local_fallback.should_failover()`` filter) AND the local
   llama-server is ready, swap to local + emit ``provider_switched``
   instead of ``apperror``. Splices just before
   ``_provider_error_payload(...)`` in the success-path block.
3. **FITB#303 silent failover — exception path.** Same logic as (2)
   but at the exception-handler block (when the agent's
   ``run_conversation()`` raises rather than returning an error
   response). Splices just before ``_provider_error_payload(...)`` in
   the exception-path block.

## Why a wrap-and-splice wasn't an option

Wrap-and-splice (the pattern from v0.7.4 ``_wrap_get_available_models``)
works for post-call mutations of a return value. ``_run_agent_streaming``
is a stream-emitting function (yields nothing, writes SSE events via a
passed handler) — there is no return value to mutate. The right tool
here is in-function substitution.

## Relationship to upstream's self-heal

Upstream's ``_attempt_credential_self_heal()`` already retries
``auth_mismatch`` errors automatically with refreshed credentials. Fox's
failover deliberately filters out ``auth_mismatch`` (via
``_NEVER_FAILOVER_SUBSTRINGS`` in ``local_fallback.py``) so the two
mechanisms don't double-retry. Fox covers what self-heal doesn't:
``rate_limit`` (429), ``no_response``, ``stream_interrupted`` mid-stream
exceptions, and other non-auth/non-quota transient failures.

## What this does NOT do (intentional scope limits)

- Does NOT auto-retry the user's message against the local model.
  Emits ``provider_switched`` and stops the current stream cleanly;
  the user's message stays in the transcript, and their next send
  hits local. Auto-retry was the v0.5.2 behavior but adds real
  complexity (rebuilding the agent + replaying context against a
  potentially different context-window) for marginal UX gain over a
  single re-send tap.
- Does NOT modify the v0.6.1 retry-panel UX. The retry panel still
  fires on ``apperror``; when failover handles the error first,
  ``apperror`` is never emitted, so the panel naturally doesn't show
  — no UI changes needed.
- Does NOT handle ``quota_exhausted`` (filtered out — retrying on
  local doesn't fix a billing-side quota problem; user must address
  their account state).

Self-checks: ``inspect.signature`` on ``_run_agent_streaming`` (catches
signature drift); anchor exactly-once via ``substitute_function`` for
each of the 3 substitutions; per-patch sentinel + apply-level
idempotency guard.
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

    # ── Substitute _run_agent_streaming with 4 anchored edits ───────────
    substitute_function(
        upstream_module=_u,
        function_name="_run_agent_streaming",
        substitutions=[
            # ── (0) FITB#278 keyless local-server fallback ──
            # After _resolve_custom_provider_runtime_overrides, supply a
            # keyless placeholder when the provider is a known local
            # server (Ollama, LM Studio, etc.) with a base_url but no
            # API key. Prevents "no API key found" errors for keyless
            # daemons. Anchor: the _resolve_custom_provider_runtime_overrides
            # call through to "Read per-profile config".
            (
                "            resolved_provider, resolved_api_key, resolved_base_url = _resolve_custom_provider_runtime_overrides(\n"
                "                resolved_provider, resolved_api_key, resolved_base_url\n"
                "            )\n"
                "\n"
                "            # Read per-profile config at call time (not module-level snapshot)\n",

                "            resolved_provider, resolved_api_key, resolved_base_url = _resolve_custom_provider_runtime_overrides(\n"
                "                resolved_provider, resolved_api_key, resolved_base_url\n"
                "            )\n"
                "\n"
                "            # FITB#278: keyless fallback for local server providers.\n"
                "            if not resolved_api_key and resolved_base_url:\n"
                "                from api.config import _is_local_server_provider as _fox_is_local\n"
                "                if _fox_is_local(str(resolved_provider or '')):\n"
                "                    resolved_api_key = _KEYLESS_CUSTOM_API_KEY\n"
                "\n"
                "            # Read per-profile config at call time (not module-level snapshot)\n",
            ),
            # ── (1) FITB#9 local-fallback plumbing ──
            # Insert the local-fallback block right BEFORE "Build kwargs
            # defensively". Anchor includes 3 lines of context to remain
            # unique within the function.
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
            # ── (2) FITB#303 silent failover — success path ──
            # Splice just before _provider_error_payload(...) in the
            # success-path block (post-self-heal). Anchor includes the
            # if-_assistant_added / else / _error_payload structure that
            # is unique to this block (the exception-path block does NOT
            # have the `if _assistant_added:` pre-amble).
            (
                "                    if _assistant_added:\n"
                "                        # Self-heal succeeded: messages are already merged into s,\n"
                "                        # fall through to normal post-result persistence below.\n"
                "                        pass\n"
                "                    else:\n"
                "                        _error_payload = _provider_error_payload(\n",

                "                    if _assistant_added:\n"
                "                        # Self-heal succeeded: messages are already merged into s,\n"
                "                        # fall through to normal post-result persistence below.\n"
                "                        pass\n"
                "                    else:\n"
                "                        # ── FITB v0.7.6 silent failover (success path, #303) ──\n"
                "                        # When upstream's classification says the error is failover-\n"
                "                        # eligible AND the bundled local llama-server is ready, swap\n"
                "                        # to local and emit `provider_switched` instead of apperror.\n"
                "                        # auth_mismatch is excluded by Fox's should_failover() filter\n"
                "                        # (upstream's _attempt_credential_self_heal handles that case\n"
                "                        # automatically); quota_exhausted is excluded because retrying\n"
                "                        # on local doesn't fix a billing-side problem.\n"
                "                        try:\n"
                "                            from fox_overlay.webui_modules import local_fallback as _fitb_lf\n"
                "                            if _fitb_lf.should_failover(_err_str or _err_label, None):\n"
                "                                _fitb_status = _fitb_lf.get_status()\n"
                "                                if _fitb_status.get('ready'):\n"
                "                                    _fitb_result = _fitb_lf.activate()\n"
                "                                    if _fitb_result.get('ok'):\n"
                "                                        put('provider_switched', {\n"
                "                                            'from_provider': resolved_provider or '',\n"
                "                                            'to_provider': 'local',\n"
                "                                            'reason': _err_type or 'failover',\n"
                "                                            'message': 'Switched to local model. Re-send your message to retry.',\n"
                "                                        })\n"
                "                                        _materialize_pending_user_turn_before_error(s)\n"
                "                                        s.active_stream_id = None\n"
                "                                        s.pending_user_message = None\n"
                "                                        s.pending_attachments = []\n"
                "                                        s.pending_started_at = None\n"
                "                                        return\n"
                "                        except Exception:\n"
                "                            logger.exception('[fox-overlay] silent failover (success path) failed; falling through to upstream apperror')\n"
                "                        _error_payload = _provider_error_payload(\n",
            ),
            # ── (3) FITB#303 silent failover — exception path ──
            # Splice just before _provider_error_payload(err_str, _exc_type,
            # _exc_hint) in the exception-handler block. Anchor includes
            # the trailing `else: _exc_label, _exc_type, _exc_hint = 'Error',
            # 'error', ''` line which is unique to the exception path.
            (
                "        else:\n"
                "            _exc_label, _exc_type, _exc_hint = 'Error', 'error', ''\n"
                "\n"
                "        _error_payload = _provider_error_payload(err_str, _exc_type, _exc_hint)\n",

                "        else:\n"
                "            _exc_label, _exc_type, _exc_hint = 'Error', 'error', ''\n"
                "\n"
                "        # ── FITB v0.7.6 silent failover (exception path, #303) ──\n"
                "        # Same logic as the success-path splice. On failover success we\n"
                "        # return without persisting any error message; the user's original\n"
                "        # message stays in the transcript and the next send hits local.\n"
                "        try:\n"
                "            from fox_overlay.webui_modules import local_fallback as _fitb_lf\n"
                "            if _fitb_lf.should_failover(err_str, None):\n"
                "                _fitb_status = _fitb_lf.get_status()\n"
                "                if _fitb_status.get('ready'):\n"
                "                    _fitb_result = _fitb_lf.activate()\n"
                "                    if _fitb_result.get('ok'):\n"
                "                        put('provider_switched', {\n"
                "                            'from_provider': resolved_provider or '',\n"
                "                            'to_provider': 'local',\n"
                "                            'reason': _exc_type or 'failover',\n"
                "                            'message': 'Switched to local model. Re-send your message to retry.',\n"
                "                        })\n"
                "                        return\n"
                "        except Exception:\n"
                "            logger.exception('[fox-overlay] silent failover (exception path) failed; falling through to upstream apperror')\n"
                "\n"
                "        _error_payload = _provider_error_payload(err_str, _exc_type, _exc_hint)\n",
            ),
        ],
        sentinel=_RUN_AGENT_STREAMING_SENTINEL,
    )
