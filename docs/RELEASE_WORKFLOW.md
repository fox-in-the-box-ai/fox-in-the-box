# Biweekly Release Workflow

**Cycle:** Every 2 weeks  
**Testing:** Clean instances (Lightsail: Linux, macOS, Windows)  
**Patch flow:** VPS → git format-patch → FITB `vps-wip` branch → manual release selection

---

## The Cycle

```
Week 1 (Mon-Fri): Development
├─ VPS work: git commit, test locally
└─ Create patches: git format-patch

Week 2 (Mon-Thu): Patch integration + testing
├─ Patches auto-cherry-pick to FITB vps-wip branch
├─ Manual feature selection for release
└─ Spin up Lightsail instances, test all 3 platforms

Week 2 (Fri): Release
├─ Tag release (v0.1.X, v0.2.0, etc.)
├─ GitHub Actions builds + publishes
├─ Teardown Lightsail instances
└─ Document changelog

Repeat...
```

---

## Phase 1: VPS Development (Monday – Friday)

### On VPS

```bash
# Work in your personal setup
cd /workspace/fox-in-the-box
git checkout -b vps/my-feature
# ... edit code, test, commit ...
git commit -m "fix(electron): Windows Docker install progress"

# Create patches for integration
git format-patch origin/main -o /patches/
# Outputs: 0001-fix-electron-Windows-Docker-install-progress.patch
```

### Why format-patch?

- **Reviewable**: each commit is a standalone file
- **Portable**: no merge conflicts, clean cherry-pick
- **Auditable**: preserves author, timestamp, commit message
- **Clean history**: no "merge commit clutter"

---

## Phase 2: Automated Patch Integration (Saturday morning)

### Cron Job: `vps-patch-sync` (FITB)

**Runs:** Every Saturday 09:00 UTC  
**Task:** Fetch patches from VPS, cherry-pick to `vps-wip`

```bash
#!/bin/bash
# /workspace/.hermes/scripts/vps-patch-sync.sh

set -euo pipefail
cd /workspace/fox-in-the-box

# Fetch latest patches from VPS
rsync -avz --delete \
    ubuntu@fitb-vps:/patches/ \
    /tmp/vps-patches/

# Ensure vps-wip exists and is up-to-date
git fetch origin vps-wip || git checkout -b vps-wip origin/main
git checkout vps-wip
git reset --hard origin/main

# Cherry-pick all patches in order
for patch in /tmp/vps-patches/*.patch; do
    if git apply --check "$patch" 2>/dev/null; then
        git am "$patch"
        echo "✓ Applied: $(basename $patch)"
    else
        echo "✗ CONFLICT: $(basename $patch)"
        echo "  Manual review needed"
        # Notify Stan
        send_notification "Patch conflict: $patch"
    fi
done

# Push vps-wip (create if needed)
git push -u origin vps-wip

echo "Patch sync complete. vps-wip updated."
```

**Cron entry:**
```bash
# At 09:00 on Saturday
0 9 * * 6 /workspace/.hermes/scripts/vps-patch-sync.sh >> ~/.hermes/logs/vps-patch-sync.log 2>&1
```

### Notification on conflict

```bash
# Send message to you (Telegram/Slack/etc.)
send_message "FITB: Patch conflict in vps-wip — manual review needed"
```

---

## Phase 3: Feature Selection & Release Branch (Monday morning)

### Manual Review

```bash
# Look at what's in vps-wip
git log origin/vps-wip..origin/main --oneline --reverse
# Shows commits NOT yet in main

# Review PRs or commit messages
git show HEAD~5..HEAD

# Example output:
#   fix(electron): Windows Docker install progress
#   feat(webui): session lock watchdog
#   fix(cli): graceful shutdown on SIGTERM
#   refactor(agent): ContextVars propagation
#   docs: update README
```

### Decide what goes in release

**Option A: Release branch (recommended)**
```bash
git checkout -b release/v0.2.0 origin/main

# Cherry-pick specific commits from vps-wip
git cherry-pick <commit-hash>  # fix(electron)
git cherry-pick <commit-hash>  # feat(webui)
# skip others (docs, refactor)
```

**Option B: Merge all of vps-wip**
```bash
git checkout release/v0.2.0
git merge --no-ff origin/vps-wip  # All commits from vps-wip
```

### Create release
```bash
# Update VERSION
echo "0.2.0" > VERSION

# Commit + tag
git add VERSION
git commit -m "release: v0.2.0"
git tag -a v0.2.0 -m "Release v0.2.0 — Session locks, graceful shutdown, Windows Docker"

# Push (triggers CI/CD)
git push origin release/v0.2.0
git push origin v0.2.0
```

---

## Phase 4: Testing on Lightsail (Tuesday – Thursday)

### Provision: 3 Clean Instances

**Use:** AWS Lightsail (you have free credits)

```bash
# Create script: provision-lightsail.sh
for OS in linux-2025-ubuntu macos-13 windows-2022; do
    aws lightsail create-instances \
        --instance-name "fitb-test-$OS" \
        --availability-zone us-east-1a \
        --blueprint-id "$OS" \
        --bundle-id small_3_0 \
        --tags "Name=FITB Test,Date=$(date +%Y-%m-%d)"
done

echo "Waiting for instances..."
sleep 30

# Get IPs
aws lightsail get-instances --query 'instances[*].[name,publicIpAddress]' --output table
```

### Test Scenarios (per platform)

Each instance runs the same test checklist:

#### Linux (Ubuntu 24.04)

```bash
# 1. Fresh start
docker pull ghcr.io/fox-in-the-box-ai/cloud:v0.2.0
docker run -d --name fitb \
  --cap-add=NET_ADMIN \
  --device /dev/net/tun \
  -p 8787:8787 \
  -e TAILSCALE_AUTH_KEY=$KEY \
  ghcr.io/fox-in-the-box-ai/cloud:v0.2.0

# 2. Wait for health
curl -f http://localhost:8787/health || echo "FAILED"

# 3. User workflow
# - Open WebUI at http://localhost:8787
# - Create new chat session
# - Send message: "What is your name?"
# - Verify response

# 4. Check logs for errors
docker logs fitb | grep -i error || echo "No errors"

# 5. Test graceful restart
docker restart fitb
sleep 5
curl -f http://localhost:8787/health || echo "FAILED"

# 6. Cleanup
docker stop fitb && docker rm fitb
```

#### macOS (13.x)

Releases do **not** ship a `.dmg`. Use the same **`install.sh`** path as Linux (Docker + optional launchd):

```bash
# 1. Install Docker Desktop if needed, pull image, run container (interactive prompts)
curl -fsSL https://raw.githubusercontent.com/fox-in-the-box-ai/fox-in-the-box/main/packages/scripts/install.sh | bash

# 2. Wait for health (adjust URL if you chose Tailscale-only in the script)
sleep 15
curl -f http://localhost:8787/health || echo "FAILED"

# 3. User workflow (same as Linux)
# - Open WebUI at http://localhost:8787 (or Tailscale URL from script output)
# - Create chat session
# - Send message
# - Verify response

# 4. Check logs
docker logs fox-in-the-box 2>&1 | tail -50

# 5. Cleanup (optional)
docker stop fox-in-the-box && docker rm fox-in-the-box
launchctl unload "$HOME/Library/LaunchAgents/io.foxinthebox.plist" 2>/dev/null || true
```

#### Windows (Server 2022)

```powershell
# 1. Download installer
aws s3 cp s3://fitb-releases/fox-in-the-box-0.2.0.exe ./

# 2. Install (silent)
.\fox-in-the-box-0.2.0.exe /S /D=C:\Program Files\Fox in the Box

# 3. Wait for app
Start-Sleep -Seconds 10

# 4. Run
& "C:\Program Files\Fox in the Box\Fox in the Box.exe"

# 5. Wait for UI
Start-Sleep -Seconds 10

# 6. User workflow
# - Check app launched in taskbar
# - Open WebUI
# - Create chat session
# - Send message
# - Verify response

# 7. Check logs
Get-Content $env:APPDATA\.hermes\logs\agent.log | Select-String -Pattern "error" -NotMatch | Tail -50

# 8. Cleanup
taskkill /IM "Fox in the Box.exe"
```

### Results Template

```markdown
## Release v0.2.0 Test Results

| Platform | Status | Notes | Tested By |
|----------|--------|-------|-----------|
| Linux (Ubuntu 24.04) | ✅ PASS | Docker start OK, chat responsive | Stan |
| macOS (13.6) | ✅ PASS | `install.sh` + Docker, WebUI OK | Stan |
| Windows (Server 2022) | ⚠️ WARN | Slow startup (Docker Desktop busy), but works | Stan |

### Issues Found
- None blocking release

### Recommendations
- Deploy v0.2.0 to prod

### Teardown
- All instances terminated at 2026-05-15 18:00 UTC
```

---

## Phase 5: Release & Cleanup (Friday)

### Release

```bash
# GitHub Actions already built + published on tag push
# Verify images exist
docker pull ghcr.io/fox-in-the-box-ai/cloud:v0.2.0
docker pull ghcr.io/fox-in-the-box-ai/cloud:latest

# Windows installer on releases page (macOS: use install.sh from README)
# https://github.com/fox-in-the-box-ai/fox-in-the-box/releases/tag/v0.2.0
```

### Terminate Lightsail instances

```bash
aws lightsail delete-instances \
    --instance-names \
        fitb-test-linux-2025-ubuntu \
        fitb-test-macos-13 \
        fitb-test-windows-2022

# Verify deletion
aws lightsail get-instances --query 'instances[*].name'
```

### Document changelog

```bash
# Create CHANGELOG entry (or auto-generate from commits)
cat >> CHANGELOG.md << 'EOF'
## v0.2.0 (2026-05-15)

### Features
- Session lock watchdog — prevents "session unresponsive" on agent crash
- CLI graceful shutdown — SIGTERM/SIGINT handlers, session checkpoint

### Fixes
- Windows Docker fully automated — no user steps required
- Electron icon on Windows

### Testing
- ✅ Linux: Docker
- ✅ macOS: install.sh + Docker
- ✅ Windows: Installer

### Contributors
- Stan
EOF

git add CHANGELOG.md
git commit -m "chore: document v0.2.0 release"
git push origin main
```

---

## Automation: Cron Schedule

```bash
# ~/.hermes/cron/fitb-release-workflow.txt (Hermes cron job)

# Every Saturday 09:00 UTC — fetch patches from VPS, cherry-pick to vps-wip
0 9 * * 6 /workspace/.hermes/scripts/vps-patch-sync.sh

# Every Monday 08:00 UTC — remind Stan to review vps-wip and create release branch
0 8 * * 1 send_notification "FITB: Review vps-wip branch, create release/v*.x.x if ready"
```

---

## Git Branch Strategy

```
origin/main (production)
├─ release/v0.2.0 (testing)
│  └─ cherry-picked commits
└─ vps-wip (WIP accumulation)
   ├─ cherry-picked patches from VPS
   └─ conflicts resolved manually
```

**Key points:**
- `main` = production-ready code
- `vps-wip` = staging (all patches from VPS)
- `release/vX.X.X` = subset of vps-wip for testing
- Only tags trigger CI/CD (v0.2.0, etc.)

---

## Files to Create

1. **`/workspace/.hermes/scripts/vps-patch-sync.sh`** — Cron job (auto cherry-pick)
2. **`RELEASE_WORKFLOW.md`** — This doc (in FITB repo)
3. **`LIGHTSAIL_TEST_CHECKLIST.md`** — Test scenarios per platform
4. **`CHANGELOG.md`** — Auto-updated per release

---

## Environment Setup (One-time)

### On VPS (fitb-vps)

```bash
# Create patches directory
mkdir -p /patches
chmod 777 /patches

# SSH key for rsync (allow FITB to pull patches)
ssh-keygen -t ed25519 -f ~/.ssh/vps-patch-sync -N ""
# Share public key with FITB machine (for rsync)
```

### On FITB (dev machine)

```bash
# Add SSH key for VPS
cat ~/.ssh/vps-patch-sync >> ~/.ssh/authorized_keys

# Create cron job
cat > ~/.hermes/scripts/vps-patch-sync.sh << 'EOF'
#!/bin/bash
... (script above)
EOF
chmod +x ~/.hermes/scripts/vps-patch-sync.sh

# Schedule
crontab -e
# Add: 0 9 * * 6 /workspace/.hermes/scripts/vps-patch-sync.sh
```

---

## Tools Used

| Tool | Purpose |
|------|---------|
| `git format-patch` | Create portable patch files |
| `git am` | Apply patches with history |
| `aws lightsail` | Create clean test instances |
| `docker pull` | Deploy test images |
| `rsync` | Transfer patches from VPS to FITB |
| Hermes cronjob | Automate patch sync |

---

## Typical Timeline

```
Saturday 09:00 → Patches auto-synced to vps-wip
Monday 08:00 → Reminder to review + create release branch
Monday 14:00 → Release branch created, tagging triggers CI
Monday 16:00 → Images available on GHCR, installers uploaded
Tuesday 10:00 → Lightsail instances spin up
Tue–Thu → Testing on 3 platforms
Thursday 17:00 → All tests pass, instances terminated
Friday 10:00 → Release announcement
```

Total hands-on time: ~4 hours (mostly waiting for builds + testing)

---

## Cost Estimate

**Per biweekly cycle:**
- 3 Lightsail instances × 2 days × $0.005/hour = ~$0.72
- You have free credits, so no actual cost

**Total:** ~$1.50/month (negligible with free tier)
