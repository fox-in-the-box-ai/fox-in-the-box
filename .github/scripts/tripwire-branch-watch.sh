#!/usr/bin/env bash
# Tripwire #209 — branch-creation watch.
#
# Lists upstream branches; fires on any branch name matching the rewrite-
# regex. Stateless — dedupe is by branch name in the issue title, so once
# fired for "react", the issue gets re-fired (comment) not re-created.

set -eu
source "$(dirname "$0")/tripwire-common.sh"

REWRITE_REGEX='react|vue|svelte|preact|rewrite|^v[0-9]+$|^next$|major'

check_repo() {
    local repo="$1"
    local matches
    matches=$(git ls-remote --heads "https://github.com/$repo.git" 2>/dev/null \
              | awk '{sub("refs/heads/", "", $2); print $2}' \
              | grep -iE "$REWRITE_REGEX" \
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

The regex \`$REWRITE_REGEX\` flags branches that historically signal:
- A framework rewrite (\`react\`, \`vue\`, \`svelte\`, \`preact\`)
- A major version bump (\`v2\`, \`v3\`, etc.)
- A long-running rewrite (\`rewrite\`, \`major\`)
- An upstream "next-gen" branch (\`next\`)

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
            "tripwire-fire,tripwire/branch,P1"
    done <<<"$matches"
}

check_repo "$WEBUI_REPO"
check_repo "$AGENT_REPO"
