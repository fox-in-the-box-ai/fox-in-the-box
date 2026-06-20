/**
 * Onboarding API flow — /api/setup/* endpoints.
 *
 * Tests the onboarding lifecycle: welcome → skip → complete. Uses
 * /test/reset to guarantee fresh-install state. This flow is the
 * first thing every new user hits; a broken onboarding blocks
 * adoption entirely.
 *
 * Redirect behavior (/ → /setup before onboarding) is not tested
 * here — that check is inherently flaky in fullyParallel mode because
 * any parallel worker calling /test/reset resets global onboarding
 * state between our setup/skip and our page.goto.
 */
import { test, expect, request } from '@playwright/test';

test.describe('Onboarding API', () => {
  test('GET /api/setup/welcome returns welcome text', async ({ baseURL }) => {
    const api = await request.newContext({ baseURL });
    const resetRes = await api.post('/test/reset');
    expect(resetRes.status(), '/test/reset must return 200 — test infra broken otherwise').toBe(200);

    const res = await api.get('/api/setup/welcome');
    expect(res.status(), '/api/setup/welcome must return 200').toBe(200);
    const body = await res.json();
    expect(body, 'welcome response must have a text field').toHaveProperty('text');
    expect(typeof body.text, 'text must be a string').toBe('string');
  });

  test('POST /api/setup/skip returns ok', async ({ baseURL }) => {
    const api = await request.newContext({ baseURL });
    const resetRes = await api.post('/test/reset');
    expect(resetRes.status(), '/test/reset must return 200 — test infra broken otherwise').toBe(200);

    const res = await api.post('/api/setup/skip');
    expect(res.status(), '/api/setup/skip must return 200').toBe(200);
    const body = await res.json();
    expect(body, 'skip response must have ok=true').toHaveProperty('ok', true);
  });

  test('POST /api/setup/complete returns ok', async ({ baseURL }) => {
    const api = await request.newContext({ baseURL });
    const resetRes = await api.post('/test/reset');
    expect(resetRes.status(), '/test/reset must return 200 — test infra broken otherwise').toBe(200);

    const res = await api.post('/api/setup/complete');
    expect(res.status(), '/api/setup/complete must return 200').toBe(200);
    const body = await res.json();
    expect(body, 'complete response must have ok=true').toHaveProperty('ok', true);
  });
});
