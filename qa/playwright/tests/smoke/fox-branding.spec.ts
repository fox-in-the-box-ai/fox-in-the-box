/**
 * Phase 1 spec — Fox branding overlay assets and class injection.
 *
 * Closes coverage gaps from v0.7.23 (#360):
 *
 *   fox-overlay.js now injects `.fox-in-the-box` onto <html> for every
 *   Fox container. This file verifies:
 *
 *   1. fox-overlay.js is served and non-empty (already in static-overlay.spec.ts
 *      but that spec predates the class-injection content — we assert the
 *      actual class-add line here).
 *
 *   2. The Fox avatar asset is reachable at /extensions/fox_avatar_cropped.jpg
 *      (patch 005 references this path; a wrong path silently serves 404 and
 *      every chat message shows a broken image instead of the Fox avatar).
 *
 *   3. The webui patch series files (004/005/006) are NOT directly served
 *      (they live in patches/webui/, not webui_static/ — they should 404 at
 *      /extensions/ so the raw patch text never leaks to users).
 *
 * All assertions target the static-file serving layer, not a live DOM, so
 * these specs run without FITB_TEST_MODE and don't need /test/reset.
 */
import { test, expect, request } from '@playwright/test';

test.describe('Phase 1 — Fox branding assets (#360, v0.7.23)', () => {
  test('fox-overlay.js is served and contains the .fox-in-the-box class injection', async ({ baseURL }) => {
    const api = await request.newContext({ baseURL });
    const res = await api.get('/extensions/fox-overlay.js');

    expect(
      res.status(),
      '/extensions/fox-overlay.js returned non-200. HERMES_WEBUI_EXTENSION_SCRIPT_URLS ' +
        'must list this file and the Dockerfile must COPY webui_static/.',
    ).toBe(200);

    const body = await res.text();
    expect(
      body,
      'fox-overlay.js does not contain classList.add(\'fox-in-the-box\'). ' +
        'The class injection that activates all Fox-branded CSS conditionals and ' +
        'patch 004 bot-name override is missing. Every Fox UI element that keys ' +
        'on .fox-in-the-box will be invisible.',
    ).toContain("classList.add('fox-in-the-box')");
  });

  test('Fox avatar image is reachable at /extensions/fox_avatar_cropped.jpg', async ({ baseURL }) => {
    // Patch 005 (ui.js) hardcodes src="/extensions/fox_avatar_cropped.jpg".
    // If this path 404s, every assistant chat message shows a broken image.
    const api = await request.newContext({ baseURL });
    const res = await api.get('/extensions/fox_avatar_cropped.jpg');

    expect(
      res.status(),
      '/extensions/fox_avatar_cropped.jpg returned ' + res.status() +
        '. Patch 005 references this exact path. Either the asset was not ' +
        'COPYd to webui_static/ root (it lives at webui_static/images/ — ' +
        'the Dockerfile COPY must cover that subdir), or the path in patch 005 drifted.',
    ).toBe(200);

    const ct = res.headers()['content-type'] || '';
    expect(
      ct,
      'fox_avatar_cropped.jpg content-type is not image/jpeg: ' + ct,
    ).toMatch(/image\/(jpeg|jpg)/i);
  });

  test('patch series files are NOT served at /extensions/ (patch dir is not webui_static)', async ({ baseURL }) => {
    // patches/webui/ is NOT in the extension dir — these files should 404.
    // If they were served it would expose raw patch text publicly.
    const api = await request.newContext({ baseURL });
    for (const patchFile of [
      '004-fox-bot-name-override.patch',
      '005-fox-avatar-override.patch',
      '006-fox-empty-state-branding.patch',
    ]) {
      const res = await api.get(`/extensions/${patchFile}`);
      expect(
        res.status(),
        `/extensions/${patchFile} should 404 — patch files must not be served as static assets.`,
      ).toBe(404);
    }
  });
});
