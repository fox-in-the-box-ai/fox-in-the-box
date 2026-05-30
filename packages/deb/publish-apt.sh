#!/usr/bin/env bash
# publish-apt.sh — Publish Fox in the Box .deb packages to apt.foxinthebox.ai
#
# Required env vars:
#   GPG_PRIVATE_KEY   Armored GPG private key
#   GPG_KEY_ID        Key fingerprint or ID
#   R2_ACCOUNT_ID     Cloudflare account ID
#   R2_ACCESS_KEY     R2 access key (read+write on foxinthebox-apt bucket)
#   R2_SECRET_KEY     R2 secret key
#
# Optional:
#   DRY_RUN=1         Print commands without executing
set -euo pipefail

DRY_RUN="${DRY_RUN:-0}"
BUCKET="foxinthebox-apt"
ENDPOINT="https://${R2_ACCOUNT_ID}.r2.cloudflarestorage.com"

_log() { echo "[publish-apt] $*"; }
_die() { echo "[publish-apt] ERROR: $*" >&2; exit 1; }

[ -n "${GPG_PRIVATE_KEY:-}" ] || _die "GPG_PRIVATE_KEY not set"
[ -n "${GPG_KEY_ID:-}" ]      || _die "GPG_KEY_ID not set"
[ -n "${R2_ACCOUNT_ID:-}" ]   || _die "R2_ACCOUNT_ID not set"
[ -n "${R2_ACCESS_KEY:-}" ]   || _die "R2_ACCESS_KEY not set"
[ -n "${R2_SECRET_KEY:-}" ]   || _die "R2_SECRET_KEY not set"

# ── 1. Install tools ──────────────────────────────────────────────────────────
_log "Installing tools..."
sudo apt-get install -y -q reprepro gpg
if ! command -v rclone &>/dev/null; then
    curl -fsSL https://rclone.org/install.sh | sudo bash
fi

# ── 2. Import GPG key ─────────────────────────────────────────────────────────
_log "Importing GPG key..."
echo "$GPG_PRIVATE_KEY" | gpg --batch --import

# ── 3. Configure rclone for R2 ───────────────────────────────────────────────
mkdir -p ~/.config/rclone
cat > ~/.config/rclone/rclone.conf << EOF
[r2]
type = s3
provider = Cloudflare
access_key_id = ${R2_ACCESS_KEY}
secret_access_key = ${R2_SECRET_KEY}
endpoint = ${ENDPOINT}
EOF

# ── 4. Pull current apt repo state ───────────────────────────────────────────
_log "Pulling current repo state from R2..."
mkdir -p ./apt-repo
if [ "$DRY_RUN" != "1" ]; then
    rclone sync "r2:$BUCKET" ./apt-repo --quiet
else
    _log "(DRY_RUN) would sync r2:$BUCKET -> ./apt-repo"
fi

# ── 5. Bootstrap reprepro config on first run ────────────────────────────────
mkdir -p ./apt-repo/conf
if [ ! -f ./apt-repo/conf/distributions ]; then
    _log "Bootstrapping reprepro distributions config..."
    cat > ./apt-repo/conf/distributions << EOF2
Origin: Fox in the Box
Label: Fox in the Box
Codename: stable
Architectures: amd64 arm64
Components: main
SignWith: ${GPG_KEY_ID}
EOF2
fi

# ── 6. Add .deb files ─────────────────────────────────────────────────────────
_log "Adding .deb packages..."
shopt -s nullglob
debs=(dist/*.deb)
[ ${#debs[@]} -gt 0 ] || _die "No .deb files found in dist/"
for deb in "${debs[@]}"; do
    arch=$(dpkg --field "$deb" Architecture)
    _log "  includedeb stable $deb (arch=$arch)"
    if [ "$DRY_RUN" != "1" ]; then
        reprepro -b ./apt-repo includedeb stable "$deb"
    else
        _log "  (DRY_RUN) would includedeb stable $deb"
    fi
done

# ── 7. Sync back to R2 ────────────────────────────────────────────────────────
_log "Pushing updated repo to R2..."
if [ "$DRY_RUN" != "1" ]; then
    rclone sync ./apt-repo "r2:$BUCKET" --quiet
    _log "Published successfully to apt.foxinthebox.ai"
else
    _log "(DRY_RUN) would sync ./apt-repo -> r2:$BUCKET"
    _log "(DRY_RUN) complete — no changes made"
fi
