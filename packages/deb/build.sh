#!/usr/bin/env bash
# build.sh — Build a Fox in the Box .deb package
# Usage: bash packages/deb/build.sh [amd64|arm64]
# Output: dist/foxinthebox_<version>_<arch>.deb
set -euo pipefail

ARCH="${1:-amd64}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VERSION="$(cat "$REPO_ROOT/VERSION")"
PKGNAME="foxinthebox_${VERSION}_${ARCH}"
BUILDDIR="$(mktemp -d)"

_log()  { echo "[deb-build] $*"; }
_die()  { echo "[deb-build] ERROR: $*" >&2; exit 1; }

trap 'rm -rf "$BUILDDIR"' EXIT

_log "Building $PKGNAME.deb from $REPO_ROOT..."

# ── Directory structure ───────────────────────────────────────────────────────
mkdir -p "$BUILDDIR/DEBIAN"
mkdir -p "$BUILDDIR/opt/foxinthebox/scripts"
mkdir -p "$BUILDDIR/opt/foxinthebox/defaults"
mkdir -p "$BUILDDIR/opt/foxinthebox/fox-overlay"
mkdir -p "$BUILDDIR/etc/foxinthebox"
mkdir -p "$BUILDDIR/lib/systemd/system"

APPDIR="$BUILDDIR/opt/foxinthebox"

# ── Bundle app files ──────────────────────────────────────────────────────────
# Runtime scripts first (run-with-env.sh, migrate.sh, tailscale-operator-watchdog.sh)
cp -r "$REPO_ROOT/packages/integration/scripts/." "$APPDIR/scripts/"
# install-core.sh and preflight.sh overlay on top
cp "$REPO_ROOT/packages/install-core/install-core.sh" "$APPDIR/install-core.sh"
cp "$REPO_ROOT/packages/install-core/preflight.sh"    "$APPDIR/scripts/preflight.sh"
chmod +x "$APPDIR/install-core.sh" "$APPDIR/scripts/"*.sh 2>/dev/null || true

# Default configs
cp -r "$REPO_ROOT/packages/integration/default-configs/." "$APPDIR/defaults/"

# Fox overlay (Python package + patches + static assets + versions.toml)
cp -r "$REPO_ROOT/packages/fox-overlay/." "$APPDIR/fox-overlay/"

# Version file
echo "$VERSION" > "$APPDIR/version.txt"

# ── DEBIAN control files ──────────────────────────────────────────────────────
SIZE_KB=$(du -sk "$BUILDDIR" | cut -f1)

sed \
    -e "s/__VERSION__/$VERSION/g" \
    -e "s/__ARCH__/$ARCH/g" \
    -e "s/__SIZE_KB__/$SIZE_KB/g" \
    "$REPO_ROOT/packages/deb/control/control" \
    > "$BUILDDIR/DEBIAN/control"

for f in postinst prerm postrm; do
    cp "$REPO_ROOT/packages/deb/control/$f" "$BUILDDIR/DEBIAN/$f"
    chmod 755 "$BUILDDIR/DEBIAN/$f"
done

# ── Systemd units ─────────────────────────────────────────────────────────────
for tmpl in "$REPO_ROOT/packages/deb/templates/"*.tmpl; do
    name="$(basename "$tmpl" .tmpl)"
    sed "s|__APP_DIR__|/opt/foxinthebox|g" "$tmpl" \
        > "$BUILDDIR/lib/systemd/system/$name"
done

# ── Build the .deb ────────────────────────────────────────────────────────────
mkdir -p "$REPO_ROOT/dist"
OUT="$REPO_ROOT/dist/$PKGNAME.deb"
dpkg-deb --build --root-owner-group "$BUILDDIR" "$OUT"

_log "Built: $OUT"
dpkg-deb --info "$OUT" | grep -E 'Package|Version|Architecture|Installed-Size'
