/**
 * Phase 1 spec — v0.7.10 #299: Fox avatar shows in mobile titlebar.
 *
 * v0.7.10 lands the CSS swap from upstream's Hermes caduceus SVG to the
 * Fox avatar photo at <768px viewport. This spec ships in two halves:
 *
 * - **NOW (v0.7.10):** assert the asset is actually served at
 *   `/extensions/images/`. This works against ANY `:stable` from v0.6.0+
 *   because the asset has been in MANIFEST.toml + the extension dir
 *   forever; just the CSS that *uses* it is new in v0.7.10.
 *
 * - **NEXT (v0.7.11+):** assert the computed background-image actually
 *   references the asset at mobile viewport. This can't run on v0.7.10's
 *   own PR CI because the smoke job pulls `:stable` (= v0.7.9 at PR-CI
 *   time), which doesn't yet have the CSS. Once v0.7.10 ships and
 *   `:stable` advances, the v0.7.11 PR's CI will run against v0.7.10 +
 *   the bg-image assertion can land then.
 *
 * Both halves catch the same regression classes: missing asset, CSS
 * load-order, upstream selector rename — the asset-served check catches
 * the first; the bg-image check catches the latter two.
 */
import { test, expect, request } from '@playwright/test';

test.use({
  viewport: { width: 375, height: 667 },  // iPhone SE / 8 dimensions
});

test.describe('Phase 1 — v0.7.10 #299 mobile avatar (asset shipping)', () => {
  test('Fox avatar asset is served at /extensions/images/', async ({ baseURL }) => {
    // Pre-flight: the asset must actually load. If this 404s, the CSS swap
    // would silently fall back to whatever upstream renders.
    const api = await request.newContext({ baseURL });
    const res = await api.get('/extensions/images/fox_avatar_cropped.jpg');
    expect(
      res.status(),
      '/extensions/images/fox_avatar_cropped.jpg must return 200 — check ' +
        'MANIFEST.toml + Dockerfile COPY chain + HERMES_WEBUI_EXTENSION_DIR.',
    ).toBe(200);
    const ct = res.headers()['content-type'] || '';
    expect(ct, 'asset content-type must be image/*').toMatch(/^image\//);
  });
});
