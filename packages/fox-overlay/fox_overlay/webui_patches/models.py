"""Fox webui patch: models.py — #1558 metadata-only save guard, .bak backup, project_id pass-through.

Re-applies 4 Fox edits to ``api/models.py`` reverted to upstream
merge-base in fork PR fox-in-the-box-ai/hermes-webui#NN (Phase 6
fork-side, parent #189). Closes monorepo issue #192.

## Fox edits restored

1. ``Session.save`` — top-of-method ``RuntimeError`` if the session
   was loaded with ``metadata_only=True``. Prevents the #1558 P0
   data-loss regression (saving a metadata-only stub atomically
   wipes on-disk messages).
2. ``Session.save`` — mid-method ``.bak`` backup of the previous JSON
   before overwriting, IFF the incoming messages array is shorter.
   Powers the recovery path in ``api/session_recovery.py``.
3. ``Session.load_metadata_only`` — set ``_loaded_metadata_only=True``
   so the guard in #1 can detect metadata-only sessions.
4. ``new_session`` — add ``project_id`` keyword to the factory
   signature + pass through to ``Session(...)``. Upstream
   ``Session.__init__`` already accepts ``project_id``; the Fox edit
   bridges the factory API.

## Self-checks

* ``inspect.signature`` self-check on ``Session.save`` and
  ``new_session`` — catches upstream signature drift not in the
  substitution anchor regions.
* ``substitute_function`` / ``substitute_method`` anchor self-checks
  (each anchor MUST appear exactly once) catch any local drift.
* Idempotent via per-patch sentinel attributes.
"""
import inspect
import logging

from ._helpers import substitute_function, substitute_method

_log = logging.getLogger("fox_overlay.webui_patches.models")

_SAVE_SENTINEL = "_fox_patched_session_save"
_LOAD_META_SENTINEL = "_fox_patched_load_metadata_only"
_NEW_SESSION_SENTINEL = "_fox_patched_new_session"

# Expected upstream signatures — see _check_signature() docstring.
_EXPECTED_SAVE_SIG = "(self, touch_updated_at: bool = True, skip_index: bool = False) -> None"
# load_metadata_only is @classmethod; bound signature shown.
_EXPECTED_LOAD_META_SIG = "(sid)"
_EXPECTED_NEW_SESSION_SIG = "(workspace=None, model=None, profile=None, model_provider=None)"


def _check_signature(callable_obj, expected: str, label: str) -> None:
    """Fail fast if upstream signature drifts outside the anchor region.

    Anchor checks in substitute_function catch local drift (the lines we
    rewrite). Signature check catches drift elsewhere — e.g. a kwarg
    added/removed/renamed in upstream that doesn't touch our anchor but
    would break the patched body's references.
    """
    actual = str(inspect.signature(callable_obj))
    if actual != expected:
        raise AssertionError(
            "[fox-overlay] models patch: %s signature drift.\n"
            "  expected: %s\n"
            "  actual:   %s\n"
            "Refresh both the expected signature and the substitution "
            "anchors in fox_overlay/webui_patches/models.py." % (label, expected, actual)
        )


def apply() -> None:
    from api import models as _u

    # Idempotency at the apply() level — the 4 substitutions are
    # interdependent (save guard depends on load_metadata_only setting
    # the flag; new_session needs project_id pass-through to match the
    # Session.__init__ surface). Either all run or none.
    if getattr(_u.Session.save, _SAVE_SENTINEL, False):
        return

    # ── Signature self-checks (only on first apply — sentinel-guarded above) ──
    _check_signature(_u.Session.save, _EXPECTED_SAVE_SIG, "Session.save")
    _check_signature(_u.Session.load_metadata_only, _EXPECTED_LOAD_META_SIG,
                     "Session.load_metadata_only")
    _check_signature(_u.new_session, _EXPECTED_NEW_SESSION_SIG, "new_session")

    # ── Patch Session.save: 2 substitutions ─────────────────────────────
    substitute_method(
        upstream_module=_u,
        class_name="Session",
        method_name="save",
        substitutions=[
            (
                # #1558 P0 guard — insert at top of method body.
                "    def save(self, touch_updated_at: bool = True, skip_index: bool = False) -> None:\n"
                "        if touch_updated_at:\n",
                "    def save(self, touch_updated_at: bool = True, skip_index: bool = False) -> None:\n"
                "        # Fox #1558 P0 guard — refuse to save metadata-only sessions.\n"
                "        # See fox_overlay.webui_patches.models for rationale.\n"
                "        if getattr(self, '_loaded_metadata_only', False):\n"
                "            raise RuntimeError(\n"
                "                f\"Refusing to save metadata-only session {self.session_id!r}: \"\n"
                "                f\"would atomically overwrite on-disk messages with []. \"\n"
                "                f\"Reload with metadata_only=False before mutating state. \"\n"
                "                f\"See #1558.\"\n"
                "            )\n"
                "        if touch_updated_at:\n",
            ),
            (
                # #1558 .bak backup — insert between payload= and tmp=.
                "        payload = json.dumps({**meta, **extra}, ensure_ascii=False, indent=2)\n"
                "        tmp = self.path.with_suffix(",
                "        payload = json.dumps({**meta, **extra}, ensure_ascii=False, indent=2)\n"
                "\n"
                "        # Fox #1558 backup safeguard — copy existing JSON to .bak\n"
                "        # if the incoming messages array shrinks. See\n"
                "        # fox_overlay.webui_patches.models for rationale.\n"
                "        try:\n"
                "            if self.path.exists():\n"
                "                existing_text = self.path.read_text(encoding='utf-8')\n"
                "                try:\n"
                "                    existing = json.loads(existing_text)\n"
                "                    existing_msg_count = len(existing.get('messages') or [])\n"
                "                except (json.JSONDecodeError, ValueError):\n"
                "                    existing_msg_count = -1  # corrupt → always back up\n"
                "                incoming_msg_count = len(self.messages or [])\n"
                "                if existing_msg_count > incoming_msg_count:\n"
                "                    bak_path = self.path.with_suffix('.json.bak')\n"
                "                    try:\n"
                "                        bak_path.write_text(existing_text, encoding='utf-8')\n"
                "                    except OSError:\n"
                "                        pass\n"
                "        except OSError:\n"
                "            pass\n"
                "\n"
                "        tmp = self.path.with_suffix(",
            ),
        ],
        sentinel=_SAVE_SENTINEL,
    )

    # ── Patch Session.load_metadata_only: 1 substitution ────────────────
    substitute_method(
        upstream_module=_u,
        class_name="Session",
        method_name="load_metadata_only",
        substitutions=[
            (
                # Set _loaded_metadata_only=True before return so save() guard fires.
                "            session._metadata_message_count = _lookup_index_message_count(sid)\n"
                "            return session\n",
                "            session._metadata_message_count = _lookup_index_message_count(sid)\n"
                "            # Fox #1558 — flag this session as metadata-only stub.\n"
                "            # Save guard above (Session.save) refuses to write metadata-only sessions.\n"
                "            session._loaded_metadata_only = True\n"
                "            return session\n",
            ),
        ],
        sentinel=_LOAD_META_SENTINEL,
    )

    # ── Patch new_session: 2 substitutions (signature + body) ───────────
    substitute_function(
        upstream_module=_u,
        function_name="new_session",
        substitutions=[
            (
                "def new_session(workspace=None, model=None, profile=None, model_provider=None):\n",
                "def new_session(workspace=None, model=None, profile=None, model_provider=None, project_id=None):\n",
            ),
            (
                "        model=effective_model,\n"
                "        model_provider=model_provider,\n"
                "        profile=profile,\n"
                "    )\n",
                "        model=effective_model,\n"
                "        model_provider=model_provider,\n"
                "        profile=profile,\n"
                "        project_id=project_id,\n"
                "    )\n",
            ),
        ],
        sentinel=_NEW_SESSION_SENTINEL,
    )
