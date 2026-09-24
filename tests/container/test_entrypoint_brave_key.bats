#!/usr/bin/env bats
# tests/container/test_entrypoint_brave_key.bats
# Run: bats tests/container/test_entrypoint_brave_key.bats
#
# Regression gate for #908 — a BRAVE_API_KEY containing shell/sed/supervisord
# metacharacters must not brick boot. Two consuming surfaces, two mechanisms:
#   * supervisord.conf: value carried through the env channel (%(ENV_x)s), never
#     spliced into the environment= grammar — inert to `"`, `,`, `|`, `&`, `\`.
#   * hermes.yaml: value escaped as literal data before the sed rewrite, with a
#     non-fatal guard so no content can abort boot.
# Same family as the closed #817 (content-dependent boot-brick).

ENTRYPOINT="$BATS_TEST_DIRNAME/../../packages/integration/entrypoint.sh"
SUPERVISORD_CONF="$BATS_TEST_DIRNAME/../../packages/integration/supervisord.conf"

# Mirrors the entrypoint §5b escape+rewrite. Portable sed (no -i) so the escape
# logic is exercised identically on GNU (container/CI) and BSD (macOS) sed.
_patch_yaml() {
  local key="$1" yaml="$2"
  local repl="$key"
  repl="${repl//\\/\\\\}"   # backslash — must be first
  repl="${repl//|/\\|}"     # sed delimiter
  repl="${repl//&/\\&}"     # whole-match back-reference
  sed "s|\${BRAVE_API_KEY}|${repl}|g" "$yaml"
}

# ---------------------------------------------------------------------------
# Source-text gates — fail if the container fix is reverted.
# ---------------------------------------------------------------------------
@test "#908 container: supervisord.conf carries the key via %(ENV_BRAVE_API_KEY)s" {
  run grep -F 'BRAVE_API_KEY="%(ENV_BRAVE_API_KEY)s"' "$SUPERVISORD_CONF"
  [ "$status" -eq 0 ]
}

@test "#908 container: no __BRAVE_API_KEY__ placeholder remains in supervisord.conf" {
  run grep -F '__BRAVE_API_KEY__' "$SUPERVISORD_CONF"
  [ "$status" -ne 0 ]
}

@test "#908 container: entrypoint exports BRAVE_API_KEY for supervisord" {
  run grep -F 'export BRAVE_API_KEY="${BRAVE_API_KEY:-}"' "$ENTRYPOINT"
  [ "$status" -eq 0 ]
}

@test "#908 container: entrypoint no longer seds BRAVE into supervisord.conf" {
  run grep -nE 'sed .*__BRAVE_API_KEY__' "$ENTRYPOINT"
  [ "$status" -ne 0 ]
}

@test "#908 container: entrypoint escapes the key before the hermes.yaml rewrite" {
  run grep -F '_brave_repl="${_brave_repl//\\/\\\\}"' "$ENTRYPOINT"
  [ "$status" -eq 0 ]
}

# ---------------------------------------------------------------------------
# Behavioral — the escape technique lands the value verbatim, no injection.
# ---------------------------------------------------------------------------
@test "#908 hermes.yaml: a key with sed metachars lands verbatim" {
  local yaml="$BATS_TEST_TMPDIR/hermes.yaml"
  printf 'brave:\n  api_key: ${BRAVE_API_KEY}\n' > "$yaml"
  run _patch_yaml 'a|b&c\d' "$yaml"
  [ "$status" -eq 0 ]
  [[ "$output" == *'api_key: a|b&c\d'* ]]
}

@test "#908 hermes.yaml: an injection payload does not execute as a sed program" {
  local yaml="$BATS_TEST_TMPDIR/hermes.yaml"
  printf 'brave:\n  api_key: ${BRAVE_API_KEY}\nsentinel: foxinthebox\n' > "$yaml"
  run _patch_yaml 'abc|g;s|foxinthebox|INJECTED|g' "$yaml"
  [ "$status" -eq 0 ]
  # The sentinel must survive untouched: if the payload had run as a sed program
  # it would have rewritten this line to "sentinel: INJECTED".
  [[ "$output" == *"sentinel: foxinthebox"* ]]
  [[ "$output" != *"sentinel: INJECTED"* ]]
  # The whole payload lands literally as the key value (INJECTED here is inert
  # text inside the key, not an executed substitution).
  [[ "$output" == *'api_key: abc|g;s|foxinthebox|INJECTED|g'* ]]
}

@test "#908 hermes.yaml: an ordinary alphanumeric key lands verbatim (no over-escaping)" {
  local yaml="$BATS_TEST_TMPDIR/hermes.yaml"
  printf 'brave:\n  api_key: ${BRAVE_API_KEY}\n' > "$yaml"
  run _patch_yaml 'BSAplainKey123' "$yaml"
  [ "$status" -eq 0 ]
  [[ "$output" == *'api_key: BSAplainKey123'* ]]
}
