/**
 * Phase 1 spec — static-overlay assets are served.
 *
 * Phase 2 of the v0.6.0 migration shipped `HERMES_WEBUI_EXTENSION_*` env
 * vars so upstream's webui serves Fox's static assets from
 * `packages/fox-overlay/webui_static/` at `/extensions/*`. If those env
 * vars aren't set correctly OR if the assets weren't COPYd into the
 * image, every Fox-skinned UI element regresses to the default upstream
 * look — visible to users immediately on chat load.
 *
 * This spec hits a sample of overlay assets and asserts each loads. Not
 * exhaustive (Phase 2 spec #266 will sweep the full asset manifest);
 * just enough to catch the env-var-unset / Dockerfile-COPY-missing
 * regressions.
 */
import { test, expect, request } from '@playwright/test';

const OVERLAY_ASSETS = [
  // CSS — proves stylesheet serving works
  '/extensions/fox-in-the-box.css',
  // JS — proves script serving works
  '/extensions/fox-overlay.js',
  '/extensions/chat-model-preselect.js',
];

// New in v0.7.29 — chicken-and-egg until :stable advances.
const OVERLAY_ASSETS_V0729 = [
  '/extensions/model-picker-filter.js',
];

test.describe('Phase 1 — static-overlay assets', () => {
  for (const path of OVERLAY_ASSETS) {
    test(`${path} served at /extensions/`, async ({ baseURL }) => {
      const api = await request.newContext({ baseURL });
      const res = await api.get(path);

      expect(
        res.status(),
        `${path} returned ${res.status()} — expected 200. ` +
          `Either the Dockerfile didn't COPY webui_static/, or ` +
          `HERMES_WEBUI_EXTENSION_DIR isn't set on supervisord's hermes-webui block.`,
      ).toBe(200);

      const body = await res.text();
      expect(body.length, `${path} body is empty`).toBeGreaterThan(0);
    });
  }
});

// Unskip once :stable >= v0.7.29 (these files added in this PR).
test.describe.skip('Phase 1 — static-overlay assets v0.7.29+ (unskip when :stable advances)', () => {
  for (const path of OVERLAY_ASSETS_V0729) {
    test(`${path} served at /extensions/`, async ({ baseURL }) => {
      const api = await request.newContext({ baseURL });
      const res = await api.get(path);
      expect(res.status(), `${path} must return 200`).toBe(200);
      const body = await res.text();
      expect(body.length, `${path} body is empty`).toBeGreaterThan(0);
    });
  }
});
