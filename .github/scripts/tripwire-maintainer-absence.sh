#!/usr/bin/env bash
# Tripwire #211 — maintainer absence canary (nesquena).
#
# Fires if `nesquena` (the upstream webui maintainer) has zero commits to
# nesquena/hermes-webui in the last N days. Default N=5 (matches v0.6.0
# baseline of "zero 5+ day gaps in 48 days").

set -eu
source "$(dirname "$0")/tripwire-common.sh"

MAINTAINER="nesquena"
WINDOW_DAYS=5

since=$(date -u -v-${WINDOW_DAYS}d +%Y-%m-%dT%H:%M:%SZ 2>/dev/null \
        || date -u -d "$WINDOW_DAYS days ago" +%Y-%m-%dT%H:%M:%SZ)

count=$(gh api -X GET "repos/$WEBUI_REPO/commits" \
          -f sha="$WEBUI_BRANCH" -f author="$MAINTAINER" -f since="$since" --paginate 2>/dev/null \
          | jq -r '.[].sha' | wc -l | tr -d ' ')

if [ "$count" -gt 0 ]; then
    echo "[tripwire/absence] $MAINTAINER: $count commits in last $WINDOW_DAYS days; no-op"
    exit 0
fi

body=$(cat <<EOF
## \`$MAINTAINER\` silent for $WINDOW_DAYS+ days on \`$WEBUI_REPO\`

Baseline at v0.6.0: zero gaps of $WINDOW_DAYS+ silent days in 48 observed days. Today's run finds zero \`$MAINTAINER\`-authored commits to \`$WEBUI_BRANCH\` since $since.

## Why this matters

\`$WEBUI_REPO\` is Fox's webui submodule source. If \`$MAINTAINER\` becomes unresponsive (illness, life event, abandonment), the project enters Scenario A per Architect 3 §8: Fox eventually has to fork-and-stop or migrate to an alternative.

## Actions

- [ ] Check \`$MAINTAINER\`'s public activity: https://github.com/$MAINTAINER
- [ ] Inspect \`$WEBUI_REPO\`'s issue tracker for maintainer comments in the last week
- [ ] If genuinely absent for an extended period: re-evaluate v0.6.x/v0.7.x strategy
- [ ] Debounce: during known multi-week migrations (e.g. our own v0.6.0), this fires spuriously — close this issue if context explains the gap

EOF
)

tripwire_fire \
    "[tripwire/absence] $MAINTAINER silent for $WINDOW_DAYS+ days on $WEBUI_REPO" \
    "$body" \
    "tripwire-fire,tripwire/absence,P1"
