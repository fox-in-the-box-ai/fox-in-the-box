# Release Workflow

How a Fox in the Box release actually happens. Ship-on-demand cadence — typically several releases per day during active development, longer gaps during stabilization.

## Anti-regression rules (NON-NEGOTIABLE)

These five rules govern every release. They came out of the v0.4.7 / v0.5.0 stabilization pass after we'd shipped 7 releases that turned out to be untested.

1. **One large change per release.** Never ship a guardrail scaffold and a UI overhaul in the same version — if something breaks, you need to know which change caused it.
2. **48-hour soak after every tag.** Don't start the next phase for 48 hours. Use the soak to run the smoke checklist on the released binary and watch for user reports. The clock is calendar time, not "wait around" — verification work counts as productive use of the window.
3. **Regression test suite grows with every phase.** Each testing gate's checklist becomes a permanent regression checklist. By v0.8.0 it covers: clean install (3 platforms), onboarding wizard, PII masking, business rules, Llama Guard, UI rendering, Routines CRUD.
4. **Feature flags for everything new.** Every guard, every UI change, every routine is behind a toggle. If something breaks in production, disable it without a release.
5. **Stabilization pass before every minor version bump.** Before tagging x.Y.0 (v0.6.0, v0.7.0, v0.8.0), re-run the full smoke checklist plus all accumulated regression checks.

## Pre-release checklist

Before tagging anything:

- [ ] All issues for this release closed in GitHub
- [ ] PR merged to `main` with all the changes
- [ ] **`qa/SMOKE_CHECKLIST.md` run end-to-end against a fresh container built from `main`**
- [ ] CHANGELOG entry drafted in concise / sectioned style (see prior releases for tone — `Fixed`/`Added`/`What's next`)

## Cutting the release

Patch releases (v0.X.Y → v0.X.Y+1) and minor bumps (v0.X.0 → v0.X+1.0) follow the same flow.

```bash
# 1. Branch from main
git checkout main && git pull --ff-only
git checkout -b release/0.5.0

# 2. Bump version files
echo "0.5.0" > VERSION
# Edit packages/electron/package.json — change "version" field
# Edit CHANGELOG.md — add new section at top, copy your draft

# 3. Commit + push
git add VERSION packages/electron/package.json CHANGELOG.md
git commit -m "release: v0.5.0"
git push -u origin release/0.5.0

# 4. Open PR via gh CLI, admin-merge once CI is green
gh pr create --title "release: v0.5.0" --body "..."
gh pr merge <PR#> --squash --delete-branch --admin

# 5. Pull main, tag, push tag (the tag push triggers .github/workflows/release.yml)
git checkout main && git pull --ff-only
git tag v0.5.0
git push origin v0.5.0
```

The `release.yml` workflow runs automatically on tag push. It chains `build-container.yml` (multi-arch Docker → GHCR) and `build-electron.yml` (signed macOS DMGs + signed Windows exe) and creates the GitHub Release with the CHANGELOG entry as the body.

## Verifying the release

```bash
# Watch the pipeline
gh run watch --exit-status

# Confirm the 5 binaries
gh release view v0.5.0 --json assets -q '.assets[].name'
# Expected: arm64-mac.dmg, arm64-mac.zip, setup-x64.exe, x64-mac.dmg, x64-mac.zip
```

Then, **on the released binary** (not on local main):
- Download the macOS DMG from the GitHub Release page → install → launch → walk wizard → real chat
- Download the Windows .exe → install on a Windows box → SmartScreen accepts → launch → walk wizard → real chat
- For Linux: `curl -fsSL …/install.sh | bash` on a fresh Ubuntu VM (or Docker-in-Docker container with Docker installed)

Anything fails → file the bug, fix, ship a hotfix patch release. Don't start the next phase until the current release is clean.

## Rollback

If a release ships and is broken in a way the smoke checklist missed:

1. **Don't unpublish the release** (would break auto-update for users who already pulled it). Instead, ship a hotfix x.Y.Z+1 that supersedes it.
2. If the issue is severe (data loss, security), draft a GitHub Security Advisory and pin a notice on the README until the hotfix is out.
3. Update the smoke checklist with the missed scenario so future releases catch it.

## Where the configuration lives

| Concern | File |
|---|---|
| Version source of truth | `VERSION` (repo root) |
| Electron app version | `packages/electron/package.json` (must match `VERSION`) |
| Container build | `packages/integration/Dockerfile` |
| Multi-arch CI | `.github/workflows/build-container.yml` |
| Electron CI | `.github/workflows/build-electron.yml` |
| Release orchestration | `.github/workflows/release.yml` |
| Code signing config | `packages/electron/electron-builder.yml` |
| GitHub secrets needed | macOS: `CSC_LINK`, `CSC_KEY_PASSWORD`, `APPLE_ID`, `APPLE_APP_SPECIFIC_PASSWORD`, `APPLE_TEAM_ID`. Windows: `AZURE_TENANT_ID`, `AZURE_CLIENT_ID` (OIDC, no client secret) |

## Naming conventions

- **Branches:** `feat/description`, `fix/description`, `docs/description`, `release/X.Y.Z`, `qa/...`
- **Tags:** `vX.Y.Z` (no `release-` prefix, no underscores)
- **Commit messages:** Conventional Commits (`feat(scope): …`, `fix(scope): …`, `docs(scope): …`, `release: vX.Y.Z`)
- **Co-author lines:** **never** add `Co-authored-by` for AI tools. The repo's git identity must always be a human.

## Related

- [`qa/SMOKE_CHECKLIST.md`](../qa/SMOKE_CHECKLIST.md) — pre-release verification gate
- [`docs/DEV_MODE.md`](DEV_MODE.md) — local development with bind-mounted submodules (separate from release flow)
- [`CHANGELOG.md`](../CHANGELOG.md) — every shipped release with what changed and why
- [`CLAUDE.md`](../CLAUDE.md) — instructions for AI coding agents working in this repo
