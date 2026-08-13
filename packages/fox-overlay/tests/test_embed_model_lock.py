"""Static pin-consumption tests for packages/integration/embed-model.lock.

The lock is the single source of truth for the local embedding model pin
(URL / sha256 / filename). These tests are dependency-free text assertions:

* the lock parses (exactly the three expected keys, sha256 shape, https URL
  pinned to the org's GitHub releases, provenance comment present);
* the Dockerfile references the lock AND COPYs it to /tmp/ (the directory
  install-core.sh runs from during the image build);
* install-core.sh sources the lock via "$(dirname "$0")/embed-model.lock",
  OUTSIDE the FITB_SKIP_BINARIES gate (the image build skips binary
  downloads but still writes the supervisord heredoc, which needs
  EMBED_MODEL_FILENAME);
* no literal GGUF URL, sha256, or filename appears in any other repo file —
  drift between pin consumers is structurally impossible.
"""

import os
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
LOCK_PATH = REPO_ROOT / "packages" / "integration" / "embed-model.lock"
DOCKERFILE_PATH = REPO_ROOT / "packages" / "integration" / "Dockerfile"
INSTALL_CORE_PATH = REPO_ROOT / "packages" / "install-core" / "install-core.sh"

# Directory names never scanned by the repo-wide literal sweep. .git and
# node_modules/coverage/dist hold artifacts, forks/ is upstream source.
_SKIP_DIRS = {
    ".git",
    "forks",
    "node_modules",
    "coverage",
    "dist",
    "__pycache__",
    ".venv",
    "venv",
    ".pytest_cache",
}

EXPECTED_KEYS = ("EMBED_MODEL_URL", "EMBED_MODEL_SHA256", "EMBED_MODEL_FILENAME")


def _parse_lock():
    """Parse the KEY=VALUE lines of the lock; comments/blank lines ignored."""
    values = {}
    for line in LOCK_PATH.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        assert "=" in stripped, f"non KEY=VALUE, non-comment line in lock: {line!r}"
        key, _, value = stripped.partition("=")
        values[key] = value
    return values


def test_lock_exists():
    assert LOCK_PATH.is_file(), "packages/integration/embed-model.lock is missing"


def test_lock_has_exactly_three_keys():
    values = _parse_lock()
    assert tuple(sorted(values)) == tuple(sorted(EXPECTED_KEYS)), (
        f"lock must define exactly {EXPECTED_KEYS}, got {sorted(values)}"
    )
    for key in EXPECTED_KEYS:
        assert values[key], f"{key} is empty"


def test_lock_is_shell_safe():
    """Every line is either a comment, blank, or KEY=VALUE without quoting
    tricks — the lock is sourced by sh in the Dockerfile and by bash in
    install-core.sh."""
    for line in LOCK_PATH.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        assert re.fullmatch(r"[A-Z0-9_]+=[^\s'\"$`\\;|&<>]+", stripped), (
            f"lock line is not plain shell-safe KEY=VALUE: {line!r}"
        )


def test_sha256_shape():
    sha = _parse_lock()["EMBED_MODEL_SHA256"]
    assert re.fullmatch(r"[0-9a-f]{64}", sha), f"not a lowercase sha256: {sha!r}"


def test_url_is_https_on_org_host():
    url = _parse_lock()["EMBED_MODEL_URL"]
    assert url.startswith("https://github.com/fox-in-the-box-ai/"), (
        f"model URL must be pinned to the org's GitHub host, got {url!r}"
    )
    filename = _parse_lock()["EMBED_MODEL_FILENAME"]
    assert url.endswith("/" + filename), "URL basename must match EMBED_MODEL_FILENAME"


def test_provenance_comment_present():
    text = LOCK_PATH.read_text()
    assert "huggingface.co/nomic-ai/nomic-embed-text-v1.5-GGUF" in text, (
        "upstream provenance comment (Hugging Face source) missing from lock"
    )
    assert "Apache 2.0" in text, "upstream license missing from provenance comment"


def test_dockerfile_copies_lock_to_tmp():
    text = DOCKERFILE_PATH.read_text()
    assert "embed-model.lock" in text, "Dockerfile does not reference embed-model.lock"
    assert re.search(
        r"^COPY packages/integration/embed-model\.lock /tmp/", text, re.MULTILINE
    ), (
        "Dockerfile must COPY embed-model.lock to /tmp/ — install-core.sh runs "
        'from /tmp at image build and sources "$(dirname "$0")/embed-model.lock"'
    )


def test_dockerfile_sources_lock_and_verifies_hash():
    text = DOCKERFILE_PATH.read_text()
    assert ". /tmp/embed-model.lock" in text, (
        "Dockerfile fetch layer must source the lock"
    )
    assert "sha256sum -c" in text, "Dockerfile fetch layer must verify the sha256"


def test_dockerfile_removes_lock_in_install_core_cleanup():
    text = DOCKERFILE_PATH.read_text()
    assert re.search(
        r"rm [^\n]*/tmp/install-core\.sh [^\n]*/tmp/embed-model\.lock", text
    ) or ("rm /tmp/install-core.sh /tmp/embed-model.lock" in text), (
        "the install-core RUN layer's cleanup must also rm /tmp/embed-model.lock"
    )


def test_install_core_sources_lock_beside_itself_outside_skip_binaries_gate():
    text = INSTALL_CORE_PATH.read_text()
    source_line = 'EMBED_MODEL_LOCK="$(dirname "$0")/embed-model.lock"'
    assert source_line in text, (
        'install-core.sh must locate the lock via "$(dirname "$0")/embed-model.lock" '
        "(per-context discovery rule: deb → $APPDIR, docker → /tmp)"
    )
    gate = 'if [ "$FITB_SKIP_BINARIES" != "1" ]'
    assert gate in text, "FITB_SKIP_BINARIES gate missing from install-core.sh"
    assert text.index(source_line) < text.index(gate), (
        "the lock sourcing must sit OUTSIDE (before) the FITB_SKIP_BINARIES gate — "
        "_write_supervisord_conf needs EMBED_MODEL_FILENAME even in skip-binaries builds"
    )


def test_no_literal_pin_outside_the_lock():
    """The GGUF URL, sha256, and filename must appear ONLY in the lock.

    Scans every repo file (minus VCS internals, upstream forks, and package
    artifacts) as bytes so binary files can't crash the sweep.
    """
    values = _parse_lock()
    needles = {key: values[key].encode() for key in EXPECTED_KEYS}
    offenders = []
    for dirpath, dirnames, filenames in os.walk(REPO_ROOT):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for filename in filenames:
            path = Path(dirpath) / filename
            if path == LOCK_PATH:
                continue
            try:
                blob = path.read_bytes()
            except OSError:
                continue
            for key, needle in needles.items():
                if needle in blob:
                    offenders.append(f"{path.relative_to(REPO_ROOT)}: literal {key}")
    assert not offenders, (
        "GGUF pin literals found outside embed-model.lock (derive from the lock "
        "instead):\n" + "\n".join(offenders)
    )
