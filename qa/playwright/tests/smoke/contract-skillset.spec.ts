/**
 * Contract endpoint — GET /skillset (INSTANCE_CONTRACT §4.6).
 *
 * In standalone mode (no skillset manifest loaded), /skillset returns
 * 404 with an error body. This is the correct default — Fleet injects
 * a skillset manifest at provision time. A non-404 here in standalone
 * mode means a stale manifest leaked into the container image.
 */
import { test, expect, request } from '@playwright/test';

test.describe('Contract — /skillset', () => {
  test('returns 404 when no skillset loaded (standalone default)', async ({ baseURL }) => {
    const api = await request.newContext({ baseURL });
    const res = await api.get('/skillset');
    expect(
      res.status(),
      '/skillset must return 404 in standalone mode — the container ships without ' +
        'a skillset manifest. 200 means a manifest file leaked into the image.',
    ).toBe(404);
  });

  test('404 response body has error field', async ({ baseURL }) => {
    const api = await request.newContext({ baseURL });
    const res = await api.get('/skillset');
    const ct = res.headers()['content-type'] || '';
    expect(ct, '/skillset 404 must return JSON, not HTML').toContain('application/json');
    const body = await res.json();
    expect(body, '404 body must have an error field').toHaveProperty('error');
  });
});
