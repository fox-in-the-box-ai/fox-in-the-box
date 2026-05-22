# Fox in the Box — Playwright E2E suite

Replacing the manual smoke checklist (`qa/SMOKE_CHECKLIST.md`) as the release gate over the v0.7.x cycle.

## Phase status

| Phase | Scope | Status |
|---|---|---|
| 0 | Infra: workflow + workspace + 1 trivial spec | v0.7.7 (shipped) |
| 1 partial | 5 of ~12 smoke specs (4 integration: endpoints sweep, /health deep, static-overlay assets, test-hooks safety + 1 mobile UI: avatar swap #299) | v0.7.8 + v0.7.10 |
| 1 full | Remaining specs: wizard flows + retry-panel + settings-persist + sentinel checks + .fox-removals — plus testid retrofit + smoke-job-becomes-required (#265) | v0.7.9+ |
| 2 | ~30 critical-path specs: failover/recovery/Ollama/Tailscale/fallback + Electron parity (#266) | deferred |

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

## File layout

```
qa/playwright/
├── package.json              workspace member, depends on @playwright/test
├── playwright.config.ts      workers/retries/reporter; project = "smoke" for Phase 0
├── global-setup.ts           Phase 0 stub (waits for /health); Phase 1+ adds orchestration
├── tests/
│   └── smoke/
│       └── health-loads.spec.ts   the one Phase 0 spec
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
| `electron-parity` | weekly cron Sun 04:00 UTC | macos + windows | ~8 min/OS |

`smoke` becomes a required check in Phase 1 — for Phase 0 it runs but isn't blocking, so we can iterate on the infrastructure without breaking everyone's PRs.

## See also

- [`docs/architecture/upstream-overlay.md`](../../docs/architecture/upstream-overlay.md) — overlay architecture
- [`qa/SMOKE_CHECKLIST.md`](../SMOKE_CHECKLIST.md) — the manual checklist Playwright is replacing
- Issue #263 — Playwright epic
- Issue #264 — Phase 0 spec (this work)
- Issue #265 — Phase 1 spec (next)
- Issue #266 — Phase 2 spec (deferred)
