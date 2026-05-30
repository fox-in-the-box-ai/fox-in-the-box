#!/usr/bin/env bash
# test_deb_install.sh — Smoke test: build .deb, install in ubuntu:22.04, assert /health
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
    ubuntu:22.04 bash -c "
        set -euo pipefail
        export DEBIAN_FRONTEND=noninteractive
        apt-get update -q
        apt-get install -y -q /debs/foxinthebox_*_amd64.deb
        echo 'Install complete. Waiting for service...'
        sleep 20
        curl -sf http://localhost:8787/health && echo 'PASS: health check ok' || {
            echo 'FAIL: health check failed'
            exit 1
        }
    "

echo "[test-deb] PASS"
