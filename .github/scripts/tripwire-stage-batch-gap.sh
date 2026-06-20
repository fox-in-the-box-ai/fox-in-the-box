#!/usr/bin/env bash
# Tripwire #213 — stage-batch monitoring.
#
# nesquena's release cadence stamps commits with messages like
# "Stamp CHANGELOG for v0.51.84 (Release BH / stage-377)".
# If the gap between the most-recent such stamp and now > $THRESHOLD_HOURS
# AND there have been non-stamp commits since (unreleased activity), the
# release pipeline is likely down. Early signal of maintainer outage.

set -eu
source "$(dirname "$0")/tripwire-common.sh"

STAMP_REGEX='Stamp CHANGELOG'
THRESHOLD_HOURS=48

last_stamp_iso=$(gh api -X GET "repos/$WEBUI_REPO/commits" \
                   -f sha="$WEBUI_BRANCH" -f per_page=100 --paginate 2>/dev/null \
                   | jq -r '.[] | select(.commit.message | test("'"$STAMP_REGEX"'")) | .commit.committer.date' \
                   2>/dev/null \
                   | head -1 || true)

if [ -z "$last_stamp_iso" ]; then
    echo "[tripwire/stage-batch] no stamp commit found in recent history; cannot evaluate"
    exit 0
fi

# Hours since last stamp.
now_epoch=$(date -u +%s)
last_stamp_epoch=$(date -u -j -f '%Y-%m-%dT%H:%M:%SZ' "$last_stamp_iso" +%s 2>/dev/null \
                   || date -u -d "$last_stamp_iso" +%s)
gap_hours=$(( (now_epoch - last_stamp_epoch) / 3600 ))

# Commits since the last stamp (i.e. unreleased work).
unreleased=$(gh api -X GET "repos/$WEBUI_REPO/commits" \
               -f sha="$WEBUI_BRANCH" -f since="$last_stamp_iso" --paginate 2>/dev/null \
               | jq -r '.[].sha' | wc -l | tr -d ' ')
# Subtract 1 (the stamp itself is in the range).
unreleased=$((unreleased - 1))
[ "$unreleased" -lt 0 ] && unreleased=0

CLEAR_TITLE="[tripwire/stage-batch] $WEBUI_REPO release stamp gap >${THRESHOLD_HOURS}h"

if [ "$gap_hours" -lt "$THRESHOLD_HOURS" ]; then
    echo "[tripwire/stage-batch] last stamp $gap_hours h ago (< $THRESHOLD_HOURS h); condition clear"
    tripwire_clear "$CLEAR_TITLE" "Last stamp was $gap_hours h ago (under ${THRESHOLD_HOURS}h threshold)."
    exit 0
fi

if [ "$unreleased" -eq 0 ]; then
    echo "[tripwire/stage-batch] $gap_hours h since last stamp BUT no unreleased commits; condition clear (quiet period)"
    tripwire_clear "$CLEAR_TITLE" "No unreleased commits — quiet period, not a stall."
    exit 0
fi

body=$(cat <<EOF
## Stage-batch release stamp gap on \`$WEBUI_REPO\`

Last \`$STAMP_REGEX\` commit on \`$WEBUI_BRANCH\` was **$gap_hours hours ago** ($last_stamp_iso). Since then, **$unreleased non-stamp commits** have landed without a new release stamp.

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
