# Changelog

All notable changes to Fox in the Box are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.1.5] - 2026-05-04

This is the actual ship of the v0.1.4 work. The v0.1.4 tag exists in the repo but has no GitHub Release: when `release.yml` called `build-electron.yml` for that tag, GitHub's workflow validation rejected the call with `"requesting 'id-token: write', but is only allowed 'id-token: none'"`. The OIDC permission was declared at the called workflow's level but not granted at the calling job's `permissions:` block, so it defaulted to `none` and signing never ran.

### Added

- Windows installer (`fox-in-the-box-setup-x64.exe`) is now signed with Azure Trusted Signing under the Icemint LLC certificate profile. Microsoft Defender SmartScreen no longer blocks first launch with the "Windows protected your PC" dialog. (Originally targeted v0.1.4.)

### Fixed

- `release.yml`'s `wait-for-electron` job now grants `id-token: write`, allowing the called `build-electron.yml` to request the OIDC token needed by `azure/login@v2` and the Trusted Signing action when the workflow runs in `workflow_call` context.

[0.1.5]: https://github.com/fox-in-the-box-ai/fox-in-the-box/releases/tag/v0.1.5

## [0.1.4] - 2026-05-04

### Added

- Windows installer (`fox-in-the-box-setup-x64.exe`) is now signed with Azure Trusted Signing under the Icemint LLC certificate profile. Microsoft Defender SmartScreen no longer blocks first launch with the "Windows protected your PC" dialog.

[0.1.4]: https://github.com/fox-in-the-box-ai/fox-in-the-box/releases/tag/v0.1.4

## [0.1.3] - 2026-05-04

### Fixed

- Chat input's model dropdown now refreshes immediately after a provider key is saved or removed in Settings → Providers. Previously, adding an Anthropic (or other non-OpenRouter) key would update the server's model cache but leave the chat dropdown stale — users had to reload the page, and many didn't realize they needed to. Affected anyone routing through a provider added post-onboarding (#37).

### Added

- Tailscale device hostname is now configurable during install. `packages/scripts/install.sh` prompts for a name when Tailscale is part of the chosen access mode, defaulting to `fox-<adjective>` from a curated list (e.g. `fox-quick`, `fox-clever`). Honors `FOX_HOSTNAME` env var for non-interactive installs. Inputs are sanitized to lowercase letters/digits/hyphens, max 63 chars (#3).
- README rewritten for clarity: Windows and macOS desktop downloads are now the first install options (with the actual `.exe` and `.dmg` filenames), features described in plain language, and new FAQ / Support / Acknowledgments sections. Reset / clean-install procedures moved out to `docs/RESET.md` (#40).

### Changed

- README accuracy fixes: removed the incorrect "no signed macOS .dmg in releases" line — we ship signed and notarized DMGs (arm64 + x64) since v0.1.0.

[0.1.3]: https://github.com/fox-in-the-box-ai/fox-in-the-box/releases/tag/v0.1.3

## [0.1.2] - 2026-05-04

### Fixed

- Windows `.exe` now reliably ships with every release. The previous pipeline ran `build-electron.yml` twice on every tag push (once via the `tags:` trigger, once via `release.yml`'s `workflow_call`), causing concurrent uploaders to race on the same GitHub Release. The Windows asset lost the race and was dropped from v0.1.1.

### Changed

- Single-source-of-truth release uploads. `release.yml` is now the only workflow that writes assets to a GitHub Release. `build-electron.yml` only produces GitHub Actions artifacts; `release.yml` downloads them and publishes atomically.
- `release.yml` now refuses to publish a release with an empty body — fails fast if `CHANGELOG.md` has no matching version section.
- `release.yml` sets `fail_on_unmatched_files: true` so a missing artifact glob is a hard failure, not a silent success.
- `release.yml` runs in a `release-${{ github.ref }}` concurrency group so re-runs of the same tag never race themselves.

[0.1.2]: https://github.com/fox-in-the-box-ai/fox-in-the-box/releases/tag/v0.1.2

## [0.1.1] - 2026-05-04

### Fixed

- First-run chat unusable due to missing onboarding endpoint — wizard now writes the OpenRouter API key to `hermes.env` and marks onboarding complete (#28, #34)
- Wizard "Open Fox" button now actually applies the new key without a container restart — `hermes-gateway` and `hermes-webui` are wrapped in a script that re-sources `hermes.env` on every supervisord restart (#35)
- Product name now consistently rendered as "Fox in the Box" across the UI

### Added

- Manual `workflow_dispatch` trigger on `build-electron.yml` for on-demand smoke testing of Windows and macOS builds (#25)

[0.1.1]: https://github.com/fox-in-the-box-ai/fox-in-the-box/releases/tag/v0.1.1

## [0.1.0] - 2026-05-04

### Added

- Signed macOS DMG build in the Electron CI pipeline (#31)
- macOS DMG and ZIP artifacts included in GitHub Releases alongside Windows installer (#32)

### Fixed

- macOS notarization: `APPLE_TEAM_ID` is now passed explicitly to `@electron/notarize` instead of relying on env-var forwarding (#33)

[0.1.0]: https://github.com/fox-in-the-box-ai/fox-in-the-box/releases/tag/v0.1.0

## [0.0.2] - 2026-05-04

### Fixed

- Mobile: titlebar now visible for safe-area spacing; inner content hidden and border removed on narrow viewports
- Submodule sync: hermes-webui and hermes-agent now auto-synced to latest on every upstream commit

[0.0.2]: https://github.com/fox-in-the-box-ai/fox-in-the-box/releases/tag/v0.0.2

## [0.0.1] - 2026-05-04

Initial public release.

### Added

- Single Docker container bundling Hermes Agent, Hermes WebUI, mem0\_oss, Qdrant, Tailscale, and supervisord
- Browser-based onboarding wizard at `/setup` — enter your OpenRouter API key and Tailscale auth token with no terminal required
- Brave Search MCP integration available out of the box
- Persistent memory across sessions via local Qdrant vector store
- Automatic HTTPS and remote access via Tailscale Serve
- Electron desktop app for Windows (.exe installer) and macOS (.zip)
- Linux and macOS shell install scripts
- GitHub Actions CI/CD: container build to GHCR, Electron builds for Windows and macOS
- Data directory structure at `~/.foxinthebox` with `config/`, `data/`, and `cache/` separation
- MIT license

[0.0.1]: https://github.com/fox-in-the-box-ai/fox-in-the-box/releases/tag/v0.0.1
