"""Fox webui patch: streaming.py — local-fallback plumbing + #89 mid-stream break + #129b silent failover.

Re-applies the Fox edits to ``api/streaming.py`` reverted to upstream
merge-base in fork PR fox-in-the-box-ai/hermes-webui#NN (Phase 6
fork-side, parent #189). Closes monorepo issue #191.

## Fox edits restored

### Module-scope additions (direct attribute assignment)

* ``_FAILOVER_ELIGIBLE_TYPES`` — frozenset of error types that qualify
  for silent failover to the local model.
* ``_attempt_failover`` — decision-tree helper called by the patched
  ``_run_agent_streaming``. Lives here, assigned to ``api.streaming``
  module scope so the patched body can call it by bare name.

### Function substitutions (all in _run_agent_streaming)

6 substitutions across the ~700-line ``_run_agent_streaming`` function:

1. **FITB#9 local-fallback plumbing** — if the user has the Settings
   toggle on AND llama-server is healthy, set ``_fallback_resolved``
   to the local endpoint (preempts any config-driven fallback).
2. **FITB#89 token_sent gate** — change ``if not _assistant_added and
   not _token_sent`` to ``if not _assistant_added`` so mid-stream
   breaks (provider drop after partial tokens) ALSO surface as an
   apperror instead of silent failures.
3. **FITB#89 mid-stream break branch** — add ``elif _token_sent`` to
   the err_label cascade.
4. **FITB#129b failover decision (success path)** — call
   ``_attempt_failover`` before emitting apperror; suppress apperror
   if failover took it.
5. **FITB#89+129b persistence wrap** — skip persisting the error
   message if failover succeeded; preserve partial streamed text if
   one was visible (chat bubble doesn't appear to vanish on reload).
6. **FITB#129b exception path** (2 sub-edits): compute
   ``_exc_did_failover`` before persistence; gate both the
   ``s.messages.append`` and the ``put('apperror', ...)`` on
   ``not _exc_did_failover``.

## Self-checks

* ``inspect.signature`` self-check on ``_run_agent_streaming`` —
  catches upstream parameter-list drift outside the anchor regions.
* ``substitute_function`` anchor self-check (each anchor MUST appear
  exactly once in the target function source).
* Per-patch sentinel + apply-level idempotency guard.
"""
import inspect
import logging

from ._helpers import substitute_function

_log = logging.getLogger("fox_overlay.webui_patches.streaming")

_RUN_AGENT_STREAMING_SENTINEL = "_fox_patched_run_agent_streaming"

# Expected upstream signature for _run_agent_streaming. Catches drift
# outside the anchor regions (e.g. a new kwarg). Verbatim from upstream
# merge-base 9e31a2a — refresh both this and the anchors when upstream
# renames a parameter.
_EXPECTED_RUN_AGENT_STREAMING_SIG = (
    "(session_id, msg_text, model, workspace, stream_id, attachments=None, "
    "*, ephemeral=False, model_provider=None)"
)

# Eligibility set is broader than local_fallback.should_failover()'s
# substring matcher (which excludes auth/quota for "don't mask config
# errors"). The v0.5.2 design call: BEST UX — chat must work. Local IS
# a working model regardless of why cloud failed.
_FAILOVER_ELIGIBLE_TYPES = frozenset({
    'auth_mismatch', 'quota_exhausted',
    'stream_interrupted', 'no_response',
    'unknown', 'model_not_found',
})


def _attempt_failover(err_type, token_sent, put, stream_id):
    """Decide whether to silent-failover this error to the local model.

    Returns True if the failover handled the error (caller should NOT
    emit apperror but SHOULD still do its normal stream-state cleanup).
    Returns False if the caller should continue with apperror as today.

    Decision tree (FITB#129b, v0.5.2 locked design):
      err_type not eligible           -> False
      fallback disabled               -> False
      fallback enabled + ready        -> activate, emit provider_switched, True
      fallback enabled + no model     -> emit local_fallback_unprepared, True
      fallback enabled + unhealthy    -> False
    """
    if err_type not in _FAILOVER_ELIGIBLE_TYPES:
        return False
    try:
        from api.local_fallback import is_enabled, get_status, activate, LLAMA_SERVER_BASE_URL
    except Exception:
        return False
    if not is_enabled():
        return False
    # If active model is already local, this error came FROM local — don't loop.
    try:
        from api.config import get_config
        active_cfg = (get_config() or {}).get('model') or {}
        if str(active_cfg.get('base_url') or '').rstrip('/') == LLAMA_SERVER_BASE_URL.rstrip('/'):
            return False
    except Exception:
        pass

    # Forward-declare for the import-failure path above; satisfies linters.
    from api.local_fallback import STREAM_PARTIAL_TEXT  # type: ignore[attr-defined]  # noqa: F401

    snap = get_status()
    if snap.get('ready'):
        if token_sent:
            put('partial_response_truncated', {'reason': err_type})
            # Drop accumulated partial text — see the equivalent line in
            # the patched _run_agent_streaming body.
            try:
                from api.streaming import STREAM_PARTIAL_TEXT as _SPT
                _SPT.pop(stream_id, None)
            except Exception:
                pass
        result = activate()
        if not result.get('ok'):
            _log.warning("[fox-overlay] streaming: fallback activate() failed: %s",
                         result.get('error'))
            return False
        put('provider_switched', {
            'from_type': err_type,
            'to_provider': result.get('provider', 'custom'),
            'to_model': result.get('active_model'),
            'message': "Switched to local model.",
        })
        return True
    if not snap.get('model_installed'):
        put('local_fallback_unprepared', {
            'reason': err_type,
            'fallback_state': snap.get('ui_state'),
            'model_id': snap.get('model_id'),
            'model_size_bytes': snap.get('model_size_bytes'),
        })
        return True
    return False


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

    # Add module-scope helpers BEFORE substitution so the patched body
    # can reference them by bare name in its globals namespace.
    _u._FAILOVER_ELIGIBLE_TYPES = _FAILOVER_ELIGIBLE_TYPES
    _u._attempt_failover = _attempt_failover

    # ── Substitute _run_agent_streaming with 6 anchored edits ───────────
    substitute_function(
        upstream_module=_u,
        function_name="_run_agent_streaming",
        substitutions=[
            # ── #1: FITB#9 local-fallback plumbing ─────────────────────
            # Insert the local-fallback block right BEFORE "Build kwargs
            # defensively". The anchor includes 3 lines of context so it
            # remains unique within the function.
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
            # ── #2: FITB#89 token_sent gate change ─────────────────────
            # `if not _assistant_added and not _token_sent` → `if not _assistant_added`
            # so mid-stream breaks ALSO surface as apperror.
            (
                "                # _token_sent tracks whether on_token() was called (any streamed text)\n"
                "                if not _assistant_added and not _token_sent:\n",
                "                # _token_sent tracks whether on_token() was called (any streamed text)\n"
                "                # Fox #89: drop the `not _token_sent` gate so mid-stream breaks\n"
                "                # (provider drop after partial tokens) also surface as apperror.\n"
                "                if not _assistant_added:\n",
            ),
            # ── #3: FITB#89 mid-stream break branch ────────────────────
            # Add an `elif _token_sent:` between the `elif _is_auth:` block
            # and the `else: 'No response received'` block.
            (
                "                    else:\n"
                "                        _err_label = 'No response received'\n"
                "                        _err_type = 'no_response'\n"
                "                        _err_hint = 'Verify your API key is valid and the selected model is available for your account.'\n"
                "                    put('apperror', {\n"
                "                        'message': _err_str or f'{_err_label}.',\n"
                "                        'type': _err_type,\n"
                "                        'hint': _err_hint,\n"
                "                    })\n",
                "                    elif _token_sent:\n"
                "                        # Fox #89: mid-stream break — user already saw partial text.\n"
                "                        _err_label = 'Stream interrupted'\n"
                "                        _err_type = 'stream_interrupted'\n"
                "                        _err_hint = 'The provider closed the connection before the response completed. Send the message again to retry.'\n"
                "                    else:\n"
                "                        _err_label = 'No response received'\n"
                "                        _err_type = 'no_response'\n"
                "                        _err_hint = 'Verify your API key is valid and the selected model is available for your account.'\n"
                "                    # Fox #129b: try silent failover before emitting apperror.\n"
                "                    _did_failover = _attempt_failover(_err_type, _token_sent, put, stream_id)\n"
                "                    if not _did_failover:\n"
                "                        put('apperror', {\n"
                "                            'message': _err_str or f'{_err_label}.',\n"
                "                            'type': _err_type,\n"
                "                            'hint': _err_hint,\n"
                "                        })\n",
            ),
            # ── #4: FITB#89+129b persistence wrap (silent-failure path) ─
            # Wrap the s.messages.append in `if not _did_failover`; add
            # partial-text preservation.
            (
                "                    s.active_stream_id = None\n"
                "                    s.pending_user_message = None\n"
                "                    s.pending_attachments = []\n"
                "                    s.pending_started_at = None\n"
                "                    s.messages.append({\n"
                "                        'role': 'assistant',\n"
                "                        'content': f'**{_err_label}:** {_err_str or _err_label}\\n\\n*{_err_hint}*',\n"
                "                        'timestamp': int(time.time()),\n"
                "                        '_error': True,\n"
                "                    })\n"
                "                    try:\n"
                "                        s.save()\n"
                "                    except Exception:\n"
                "                        pass\n"
                "                    return  # apperror already closes the stream on the client side\n",

                "                    s.active_stream_id = None\n"
                "                    s.pending_user_message = None\n"
                "                    s.pending_attachments = []\n"
                "                    s.pending_started_at = None\n"
                "                    # Fox #129b: skip persisting an error message if we\n"
                "                    # silently failed over — the chat history shouldn't\n"
                "                    # show an error the user effectively never saw.\n"
                "                    if not _did_failover:\n"
                "                        # Fox #89: preserve partial streamed text on reload.\n"
                "                        _partial = STREAM_PARTIAL_TEXT.get(stream_id, '') if _token_sent else ''\n"
                "                        if _partial:\n"
                "                            _persist_content = (\n"
                "                                f\"{_partial}\\n\\n*[Stream interrupted: {_err_label}\"\n"
                "                                + (f' — {_err_str}' if _err_str else '')\n"
                "                                + ']*'\n"
                "                            )\n"
                "                        else:\n"
                "                            _persist_content = f'**{_err_label}:** {_err_str or _err_label}\\n\\n*{_err_hint}*'\n"
                "                        s.messages.append({\n"
                "                            'role': 'assistant',\n"
                "                            'content': _persist_content,\n"
                "                            'timestamp': int(time.time()),\n"
                "                            '_error': True,\n"
                "                        })\n"
                "                    try:\n"
                "                        s.save()\n"
                "                    except Exception:\n"
                "                        pass\n"
                "                    return  # apperror or provider_switched already closed the stream\n",
            ),
            # ── #5: FITB#129b exception-path failover decision ─────────
            # Insert _exc_did_failover BEFORE the if-s-is-not-None block.
            (
                "        else:\n"
                "            _exc_label, _exc_type, _exc_hint = 'Error', 'error', ''\n"
                "        if s is not None:\n",
                "        else:\n"
                "            _exc_label, _exc_type, _exc_hint = 'Error', 'error', ''\n"
                "        # Fox #129b: decide failover BEFORE persistence + apperror so\n"
                "        # both branches respect the silent-failover outcome.\n"
                "        _exc_did_failover = _attempt_failover(_exc_type, _token_sent, put, stream_id)\n"
                "        if s is not None:\n",
            ),
            # ── #6: FITB#129b exception-path persistence + apperror ────
            # Wrap messages.append in `if not _exc_did_failover` (with
            # partial-text preservation) + wrap the apperror put.
            (
                "                s.active_stream_id = None\n"
                "                s.pending_user_message = None\n"
                "                s.pending_attachments = []\n"
                "                s.pending_started_at = None\n"
                "                s.messages.append({\n"
                "                    'role': 'assistant',\n"
                "                    'content': f'**{_exc_label}:** {err_str}' + (f'\\n\\n*{_exc_hint}*' if _exc_hint else ''),\n"
                "                    'timestamp': int(time.time()),\n"
                "                    '_error': True,\n"
                "                })\n"
                "                try:\n"
                "                    s.save()\n"
                "                except Exception:\n"
                "                    pass\n"
                "        _apperror_payload: dict = {'message': err_str, 'type': _exc_type}\n"
                "        if _exc_hint:\n"
                "            _apperror_payload['hint'] = _exc_hint\n"
                "        put('apperror', _apperror_payload)\n",

                "                s.active_stream_id = None\n"
                "                s.pending_user_message = None\n"
                "                s.pending_attachments = []\n"
                "                s.pending_started_at = None\n"
                "                # Fox #129b: skip persisting an error message if we\n"
                "                # silently failed over.\n"
                "                if not _exc_did_failover:\n"
                "                    # Fox #89: preserve partial streamed text on reload.\n"
                "                    _exc_partial = STREAM_PARTIAL_TEXT.get(stream_id, '')\n"
                "                    if _exc_partial:\n"
                "                        _exc_persist = (\n"
                "                            f\"{_exc_partial}\\n\\n*[Stream interrupted: {_exc_label}\"\n"
                "                            + (f' — {err_str}' if err_str else '')\n"
                "                            + ']*'\n"
                "                            + (f'\\n*{_exc_hint}*' if _exc_hint else '')\n"
                "                        )\n"
                "                    else:\n"
                "                        _exc_persist = (\n"
                "                            f'**{_exc_label}:** {err_str}'\n"
                "                            + (f'\\n\\n*{_exc_hint}*' if _exc_hint else '')\n"
                "                        )\n"
                "                    s.messages.append({\n"
                "                        'role': 'assistant',\n"
                "                        'content': _exc_persist,\n"
                "                        'timestamp': int(time.time()),\n"
                "                        '_error': True,\n"
                "                    })\n"
                "                try:\n"
                "                    s.save()\n"
                "                except Exception:\n"
                "                    pass\n"
                "        # Fox #129b: only emit apperror if we did NOT failover.\n"
                "        if not _exc_did_failover:\n"
                "            _apperror_payload: dict = {'message': err_str, 'type': _exc_type}\n"
                "            if _exc_hint:\n"
                "                _apperror_payload['hint'] = _exc_hint\n"
                "            put('apperror', _apperror_payload)\n",
            ),
        ],
        sentinel=_RUN_AGENT_STREAMING_SENTINEL,
    )
