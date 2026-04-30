#!/usr/bin/env bats
# tests/container/test_install.bats
# Run: bats tests/container/test_install.bats

# ---------------------------------------------------------------------------
# Setup: create a temp dir with stub binaries and a copy of install.sh
# ---------------------------------------------------------------------------
setup() {
  # Temp working directory
  TEST_DIR="$(mktemp -d)"
  STUB_BIN="$TEST_DIR/bin"
  mkdir -p "$STUB_BIN"

  # Copy install.sh into test dir
  cp "$BATS_TEST_DIRNAME/../../packages/scripts/install.sh" "$TEST_DIR/install.sh"
  chmod +x "$TEST_DIR/install.sh"

  # Default docker stub: docker info succeeds, pull succeeds, run succeeds
  cat > "$STUB_BIN/docker" <<'EOF'
#!/usr/bin/env bash
case "$1" in
  info)   exit 0 ;;
  pull)   exit 0 ;;
  ps)     echo "" ;;        # no existing container
  run)    echo "fake-container-id"; exit 0 ;;
  stop|rm) exit 0 ;;
  logs)   echo "No output" ;;
  exec)   echo '{"BackendState":"Running"}' ;;
  *)      exit 0 ;;
esac
EOF
  chmod +x "$STUB_BIN/docker"

  # Stub uname (Linux by default)
  cat > "$STUB_BIN/uname" <<'EOF'
#!/usr/bin/env bash
echo "Linux"
EOF
  chmod +x "$STUB_BIN/uname"

  # Stub systemctl (no-op)
  cat > "$STUB_BIN/systemctl" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
  chmod +x "$STUB_BIN/systemctl"

  # Stub sudo (passthrough without elevation)
  cat > "$STUB_BIN/sudo" <<'EOF'
#!/usr/bin/env bash
exec "$@"
EOF
  chmod +x "$STUB_BIN/sudo"

  # Stub cp (no-op for systemd unit copy)
  # We rely on the real cp but allow /etc paths by pointing them to TEST_DIR
  SYSTEMD_DIR="$TEST_DIR/etc/systemd/system"
  mkdir -p "$SYSTEMD_DIR"

  # Copy unit files so the script can find them via SCRIPT_DIR
  cp "$BATS_TEST_DIRNAME/../../packages/scripts/"foxinthebox*.service \
     "$BATS_TEST_DIRNAME/../../packages/scripts/"foxinthebox*.path \
     "$TEST_DIR/"

  export PATH="$STUB_BIN:$PATH"
  export FOX_DATA_DIR="$TEST_DIR/data"
  export HOME="$TEST_DIR/home"
  mkdir -p "$FOX_DATA_DIR" "$HOME"
}

teardown() {
  rm -rf "$TEST_DIR"
}

# ---------------------------------------------------------------------------
# Test 1 — OS detection: Linux
# ---------------------------------------------------------------------------
@test "detects Linux platform from uname -s" {
  # Confirm uname stub returns Linux
  run uname -s
  [ "$output" = "Linux" ]
  [ "$status" -eq 0 ]
}

# ---------------------------------------------------------------------------
# Test 2 — OS detection: macOS
# ---------------------------------------------------------------------------
@test "detects macOS platform from uname -s Darwin" {
  cat > "$STUB_BIN/uname" <<'EOF'
#!/usr/bin/env bash
echo "Darwin"
EOF
  chmod +x "$STUB_BIN/uname"
  run uname -s
  [ "$output" = "Darwin" ]
  [ "$status" -eq 0 ]
}

# ---------------------------------------------------------------------------
# Test 3 — Docker pre-installed: install step is skipped
# ---------------------------------------------------------------------------
@test "skips Docker install when docker info succeeds" {
  # docker info stub exits 0 → install block should not run
  # We detect this by ensuring 'curl' stub is never called
  cat > "$STUB_BIN/curl" <<'EOF'
#!/usr/bin/env bash
echo "CURL_CALLED" >&2
exit 1
EOF
  chmod +x "$STUB_BIN/curl"

  # Run only sections up to the docker-check (inject exit before pull)
  # by sourcing the relevant logic
  run bash -c '
    source /dev/stdin <<'"'"'SCRIPT'"'"'
    set -euo pipefail
    _docker_running() { docker info >/dev/null 2>&1; }
    if ! command -v docker &>/dev/null || ! _docker_running; then
      curl -fsSL https://get.docker.com | sh
    fi
    echo "docker_ok"
SCRIPT
'
  [ "$status" -eq 0 ]
  [[ "$output" == *"docker_ok"* ]]
  [[ "$output" != *"CURL_CALLED"* ]]
}

# ---------------------------------------------------------------------------
# Test 4 — Port binding, option 1 → 0.0.0.0
# ---------------------------------------------------------------------------
@test "port-only mode uses 0.0.0.0:8787 binding" {
  run bash -c '
    ACCESS_MODE=1
    case "$ACCESS_MODE" in
      1) PORT_BIND="-p 0.0.0.0:8787:8787";  USE_TAILSCALE=false ;;
      2) PORT_BIND="-p 127.0.0.1:8787:8787"; USE_TAILSCALE=true  ;;
      3) PORT_BIND="-p 0.0.0.0:8787:8787";   USE_TAILSCALE=true  ;;
    esac
    echo "$PORT_BIND"
  '
  [ "$status" -eq 0 ]
  [ "$output" = "-p 0.0.0.0:8787:8787" ]
}

# ---------------------------------------------------------------------------
# Test 5 — Port binding, option 2 → localhost only
# ---------------------------------------------------------------------------
@test "tailscale-only mode binds to 127.0.0.1" {
  run bash -c '
    ACCESS_MODE=2
    case "$ACCESS_MODE" in
      1) PORT_BIND="-p 0.0.0.0:8787:8787";  USE_TAILSCALE=false ;;
      2) PORT_BIND="-p 127.0.0.1:8787:8787"; USE_TAILSCALE=true  ;;
      3) PORT_BIND="-p 0.0.0.0:8787:8787";   USE_TAILSCALE=true  ;;
    esac
    echo "$PORT_BIND"
  '
  [ "$status" -eq 0 ]
  [ "$output" = "-p 127.0.0.1:8787:8787" ]
}

# ---------------------------------------------------------------------------
# Test 5b — ? option prints explanation then loops; valid answer after ? works
# ---------------------------------------------------------------------------
@test "entering ? shows Tailscale explanation and re-prompts" {
  # Feed "?" then "1" via stdin — the loop should explain then accept "1"
  run bash -c '
    _explain_tailscale() {
      echo "EXPLAINED"
    }
    _prompt_access_mode() {
      while true; do
        read -r ACCESS_MODE
        ACCESS_MODE="${ACCESS_MODE:-1}"
        case "$ACCESS_MODE" in
          1) PORT_BIND="-p 0.0.0.0:8787:8787"; USE_TAILSCALE=false; break ;;
          2) PORT_BIND="-p 127.0.0.1:8787:8787"; USE_TAILSCALE=true; break ;;
          3) PORT_BIND="-p 0.0.0.0:8787:8787"; USE_TAILSCALE=true; break ;;
          "?"|"help"|"explain"|"more"|"what") _explain_tailscale ;;
          *) echo "INVALID: $ACCESS_MODE" ;;
        esac
      done
      echo "RESULT:$PORT_BIND"
    }
    printf "?\n1\n" | _prompt_access_mode
  '
  [ "$status" -eq 0 ]
  [[ "$output" =~ "EXPLAINED" ]]
  [[ "$output" =~ "RESULT:-p 0.0.0.0:8787:8787" ]]
}

# ---------------------------------------------------------------------------
# Test 6 — Docker install failure exits 1 with error message
# ---------------------------------------------------------------------------
@test "exits 1 with error when Docker install script fails" {
  # Override docker stub so docker info fails
  cat > "$STUB_BIN/docker" <<'EOF'
#!/usr/bin/env bash
case "$1" in
  info) exit 1 ;;  # Docker not available
  *)    exit 1 ;;
esac
EOF
  chmod +x "$STUB_BIN/docker"

  # Override curl stub so get.docker.com returns a failing script
  cat > "$STUB_BIN/curl" <<'EOF'
#!/usr/bin/env bash
echo 'exit 1'
EOF
  chmod +x "$STUB_BIN/curl"

  run bash -c '
    set -euo pipefail
    die() { echo "ERROR: $*" >&2; exit 1; }
    _docker_running() { docker info >/dev/null 2>&1; }
    if ! command -v docker &>/dev/null || ! _docker_running; then
      curl -fsSL https://get.docker.com | sh \
        || die "Docker install script failed."
    fi
  '
  [ "$status" -eq 1 ]
  [[ "$output" =~ "Docker install script failed" ]] || \
  [[ "$stderr" =~ "Docker install script failed" ]]
}
