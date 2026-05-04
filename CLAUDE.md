# CLAUDE.md — Fox in the Box Project Context

## What is this?
Fox in the Box is a self-hosted AI assistant (Electron desktop app + Docker container). It bundles Hermes Agent, Hermes WebUI, mem0, Qdrant, and Tailscale into a single Docker image with a native desktop wrapper for Windows/macOS.

## Repository Structure
- `packages/electron/` — Electron desktop app (Windows .exe + macOS .dmg)
- `packages/integration/` — Docker container build (Dockerfile, entrypoint.sh)
- `packages/scripts/` — Install scripts for Linux/macOS
- `forks/hermes-agent` — Git submodule: AI agent core (Python)
- `forks/hermes-webui` — Git submodule: Browser-based chat UI (Python + JS)
- `.github/workflows/` — CI/CD pipelines

## Key Config Files
- `packages/electron/electron-builder.yml` — Electron build config (signing, notarization, targets)
- `packages/electron/package.json` — Electron app dependencies and version
- `.github/workflows/build-electron.yml` — Builds Windows + macOS Electron apps
- `.github/workflows/build-container.yml` — Builds Docker container to GHCR
- `.github/workflows/release.yml` — Creates GitHub Release on tag push (calls build workflows)
- `VERSION` — Single source of truth for version number
- `CHANGELOG.md` — Keep a Changelog format

## Code Signing Setup
### macOS (Apple Developer ID)
- Cert: Developer ID Application — ELTEKS SOFT, TOV (Z6J8AVT9QK)
- GitHub Secrets: CSC_LINK, CSC_KEY_PASSWORD, APPLE_ID, APPLE_APP_SPECIFIC_PASSWORD, APPLE_TEAM_ID
- electron-builder handles signing + notarization via these env vars
- Team ID is also hardcoded in electron-builder.yml under mac.notarize.teamId

### Windows (Azure Artifact Signing — in progress)
- Entity: Icemint LLC (US)
- Azure Artifact Signing account created, identity validated
- Certificate profile pending setup
- Will use GitHub Actions integration via official Azure action

## Branching & Release Flow
- Feature/fix branches: `fix/description` or `feat/description`
- PR into `main` with issue reference: `closes #XX`
- Release: bump VERSION + package.json version, update CHANGELOG.md, commit, tag `vX.Y.Z`, push
- Tag push triggers release.yml → builds all platforms → creates GitHub Release

## Current State (as of v0.1.0)
- macOS DMG build with signing + notarization: ✅ working
- Windows .exe build: ✅ working (unsigned, Azure signing pending)
- Docker container build: ✅ working
- Release workflow with changelog: ✅ working

## Known Issues
- #28 (P0): "No LLM provider configured" — onboarding wizard doesn't persist API key. Root cause: `api/onboarding.py` referenced but missing in hermes-webui. Needs fix in forks/hermes-webui submodule.
- #13: Provider setup step needed in chat UI
- #11: First-run conversation flow in WebUI

## Brand vs Signing Entities
- Brand: Vulpy, Inc. (copyright, publisherName in electron-builder)
- macOS signing cert: ELTEKS SOFT, TOV
- Windows signing cert: Icemint LLC (Azure Artifact Signing)

## Commands
```bash
# Dev build (no signing)
cd packages/electron
CSC_IDENTITY_AUTO_DISCOVERY=false pnpm build

# Run locally
cd packages/electron
pnpm start

# Docker container
docker run -d --name fox-in-the-box -p 127.0.0.1:8787:8787 -v ~/.foxinthebox:/data ghcr.io/fox-in-the-box-ai/cloud:stable
```

## GitHub Organization
- Org: fox-in-the-box-ai
- Main repo: fox-in-the-box-ai/fox-in-the-box
- Submodule repos: fox-in-the-box-ai/hermes-agent, fox-in-the-box-ai/hermes-webui
