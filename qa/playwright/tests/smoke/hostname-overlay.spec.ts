/**
 * Hostname overlay — GET /api/settings/hostname and POST dismiss-prompt.
 *
 * The hostname prompt appears post-wizard. Fleet reads the hostname
 * to populate the instance name in the panel. A broken hostname
 * endpoint means Fleet shows "unknown" for newly provisioned instances.
 *
 * /api/settings/hostname is not in the onboarding whitelist — call
 * /api/setup/skip first to prevent 302 redirect when running in
 * parallel with tests that call /test/reset.
 */
import { test, expect, request } from '@playwright/test';

test.describe('Hostname overlay', () => {
  test('GET /api/settings/hostname returns state object', async ({ baseURL }) => {
    const api = await request.newContext({ baseURL });
    await api.post('/api/setup/skip');

    const res = await api.get('/api/settings/hostname');
    expect(res.status(), '/api/settings/hostname must return 200').toBe(200);
    const body = await res.json();
    expect(body, 'response must have a configured field').toHaveProperty('configured');
    expect(body, 'response must have an effective field').toHaveProperty('effective');
  });

  test('POST /api/settings/hostname/dismiss-prompt returns ok', async ({ baseURL }) => {
    const api = await request.newContext({ baseURL });
    await api.post('/api/setup/skip');

    const res = await api.post('/api/settings/hostname/dismiss-prompt', {
      data: {},
    });
    expect(
      res.status(),
      'POST /api/settings/hostname/dismiss-prompt must return 200 — dismissing the ' +
        'hostname prompt should always succeed',
    ).toBe(200);
  });
});
