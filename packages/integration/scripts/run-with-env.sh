#!/bin/bash
# run-with-env.sh — source /data/config/hermes.env, then exec the wrapped command.
#
# Why: supervisord freezes its environment at startup, so `supervisorctl restart`
# alone cannot pick up keys the user adds via the onboarding wizard. Wrapping the
# program command lets each restart re-read the latest hermes.env on disk, so the
# wizard's restart path takes effect in seconds without a container restart.
#
# Source is best-effort: a malformed hermes.env must not block the wrapped
# process from starting — a missing key surfaces downstream as the existing
# "No LLM provider configured" error, not as a supervisord crash loop.
if [ -f /data/config/hermes.env ]; then
  set -a
  # shellcheck disable=SC1091
  source /data/config/hermes.env || true
  set +a
fi
exec "$@"
