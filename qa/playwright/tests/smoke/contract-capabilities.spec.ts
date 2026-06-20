/**
 * Contract endpoint — GET /capabilities (INSTANCE_CONTRACT §4.3).
 *
 * Fleet reads capabilities to decide what management features to
 * surface per instance (e.g. only show the data-plane panel when
 * data_plane_access is true). A missing key or non-boolean value
 * breaks Fleet's capability gating.
 */
import { test, expect, request } from '@playwright/test';

// Canonical source: INSTANCE_CONTRACT §4.3 — update when the contract adds a capability.
const EXPECTED_KEYS = [
  'local_fallback',
  'tailscale',
  'ollama',
  'web_search',
  'file_upload',
  'cron_jobs',
  'model_download',
  'data_plane_access',
];

test.describe('Contract — /capabilities', () => {
  test('returns 200 with JSON', async ({ baseURL }) => {
    const api = await request.newContext({ baseURL });
    const res = await api.get('/capabilities');
    expect(res.status(), '/capabilities must return 200').toBe(200);
    const ct = res.headers()['content-type'] || '';
    expect(ct, '/capabilities must return JSON').toContain('application/json');
  });

  test('response has contract_version and capabilities object', async ({ baseURL }) => {
    const api = await request.newContext({ baseURL });
    const body = await (await api.get('/capabilities')).json();
    expect(body, 'missing contract_version').toHaveProperty('contract_version');
    expect(body, 'missing capabilities object').toHaveProperty('capabilities');
    expect(typeof body.capabilities, 'capabilities must be an object').toBe('object');
  });

  test('all expected capability keys are present', async ({ baseURL }) => {
    const api = await request.newContext({ baseURL });
    const body = await (await api.get('/capabilities')).json();
    for (const key of EXPECTED_KEYS) {
      expect(body.capabilities, `capability "${key}" missing`).toHaveProperty(key);
    }
  });

  test('all capability values are booleans', async ({ baseURL }) => {
    const api = await request.newContext({ baseURL });
    const body = await (await api.get('/capabilities')).json();
    for (const [key, value] of Object.entries(body.capabilities)) {
      expect(
        typeof value,
        `capability "${key}" is ${typeof value}, expected boolean — ` +
          `Fleet gates features on these values; non-boolean breaks the check`,
      ).toBe('boolean');
    }
  });
});
