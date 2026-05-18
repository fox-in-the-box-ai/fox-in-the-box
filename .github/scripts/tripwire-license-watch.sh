#!/usr/bin/env bash
# Tripwire #208 — license watch.
#
# Compares the SHA-1 (git blob OID) of LICENSE on each upstream's default
# branch to the baseline SHA recorded in .github/state/upstream-licenses.json.
# Fires on any mismatch.
#
# Resolve by:
#   1. Reviewing the new LICENSE text on the upstream
#   2. If acceptable, editing .github/state/upstream-licenses.json with the
#      new SHA and merging — workflow will go quiet
#   3. If unacceptable (license change!), strategic decision required
#      before bumping the submodule pin

set -eu
source "$(dirname "$0")/tripwire-common.sh"

STATE_FILE=".github/state/upstream-licenses.json"

# Fetch current LICENSE SHA from each upstream.
current_webui_sha=$(gh api "repos/$WEBUI_REPO/contents/LICENSE?ref=$WEBUI_BRANCH" -q .sha 2>/dev/null || echo "MISSING")
current_agent_sha=$(gh api "repos/$AGENT_REPO/contents/LICENSE?ref=$AGENT_BRANCH" -q .sha 2>/dev/null || echo "MISSING")

state=$(tripwire_state_read "$STATE_FILE")
baseline_webui_sha=$(echo "$state" | jq -r '.webui // ""')
baseline_agent_sha=$(echo "$state" | jq -r '.agent // ""')

fires=()
if [ -n "$baseline_webui_sha" ] && [ "$baseline_webui_sha" != "$current_webui_sha" ]; then
    fires+=("$WEBUI_REPO: $baseline_webui_sha → $current_webui_sha")
fi
if [ -n "$baseline_agent_sha" ] && [ "$baseline_agent_sha" != "$current_agent_sha" ]; then
    fires+=("$AGENT_REPO: $baseline_agent_sha → $current_agent_sha")
fi

# Empty baseline = first run; just log and exit without firing. Bootstrap
# the baseline by editing $STATE_FILE manually with today's SHAs.
if [ -z "$baseline_webui_sha" ] && [ -z "$baseline_agent_sha" ]; then
    echo "[tripwire/license] baseline empty; bootstrap $STATE_FILE with:"
    echo "  webui ($WEBUI_REPO): $current_webui_sha"
    echo "  agent ($AGENT_REPO): $current_agent_sha"
    exit 0
fi

if [ ${#fires[@]} -eq 0 ]; then
    echo "[tripwire/license] both LICENSE SHAs match baseline; no-op"
    exit 0
fi

body=$(cat <<EOF
## LICENSE drift detected on at least one upstream

$(printf -- '- %s\n' "${fires[@]}")

The baseline SHA in \`$STATE_FILE\` no longer matches the upstream LICENSE file's blob SHA. Possible causes:
1. **Cosmetic change** (formatting, copyright year bump) — acceptable; update baseline and move on.
2. **Material license change** — STOP. Do not bump the submodule pin until legal/compliance review.

## Resolution

1. Inspect the diff:
   \`\`\`
   gh api repos/$WEBUI_REPO/contents/LICENSE?ref=$WEBUI_BRANCH -q .content | base64 -d
   gh api repos/$AGENT_REPO/contents/LICENSE?ref=$AGENT_BRANCH -q .content | base64 -d
   \`\`\`
2. If accepted: open a PR updating \`$STATE_FILE\` with the new SHA(s) — workflow will go quiet.
3. If material: file a P0 + halt the next \`upstream-watch.yml\` bump-PR until resolved.
EOF
)

tripwire_fire \
    "[tripwire/license] upstream LICENSE drift" \
    "$body" \
    "tripwire-fire,tripwire/license,P1"
