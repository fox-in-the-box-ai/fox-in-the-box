#!/usr/bin/env bash
# Tripwire #210 — NousResearch official-UI watch.
#
# Checks for the appearance of `webui/`, `frontend/`, or `static/`
# directories at the root of NousResearch/hermes-agent. Their appearance
# would signal NousResearch is shipping their own UI — Fox should pivot
# to "build-our-own" per Architect 3 §8 Scenario B.

set -eu
source "$(dirname "$0")/tripwire-common.sh"

# `gh api repos/{owner}/{repo}/contents/` lists root dir; filter for any
# directory entry whose name matches our watch list.
dirs=$(gh api "repos/$AGENT_REPO/contents?ref=$AGENT_BRANCH" \
        -q '.[] | select(.type=="dir") | .name' 2>/dev/null || true)

watch_list="webui frontend static ui app react-app"
matches=""
for d in $dirs; do
    for w in $watch_list; do
        if [ "$d" = "$w" ]; then
            matches="$matches $d"
        fi
    done
done

# Trim leading whitespace.
matches="$(echo "$matches" | sed -E 's/^[[:space:]]+//')"

if [ -z "$matches" ]; then
    echo "[tripwire/nous-ui] no UI-suggestive dir at root of $AGENT_REPO"
    exit 0
fi

body=$(cat <<EOF
## CRITICAL — NousResearch may be shipping an official UI

\`$AGENT_REPO@$AGENT_BRANCH\` root now contains UI-suggestive directories:

$(printf -- '- `%s/`\n' $matches)

If NousResearch ships an official UI, the calculus for depending on \`nesquena/hermes-webui\` changes substantially. Per Architect 3 §8 Scenario B: pivot Fox to either (a) use the official UI directly with a thin Fox overlay, or (b) build Fox's own UI.

## Actions

- [ ] Inspect the directory: https://github.com/$AGENT_REPO/tree/$AGENT_BRANCH/$(echo $matches | awk '{print $1}')
- [ ] Read NousResearch's announcement / discussion / README context
- [ ] Strategic review with Dennis — does this change v0.7.x / v0.8.x direction?
- [ ] If false positive (dir exists for unrelated reasons), close this issue

EOF
)

tripwire_fire \
    "[tripwire/nous-ui] $AGENT_REPO root contains UI-suggestive directory" \
    "$body" \
    "tripwire-fire,tripwire/nous-ui,P0"
