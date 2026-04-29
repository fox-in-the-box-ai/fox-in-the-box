# DONE — Task 01: GitHub Repository Setup

**Completed by:** Hermes (Supervisor agent)
**Date:** 2026-04-29
**Status:** ✅ ALL ACCEPTANCE CRITERIA PASS

---

## What Was Done

1. **GitHub org confirmed** — `fox-in-the-box-ai` already existed (Stan created it).

2. **Main monorepo created** — `fox-in-the-box-ai/fox-in-the-box` created via API:
   - Public repo, MIT license, default branch `main`
   - URL: https://github.com/fox-in-the-box-ai/fox-in-the-box

3. **hermes-agent fork created** — Forked `NousResearch/hermes-agent` into `fox-in-the-box-ai/hermes-agent`:
   - URL: https://github.com/fox-in-the-box-ai/hermes-agent
   - Upstream: NousResearch/hermes-agent, default branch `main`

4. **hermes-webui fork created** — Forked `nesquena/hermes-webui` into `fox-in-the-box-ai/hermes-webui`:
   - URL: https://github.com/fox-in-the-box-ai/hermes-webui
   - Upstream: nesquena/hermes-webui, default branch `master`
   - Note: upstream default branch is `master`, not `main` — submodule config in task 02 should use `master`

5. **Local repo initialized and pushed** — Initial commit pushed to `main` with all pre-existing doc files:
   - REQUIREMENTS.md, ROADMAP.md, AGENTS.md, docs/tasks/*, LICENSE, README.md, CONTRIBUTING.md

6. **Git identity configured globally**: Stanislav Polyakov / polyakov.ci@gmail.com

---

## Acceptance Criteria Verification

| # | Criterion | Result |
|---|-----------|--------|
| 1 | `fox-in-the-box-ai` org exists | ✅ PASS |
| 2 | `fox-in-the-box-ai/fox-in-the-box` exists, default branch `main` | ✅ PASS |
| 3 | `fox-in-the-box-ai/hermes-agent` exists as fork of NousResearch/hermes-agent | ✅ PASS |
| 4 | `fox-in-the-box-ai/hermes-webui` exists as fork of nesquena/hermes-webui | ✅ PASS |
| 5 | All three repos visible under `fox-in-the-box-ai` org | ✅ PASS |
| 6 | Admin access confirmed (token has admin rights to all three) | ✅ PASS |

---

## Notes for Task 02

- **hermes-webui upstream default branch is `master`**, not `main`. Use `git submodule add -b master` for that submodule.
- GitHub token does NOT have `workflow` scope — GitHub Actions YAML files cannot be pushed via token. Task 08 agent must either: (a) push workflow files via a token with workflow scope, or (b) Stan adds workflow scope to the token before task 08 runs.
- Current repo state: docs + markdown files pushed. No pnpm scaffold, no packages/ directory, no submodules yet — all of that is Task 02.
- Remote URL in local repo uses token-embedded HTTPS — already configured at `origin`.
