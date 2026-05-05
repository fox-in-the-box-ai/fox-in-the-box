# Changelog

All notable changes to Fox in the Box are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.3.0] - 2026-05-05

The "Smoother onboarding + first taste of local" release. Clears both of v0.2.0's "Coming soon" promises and adds first-class local Ollama support so users with Ollama already installed can chat without an API key, without a terminal, without a custom-endpoint config.

### Added

- **First-class local Ollama integration.** Settings → Providers gets a new **Local Ollama** tile that auto-detects a host-side Ollama daemon (probing `host.docker.internal:11434` then `localhost:11434`, 10s cache), lists installed models from `/api/tags` with parameter size, quantization, and disk size, and offers a one-click **"Use"** button per model. Picking a model writes `model.{provider:custom, base_url, name}` into `config.yaml` and triggers the gateway hot-reload pattern from v0.2.0 — no API key, no terminal, no manual configuration. Routes through Hermes Agent's existing custom OpenAI-compat endpoint path; no agent-side changes. Closes #66 (phases 1 and 2; phase 3 — pull/delete model UI — tracked as #67 for v0.3.1).

- **Local Ollama fast-path on the onboarding wizard.** When a host-side Ollama daemon is detected with at least one model installed, the wizard's Welcome step surfaces a green-bordered "Local model detected" panel with a **"Use <model name>"** CTA. Click → activates the model server-side → marks onboarding complete → drops the user straight into chat. No API key step. Falls back to the existing OpenRouter wizard when Ollama isn't detected. Part of #11.

- **Skip CTA on every onboarding step.** `POST /api/setup/skip` marks onboarding complete without collecting an API key — exit hatch for users who'll configure providers later from Settings, or who already have keys persisted from a prior install. Closes the "User can skip onboarding entirely" AC of #11.

- **Externalized onboarding welcome text.** The wizard's Welcome paragraph(s) are now read from `/data/config/onboarding.md` (default copy ships from the container's defaults sweep). Edit the file in place to customize the greeting per install. New `GET /api/setup/welcome` endpoint serves the content. Closes the "Script is externalized" AC of #11.

- **Tailscale device hostname customization in Settings.** A new **Device name (Tailscale)** field in Settings → System lets desktop-app users pick a friendly name for their Fox on their tailnet — no longer stuck with Tailscale's auto-generated `ip-x-x-x-x` hostnames in the HTTPS URL Tailscale Serve publishes. The field defaults to a `fox-<adjective>` from the same curated list `install.sh` uses (parity with the v0.1.3 shell-install fix from #3). Persists `FOX_HOSTNAME` to `/data/config/hermes.env` and applies live via `tailscale set --hostname=<sanitized>` against the running daemon — surgical `EditPrefs` mutation, not the full-preferences-reset risk of `tailscale up`. After applying, re-reads `tailscale status --json` and surfaces any collision suffix the control plane appended. If the daemon isn't running or authenticated yet (common at first run), the persist is a soft-success — the value applies on the next daemon start. Closes #44. Wizard-step refinement tracked separately as #68.

- **Linux Docker host networking.** `packages/electron/src/docker-manager.js` (Dockerode `HostConfig.ExtraHosts`) and `packages/scripts/install.sh` now add `--add-host=host.docker.internal:host-gateway` so the local-Ollama probe (and any future host-reaching code) works on Linux Docker Engine 20.10+. macOS / Windows Docker Desktop resolves this name natively; Linux Engine takes `host-gateway` as a placeholder for the host's gateway address.

### Fixed

- **Onboarding state drift.** `onboarding.json:completed` and `settings.json:onboarding_completed` were two unsynchronized flags — the redirect middleware read only the first, and any code path flipping the second was silently ignored. `/api/setup/{complete,skip}` now write both, and `onboarding_complete()` reads either. Future CLI / direct-config bootstrappers can flip either flag and the redirect agrees.

### Caveats

- **Local Ollama on existing v0.2.x containers.** The Linux `--add-host` flag was added to the container creation flow in this release. Containers created before v0.3.0 don't have it — the Local Ollama tile will show "Not detected" on Linux until the container is re-created. macOS / Windows Docker Desktop is unaffected. Surfaced inline in the Local Ollama tile's not-detected copy.

- **Live Tailscale hostname mutation requires an authenticated daemon.** If you set the device name before authenticating Tailscale (or with the daemon stopped), the value still persists to `hermes.env` and applies on the next daemon start. The Settings UI surfaces this distinction in its status line.

[0.3.0]: https://github.com/fox-in-the-box-ai/fox-in-the-box/releases/tag/v0.3.0

## [0.2.0] - 2026-05-04

The "App works out of the box" release. The first-launch flow now closes itself when services are healthy, post-onboarding key changes take effect without a container restart, and the release pipeline pins images by content digest so a tagged version is reproducible.

### Fixed

- **Setup window stuck at Step 5/6 — Wait for services.** The Electron `/health` probe in `packages/electron/src/health-check.js` accepted any HTTP 200 and discarded the body, while the in-container probe (`forks/hermes-webui/bootstrap.py:wait_for_health`) requires the body to contain `"status": "ok"`. Same endpoint, two different success criteria — and when those gates disagreed, the setup window hung at 5/6 even when curl returned a healthy response. Polling now reads the body (4KB cap) and requires both the 200 and the marker. Closes #57 (also closed #56 as a duplicate).

### Added

- **Provider keys can be added or changed after onboarding.** Users can now open Settings → Providers from the chat (gear icon → Settings → Providers tab) to add or remove API keys for Anthropic, OpenAI, OpenRouter, DeepSeek, and other supported providers. The change takes effect within seconds — no container restart needed. Two coordinated fixes:
  - `packages/integration/scripts/run-with-env.sh` now sources `$HOME/.hermes/.env` in addition to `/data/config/hermes.env`. The wizard writes to the first; Settings writes to the second; the wrapper sources both so either path's keys end up in the gateway's process env.
  - `forks/hermes-webui` (now at `98eb7d9`) — `api/providers.py:set_provider_key` best-effort calls `supervisorctl restart hermes-gateway` after writing the env file. No-op outside supervisor-managed deployments. Closes #13.

### Changed

- **Release pipeline pins the container image by content digest.** `release.yml` previously did `docker pull :latest && docker tag :vX.Y.Z`. A concurrent push to `main` between `wait-for-container`'s push and this pull could mutate `:latest`, leaving the released `:vX.Y.Z` / `:stable` tags pointing at a different commit's image than the tagged one. `build-container.yml` now exposes the pushed image's content digest as a `workflow_call` output, and `release.yml` pulls / retags `name@sha256:...` so the released image is verifiably the one this run produced. Fails fast if the digest is missing. Closes #41 (and #43, which described the same race from a different angle — the digest pin makes the prescribed `tags:` trigger redundant; adding that trigger would create the duplicate parallel build pattern that broke v0.1.1's Windows asset upload).

- **CI: documented why Windows installs Electron deps with `npm`, not `pnpm`.** `build-electron.yml` uses `npm install` on Windows runners while macOS/Linux use `pnpm install --frozen-lockfile` at the workspace root. The divergence is load-bearing: pnpm's content-addressed store nests deps under `node_modules/.pnpm/<name>@<ver>_<longhash>/...` which exceeds Windows MAX_PATH (260) for makensis.exe's NSIS include resolver. The earlier attempt with `--shamefully-hoist` (4510cc5) still produced unreachable include paths, and `cache: "pnpm"` for setup-node was likewise removed (4550e94) because the cache path doesn't exist when npm is used. Added an inline comment so the next person doesn't try to "fix" it back to pnpm and break Windows installer builds. Closes #42.

[0.2.0]: https://github.com/fox-in-the-box-ai/fox-in-the-box/releases/tag/v0.2.0

## [0.1.6] - 2026-05-04

This is the actual ship of the signed Windows installer that v0.1.4 and v0.1.5 attempted. Both prior tags are orphans — neither has a published GitHub Release. The chain of failures and what unblocked them:

- **v0.1.4** failed because `release.yml`'s caller didn't grant `id-token: write` to the `wait-for-electron` job; the called workflow's permissions inherit from the caller, not from its own declaration. Fixed in #52.
- **v0.1.5** failed because the Azure federated credential was set up with subject `repo:.../ref:refs/tags/v*` — the asterisk is treated as a literal string, not a wildcard. Microsoft's standard FICs don't support pattern matching on tag names by design.

### Added

- Windows installer (`fox-in-the-box-setup-x64.exe`) is now signed with Azure Trusted Signing under the Icemint LLC certificate profile (`fitb-exe-signing`). Microsoft Defender SmartScreen no longer blocks first launch with the "Windows protected your PC" dialog. (Originally targeted v0.1.4.)

### Changed

- Windows signing now uses GitHub Environment-bound federated credentials (subject `repo:.../environment:release`) instead of tag-pattern matching. Microsoft's recommended pattern for "many tags" releases — independent of the tag name, so every future release works without per-tag Azure setup. `build-electron.yml` accepts a `signing-environment` workflow_call input; `release.yml` passes `release`. Push-to-main and `workflow_dispatch` builds skip Azure login + signing entirely (no auth attempt, faster CI).

[0.1.6]: https://github.com/fox-in-the-box-ai/fox-in-the-box/releases/tag/v0.1.6

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
