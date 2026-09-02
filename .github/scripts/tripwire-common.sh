# .github/scripts/tripwire-common.sh
#
# Shared helpers sourced by every tripwire script. Keep this thin —
# anything that diverges per-tripwire stays in the per-tripwire script.

set -eu

REPO="${GITHUB_REPOSITORY:-fox-in-the-box-ai/fox-in-the-box}"
RUN_URL="${GITHUB_SERVER_URL:-https://github.com}/${REPO}/actions/runs/${GITHUB_RUN_ID:-local}"
# Actions sets GITHUB_WORKFLOW to the calling workflow's name; issues and
# labels created by the helpers cite it so callers outside
# upstream-tripwires.yml (e.g. build-container.yml's main_push_health)
# carry correct provenance.
SOURCE_WORKFLOW="${GITHUB_WORKFLOW:-upstream-tripwires.yml}"

# Bounded-retry gh issue lookup (#774): a transient API failure (429,
# network) must not read as "no matching issue" — in the fire path that
# stacks a duplicate, in the ack path it re-fires an acknowledged
# condition, and in the clear path it silently skips the close. Retry
# 3x with backoff; on exhaustion fail the script. In
# upstream-tripwires.yml the self-health handler then reports the API
# outage once; the other sourcing workflows (build-container
# main_push_health, playwright cron_health) have no such backstop — an
# exhaustion there fails the handler step, so the signal is the red
# run itself, not an issue. (Immediate exit-1 without retry was rejected
# in #774: one 429 blip would fail all ten tripwires.)
# Uses TW_TITLE from the environment for both the server-side search
# narrowing and the exact jq match — same injection rule as the callers.
_tw_issue_numbers() {
    local state="$1"
    local attempt out err errfile
    errfile=$(mktemp)
    # Expand errfile now (it never changes) — hence double quotes.
    # shellcheck disable=SC2064
    trap "rm -f '$errfile'" RETURN
    for attempt in 1 2 3; do
        # stderr goes to a file, NOT 2>&1 — a success-with-warning would
        # otherwise mix warning text into the captured number list and
        # head -1 could read a warning line as an issue number.
        if out=$(gh issue list --repo "$REPO" --state "$state" --limit 100 \
                   --search "in:title \"$TW_TITLE\"" \
                   --json number,title \
                   -q '.[] | select(.title == env.TW_TITLE) | .number' 2>"$errfile"); then
            rm -f "$errfile"
            printf '%s\n' "$out"
            return 0
        fi
        err=$(cat "$errfile" 2>/dev/null || true)
        echo "[tripwire] gh issue list ($state) failed (attempt $attempt/3): $err" >&2
        [ "$attempt" -lt 3 ] && sleep $((attempt * 5))
    done
    rm -f "$errfile"
    # >&2: inside $(…) capture, stdout is swallowed into the (discarded)
    # assignment — the annotation must ride stderr to reach the job log.
    echo "::error::gh issue list ($state) failed after 3 attempts — cannot determine tripwire issue state for: $TW_TITLE" >&2
    return 1
}

# Open or re-fire an issue. De-dupe by exact title match.
#
# Usage:
#   tripwire_fire "<exact-title>" "<body markdown>" "<comma,sep,labels>" [ack_dedupe]
#
# If an open issue with the same title exists, comment "Re-fired on
# <RUN_URL>" + the new body on it. Otherwise create.
#
# Pass "ack_dedupe" as the 4th arg for tripwires whose titles name a
# SPECIFIC subject (an upstream issue number, a branch name): a CLOSED
# issue with the same title then counts as a human acknowledgement and
# the fire is skipped instead of re-created (#747 re-fired nightly after
# #723 was dispositioned). A different subject produces a different
# title, so genuinely new conditions still fire. Do NOT use it for
# recurring-condition tripwires with stable titles (absence, stage-batch)
# — there a past closed issue must not suppress a future real fire.
tripwire_fire() {
    local title="$1"
    local body="$2"
    local labels="$3"
    local mode="${4:-}"

    # Titles reach jq via the environment (env.TW_TITLE), never by
    # splicing into the program text: branch-watch titles embed
    # upstream-controlled branch names, and a crafted name containing
    # jq-significant characters must not be able to break the filter —
    # in the ack path that breakage would SUPPRESS a P1 fire.
    export TW_TITLE="$title"

    if [ "$mode" = "ack_dedupe" ]; then
        local acked
        acked=$(_tw_issue_numbers closed)
        acked=$(printf '%s' "$acked" | head -1)
        if [ -n "$acked" ]; then
            echo "[tripwire] condition previously acknowledged in closed #$acked — skipping re-fire"
            return 0
        fi
    fi

    local existing
    existing=$(_tw_issue_numbers open)
    existing=$(printf '%s' "$existing" | head -1)

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
            --description "auto-created by $SOURCE_WORKFLOW" >/dev/null 2>&1 || true
        label_args+=("--label" "$l")
    done

    gh issue create --repo "$REPO" \
        --title "$title" \
        --body "$(printf '%s\n\n_Fired by %s run %s_' "$body" "$SOURCE_WORKFLOW" "$RUN_URL")" \
        "${label_args[@]}"
}

# Close an existing tripwire issue when the condition clears.
#
# Usage:
#   tripwire_clear "<exact-title>" "<reason>"
#
# If an open issue with the same title exists, comment with the reason
# and close it. Otherwise no-op.
tripwire_clear() {
    local title="$1"
    local reason="$2"

    export TW_TITLE="$title"
    local numbers
    numbers=$(_tw_issue_numbers open)

    if [ -z "$numbers" ]; then
        return 0
    fi

    echo "$numbers" | while read -r num; do
        gh issue comment "$num" --repo "$REPO" \
            --body "$(printf 'Condition cleared: %s\n\n_Auto-closed by %s run %s_' "$reason" "$SOURCE_WORKFLOW" "$RUN_URL")" \
            || echo "[tripwire] warning: failed to comment on #$num"
        gh issue close "$num" --repo "$REPO" --reason "completed" \
            || echo "[tripwire] warning: failed to close #$num"
        echo "[tripwire] auto-closed issue #$num — condition cleared"
    done
}

# Stable colour per label family so the issue list reads at a glance.
tripwire_label_color() {
    case "$1" in
        tripwire-fire)         echo "d73a4a" ;;  # red
        tripwire-self-health)  echo "fbca04" ;;  # yellow
        ci-health)             echo "b60205" ;;  # dark red — main-push pipeline failures
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
