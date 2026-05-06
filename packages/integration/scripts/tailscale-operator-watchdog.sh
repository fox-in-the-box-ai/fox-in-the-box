#!/usr/bin/env bash
# Re-assert tailscaled's OperatorUser=foxinthebox preference every 30s.
#
# tailscaled drops the OperatorUser pref on the NeedsLogin transition that
# follows a tailnet key expiry. Once dropped, the foxinthebox-owned webui
# can no longer drive `tailscale up` — checkprefs returns "Access denied"
# and the user's only recovery is `docker exec ... tailscale set --operator`
# from a host shell. FITB#127.
#
# This watchdog runs as root (supervisord's UID) so it has the authority to
# (re-)set OperatorUser even when tailscaled cleared it. The grant is a
# no-op when already set, so the constant polling has no observable effect
# on a healthy tailnet — only on the recovery path.
#
# 30s cadence picked over 60s in v0.5.2 architecture decisions
# (project_v0_5_2_decisions.md): faster reaction matters more than the
# trivial CPU cost.
set -u

while true; do
    # Best-effort: a transient daemon-not-ready or socket EAGAIN should not
    # crash the watchdog. supervisord's autorestart would respawn us, but
    # the resulting log noise is unhelpful.
    tailscale set --operator=foxinthebox >/dev/null 2>&1 || true
    sleep 30
done
