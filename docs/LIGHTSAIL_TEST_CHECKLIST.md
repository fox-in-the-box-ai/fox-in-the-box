# Lightsail Test Checklist

**Release:** v0.2.0  
**Test Date:** 2026-05-14  
**Tester:** Stan  

---

## Pre-Test Setup

- [ ] All 3 Lightsail instances spun up and accessible
- [ ] GitHub release v0.2.0 published with images + installers
- [ ] GHCR image available: `ghcr.io/fox-in-the-box-ai/cloud:v0.2.0`
- [ ] Installers uploaded to S3 or GitHub releases

---

## Linux (Ubuntu 24.04) — Docker

### Instance Details
- **Instance:** fitb-test-linux-2025-ubuntu
- **IP:** `__________`
- **Status:** ✅ Running

### Test Steps

#### 1. Docker Start
```bash
ssh -i ~/.ssh/lightsail.pem ubuntu@<IP>

docker pull ghcr.io/fox-in-the-box-ai/cloud:v0.2.0
docker run -d --name fitb \
  --cap-add=NET_ADMIN \
  --device /dev/net/tun \
  -p 8787:8787 \
  ghcr.io/fox-in-the-box-ai/cloud:v0.2.0
```

- [ ] Docker pull succeeded
- [ ] Docker run succeeded
- [ ] Container ID: `__________`

#### 2. Health Check
```bash
sleep 10
curl -v http://localhost:8787/health
```

- [ ] HTTP 200 response
- [ ] Response time: `__________` ms
- [ ] Logs clean (no errors): `docker logs fitb`

#### 3. User Workflow
- [ ] Open browser: http://<IP>:8787
- [ ] WebUI loaded successfully
- [ ] Create new chat session
- [ ] Send message: "What is your name?"
- [ ] Response received and display correct
- [ ] Response time: `__________` seconds

#### 4. Session Persistence
```bash
docker restart fitb
sleep 5
curl -f http://localhost:8787/health
```

- [ ] Container restarted
- [ ] Health check passed
- [ ] Previously created session still visible
- [ ] Can send new message in same session

#### 5. CLI Test (if applicable)
```bash
docker exec -it fitb hermes chat
# Send: "Hello"
# Exit: Ctrl+C
```

- [ ] CLI interactive
- [ ] Response received
- [ ] Clean shutdown

#### 6. Error Logs
```bash
docker logs fitb | grep -i error | head -10
```

- [ ] Paste any errors below:
```
__________
```

- [ ] Errors are expected/documented: YES / NO

#### 7. Cleanup
```bash
docker stop fitb && docker rm fitb
```

- [ ] Container stopped and removed

---

### Linux Summary

| Check | Status | Notes |
|-------|--------|-------|
| Docker pull | ✅ / ⚠️ / ❌ | __________ |
| Health check | ✅ / ⚠️ / ❌ | __________ |
| WebUI load | ✅ / ⚠️ / ❌ | __________ |
| Chat response | ✅ / ⚠️ / ❌ | __________ |
| Restart resilience | ✅ / ⚠️ / ❌ | __________ |
| Error-free logs | ✅ / ⚠️ / ❌ | __________ |

**Overall:** ✅ PASS / ⚠️ WARN / ❌ FAIL

---

## macOS (13.x) — `install.sh` + Docker

GitHub Releases do **not** ship a macOS `.dmg`. Validate the same path as end users: **`packages/scripts/install.sh`** (curl from `main` or copy from the repo).

### Instance Details
- **Instance:** fitb-test-macos-13
- **IP:** `__________`
- **Status:** ✅ Running

### Pre-Test
- [ ] **Docker Desktop** installed and running (script can install via Homebrew if `brew` is present; otherwise install manually first)
- [ ] SSH session ready: `ssh -i ~/.ssh/lightsail.pem ec2-user@<IP>` (or your test user)

### Test Steps

#### 1. Run installer (interactive)
```bash
ssh -i ~/.ssh/lightsail.pem ec2-user@<IP>

# Pipe from GitHub (default) or: bash /path/to/repo/packages/scripts/install.sh
curl -fsSL https://raw.githubusercontent.com/fox-in-the-box-ai/fox-in-the-box/main/packages/scripts/install.sh | bash
```

- [ ] Script completed without `die` / fatal error
- [ ] Container `fox-in-the-box` running: `docker ps --filter name=fox-in-the-box`

#### 2. Health & port
```bash
curl -f http://localhost:8787/health
# If you chose Tailscale-only in the script, use the HTTPS URL from script output instead.
```

- [ ] Health check: YES / NO
- [ ] Port 8787 reachable (or Tailscale URL): YES / NO

#### 3. WebUI access
```bash
# From the same Mac instance, open in browser or:
curl -fsS -o /dev/null -w "%{http_code}" http://localhost:8787/
```

- [ ] WebUI loaded
- [ ] Create chat session
- [ ] Send message: "Hello"
- [ ] Response received

#### 4. launchd (if script installed it)
```bash
launchctl list io.foxinthebox 2>/dev/null || echo "not loaded"
```

- [ ] Agent loaded: YES / NO / N/A (skipped)

#### 5. Logs
```bash
docker logs --tail 50 fox-in-the-box
```

- [ ] Paste any errors below:
```
__________
```

- [ ] Errors are expected: YES / NO

#### 6. Cleanup
```bash
docker stop fox-in-the-box && docker rm fox-in-the-box
launchctl unload "$HOME/Library/LaunchAgents/io.foxinthebox.plist" 2>/dev/null || true
# Optional: remove data dir used in test
```

- [ ] Container stopped/removed
- [ ] launchd unloaded if it was installed

---

### macOS Summary

| Check | Status | Notes |
|-------|--------|-------|
| install.sh | ✅ / ⚠️ / ❌ | __________ |
| Docker / container | ✅ / ⚠️ / ❌ | __________ |
| Health / port | ✅ / ⚠️ / ❌ | __________ |
| WebUI access | ✅ / ⚠️ / ❌ | __________ |
| launchd (optional) | ✅ / ⚠️ / ❌ | __________ |
| Error-free logs | ✅ / ⚠️ / ❌ | __________ |

**Overall:** ✅ PASS / ⚠️ WARN / ❌ FAIL

---

## Windows (Server 2022) — Installer

### Instance Details
- **Instance:** fitb-test-windows-2022
- **IP:** `__________`
- **Status:** ✅ Running

### Test Steps

#### 1. EXE Download & Install
```powershell
# On local machine: Copy installer to instance
$InstanceIP = "__________"
$InstallerPath = "fox-in-the-box-0.2.0.exe"

# Use RDP or SCP to transfer
# SCP equivalent: scp -i ~/.ssh/lightsail.pem $InstallerPath Administrator@${InstanceIP}:C:\temp\

# Then via RDP or SSH:
cd C:\temp\
.\fox-in-the-box-0.2.0.exe /S /D="C:\Program Files\Fox in the Box"
```

- [ ] Download completed
- [ ] Installation started
- [ ] Installation completed (exit code 0)

#### 2. App Launch
```powershell
# Wait for install to finish
Start-Sleep -Seconds 10

# Run app
& "C:\Program Files\Fox in the Box\Fox in the Box.exe"

Start-Sleep -Seconds 5

# Check process
Get-Process | Where-Object {$_.Name -like "*fox*"}
```

- [ ] App launched
- [ ] Process visible: YES / NO
- [ ] Process name: `__________`

#### 3. Port Check
```powershell
Get-NetTCPConnection -LocalPort 8787 -ErrorAction SilentlyContinue | Select-Object State, OwningProcess
```

- [ ] Port 8787 listening: YES / NO
- [ ] Process ID: `__________`

#### 4. WebUI Access
```powershell
# On local machine: Port forward via RDP or SSH
ssh -i ~/.ssh/lightsail.pem -L 8787:localhost:8787 Administrator@${InstanceIP}
# Then open http://localhost:8787
```

- [ ] WebUI loaded
- [ ] Create chat session
- [ ] Send message: "Hello"
- [ ] Response received

#### 5. Taskbar Icon
- [ ] Check Windows taskbar
- [ ] App icon visible: YES / NO

#### 6. Event Viewer Check
```powershell
# Check for critical errors
Get-EventLog -LogName Application -EntryType Error -Newest 10 | Select-Object TimeGenerated, Source, Message
```

- [ ] Critical errors: NONE / SOME
- [ ] Errors listed below:
```
__________
```

#### 7. Startup Performance
```powershell
# Time from launch to port open
Measure-Command {
    & "C:\Program Files\Fox in the Box\Fox in the Box.exe"
    Start-Sleep -Seconds 1
    while (!(Get-NetTCPConnection -LocalPort 8787 -ErrorAction SilentlyContinue)) {
        Start-Sleep -Seconds 1
    }
}
```

- [ ] Startup time: `__________` seconds

#### 8. Cleanup
```powershell
# Terminate process
taskkill /IM "Fox in the Box.exe" /F

# Uninstall
& "C:\Program Files\Fox in the Box\Uninstall.exe" /S
```

- [ ] Process terminated
- [ ] Uninstall completed

---

### Windows Summary

| Check | Status | Notes |
|-------|--------|-------|
| EXE install | ✅ / ⚠️ / ❌ | __________ |
| App launch | ✅ / ⚠️ / ❌ | __________ |
| Port open | ✅ / ⚠️ / ❌ | __________ |
| WebUI access | ✅ / ⚠️ / ❌ | __________ |
| Taskbar icon | ✅ / ⚠️ / ❌ | __________ |
| No critical errors | ✅ / ⚠️ / ❌ | __________ |
| Startup time | `____` sec | __________ |

**Overall:** ✅ PASS / ⚠️ WARN / ❌ FAIL

---

## Summary

| Platform | Status | Blocker | Notes |
|----------|--------|---------|-------|
| Linux | ✅ / ⚠️ / ❌ | YES/NO | __________ |
| macOS | ✅ / ⚠️ / ❌ | YES/NO | __________ |
| Windows | ✅ / ⚠️ / ❌ | YES/NO | __________ |

### Issues Found

1. **Issue:** __________
   - **Platform:** __________
   - **Severity:** 🔴 Blocker / 🟡 Warning / 🟢 Minor
   - **Status:** New / In progress / Fixed
   - **Notes:** __________

2. (Add as needed)

### Recommendation

- ✅ **DEPLOY** — All tests pass, no blockers
- ⚠️ **DEPLOY WITH CAVEATS** — Warnings noted, user impact minimal
- ❌ **DO NOT DEPLOY** — Blockers found, fix before release

### Teardown

```bash
# All instances terminated:
aws lightsail delete-instances --instance-names \
    fitb-test-linux-2025-ubuntu \
    fitb-test-macos-13 \
    fitb-test-windows-2022
```

- [ ] Linux instance deleted
- [ ] macOS instance deleted
- [ ] Windows instance deleted
- [ ] Deletion timestamp: __________

### Sign-Off

**Tested by:** Stan  
**Test date:** 2026-05-14  
**Duration:** __________ hours  
**Approved for release:** YES / NO  
**Signature:** __________
