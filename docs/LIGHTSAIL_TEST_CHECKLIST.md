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

## macOS (13.x) — Installer

### Instance Details
- **Instance:** fitb-test-macos-13
- **IP:** `__________`
- **Status:** ✅ Running

### Pre-Test
- [ ] Download installer to local machine first (faster than from Lightsail)
- [ ] Copy to Lightsail: `scp -i ~/.ssh/lightsail.pem fox-in-the-box-0.2.0.dmg ec2-user@<IP>:/tmp/`

### Test Steps

#### 1. DMG Mount & Install
```bash
ssh -i ~/.ssh/lightsail.pem ec2-user@<IP>

# Mount DMG
hdiutil mount /tmp/fox-in-the-box-0.2.0.dmg
# → /Volumes/fox-in-the-box-0.2.0

# Copy app
cp -r /Volumes/fox-in-the-box-0.2.0/"Fox in the Box.app" /Applications/

# Unmount
umount /Volumes/fox-in-the-box-0.2.0
```

- [ ] DMG mounted successfully
- [ ] App copied to /Applications/
- [ ] DMG unmounted

#### 2. App Launch
```bash
# Start app in background
nohup /Applications/"Fox in the Box.app"/Contents/MacOS/"Fox in the Box" > /tmp/fitb.log 2>&1 &

sleep 5

# Check process
ps aux | grep -i fox
```

- [ ] Process running: YES / NO
- [ ] PID: `__________`

#### 3. Port Open
```bash
netstat -tuln | grep 8787
# Or: sudo lsof -i :8787
```

- [ ] Port 8787 open: YES / NO
- [ ] App listening: YES / NO

#### 4. WebUI Access
```bash
# On local machine:
ssh -i ~/.ssh/lightsail.pem -L 8787:localhost:8787 ec2-user@<IP>
# Then open http://localhost:8787
```

- [ ] WebUI loaded
- [ ] Create chat session
- [ ] Send message: "Hello"
- [ ] Response received

#### 5. Gatekeeper Check
```bash
# Check for notarization status
spctl -a -v /Applications/"Fox in the Box.app"
```

- [ ] Status: ✅ Notarized / ⚠️ Unsigned warning / ❌ Blocked

#### 6. Logs
```bash
tail -50 ~/.hermes/logs/agent.log
cat /tmp/fitb.log
```

- [ ] Paste any errors below:
```
__________
```

- [ ] Errors are expected: YES / NO

#### 7. Cleanup
```bash
kill %1  # or: killall "Fox in the Box"
rm -rf /Applications/"Fox in the Box.app"
```

- [ ] App terminated
- [ ] App removed

---

### macOS Summary

| Check | Status | Notes |
|-------|--------|-------|
| DMG mount | ✅ / ⚠️ / ❌ | __________ |
| App copy | ✅ / ⚠️ / ❌ | __________ |
| App launch | ✅ / ⚠️ / ❌ | __________ |
| Port open | ✅ / ⚠️ / ❌ | __________ |
| WebUI access | ✅ / ⚠️ / ❌ | __________ |
| Gatekeeper | ✅ / ⚠️ / ❌ | __________ |
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
