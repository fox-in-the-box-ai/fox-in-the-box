"""#913 matcher coverage for the webui/011 health-liveness fast-path patch.

The 011 overlay patch adds ``QuietHTTPServer._is_health_liveness_probe`` to the
upstream hermes-webui ``server.py``.  The overlay pytest env has the UNPATCHED
submodule on ``PYTHONPATH``, so this test applies the shipped 011 patch to a
throwaway copy of the pinned ``server.py`` and extracts the matcher from the
patched source (via ``ast``, without importing the heavy module) to lock its
contract: ONLY an exact GET/HEAD ``/health`` is served the canned 200; every
other path — including ``/readyz`` and ``/health?deep=1`` — must fall through
to the real handler, so a future edit cannot silently mask a degraded
subsystem.
"""

from __future__ import annotations

import ast
import importlib.util
import shutil
import subprocess
import tempfile
import textwrap
from pathlib import Path

import pytest

_PATCH = (
    Path(__file__).resolve().parents[1]
    / "patches"
    / "webui"
    / "011-server-py-health-liveness-fastpath.patch"
)


def _pinned_server_py() -> Path | None:
    """Locate the pinned hermes-webui ``server.py`` on PYTHONPATH WITHOUT
    importing it (importing runs the full webui bootstrap)."""
    spec = importlib.util.find_spec("server")
    if spec is None or not spec.origin:
        return None
    return Path(spec.origin)


def _load_patched_matcher():
    """Apply 011 to a tmp copy of the pinned ``server.py`` and return the
    compiled ``_is_health_liveness_probe`` function, or skip if the pinned
    source / git is unavailable in this environment."""
    if not _PATCH.is_file():
        pytest.skip(f"011 patch not found at {_PATCH}")
    server_py = _pinned_server_py()
    if server_py is None or not server_py.is_file():
        pytest.skip("pinned hermes-webui server.py not importable in this env")
    if shutil.which("git") is None:
        pytest.skip("git not available to apply the overlay patch")

    tmp = Path(tempfile.mkdtemp())
    dest = tmp / "server.py"
    dest.write_text(server_py.read_text(encoding="utf-8"), encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=tmp, check=True)
    subprocess.run(["git", "add", "server.py"], cwd=tmp, check=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "p"],
        cwd=tmp,
        check=True,
    )
    applied = subprocess.run(
        ["git", "apply", str(_PATCH)], cwd=tmp, capture_output=True, text=True
    )
    assert applied.returncode == 0, f"011 failed to apply: {applied.stderr}"

    source = dest.read_text(encoding="utf-8")
    tree = ast.parse(source)
    func_src = None
    for cls in tree.body:
        if isinstance(cls, ast.ClassDef) and cls.name == "QuietHTTPServer":
            for item in cls.body:
                if (
                    isinstance(item, ast.FunctionDef)
                    and item.name == "_is_health_liveness_probe"
                ):
                    func_src = ast.get_source_segment(source, item)
    assert func_src is not None, "patched server.py is missing the matcher method"

    # The method body uses only builtins, so compile it standalone (dedented,
    # with the leading `self` argument kept — callers pass a sentinel).
    namespace: dict = {}
    exec(textwrap.dedent(func_src), namespace)  # noqa: S102 — trusted patched source
    return namespace["_is_health_liveness_probe"]


@pytest.mark.parametrize(
    "request_line, expected",
    [
        (b"GET /health HTTP/1.1\r\nHost: x\r\n\r\n", True),
        (b"HEAD /health HTTP/1.1\r\n\r\n", True),
        (b"get /health HTTP/1.1\r\n\r\n", True),  # method is case-insensitive
        (b"GET /health?deep=1 HTTP/1.1\r\n\r\n", False),
        (b"HEAD /readyz HTTP/1.1\r\n\r\n", False),
        (b"GET /readyz HTTP/1.1\r\n\r\n", False),
        (b"POST /health HTTP/1.1\r\n\r\n", False),
        (b"GET /health/ HTTP/1.1\r\n\r\n", False),
        (b"GET /healthz HTTP/1.1\r\n\r\n", False),
        (b"GET /healthcheck HTTP/1.1\r\n\r\n", False),
        (b"", False),
        (b"garbage-not-a-request-line", False),
    ],
)
def test_health_liveness_matcher(request_line, expected):
    match = _load_patched_matcher()
    # Called unbound with a sentinel self — the matcher does not touch self.
    assert match(None, request_line) is expected
