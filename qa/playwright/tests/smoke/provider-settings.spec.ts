/**
 * Provider settings — /api/providers read endpoint.
 *
 * Tests the provider listing that the Settings UI and model picker
 * consume. A broken GET /api/providers means the model picker shows
 * no providers and the Settings UI can't render the provider list.
 *
 * POST /api/providers is provider-key-specific and needs a valid
 * provider name from the running instance — tested here only via
 * the GET shape contract.
 */
import { test, expect, request } from '@playwright/test';

test.describe('Provider settings', () => {
  test('GET /api/providers returns a provider list', async ({ baseURL }) => {
    const api = await request.newContext({ baseURL });
    const res = await api.get('/api/providers');
    expect(res.status(), '/api/providers must return 200').toBe(200);
    const body = await res.json();
    expect(Array.isArray(body), '/api/providers must return an array').toBe(true);
  });

  test('each provider has required display fields', async ({ baseURL }) => {
    const api = await request.newContext({ baseURL });
    const body = await (await api.get('/api/providers')).json();
    if (body.length > 0) {
      const first = body[0];
      expect(first, 'provider must have an id').toHaveProperty('id');
      expect(first, 'provider must have a display_name').toHaveProperty('display_name');
      expect(first, 'provider must have a has_key flag').toHaveProperty('has_key');
    }
  });
});
