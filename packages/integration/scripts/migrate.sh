#!/usr/bin/env bash
# /app/scripts/migrate.sh — data volume migration helper
# Called by entrypoint.sh when /data/version.txt differs from /app/version.txt
# Arguments:
#   $1  — current version (from /data/version.txt, e.g. "0.0.0")
#   $2  — latest version  (from /app/version.txt,  e.g. "0.1.0")
set -euo pipefail

CURRENT="$1"
LATEST="$2"

echo "[migrate] Migration $CURRENT -> $LATEST, nothing to do."
exit 0
