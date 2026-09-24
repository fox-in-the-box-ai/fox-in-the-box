"""Phase 1 baseline regression tests for fox_overlay.bootstrap.

Seeds packages/fox-overlay/tests/ for Phases 3-6 to extend (anti-regression
Rule 3: regression suite grows with every phase).
"""

import importlib
import logging
import os
import sys


def test_install_is_idempotent():
    """install() must be safely callable any number of times."""
    import fox_overlay.bootstrap as b

    b.install()
    b.install()
    assert b._INSTALLED is True


def test_autoinstall_default_on(monkeypatch):
    """Without FOX_OVERLAY_AUTOINSTALL set, importing the module installs."""
    monkeypatch.delenv("FOX_OVERLAY_AUTOINSTALL", raising=False)
    import fox_overlay.bootstrap as b

    importlib.reload(b)
    assert b._INSTALLED is True


def test_autoinstall_opt_out(monkeypatch):
    """FOX_OVERLAY_AUTOINSTALL=0 leaves _INSTALLED False until install() is called."""
    monkeypatch.setenv("FOX_OVERLAY_AUTOINSTALL", "0")
    import fox_overlay.bootstrap as b

    importlib.reload(b)
    assert b._INSTALLED is False
    b.install()
    assert b._INSTALLED is True


def test_bad_model_size_env_degrades_not_bricks(monkeypatch, caplog):
    """#910: a non-numeric MODEL_SIZE_PHI4MINI raises at webui_modules import,
    but bootstrap.install() must degrade Fox routes and keep booting — not
    propagate the ValueError and brick WebUI boot."""
    monkeypatch.setenv("MODEL_SIZE_PHI4MINI", "2,491,874,688")
    monkeypatch.setenv("FOX_OVERLAY_AUTOINSTALL", "0")

    # Purge the overlay module cache so the bad env is hit at a FRESH import
    # (a cached webui_modules would not re-execute models_download).
    for name in list(sys.modules):
        if name == "fox_overlay" or name.startswith("fox_overlay."):
            del sys.modules[name]

    import fox_overlay.bootstrap as b

    importlib.reload(b)

    with caplog.at_level(logging.WARNING):
        b.install()  # must NOT raise

    assert b._INSTALLED is True
    import fox_overlay.dispatch as d

    assert d._BootstrapState.frozen is True
    assert any("webui_modules" in r.getMessage() for r in caplog.records)

    # Reset overlay cache to a clean state for order-independence.
    monkeypatch.delenv("MODEL_SIZE_PHI4MINI", raising=False)
    for name in list(sys.modules):
        if name == "fox_overlay" or name.startswith("fox_overlay."):
            del sys.modules[name]
