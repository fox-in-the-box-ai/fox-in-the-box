/**
 * Global setup — Phase 0 stub.
 *
 * Phase 0 (v0.7.7): the smoke job in `.github/workflows/playwright.yml`
 * pre-starts a single container on port 8801 via `docker run`. This setup
 * file is a no-op stub that just verifies the container is reachable
 * before any specs run — fail fast if CI's container-start step silently
 * regressed.
 *
 * Phase 1+ (v0.7.8): replace with in-test orchestration:
 *   - Spin up 4 containers on ports 8801-8804 (one per shard)
 *   - Start mock servers (mocks/openrouter, mocks/ollama)
 *   - Reset each container's `/data` between specs via the `/test/reset` route
 *     (registered by `fox_overlay/webui_modules/test_hooks.py` when
 *     FITB_TEST_MODE=1)
 *
 * To enable in Phase 1, uncomment the `globalSetup` line in playwright.config.ts.
 */
import { FullConfig } from '@playwright/test';

async function globalSetup(config: FullConfig) {
  const baseURL = config.projects[0]?.use?.baseURL || 'http://localhost:8801';
  const url = `${baseURL.replace(/\/$/, '')}/health`;

  // Poll for up to 60s — container may still be coming up after `docker run`.
  const deadline = Date.now() + 60_000;
  let lastErr: unknown = null;
  while (Date.now() < deadline) {
    try {
      const res = await fetch(url);
      if (res.ok) {
        // eslint-disable-next-line no-console
        console.log(`[playwright] Container ready at ${baseURL}`);
        return;
      }
      lastErr = new Error(`HTTP ${res.status}`);
    } catch (e) {
      lastErr = e;
    }
    await new Promise((r) => setTimeout(r, 2000));
  }
  throw new Error(
    `[playwright] Container at ${baseURL} not ready after 60s. Last error: ${String(lastErr)}\n` +
      `Check that the CI workflow's "Start container" step succeeded, or run ` +
      `\`docker logs fitb-playwright\` locally.`,
  );
}

export default globalSetup;
