# Task 10: CLI Graceful Shutdown on Service Restart (P0)

**Priority:** P0 — UX-critical  
**Status:** In progress (upstream feature branches)  
**Epic:** Service stability & reliability  
**Owner:** Upstream (Hermes Agent + WebUI teams)  
**FITB Sync:** Tracking `cli-graceful-shutdown` branches in both forks

---

## Problem Statement

When Hermes gateway restarts due to process conflicts, it kills active CLI sessions with `pkill -9`, leaving TUI in a broken state with cryptic asyncio exceptions:

```
ERROR asyncio: unhandled exception during asyncio.run() shutdown
OSError(5, 'Input/output error')
```

**UX Impact:** Session drops silently. User has no way to recover context or understand what happened.

**Root Cause:**
- CLI processes receive SIGKILL (force-kill) instead of SIGTERM (graceful shutdown)
- prompt_toolkit TUI has no signal handlers
- No session checkpoint before termination
- No user notification

---

## Solution (Upstream Implementation)

### Branches

- **hermes-agent:** `cli-graceful-shutdown` (implements CLI signal handling + session checkpoint)
- **hermes-webui:** `cli-graceful-shutdown` (implements lock timeout + watchdog)

### Components

**1. CLI Signal Handling (hermes-agent)**
- Add SIGTERM/SIGINT handlers to `HermesCLI`
- Implement session checkpoint to `~/.hermes/sessions/`
- Catch `OSError(5)` on asyncio shutdown
- Show user-friendly "Gateway restarting..." banner
- Exit cleanly without exception spam

**2. TUI Renderer Error Handling (hermes-agent)**
- Wrap `asyncio.run()` with try/except for I/O loss
- Distinguish clean shutdown from real errors
- Log as INFO (not ERROR) when I/O is intentionally severed

**3. WebUI Session Lock Watchdog (hermes-webui)**
- `AgentSessionLock` class with timeout-acquire (300s default)
- Watchdog thread scans for dead lock-holders every 60s
- Force-release with diagnostic callbacks
- Prevents "session unresponsive" when agent thread crashes

**4. Integration**
- Integrate `AgentSessionLock` into `api/config.py`
- Add error routes for lock timeout in `api/routes.py`
- Surface lock errors as SSE "error" event
- Update gateway graceful shutdown sequence

### Acceptance Criteria

- [ ] CLI receives SIGTERM on gateway restart and exits cleanly (no OSError exceptions)
- [ ] Session checkpoint is persisted and recoverable
- [ ] User sees clear message explaining what happened
- [ ] WebUI lock timeout prevents "session unresponsive" when agent thread dies
- [ ] Watchdog successfully force-releases dead-held locks
- [ ] No exception spam in logs on graceful shutdown
- [ ] Auto-resume works after interrupted session
- [ ] End-to-end test passes: gateway restart → CLI checkpoint → recover

---

## Implementation Phases

### Phase 1: CLI Signal Handling (hermes-agent)
- Files: `cli.py`, `agent/display.py`, `hermes_logging.py`
- Expected commits: 3-4
- Status: Ready for implementation

### Phase 2: WebUI Session Locks (hermes-webui)
- Files: `api/agent_lock.py` (existing, stashed), `api/config.py`, `api/routes.py`, `api/streaming.py`
- Expected commits: 2-3
- Status: WIP code stashed, ready to integrate

### Phase 3: Integration & Testing
- Test SIGTERM handling with `kill -15 $PID`
- Verify session checkpoint persists
- Test lock watchdog force-release
- End-to-end: gateway restart → CLI clean exit
- Expected commits: 2-3

### Phase 4: Polish (optional)
- Auto-resume on next launch
- Gateway shutdown notification
- Metrics tracking
- Expected commits: 1-2

---

## FITB Integration

**Submodules tracking:**
```
forks/hermes-agent       → cli-graceful-shutdown branch
forks/hermes-webui       → cli-graceful-shutdown branch
```

**Once upstream merges to `local-patches`:**
- FITB submodule pointers update to include these fixes
- User-facing CLI gets graceful restart handling
- WebUI gets lock timeout protection

---

## Testing Strategy

### hermes-agent
```bash
# Test signal handler
kill -15 $CLI_PID  # SIGTERM while running
# Expected: clean exit with checkpoint message

# Test asyncio OSError catch
# (Verify I/O loss triggers graceful exit, not exception)
```

### hermes-webui
```bash
# Test lock timeout
python -m pytest tests/test_agent_lock.py::test_acquire_timeout

# Test watchdog force-release
python -m pytest tests/test_agent_lock.py::test_watchdog_force_release
```

### End-to-End
```bash
# Terminal 1: start gateway
hermes gateway run

# Terminal 2: start CLI
hermes chat

# Terminal 3: restart gateway
systemctl --user restart hermes-gateway

# Expected in Terminal 2:
#   ⚠ Gateway is restarting...
#   Saving session checkpoint...
#   Session <ID> saved ✓
#   Exiting cleanly.
```

---

## FITB Todo

- [ ] Monitor upstream branches for merge to `local-patches`
- [ ] Update submodule pointers when ready
- [ ] Update DONE.md with merge status
- [ ] Test full CLI → gateway restart → resume flow in container
- [ ] Verify Electron desktop client handles graceful restarts

---

## Documentation

- **Upstream:** `~/.hermes/hermes-agent/` and `~/hermes-webui/` on `cli-graceful-shutdown` branches
- **Plan:** `/workspace/CLI_GRACEFUL_SHUTDOWN.md` (full implementation details)
- **Cleanup log:** `/workspace/.git-cleanup-log.md` (what was cleaned, stashed, how to restore)

---

## References

- **Session files:** `~/.hermes/sessions/`
- **Agent logs:** `~/.hermes/logs/agent.log` + `errors.log`
- **Gateway logs:** `~/.hermes/logs/gateway.log`
- **Related upstream PR:** #18123 (ContextVars propagation to tool workers)
