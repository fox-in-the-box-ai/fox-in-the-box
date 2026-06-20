/**
 * Contract endpoint — GET /readyz (INSTANCE_CONTRACT §4.2).
 *
 * Fleet polls /readyz after provisioning to decide when an instance
 * is ready for traffic. A broken /readyz means Fleet either never
 * marks instances ready (stuck provisioning) or marks them ready
 * prematurely (users hit uninitialized state).
 */
import { test, expect, request } from '@playwright/test';

test.describe('Contract — /readyz', () => {
  test('returns 200 with JSON', async ({ baseURL }) => {
    const api = await request.newContext({ baseURL });
    const res = await api.get('/readyz');
    expect(res.status(), '/readyz must return 200').toBe(200);
    const ct = res.headers()['content-type'] || '';
    expect(ct, '/readyz must return JSON').toContain('application/json');
  });

  test('response has ready flag and checks object', async ({ baseURL }) => {
    const api = await request.newContext({ baseURL });
    const body = await (await api.get('/readyz')).json();
    expect(body, 'missing ready flag').toHaveProperty('ready');
    expect(typeof body.ready, 'ready must be boolean').toBe('boolean');
    expect(body, 'missing checks object').toHaveProperty('checks');
    expect(
      typeof body.checks,
      'checks must be an object (keyed by check name)',
    ).toBe('object');
  });

  test('each check entry has an ok boolean', async ({ baseURL }) => {
    const api = await request.newContext({ baseURL });
    const body = await (await api.get('/readyz')).json();
    for (const [name, check] of Object.entries(body.checks) as [string, any][]) {
      expect(check, `check "${name}" missing "ok" field`).toHaveProperty('ok');
      expect(typeof check.ok, `check "${name}" ok must be boolean`).toBe('boolean');
    }
  });

  test('http_server check is always ok', async ({ baseURL }) => {
    const api = await request.newContext({ baseURL });
    const body = await (await api.get('/readyz')).json();
    expect(
      body.checks,
      '/readyz must include an http_server check — if we got a 200 from /readyz, ' +
        'HTTP is obviously working, so this check validates self-consistency',
    ).toHaveProperty('http_server');
    expect(body.checks.http_server.ok, 'http_server check must be true').toBe(true);
  });
});
