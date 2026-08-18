# Fox in the Box — Playwright E2E suite

Replacing the manual smoke checklist (`qa/SMOKE_CHECKLIST.md`) as the release gate over the v0.7.x cycle.

## Suite status (as of v0.7.60)

**57 tests across 18 smoke spec files** plus a 1-test `release` project. The smoke suite covers contract endpoints (capabilities, endpoints-sweep, readyz, skillset, version), Fox branding, hostname overlay, model picker, onboarding API, provider settings, wizard flows (renders + local-fallback), health (basic + deep), static overlay assets, mobile avatar, and test-hook safety. Historical phase plan (0 → 1 partial → 1 full, #263–#266): shipped through the v0.7.x cycle; Phase 2's Electron-parity specs remain the open deferral (the CI `electron-parity` job is still a Phase 0 stub).

## Run locally

Requires Docker + Node ≥ 20 + pnpm ≥ 9.

```bash
# One-time: install browsers (~250 MB, chromium only for the smoke project)
pnpm --filter @fox-in-the-box/playwright test:e2e:install-browsers

# Start the test container (Phase 0 uses one container; Phase 2 will use four)
docker run -d --name fitb-playwright \
  --cap-add=NET_ADMIN --device /dev/net/tun \
  --sysctl net.ipv4.ip_forward=1 \
  -e FITB_TEST_MODE=1 \
  -p 127.0.0.1:8801:8787 \
  -v fitb-playwright-data:/data \
  ghcr.io/fox-in-the-box-ai/cloud:stable

# Run the smoke project (~30s when the container is already up)
pnpm --filter @fox-in-the-box/playwright test:e2e:smoke

# Teardown
docker stop fitb-playwright && docker rm fitb-playwright && docker volume rm fitb-playwright-data
```

## Required CI checks

`smoke` and `validate` are **enforced required status checks** on `main` (flipped shortly after v0.7.15; the deferral pattern that let #331 ship broken for 6 releases is what forced it). Every PR must pass both before merge.

## File layout

```
qa/playwright/
├── package.json              workspace member, depends on @playwright/test
├── playwright.config.ts      workers/retries/reporter; project = "smoke" for Phase 0
├── global-setup.ts           Phase 0 stub (waits for /health); Phase 1+ adds orchestration
├── tests/
│   ├── smoke/                18 spec files, 57 tests (contract-*,
│   │                         fox-branding, health-*, hostname-overlay,
│   │                         mobile-avatar, model-picker, onboarding-api,
│   │                         provider-settings, static-overlay,
│   │                         test-hooks-safety, wizard-*, endpoints-sweep)
│   └── release/
│       └── memory-state.spec.ts   release project — /readyz memory component
├── mocks/
│   ├── openrouter.ts         Phase 1 entry point — OpenRouter SSE + key responses
│   └── ollama.ts             Phase 1 entry point — Ollama daemon probe + tags
└── README.md
```

## Test-only routes inside the container

When the container is run with `FITB_TEST_MODE=1`, Fox's overlay registers
additional `/test/*` routes (see `packages/fox-overlay/fox_overlay/webui_modules/test_hooks.py`).
These let Playwright reset state between specs and drive deterministic
internal states. **Never enabled in production** — the module's `apply()`
checks the env var and bails when not set.

## CI

`.github/workflows/playwright.yml` runs three jobs:

| Job | Trigger | Matrix | Budget |
|---|---|---|---|
| `smoke` | PR | chromium only | ~5 min |
| `full` | nightly cron 04:00 UTC | chromium + firefox + webkit × 4 shards | ~12 min/shard |
| `electron-parity` | weekly cron Sun 04:00 UTC | macos + windows | ~1 min/OS (Phase 0 stub) |

`electron-parity` is a **Phase 0 stub**: it verifies Playwright installs and lists tests on the macOS/Windows runners — it does not launch the Electron app (real parity specs are the open Phase 2 deferral). The `windows-real-smoke` workflow is likewise v1 container-only. `smoke` and `validate` are enforced required checks (see above).

### The `release` project

`playwright.config.ts` registers a `release` project (testDir `./tests/release`) only when `FITB_RELEASE_E2E` is set. Run at release time against the candidate image:

```bash
FITB_RELEASE_E2E=1 pnpm exec playwright test --project=release
```

## See also

- [`docs/architecture/upstream-overlay.md`](../../docs/architecture/upstream-overlay.md) — overlay architecture
- [`qa/SMOKE_CHECKLIST.md`](../SMOKE_CHECKLIST.md) — the manual checklist Playwright is replacing
- Issue #263 — Playwright epic
- Issue #264 — Phase 0 spec (this work)
- Issue #265 — Phase 1 spec (next)
- Issue #266 — Phase 2 spec (deferred)
