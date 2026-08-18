#!/usr/bin/env bash
# Tripwire #213 — stage-batch monitoring.
#
# Watches nesquena's release pipeline: if the gap between the newest
# published release (any kind, prereleases included) and now exceeds
# $THRESHOLD_HOURS AND commits have landed since (unreleased activity), the
# release pipeline is likely down. Early signal of maintainer outage.

set -eu
source "$(dirname "$0")/tripwire-common.sh"

# 2026-08-18 rework: the original detector keyed on "Stamp CHANGELOG"
# commit messages, but nesquena's release flow stopped producing those
# (releases now come via the exp-series process with occasional stable
# promotions) — #727 fired with an 823h "gap" while stable v0.52.113 had
# shipped days earlier. The pipeline-alive signal is now the newest
# *published release* of any kind: prereleases count, because an
# exp-series prerelease proves the release pipeline is running, which is
# what this tripwire watches (outage, not stable-promotion cadence).
THRESHOLD_HOURS=48

last_stamp_iso=$(gh api -X GET "repos/$WEBUI_REPO/releases" -f per_page=100 2>/dev/null \
                   | jq -r '[.[] | select(.draft == false)] | sort_by(.published_at) | last | .published_at // empty' \
                   || true)

if [ -z "$last_stamp_iso" ]; then
    echo "[tripwire/stage-batch] no published release found; cannot evaluate"
    exit 0
fi

# Hours since the newest published release.
now_epoch=$(date -u +%s)
last_stamp_epoch=$(date -u -j -f '%Y-%m-%dT%H:%M:%SZ' "$last_stamp_iso" +%s 2>/dev/null \
                   || date -u -d "$last_stamp_iso" +%s)
gap_hours=$(( (now_epoch - last_stamp_epoch) / 3600 ))

# Commits since the newest release (i.e. unreleased work).
unreleased=$(gh api -X GET "repos/$WEBUI_REPO/commits" \
               -f sha="$WEBUI_BRANCH" -f since="$last_stamp_iso" --paginate 2>/dev/null \
               | jq -r '.[].sha' | wc -l | tr -d ' ')
[ "$unreleased" -lt 0 ] && unreleased=0

CLEAR_TITLE="[tripwire/stage-batch] $WEBUI_REPO release stamp gap >${THRESHOLD_HOURS}h"

if [ "$gap_hours" -lt "$THRESHOLD_HOURS" ]; then
    echo "[tripwire/stage-batch] newest release $gap_hours h ago (< $THRESHOLD_HOURS h); condition clear"
    tripwire_clear "$CLEAR_TITLE" "Newest published release was $gap_hours h ago (under ${THRESHOLD_HOURS}h threshold)."
    exit 0
fi

if [ "$unreleased" -eq 0 ]; then
    echo "[tripwire/stage-batch] $gap_hours h since newest release BUT no unreleased commits; condition clear (quiet period)"
    tripwire_clear "$CLEAR_TITLE" "No unreleased commits — quiet period, not a stall."
    exit 0
fi

body=$(cat <<EOF
## Stage-batch release stamp gap on \`$WEBUI_REPO\`

Newest published release on \`$WEBUI_REPO\` (prereleases included) was **$gap_hours hours ago** ($last_stamp_iso). Since then, **$unreleased commits** have landed on \`$WEBUI_BRANCH\` without a new release of any kind.

Threshold: $THRESHOLD_HOURS hours.

## Why this matters

\`nesquena\`'s normal cadence is a stage-NNN release within hours of merging stage-N commits. A multi-day gap with unreleased work usually signals the release pipeline broke (CI failure, deployment block, maintainer outage).

## Actions

- [ ] Check \`$WEBUI_REPO\`'s Actions tab for failing release runs
- [ ] Read recent unreleased commits — anything indicating intentional release delay?
- [ ] If genuine stall, surface to upstream via issue
- [ ] If intentional pause (e.g. holiday, planned reorg), close this issue

EOF
)

tripwire_fire \
    "[tripwire/stage-batch] $WEBUI_REPO release stamp gap >${THRESHOLD_HOURS}h" \
    "$body" \
    "tripwire-fire,tripwire/stage-batch,P2"
