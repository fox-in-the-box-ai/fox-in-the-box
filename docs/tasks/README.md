# Fox in the Box — Task Orchestration Guide

**Audience:** Stan (human manager coordinating AI agent execution)
**Deadline:** v0.1.0 by May 3, 2026 PST
**Total tasks:** 9 — 1 human, 8 AI agents (task 05 split into 05a tests + 05b implementation)

---

## 1. Task Index

| # | File | Title | Executor | Status | Depends On | Unblocks |
|---|------|-------|----------|--------|------------|----------|
| 01 | [01-github-repo-setup.md](01-github-repo-setup.md) | GitHub Repository Setup | **Stan** | — | _(nothing)_ | 02 |
| 02 | [02-monorepo-scaffold.md](02-monorepo-scaffold.md) | Monorepo Scaffold | Agent | — | 01 | 03, 04, 05, 08 |
| 03 | [03-dockerfile.md](03-dockerfile.md) | Dockerfile & Container Build | Agent | — | 02 | 04, 05, 06, 07, 08 |
| 04 | [04-entrypoint.md](04-entrypoint.md) | Container Entrypoint Script | Agent | — | 03 | Integration test |
|| 05a | [05a-onboarding-wizard-tests.md](05a-onboarding-wizard-tests.md) | Onboarding Wizard — Tests | Agent | — | 02 + 03 | 05b |
|| 05b | [05b-onboarding-wizard-impl.md](05b-onboarding-wizard-impl.md) | Onboarding Wizard — Implementation | Agent | — | 05a approved | 06 |
| 06 | [06-electron-app.md](06-electron-app.md) | Electron Desktop App | Agent | — | 03 | Release |
| 07 | [07-install-scripts.md](07-install-scripts.md) | Install Scripts | Agent | — | 02 + 03 | Release |
| 08 | [08-github-actions.md](08-github-actions.md) | GitHub Actions CI/CD | Agent | — | 02 (write early); fully works after 03 + 06 | Release |

> **Note:** `08-github-actions.md` has not been written yet — create it before spawning Agent C.

---

## 2. Parallel Execution Map

```
01 (Stan) — ~15 min
 └─ 02 (Agent A) ─────────────────────────────────────────────────────────────
     │                                                                         │
     ├─ 03 (Agent B)  ← CRITICAL PATH                                         │
     │    ├─ 04 (Agent D) ─────────────────────┐                              │
     │    ├─ 05 (Agent E) ─────────────────────┼─ Integration smoke test      │
     │    ├─ 06 (Agent F) ──────┐              │                              │
     │    └─ 07 (Agent G) ──────┤              │                              │
     │                          │              │                              │
     └─ 08 (Agent C, write YAML now) ──────────┘──────────────────────────────┘
          └─ fully works after 03 + 06 ──► Release gate (06 + 07 + 08 all pass)
```

**Key insight:** Agent C can write all the GitHub Actions YAML as soon as the monorepo structure (02) is known. The workflows won't run green until 03 and 06 are done, but the YAML can be committed and reviewed early.

---

## 3. Stan vs Agent Split

| Task | Who | Why |
|------|-----|-----|
| 01 — GitHub repo setup | **Stan** | Requires GitHub account access, org settings, SSH keys, and branch protection rules. Can't delegate auth to an agent. 15 min max. |
| 02 — Monorepo scaffold | Agent | Mechanical: `pnpm init`, workspace config, directory structure, `.gitignore`. No secrets needed. |
| 03 — Dockerfile | Agent | Docker syntax, layer ordering, slim base selection. Well-defined spec in task doc. Critical path — spawn immediately after 02. |
| 04 — Entrypoint script | Agent | Bash scripting, first-run detection logic. Fully specified in task doc. |
| 05 — Onboarding wizard | Agent | HTML/JS + Python backend endpoints. Spec is detailed. Needs monorepo (02) and running container (03). |
| 06 — Electron app | Agent | Node/Electron + Docker Desktop detection logic. Container image name and flags come from 03. |
| 07 — Install scripts | Agent | Bash scripts for Linux/macOS. Needs monorepo layout (02) and container image tag from 03. |
| 08 — GitHub Actions | Agent | YAML-heavy. Structure comes from 02; workflows test and publish output of 03 + 06. Can draft early. |

---

## 4. Orchestration Instructions

### Task 01 — Stan does this himself

- Create GitHub org `fox-in-the-box-ai`
- Fork `hermes-agent` and `hermes-webui` into the org
- Create the main `fox-in-the-box` monorepo with `main` branch protection
- **Time cap: 15 minutes.** Do not overthink it — a bare repo with a README is enough to unblock 02.

---

### After 01 completes → Spawn Agent A (Task 02)

**Prompt Agent A with:**
- `REQUIREMENTS.md`
- `ROADMAP.md`
- `02-monorepo-scaffold.md`

Agent A must output a committed monorepo skeleton before anything else can proceed.

---

### After 02 completes → Spawn Agent B and Agent C in parallel

**Agent B — Task 03 (Dockerfile)** ← spawn first, this is the critical path
- Pass: `REQUIREMENTS.md`, `ROADMAP.md`, `02-monorepo-scaffold.md`, `03-dockerfile.md`

**Agent C — Task 08 (GitHub Actions)** ← can write YAML now
- Pass: `REQUIREMENTS.md`, `ROADMAP.md`, `02-monorepo-scaffold.md`, `08-github-actions.md`
- Agent C writes the workflow files and commits them. They won't pass CI until 03 + 06 land, but committing early surfaces issues early.

---

### After 03 completes → Spawn Agents D, E, F, G all at once

All four can run in parallel:

| Agent | Task | Context files |
|-------|------|---------------|
| D | 04 — Entrypoint | `REQUIREMENTS.md`, `ROADMAP.md`, `03-dockerfile.md`, `04-entrypoint.md` |
| E1 | 05a — Onboarding wizard tests | `REQUIREMENTS.md`, `ROADMAP.md`, `02-monorepo-scaffold.md`, `03-dockerfile.md`, `05a-onboarding-wizard-tests.md` |
| E2 | 05b — Onboarding wizard impl | `REQUIREMENTS.md`, `ROADMAP.md`, `02-monorepo-scaffold.md`, `03-dockerfile.md`, `05a-onboarding-wizard-tests.md`, `05b-onboarding-wizard-impl.md` |
| F | 06 — Electron app | `REQUIREMENTS.md`, `ROADMAP.md`, `03-dockerfile.md`, `06-electron-app.md` |
| G | 07 — Install scripts | `REQUIREMENTS.md`, `ROADMAP.md`, `02-monorepo-scaffold.md`, `03-dockerfile.md`, `07-install-scripts.md` |

> **05a → Supervisor review → 05b:** After Agent E1 writes the tests, Hermes (supervisor)
> reviews them before spawning Agent E2. Spawn E1 in parallel with D, F, G.
> Spawn E2 only after supervisor approval.

---

### Integration smoke test — when 04 AND 05 both pass their ACs

```bash
# Fresh container, no prior state
docker run --rm -it \
  -v $(pwd)/test-data:/data \
  -p 8787:8787 \
  ghcr.io/fox-in-the-box-ai/cloud:dev

# Expected: browser opens to /setup, wizard completes, chat works
```

This is the gate before calling the core product "working."

---

### Release gate — when 06 AND 07 AND 08 all pass their ACs

```
06 ✅  Electron app starts container, opens browser on Windows
07 ✅  install.sh works on Ubuntu 22.04 LTS
08 ✅  GitHub Actions: container built, Electron .exe artifact uploaded
```

When all three are green: **tag `v0.1.0`** — the release workflow in 08 fires automatically and
attaches the Windows `.exe` and macOS `.zip` to the GitHub Release.

---

## 5. Acceptance Gate

The project is **release-ready** when every item below is checked:

- [ ] Container builds in CI and passes the container smoke test
- [ ] Onboarding wizard completes end-to-end in a fresh container (no prior `/data`)
- [ ] Electron app detects Docker Desktop, starts the container, and opens the browser on Windows
- [ ] `install.sh` runs successfully on Ubuntu 22.04 LTS (tested in CI or a clean VM)
- [ ] GitHub Release `v0.1.0` has Windows `.exe` and macOS `.zip` attached as release assets
- [ ] Access URL (e.g. `https://<device>.tailnet-name.ts.net`) is reachable via Tailscale HTTPS and passes a basic PWA manifest check

All six must pass. No exceptions for v0.1.0.

---

## 6. Context Files for Each Agent

Pass these files when spawning each agent. More context = fewer wrong assumptions.

| Agent | Task | Always include | Also include |
|-------|------|----------------|--------------|
| A | 02 — Monorepo scaffold | `REQUIREMENTS.md`, `ROADMAP.md` | _(just the task doc)_ |
| B | 03 — Dockerfile | `REQUIREMENTS.md`, `ROADMAP.md` | `02-monorepo-scaffold.md` |
| C | 08 — GitHub Actions | `REQUIREMENTS.md`, `ROADMAP.md` | `02-monorepo-scaffold.md` |
| D | 04 — Entrypoint | `REQUIREMENTS.md`, `ROADMAP.md` | `02-monorepo-scaffold.md`, `03-dockerfile.md` |
| E | 05 — Onboarding wizard | `REQUIREMENTS.md`, `ROADMAP.md` | `02-monorepo-scaffold.md`, `03-dockerfile.md` |
| F | 06 — Electron app | `REQUIREMENTS.md`, `ROADMAP.md` | `03-dockerfile.md` |
| G | 07 — Install scripts | `REQUIREMENTS.md`, `ROADMAP.md` | `02-monorepo-scaffold.md`, `03-dockerfile.md` |

**Rationale for extras:**
- Agents 03+: need the monorepo layout to know where to put files
- Agent E (onboarding wizard): needs `03-dockerfile.md` to understand how the webui server is structured inside the container — specifically what Python server framework is used and how static files are served
- Agent F (Electron app): needs `03-dockerfile.md` to get the exact container image name (`ghcr.io/fox-in-the-box-ai/cloud:stable`), port (`8787`), volume mount path (`~/.foxinthebox`), and required `--cap-add` flags

---

## Quick Reference — Agent Spawn Order

```
[Now]          Stan does Task 01

[+15 min]      Spawn Agent A → Task 02

[A done]       Spawn Agent B → Task 03  (CRITICAL PATH — do this first)
               Spawn Agent C → Task 08  (can write YAML in parallel)

[B done]       Spawn Agent D  → Task 04  ─┐
               Spawn Agent E1 → Task 05a ─┤  all four in parallel
               Spawn Agent F  → Task 06  ─┤
               Spawn Agent G  → Task 07  ─┘

[E1 done]      Supervisor reviews tests → approve → Spawn Agent E2 → Task 05b

[D + E2 done]   Run integration smoke test

[F + G + C done, 08 green]   Tag v0.1.0 → release fires automatically
```
