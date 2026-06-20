/**
 * Contract endpoint — GET /version (INSTANCE_CONTRACT §4.1).
 *
 * Validates the response shape, field types, and non-empty values.
 * Fleet's health monitor reads these fields; a shape change here
 * breaks fleet-level instance tracking.
 */
import { test, expect, request } from '@playwright/test';

test.describe('Contract — /version', () => {
  test('returns 200 with JSON', async ({ baseURL }) => {
    const api = await request.newContext({ baseURL });
    const res = await api.get('/version');
    expect(res.status(), '/version must return 200').toBe(200);
    const ct = res.headers()['content-type'] || '';
    expect(ct, '/version must return JSON').toContain('application/json');
  });

  test('response has required fields', async ({ baseURL }) => {
    const api = await request.newContext({ baseURL });
    const body = await (await api.get('/version')).json();
    const required = ['contract_version', 'runtime', 'runtime_version', 'overlay_version'];
    for (const field of required) {
      expect(body, `/version missing required field "${field}"`).toHaveProperty(field);
    }
  });

  test('contract_version is semver-shaped', async ({ baseURL }) => {
    const api = await request.newContext({ baseURL });
    const body = await (await api.get('/version')).json();
    expect(
      body.contract_version,
      `contract_version="${body.contract_version}" does not match semver pattern`,
    ).toMatch(/^\d+\.\d+\.\d+$/);
  });

  test('runtime is "hermes"', async ({ baseURL }) => {
    const api = await request.newContext({ baseURL });
    const body = await (await api.get('/version')).json();
    expect(body.runtime, 'Fox instances must report runtime=hermes').toBe('hermes');
  });
});
