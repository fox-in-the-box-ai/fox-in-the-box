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

# 1. build-container.yml exists.
if [ ! -f .github/workflows/build-container.yml ]; then
    failures+=("missing: .github/workflows/build-container.yml")
fi

# 2. It still references both Smoke jobs.
for arch in amd64 arm64; do
    if ! grep -qE "Smoke.*$arch|smoke.*$arch" .github/workflows/build-container.yml; then
        failures+=("build-container.yml no longer references Smoke ($arch)")
    fi
done

# 3. It still includes the check-overlay-basis gate (proves it's exercising the overlay).
if ! grep -q 'check-overlay-basis.sh' .github/workflows/build-container.yml; then
    failures+=("build-container.yml no longer runs check-overlay-basis.sh — pair test may not be exercising overlay properly")
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
