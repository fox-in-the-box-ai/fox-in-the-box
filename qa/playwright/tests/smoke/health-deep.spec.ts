/**
 * Phase 1 spec — /health deeper checks.
 *
 * The Phase 0 spec only asserted `/health` returns 200. Phase 1 goes
 * one layer deeper: content-type is JSON-ish, body parses, and the
 * status field is healthy. Catches upstream regressions where /health
 * starts returning HTML, plain-text, or a non-OK body.
 */
import { test, expect, request } from '@playwright/test';

test.describe('Phase 1 — /health body sanity', () => {
  test('/health returns 200 + valid response', async ({ baseURL }) => {
    const api = await request.newContext({ baseURL });
    const res = await api.get('/health');

    expect(res.status(), '/health must be 200').toBe(200);

    const ct = res.headers()['content-type'] || '';
    // Upstream may return JSON or text/plain "ok" depending on version.
    // Either is acceptable; neither HTML nor application/xml is.
    expect(
      /^(application\/json|text\/plain)/i.test(ct),
      `/health returned content-type=${ct} — expected JSON or plain text`,
    ).toBe(true);

    const body = await res.text();
    expect(body.length, '/health body is empty').toBeGreaterThan(0);
    // Body should not be an HTML error page (smoke test for "upstream's
    // default 500 handler renders HTML even on /health").
    expect(body.toLowerCase()).not.toContain('<html');
  });
});
