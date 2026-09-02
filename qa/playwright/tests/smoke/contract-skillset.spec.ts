/**
 * Contract endpoint — GET /skillset (INSTANCE_CONTRACT §4.6).
 *
 * Returns the active skillset manifest summary (200) or 404 when no
 * skillset is loaded. In standalone mode the default is 404; in managed
 * mode Fleet injects a manifest at provision time.
 *
 * /skillset is not in the onboarding whitelist — requests go through
 * the shared onboarding helper (#779) to survive parallel tests that
 * call /test/reset.
 */
import { test, expect, request } from '@playwright/test';
import { getSkippingOnboarding } from '../helpers/onboarding';

test.describe('Contract — /skillset', () => {
  test('returns 200 or 404 with JSON', async ({ baseURL }) => {
    const api = await request.newContext({ baseURL });
    const res = await getSkippingOnboarding(api, '/skillset', [200, 404]);
    const status = res.status();
    expect(
      [200, 404].includes(status),
      `/skillset returned ${status} — expected 200 (manifest loaded) or 404 (standalone)`,
    ).toBe(true);
    const ct = res.headers()['content-type'] || '';
    expect(ct, '/skillset must return JSON, not HTML').toContain('application/json');
  });

  test('response body has expected shape', async ({ baseURL }) => {
    const api = await request.newContext({ baseURL });
    const res = await getSkippingOnboarding(api, '/skillset', [200, 404]);
    expect([200, 404], '/skillset must return 200 or 404').toContain(res.status());
    const body = await res.json();
    if (res.status() === 200) {
      expect(body, '200 response must have a name field').toHaveProperty('name');
    } else {
      expect(body, '404 response must have an error field').toHaveProperty('error');
    }
  });
});
