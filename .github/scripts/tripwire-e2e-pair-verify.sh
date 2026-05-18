#!/usr/bin/env bash
# Tripwire #214 — end-to-end pair test in Fox CI.
#
# ALREADY SHIPPED via `.github/workflows/build-container.yml`:
#   - assembles the container from the pinned webui + pinned agent + overlay
#   - runs Smoke (amd64) and Smoke (arm64) against the assembled image
# That IS the pair test.
#
# This tripwire's job is to (a) sanity-check that build-container.yml still
# does what it claims and (b) keep the tripwire accounted for in the daily
# matrix.

set -eu
source "$(dirname "$0")/tripwire-common.sh"

failures=()
wf=.github/workflows/build-container.yml

# 1. build-container.yml exists.
if [ ! -f "$wf" ]; then
    failures+=("missing: $wf")
fi

# 2. It defines a `smoke:` job (lowercase YAML key — the job that actually
#    runs the assembled container, distinct from the build-and-push jobs).
if [ -f "$wf" ] && ! grep -qE '^[[:space:]]+smoke:' "$wf"; then
    failures+=("$wf no longer defines a 'smoke:' job — pair-test entry point gone")
fi

# 3. It runs on both archs via matrix entries. The exact format is
#    `short: amd64` / `short: arm64` in the matrix list (rendered into
#    the visible job name `Smoke (amd64)` / `Smoke (arm64)`), not a
#    single line. Check each matrix entry.
if [ -f "$wf" ]; then
    for arch in amd64 arm64; do
        if ! grep -qE "short:[[:space:]]+$arch" "$wf"; then
            failures+=("$wf matrix no longer includes arch '$arch' (looked for 'short: $arch')")
        fi
    done
fi

# 4. It still includes the check-overlay-basis gate (proves the build
#    actually exercises the overlay).
if [ -f "$wf" ] && ! grep -q 'check-overlay-basis.sh' "$wf"; then
    failures+=("$wf no longer runs check-overlay-basis.sh — pair test may not be exercising overlay properly")
fi

if [ ${#failures[@]} -eq 0 ]; then
    echo "[tripwire/e2e-pair] verified: build-container.yml exercises pinned webui + pinned agent + overlay end-to-end"
    exit 0
fi

body=$(cat <<EOF
## E2E pair-test invariants broken

The \`build-container.yml\` workflow is meant to be the end-to-end pair test — assembling the pinned webui + pinned agent + fox-overlay and running smoke jobs against the resulting container. The following invariants have been violated:

$(printf -- '- %s\n' "${failures[@]}")

## Actions

- [ ] Inspect \`.github/workflows/build-container.yml\` and restore the missing piece, OR
- [ ] Update this tripwire's expected invariants in \`.github/scripts/tripwire-e2e-pair-verify.sh\` if the build pipeline intentionally moved

EOF
)

tripwire_fire \
    "[tripwire/e2e-pair] build-container.yml pair-test invariants broken" \
    "$body" \
    "tripwire-fire,tripwire/e2e-pair,P1"
