# Fox in the Box — Cursor Development Instructions

This file governs how Cursor (and any AI coding agent) works in this repository.
Read it in full before writing any code.

---

## 1. Your Role

You are the **implementer**. You write code, tests, and config files.
You do NOT commit, push, or open PRs on your own.

A separate **Supervisor agent (Hermes)** reviews all changes before they are committed.
The workflow is: **you implement → Supervisor reviews → Supervisor commits**.

Do not bypass this. Do not `git push` under any circumstances.

**You MUST make a WIP draft commit** when you are done (see Section 6 — Signal Done).
This protects your work from being lost if the worktree directory is touched.
The Supervisor will amend the commit message and push.

---

## 2. Repository Layout

```
fox-in-the-box/             ← monorepo root
├── forks/
│   ├── hermes-agent/       ← git submodule (NousResearch/hermes-agent, pinned via packages/fox-overlay/versions.toml)
│   └── hermes-webui/       ← git submodule (nesquena/hermes-webui, pinned via packages/fox-overlay/versions.toml)
├── packages/
│   ├── integration/        ← Dockerfile, supervisord, entrypoint, default-configs
│   ├── electron/           ← Electron desktop app
│   ├── scripts/            ← install.sh, dev utilities
│   └── fox-overlay/        ← sibling overlay for hermes-{agent,webui} (v0.6.0 migration; phases 2-10 populate it)
├── docs/
│   ├── tasks/              ← One task doc per feature (your specs live here)
│   ├── archive/            ← Frozen design docs (REQUIREMENTS.md, ROADMAP.md)
│   └── GATEWAY.md, RESET.md, GETTING_STARTED.md, …
├── tests/
│   ├── integration/        ← Full-stack tests
│   ├── electron/           ← Electron unit tests (jest)
│   └── container/          ← Shell/bats tests
├── README.md               ← Live roadmap lives in README's Roadmap section
└── AGENTS.md               ← This file
```

Submodules are in `forks/`. Do not modify submodule content directly.
If you need to change `hermes-agent` or `hermes-webui`, say so explicitly in your output —
the Supervisor will handle the fork workflow.

**Docker image:** `packages/integration/Dockerfile` **COPY**s `forks/hermes-agent` and `forks/hermes-webui` into the image and runs `pip install` at **build** time. That is normal integration work (not “editing forks” in place). A local `docker build` **fails** if submodules are not checked out — run `git submodule update --init --recursive` first (CI already uses recursive submodules). Runtime entrypoint **does not** clone those repos from GitHub for production containers.

**Line endings:** `.gitattributes` keeps `packages/integration/**/*.sh` as **LF** so Windows checkouts do not break Linux shebangs inside Docker.

---

## 3. Git Worktrees

Each task runs in its own **git worktree** to keep work isolated.

```bash
# Supervisor creates the worktree for you before handing you the task:
git worktree add ../fitb-task-03 -b task/03-dockerfile

# You work inside that directory:
cd ../fitb-task-03

# When done, you signal completion. Supervisor reviews and commits.
# Supervisor merges back to main and removes the worktree.
```

Rules:
- One task = one worktree = one branch (`task/NN-short-name`)
- Never work on `main` directly
- Never switch branches inside a worktree
- Leave the worktree in a clean, buildable state when done

---

## 4. Task Workflow

For every task you receive:

1. **Read the task doc** (`docs/tasks/NN-taskname.md`) in full before writing any code
2. **Read `docs/archive/REQUIREMENTS.md`** — frozen design doc that captures the broader-system intent. Cross-check anything material against the current code; the design doc is from before v0.1 and many specifics have evolved.
3. **Write tests first** (TDD) — every acceptance criterion in the task doc maps to at least one test
4. **Make tests pass** — implement until all AC tests are green
5. **Self-review checklist** (before signalling done):
   - [ ] All acceptance criteria tests pass
   - [ ] No secrets, API keys, or credentials in any file
   - [ ] No hardcoded paths that differ between dev and container (`/data` not `~/whatever`)
   - [ ] Code follows existing patterns in the repo (check neighboring files first)
   - [ ] No `console.log` / `print` debug statements left in
   - [ ] `docker build` still succeeds if you touched anything in `packages/integration/`
6. **Signal done** — do these steps in order:
   a. Write `DONE.md` in the worktree root with:
      - What you implemented
      - How to run the tests
      - Any open issues or assumptions you made
      - Anything that needs Supervisor's attention
   b. **Make a WIP draft commit** (this is mandatory — not optional):
      ```bash
      git add -A
      git commit -m "WIP: task(NN) — pending supervisor review"
      ```
      This protects your work. The Supervisor will amend the message on approval.
      Do NOT `git push`. The Supervisor handles all pushes.

---

## 5. Testing Standards

### Python (backend, entrypoint logic)
```bash
pytest tests/ -v
```
- Use `pytest` + `unittest.mock` for mocking subprocesses and filesystem
- All `/api/setup/*` endpoints must have unit tests (see task 05)
- Test files: `tests/integration/test_*.py`

### JavaScript (Electron)
```bash
cd packages/electron && pnpm test
```
- Use `jest` for unit tests
- Mock `dockerode` — never require a live Docker daemon for unit tests
- Test files: `tests/electron/*.test.js`

### Shell (install scripts)
```bash
cd tests/container && bats test_install.bats
```
- Use `bats` (Bash Automated Testing System)
- Mock `docker`, `systemctl`, `uname` with shell stubs in `test_helpers/`

### Container smoke test
```bash
git submodule update --init --recursive
docker build -f packages/integration/Dockerfile -t fitb:test .
docker run -d --name fitb-test --cap-add=NET_ADMIN --device /dev/net/tun -p 127.0.0.1:8787:8787 fitb:test
sleep 20
curl -f http://localhost:8787/health
docker stop fitb-test && docker rm fitb-test
```
(First `/health` may take a few tens of seconds on a slow machine; Hermes is already in the image, so clone/pip-on-start is not the bottleneck.)

Coverage bar: every acceptance criterion from the task doc must have an automated test.
If a criterion is genuinely untestable automatically (UI layout, Tailscale auth), note it
in `DONE.md` with a manual verification step.

---

## 6. Code Style

- **Python**: no formatter enforced, but match the style in `forks/hermes-webui/` (the existing codebase)
- **JavaScript**: no bundler, no TypeScript, plain ES2020 modules in Electron
- **Shell**: `set -euo pipefail` at the top of every script, functions for repeated logic
- **Dockerfile**: multi-stage if it meaningfully reduces image size, otherwise single stage is fine
- Keep it simple. This is a v0.1 hackathon build — clean and working beats clever.

---

## 7. Secrets & Security

- Never write API keys, tokens, or passwords to any file in the repo
- Config templates use placeholder values: `YOUR_OPENROUTER_KEY_HERE`
- The file `packages/integration/default-configs/hermes.env.template` is a template — not a real env file
- `.gitignore` must cover: `*.env`, `hermes.env`, `*.key`, `.env.*`, `tailscale*.state`
- If a test needs a real key, use environment variables (`os.environ.get('OPENROUTER_KEY')`) and skip the test if unset

---

## 8. What to Do When Stuck

- **Ambiguous spec**: document your assumption in `DONE.md` and make a reasonable call — don't block
- **Upstream hermes-agent/webui behavior unclear**: read the source in `forks/`, note findings in `DONE.md`
- **Build fails in a way you can't fix**: note exact error in `DONE.md`, leave code in best state you can
- **Dependency missing from container**: add to Dockerfile, note the addition in `DONE.md`

Never delete tests to make the suite pass. Fix the code, not the tests.

---

## 9. Out of Scope (Do Not Touch)

- `forks/` submodule content — read-only for you
- `docs/archive/REQUIREMENTS.md` and `docs/archive/ROADMAP.md` — frozen design docs, do not edit. The live roadmap is the README's Roadmap section, maintained by Supervisor.
- `main` branch — Supervisor commits to main after review
- GitHub Actions secrets or org settings
- Any OAuth credentials or Tailscale auth tokens
