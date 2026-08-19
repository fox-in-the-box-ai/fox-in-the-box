#!/usr/bin/env bash
# Tripwire — scheduled-run health (added in the 2026-08-19 verification
# sweep; unlike #207-#216 this one has no spec issue under epic #206).
#
# A scheduled workflow whose runner is offline (or whose runs queue
# forever and get cancelled) fails SILENTLY: no PR goes red, and the
# workflow's own failure handlers never execute. The windows-real-smoke
# nightly vanished this way for ~2 months (runner offline since late
# June, discovered 2026-08-19). This tripwire checks, for each watched
# scheduled workflow, when it last COMPLETED SUCCESSFULLY; older than
# the threshold fires one rolling ci-health issue per workflow.

set -eu
source "$(dirname "$0")/tripwire-common.sh"

# Default staleness threshold; per-entry ":<hours>" overrides it.
THRESHOLD_HOURS=48
# workflow-file[:allowed-staleness-hours], space-separated.
WATCHED="windows-real-smoke.yml"

now_epoch=$(date -u +%s)

for entry in $WATCHED; do
    wf="${entry%%:*}"
    case "$entry" in *:*) max_h="${entry##*:}" ;; *) max_h="$THRESHOLD_HOURS" ;; esac
    # An API failure must fail the JOB (into the tripwire-self-health
    # handler), never masquerade as "never succeeded" — a 403/rate-limit
    # would otherwise false-fire and permanently break auto-clear.
    if ! resp=$(gh api -X GET "repos/$REPO/actions/workflows/$wf/runs" \
                  -f status=success -f per_page=1 2>&1); then
        echo "::error::gh api failed for $wf runs: $resp"
        exit 1
    fi
    last_ok=$(printf '%s' "$resp" | jq -r '.workflow_runs[0].updated_at // empty')
    if [ -z "$last_ok" ]; then
        age_desc="never (no successful run on record)"
        stale=1
    else
        ok_epoch=$(date -u -j -f '%Y-%m-%dT%H:%M:%SZ' "$last_ok" +%s 2>/dev/null \
                   || date -u -d "$last_ok" +%s)
        age_h=$(( (now_epoch - ok_epoch) / 3600 ))
        age_desc="${age_h}h ago ($last_ok)"
        [ "$age_h" -gt "$max_h" ] && stale=1 || stale=0
    fi

    title="[ci-health] scheduled workflow $wf has no recent successful run (rolling)"
    if [ "$stale" -eq 0 ]; then
        tripwire_clear "$title" "Last successful run: $age_desc (within ${max_h}h)."
        echo "[tripwire/sched-health] $wf ok — last success $age_desc"
        continue
    fi

    body=$(cat <<BODY_EOF
## \`$wf\` has not completed successfully within ${max_h}h

Last successful run: **$age_desc**.

Queued-forever runs (offline self-hosted runner) and cancelled crons die
without any failure handler executing; this watchdog is the only signal.

## Resolution

- Self-hosted runner workflows: check the runner host is up and the
  runner service registered (Settings → Actions → Runners)
- Hosted crons: inspect the latest run's failure/cancellation
- Close this issue once a successful run lands; it re-fires if the
  condition returns
BODY_EOF
    )
    tripwire_fire "$title" "$body" "ci-health,P2"
done
