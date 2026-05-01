#!/usr/bin/env bash
# /workspace/.hermes/scripts/vps-patch-sync.sh
# Runs every Saturday 09:00 UTC
# Fetches patches from VPS, cherry-picks to FITB vps-wip branch

set -euo pipefail

FITB_REPO="/home/ubuntu/workspace/fox-in-the-box"
VPS_HOST="ubuntu@fitb-vps"
VPS_PATCHES_DIR="/patches"
LOCAL_PATCHES_TMP="/tmp/vps-patches-$$"
LOG_FILE="$HOME/.hermes/logs/vps-patch-sync.log"

mkdir -p "$HOME/.hermes/logs"

log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

error() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $*" | tee -a "$LOG_FILE"
    return 1
}

log "=== VPS Patch Sync Started ==="

# ── Step 1: Fetch patches from VPS via rsync ─────────────────────────────────
log "Fetching patches from $VPS_HOST:$VPS_PATCHES_DIR..."

mkdir -p "$LOCAL_PATCHES_TMP"

if rsync -avz --delete "$VPS_HOST:$VPS_PATCHES_DIR/" "$LOCAL_PATCHES_TMP/"; then
    log "✓ Patches fetched successfully"
else
    error "Failed to fetch patches from VPS" && exit 1
fi

# ── Step 2: Count patches ────────────────────────────────────────────────────
PATCH_COUNT=$(find "$LOCAL_PATCHES_TMP" -name "*.patch" | wc -l)
log "Found $PATCH_COUNT patches to apply"

if [ "$PATCH_COUNT" -eq 0 ]; then
    log "No patches to apply — exiting"
    rm -rf "$LOCAL_PATCHES_TMP"
    exit 0
fi

# ── Step 3: Setup FITB repo ──────────────────────────────────────────────────
cd "$FITB_REPO"

log "Fetching origin..."
git fetch origin || error "Failed to fetch origin" && exit 1

# ── Step 4: Create or update vps-wip branch ──────────────────────────────────
if git show-ref --quiet refs/heads/vps-wip; then
    log "vps-wip exists, resetting to origin/main..."
    git checkout vps-wip || error "Failed to checkout vps-wip" && exit 1
    git reset --hard origin/main || error "Failed to reset vps-wip" && exit 1
else
    log "Creating new vps-wip branch from origin/main..."
    git checkout -b vps-wip origin/main || error "Failed to create vps-wip" && exit 1
fi

# ── Step 5: Cherry-pick patches ──────────────────────────────────────────────
log "Applying patches..."
APPLIED=0
CONFLICTS=0
SKIPPED=0

for patch in "$LOCAL_PATCHES_TMP"/*.patch; do
    [ -f "$patch" ] || continue
    
    patch_name=$(basename "$patch")
    
    # Check if patch applies cleanly
    if git apply --check "$patch" 2>/dev/null; then
        if git am "$patch" 2>/dev/null; then
            log "✓ Applied: $patch_name"
            ((APPLIED++))
        else
            error "Failed to apply: $patch_name (git am failed)"
            ((CONFLICTS++))
            git am --abort 2>/dev/null || true
        fi
    else
        # Patch doesn't apply — log and skip
        log "⚠ Skipped (doesn't apply): $patch_name"
        ((SKIPPED++))
    fi
done

log "Patch results: $APPLIED applied, $CONFLICTS conflicts, $SKIPPED skipped"

# ── Step 6: Push vps-wip ─────────────────────────────────────────────────────
log "Pushing vps-wip to origin..."
if git push -u origin vps-wip; then
    log "✓ vps-wip pushed successfully"
else
    error "Failed to push vps-wip" && exit 1
fi

# ── Step 7: Cleanup ──────────────────────────────────────────────────────────
rm -rf "$LOCAL_PATCHES_TMP"

# ── Step 8: Send notification ────────────────────────────────────────────────
if [ "$CONFLICTS" -gt 0 ]; then
    log "Sending conflict notification..."
    NOTIFY_MSG="🚨 FITB: Patch sync completed with $CONFLICTS conflicts. Manual review needed."
    # Use Hermes send_message if available
    if command -v send_message &> /dev/null; then
        send_message "$NOTIFY_MSG"
    else
        log "$NOTIFY_MSG"
    fi
else
    log "Sending success notification..."
    NOTIFY_MSG="✅ FITB: Patch sync complete. vps-wip updated with $APPLIED commits."
    if command -v send_message &> /dev/null; then
        send_message "$NOTIFY_MSG"
    else
        log "$NOTIFY_MSG"
    fi
fi

log "=== VPS Patch Sync Complete ==="
