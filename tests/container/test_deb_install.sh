#!/usr/bin/env bash
# test_deb_install.sh — Smoke test: install .deb in ubuntu:22.04, verify package integrity
#
# Scope: verifies dpkg install succeeds, dependencies resolve, and installed
# files are present. Does NOT verify service start — the test container has no
# systemd, so foxinthebox.service cannot run. Full service testing requires a
# VM or bare-metal machine.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

echo "[test-deb] Building .deb..."
bash "$REPO_ROOT/packages/deb/build.sh" amd64

DEB="$(ls "$REPO_ROOT/dist/foxinthebox_"*"_amd64.deb" 2>/dev/null | head -1)"
[ -f "$DEB" ] || { echo "[test-deb] ERROR: no .deb found in dist/"; exit 1; }
echo "[test-deb] Built: $DEB"

echo "[test-deb] Installing in ubuntu:22.04 container..."
docker run --rm \
    -v "$REPO_ROOT/dist:/debs:ro" \
    ubuntu:22.04 bash -c '
        set -euo pipefail
        export DEBIAN_FRONTEND=noninteractive
        apt-get update -q
        apt-get install -y -q /debs/foxinthebox_*_amd64.deb

        echo "--- Verify installed files ---"
        [ -f /opt/foxinthebox/install-core.sh ] || { echo "FAIL: install-core.sh missing"; exit 1; }
        [ -f /opt/foxinthebox/version.txt ]     || { echo "FAIL: version.txt missing"; exit 1; }
        [ -d /opt/foxinthebox/fox-overlay ]      || { echo "FAIL: fox-overlay missing"; exit 1; }
        [ -f /opt/foxinthebox/scripts/preflight.sh ] || { echo "FAIL: preflight.sh missing"; exit 1; }
        [ -f /lib/systemd/system/foxinthebox.service ] || { echo "FAIL: systemd unit missing"; exit 1; }

        echo "--- Verify foxinthebox user ---"
        id foxinthebox || { echo "FAIL: foxinthebox user not created"; exit 1; }

        echo "--- Verify supervisor available ---"
        [ -x /opt/foxinthebox/venv/bin/supervisord ] || { echo "FAIL: supervisord not found in venv"; exit 1; }

        echo "PASS: package installed, files present, user created"
    '

echo "[test-deb] PASS"
