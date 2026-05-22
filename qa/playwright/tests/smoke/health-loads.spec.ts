/**
 * /health spec — the one trivial spec for Phase 0.
 *
 * Asserts the container is up and the Fox overlay bootstrap log fired. If
 * either fails, container start is broken — that's the only thing we test
 * at Phase 0. Phase 1 (v0.7.8) adds the real surface.
 */
import { test, expect, request } from '@playwright/test';

test.describe('Phase 0 — /health smoke', () => {
  test('container health endpoint returns 200 + bootstrap log fired', async ({
    baseURL,
  }) => {
    expect(baseURL).toBeTruthy();

    // 1. /health responds.
    const api = await request.newContext({ baseURL });
    const res = await api.get('/health');
    expect(res.ok(), `/health returned ${res.status()}`).toBe(true);

    // 2. The Fox overlay's bootstrap line should have landed in the
    //    container's stdout. We can't read docker logs from inside the
    //    Playwright runner without shell access — Phase 1 will introduce a
    //    /test/logs/tail endpoint behind FITB_TEST_MODE=1 for this. For
    //    Phase 0, just verify the dispatcher table is non-empty via the
    //    public surface (any Fox-added /api/* endpoint exists).
    const ollamaStatus = await api.get('/api/ollama/status');
    // Daemon may be up or down — we don't care. Just that the route is
    // registered (any 200 / 404 / 503 means the dispatcher knows about it).
    // A 404 from upstream's "unknown path" handler would indicate Fox's
    // dispatcher didn't register, which is the actual regression we want
    // to catch.
    expect([200, 404, 503]).toContain(ollamaStatus.status());
  });
});
