/**
 * Contract endpoints sweep — INSTANCE_CONTRACT + overlay endpoints respond.
 *
 * Complements the Phase 1 endpoints-sweep (which covers the 5 original
 * Fox-overlay prefixes) with the v0.7.55 contract endpoints and new
 * overlay surfaces. No overlap — paths covered by endpoints-sweep.spec.ts
 * are excluded here.
 *
 * Unlike the per-endpoint specs (contract-version, contract-capabilities,
 * etc.) which validate response shapes, this sweep only checks that
 * each endpoint is REGISTERED (returns an acceptable status, not
 * upstream's default-path handler).
 */
import { test, expect, request } from '@playwright/test';

const CONTRACT_ENDPOINTS: Array<{ path: string; ok: number[] }> = [
  { path: '/version', ok: [200] },
  { path: '/capabilities', ok: [200] },
  { path: '/readyz', ok: [200, 503] },
  { path: '/skillset', ok: [200, 404] },
  { path: '/health', ok: [200] },
  { path: '/hostname', ok: [200, 404, 503] },
  { path: '/api/providers', ok: [200] },
  { path: '/api/setup/welcome', ok: [200] },
];

test.describe('Contract + Fox endpoints sweep', () => {
  for (const { path, ok } of CONTRACT_ENDPOINTS) {
    test(`${path} registered (status in {${ok.join(', ')}})`, async ({ baseURL }) => {
      const api = await request.newContext({ baseURL });
      const res = await api.get(path);
      const status = res.status();
      expect(
        ok.includes(status),
        `${path} returned ${status} — expected one of [${ok.join(', ')}]. ` +
          `A 500 or unexpected status means the dispatcher didn't register the ` +
          `endpoint or the handler crashed.`,
      ).toBe(true);
    });
  }
});
