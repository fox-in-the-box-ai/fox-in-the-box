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
# 3. ORPHAN-PATCH DETECTION (v0.7.21): every .patch file in patches/webui/
#    and patches/agent/ MUST be listed in its series file. Patches sitting
#    in the directory but missing from series are silently NOT applied at
#    Docker build time — exactly the v0.7.13 #331 failure mode where
#    003-server-py-onboarding-redirect.patch existed for 2 releases but
#    wasn't in series, so the onboarding redirect shipped broken.
#
# Runs as a CI gate BEFORE the Docker build. Failure means: either
# (a) the submodule pin needs to be rolled back to the previous tag
# the overlay tracked, or (b) the manifest/patches need refresh for
# the new upstream tag.
#
# Made real in Phase 8 follow-up #246 (was an empty `exit 0` stub
# from Phase 1).
#
# v0.7.21 changes:
#   - REFUSE-IF-DIRTY instead of stash+restore. The old stash pattern
#     created a stash on each run + never popped it + then reset --hard'd
#     the submodule. On CI runners (always fresh) this was a no-op; for
#     local dev runs it silently destroyed in-progress submodule work.
#     Now we check `git status --porcelain` first and bail with a clear
#     error if the submodule has uncommitted changes — let the dev
#     resolve their state explicitly.
#   - Added orphan-patch detection per the v0.7.15 audit recommendation.
#
# Exit codes:
#   0 = overlay basis is clean against current submodule pointers
#   1 = at least one mismatch — diagnostics printed to stderr; CI fails
#   2 = preflight failure (submodule in dirty state) — fix before re-run

set -eu

REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
OVERLAY="$REPO_ROOT/packages/fox-overlay"
WEBUI="$REPO_ROOT/forks/hermes-webui"
AGENT="$REPO_ROOT/forks/hermes-agent"

failed=0

note() { printf '[check-overlay-basis] %s\n' "$*"; }
fail() { printf '[check-overlay-basis] FAIL: %s\n' "$*" >&2; failed=1; }

# ── 0. Preflight: refuse if either submodule has uncommitted state ─────────
# v0.7.21: was a stash+reset pattern that silently destroyed dev WIP.
# Now: explicit error + exit 2 so the dev can fix their state intentionally.
check_submodule_clean() {
    local sm_name="$1" sm_path="$2"
    if [ ! -d "$sm_path/.git" ] && [ ! -f "$sm_path/.git" ]; then
        fail "submodule not initialized: $sm_name ($sm_path). Run \`git submodule update --init --recursive\` first."
        return 1
    fi
    local status
    status="$(cd "$sm_path" && git status --porcelain 2>/dev/null || true)"
    if [ -n "$status" ]; then
        printf '[check-overlay-basis] FAIL: submodule has uncommitted changes: %s\n' "$sm_name" >&2
        printf '[check-overlay-basis]       location: %s\n' "$sm_path" >&2
        printf '[check-overlay-basis]       status (first 10 lines):\n' >&2
        printf '%s\n' "$status" | head -10 | sed 's/^/[check-overlay-basis]         /' >&2
        printf '[check-overlay-basis] This script applies patches IN PLACE to verify the basis is clean.\n' >&2
        printf '[check-overlay-basis] Pre-v0.7.21 it auto-stashed your changes (and never popped them, losing the stash).\n' >&2
        printf '[check-overlay-basis] Fix your submodule state explicitly: commit, stash, or reset, then re-run.\n' >&2
        failed=1
        return 1
    fi
    return 0
}

check_submodule_clean "hermes-webui" "$WEBUI" || true
check_submodule_clean "hermes-agent" "$AGENT" || true
if [ "$failed" -ne 0 ]; then
    exit 2
fi

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

# ── Helper: read a series file into a normalized newline-list of patch names.
# Strips comments + blank lines. Used by both the apply-check (sec 2/3) and
# the orphan-patch detection (sec 4).
read_series() {
    local series_file="$1"
    [ -f "$series_file" ] || return 0
    while IFS= read -r line; do
        line="${line%%#*}"
        line="$(printf '%s' "$line" | tr -d '\r' | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')"
        [ -z "$line" ] && continue
        printf '%s\n' "$line"
    done < "$series_file"
}

# ── 2. webui patch series must apply --check SEQUENTIALLY against current ──
# v0.7.15 fix: apply each patch in series order so the next patch sees the
# post-prior-patches state (mirrors the Dockerfile). v0.7.21: dropped the
# stash dance — section 0 preflight guarantees the submodule starts clean,
# and we restore via reset --hard at the end regardless of outcome (safe
# because we proved the working tree was clean before touching it).
webui_series="$OVERLAY/patches/webui/series"
if [ -f "$webui_series" ]; then
    note "checking webui patch series against $WEBUI ($(cd "$WEBUI" && git describe --tags --always 2>/dev/null || echo unknown))"
    while IFS= read -r patch; do
        [ -z "$patch" ] && continue
        patch_path="$OVERLAY/patches/webui/$patch"
        if [ ! -f "$patch_path" ]; then
            fail "webui series references missing patch: $patch"
            continue
        fi
        if ! (cd "$WEBUI" && git apply --check "$patch_path") 2>/dev/null; then
            fail "webui patch fails --check (after prior patches stacked): $patch"
            (cd "$WEBUI" && git apply --check "$patch_path" 2>&1 | sed 's/^/    /') >&2 || true
            break  # can't continue applying if this one didn't check
        fi
        (cd "$WEBUI" && git apply "$patch_path") || {
            fail "webui patch passed --check but apply failed: $patch"
            break
        }
    done < <(read_series "$webui_series")
    # Restore submodule to pristine state. Safe because section 0 preflight
    # confirmed the working tree was clean before we touched it.
    (cd "$WEBUI" && git reset --hard --quiet 2>/dev/null) || true
fi

# ── 3. agent patch series must apply --check SEQUENTIALLY against current ──
agent_series="$OVERLAY/patches/agent/series"
if [ -f "$agent_series" ]; then
    note "checking agent patch series against $AGENT ($(cd "$AGENT" && git describe --tags --always 2>/dev/null || echo unknown))"
    while IFS= read -r patch; do
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
    done < <(read_series "$agent_series")
    (cd "$AGENT" && git reset --hard --quiet 2>/dev/null) || true
fi

# ── 4. Orphan-patch detection (v0.7.21) ────────────────────────────────────
# Every .patch file in patches/{webui,agent}/ MUST appear in its series file.
# Patches sitting in the directory but missing from series are silently NOT
# applied at Docker build time. This is the v0.7.13 #331 root cause:
# 003-server-py-onboarding-redirect.patch existed in patches/webui/ from
# v0.7.13 onwards but wasn't added to series until v0.7.15 — for 2 releases
# the onboarding-redirect fix shipped broken because the Dockerfile only
# iterates the series file, not the directory.
check_orphans() {
    local label="$1" series_file="$2" patches_dir="$3"
    [ -d "$patches_dir" ] || return 0
    # All .patch files actually on disk.
    local disk_patches
    disk_patches="$(cd "$patches_dir" && ls -1 *.patch 2>/dev/null | sort -u || true)"
    if [ -z "$disk_patches" ]; then return 0; fi
    # All patches listed in series (sorted unique for comm).
    local listed
    listed="$(read_series "$series_file" | sort -u)"
    # Find disk patches NOT in series — those are orphans.
    local orphans
    orphans="$(comm -23 <(printf '%s\n' "$disk_patches") <(printf '%s\n' "$listed"))"
    if [ -n "$orphans" ]; then
        while IFS= read -r orphan; do
            [ -z "$orphan" ] && continue
            fail "$label orphan patch (file exists but missing from series): $orphan"
            printf '[check-overlay-basis]       → either add %s to %s, or delete the patch file if intentionally inert\n' "$orphan" "$series_file" >&2
        done <<< "$orphans"
    fi
}

note "checking for orphan patches (file in dir but missing from series)"
check_orphans "webui" "$webui_series" "$OVERLAY/patches/webui"
check_orphans "agent" "$agent_series" "$OVERLAY/patches/agent"

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
[check-overlay-basis]   * A patch was added to packages/fox-overlay/patches/
[check-overlay-basis]     but never registered in the series file (v0.7.13
[check-overlay-basis]     #331 class of failure — silently inert at build).
[check-overlay-basis] Resolution:
[check-overlay-basis]   * Revert the submodule pointer to the last clean tag
[check-overlay-basis]     AND open an issue to refresh anchors/manifest, OR
[check-overlay-basis]   * Refresh the failing anchor/manifest entry first,
[check-overlay-basis]     then re-bump the submodule, OR
[check-overlay-basis]   * For orphan patches, add the file to series or delete it.
BANNER
exit 1
