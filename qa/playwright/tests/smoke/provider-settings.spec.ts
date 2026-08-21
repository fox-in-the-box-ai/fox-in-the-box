/**
 * Provider settings — /api/providers read endpoint.
 *
 * Tests the provider listing that the Settings UI and model picker
 * consume. A broken GET /api/providers means the model picker shows
 * no providers and the Settings UI can't render the provider list.
 *
 * Response shape (upstream hermes-webui api/providers.py):
 *   { providers: [{id, display_name, has_key, configurable, ...}], active_provider: string }
 *
 * /api/providers is not in the onboarding whitelist — tests go
 * through getProvidersJson below, which re-skips onboarding before
 * each attempt to survive parallel tests calling /test/reset.
 */
import { test, expect, request } from '@playwright/test';
import type { APIRequestContext } from '@playwright/test';

/**
 * skip + GET with retry: a parallel test calling /test/reset between our
 * /api/setup/skip and the GET flips the app back into onboarding, and the
 * GET 302s to the onboarding HTML page. Re-skipping immediately before
 * each attempt narrows the window; the last attempt asserts status so a
 * real endpoint break fails with the status, not a JSON SyntaxError.
 */
async function getProvidersJson(api: APIRequestContext) {
  let res;
  for (let attempt = 0; attempt < 3; attempt++) {
    await api.post('/api/setup/skip');
    res = await api.get('/api/providers');
    if (res.status() === 200) return res.json();
  }
  expect(res!.status(), '/api/providers must return 200').toBe(200);
  return res!.json();
}

test.describe('Provider settings', () => {
  test('GET /api/providers returns provider object with list', async ({ baseURL }) => {
    const api = await request.newContext({ baseURL });

    const body = await getProvidersJson(api);
    expect(body, 'response must have a providers key').toHaveProperty('providers');
    expect(Array.isArray(body.providers), 'providers must be an array').toBe(true);
  });

  test('each provider has required display fields', async ({ baseURL }) => {
    const api = await request.newContext({ baseURL });

    const body = await getProvidersJson(api);
    const providers = body.providers;
    if (providers.length > 0) {
      const first = providers[0];
      expect(first, 'provider must have an id').toHaveProperty('id');
      expect(first, 'provider must have a display_name').toHaveProperty('display_name');
      expect(first, 'provider must have a has_key flag').toHaveProperty('has_key');
    }
  });
});
