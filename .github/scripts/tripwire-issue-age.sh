#!/usr/bin/env bash
# Tripwire #216 — open-issue-age sentry.
#
# Fires when the oldest open issue on either upstream is > $THRESHOLD_DAYS
# old AND the upstream itself is < $UPSTREAM_AGE_MAX_MONTHS months old (so
# this catches "active project, neglected issues" rather than misfiring on
# mature projects with naturally old backlog).

set -eu
source "$(dirname "$0")/tripwire-common.sh"

THRESHOLD_DAYS=90
UPSTREAM_AGE_MAX_MONTHS=12

check_repo() {
    local repo="$1"

    # Upstream age (in months).
    local created
    created=$(gh api "repos/$repo" -q .created_at 2>/dev/null || echo "")
    [ -z "$created" ] && { echo "[tripwire/issue-age] $repo: cannot read created_at; skip"; return 0; }

    local created_epoch now_epoch upstream_age_months
    created_epoch=$(date -u -j -f '%Y-%m-%dT%H:%M:%SZ' "$created" +%s 2>/dev/null \
                    || date -u -d "$created" +%s)
    now_epoch=$(date -u +%s)
    upstream_age_months=$(( (now_epoch - created_epoch) / 2592000 ))  # ~30d/mo

    if [ "$upstream_age_months" -gt "$UPSTREAM_AGE_MAX_MONTHS" ]; then
        echo "[tripwire/issue-age] $repo: upstream age $upstream_age_months mo > cap $UPSTREAM_AGE_MAX_MONTHS mo; skip (mature project)"
        return 0
    fi

    # Oldest open issue (`gh api` sorts asc by created with `-f sort=created -f direction=asc`).
    local oldest
    oldest=$(gh api -X GET "repos/$repo/issues" \
              -f state=open -f sort=created -f direction=asc -f per_page=1 2>/dev/null \
              | jq -c '.[0] // empty' \
              2>/dev/null || true)

    if [ -z "$oldest" ]; then
        echo "[tripwire/issue-age] $repo: no open issues; no-op"
        return 0
    fi

    local oldest_iso oldest_num oldest_title oldest_url
    oldest_iso=$(echo "$oldest" | jq -r .created_at)
    oldest_num=$(echo "$oldest" | jq -r .number)
    oldest_title=$(echo "$oldest" | jq -r .title)
    oldest_url=$(echo "$oldest" | jq -r .html_url)

    local oldest_epoch age_days
    oldest_epoch=$(date -u -j -f '%Y-%m-%dT%H:%M:%SZ' "$oldest_iso" +%s 2>/dev/null \
                   || date -u -d "$oldest_iso" +%s)
    age_days=$(( (now_epoch - oldest_epoch) / 86400 ))

    if [ "$age_days" -le "$THRESHOLD_DAYS" ]; then
        echo "[tripwire/issue-age] $repo: oldest open issue is $age_days days old (≤ $THRESHOLD_DAYS); no-op"
        return 0
    fi

    local body
    body=$(cat <<EOF
## Oldest open issue on \`$repo\` exceeds $THRESHOLD_DAYS days

| Field | Value |
|-------|-------|
| Oldest issue | [\`#$oldest_num\` $oldest_title]($oldest_url) |
| Created | $oldest_iso ($age_days days ago) |
| Upstream age | $upstream_age_months months (within $UPSTREAM_AGE_MAX_MONTHS-month freshness window) |

## Why this matters

Issue accretion in young projects signals maintainer triage capacity is below intake rate. Per Architect 3 §10, persistent issue-age growth on a young upstream is a leading indicator that Scenario A (maintainer overload → eventual abandonment) is in play.

## Actions

- [ ] Inspect $oldest_url — is it truly neglected or just a low-priority enhancement?
- [ ] Skim the upstream's recent issue activity — is overall response time degrading?
- [ ] If yes: re-evaluate dependence on this upstream in v0.7.x planning
- [ ] If no (one-off neglected enhancement): close this issue; tripwire will re-fire if the new oldest issue also exceeds threshold

EOF
)

    tripwire_fire \
        "[tripwire/issue-age] $repo oldest open issue >${THRESHOLD_DAYS}d (#$oldest_num)" \
        "$body" \
        "tripwire-fire,tripwire/issue-age,P2"
}

check_repo "$WEBUI_REPO"
check_repo "$AGENT_REPO"
