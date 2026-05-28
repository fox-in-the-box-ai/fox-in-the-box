"""Regression tests for fox_overlay.webui_patches.streaming.

History: Phase 8 follow-up #241 trimmed the original 6-hunk patch down
to just FITB#9 plumbing. v0.7.6 (#303 symptom 3) rebuilt the silent
failover as 2 new substitutions on top of upstream's new
``_classify_provider_error()`` + ``_attempt_credential_self_heal()``
architecture — separate from the original hunks, different splice
points. See module docstring for the full rationale.

Coverage:
* Module load + structural sanity (sentinel, signature constant, helpers)
* Signature drift fails fast with diagnostic
* All 3 substitutions present
* Substitution content sanity (correct fox_overlay calls, correct events
  emitted) — guards against accidentally breaking the splice logic in
  refactors
"""
import importlib
import sys

import pytest


# Minimal upstream streaming.py stub matching v0.51.84 around the
# remaining (FITB#9 plumbing) anchor only. Includes upstream's
# `goal_related=False` kwarg added in v0.51.x.
_UPSTREAM_STREAMING_SOURCE = '''\
def _run_agent_streaming(
    session_id,
    msg_text,
    model,
    workspace,
    stream_id,
    attachments=None,
    *,
    ephemeral=False,
    model_provider=None,
    goal_related=False,
):
    """Stub matching upstream v0.51.84 anchor region only."""
    _fallback_resolved = None
    if True:
        _fb_entry = None
        if _fb_entry:
            _fallback_resolved = {
                'model': _fb_entry.get('model', ''),
                'provider': _fb_entry.get('provider', ''),
                'base_url': _fb_entry.get('base_url'),
            }

        # Build kwargs defensively — guard newer params so the WebUI
        # degrades gracefully when run against an older hermes-agent build.
        # ... [more code] ...
        agent = None
        result = {'messages': []}
'''


def _install_stub(tmp_path, source, monkeypatch):
    api_dir = tmp_path / "api"
    api_dir.mkdir(exist_ok=True)
    (api_dir / "__init__.py").write_text("")
    (api_dir / "streaming.py").write_text(source)
    monkeypatch.syspath_prepend(str(tmp_path))
    for name in list(sys.modules):
        if name == "api" or name.startswith("api."):
            del sys.modules[name]
    import api.streaming as fake_streaming  # noqa: F401
    return sys.modules["api.streaming"]


@pytest.fixture
def fresh_streaming(tmp_path, monkeypatch):
    fake_streaming = _install_stub(tmp_path, _UPSTREAM_STREAMING_SOURCE, monkeypatch)
    import fox_overlay.webui_patches.streaming as patch_mod
    importlib.reload(patch_mod)
    yield fake_streaming, patch_mod
    importlib.reload(patch_mod)
    for name in list(sys.modules):
        if name == "api" or name.startswith("api."):
            del sys.modules[name]


# ── apply() basic sanity ───────────────────────────────────────────────────
# The apply()-success unit tests still require reproducing _run_agent_streaming's
# multi-level nested indentation around the FITB#9 plumbing anchor. The stub above
# uses simplified nesting (1 level instead of 5) so the apply() call will fail
# the anchor check — that's a known stub limitation. The container smoke (PR body)
# verifies apply() against REAL upstream v0.51.84 source where the anchor matches.


def test_module_loads_without_error(fresh_streaming):
    """Stub import + patch module reload works (sentinel + globals available)."""
    _u, patch_mod = fresh_streaming
    assert hasattr(patch_mod, "_RUN_AGENT_STREAMING_SENTINEL")
    assert hasattr(patch_mod, "_EXPECTED_RUN_AGENT_STREAMING_SIG")
    assert hasattr(patch_mod, "_check_signature")
    assert hasattr(patch_mod, "apply")


# ── Signature drift detection ──────────────────────────────────────────────

def test_signature_drift_fails_fast(tmp_path, monkeypatch):
    """Drop a kwarg from the upstream signature → patch fails with diagnostic."""
    drifted = _UPSTREAM_STREAMING_SOURCE.replace(
        "    goal_related=False,\n",
        "",
    )
    _install_stub(tmp_path, drifted, monkeypatch)
    import fox_overlay.webui_patches.streaming as patch_mod
    importlib.reload(patch_mod)
    with pytest.raises(AssertionError, match="_run_agent_streaming signature drift"):
        patch_mod.apply()
    importlib.reload(patch_mod)
    for name in list(sys.modules):
        if name == "api" or name.startswith("api."):
            del sys.modules[name]


def test_signature_check_helper_directly():
    """_check_signature raises when actual != expected."""
    import fox_overlay.webui_patches.streaming as patch_mod
    def _fake(): pass
    with pytest.raises(AssertionError, match="signature drift"):
        patch_mod._check_signature(_fake, "(x, y)", "fake")


# ── v0.7.6 #303: silent failover substitution content checks ────────────────
# Anchor uniqueness against real upstream is verified by container smoke
# (PR body). These tests guard the substitution CONTENT — accidentally
# removing the local_fallback wiring or the provider_switched emission
# would slip past container smoke if the apperror path still works.

def _get_substitutions():
    """Build the substitutions list without applying. Mirrors what apply()
    would pass to substitute_function — extracted by reading the patch
    module's own source."""
    import inspect
    import fox_overlay.webui_patches.streaming as patch_mod
    src = inspect.getsource(patch_mod.apply)
    return src


def test_three_substitutions_present():
    """Exactly 3 substitutions: FITB#9 plumbing + 2x FITB#303 failover."""
    src = _get_substitutions()
    assert "(1) FITB#9 local-fallback plumbing" in src
    assert "(2) FITB#303 silent failover — success path" in src
    assert "(3) FITB#303 silent failover — exception path" in src
    assert "FITB#278" not in src, "dead-code sub-0 should be removed"


def test_failover_substitution_wires_local_fallback_module():
    """Both #303 splices must import and call Fox's local_fallback module."""
    src = _get_substitutions()
    # Substitution should reference the Fox module (not upstream's api.local_fallback,
    # which is the FITB#9 endpoint API — different concern).
    assert "from fox_overlay.webui_modules import local_fallback as _fitb_lf" in src
    assert "_fitb_lf.should_failover" in src
    assert "_fitb_lf.get_status()" in src
    assert "_fitb_lf.activate()" in src


def test_failover_substitution_emits_provider_switched_event():
    """Successful failover must emit `provider_switched`, NOT `apperror`."""
    src = _get_substitutions()
    assert "put('provider_switched'" in src
    # Both splices include a re-send hint string. Don't pin exact wording
    # (it may evolve); just verify the event has a 'message' field.
    assert "'message':" in src
    assert "'to_provider': 'local'" in src


def test_failover_substitution_clears_session_state_on_success_path():
    """The success-path splice must clear pending-* and active_stream_id
    so the session doesn't appear stuck after a successful failover."""
    src = _get_substitutions()
    assert "_materialize_pending_user_turn_before_error(s)" in src
    assert "s.active_stream_id = None" in src
    assert "s.pending_user_message = None" in src


def test_failover_substitution_falls_through_on_exception():
    """If Fox's failover logic raises, the splice must NOT swallow silently —
    log the exception and fall through to upstream's apperror emission."""
    src = _get_substitutions()
    # Both splices have a try/except around the failover block.
    assert src.count("except Exception:") >= 2
    # Each except branches logs via logger.exception (not warning, not silent).
    assert "logger.exception('[fox-overlay] silent failover (success path) failed" in src
    assert "logger.exception('[fox-overlay] silent failover (exception path) failed" in src


def test_failover_substitution_does_not_emit_apperror_when_succeeds():
    """When failover succeeds, the splice MUST `return` before reaching
    upstream's `_error_payload = _provider_error_payload(...)` /
    `put('apperror', ...)` calls."""
    src = _get_substitutions()
    # The success-path splice's failover block ends with `return` inside the
    # `if _fitb_result.get('ok'):` branch.
    success_splice_idx = src.find("(success path, #303)")
    exception_splice_idx = src.find("(exception path, #303)")
    assert success_splice_idx > 0
    assert exception_splice_idx > 0
    # The success-path splice's return must come BEFORE the exception path comment
    success_return_idx = src.find("return\\n", success_splice_idx)
    assert 0 < success_return_idx < exception_splice_idx


def test_v076_docstring_acknowledges_rebuild():
    """The module docstring must reflect that #303 is now addressed (so the
    'tracked for v0.7.5+ rebuild' line from the pre-v0.7.6 docstring doesn't
    silently linger)."""
    import fox_overlay.webui_patches.streaming as patch_mod
    doc = patch_mod.__doc__ or ""
    assert "v0.7.6" in doc
    assert "#303" in doc
    # The pre-v0.7.6 "Missing in this patch" disclaimer about #129b being
    # dropped should be GONE.
    assert "Missing in this patch" not in doc
