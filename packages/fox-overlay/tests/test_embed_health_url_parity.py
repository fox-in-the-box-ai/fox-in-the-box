"""Static parity guard for the embed-server :8644 default (issue #873).

The embed-server /health default (http://127.0.0.1:8644/health) is spelled
out independently in the readyz probe and the mem0_oss plugin, and the same
:8644 port carries the plugin's /v1 base URL and the supervisord
[program:embed-server] --port.  Nothing shares a single source, so a future
embed-port change that misses one site silently relapses #869 on the DEFAULT
path.  This test fails CI the moment the :8644 default diverges across its
definition sites.

Literals are text-extracted, never imported: importing the plugin needs the
hermes-agent fork on sys.path (an importorskip would make the guard vacuously
pass when the fork is absent), and readyz deliberately does NOT import the
plugin.  Parsing the source text sidesteps both.

The supervisord cross-check mirrors test_supervisord_carrier.py: the
authoritative config is the heredoc in install-core.sh, and
packages/integration/supervisord.conf is a reference copy kept in sync.
"""

import re
import urllib.parse
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
READYZ_PATH = (
    REPO_ROOT
    / "packages"
    / "fox-overlay"
    / "fox_overlay"
    / "webui_modules"
    / "readyz.py"
)
PLUGIN_PATH = (
    REPO_ROOT
    / "packages"
    / "fox-overlay"
    / "agent_memory_plugins"
    / "mem0_oss"
    / "__init__.py"
)
INSTALL_CORE_PATH = REPO_ROOT / "packages" / "install-core" / "install-core.sh"
REFERENCE_CONF_PATH = REPO_ROOT / "packages" / "integration" / "supervisord.conf"

_EXPECTED_HOST = "127.0.0.1"
_EXPECTED_PORT = 8644


def _extract_str_const(path, name):
    """The value of a module-level ``name = "..."`` string assignment."""
    match = re.search(rf'{name}\s*=\s*"([^"]+)"', path.read_text())
    assert match, f"{name} not found in {path.name} (renamed or removed?)"
    return match.group(1)


def _heredoc():
    """The supervisord heredoc body from install-core.sh."""
    text = INSTALL_CORE_PATH.read_text()
    match = re.search(r"<< SUPERVISORD_EOF\n(.*?)\nSUPERVISORD_EOF", text, re.DOTALL)
    assert match, "supervisord heredoc not found in install-core.sh"
    return match.group(1)


def _embed_server_port(text, label):
    section = re.search(
        r"\[program:embed-server\]\n(.*?)(?:\n\n|\n; ──|\Z)", text, re.DOTALL
    )
    assert section, f"[program:embed-server] block missing from {label}"
    command = re.search(r"^command=(.+)$", section.group(1), re.MULTILINE)
    assert command, f"embed-server command= line missing from {label}"
    port = re.search(r"--port (\d+)", command.group(1))
    assert port, f"embed-server --port missing from {label}"
    return int(port.group(1))


def test_readyz_and_plugin_health_url_are_identical():
    readyz_url = _extract_str_const(READYZ_PATH, "_EMBED_HEALTH_URL")
    plugin_url = _extract_str_const(PLUGIN_PATH, "_LOCAL_EMBED_HEALTH_URL")
    assert readyz_url == plugin_url, (
        "readyz _EMBED_HEALTH_URL and mem0_oss _LOCAL_EMBED_HEALTH_URL must be "
        f"byte-identical (got {readyz_url!r} vs {plugin_url!r}) — a divergence "
        "relapses #869 on the default probe path"
    )


def test_all_embed_default_urls_resolve_to_expected_host_port():
    urls = {
        "readyz _EMBED_HEALTH_URL": _extract_str_const(
            READYZ_PATH, "_EMBED_HEALTH_URL"
        ),
        "mem0_oss _LOCAL_EMBED_HEALTH_URL": _extract_str_const(
            PLUGIN_PATH, "_LOCAL_EMBED_HEALTH_URL"
        ),
        "mem0_oss _LOCAL_EMBED_BASE_URL": _extract_str_const(
            PLUGIN_PATH, "_LOCAL_EMBED_BASE_URL"
        ),
    }
    for label, url in urls.items():
        parsed = urllib.parse.urlparse(url)
        assert parsed.hostname == _EXPECTED_HOST, (
            f"{label} host must be {_EXPECTED_HOST} (got {parsed.hostname!r} "
            f"from {url!r})"
        )
        assert parsed.port == _EXPECTED_PORT, (
            f"{label} port must be {_EXPECTED_PORT} (got {parsed.port!r} from "
            f"{url!r}) — the embed-server default port moved on one site only"
        )


def test_heredoc_embed_server_port_matches_default():
    port = _embed_server_port(_heredoc(), "install-core.sh heredoc")
    assert port == _EXPECTED_PORT, (
        f"install-core.sh embed-server binds --port {port}, but the plugin/"
        f"readyz default probes {_EXPECTED_PORT} — a port move must land on "
        "every site at once (#873)"
    )


def test_reference_conf_embed_server_port_matches_default():
    port = _embed_server_port(
        REFERENCE_CONF_PATH.read_text(), "reference supervisord.conf"
    )
    assert port == _EXPECTED_PORT, (
        f"reference supervisord.conf embed-server binds --port {port}, but the "
        f"plugin/readyz default probes {_EXPECTED_PORT} — a port move must land "
        "on every site at once (#873)"
    )
