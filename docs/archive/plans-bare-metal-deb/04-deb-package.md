# 04 — .deb Package Structure

## Directory layout

```
packages/deb/
├── build.sh                  ← builds the .deb from current repo state
├── control/
│   ├── control               ← package metadata
│   ├── postinst              ← install + upgrade logic
│   ├── prerm                 ← stop service before removal
│   └── postrm                ← purge: remove /opt/foxinthebox
└── templates/
    ├── foxinthebox.service.tmpl
    ├── foxinthebox-updater.service.tmpl
    └── foxinthebox-updater.path.tmpl
```

## control file

```
Package: foxinthebox
Version: __VERSION__
Architecture: amd64              ← amd64 or arm64, set by build.sh
Maintainer: Fox in the Box <support@foxinthebox.ai>
Installed-Size: __SIZE_KB__
Depends: python3.11 | python3 (>= 3.11),
         python3-pip,
         python3-venv,
         nodejs (>= 18),
         git,
         curl,
         ca-certificates,
         libgomp1,
         libcurl4,
         iproute2,
         iptables,
         supervisor
Recommends: tailscale
Section: net
Priority: optional
Homepage: https://foxinthebox.ai
Description: Fox in the Box — privacy-first self-hosted AI assistant
 Fox in the Box bundles Hermes Agent, a customized web UI, Qdrant vector
 store, and a local LLM fallback. Runs entirely on your machine.
 .
 Supports Ubuntu 22.04 LTS, Ubuntu 24.04 LTS, Zorin OS 16, Zorin OS 17.
```

Notes:
- Tailscale is `Recommends` not `Depends` — Fox works without it (localhost-only mode)
- `supervisor` is the pip-installed supervisord; on Ubuntu it's also in apt as `supervisor`
- Python 3.11 fallback `| python3 (>= 3.11)` handles Ubuntu 22.04 (needs `python3.11` package) and 24.04 (ships 3.12, but 3.11 compat)

## postinst

```bash
#!/bin/bash
set -e
ACTION="$1"   # configure | upgrade | abort-upgrade | ...

# 1. Create system user (idempotent)
if ! id foxinthebox &>/dev/null; then
    adduser --system --group --home /opt/foxinthebox --shell /bin/bash foxinthebox
fi

# 2. Set ownership
chown -R foxinthebox:foxinthebox /opt/foxinthebox

# 3. Run install-core.sh (idempotent — handles fresh install and upgrade)
FITB_APP_DIR=/opt/foxinthebox \
FITB_CONTEXT=bare-metal \
bash /opt/foxinthebox/install-core.sh

# 4. Install + enable systemd units
systemctl daemon-reload
systemctl enable foxinthebox.service
systemctl enable foxinthebox-updater.path

# 5. On fresh install: start the service
if [ "$ACTION" = "configure" ] && [ -z "$2" ]; then
    systemctl start foxinthebox.service
    echo "Fox in the Box is running at http://localhost:8787"
fi

# 6. On upgrade: restart to pick up new version
if [ "$ACTION" = "configure" ] && [ -n "$2" ]; then
    systemctl restart foxinthebox.service
    echo "Fox in the Box upgraded to $(cat /opt/foxinthebox/version.txt)"
fi
```

## prerm

```bash
#!/bin/bash
set -e
case "$1" in
  remove|upgrade|deconfigure)
    systemctl stop foxinthebox.service    || true
    systemctl disable foxinthebox.service || true
    systemctl disable foxinthebox-updater.path || true
    ;;
esac
```

## postrm

```bash
#!/bin/bash
set -e
case "$1" in
  purge)
    # Remove app directory (NOT user data — ~/.foxinthebox stays)
    rm -rf /opt/foxinthebox
    # Remove systemd units
    rm -f /etc/systemd/system/foxinthebox*.service
    rm -f /etc/systemd/system/foxinthebox*.path
    systemctl daemon-reload
    # Remove system user
    deluser --system foxinthebox || true
    echo "Fox in the Box removed. Your data at ~/.foxinthebox was NOT deleted."
    echo "To also delete your data: rm -rf ~/.foxinthebox"
    ;;
esac
```

## build.sh

```bash
#!/usr/bin/env bash
# Usage: bash packages/deb/build.sh [amd64|arm64]
# Output: dist/foxinthebox_<version>_<arch>.deb
set -euo pipefail

ARCH="${1:-amd64}"
VERSION="$(cat VERSION)"
PKGNAME="foxinthebox_${VERSION}_${ARCH}"
BUILDDIR="$(mktemp -d)"
APPDIR="$BUILDDIR/opt/foxinthebox"

# 1. Create deb directory structure
mkdir -p "$BUILDDIR/DEBIAN"
mkdir -p "$APPDIR"
mkdir -p "$BUILDDIR/etc/foxinthebox"
mkdir -p "$BUILDDIR/lib/systemd/system"

# 2. Copy app files into deb tree
cp -r packages/install-core/install-core.sh "$APPDIR/"
cp -r packages/integration/default-configs/ "$APPDIR/defaults/"
cp -r packages/integration/scripts/ "$APPDIR/scripts/"
cp -r packages/fox-overlay "$APPDIR/fox-overlay"
cp VERSION "$APPDIR/version.txt"

# Note: hermes-agent and hermes-webui are NOT bundled in the .deb
# install-core.sh clones them at install time from pinned upstream tags
# This keeps the .deb small (~50MB vs ~500MB)

# 3. Copy DEBIAN control files
sed "s/__VERSION__/$VERSION/g; s/__ARCH__/$ARCH/g" \
    packages/deb/control/control > "$BUILDDIR/DEBIAN/control"
cp packages/deb/control/postinst "$BUILDDIR/DEBIAN/postinst"
cp packages/deb/control/prerm    "$BUILDDIR/DEBIAN/prerm"
cp packages/deb/control/postrm   "$BUILDDIR/DEBIAN/postrm"
chmod 755 "$BUILDDIR/DEBIAN/"post* "$BUILDDIR/DEBIAN/"pre*

# 4. Systemd units (path-substituted for bare-metal)
for tmpl in packages/deb/templates/*.tmpl; do
    name="$(basename "$tmpl" .tmpl)"
    sed "s|__APP_DIR__|/opt/foxinthebox|g" "$tmpl" \
        > "$BUILDDIR/lib/systemd/system/$name"
done

# 5. Calculate installed size
SIZE_KB=$(du -sk "$BUILDDIR" | cut -f1)
sed -i "s/__SIZE_KB__/$SIZE_KB/" "$BUILDDIR/DEBIAN/control"

# 6. Build the .deb
mkdir -p dist
dpkg-deb --build --root-owner-group "$BUILDDIR" "dist/$PKGNAME.deb"
echo "Built: dist/$PKGNAME.deb"
rm -rf "$BUILDDIR"
```

## Size estimate

| Component | Size |
|-----------|------|
| fox-overlay (Python + patches + static) | ~5 MB |
| install-core.sh + scripts | ~100 KB |
| default-configs | ~50 KB |
| qdrant binary (downloaded at install time) | ~50 MB (not in .deb) |
| llama-server binary (downloaded at install time) | ~80 MB (not in .deb) |
| hermes-agent (cloned at install time) | ~30 MB (not in .deb) |
| hermes-webui (cloned at install time) | ~20 MB (not in .deb) |
| **.deb size** | **~6 MB** |

Binaries are downloaded at install time, not bundled. This is the right call — they are large, arch-specific, and change independently of Fox's version.
