"""Phase 5 hard-prereq test: registered dispatcher prefixes must not overlap.

The dispatcher iterates registered prefixes in insertion order; if two
prefixes overlap (e.g. `/api/foo/` and `/api/foo/bar/`), the first
inserted wins for paths that match both. That's a footgun: silent
behavior change when modules import in a different order, and a
correctness bug if the more specific prefix has different semantics
than the more general one.

This test enumerates every registered prefix after `bootstrap.install()`
and rejects any pair where one is a prefix of the other.

Added as a hard prerequisite of Phase 5's first module (ollama). Every
subsequent webui_module that registers a new prefix is checked against
the growing set automatically.
"""
import importlib

import pytest


@pytest.fixture
def installed_dispatch():
    """Reload fox_overlay so install() runs once with current modules."""
    import fox_overlay.dispatch as d
    import fox_overlay.bootstrap as b
    importlib.reload(d)
    importlib.reload(b)
    b.install()
    return d


def _find_overlaps(prefixes: list[str]) -> list[tuple[str, str]]:
    """Return all (shorter, longer) pairs where shorter is a prefix of longer.

    Exact duplicates are also returned — dispatch._register only WARNs on
    duplicate registration (it overwrites silently otherwise), so the
    no-overlap test is the gate that surfaces the conflict.
    """
    overlaps = []
    for i, p in enumerate(prefixes):
        for q in prefixes[i + 1:]:
            if p == q:
                overlaps.append((p, q))
            elif p.startswith(q) or q.startswith(p):
                shorter, longer = (q, p) if len(q) < len(p) else (p, q)
                overlaps.append((shorter, longer))
    return overlaps


def test_no_overlap_in_get_table(installed_dispatch):
    prefixes = list(installed_dispatch.GET_TABLE.keys())
    overlaps = _find_overlaps(prefixes)
    assert not overlaps, (
        f"GET-handler prefixes overlap: {overlaps}. "
        f"The shorter prefix would shadow the longer one (or vice versa, "
        f"depending on registration order). Pick non-overlapping prefixes "
        f"or split the more general one into specific subroutes."
    )


def test_no_overlap_in_post_table(installed_dispatch):
    prefixes = list(installed_dispatch.POST_TABLE.keys())
    overlaps = _find_overlaps(prefixes)
    assert not overlaps, (
        f"POST-handler prefixes overlap: {overlaps}. "
        f"Pick non-overlapping prefixes or split the general one."
    )


def test_install_freezes_tables(installed_dispatch):
    """Side-effect check — bootstrap.install() must freeze after registration."""
    from fox_overlay.dispatch import _BootstrapState
    assert _BootstrapState.frozen is True


def test_overlay_detector_self_test():
    """Sanity: _find_overlaps catches the obvious cases."""
    assert _find_overlaps(["/api/foo/", "/api/foo/bar/"]) == [
        ("/api/foo/", "/api/foo/bar/")
    ]
    assert _find_overlaps(["/api/foo/", "/api/bar/"]) == []
    assert _find_overlaps(["/a/", "/a/"]) == [("/a/", "/a/")]
