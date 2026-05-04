#!/usr/bin/env bash
# /app/scripts/migrate.sh — data volume migration helper
# Called by entrypoint.sh when /data/version.txt differs from /app/version.txt
# Arguments:
#   $1  — current version (from /data/version.txt, e.g. "0.0.0")
#   $2  — latest version  (from /app/version.txt,  e.g. "0.1.0")
set -euo pipefail

CURRENT="$1"
LATEST="$2"

HERMES_YAML="/data/config/hermes.yaml"

# ── Patch: add skills.external_dirs if missing ────────────────────────────────
# Needed for any install where hermes.yaml was seeded before the skills block
# was added to the defaults (all v0.1.0 installs).
if [ -f "$HERMES_YAML" ] && ! grep -q "^skills:" "$HERMES_YAML"; then
    echo "[migrate] Adding skills.external_dirs to $HERMES_YAML ..."
    cat >> "$HERMES_YAML" << 'EOF'

# ── Skills ────────────────────────────────────────────────────────────────────
skills:
  external_dirs:
    - /data/apps/hermes-agent/skills
EOF
    echo "[migrate] skills block added."
fi

echo "[migrate] Migration $CURRENT -> $LATEST complete."
exit 0
