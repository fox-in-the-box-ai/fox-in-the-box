# .github/scripts/tripwire-common.sh
#
# Shared helpers sourced by every tripwire script. Keep this thin —
# anything that diverges per-tripwire stays in the per-tripwire script.

set -eu

REPO="${GITHUB_REPOSITORY:-fox-in-the-box-ai/fox-in-the-box}"
RUN_URL="${GITHUB_SERVER_URL:-https://github.com}/${REPO}/actions/runs/${GITHUB_RUN_ID:-local}"

# Open or re-fire an issue. De-dupe by exact title match.
#
# Usage:
#   tripwire_fire "<exact-title>" "<body markdown>" "<comma,sep,labels>"
#
# If an open issue with the same title exists, comment "Re-fired on
# <RUN_URL>" + the new body on it. Otherwise create.
tripwire_fire() {
    local title="$1"
    local body="$2"
    local labels="$3"

    local existing
    existing=$(gh issue list --repo "$REPO" --state open \
                 --search "in:title \"$title\"" \
                 --json number,title \
                 -q ".[] | select(.title == \"$title\") | .number" \
                 2>/dev/null | head -1)

    if [ -n "$existing" ]; then
        gh issue comment "$existing" --repo "$REPO" --body "$(printf '%s\n\n_Re-fired on %s_' "$body" "$RUN_URL")"
        echo "[tripwire] re-fired existing issue #$existing"
        return 0
    fi

    # Build --label args from comma-separated list. Idempotently create
    # any missing labels first; `gh issue create --label X` errors out if
    # X doesn't exist in the repo, and we don't want to pre-seed labels
    # by hand or in a separate workflow step. `gh label create --force`
    # is the idempotent variant: creates if missing, updates if present.
    local label_args=()
    IFS=',' read -ra parts <<<"$labels"
    for l in "${parts[@]}"; do
        l="$(echo "$l" | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')"
        [ -z "$l" ] && continue
        # Best-effort: don't fail the tripwire if label creation hits a
        # permissions issue (the issue creation will surface the error).
        gh label create "$l" --repo "$REPO" --force \
            --color "$(tripwire_label_color "$l")" \
            --description "auto-created by upstream-tripwires.yml" >/dev/null 2>&1 || true
        label_args+=("--label" "$l")
    done

    gh issue create --repo "$REPO" \
        --title "$title" \
        --body "$(printf '%s\n\n_Fired by upstream-tripwires.yml run %s_' "$body" "$RUN_URL")" \
        "${label_args[@]}"
}

# Stable colour per label family so the issue list reads at a glance.
tripwire_label_color() {
    case "$1" in
        tripwire-fire)         echo "d73a4a" ;;  # red
        tripwire-self-health)  echo "fbca04" ;;  # yellow
        tripwire/cve|security) echo "b60205" ;;  # dark red
        tripwire/license)      echo "5319e7" ;;  # purple
        tripwire/branch|tripwire/nous-ui) echo "d93f0b" ;;  # orange
        tripwire/*)            echo "1d76db" ;;  # blue (generic tripwire scope)
        P0)                    echo "b60205" ;;
        P1)                    echo "d93f0b" ;;
        P2)                    echo "fbca04" ;;
        *)                     echo "cccccc" ;;
    esac
}

# Read JSON state file (one shared file per category), defaulting to "{}"
# if missing. Used by license_watch + branch_watch for diff baselines.
tripwire_state_read() {
    local path="$1"
    if [ -f "$path" ]; then
        cat "$path"
    else
        echo "{}"
    fi
}

# Pretty-print the date used in titles so dedupe works across days. Keep
# titles STABLE across days — only the body/comment date changes.
tripwire_today() {
    date -u +%Y-%m-%d
}
