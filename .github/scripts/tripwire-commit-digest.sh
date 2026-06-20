#!/usr/bin/env bash
# Tripwire #207 — daily upstream-commit digest.
#
# Fires once per day with the previous 24h of commits on each upstream,
# highlighting commits matching keyword regex AND commits touching the
# "always-conflict" file set. If both upstreams had zero commits AND no
# keyword matches, no-op (don't open a noise issue).

set -eu
source "$(dirname "$0")/tripwire-common.sh"

KEYWORDS='breaking|deprecat|migration|rewrite|schema|password|auth|csrf|xss|injection'
CONFLICT_FILES='api/routes.py|api/onboarding.py|api/streaming.py|api/config.py|static/index.html|static/panels.js'

since=$(date -u -v-1d +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -d '24 hours ago' +%Y-%m-%dT%H:%M:%SZ)

# Returns markdown list of commits since $since for the given repo+branch.
# Each line: "- {sha} {author}: {message-first-line}"
list_commits() {
    local repo="$1" branch="$2"
    gh api -X GET "repos/$repo/commits" \
        -f sha="$branch" -f since="$since" --paginate 2>/dev/null \
        | jq -r '.[] | "- `\(.sha[0:7])` \(.commit.author.name): \(.commit.message | split("\n")[0])"' \
        || true
}

# Returns repo's commit count touching any of $CONFLICT_FILES since $since.
list_conflict_commits() {
    local repo="$1" branch="$2"
    local count=0
    local out=""
    IFS='|' read -ra paths <<<"$CONFLICT_FILES"
    for p in "${paths[@]}"; do
        local shas
        shas=$(gh api -X GET "repos/$repo/commits" \
                 -f sha="$branch" -f path="$p" -f since="$since" --paginate 2>/dev/null \
                 | jq -r '.[] | "\(.sha[0:7]) \(.commit.author.name): \(.commit.message | split("\n")[0])"' \
                 || true)
        if [ -n "$shas" ]; then
            out="$out\n\n**Touched \`$p\`**:\n$(echo "$shas" | sed 's/^/- `/' | sed 's/ /` /')"
            count=$((count + $(echo "$shas" | grep -c '^' || true)))
        fi
    done
    echo "$count"
    printf '%s' "$out"
}

webui=$(list_commits "$WEBUI_REPO" "$WEBUI_BRANCH")
agent=$(list_commits "$AGENT_REPO" "$AGENT_BRANCH")

# Filter to keyword hits.
webui_kw=$(echo "$webui" | grep -iE "$KEYWORDS" || true)
agent_kw=$(echo "$agent" | grep -iE "$KEYWORDS" || true)

# Conflict-file fires (returns: count\nmarkdown)
webui_conf_full=$(list_conflict_commits "$WEBUI_REPO" "$WEBUI_BRANCH")
webui_conf_count=$(echo "$webui_conf_full" | head -1)
webui_conf_md=$(echo "$webui_conf_full" | tail -n +2)

webui_count=$(echo "$webui" | grep -c '^-' || true)
agent_count=$(echo "$agent" | grep -c '^-' || true)

CLEAR_TITLE="[tripwire/digest] upstream-commit digest (rolling)"

# No-op if zero activity AND zero keyword hits AND zero conflict-file fires.
if [ "$webui_count" = "0" ] && [ "$agent_count" = "0" ] \
   && [ -z "$webui_kw" ] && [ -z "$agent_kw" ] \
   && [ "$webui_conf_count" = "0" ]; then
    echo "[tripwire/digest] no upstream activity in last 24h; condition clear"
    tripwire_clear "$CLEAR_TITLE" "No upstream activity in the last 24h."
    exit 0
fi

# Only fire issue if there's something noteworthy (keyword OR conflict file).
# Plain commit counts go to log only, not an issue.
if [ -z "$webui_kw" ] && [ -z "$agent_kw" ] && [ "$webui_conf_count" = "0" ]; then
    echo "[tripwire/digest] $webui_count webui + $agent_count agent commits in last 24h; nothing noteworthy"
    tripwire_clear "$CLEAR_TITLE" "Activity present but no keyword or conflict-file hits."
    exit 0
fi

today=$(tripwire_today)
body=$(cat <<EOF
## Upstream activity digest (24h ending $today)

| Upstream | Total commits | Keyword-flagged | Touched always-conflict file |
|----------|--------------|------------------|------------------------------|
| ${WEBUI_REPO}@${WEBUI_BRANCH} | $webui_count | $(echo "$webui_kw" | grep -c '^-' || echo 0) | $webui_conf_count |
| ${AGENT_REPO}@${AGENT_BRANCH} | $agent_count | $(echo "$agent_kw" | grep -c '^-' || echo 0) | n/a |

### Keyword matches (regex: \`$KEYWORDS\`)

**${WEBUI_REPO}:**
${webui_kw:-_(none)_}

**${AGENT_REPO}:**
${agent_kw:-_(none)_}

### Always-conflict file touches (regex: \`$CONFLICT_FILES\`)

${webui_conf_md:-_(none)_}

---

**Action:** review listed commits; if any will conflict with the Fox overlay anchors, plan a pre-emptive anchor refresh before the next \`upstream-watch.yml\` auto-PR opens.
EOF
)

tripwire_fire \
    "[tripwire/digest] upstream-commit digest (rolling)" \
    "$body" \
    "tripwire-fire,tripwire/digest"
