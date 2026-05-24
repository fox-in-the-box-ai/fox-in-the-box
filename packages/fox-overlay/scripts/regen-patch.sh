#!/usr/bin/env bash
# regen-patch.sh — atomic patch regeneration for the Fox overlay system.
#
# Per #328: the "edit fork file then git diff > my.patch" workflow has
# bitten us repeatedly (commit e9bd4cd most recently). The fork ends up
# with uncommitted changes that the diff captures as stray context, and
# the patch applies locally but breaks against virgin upstream in CI.
#
# This script makes the workflow atomic:
#   1. Force-reset the fork to its pinned commit (verbatim upstream)
#   2. Apply all EARLIER patches in series so the new patch stacks correctly
#   3. Commit that state as a local baseline (the diff target)
#   4. Drop into $SHELL for the developer to make their edits
#   5. On exit, compute `git diff HEAD --` against the baseline commit and
#      write that to the named patch file
#   6. Force-reset the fork again so nothing leaks into the parent repo
#
# v0.7.21 rewrite: the previous version was broken-on-arrival. It tried
# two diff approaches (mktemp snapshot + diff -ruN, then a second pass
# with stash --keep-index + reset --hard + cp -r snapshot/*) — the
# second pass OVERWROTE the dev's edits with the snapshot before
# computing the diff, so the output was always empty. The "let me redo"
# comment shipped to main in that version was the smoking gun. This
# rewrite uses git as the diff engine (commit baseline + diff HEAD)
# instead of filesystem snapshots, which sidesteps the ordering issue
# entirely and produces patches in git's canonical unified format.
#
# Usage:
#   make regen-patch FORK=webui PATCH=003-server-py-onboarding-redirect.patch
#   make regen-patch FORK=agent PATCH=001-gateway-bootstrap-shim.patch
#
# Or directly:
#   packages/fox-overlay/scripts/regen-patch.sh webui 003-server-py-onboarding-redirect.patch
#
# The named patch file does NOT need to exist beforehand — if you're
# regenerating an existing patch, prior contents are overwritten. If you're
# creating a new patch, supply the new filename + add it to the series file
# afterward (the script reminds you).

set -euo pipefail

FORK="${1:-}"
PATCH_NAME="${2:-}"

if [ -z "$FORK" ] || [ -z "$PATCH_NAME" ]; then
    echo "Usage: $0 <agent|webui> <patch-name.patch>" >&2
    exit 1
fi

case "$FORK" in
    agent|webui) ;;
    *) echo "FORK must be 'agent' or 'webui', got '$FORK'" >&2; exit 1 ;;
esac

REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$REPO_ROOT"

FORK_DIR="forks/hermes-$FORK"
PATCH_DIR="packages/fox-overlay/patches/$FORK"
SERIES_FILE="$PATCH_DIR/series"
TARGET_PATCH="$PATCH_DIR/$PATCH_NAME"
TARGET_PATCH_ABS="$REPO_ROOT/$TARGET_PATCH"

if [ ! -d "$FORK_DIR" ]; then
    echo "Submodule $FORK_DIR not found. Run: git submodule update --init $FORK_DIR" >&2
    exit 1
fi

if [ ! -f "$SERIES_FILE" ]; then
    echo "Series file $SERIES_FILE not found" >&2
    exit 1
fi

# Verify the fork is at the pinned commit. If the submodule pointer drifts
# from the parent repo's recorded pin, the regen would target a different
# upstream tree — silently producing a patch that doesn't apply against
# what the Dockerfile actually checks out.
PINNED_COMMIT="$(git ls-tree HEAD "$FORK_DIR" | awk '{print $3}')"
CURRENT_COMMIT="$(git -C "$FORK_DIR" rev-parse HEAD)"
if [ "$PINNED_COMMIT" != "$CURRENT_COMMIT" ]; then
    echo "Submodule $FORK_DIR is at $CURRENT_COMMIT but parent repo pins it at $PINNED_COMMIT." >&2
    echo "Run: git submodule update --init $FORK_DIR" >&2
    exit 1
fi

# Refuse to run with a dirty submodule — same rationale as
# check-overlay-basis.sh's preflight. Pre-v0.7.21 this script would
# `git reset --hard` unconditionally and silently destroy your work.
DIRTY="$(git -C "$FORK_DIR" status --porcelain)"
if [ -n "$DIRTY" ]; then
    echo "Submodule $FORK_DIR has uncommitted changes:" >&2
    printf '%s\n' "$DIRTY" | head -10 | sed 's/^/  /' >&2
    echo "Commit or reset them explicitly before running regen-patch." >&2
    exit 2
fi

echo "[regen-patch] Fork at pinned commit ${PINNED_COMMIT:0:12} — clean."

# ── Apply all EARLIER patches in series ────────────────────────────────────
# Stops when it encounters the target patch name OR runs out of patches
# (the latter means we're authoring a brand-new patch at the end).
APPLIED=()
TARGET_FOUND=0
echo "[regen-patch] Stacking earlier patches in series..."
while IFS= read -r line; do
    case "$line" in ''|\#*) continue ;; esac
    if [ "$line" = "$PATCH_NAME" ]; then
        TARGET_FOUND=1
        break
    fi
    p="$PATCH_DIR/$line"
    if [ ! -f "$p" ]; then
        echo "  ! series references missing patch: $p — skipping" >&2
        continue
    fi
    echo "  applying $line..."
    if ! git -C "$FORK_DIR" apply "$REPO_ROOT/$p" 2>&1 | sed 's/^/      /'; then
        echo "  failed to apply $line — cannot stack $PATCH_NAME on top." >&2
        echo "  Resetting fork." >&2
        git -C "$FORK_DIR" reset --hard --quiet
        git -C "$FORK_DIR" clean -fdx --quiet
        exit 1
    fi
    APPLIED+=("$line")
done < "$SERIES_FILE"

if [ "$TARGET_FOUND" -eq 0 ]; then
    echo "[regen-patch] $PATCH_NAME is not in series yet — will author as new patch at end."
fi

# ── Commit baseline so we can diff against it cleanly ──────────────────────
# `git diff HEAD` against this commit captures exactly the dev's edits in
# canonical unified format — much cleaner than the mktemp-snapshot + diff -ruN
# pattern the previous version tried (which had two competing diff blocks
# fighting each other; see the v0.7.15 audit's "let me redo" finding).
#
# Local-only commit. The fork's reset --hard at the end discards it; nothing
# leaks into the submodule's history or the parent repo.
BASELINE_SHA="(no-baseline)"
if [ "${#APPLIED[@]}" -gt 0 ]; then
    git -C "$FORK_DIR" add -A
    git -C "$FORK_DIR" -c user.name="regen-patch" -c user.email="regen-patch@local" \
        commit --quiet --no-verify -m "regen-patch baseline: ${APPLIED[*]}"
    BASELINE_SHA="$(git -C "$FORK_DIR" rev-parse HEAD)"
fi

# ── Hand off to interactive shell ──────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════════════════════════════"
echo " regen-patch interactive session"
echo "════════════════════════════════════════════════════════════════════"
echo ""
echo " Fork:              $FORK_DIR"
echo " Pinned at:         ${PINNED_COMMIT:0:12}"
echo " Patches stacked:   ${APPLIED[*]:-(none)}"
echo " Baseline commit:   ${BASELINE_SHA:0:12}"
echo " Target patch:      $TARGET_PATCH"
echo ""
echo " Make your edits inside $FORK_DIR/, then exit this shell (Ctrl-D or"
echo " 'exit'). The diff vs the baseline commit will be written to the"
echo " target patch file and the fork reset to pristine."
echo ""
echo "════════════════════════════════════════════════════════════════════"
echo ""

(cd "$FORK_DIR" && "${SHELL:-bash}")

# ── Compute diff ───────────────────────────────────────────────────────────
echo ""
echo "[regen-patch] Computing diff against baseline..."
# Stage everything (handles new files too) so `git diff --cached HEAD` sees
# them. Then diff the staged tree against the baseline commit.
git -C "$FORK_DIR" add -A
DIFF_OUTPUT="$(git -C "$FORK_DIR" diff --cached HEAD 2>/dev/null || git -C "$FORK_DIR" diff HEAD 2>/dev/null || true)"

# Always reset the fork before exiting, regardless of whether we wrote a patch.
# Use a trap so even an error mid-write leaves the submodule pristine.
cleanup_fork() {
    git -C "$FORK_DIR" reset --hard --quiet "$PINNED_COMMIT" 2>/dev/null || true
    git -C "$FORK_DIR" clean -fdx --quiet 2>/dev/null || true
}
trap cleanup_fork EXIT

if [ -z "$DIFF_OUTPUT" ]; then
    echo "[regen-patch] No changes detected. Nothing written to $TARGET_PATCH."
    echo "[regen-patch] Fork reset to pristine state."
    exit 0
fi

# ── Write the patch file ───────────────────────────────────────────────────
# Patch format: a short header (subject + author) followed by the unified diff.
# Matches the format of the existing series patches (001/002/003) which were
# generated by `git diff` then hand-edited.
mkdir -p "$(dirname "$TARGET_PATCH_ABS")"
{
    printf 'From: Fox in the Box overlay <noreply@fox-in-the-box.local>\n'
    printf 'Subject: [PATCH] %s\n' "$(basename "$PATCH_NAME" .patch)"
    printf '\n'
    printf '(Edit this header to describe what the patch does and why.\n'
    printf 'Anchor context: this patch was generated against pinned commit %s\n' "${PINNED_COMMIT:0:12}"
    printf 'with %d earlier patches stacked: %s)\n' "${#APPLIED[@]}" "${APPLIED[*]:-(none)}"
    printf '\n'
    printf '%s\n' "$DIFF_OUTPUT"
} > "$TARGET_PATCH_ABS"

echo "[regen-patch] Wrote $TARGET_PATCH ($(wc -l < "$TARGET_PATCH_ABS") lines)"
echo "[regen-patch] Fork reset to pristine state."
echo ""
echo "Next steps:"
echo "  1. Edit the patch header (Subject + description) to explain the change."
if [ "$TARGET_FOUND" -eq 0 ]; then
    echo "  2. Add to series: echo '$PATCH_NAME' >> $SERIES_FILE"
    echo "  3. Verify: bash packages/fox-overlay/scripts/check-overlay-basis.sh"
    echo "  4. Commit: git add $TARGET_PATCH $SERIES_FILE"
else
    echo "  2. Verify: bash packages/fox-overlay/scripts/check-overlay-basis.sh"
    echo "  3. Commit: git add $TARGET_PATCH"
fi
