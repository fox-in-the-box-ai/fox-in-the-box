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
* the reference copy mirrors the block and the telemetry entries;
* both the heredoc and the reference copy carry the [supervisord] baseline
  MEM0_OSS_QDRANT_URL (issue #803 — a single shared surface, never per-program)
  and the one-shot [program:mem0-migrate] unit (autorestart=false, startsecs=0,
  priority=22) that runs the embedded → server migration.
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


# ── issue #803: shared server URL surface + one-shot migration unit ──────────


def _supervisord_section(text, label):
    """The [supervisord] block body (up to the next section header)."""
    section = re.search(r"\[supervisord\]\n(.*?)\n\[", text, re.DOTALL)
    assert section, f"[supervisord] block missing from {label}"
    return section.group(1)


def _program_block(text, program, label):
    section = re.search(
        rf"\[program:{program}\]\n(.*?)(?:\n\n|\n; ──|\Z)", text, re.DOTALL
    )
    assert section, f"[program:{program}] block missing from {label}"
    return section.group(1)


def _assert_supervisord_carries_qdrant_url(text, label):
    body = _supervisord_section(text, label)
    env_line = re.search(r"^environment=(.+)$", body, re.MULTILINE)
    assert env_line, f"[supervisord] environment= line missing from {label}"
    assert 'MEM0_OSS_QDRANT_URL="http://127.0.0.1:6333"' in env_line.group(1), (
        f"{label} [supervisord] environment= must carry the shared "
        'MEM0_OSS_QDRANT_URL="http://127.0.0.1:6333" baseline (issue #803)'
    )


def _assert_mem0_migrate_unit(text, label):
    body = _program_block(text, "mem0-migrate", label)
    command = re.search(r"^command=(.+)$", body, re.MULTILINE)
    assert command, f"mem0-migrate command= line missing from {label}"
    assert command.group(1).endswith(
        "python3 -m plugins.memory.mem0_oss.migrate_store --boot"
    ), f"{label} mem0-migrate must run the --boot wrapper via run-with-env.sh"
    assert "run-with-env.sh" in command.group(1), (
        f"{label} mem0-migrate must wrap run-with-env.sh so the opt-out "
        "(empty MEM0_OSS_QDRANT_URL in hermes.env) still applies"
    )
    # One-shot job, not a supervised daemon.
    assert re.search(r"^autostart=true$", body, re.MULTILINE), (
        f"{label} mem0-migrate must autostart"
    )
    assert re.search(r"^autorestart=false$", body, re.MULTILINE), (
        f"{label} mem0-migrate must set autorestart=false (one-shot job)"
    )
    assert re.search(r"^startsecs=0$", body, re.MULTILINE), (
        f"{label} mem0-migrate must set startsecs=0 (clean exit is success)"
    )
    assert re.search(r"^startretries=0$", body, re.MULTILINE), (
        f"{label} mem0-migrate must set startretries=0"
    )
    assert re.search(r"^priority=22$", body, re.MULTILINE), (
        f"{label} mem0-migrate must run at priority=22 (after qdrant=20, "
        "before embed-server=25)"
    )
    # The URL must be inherited from [supervisord], never redeclared per-program.
    env_line = re.search(r"^environment=(.+)$", body, re.MULTILINE)
    assert env_line, f"{label} mem0-migrate environment= line missing"
    assert "MEM0_OSS_QDRANT_URL" not in env_line.group(1), (
        f"{label} mem0-migrate must NOT redeclare MEM0_OSS_QDRANT_URL — it "
        "inherits the [supervisord] baseline (per-program divergence is the "
        "split-brain bug #803 kills)"
    )


def _assert_no_per_program_qdrant_url(text, label):
    for program in ("hermes-gateway", "hermes-webui"):
        body = _program_block(text, program, label)
        env_line = re.search(r"^environment=(.+)$", body, re.MULTILINE)
        assert env_line, f"{program} environment= line missing from {label}"
        assert "MEM0_OSS_QDRANT_URL" not in env_line.group(1), (
            f"{label} {program} must NOT carry a per-program MEM0_OSS_QDRANT_URL "
            "— it inherits the [supervisord] baseline (issue #803)"
        )


def test_heredoc_supervisord_carries_shared_qdrant_url():
    _assert_supervisord_carries_qdrant_url(_heredoc(), "install-core.sh heredoc")


def test_reference_conf_supervisord_carries_shared_qdrant_url():
    _assert_supervisord_carries_qdrant_url(
        REFERENCE_CONF_PATH.read_text(), "reference supervisord.conf"
    )


def test_heredoc_has_mem0_migrate_unit():
    _assert_mem0_migrate_unit(_heredoc(), "install-core.sh heredoc")


def test_reference_conf_has_mem0_migrate_unit():
    _assert_mem0_migrate_unit(
        REFERENCE_CONF_PATH.read_text(), "reference supervisord.conf"
    )


def test_heredoc_no_per_program_qdrant_url():
    _assert_no_per_program_qdrant_url(_heredoc(), "install-core.sh heredoc")


def test_reference_conf_no_per_program_qdrant_url():
    _assert_no_per_program_qdrant_url(
        REFERENCE_CONF_PATH.read_text(), "reference supervisord.conf"
    )
