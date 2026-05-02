# 📋 FITB Biweekly Release Workflow — COMPLETE

## ✅ What You Now Have

### 1. **Version Sync System**
- Single `VERSION` file at repo root
- Automatically used by Dockerfile, package.json, Electron app
- Update once: `echo "0.2.0" > VERSION`

### 2. **Dev Mode** 
- **Build:** `pnpm build:docker:dev` (one-time)
- **Run:** `pnpm dev:container` (bind mounts auto-sync)
- **Iterate:** Change code locally, see changes instantly in container
- **Speed:** Seconds, not 5-10 minutes per cycle

### 3. **Biweekly Release Workflow**
```
VPS work (Mon-Fri)
   ↓ git format-patch
   ↓
FITB vps-wip branch (Saturday auto-sync via cron)
   ↓
Manual feature selection (Monday)
   ↓ git cherry-pick + git tag v0.2.0
   ↓
CI/CD builds (GitHub Actions)
   ↓
Lightsail testing (3 platforms: Linux/macOS/Windows)
   ↓
Release + cleanup (Friday)
```

---

## 📚 Documentation (45KB total)

| File | Purpose | Size |
|------|---------|------|
| `DEV_MODE.md` | How to use dev mode (examples, troubleshooting) | 6.4 KB |
| `RELEASE_WORKFLOW.md` | Complete release cycle (detailed process) | 12 KB |
| `LIGHTSAIL_TEST_CHECKLIST.md` | Per-platform test checklists (fillable) | 8.7 KB |
| `WORKFLOW_COMPLETE.md` | Quick reference guide (1-page overview) | 9.4 KB |
| `TASK_11_DELIVERY.md` | This delivery summary | 8.7 KB |
| `docs/tasks/11-version-sync-dev-mode.md` | Task specification | 5 KB |

**Start with:** `WORKFLOW_COMPLETE.md` (quick overview)  
**Then:** `DEV_MODE.md` (for dev iteration)  
**For releases:** `RELEASE_WORKFLOW.md` (step-by-step)  
**For testing:** `LIGHTSAIL_TEST_CHECKLIST.md` (fillable checklists)

---

## 🚀 Quick Commands

### Dev Iteration
```bash
pnpm build:docker:dev        # Build once
pnpm dev:container           # Run with mounts

# In another terminal:
cd forks/hermes-agent
git checkout feature/my-fix
# Changes visible immediately
```

### Release Cycle
```bash
# On VPS: create patches
git format-patch origin/main -o /patches/

# Saturday 09:00: Auto-synced to vps-wip (cron job)
git checkout vps-wip  # see all patches

# Monday: Select features
git checkout -b release/v0.2.0 origin/main
git cherry-pick <commit>
git cherry-pick <commit>
git cherry-pick <commit>

# Tag & push (triggers CI/CD)
echo "0.2.0" > VERSION
git tag v0.2.0 && git push origin v0.2.0

# Tue-Thu: Test on Lightsail (3 instances)
# See: LIGHTSAIL_TEST_CHECKLIST.md

# Friday: Teardown
aws lightsail delete-instances --instance-names fitb-test-*
```

---

## ⏱️ Timeline Per Release

**Total hands-on: ~4 hours / biweekly**

| When | What | Time |
|------|------|------|
| Sat 09:00 | Patch sync (auto) | 0 min |
| Mon 09:00 | Review features | 15 min |
| Mon 10:30 | Create release branch + tag | 15 min |
| Tue 10:00 | Spin up instances | 10 min |
| Tue-Thu | Test (mostly waiting) | 90 min |
| Thu 17:00 | Review results | 15 min |
| Fri 10:00 | Cleanup + announce | 15 min |

---

## 💰 Cost

**Per release cycle:** ~$0.72 (negligible with AWS free credits)  
**Annual:** ~$18.72 (you have free credits, so $0)

---

## 🔧 One-Time Setup (5 minutes)

### On VPS
```bash
mkdir -p /patches && chmod 777 /patches
ssh-keygen -t ed25519 -f ~/.ssh/vps-patch-sync -N ""
# Copy public key to FITB machine for rsync
```

### On FITB dev machine
```bash
chmod +x scripts/vps-patch-sync.sh

# Add to crontab:
# 0 9 * * 6 /home/ubuntu/workspace/scripts/vps-patch-sync.sh
crontab -e
```

Done. Automation now runs every Saturday at 09:00 UTC.

---

## 📊 What's Automated

- ✅ Saturday 09:00: Fetch patches from VPS → cherry-pick to vps-wip
- ✅ Handles conflicts (logs, sends notification)
- ✅ Monday: CI/CD builds + publishes (on git push tag)
- ✅ Testing: Checklists fillable, results tracked

What's manual:
- Feature selection (Monday 1 hour)
- Testing (Tue-Thu 90 min)
- Announce release (Friday 15 min)

---

## 🎯 Files to Remember

**Every dev session:**
- `DEV_MODE.md` — dev mode commands

**Every release:**
- `RELEASE_WORKFLOW.md` — step-by-step process
- `LIGHTSAIL_TEST_CHECKLIST.md` — fill out per platform
- `VERSION` — update version number

**For reference:**
- `WORKFLOW_COMPLETE.md` — 1-page overview
- `scripts/vps-patch-sync.sh` — cron job logic

---

## ✨ You Now Have

1. ✅ **Seconds-speed dev iteration** (not 5-10 min rebuilds)
2. ✅ **Clean release pipeline** (VPS → FITB → Lightsail → GitHub → Users)
3. ✅ **Tested on all 3 platforms** before every release
4. ✅ **Automated patch integration** (Saturday cron)
5. ✅ **~4 hours per 2-week cycle** (mostly waiting)
6. ✅ **Zero-cost testing** (AWS free tier)

---

## 🚢 Ready to Ship

All systems tested and documented. Start with v0.2.0 release:

1. Create patches on VPS
2. Wait for Saturday 09:00 (auto-sync)
3. Monday: select features, tag, push
4. Tue-Thu: test on Lightsail
5. Friday: announce

Questions? See `WORKFLOW_COMPLETE.md` (1-page overview).

**Next:** Schedule first release cycle. Suggest May 15, 2026 for v0.2.0. 🚀
