#!/usr/bin/env bash
# Tripwire #209 — branch-creation watch.
#
# Lists upstream branches; fires on any branch name matching the rewrite-
# regex. Stateless — dedupe is by branch name in the issue title: an OPEN
# same-title issue gets a re-fire comment; a CLOSED one is a standing
# acknowledgement of that branch (ack_dedupe) and suppresses re-fire.
# Accepted tradeoff: a dispositioned branch deleted and later re-created
# under the same name will not alert again.

set -eu
source "$(dirname "$0")/tripwire-common.sh"

# Rewrite-signal regexes, tightened after three false positives on
# 2026-08-14 (#722 'centaur-port/slack-reaction-context' — 'react' inside
# 'reaction'; #724 'feat/skill-react-best-practices' — a skill doc, not a
# frontend rewrite of a Python backend; #726 'fix/electron-41-major' — a
# fix branch, not a major rewrite):
# - tokens must be whole path segments (bounded by / _ - or string edge),
# - frontend-framework tokens apply only to the webui repo — the agent
#   repo is a Python backend where such branch names are docs/skills,
# - conventional maintenance prefixes are excluded outright.
COMMON_REGEX='(^|[/_-])(rewrite|major)([/_-]|$)|^v[0-9]+$|^next$'
WEBUI_REGEX="$COMMON_REGEX|(^|[/_-])(react|vue|svelte|preact)([/_-]|\$)"
EXCLUDE_REGEX='^(fix|chore|docs|test|ci)/'

check_repo() {
    local repo="$1"
    local regex="$2"
    local matches
    matches=$(git ls-remote --heads "https://github.com/$repo.git" 2>/dev/null \
              | awk '{sub("refs/heads/", "", $2); print $2}' \
              | grep -ivE "$EXCLUDE_REGEX" \
              | grep -iE "$regex" \
              | grep -vE '^(master|main)$' \
              || true)

    if [ -z "$matches" ]; then
        echo "[tripwire/branch] $repo: no rewrite-regex branches"
        return 0
    fi

    while IFS= read -r branch; do
        [ -z "$branch" ] && continue
        body=$(cat <<EOF
## Upstream \`$repo\` has a branch matching rewrite-regex

Branch: **\`$branch\`**

The regex \`$regex\` flags branches that historically signal:
- A major version bump (\`v2\`, \`v3\`, etc.)
- A long-running rewrite (\`rewrite\`, \`major\` as a path segment)
- An upstream "next-gen" branch (\`next\`)
- On the webui repo only: a frontend-framework rewrite (\`react\`, \`vue\`, \`svelte\`, \`preact\`)

Maintenance-prefixed branches (\`fix/\`, \`chore/\`, \`docs/\`, \`test/\`, \`ci/\`) are excluded.

**Why this matters:** if upstream merges a rewrite branch to default, the Fox overlay's anchors will catastrophically fail — most or all monkey-patch substitutions will miss. Plan a strategic re-evaluation before that merge lands.

## Actions

- [ ] Inspect the branch: https://github.com/$repo/tree/$branch
- [ ] Read the latest commits to understand intent
- [ ] If serious, file a Fox strategic-review issue and notify Dennis
- [ ] If false positive (e.g. unrelated feature name happens to match \`major\`), close this issue — dedupe will not re-fire unless a different matching branch appears

EOF
)
        tripwire_fire \
            "[tripwire/branch] $repo has rewrite-regex branch: $branch" \
            "$body" \
            "tripwire-fire,tripwire/branch,P1" \
            ack_dedupe
    done <<<"$matches"
}

check_repo "$WEBUI_REPO" "$WEBUI_REGEX"
check_repo "$AGENT_REPO" "$COMMON_REGEX"
