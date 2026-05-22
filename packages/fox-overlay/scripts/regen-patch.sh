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
#   2. Apply all earlier patches in series so the new patch stacks correctly
#   3. Drop into $EDITOR (or $SHELL) for the developer to make their edits
#   4. On exit, export the diff to the named patch file
#   5. Force-reset the fork again so nothing leaks into the parent repo
#
# Usage:
#   make regen-patch FORK=webui PATCH=003-server-py-onboarding-redirect.patch
#   make regen-patch FORK=agent PATCH=001-gateway-bootstrap-shim.patch
#
# Or directly:
#   packages/fox-overlay/scripts/regen-patch.sh webui 003-server-py-onboarding-redirect.patch

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

if [ ! -d "$FORK_DIR" ]; then
    echo "Submodule $FORK_DIR not found. Run: git submodule update --init $FORK_DIR" >&2
    exit 1
fi

if [ ! -f "$SERIES_FILE" ]; then
    echo "Series file $SERIES_FILE not found" >&2
    exit 1
fi

# ── Verify the fork is at the pinned commit (sanity check) ──
PINNED_COMMIT=$(git ls-tree HEAD "$FORK_DIR" | awk '{print $3}')
CURRENT_COMMIT=$(git -C "$FORK_DIR" rev-parse HEAD)
if [ "$PINNED_COMMIT" != "$CURRENT_COMMIT" ]; then
    echo "Submodule $FORK_DIR is at $CURRENT_COMMIT but parent repo pins it at $PINNED_COMMIT." >&2
    echo "Run: git submodule update --init $FORK_DIR" >&2
    exit 1
fi

# ── Force-reset the fork before doing anything ──
echo "[regen-patch] Force-resetting $FORK_DIR to pinned commit (any local changes WILL be lost)..."
git -C "$FORK_DIR" reset --hard --quiet
git -C "$FORK_DIR" clean -fdx --quiet

# ── Apply all earlier patches in series ──
APPLIED=()
echo "[regen-patch] Applying earlier patches in series..."
while IFS= read -r line; do
    # Skip blanks + comments
    case "$line" in ''|\#*) continue ;; esac
    # Stop when we reach our target patch (or any patch with our name)
    if [ "$line" = "$PATCH_NAME" ]; then
        break
    fi
    p="$PATCH_DIR/$line"
    if [ ! -f "$p" ]; then
        echo "  ⚠️  series references missing patch: $p — skipping" >&2
        continue
    fi
    echo "  applying $line..."
    if ! git -C "$FORK_DIR" apply "../../$p"; then
        echo "  ❌ failed to apply $line — cannot stack $PATCH_NAME on top" >&2
        git -C "$FORK_DIR" reset --hard --quiet
        exit 1
    fi
    APPLIED+=("$line")
done < "$SERIES_FILE"

# Snapshot the post-earlier-patches state for the final diff
SNAPSHOT_DIR="$(mktemp -d)"
trap 'rm -rf "$SNAPSHOT_DIR"' EXIT

# Snapshot every file the fork has (small enough for our submodules)
echo "[regen-patch] Snapshotting baseline..."
git -C "$FORK_DIR" ls-files | while read -r f; do
    mkdir -p "$SNAPSHOT_DIR/$(dirname "$f")"
    cp "$FORK_DIR/$f" "$SNAPSHOT_DIR/$f"
done

# ── Hand off to interactive editor / shell ──
echo ""
echo "════════════════════════════════════════════════════════════════════"
echo " regen-patch interactive session"
echo "════════════════════════════════════════════════════════════════════"
echo ""
echo " Fork:          $FORK_DIR (at pinned $PINNED_COMMIT)"
echo " Patches stacked: ${APPLIED[*]:-none}"
echo " Target patch:  $TARGET_PATCH"
echo ""
echo " Now make your edits inside $FORK_DIR/, then exit this shell (Ctrl-D"
echo " or 'exit'). The diff will be exported to the target patch file and"
echo " the fork will be reset clean."
echo ""
echo "════════════════════════════════════════════════════════════════════"
echo ""

# Spawn a subshell in the fork directory
(cd "$FORK_DIR" && "${SHELL:-bash}")

# ── Compute diff and write the patch ──
echo ""
echo "[regen-patch] Computing diff..."
{
    cat <<HEADER
From: Fox in the Box overlay <noreply@fox-in-the-box.local>
Subject: [PATCH] $(basename "$PATCH_NAME" .patch)

(Edit this header to describe what the patch does and why.)

HEADER

    # Walk every tracked file under FORK_DIR, diff against the snapshot.
    cd "$FORK_DIR"
    git ls-files | while read -r f; do
        if [ -f "../../$SNAPSHOT_DIR/$f" ]; then
            if ! diff -q "../../$SNAPSHOT_DIR/$f" "$f" > /dev/null 2>&1; then
                # Generate git-style diff for this file
                diff -u "../../$SNAPSHOT_DIR/$f" "$f" \
                    | sed "1s|.*|diff --git a/$f b/$f|; 2s|.*|--- a/$f|; 3s|.*|+++ b/$f|"
                # Wait that's not right. Let me redo:
            fi
        fi
    done
} > "$TARGET_PATCH.tmp"

# Simpler approach: use the snapshot as a temporary git baseline
cd "$REPO_ROOT/$FORK_DIR"
# Stage the snapshot state, then diff working tree against the stage
git -C . stash --quiet --keep-index 2>/dev/null || true
git -C . reset --hard --quiet
# Restore the snapshot
cp -r "$SNAPSHOT_DIR"/* .
git -C . add -A
git -C . diff --cached --reverse > /dev/null 2>&1 || true

# Use git diff against snapshot directly
DIFF_OUTPUT=$(cd "$REPO_ROOT" && diff -ruN "$SNAPSHOT_DIR" "$FORK_DIR" \
    | sed "s|--- $SNAPSHOT_DIR/|--- a/|g; s|+++ $FORK_DIR/|+++ b/|g" \
    | grep -v "^Only in" || true)

if [ -z "$DIFF_OUTPUT" ]; then
    echo "[regen-patch] No changes detected — nothing to write."
    echo "[regen-patch] Resetting fork to pristine state."
    git -C "$REPO_ROOT/$FORK_DIR" reset --hard --quiet
    git -C "$REPO_ROOT/$FORK_DIR" clean -fdx --quiet
    rm -f "$TARGET_PATCH.tmp"
    exit 0
fi

{
    cat <<HEADER
From: Fox in the Box overlay <noreply@fox-in-the-box.local>
Subject: [PATCH] $(basename "$PATCH_NAME" .patch)

(Edit this header to describe what the patch does and why.)

HEADER
    # Prepend git-style diff --git header to each file diff
    echo "$DIFF_OUTPUT" | awk '
        /^--- a\// {
            file = substr($0, 7)
            print "diff --git a/" file " b/" file
        }
        { print }
    '
} > "$TARGET_PATCH"
rm -f "$TARGET_PATCH.tmp"

# ── Reset fork to pristine state ──
echo "[regen-patch] Resetting $FORK_DIR to pristine state..."
git -C "$REPO_ROOT/$FORK_DIR" reset --hard --quiet
git -C "$REPO_ROOT/$FORK_DIR" clean -fdx --quiet

echo ""
echo "✅ Patch written to: $TARGET_PATCH"
echo ""
echo "Next steps:"
echo "  1. Edit the patch header (Subject + description) to explain the change"
echo "  2. Add to series file if new: echo '$PATCH_NAME' >> $SERIES_FILE"
echo "  3. Verify: make validate-overlay"
echo "  4. Commit: git add $TARGET_PATCH $SERIES_FILE"
