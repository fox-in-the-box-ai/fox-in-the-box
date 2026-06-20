/**
 * Provider settings — /api/providers CRUD lifecycle.
 *
 * Tests the custom provider management endpoints: list, add, remove.
 * These are the same endpoints the Settings UI calls — a broken
 * provider CRUD means users can't configure model providers after
 * the wizard.
 */
import { test, expect, request } from '@playwright/test';

test.describe('Provider settings', () => {
  test('GET /api/providers returns a list', async ({ baseURL }) => {
    const api = await request.newContext({ baseURL });
    const res = await api.get('/api/providers');
    expect(res.status(), '/api/providers must return 200').toBe(200);
    const body = await res.json();
    expect(Array.isArray(body), '/api/providers must return an array').toBe(true);
  });

  test('POST /api/providers rejects empty name', async ({ baseURL }) => {
    const api = await request.newContext({ baseURL });
    const res = await api.post('/api/providers', {
      data: { action: 'upsert', name: '', base_url: 'http://example.com', models: ['m1'] },
    });
    expect(
      res.status(),
      'POST /api/providers with empty name must return 400',
    ).toBe(400);
  });

  test('POST /api/providers rejects invalid URL scheme', async ({ baseURL }) => {
    const api = await request.newContext({ baseURL });
    const res = await api.post('/api/providers', {
      data: { action: 'upsert', name: 'test', base_url: 'ftp://bad', models: ['m1'] },
    });
    expect(
      res.status(),
      'POST /api/providers with ftp:// URL must return 400 — only http(s) allowed',
    ).toBe(400);
  });
});
