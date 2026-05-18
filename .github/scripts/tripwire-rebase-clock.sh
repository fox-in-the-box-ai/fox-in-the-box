#!/usr/bin/env bash
# Tripwire #215 — patch-series rebase clock.
#
# v0 implementation: opens issue if any patch file under
# `packages/fox-overlay/patches/{webui,agent}/*.patch` was last modified
# more than $THRESHOLD_DAYS days ago.
#
# Original spec wanted a rolling-average of "time-to-rebase per upstream
# pull" — that needs historical telemetry we don't have. The freshness
# clock catches the same underlying concern (overlay anchors going stale)
# with simpler infrastructure.

set -eu
source "$(dirname "$0")/tripwire-common.sh"

THRESHOLD_DAYS=90

stale=()
for series_dir in packages/fox-overlay/patches/webui packages/fox-overlay/patches/agent; do
    [ -d "$series_dir" ] || continue
    for patch in "$series_dir"/*.patch; do
        [ -f "$patch" ] || continue
        # Last commit touching this file.
        last_iso=$(git log -1 --format=%cI -- "$patch" 2>/dev/null || true)
        [ -z "$last_iso" ] && continue
        last_epoch=$(date -u -j -f '%Y-%m-%dT%H:%M:%S%z' "$last_iso" +%s 2>/dev/null \
                     || date -u -d "$last_iso" +%s 2>/dev/null \
                     || echo 0)
        now_epoch=$(date -u +%s)
        age_days=$(( (now_epoch - last_epoch) / 86400 ))
        if [ "$age_days" -gt "$THRESHOLD_DAYS" ]; then
            stale+=("\`$patch\` ($age_days days since last touch)")
        fi
    done
done

if [ ${#stale[@]} -eq 0 ]; then
    echo "[tripwire/rebase-clock] no overlay patch file older than $THRESHOLD_DAYS days; no-op"
    exit 0
fi

body=$(cat <<EOF
## Overlay patch files exceed freshness threshold ($THRESHOLD_DAYS days)

$(printf -- '- %s\n' "${stale[@]}")

## Why this matters

Long-lived overlay patches against upstream that keeps moving are a structural risk: the anchors silently rot, then a routine \`upstream-watch.yml\` bump fails \`check-overlay-basis.sh\` with no recent context to guide the fix. Per Architect 3 §9 (\"fork-and-stop precondition\"), persistently stale overlay code is a leading indicator that the overlay strategy itself needs re-evaluation.

## Actions

- [ ] For each stale patch: refresh against the current submodule pin (re-generate from a fresh \`git apply\`-able state)
- [ ] If a patch is intentionally long-lived because the anchor truly hasn't moved, document why in a comment above the patch in its \`series\` file
- [ ] Close this issue once patches are refreshed; will re-fire if it crosses the threshold again

EOF
)

tripwire_fire \
    "[tripwire/rebase-clock] overlay patch file(s) older than ${THRESHOLD_DAYS}d" \
    "$body" \
    "tripwire-fire,tripwire/rebase-clock,P2"
