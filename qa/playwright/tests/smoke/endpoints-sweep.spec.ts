/**
 * Phase 1 spec — Fox-claimed endpoints sweep.
 *
 * Parametrize over every Fox-added route prefix. Each must return an
 * acceptable status (200 / 404 / 503) — anything outside that range
 * means upstream returned its default "unknown path" 404 because Fox's
 * dispatcher didn't register the prefix, which is the regression we're
 * catching.
 *
 * Why these specific statuses are OK:
 * - 200: route registered AND ran cleanly
 * - 404: route registered, handler decided the specific sub-path doesn't
 *   exist (common for GETs against bare prefixes that only handle sub-paths)
 * - 503: route registered, dependency-not-ready (e.g. /api/ollama/status
 *   when daemon isn't running). Distinct from upstream's "unknown path"
 *   500/404 because it comes from inside Fox's handler.
 *
 * NOT OK: 500 (handler crashed) or any status that smells like upstream's
 * default-path response (Fox's modules never raise 500 in normal flow).
 */
import { test, expect, request } from '@playwright/test';

const FOX_PREFIXES = [
  '/api/ollama/status',
  '/api/tailscale/status',
  '/api/local-fallback/status',
  '/api/local-models',
  '/setup',
];

test.describe('Phase 1 — Fox-claimed endpoints sweep', () => {
  for (const path of FOX_PREFIXES) {
    test(`${path} registered (status in {200, 404, 503})`, async ({ baseURL }) => {
      const api = await request.newContext({ baseURL });
      const res = await api.get(path);
      const status = res.status();
      expect(
        [200, 404, 503].includes(status),
        `${path} returned ${status} — expected 200/404/503 to prove Fox's dispatcher claimed the prefix. ` +
          `A different status (especially 500) suggests Fox's module didn't register or crashed.`,
      ).toBe(true);
    });
  }
});
