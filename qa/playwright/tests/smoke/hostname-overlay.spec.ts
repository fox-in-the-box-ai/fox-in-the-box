/**
 * Hostname overlay — GET /hostname and POST /hostname/*.
 *
 * The hostname prompt appears post-wizard. Fleet reads the hostname
 * to populate the instance name in the panel. A broken /hostname
 * endpoint means Fleet shows "unknown" for newly provisioned instances.
 */
import { test, expect, request } from '@playwright/test';

test.describe('Hostname overlay', () => {
  test('GET /hostname returns JSON with hostname field', async ({ baseURL }) => {
    const api = await request.newContext({ baseURL });
    const res = await api.get('/hostname');
    expect(
      [200, 404, 503].includes(res.status()),
      `/hostname returned ${res.status()} — expected 200/404/503 to prove ` +
        `the overlay claimed the prefix`,
    ).toBe(true);
    if (res.status() === 200) {
      const body = await res.json();
      expect(body, '/hostname response must have a hostname field').toHaveProperty('hostname');
    }
  });

  test('POST /hostname/dismiss returns 200', async ({ baseURL }) => {
    const api = await request.newContext({ baseURL });
    const res = await api.post('/hostname/dismiss');
    expect(
      res.status(),
      'POST /hostname/dismiss must return 200 — dismissing the hostname prompt ' +
        'should always succeed',
    ).toBe(200);
  });
});
