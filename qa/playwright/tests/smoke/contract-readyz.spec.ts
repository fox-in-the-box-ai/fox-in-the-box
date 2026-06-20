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

  test('response has ready flag and checks array', async ({ baseURL }) => {
    const api = await request.newContext({ baseURL });
    const body = await (await api.get('/readyz')).json();
    expect(body, 'missing ready flag').toHaveProperty('ready');
    expect(typeof body.ready, 'ready must be boolean').toBe('boolean');
    expect(body, 'missing checks array').toHaveProperty('checks');
    expect(Array.isArray(body.checks), 'checks must be an array').toBe(true);
  });

  test('each check has name, ok, and detail fields', async ({ baseURL }) => {
    const api = await request.newContext({ baseURL });
    const body = await (await api.get('/readyz')).json();
    for (const check of body.checks) {
      expect(check, `check missing "name": ${JSON.stringify(check)}`).toHaveProperty('name');
      expect(check, `check missing "ok": ${JSON.stringify(check)}`).toHaveProperty('ok');
      expect(check, `check missing "detail": ${JSON.stringify(check)}`).toHaveProperty('detail');
      expect(typeof check.ok, `check "${check.name}" ok must be boolean`).toBe('boolean');
    }
  });

  test('http_server check is always ok', async ({ baseURL }) => {
    const api = await request.newContext({ baseURL });
    const body = await (await api.get('/readyz')).json();
    const httpCheck = body.checks.find((c: { name: string }) => c.name === 'http_server');
    expect(
      httpCheck,
      '/readyz must include an http_server check — if we got a 200 from /readyz, ' +
        'HTTP is obviously working, so this check validates self-consistency',
    ).toBeTruthy();
    expect(httpCheck.ok, 'http_server check must be true').toBe(true);
  });
});
