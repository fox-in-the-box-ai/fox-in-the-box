"""Hermes Web UI — Tailscale connection orchestration (issue #96).

Wraps the in-container `tailscale` CLI so the desktop app can drive the
auth flow without docker-exec. Three personas are supported:

  1. Silent  — BackendState is already Running. /status returns it; no
               action needed; UI hides auth prompts.
  2. Interactive — User clicks Connect. We spawn `tailscale up` in a
               background thread, scrape the auth URL from stdout, return
               it to the client which opens it in the system browser.
               Client polls /up/poll until BackendState becomes Running.
  3. Power-user — User supplies an auth key (and/or login server,
               advertise-routes, exit-node, etc.). We pass these verbatim
               to `tailscale up` and skip the URL extraction (auth-key
               path is non-interactive).

Status state machine (kept in `_up_state`):

    idle         — nothing in flight
    starting     — subprocess spawned, no URL captured yet
    awaiting-auth — auth URL captured, waiting for user to click through
    running      — BackendState observed Running (terminal success)
    failed       — subprocess exited non-zero or polling timed out
                   (terminal; client must call /up again to retry)

The subprocess is reaped by a daemon thread. The HTTP request that
triggers /up returns immediately with the URL — never blocks on the
user's browser interaction.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)


# Auth URLs Tailscale prints. Both forms appear depending on whether the
# tailnet uses Tailscale's control plane (login.tailscale.com) or a custom
# login-server (headscale, on-prem) — power users with --login-server get
# their own host's URL. The regex matches either.
_AUTH_URL_RE = re.compile(r"https?://[^\s]*[/](?:a|register|login)/[^\s]+")
_TS_AUTH_URL_RE = re.compile(r"https?://login\.tailscale\.com[^\s]+")

# How long we'll keep `tailscale up` alive waiting for the user to click
# through. Mirrors install.sh's 600s `--timeout=` flag.
_UP_TIMEOUT_S = 600.0
# How long we'll consider a /up/poll outcome valid before the next /up
# overwrites it. Long enough that a slow user can finish auth.
_TERMINAL_GRACE_S = 900.0


# ── Subprocess wrapper ─────────────────────────────────────────────────────


def _run_tailscale(args: list[str], timeout: float = 10.0) -> tuple[int, str, str]:
    """Run a `tailscale` subcommand. Returns (returncode, stdout, stderr).
    rc=127 indicates the binary isn't on PATH (running outside the FITB
    container during dev/tests)."""
    try:
        result = subprocess.run(
            ["tailscale", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout, result.stderr
    except FileNotFoundError:
        return 127, "", "tailscale binary not found"
    except subprocess.TimeoutExpired:
        return 124, "", f"tailscale {args[0] if args else ''} timed out"


# ── Status snapshot ────────────────────────────────────────────────────────


_POWER_USER_KEYS = (
    "tailscale_login_server",
    "tailscale_advertise_routes",
    "tailscale_advertise_tags",
    "tailscale_accept_routes",
    "tailscale_accept_dns",
    "tailscale_exit_node",
)

# QA fix: defense-in-depth validators for the power-user fields. Without
# these, anything posted to /api/settings flows straight into `tailscale up`
# argv as `--flag=value`. Even though subprocess.run uses shell=False (so
# no classic shell injection), an attacker who controls settings.json can:
#   - prefix a value with `-` to inject another flag (e.g. break advertise
#     into `... --auth-key=tskey-xxx`)
#   - use `--login-server` to redirect a user's auth flow to attacker-
#     controlled headscale
#   - smuggle newlines / control characters
# Validators reject malformed input at both /api/settings save time AND at
# argv build time (belt and suspenders).
_MAX_OPT_LEN = 512
_TS_HOSTNAME_RE = __import__("re").compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")
_TS_TAG_RE = __import__("re").compile(r"^tag:[a-z][a-z0-9-]*$")
_TS_ROUTE_RE = __import__("re").compile(
    r"^(?:\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}/\d{1,2}|[0-9a-fA-F:]+/\d{1,3})$"
)
# Hostname / IP charset for --exit-node. Drop `/` (was a copy-paste from
# the URL regex; exit-node values never contain `/`).
_TS_HOST_RE = __import__("re").compile(r"^[a-zA-Z0-9.\-_:]+$")
_TS_URL_RE = __import__("re").compile(r"^https?://[a-zA-Z0-9.\-_:/]+(?:/[a-zA-Z0-9.\-_:/?&=%~]*)?$")


def _safe_str_value(v: Any, max_len: int = _MAX_OPT_LEN) -> str | None:
    """Return v as a stripped string if it's safe to pass through to a
    `tailscale up --flag=value` argument: not too long, no control chars,
    no leading dash. Returns None if the value should be rejected."""
    if v is None:
        return ""
    if not isinstance(v, str):
        return None
    s = v.strip()
    if not s:
        return ""
    if len(s) > max_len:
        return None
    if s.startswith("-"):
        return None  # blocks flag-injection
    if any(ord(c) < 0x20 for c in s):
        return None  # newlines, NUL, etc.
    return s


def _validate_ts_opt(field: str, value: Any) -> tuple[bool, str]:
    """Return ``(ok, sanitized_or_error_msg)``. Used by both
    save_settings (settings.json gate) and _build_up_argv (argv gate)."""
    s = _safe_str_value(value)
    if s is None:
        return False, f"{field}: invalid characters or too long"
    if not s:
        return True, ""

    if field == "login_server":
        if not _TS_URL_RE.match(s):
            return False, "login_server must be an http(s) URL"
        return True, s
    if field == "advertise_routes":
        # comma-separated CIDRs
        for part in (p.strip() for p in s.split(",")):
            if not part:
                continue
            if not _TS_ROUTE_RE.match(part):
                return False, f"advertise_routes: '{part}' is not a CIDR"
        return True, s
    if field == "advertise_tags":
        for part in (p.strip() for p in s.split(",")):
            if not part:
                continue
            if not _TS_TAG_RE.match(part):
                return False, f"advertise_tags: '{part}' is not a tag:* string"
        return True, s
    if field == "exit_node":
        # IP, hostname, or magic-DNS name
        if not _TS_HOST_RE.match(s):
            return False, "exit_node: invalid characters"
        return True, s
    if field == "hostname":
        if not _TS_HOSTNAME_RE.match(s):
            return False, "hostname: must match RFC 1035 label form"
        return True, s
    return True, s


def validate_settings_dict(settings: dict) -> str | None:
    """Used by api/config.save_settings to reject malformed Tailscale
    power-user values BEFORE they hit settings.json. Returns an error
    message string, or None if the dict is clean."""
    field_map = {
        "tailscale_login_server": "login_server",
        "tailscale_advertise_routes": "advertise_routes",
        "tailscale_advertise_tags": "advertise_tags",
        "tailscale_exit_node": "exit_node",
    }
    for k, vfield in field_map.items():
        if k not in settings:
            continue
        ok, msg = _validate_ts_opt(vfield, settings[k])
        if not ok:
            return msg
    return None


def _load_persisted_opts() -> dict[str, Any]:
    """Read the seven persisted Tailscale flags. Returns the body shape
    `_build_up_argv()` expects:
      {hostname, login_server, advertise_routes, advertise_tags,
       accept_routes, accept_dns, exit_node}

    QA fix: previously we did NOT include hostname here, so a saved
    FOX_HOSTNAME (from #44 / Settings → Hostname) was dropped on every
    Reconnect — the user got a Tailscale-default name (often the
    container ID) instead of the friendly fox-<adjective> they picked.
    Hostname is read from /data/config/hermes.env via the existing #44
    helper, NOT from settings.json — that's where install.sh, the wizard
    modal, and the Settings tile all converge.
    """
    out = {
        "hostname": "",
        "login_server": "",
        "advertise_routes": "",
        "advertise_tags": "",
        "accept_routes": False,
        "accept_dns": True,
        "exit_node": "",
    }
    try:
        from api.config import load_settings
        s = load_settings()
        out["login_server"] = s.get("tailscale_login_server") or ""
        out["advertise_routes"] = s.get("tailscale_advertise_routes") or ""
        out["advertise_tags"] = s.get("tailscale_advertise_tags") or ""
        out["accept_routes"] = bool(s.get("tailscale_accept_routes", False))
        out["accept_dns"] = bool(s.get("tailscale_accept_dns", True))
        out["exit_node"] = s.get("tailscale_exit_node") or ""
    except Exception:
        pass
    try:
        from api.hostname import _read_configured_hostname
        out["hostname"] = _read_configured_hostname() or ""
    except Exception:
        pass
    return out


def get_status() -> dict[str, Any]:
    """Read `tailscale status --json` and project the bits the UI cares
    about. Returns a stable shape regardless of daemon state — the UI
    can switch on `backend_state` to decide what to render.

    BackendState values from Tailscale's controlclient package:
      NoState · NeedsLogin · NeedsMachineAuth · Stopped · Starting · Running
    """
    rc, out, err = _run_tailscale(["status", "--json"], timeout=5.0)
    if rc == 127:
        return {
            "available": False,
            "backend_state": "Unknown",
            "error": "tailscale CLI not found (running outside container?)",
        }
    if rc != 0 or not out:
        return {
            "available": True,
            "backend_state": "Unknown",
            "error": err.strip() or "tailscale status failed",
        }
    try:
        s = json.loads(out)
    except json.JSONDecodeError:
        return {
            "available": True,
            "backend_state": "Unknown",
            "error": "could not parse tailscale status JSON",
        }
    self_node = s.get("Self") or {}
    # DNSName comes back like "fox-clever.tailnet-xxxx.ts.net." — trim the
    # trailing dot for display, build an HTTPS URL the UI can show.
    dns = (self_node.get("DNSName") or "").rstrip(".")
    https_url = f"https://{dns}/" if dns else ""
    # FITB#122 #2: include the webui's view of Serve state so the panel
    # can render a "Configure HTTPS" affordance steadily — works whether
    # the user authed via Connect (up_state populated) or via the desktop
    # Tailscale app (up_state stays idle; user clicks the button manually).
    with _up_lock:
        serve_snap = (_up_state.get("serve_state", "idle"),
                      _up_state.get("serve_error", ""))

    # FITB#140: if tailscaled is Running but serve_state is still "idle"
    # (we've never attempted to configure Serve for this Running session),
    # trigger a one-shot auto-config. This covers the path where the user
    # authenticated AFTER the entrypoint's 15-min boot window expired AND
    # the webui's start_up didn't witness the Running transition (e.g.
    # the tailscale up subprocess exited before _attempt_configure_serve
    # was called, or the user authed externally via `docker exec`).
    # Idempotent: configure_serve / _attempt_configure_serve update
    # serve_state on completion, so subsequent get_status calls become
    # no-ops once serve_state is "ok" or "error".
    backend_state = s.get("BackendState") or "Unknown"
    if backend_state == "Running" and serve_snap[0] == "idle":
        try:
            _attempt_configure_serve()
            with _up_lock:
                serve_snap = (_up_state.get("serve_state", "idle"),
                              _up_state.get("serve_error", ""))
        except Exception:
            logger.debug("Auto-configure Serve from get_status failed", exc_info=True)

    return {
        "available": True,
        "backend_state": backend_state,
        "self": {
            "hostname": self_node.get("HostName") or "",
            "dns_name": dns,
            "online": bool(self_node.get("Online")),
            "tailscale_ips": self_node.get("TailscaleIPs") or [],
        },
        "magic_dns_suffix": s.get("MagicDNSSuffix") or "",
        "tailnet_url": https_url,
        "peers_count": len(s.get("Peer") or {}),
        "serve_state": serve_snap[0],
        "serve_error": serve_snap[1],
        # Persisted power-user flags (#96 phase 2). UI pre-populates the
        # advanced accordion from these and sends edits back via the
        # standard /api/settings POST.
        "config": _load_persisted_opts(),
    }


# ── Up / auth flow (background subprocess + state machine) ────────────────


_up_lock = threading.Lock()
_up_state: dict[str, Any] = {
    "state": "idle",
    "auth_url": "",
    # v0.7.12 (#146): sticky copy of the most recent non-empty auth_url
    # for the *current* attempt. Some clients (notably Safari with default
    # popup-blocker settings) re-render the auth tile from every poll
    # response — if the daemon thread momentarily returns "" (the gap
    # between attempt-start and the first scrape, the gap between auth
    # success and the Running transition, or a stale poll racing a fresh
    # logout/start_up), the link briefly disappears and the user loses
    # the click. By returning `last_auth_url` from get_up_progress when
    # `auth_url` itself is empty, the client sees a stable URL string
    # across the entire awaiting-auth window even if upstream JS doesn't
    # have its own client-side sticky cache.
    # Cleared on logout + on each fresh start_up (new attempt = new URL).
    "last_auth_url": "",
    "started_at": 0.0,
    "ended_at": 0.0,
    "error": "",
    "attempt_id": 0,
    # Serve auto-config state, populated after the daemon transitions to
    # Running. "ok" = HTTPS bound to localhost:8787; "error" = the CLI
    # rejected the call (most often "Serve is not enabled on your tailnet"
    # — needs HTTPS toggled in admin console). Surfacing it lets the UI
    # show a "Configure HTTPS" retry button instead of silently failing.
    # FITB#122 #2.
    "serve_state": "idle",
    "serve_error": "",
}
# QA fix: previously _up_proc and _up_log were module-level globals
# mutated outside _up_lock, with the daemon thread reading the *current*
# global rather than its own captured handle. That caused several races:
#   - logout() did not kill an in-flight subprocess
#   - start_up() observed a half-torn-down Popen as "in flight" and
#     silently swallowed the user's click
#   - a fresh _up_subprocess overwrote _up_proc while the previous thread
#     still had .wait() pending on the old reference
# All shared state now lives in this attempt object, captured-by-reference
# inside the daemon thread so each thread operates on its own handle.
_up_proc: subprocess.Popen | None = None
_up_log: list[str] = []


def _set_up_state(attempt_id: int | None = None, **fields) -> None:
    """Update the shared state dict. If attempt_id is provided, the update
    is silently ignored when it doesn't match the current attempt — this
    is how stale daemon threads (from cancelled/superseded attempts)
    avoid clobbering the active attempt's state.

    v0.7.12 (#146): also maintains `last_auth_url` as a sticky copy
    whenever `auth_url` is set to a non-empty value. Read-side (poll
    response) prefers `auth_url` then falls back to `last_auth_url` —
    keeps clients from seeing a transient blank during the awaiting-auth
    window even if a stale daemon scrape returns empty for one tick.
    """
    with _up_lock:
        if attempt_id is not None and attempt_id != _up_state.get("attempt_id"):
            return
        _up_state.update(fields)
        # Maintain the sticky last_auth_url alongside any auth_url update.
        new_auth_url = fields.get("auth_url")
        if new_auth_url:  # truthy non-empty string only
            _up_state["last_auth_url"] = new_auth_url


def _build_up_argv(opts: dict) -> list[str]:
    """Translate the request body into `tailscale up` flags. All keys are
    optional. Each value passes through `_validate_ts_opt` first — silently
    dropped if invalid (the request-time gate already rejected at /settings
    save; this is defense in depth for the case where settings.json was
    edited by hand or a future code path bypasses the gate).

    QA fix v0.4.7: in FITB the Tailscale daemon runs as root (for
    NET_ADMIN) and the webui runs as `foxinthebox` (per supervisord).
    entrypoint.sh runs `tailscale set --operator=foxinthebox` after
    boot to delegate user-mode CLI access — but Tailscale's `up`
    semantics require any non-default preference to be re-stated on
    every invocation, otherwise it errors with "changing settings via
    'tailscale up' requires mentioning all non-default flags".
    Including --operator=foxinthebox unconditionally keeps `up` working
    no matter what other prefs are sticky on the daemon. Without this,
    the entire desktop Tailscale flow (#96) silently 1-exits with
    'Access denied: login access denied' — bug surfaced in v0.4.7 QA.
    """
    argv = [
        "tailscale", "up",
        "--operator=foxinthebox",
        f"--timeout={int(_UP_TIMEOUT_S)}s",
    ]

    def _safe(field: str) -> str:
        ok, sanitized = _validate_ts_opt(field, opts.get(field, ""))
        return sanitized if ok else ""

    hostname = _safe("hostname")
    if hostname:
        argv.append(f"--hostname={hostname}")

    login_server = _safe("login_server")
    if login_server:
        argv.append(f"--login-server={login_server}")

    advertise_routes = _safe("advertise_routes")
    if advertise_routes:
        argv.append(f"--advertise-routes={advertise_routes}")

    advertise_tags = _safe("advertise_tags")
    if advertise_tags:
        argv.append(f"--advertise-tags={advertise_tags}")

    if opts.get("accept_routes") is True:
        argv.append("--accept-routes")
    # accept-dns defaults true on Tailscale's side; only emit when explicit
    if opts.get("accept_dns") is False:
        argv.append("--accept-dns=false")

    exit_node = _safe("exit_node")
    if exit_node:
        argv.append(f"--exit-node={exit_node}")

    return argv


def _scrape_auth_url(line: str) -> str:
    """Pull an auth URL from a `tailscale up` stdout line. Tries the
    Tailscale-cloud pattern first, then the generic /a/ /register/ /login/
    fallback (covers headscale and other custom login servers)."""
    m = _TS_AUTH_URL_RE.search(line)
    if m:
        return m.group(0)
    m = _AUTH_URL_RE.search(line)
    return m.group(0) if m else ""


def _up_subprocess(argv: list[str], env: dict | None, attempt_id: int) -> None:
    """Daemon thread: spawn `tailscale up`, scrape stdout for the auth URL,
    keep the process alive until it exits (user finished auth) or until
    the timeout.

    QA fixes vs. the v0.4.4 implementation:
      - All Popen / stdout / wait operations go through the LOCAL `proc`
        variable, never the module global. A second start_up() that
        spawns its own thread cannot make this thread `.wait()` on the
        new subprocess.
      - _set_up_state takes the attempt_id; if a newer attempt has
        started, our terminal mutations are silently dropped instead of
        clobbering it.
      - readline() is wrapped in a non-blocking poll using select() so
        the deadline check fires even when the subprocess goes silent
        (your known bug #1 — readline could block past the deadline).
      - All access to the shared _up_log / _up_proc globals is under
        _up_lock.
    """
    global _up_proc
    import select

    deadline = time.time() + _UP_TIMEOUT_S
    try:
        proc = subprocess.Popen(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
        )
    except FileNotFoundError:
        _set_up_state(attempt_id, state="failed", error="tailscale CLI not found", ended_at=time.time())
        return
    except OSError as exc:
        _set_up_state(attempt_id, state="failed", error=f"failed to spawn tailscale up: {exc}", ended_at=time.time())
        return

    # Publish the proc so logout() can SIGKILL it.
    with _up_lock:
        _up_proc = proc
        _up_log.clear()

    # QA fix v0.4.7-WaveG: scrape the auth URL from `tailscale status
    # --json`'s AuthURL field, NOT from the subprocess's stdout. Tailscale
    # block-buffers stdout when not attached to a TTY, so the URL line
    # never reaches Python until the subprocess exits — meanwhile the
    # daemon already knows the URL and exposes it in status. Polling
    # status every second also gives us a clean way to detect the
    # awaiting-auth → Running transition without depending on subprocess
    # behavior.
    auth_url = ""
    stdout = proc.stdout
    POLL_INTERVAL = 1.0

    while True:
        # Deadline check fires every loop iteration regardless of subprocess
        # output. We don't read from stdout at all — the subprocess just
        # needs to stay alive while the user authenticates in the browser.
        if time.time() > deadline:
            try:
                proc.kill()
            except Exception:
                pass
            _set_up_state(attempt_id, state="failed", error="auth timed out before completion", ended_at=time.time())
            break

        # Was the attempt superseded?
        with _up_lock:
            if _up_state.get("attempt_id") != attempt_id:
                try:
                    proc.kill()
                except Exception:
                    pass
                break

        # Subprocess exited? — drop out of the polling loop and let the
        # rc-handling block below decide running/failed.
        if proc.poll() is not None:
            break

        # Probe daemon status for the auth URL or terminal Running state.
        st = get_status()
        bs = st.get("backend_state", "")
        # The daemon exposes AuthURL on the raw status JSON. get_status()
        # doesn't surface it (UI doesn't need it), so peek directly.
        if not auth_url:
            try:
                rc, out, _err = _run_tailscale(["status", "--json"], timeout=3.0)
                if rc == 0 and out:
                    raw = json.loads(out)
                    candidate = raw.get("AuthURL") or ""
                    if candidate:
                        auth_url = candidate
                        _set_up_state(attempt_id, state="awaiting-auth", auth_url=candidate)
            except Exception:
                pass

        # Promote to running as soon as the daemon reports it — kills the
        # `tailscale up` subprocess promptly so the rc=0 / configure_serve
        # path runs.
        if bs == "Running":
            try:
                proc.kill()
            except Exception:
                pass
            break

        # Drain any subprocess stdout into the log without blocking — useful
        # for diagnostics on failed attempts. This is best-effort: select()
        # avoids blocking, the buffered-text issue means we may not see
        # everything in real time, but we still get partial diagnostic
        # context for the failure-tail in the next block.
        if stdout is not None:
            try:
                ready, _, _ = select.select([stdout], [], [], 0.0)
                if ready:
                    line = stdout.readline()
                    if line:
                        with _up_lock:
                            _up_log.append(line.rstrip())
            except (ValueError, OSError):
                pass

        time.sleep(POLL_INTERVAL)

    rc = proc.wait()

    # Clear the global handle ONLY if it's still pointing at our proc —
    # avoid stomping a newer attempt's handle.
    with _up_lock:
        if _up_proc is proc:
            _up_proc = None

    # rc=0 means tailscale up returned successfully — for interactive flows
    # this happens after the user clicks through; for auth-key flows it's
    # immediate. In both cases the daemon's BackendState should now be
    # Running, but we don't claim "running" here — the /up/poll handler
    # confirms by reading status. For auth-key paths we mark state directly.
    if rc == 0:
        st = get_status()
        if st.get("backend_state") == "Running":
            _set_up_state(attempt_id, state="running", ended_at=time.time())
            # QA fix v0.4.7-WaveF: gate the Serve auto-config on still-
            # being-the-active-attempt at call time. If logout() ran
            # between the rc=0 check and this point, attempt_id has
            # been bumped and we'd otherwise re-establish a Serve
            # binding against a tunnel the user just disconnected.
            with _up_lock:
                still_current = (_up_state.get("attempt_id") == attempt_id and
                                 _up_state.get("state") == "running")
            if still_current:
                _attempt_configure_serve(attempt_id)
        else:
            # Edge case: rc=0 but daemon not Running (e.g. login-only mode).
            # Treat as failed so UI re-prompts.
            _set_up_state(
                attempt_id,
                state="failed",
                error=f"tailscale up exited 0 but BackendState={st.get('backend_state')}",
                ended_at=time.time(),
            )
    else:
        with _up_lock:
            tail = "\n".join(_up_log[-10:]) or "(no output)"
        _set_up_state(attempt_id, state="failed", error=f"tailscale up exited {rc}: {tail}", ended_at=time.time())


def start_up(opts: dict) -> dict[str, Any]:
    """POST /api/tailscale/up — spawn `tailscale up` in the background.

    Idempotency: if a previous attempt is still in flight (state=starting
    or awaiting-auth) AND its subprocess is still alive AND not stale, we
    return the in-flight state instead of starting a new one.

    QA fix vs v0.4.4: all _up_proc / _up_log / _up_state mutations happen
    under _up_lock; the daemon thread is identified by an attempt_id so
    a stale thread cannot stomp the active attempt's state when it
    eventually exits. We also actively kill the previous proc before
    spawning a new one — required when state was already terminal
    (failed/running) and the user is retrying.
    """
    global _up_proc
    new_attempt_id: int
    with _up_lock:
        cur_state = _up_state["state"]
        if cur_state in ("starting", "awaiting-auth"):
            stale = (time.time() - _up_state["started_at"]) > _UP_TIMEOUT_S
            alive = _up_proc is not None and _up_proc.poll() is None
            if not stale and alive:
                return {
                    "ok": True,
                    "reused": True,
                    "auth_url": _up_state["auth_url"],
                    "state": cur_state,
                }
        # Bump attempt id so any stale thread's terminal _set_up_state
        # is silently dropped.
        new_attempt_id = int(_up_state.get("attempt_id", 0)) + 1
        # Kill any still-running proc from a previous attempt (e.g. user
        # is retrying after a stuck `awaiting-auth`). Best-effort.
        if _up_proc is not None:
            try:
                if _up_proc.poll() is None:
                    _up_proc.kill()
            except Exception:
                pass
            _up_proc = None
        _up_log.clear()
        _up_state.update({
            "state": "starting",
            "auth_url": "",
            # v0.7.12 (#146): fresh attempt → drop the previous attempt's
            # sticky URL so the new poll won't return a stale link.
            "last_auth_url": "",
            "started_at": time.time(),
            "ended_at": 0.0,
            "error": "",
            "attempt_id": new_attempt_id,
        })

    # Merge persisted power-user settings (#96 phase 2) with body opts —
    # body wins per-key, so the user can override at Connect time without
    # touching saved settings. None / empty body keys fall through to the
    # persisted value.
    merged = dict(_load_persisted_opts())
    for k, v in (opts or {}).items():
        if v is None:
            continue
        if isinstance(v, str) and not v.strip():
            continue
        merged[k] = v

    argv = _build_up_argv(merged)
    auth_key = (opts.get("auth_key") or "").strip()
    env = None
    if auth_key:
        import os
        env = dict(os.environ)
        env["TS_AUTHKEY"] = auth_key

    threading.Thread(
        target=_up_subprocess, args=(argv, env, new_attempt_id),
        name=f"tailscale-up-{new_attempt_id}", daemon=True,
    ).start()

    # Auth-key path is non-interactive; client doesn't need an auth_url.
    # Return immediately — the polling endpoint will tell the client when
    # BackendState is Running.
    return {
        "ok": True,
        "reused": False,
        "auth_key_used": bool(auth_key),
        "state": "starting",
    }


def get_up_progress() -> dict[str, Any]:
    """GET /api/tailscale/up/poll — current state of the in-flight (or
    most recent) up attempt. Client polls this every 2s while the modal /
    wizard step is open. Once state is `running` or `failed`, polling
    can stop.

    Bonus: when the daemon's BackendState is observed Running mid-poll,
    we promote the up-state to `running` even if the subprocess hasn't
    exited yet — this is a defense for the case where `tailscale up`
    keeps the subprocess alive past auth completion.
    """
    with _up_lock:
        snap = dict(_up_state)
    if snap["state"] in ("starting", "awaiting-auth"):
        st = get_status()
        if st.get("backend_state") == "Running":
            # QA fix v0.4.7-WaveF: pass the snapshot's attempt_id into
            # _set_up_state so a stale poll cannot stomp a concurrent
            # logout()'s reset-to-idle. Without the attempt_id, the
            # guard inside _set_up_state would fall through and write
            # state="running" over freshly-cleared idle, bringing back
            # the "Connected" badge after the user explicitly disconnected.
            _set_up_state(snap.get("attempt_id"), state="running", ended_at=time.time())
            # FITB#122 #2: also drive Serve auto-config from this path —
            # users who auth via the desktop Tailscale app (not webui's
            # Connect button) hit this branch first, so without it Serve
            # would never get configured for them.
            _attempt_configure_serve(snap.get("attempt_id"))
            with _up_lock:
                snap = dict(_up_state)
    # v0.7.12 (#146): prefer current auth_url, fall back to the sticky
    # `last_auth_url` from earlier in the same attempt. Lets the client
    # ride out transient empty windows (stale daemon scrape, post-auth
    # pre-Running gap) without losing the rendered link.
    #
    # Once state is terminal (running / failed / idle) the link's job is
    # over and continuing to serve it would confuse the user (running =
    # they already authed successfully; failed = the error is what they
    # need to see; idle = no auth flow in flight). Clear unconditionally
    # in those states regardless of whether the daemon thread happened to
    # leave a residual non-empty auth_url in _up_state.
    is_terminal = snap["state"] in ("running", "failed", "idle")
    if is_terminal:
        effective_auth_url = ""
    else:
        effective_auth_url = snap["auth_url"] or snap.get("last_auth_url", "")

    return {
        "state": snap["state"],
        "auth_url": effective_auth_url,
        # v0.7.12 (#146): explicit `cleared` flag tells the client
        # whether an empty `auth_url` means "still working, transient
        # blank — keep your rendered link" (cleared=False) or "attempt
        # is over, remove the link from the UI" (cleared=True). Clients
        # that don't yet read this field still benefit from the sticky
        # `auth_url` above.
        "cleared": is_terminal,
        "error": snap["error"],
        "started_at": snap["started_at"],
        "ended_at": snap["ended_at"],
        "serve_state": snap.get("serve_state", "idle"),
        "serve_error": snap.get("serve_error", ""),
    }


def logout() -> dict[str, Any]:
    """POST /api/tailscale/logout — disconnect from the tailnet. Resets
    the up-state machine so the next Connect starts fresh.

    QA fixes:
      - Kill any in-flight `tailscale up` subprocess so it can't flip the
        state machine back to running/failed after the user logged out.
        Without this, an orphaned auth flow could complete in the
        background and the badge would say "Connected" minutes after
        the user explicitly disconnected.
      - Bump attempt_id so any still-running daemon thread's terminal
        state mutation is silently dropped.
      - Clear `tailscale serve` config (best-effort) — leaving a
        Serve binding pointing at a now-disconnected tunnel produces
        confusing UX on the next reconnect under a different tailnet
        identity.
    """
    global _up_proc
    with _up_lock:
        # Bump attempt id first so any in-flight thread's terminal mutate
        # gets dropped.
        _up_state["attempt_id"] = int(_up_state.get("attempt_id", 0)) + 1
        if _up_proc is not None:
            try:
                if _up_proc.poll() is None:
                    _up_proc.kill()
            except Exception:
                pass
            _up_proc = None
        _up_state.update({
            "state": "idle",
            "auth_url": "",
            # v0.7.12 (#146): logout clears the sticky URL too — the next
            # Connect starts an entirely fresh auth flow with a fresh URL.
            "last_auth_url": "",
            "error": "",
            "started_at": 0.0,
            "ended_at": 0.0,
            "serve_state": "idle",
            "serve_error": "",
        })

    # Reset Tailscale Serve config best-effort. `tailscale serve reset`
    # exists on recent builds; older builds use `tailscale serve / off`
    # (NOT `--remove` — that's never been a valid flag). Worst case:
    # neither succeeds and a stale Serve binding auto-reattaches on
    # next Running tunnel via `configure_serve()`'s post-Running call.
    for args in (["serve", "reset"], ["serve", "/", "off"]):
        rc, _o, _e = _run_tailscale(args, timeout=5.0)
        if rc == 0:
            break

    rc, _out, err = _run_tailscale(["logout"], timeout=15.0)
    if rc != 0:
        return {"ok": False, "error": err.strip() or f"tailscale logout exited {rc}"}
    return {"ok": True}


# ── Tailscale Serve ────────────────────────────────────────────────────────


def configure_serve() -> dict[str, Any]:
    """POST /api/tailscale/serve — bind tailnet HTTPS to localhost:8787.

    QA fix v0.4.7-WaveH: previous syntax `tailscale serve --bg / http://localhost:8787`
    was the legacy positional-URL form. Tailscale 1.60+ removed it; on 1.96.4
    the call returned `Error: invalid argument format`. The modern syntax is
    just `tailscale serve [--bg] <port>` per `tailscale serve --help`. This
    means BOTH the v0.4.7 auto-Serve-after-Running path AND the
    entrypoint.sh boot-time auto-config have been silently failing on any
    container built since the legacy syntax was removed — verified during
    v0.4.7 QA Phase 0 against a real tailnet (1.96.4). Idempotent.

    Note: this requires HTTPS to be enabled on the user's tailnet (admin
    console → DNS → "Enable HTTPS"). Without that, even the correct syntax
    returns 'Serve is not enabled on your tailnet' with a hint URL — that's
    a per-tailnet config, not a code bug.
    """
    rc, _out, err = _run_tailscale(["serve", "--bg", "8787"], timeout=15.0)
    if rc != 0:
        return {"ok": False, "error": err.strip() or f"tailscale serve exited {rc}"}
    return {"ok": True}


def _attempt_configure_serve(attempt_id: int | None = None) -> dict[str, Any]:
    """Run configure_serve() and record the outcome on _up_state so the UI
    can show success / surface the error / offer a retry. Single channel
    that every code path uses (start_up after rc=0, get_up_progress on
    mid-poll Running detection, the explicit POST /api/tailscale/serve
    retry endpoint) — keeps configure_serve itself pure (CLI only) and
    centralises the state-write so it's gated by attempt_id consistently.

    The optional attempt_id is forwarded to _set_up_state so a stale daemon
    thread can't clobber the active attempt's serve_state, mirroring the
    existing guard for state= updates.

    Returns the configure_serve() result so callers (e.g. handle_post_serve)
    can pass it back over the wire.
    """
    try:
        result = configure_serve()
    except Exception as exc:  # pragma: no cover — defensive
        logger.debug("configure_serve raised", exc_info=True)
        err_msg = f"unexpected: {exc}"
        _set_up_state(attempt_id, serve_state="error", serve_error=err_msg)
        return {"ok": False, "error": err_msg}
    if not result.get("ok"):
        _set_up_state(attempt_id, serve_state="error",
                      serve_error=result.get("error", "tailscale serve failed"))
    else:
        _set_up_state(attempt_id, serve_state="ok", serve_error="")
    return result


def get_serve_status() -> dict[str, Any]:
    """GET /api/tailscale/serve — current `tailscale serve status`."""
    rc, out, err = _run_tailscale(["serve", "status", "--json"], timeout=5.0)
    if rc != 0:
        return {"ok": False, "error": err.strip() or f"tailscale serve status exited {rc}"}
    try:
        return {"ok": True, "config": json.loads(out) if out else {}}
    except json.JSONDecodeError:
        return {"ok": True, "config": {}, "raw": out}


# ── Route handlers ─────────────────────────────────────────────────────────


def handle_get_status(handler) -> dict[str, Any]:
    return get_status()


def handle_post_up(handler, body: dict) -> dict[str, Any]:
    return start_up(body or {})


def handle_get_up_poll(handler) -> dict[str, Any]:
    return get_up_progress()


def handle_post_logout(handler, body: dict) -> dict[str, Any]:
    return logout()


def handle_post_serve(handler, body: dict) -> dict[str, Any]:
    # Route through _attempt_configure_serve so the manual retry (this
    # endpoint) writes the same up_state the auto-config paths do — UI
    # polls /api/tailscale/status and renders from there. FITB#122 #2.
    return _attempt_configure_serve()


def handle_get_serve(handler) -> dict[str, Any]:
    return get_serve_status()


# ──────────────────────────────────────────────────────────────────────
# Fox dispatcher integration — Phase 5 of v0.6.0 migration.
# Replaces 29 lines of inline routing in api/routes.py. The dispatcher
# hook in routes.py (Phase 4) intercepts /api/tailscale/* before
# upstream's if/elif chain. api.helpers lazy-imported inside each
# wrapper (see ollama.py for rationale).
# ──────────────────────────────────────────────────────────────────────
from fox_overlay import dispatch  # noqa: E402


def _handle_get(handler, parsed) -> bool:
    """GET /api/tailscale/* — returns True if handled, False to fall through."""
    from api.helpers import j

    if parsed.path == "/api/tailscale/status":
        j(handler, handle_get_status(handler))
        return True
    if parsed.path == "/api/tailscale/up/poll":
        j(handler, handle_get_up_poll(handler))
        return True
    if parsed.path == "/api/tailscale/serve":
        j(handler, handle_get_serve(handler))
        return True
    return False


def _handle_post(handler, parsed) -> bool:
    """POST /api/tailscale/* — returns True if handled, False to fall through."""
    from api.helpers import j, read_body

    body = read_body(handler)

    if parsed.path == "/api/tailscale/up":
        result = handle_post_up(handler, body)
        j(handler, result, status=200 if result.get("ok") else 400)
        return True

    if parsed.path == "/api/tailscale/logout":
        result = handle_post_logout(handler, body)
        j(handler, result, status=200 if result.get("ok") else 400)
        return True

    if parsed.path == "/api/tailscale/serve":
        result = handle_post_serve(handler, body)
        j(handler, result, status=200 if result.get("ok") else 400)
        return True

    return False


dispatch.register_get("/api/tailscale/", _handle_get)
dispatch.register_post("/api/tailscale/", _handle_post)


