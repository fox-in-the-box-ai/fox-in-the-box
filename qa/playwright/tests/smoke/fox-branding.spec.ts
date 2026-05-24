/**
 * Phase 1 spec — Fox branding overlay assets and class injection.
 *
 * Closes coverage gaps from v0.7.23 (#360):
 *
 *   1. fox-overlay.js content check — asserts classList.add('fox-in-the-box')
 *      is present. Chicken-and-egg: CI runs against :stable which predates
 *      v0.7.23. Unskip once :stable advances to v0.7.23+.
 *
 *   2. Fox avatar path — patch 005 references /extensions/images/fox_avatar_cropped.jpg
 *      (already covered by mobile-avatar.spec.ts). Redundant; removed.
 *
 *   3. Patch series files must NOT be served at /extensions/. Live now —
 *      this is a static file routing invariant independent of :stable version.
 */
import { test, expect, request } from '@playwright/test';

// ── Class injection content check (chicken-and-egg until :stable = v0.7.23+) ─
// CI :stable is pre-v0.7.23 and fox-overlay.js still contains only the
// comment line. Unskip when :stable advances to v0.7.23 (this PR's build).
test.describe.skip('Phase 1 — fox-overlay.js class injection (unskip when :stable >= v0.7.23)', () => {
  test('fox-overlay.js contains the .fox-in-the-box classList.add call', async ({ baseURL }) => {
    const api = await request.newContext({ baseURL });
    const res = await api.get('/extensions/fox-overlay.js');
    expect(res.status(), '/extensions/fox-overlay.js must return 200').toBe(200);

    const body = await res.text();
    expect(
      body,
      'fox-overlay.js does not contain classList.add(\'fox-in-the-box\'). ' +
        'The class injection that activates all Fox-branded CSS and patch 004 ' +
        'bot-name override is missing.',
    ).toContain("classList.add('fox-in-the-box')");
  });
});

// ── Live: patch files must not be served as static assets ────────────────────
test.describe('Phase 1 — Fox branding assets (#360, v0.7.23)', () => {
  test('patch series files are NOT served at /extensions/ (patch dir is not webui_static)', async ({ baseURL }) => {
    // patches/webui/ is not in HERMES_WEBUI_EXTENSION_DIR — these must 404.
    // Raw patch text leaking via /extensions/ would be a confidentiality issue.
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
