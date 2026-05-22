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

## Cutting a release — two flows

Fox in the Box has two distinct release paths since v0.7.0. Pick based on what changed.

### Flow A — Fox-code release (overlay / Electron / packaging changed)

Use this when overlay code, Electron app, install scripts, container build, or any other Fox-owned code changed. Bumps the FITB version + ships DMG/exe/container/GitHub Release.

Per-release rule: bundle the change with the v0.7.5 pattern — one PR for the code change, a separate companion PR for release mechanics (VERSION + CHANGELOG + smoke row). Keeps reviews focused and lets the release-mechanics PR ride on the code PR's CI verdict.

```bash
# 1. Code PR (already merged at this point — example: PR #314 failover engine)

# 2. Branch for release mechanics
git checkout main && git pull --ff-only
git submodule update --init forks/hermes-webui
git checkout -b release/v0.7.6

# 3. Bump version files + CHANGELOG + smoke-checklist row
echo "0.7.6" > VERSION
# Edit packages/electron/package.json — bump "version" to match
# Edit CHANGELOG.md — add new ## [0.7.6] section at top with prose lead + sections
# Edit qa/SMOKE_CHECKLIST.md — add Section L row + update "Last updated:" line

# 4. Commit + push + PR
git add VERSION packages/electron/package.json CHANGELOG.md qa/SMOKE_CHECKLIST.md
git commit -m "release(v0.7.6): <theme> (release mechanics)"
git push -u origin release/v0.7.6
gh pr create --title "release(v0.7.6): <theme>" --body "..."

# 5. Once CI is green, merge + tag + push tag (the tag push triggers release.yml)
gh pr merge <PR#> --squash
git checkout main && git pull --ff-only
git submodule update --init forks/hermes-webui
git tag -a v0.7.6 -m "v0.7.6 — <theme>"
git push origin v0.7.6
```

The `release.yml` workflow runs automatically on tag push. It chains `build-container.yml` (multi-arch Docker → GHCR) and `build-electron.yml` (signed macOS DMGs + signed Windows exe) and creates the GitHub Release with the CHANGELOG entry as the body.

### Flow B — Option B upstream-only bump (since v0.7.0)

Use this when the only change is bumping a pinned upstream tag in `packages/fox-overlay/versions.toml` (typically via the auto-issue opened by `upstream-watch.yml`). The Fox VERSION does NOT bump; instead, `build-container.yml` auto-retags `:stable` to the new digest after merge.

```bash
# 1. Branch + bump
git checkout main && git pull --ff-only
git checkout -b bump/upstream-webui-vX.Y.Z

# 2. Update the submodule pointer
cd forks/hermes-webui && git fetch --tags && git checkout vX.Y.Z && cd ../..
# Update packages/fox-overlay/versions.toml — change `hermes_webui_tag`
# (or `hermes_agent_tag`) and add a history entry under `[meta]`.

# 3. Verify basis is clean
bash packages/fox-overlay/scripts/check-overlay-basis.sh

# 4. Commit + push + PR — PR title MUST start with `bump(upstream):`
git add forks/hermes-webui packages/fox-overlay/versions.toml
git commit -m "bump(upstream): webui vX.Y.W → vX.Y.Z (closes #NNN)"
git push -u origin bump/upstream-webui-vX.Y.Z
gh pr create --title "bump(upstream): webui vX.Y.W → vX.Y.Z (closes #NNN)" --body "..."

# 5. CI runs the Option B diff guard (.github/workflows/option-b-diff-guard.yml)
#    — fails the PR if the diff touches anything outside forks/hermes-* +
#    versions.toml. Once CI is green, squash-merge with the SAME `bump(upstream):`
#    subject — build-container.yml's merge job regexes the commit subject and
#    auto-bumps :stable on match.

gh pr merge <PR#> --squash --subject "bump(upstream): webui vX.Y.W → vX.Y.Z (closes #NNN)"
```

**No tag push, no GitHub Release, no DMG/exe rebuild for Option B.** `:stable` advances; users on the desktop app get the new container content on next launch. The Option B diff guard (since v0.7.5) prevents an unintended Fox-code change from sneaking through under a `bump(upstream):` subject — that protects against the original FITB#122 class of regression.

See [`docs/architecture/upstream-overlay.md`](architecture/upstream-overlay.md) → "Versioning policy (Option B)" for the design rationale.

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

### User-side rollback escape hatch (v0.7.5+)

Users stranded by a bad release before a hotfix lands can roll back manually via the `FITB_IMAGE` env override (no Fox-side work needed):

```bash
# install.sh user: roll back to a known-good prior tag
FITB_IMAGE=ghcr.io/fox-in-the-box-ai/cloud:v0.7.5 ./install.sh

# Electron app user (macOS): set the env var before launching
FITB_IMAGE=ghcr.io/fox-in-the-box-ai/cloud:v0.7.5 open -a "Fox in the Box"

# Windows: set FITB_IMAGE as a User environment variable, then relaunch
```

This is a self-service escape hatch — communicate the tag to roll back to in the hotfix's GitHub Release notes if a release goes sideways.

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

- **Branches:**
  - `feat/description` — Fox-code feature work
  - `fix/description` — bug fix
  - `docs/description` — docs-only change
  - `release/vX.Y.Z` — release-mechanics PR (Flow A)
  - `bump/upstream-<repo>-vX.Y.Z` — Option B upstream bump (Flow B)
  - `qa/...` — verification work
- **Tags:** `vX.Y.Z` (no `release-` prefix, no underscores)
- **Commit messages:** Conventional Commits (`feat(scope): …`, `fix(scope): …`, `docs(scope): …`, `release(vX.Y.Z): …`, `bump(upstream): …`)
  - The `bump(upstream): …` prefix is **load-bearing**: `build-container.yml`'s merge job regexes the subject line; the Option B diff guard workflow keys off the PR title. Don't use this prefix for anything other than upstream-pin bumps.
- **Co-author lines:** **never** add `Co-authored-by` for AI tools. The repo's git identity must always be a human.

## Related

- [`qa/SMOKE_CHECKLIST.md`](../qa/SMOKE_CHECKLIST.md) — pre-release verification gate
- [`docs/DEV_MODE.md`](DEV_MODE.md) — local development with bind-mounted submodules (separate from release flow)
- [`CHANGELOG.md`](../CHANGELOG.md) — every shipped release with what changed and why
- [`CLAUDE.md`](../CLAUDE.md) — instructions for AI coding agents working in this repo
