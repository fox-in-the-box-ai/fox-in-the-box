/**
 * Onboarding API flow — /api/setup/* endpoints.
 *
 * Tests the onboarding lifecycle: welcome → skip → complete. Uses
 * /test/reset to guarantee fresh-install state. This flow is the
 * first thing every new user hits; a broken onboarding blocks
 * adoption entirely.
 */
import { test, expect, request } from '@playwright/test';

test.describe('Onboarding API', () => {
  test('GET /api/setup/welcome returns welcome data', async ({ baseURL }) => {
    const api = await request.newContext({ baseURL });
    await api.post('/test/reset');

    const res = await api.get('/api/setup/welcome');
    expect(res.status(), '/api/setup/welcome must return 200').toBe(200);
    const body = await res.json();
    expect(body, 'welcome response must have a status field').toHaveProperty('status');
  });

  test('POST /api/setup/skip marks onboarding skipped', async ({ baseURL }) => {
    const api = await request.newContext({ baseURL });
    await api.post('/test/reset');

    const res = await api.post('/api/setup/skip');
    expect(
      res.status(),
      '/api/setup/skip must return 200 — users who skip the wizard should ' +
        'land in the chat UI without errors',
    ).toBe(200);
  });

  test('POST /api/setup/complete marks onboarding done', async ({ baseURL }) => {
    const api = await request.newContext({ baseURL });
    await api.post('/test/reset');

    const res = await api.post('/api/setup/complete');
    expect(res.status(), '/api/setup/complete must return 200').toBe(200);
  });

  test('after complete, / no longer redirects to /setup', async ({ page, baseURL }) => {
    const api = await request.newContext({ baseURL });
    await api.post('/test/reset');
    await api.post('/api/setup/skip');

    await page.goto('/', { waitUntil: 'domcontentloaded' });
    expect(
      page.url(),
      'After onboarding is marked complete, / must NOT redirect to /setup. ' +
        'If it still redirects, the onboarding completion flag is not being read ' +
        'by the redirect middleware.',
    ).not.toMatch(/\/setup$/);
  });
});
