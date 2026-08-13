"""Static tests for the supervisord embed-server carrier.

The authoritative supervisord config is the heredoc in
packages/install-core/install-core.sh:_write_supervisord_conf (both install
contexts generate their running conf from it); packages/integration/
supervisord.conf is a reference copy kept in sync. These tests assert:

* the heredoc carries the [program:embed-server] block, keyed on the lock's
  ${EMBED_MODEL_FILENAME} variable (never a literal filename), with the
  agreed serving parameters (port 8644, -c 8192, --sleep-idle-seconds 120);
* autostart is a computed shell variable, not a literal true — a failed
  model download must leave a stopped unit, not a FATAL retry loop;
* MEM0_TELEMETRY="False" is set on both the gateway and webui environment=
  lines;
* the reference copy mirrors the block and the telemetry entries.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
INSTALL_CORE_PATH = REPO_ROOT / "packages" / "install-core" / "install-core.sh"
REFERENCE_CONF_PATH = REPO_ROOT / "packages" / "integration" / "supervisord.conf"


def _heredoc():
    """The supervisord heredoc body from install-core.sh."""
    text = INSTALL_CORE_PATH.read_text()
    match = re.search(r"<< SUPERVISORD_EOF\n(.*?)\nSUPERVISORD_EOF", text, re.DOTALL)
    assert match, "supervisord heredoc not found in install-core.sh"
    return match.group(1)


def _embed_server_command(text, label):
    section = re.search(
        r"\[program:embed-server\]\n(.*?)(?:\n\n|\n; ──|\Z)", text, re.DOTALL
    )
    assert section, f"[program:embed-server] block missing from {label}"
    command = re.search(r"^command=(.+)$", section.group(1), re.MULTILINE)
    assert command, f"embed-server command= line missing from {label}"
    return section.group(1), command.group(1)


def test_heredoc_has_embed_server_block():
    body, command = _embed_server_command(_heredoc(), "install-core.sh heredoc")
    assert "${EMBED_MODEL_FILENAME}" in command, (
        "embed-server -m path must derive from the lock's ${EMBED_MODEL_FILENAME} "
        "variable — never a literal filename"
    )
    assert "--embedding" in command
    assert "--port 8644" in command
    assert "-c 8192" in command
    assert "--sleep-idle-seconds 120" in command
    assert "--host 127.0.0.1" in command, "embed-server must bind loopback only"


def test_heredoc_embed_server_paths_use_variables():
    _, command = _embed_server_command(_heredoc(), "install-core.sh heredoc")
    assert command.startswith("${app}/llama-cpp/llama-server"), (
        "embed-server binary path must use the ${app} heredoc variable"
    )
    assert "${app}/models/${EMBED_MODEL_FILENAME}" in command, (
        "embed-server model path must be ${app}/models/${EMBED_MODEL_FILENAME}"
    )


def test_heredoc_embed_server_autostart_is_computed():
    body, _ = _embed_server_command(_heredoc(), "install-core.sh heredoc")
    autostart = re.search(r"^autostart=(.+)$", body, re.MULTILINE)
    assert autostart, "embed-server autostart= line missing"
    value = autostart.group(1)
    assert re.fullmatch(r"\$\{\w+\}", value), (
        f"embed-server autostart must be a computed shell variable "
        f"(true iff model present + hash-verified at conf-write time), got {value!r}"
    )
    # And the variable must actually be computed before the heredoc.
    text = INSTALL_CORE_PATH.read_text()
    var_name = value[2:-1]
    assert re.search(rf'local {var_name}="false"', text), (
        f"{var_name} must default to false before the presence/hash check"
    )


def test_heredoc_gateway_and_webui_have_telemetry_off():
    body = _heredoc()
    for program in ("hermes-gateway", "hermes-webui"):
        section = re.search(
            rf"\[program:{program}\]\n(.*?)(?:\n\n|\Z)", body, re.DOTALL
        )
        assert section, f"[program:{program}] block missing from heredoc"
        env_line = re.search(r"^environment=(.+)$", section.group(1), re.MULTILINE)
        assert env_line, f"{program} environment= line missing"
        assert 'MEM0_TELEMETRY="False"' in env_line.group(1), (
            f'{program} environment= must carry MEM0_TELEMETRY="False"'
        )


def test_reference_conf_mirrors_embed_server_block():
    body, command = _embed_server_command(
        REFERENCE_CONF_PATH.read_text(), "reference supervisord.conf"
    )
    assert "--embedding" in command
    assert "--port 8644" in command
    assert "-c 8192" in command
    assert "--sleep-idle-seconds 120" in command
    assert "--host 127.0.0.1" in command
    assert "${EMBED_MODEL_FILENAME}" in command, (
        "reference copy must keep the filename as the lock-derived placeholder "
        "(no literal GGUF filename outside embed-model.lock)"
    )


def test_reference_conf_mirrors_telemetry_off():
    text = REFERENCE_CONF_PATH.read_text()
    for program in ("hermes-gateway", "hermes-webui"):
        section = re.search(
            rf"\[program:{program}\]\n(.*?)(?:\n\n|\Z)", text, re.DOTALL
        )
        assert section, f"[program:{program}] block missing from reference conf"
        env_line = re.search(r"^environment=(.+)$", section.group(1), re.MULTILINE)
        assert env_line, f"{program} environment= line missing in reference conf"
        assert 'MEM0_TELEMETRY="False"' in env_line.group(1), (
            f'reference conf {program} environment= must carry MEM0_TELEMETRY="False"'
        )
