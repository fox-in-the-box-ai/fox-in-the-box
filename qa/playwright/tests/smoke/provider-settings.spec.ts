/**
 * Provider settings — /api/providers read endpoint.
 *
 * Tests the provider listing that the Settings UI and model picker
 * consume. A broken GET /api/providers means the model picker shows
 * no providers and the Settings UI can't render the provider list.
 *
 * /api/providers is not in the onboarding whitelist — call
 * /api/setup/skip first to prevent 302 redirect when running in
 * parallel with tests that call /test/reset.
 */
import { test, expect, request } from '@playwright/test';

test.describe('Provider settings', () => {
  test('GET /api/providers returns a provider list', async ({ baseURL }) => {
    const api = await request.newContext({ baseURL });
    await api.post('/api/setup/skip');

    const res = await api.get('/api/providers');
    expect(res.status(), '/api/providers must return 200').toBe(200);
    const body = await res.json();
    expect(Array.isArray(body), '/api/providers must return an array').toBe(true);
  });

  test('each provider has required display fields', async ({ baseURL }) => {
    const api = await request.newContext({ baseURL });
    await api.post('/api/setup/skip');

    const body = await (await api.get('/api/providers')).json();
    if (body.length > 0) {
      const first = body[0];
      expect(first, 'provider must have an id').toHaveProperty('id');
      expect(first, 'provider must have a display_name').toHaveProperty('display_name');
      expect(first, 'provider must have a has_key flag').toHaveProperty('has_key');
    }
  });
});
