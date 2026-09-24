#!/usr/bin/env bats
# tests/container/test_entrypoint_env.bats
# Run: bats tests/container/test_entrypoint_env.bats
#
# Regression gate for #907 — a corrupt/partial /data/config/hermes.env must not
# brick container boot. The entrypoint sources that user-writable file under
# `set -euo pipefail`; before the fix a single malformed line aborted PID 1
# before `exec supervisord`, so the container vanished under AutoRemove.

ENTRYPOINT="$BATS_TEST_DIRNAME/../../packages/integration/entrypoint.sh"
PREFLIGHT="$BATS_TEST_DIRNAME/../../packages/install-core/preflight.sh"

# ---------------------------------------------------------------------------
# Source-text gate: the guard must be present and no bare source may remain.
# This is the assertion that fails if the fix is ever reverted.
# ---------------------------------------------------------------------------
@test "#907: entrypoint sources hermes.env with a WARN-and-continue guard" {
  run grep -F 'source "$HERMES_ENV" || echo "[entrypoint] WARN:' "$ENTRYPOINT"
  [ "$status" -eq 0 ]
}

@test "#907: entrypoint has no bare 'source \"\$HERMES_ENV\"' on its own line" {
  # A bare source (optionally preceded by whitespace) with no '||' guard is the
  # bricking form. grep -E for a line that is only the source, no trailing '||'.
  run grep -nE '^[[:space:]]*source[[:space:]]+"\$HERMES_ENV"[[:space:]]*$' "$ENTRYPOINT"
  [ "$status" -ne 0 ]
}

@test "#907 desktop: preflight sources hermes.env with a WARN-and-continue guard" {
  # preflight runs as systemd ExecStartPre= under set -e; the same brick class.
  run grep -F 'source "$HERMES_ENV" || _warn' "$PREFLIGHT"
  [ "$status" -eq 0 ]
}

@test "#907 desktop: preflight has no bare 'source \"\$HERMES_ENV\"' on its own line" {
  run grep -nE '^[[:space:]]*source[[:space:]]+"\$HERMES_ENV"[[:space:]]*$' "$PREFLIGHT"
  [ "$status" -ne 0 ]
}

# ---------------------------------------------------------------------------
# Behavioral: the guard pattern under `set -euo pipefail` must survive a
# malformed file (both trigger classes) and still export a valid file's vars.
#
# The `source ... || echo WARN` guard suspends `set -e` for commands inside the
# sourced file only in bash >= 4 — the semantics the Debian-based container
# (bash 5.x) and CI (ubuntu, bash 5.x) actually run under. bash 3.2 (macOS
# /bin/bash) aborts regardless, so pin the behavioral cases to a modern bash and
# skip if none is present. The source-text gates above run everywhere.
# ---------------------------------------------------------------------------

# Echo the path to a bash >= 4, or nothing if none is found.
_modern_bash() {
  local b
  for b in bash /opt/homebrew/bin/bash /usr/local/bin/bash /bin/bash; do
    if command -v "$b" >/dev/null 2>&1 \
       && [ "$("$b" -c 'echo ${BASH_VERSINFO[0]}')" -ge 4 ] 2>/dev/null; then
      command -v "$b"
      return 0
    fi
  done
  return 1
}

# Mirrors the entrypoint's §5 load stanza exactly (guard form under set -a).
_load_env() {
  local HERMES_ENV="$1"
  set -a
  # shellcheck source=/dev/null
  source "$HERMES_ENV" || echo "[entrypoint] WARN: $HERMES_ENV failed to source (malformed) — continuing without it"
  set +a
}

@test "#907 Trigger A: unbalanced quote (syntax error) does not abort boot" {
  local bash5; bash5="$(_modern_bash)" || skip "no bash >= 4 here (macOS /bin/bash is 3.2); these run in CI (ubuntu, bash 5.x) and in the container (bash 5.x)"
  local env_file="$BATS_TEST_TMPDIR/hermes.env"
  printf 'OPENROUTER_API_KEY="unterminated\n' > "$env_file"
  run "$bash5" -c 'set -euo pipefail; '"$(declare -f _load_env)"'; _load_env "$1"; echo REACHED_HANDOFF' _ "$env_file"
  [ "$status" -eq 0 ]
  [[ "$output" == *"REACHED_HANDOFF"* ]]
  [[ "$output" == *"WARN:"* ]]
}

@test "#907 Trigger B: runtime-invalid line (value with a space) does not abort boot" {
  local bash5; bash5="$(_modern_bash)" || skip "no bash >= 4 here (macOS /bin/bash is 3.2); these run in CI (ubuntu, bash 5.x) and in the container (bash 5.x)"
  local env_file="$BATS_TEST_TMPDIR/hermes.env"
  # Syntactically valid (passes `bash -n`) but under `set -a` runs `router` as a
  # command → exit 127. This is why `bash -n` is not a sufficient guard.
  printf 'MODEL_PROVIDER=open router\n' > "$env_file"
  run "$bash5" -c 'set -euo pipefail; '"$(declare -f _load_env)"'; _load_env "$1"; echo REACHED_HANDOFF' _ "$env_file"
  [ "$status" -eq 0 ]
  [[ "$output" == *"REACHED_HANDOFF"* ]]
  [[ "$output" == *"WARN:"* ]]
}

@test "#907 happy path: a valid hermes.env still exports its vars" {
  local bash5; bash5="$(_modern_bash)" || skip "no bash >= 4 here (macOS /bin/bash is 3.2); these run in CI (ubuntu, bash 5.x) and in the container (bash 5.x)"
  local env_file="$BATS_TEST_TMPDIR/hermes.env"
  printf 'OPENROUTER_API_KEY=sk-valid-123\n' > "$env_file"
  run "$bash5" -c 'set -euo pipefail; '"$(declare -f _load_env)"'; _load_env "$1"; echo "KEY=$OPENROUTER_API_KEY"' _ "$env_file"
  [ "$status" -eq 0 ]
  [[ "$output" == *"KEY=sk-valid-123"* ]]
  [[ "$output" != *"WARN:"* ]]
}
