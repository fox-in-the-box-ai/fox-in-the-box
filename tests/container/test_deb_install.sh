#!/usr/bin/env bash
# test_deb_install.sh — Smoke test: install .deb in ubuntu:22.04 + ubuntu:24.04,
# verify package integrity.
#
# Scope: verifies dpkg install succeeds, dependencies resolve, and installed
# files are present. Does NOT verify service start — the test container has no
# systemd, so foxinthebox.service cannot run. Full service testing requires a
# VM or bare-metal machine.
#
# Two legs since the mem0 default-on release (design §e/§g.6):
#   ubuntu:22.04 — python3.11 resolves, so postinst always takes the
#                  FITB_PIP_CONSTRAINTS (constrained) pip path.
#   ubuntu:24.04 — python3 is 3.12, so postinst takes the UNCONSTRAINED pip
#                  path; its transitive resolution (protobuf inside mem0ai's
#                  <7.0.0,>=5.29.6 range, etc.) is validated here and nowhere
#                  else. Adds pip check + a protobuf import/version probe.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

echo "[test-deb] Building .deb..."
bash "$REPO_ROOT/packages/deb/build.sh" amd64

DEB="$(ls "$REPO_ROOT/dist/foxinthebox_"*"_amd64.deb" 2>/dev/null | head -1)"
[ -f "$DEB" ] || { echo "[test-deb] ERROR: no .deb found in dist/"; exit 1; }
echo "[test-deb] Built: $DEB"

# Shared in-container assertions (both legs). Kept in one string so the two
# legs cannot drift apart.
ASSERTIONS='
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

        echo "--- Verify embedding model + embed-server wiring (mem0 local embedder) ---"
        [ -f /opt/foxinthebox/embed-model.lock ] || { echo "FAIL: embed-model.lock missing from payload"; exit 1; }
        . /opt/foxinthebox/embed-model.lock
        [ -n "${EMBED_MODEL_FILENAME:-}" ] || { echo "FAIL: embed-model.lock has no EMBED_MODEL_FILENAME"; exit 1; }

        CONF=/etc/foxinthebox/supervisord.conf
        [ -f "$CONF" ] || { echo "FAIL: generated supervisord.conf missing"; exit 1; }
        grep -q "^\[program:embed-server\]" "$CONF" || { echo "FAIL: [program:embed-server] missing from generated supervisord.conf"; exit 1; }
        sed -n "/^\[program:hermes-gateway\]/,/^\[/p" "$CONF" | grep -q "MEM0_TELEMETRY" || \
            { echo "FAIL: MEM0_TELEMETRY missing from the hermes-gateway environment in generated supervisord.conf"; exit 1; }

        EMBED_BLOCK=$(sed -n "/^\[program:embed-server\]/,/^\[/p" "$CONF")
        MODEL=/opt/foxinthebox/models/$EMBED_MODEL_FILENAME
        if [ -f "$MODEL" ]; then
            echo "$EMBED_MODEL_SHA256  $MODEL" | sha256sum -c - || { echo "FAIL: embedding model sha256 mismatch vs embed-model.lock"; exit 1; }
            echo "$EMBED_BLOCK" | grep -q "^autostart=true" || { echo "FAIL: model present + verified but embed-server autostart is not true"; exit 1; }
            echo "PASS: embedding model present, hash-verified, embed-server autostart=true"
        else
            # postinst download warn-and-continue path (design §1.2): the unit
            # must stay stopped (autostart=false), never a FATAL retry loop.
            echo "WARN: embedding model not downloaded — asserting the autostart=false path"
            echo "$EMBED_BLOCK" | grep -q "^autostart=false" || { echo "FAIL: model absent but embed-server autostart is not false"; exit 1; }
            echo "PASS: model absent, embed-server correctly left autostart=false"
        fi

        echo "PASS: package installed, files present, user created"
'

echo "[test-deb] Installing in ubuntu:22.04 container (constrained pip path)..."
docker run --rm \
    -v "$REPO_ROOT/dist:/debs:ro" \
    ubuntu:22.04 bash -c "$ASSERTIONS"

echo "[test-deb] Installing in ubuntu:24.04 container (unconstrained pip path)..."
docker run --rm \
    -v "$REPO_ROOT/dist:/debs:ro" \
    ubuntu:24.04 bash -c "$ASSERTIONS"'
        echo "--- Unconstrained-path venv sanity (pip check + protobuf probe) ---"
        /opt/foxinthebox/venv/bin/pip check || { echo "FAIL: pip check reported broken requirements on the unconstrained path"; exit 1; }
        /opt/foxinthebox/venv/bin/python - <<PYEOF
import sys
import google.protobuf as protobuf

major = int(protobuf.__version__.split(".")[0])
# mem0ai pins protobuf <7.0.0,>=5.29.6 — the unconstrained resolution must
# land inside that range (the constrained path pins exactly; this leg is the
# only gate on the free resolution).
if major not in (5, 6):
    print(f"FAIL: protobuf {protobuf.__version__} outside mem0ai-compatible range (>=5.29.6,<7)", file=sys.stderr)
    sys.exit(1)
print(f"PASS: protobuf {protobuf.__version__} imports and is in range")
PYEOF
'

echo "[test-deb] PASS"
