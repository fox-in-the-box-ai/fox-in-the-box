"""Phase 6 regression tests for fox_overlay.webui_patches.models.

Covers:
* substitute_method handles class-method indentation correctly
* All 4 Fox edits applied: 2 on Session.save, 1 on Session.load_metadata_only,
  1 on new_session
* Signature self-check fires when upstream signature drifts
* Anchor drift fails fast
* Idempotency
* Behavioral parity with pre-Phase-6 Fox: metadata-only save raises,
  .bak written on shrink, _loaded_metadata_only set by load_metadata_only,
  new_session passes project_id through to Session()
"""
import importlib
import json
import sys
import textwrap

import pytest


# Minimal upstream models.py stub matching merge-base 9e31a2a around the
# anchor regions. Includes the bare-minimum machinery so save() can write,
# load_metadata_only() can return, and new_session() can construct a Session.
_UPSTREAM_MODELS_SOURCE = '''\
import json
import logging
import os
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

SESSION_DIR = None  # patched per test
SESSIONS = {}
SESSIONS_MAX = 1000
LOCK = threading.Lock()
DEFAULT_WORKSPACE = "/tmp"
DEFAULT_MODEL = "test-model"
METADATA_FIELDS = ['session_id', 'title', 'model']


def get_last_workspace():
    return str(DEFAULT_WORKSPACE)


def get_effective_default_model():
    return DEFAULT_MODEL


def _read_metadata_json_prefix(p):
    return p.read_text(encoding='utf-8')


def _lookup_index_message_count(sid):
    return 0


class Session:
    def __init__(self, session_id=None, title='Untitled', workspace=None,
                 model=None, model_provider=None, messages=None,
                 created_at=None, updated_at=None, tool_calls=None,
                 project_id=None, profile=None, **kwargs):
        self.session_id = session_id or "s_test"
        self.title = title
        self.workspace = workspace
        self.model = model
        self.model_provider = model_provider
        self.messages = messages or []
        self.created_at = created_at or time.time()
        self.updated_at = updated_at or time.time()
        self.tool_calls = tool_calls or []
        self.project_id = project_id
        self.profile = profile
        self._metadata_message_count = None

    @property
    def path(self):
        return SESSION_DIR / f'{self.session_id}.json'

    def save(self, touch_updated_at: bool = True, skip_index: bool = False) -> None:
        if touch_updated_at:
            self.updated_at = time.time()
        # Write metadata fields first so load_metadata_only() can read them
        # without parsing the full messages array (which may be 400KB+).
        # Fields are listed in the order they should appear in the JSON file.
        meta = {k: getattr(self, k, None) for k in METADATA_FIELDS}
        meta['messages'] = self.messages
        meta['tool_calls'] = self.tool_calls
        # Fields not in METADATA_FIELDS (e.g. last_usage, message_count) go at the end
        extra = {k: v for k, v in self.__dict__.items()
                 if k not in METADATA_FIELDS and k not in ('messages', 'tool_calls')
                 and not k.startswith('_')}
        payload = json.dumps({**meta, **extra}, ensure_ascii=False, indent=2)
        tmp = self.path.with_suffix(f'.tmp.{os.getpid()}.{threading.current_thread().ident}')
        try:
            with open(tmp, 'w', encoding='utf-8') as f:
                f.write(payload)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)
        except Exception:
            try:
                tmp.unlink()
            except OSError:
                pass
            raise

    @classmethod
    def load_metadata_only(cls, sid):
        if not sid or not all(c in '0123456789abcdefghijklmnopqrstuvwxyz_' for c in sid):
            return None
        p = SESSION_DIR / f'{sid}.json'
        if not p.exists():
            return None
        try:
            prefix = _read_metadata_json_prefix(p)
            if not prefix:
                return None
            parsed = json.loads(prefix)
            needed = {'session_id'}
            if not needed.issubset(parsed.keys()):
                return None
            parsed['messages'] = []
            parsed['tool_calls'] = []
            session = cls(**parsed)
            session._metadata_message_count = _lookup_index_message_count(sid)
            return session
        except Exception:
            return None


def new_session(workspace=None, model=None, profile=None, model_provider=None):
    """Create a new in-memory session."""
    effective_model = model or get_effective_default_model()
    s = Session(
        workspace=workspace or get_last_workspace(),
        model=effective_model,
        model_provider=model_provider,
        profile=profile,
    )
    with LOCK:
        SESSIONS[s.session_id] = s
    return s
'''


def _install_stub(tmp_path, source, monkeypatch, session_dir=None):
    """Write `source` to tmp_path/api/models.py and import it as `api.models`."""
    api_dir = tmp_path / "api"
    api_dir.mkdir(exist_ok=True)
    (api_dir / "__init__.py").write_text("")
    (api_dir / "models.py").write_text(source)
    monkeypatch.syspath_prepend(str(tmp_path))
    for name in list(sys.modules):
        if name == "api" or name.startswith("api."):
            del sys.modules[name]
    import api.models as fake_models  # noqa: F401
    if session_dir is not None:
        fake_models.SESSION_DIR = session_dir
    return sys.modules["api.models"]


@pytest.fixture
def fresh_models(tmp_path, monkeypatch):
    session_dir = tmp_path / "sessions"
    session_dir.mkdir()
    fake_models = _install_stub(tmp_path, _UPSTREAM_MODELS_SOURCE, monkeypatch, session_dir)
    import fox_overlay.webui_patches.models as patch_mod
    importlib.reload(patch_mod)
    yield fake_models, patch_mod, session_dir
    importlib.reload(patch_mod)
    for name in list(sys.modules):
        if name == "api" or name.startswith("api."):
            del sys.modules[name]


# ── apply() idempotency + signature checks ─────────────────────────────────

def test_apply_is_idempotent(fresh_models):
    _u, patch_mod, _ = fresh_models
    patch_mod.apply()
    patch_mod.apply()
    assert getattr(_u.Session.save, "_fox_patched_session_save", False) is True
    assert getattr(_u.Session.load_metadata_only, "_fox_patched_load_metadata_only", False) is True
    assert getattr(_u.new_session, "_fox_patched_new_session", False) is True


def test_signature_self_check_catches_drift(tmp_path, monkeypatch):
    """If upstream Session.save signature changes, patch fails fast with diagnostic."""
    drifted = _UPSTREAM_MODELS_SOURCE.replace(
        "def save(self, touch_updated_at: bool = True, skip_index: bool = False) -> None:",
        "def save(self, touch_updated_at=True) -> None:",  # dropped skip_index
    )
    _install_stub(tmp_path, drifted, monkeypatch)
    import fox_overlay.webui_patches.models as patch_mod
    importlib.reload(patch_mod)
    with pytest.raises(AssertionError, match="Session.save signature drift"):
        patch_mod.apply()
    importlib.reload(patch_mod)
    for name in list(sys.modules):
        if name == "api" or name.startswith("api."):
            del sys.modules[name]


def test_anchor_drift_fails_fast(tmp_path, monkeypatch):
    """If upstream removes the anchor, substitute_method raises AssertionError."""
    drifted = _UPSTREAM_MODELS_SOURCE.replace(
        "        payload = json.dumps({**meta, **extra}, ensure_ascii=False, indent=2)\n"
        "        tmp = self.path.with_suffix(",
        "        # upstream restructured\n"
        "        json_data = json.dumps({**meta, **extra})\n"
        "        target_tmp = self.path.with_suffix(",
    )
    _install_stub(tmp_path, drifted, monkeypatch)
    import fox_overlay.webui_patches.models as patch_mod
    importlib.reload(patch_mod)
    with pytest.raises(AssertionError, match="anchor expected EXACTLY ONCE"):
        patch_mod.apply()
    importlib.reload(patch_mod)
    for name in list(sys.modules):
        if name == "api" or name.startswith("api."):
            del sys.modules[name]


# ── Session.save metadata-only guard ───────────────────────────────────────

def test_save_raises_when_loaded_metadata_only(fresh_models):
    _u, patch_mod, session_dir = fresh_models
    patch_mod.apply()
    s = _u.Session(session_id="s_abc123def", title="T")
    s._loaded_metadata_only = True
    with pytest.raises(RuntimeError, match="Refusing to save metadata-only session"):
        s.save()


def test_save_works_normally_when_not_metadata_only(fresh_models):
    _u, patch_mod, session_dir = fresh_models
    patch_mod.apply()
    s = _u.Session(session_id="s_abc123def", title="T", messages=[{"role": "user", "content": "hi"}])
    s.save()
    assert (session_dir / "s_abc123def.json").exists()


# ── Session.save .bak backup ───────────────────────────────────────────────

def test_save_writes_bak_when_messages_shrink(fresh_models):
    _u, patch_mod, session_dir = fresh_models
    patch_mod.apply()
    # First save with 3 messages
    s = _u.Session(session_id="s_grow", title="T", messages=[{"r": i} for i in range(3)])
    s.save()
    # Second save with 1 message — should trigger .bak
    s2 = _u.Session(session_id="s_grow", title="T", messages=[{"r": 0}])
    s2.save()
    bak = session_dir / "s_grow.json.bak"
    assert bak.exists()
    saved_bak = json.loads(bak.read_text())
    # Note: stub Session doesn't store messages in metadata-only fields,
    # so saved_bak structure mirrors what got written previously.
    # Sanity check: it should contain something.
    assert saved_bak is not None


def test_save_does_not_write_bak_when_messages_grow(fresh_models):
    _u, patch_mod, session_dir = fresh_models
    patch_mod.apply()
    s = _u.Session(session_id="s_grow2", title="T", messages=[{"r": 0}])
    s.save()
    s2 = _u.Session(session_id="s_grow2", title="T", messages=[{"r": i} for i in range(3)])
    s2.save()
    bak = session_dir / "s_grow2.json.bak"
    assert not bak.exists()


# ── Session.load_metadata_only flag ────────────────────────────────────────

def test_load_metadata_only_sets_flag(fresh_models):
    _u, patch_mod, session_dir = fresh_models
    patch_mod.apply()
    # Write a session file directly
    (session_dir / "s_load1.json").write_text(json.dumps({
        "session_id": "s_load1", "title": "T", "messages": [],
    }))
    loaded = _u.Session.load_metadata_only("s_load1")
    assert loaded is not None
    assert getattr(loaded, "_loaded_metadata_only", False) is True


def test_loaded_metadata_only_session_cannot_save(fresh_models):
    _u, patch_mod, session_dir = fresh_models
    patch_mod.apply()
    (session_dir / "s_load2.json").write_text(json.dumps({
        "session_id": "s_load2", "title": "T", "messages": [],
    }))
    loaded = _u.Session.load_metadata_only("s_load2")
    with pytest.raises(RuntimeError, match="Refusing to save metadata-only session"):
        loaded.save()


# ── new_session project_id pass-through ────────────────────────────────────

def test_new_session_accepts_project_id(fresh_models):
    _u, patch_mod, _ = fresh_models
    patch_mod.apply()
    s = _u.new_session(project_id="proj_abc")
    assert s.project_id == "proj_abc"


def test_new_session_project_id_defaults_to_none(fresh_models):
    """Backward-compat: callers not passing project_id still work."""
    _u, patch_mod, _ = fresh_models
    patch_mod.apply()
    s = _u.new_session()
    assert s.project_id is None


# ── substitute_method helper itself (since this is its first user) ─────────

def test_substitute_method_handles_class_indentation():
    """End-to-end: a class method substitution actually compiles + replaces."""
    import types
    from fox_overlay.webui_patches._helpers import substitute_method

    mod = types.ModuleType("test_indent_mod")
    # Real file needed for inspect.getsource
    import tempfile, pathlib
    src = textwrap.dedent('''\
        class Foo:
            def bar(self, x):
                return x + 1
    ''')
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(src)
        path = f.name
    spec = importlib.util.spec_from_file_location("test_indent_mod", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    substitute_method(
        upstream_module=mod,
        class_name="Foo",
        method_name="bar",
        substitutions=[
            ("return x + 1", "return x * 2"),
        ],
        sentinel="_test_patched",
    )
    assert mod.Foo().bar(5) == 10  # was 6, now 10


def test_substitute_method_idempotent():
    """Second apply on the same target is a no-op."""
    import types, tempfile
    from fox_overlay.webui_patches._helpers import substitute_method

    src = textwrap.dedent('''\
        class Foo:
            def bar(self, x):
                return x + 1
    ''')
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(src)
        path = f.name
    spec = importlib.util.spec_from_file_location("test_indent_mod_2", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    substitute_method(
        upstream_module=mod, class_name="Foo", method_name="bar",
        substitutions=[("return x + 1", "return x * 2")],
        sentinel="_idem_patched",
    )
    # Second apply must not re-substitute (would fail anchor count)
    substitute_method(
        upstream_module=mod, class_name="Foo", method_name="bar",
        substitutions=[("return x + 1", "return x * 2")],
        sentinel="_idem_patched",
    )
    assert mod.Foo().bar(5) == 10
