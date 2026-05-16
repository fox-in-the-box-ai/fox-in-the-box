"""Phase 1 baseline regression tests for fox_overlay.bootstrap.

Seeds packages/fox-overlay/tests/ for Phases 3-6 to extend (anti-regression
Rule 3: regression suite grows with every phase).
"""
import importlib
import os


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
