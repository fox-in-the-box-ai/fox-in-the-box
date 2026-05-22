#!/usr/bin/env bash
#
# check-overlay-basis.sh — overlay basis sanity check for v0.6.0+.
#
# Detect upstream rename/delete of any file the overlay depends on:
#
# 1. .fox-removals entries — each path MUST exist in the webui submodule
#    (otherwise the manifest is stale; upstream renamed/removed it out
#    from under us, and the next container build silently won't perform
#    the intended removal).
# 2. patches/webui/series + patches/agent/series — each .patch MUST apply
#    --check cleanly against the current submodule pointer (otherwise
#    upstream's churn invalidated the anchor).
#
# Runs as a CI gate BEFORE the Docker build. Failure means: either
# (a) the submodule pin needs to be rolled back to the previous tag
# the overlay tracked, or (b) the manifest/patches need refresh for
# the new upstream tag.
#
# Made real in Phase 8 follow-up #246 (was an empty `exit 0` stub
# from Phase 1).
#
# Exit codes:
#   0 = overlay basis is clean against current submodule pointers
#   1 = at least one mismatch — diagnostics printed to stderr; CI fails

set -eu

REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
OVERLAY="$REPO_ROOT/packages/fox-overlay"
WEBUI="$REPO_ROOT/forks/hermes-webui"
AGENT="$REPO_ROOT/forks/hermes-agent"

failed=0

note() { printf '[check-overlay-basis] %s\n' "$*"; }
fail() { printf '[check-overlay-basis] FAIL: %s\n' "$*" >&2; failed=1; }

# ── 1. .fox-removals entries must exist in the webui submodule ──────────────
removals_file="$OVERLAY/.fox-removals"
if [ ! -f "$removals_file" ]; then
    fail "missing manifest: $removals_file"
else
    note "checking .fox-removals entries against $WEBUI"
    while IFS= read -r entry; do
        # Strip blanks + comments (same convention as the Dockerfile consumer).
        entry="${entry%%#*}"
        entry="$(printf '%s' "$entry" | tr -d '\r' | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')"
        [ -z "$entry" ] && continue
        if [ ! -e "$WEBUI/$entry" ]; then
            fail ".fox-removals entry missing in upstream: $entry"
        fi
    done < "$removals_file"
fi

# ── 2. webui patch series must apply --check SEQUENTIALLY against current ──
# v0.7.15 fix: previously this loop did `git apply --check` independently
# for each patch against the virgin submodule. That works for single-file
# patches that don't overlap, but FAILS for stacked patches where 003's
# hunks reference lines that only exist after 001+002 have been applied
# (the actual Dockerfile applies in-order, so 003 succeeds at build time).
# The mismatch let v0.7.13 ship with patch 003's series entry missing —
# basis check said "all 2 patches clean" because 003 wasn't in series,
# Dockerfile built without 003, #331 stayed broken. New behavior: apply
# each patch to a SCRATCH WORKING TREE in order, mirroring the Dockerfile.
webui_series="$OVERLAY/patches/webui/series"
if [ -f "$webui_series" ]; then
    note "checking webui patch series against $WEBUI ($(cd "$WEBUI" && git describe --tags --always 2>/dev/null || echo unknown))"
    # Working scratch: a temporary git tree we can apply patches against
    # in sequence without polluting the submodule's working dir. Use
    # `git stash` semantics: stash any state, apply, check, reset.
    SCRATCH_RESULT=0
    (cd "$WEBUI" && git stash --include-untracked --quiet 2>/dev/null || true)
    while IFS= read -r patch; do
        patch="${patch%%#*}"
        patch="$(printf '%s' "$patch" | tr -d '\r' | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')"
        [ -z "$patch" ] && continue
        patch_path="$OVERLAY/patches/webui/$patch"
        if [ ! -f "$patch_path" ]; then
            fail "webui series references missing patch: $patch"
            SCRATCH_RESULT=1
            continue
        fi
        # Check + apply each patch in sequence so the next patch sees the
        # post-prior-patches state — same as the Dockerfile does.
        if ! (cd "$WEBUI" && git apply --check "$patch_path") 2>/dev/null; then
            fail "webui patch fails --check (after prior patches stacked): $patch"
            (cd "$WEBUI" && git apply --check "$patch_path" 2>&1 | sed 's/^/    /') >&2 || true
            SCRATCH_RESULT=1
            break  # can't continue applying if this one didn't check
        fi
        (cd "$WEBUI" && git apply "$patch_path") || {
            fail "webui patch passed --check but apply failed: $patch"
            SCRATCH_RESULT=1
            break
        }
    done < "$webui_series"
    # Restore submodule to pristine state regardless of result.
    (cd "$WEBUI" && git reset --hard --quiet 2>/dev/null) && \
        (cd "$WEBUI" && git clean -fdx --quiet 2>/dev/null)
fi

# ── 3. agent patch series must apply --check SEQUENTIALLY against current ──
# Same sequential apply pattern as section 2 — see comment above for rationale.
agent_series="$OVERLAY/patches/agent/series"
if [ -f "$agent_series" ]; then
    note "checking agent patch series against $AGENT ($(cd "$AGENT" && git describe --tags --always 2>/dev/null || echo unknown))"
    (cd "$AGENT" && git stash --include-untracked --quiet 2>/dev/null || true)
    while IFS= read -r patch; do
        patch="${patch%%#*}"
        patch="$(printf '%s' "$patch" | tr -d '\r' | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')"
        [ -z "$patch" ] && continue
        patch_path="$OVERLAY/patches/agent/$patch"
        if [ ! -f "$patch_path" ]; then
            fail "agent series references missing patch: $patch"
            continue
        fi
        if ! (cd "$AGENT" && git apply --check "$patch_path") 2>/dev/null; then
            fail "agent patch fails --check (after prior patches stacked): $patch"
            (cd "$AGENT" && git apply --check "$patch_path" 2>&1 | sed 's/^/    /') >&2 || true
            break
        fi
        (cd "$AGENT" && git apply "$patch_path") || {
            fail "agent patch passed --check but apply failed: $patch"
            break
        }
    done < "$agent_series"
    (cd "$AGENT" && git reset --hard --quiet 2>/dev/null) && \
        (cd "$AGENT" && git clean -fdx --quiet 2>/dev/null)
fi

if [ "$failed" -eq 0 ]; then
    note "OK — overlay basis clean against current submodule pointers"
    exit 0
fi

cat >&2 <<'BANNER'
[check-overlay-basis] one or more overlay/submodule basis mismatches
[check-overlay-basis] detected. Likely causes:
[check-overlay-basis]   * Upstream churn since the last submodule bump
[check-overlay-basis]     renamed/removed a file the overlay depends on.
[check-overlay-basis]   * The submodule pointer was bumped without the
[check-overlay-basis]     matching overlay refresh.
[check-overlay-basis] Resolution:
[check-overlay-basis]   * Revert the submodule pointer to the last clean tag
[check-overlay-basis]     AND open an issue to refresh anchors/manifest, OR
[check-overlay-basis]   * Refresh the failing anchor/manifest entry first,
[check-overlay-basis]     then re-bump the submodule.
BANNER
exit 1
