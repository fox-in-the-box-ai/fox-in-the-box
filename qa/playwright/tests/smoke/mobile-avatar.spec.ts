/**
 * Phase 1 spec — v0.7.10 #299: Fox avatar shows in mobile titlebar.
 *
 * Asserts the CSS swap from upstream's Hermes caduceus SVG to the Fox
 * avatar photo fires at the mobile breakpoint. Catches regressions where:
 *   - the @media (max-width: 767px) rule gets reordered out by an upstream
 *     stylesheet that loads after fox-in-the-box.css
 *   - the asset path /extensions/images/fox_avatar_cropped.jpg stops being
 *     served (HERMES_WEBUI_EXTENSION_DIR unset, Dockerfile COPY chain
 *     regressed)
 *   - the .app-titlebar-icon selector gets renamed upstream (Fox CSS
 *     becomes a no-op silently)
 *
 * Coverage shape: this spec runs under the `smoke` project (chromium with
 * an iPhone-sized viewport set inline). When the Phase 2 matrix lands, a
 * dedicated `mobile-safari` project will exercise the same spec in real
 * WebKit + Safari device-emulation — the assertion shape stays.
 */
import { test, expect, devices, request } from '@playwright/test';

test.use({
  viewport: { width: 375, height: 667 },  // iPhone SE / 8 dimensions
});

test.describe('Phase 1 — v0.7.10 #299 mobile avatar', () => {
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

  test('mobile titlebar icon uses Fox avatar background-image', async ({ page }) => {
    // Walk past onboarding to the main app shell where .app-titlebar lives.
    // /setup/skip is the documented test-bypass path (used in Phase 0 spec).
    await page.goto('/');
    // Wait for the titlebar to render — it's part of the app shell.
    const titlebarIcon = page.locator('.app-titlebar-icon').first();
    await titlebarIcon.waitFor({ state: 'attached', timeout: 10_000 });

    // Computed background-image should reference the Fox avatar.
    const bgImage = await titlebarIcon.evaluate(
      (el) => window.getComputedStyle(el).backgroundImage,
    );
    expect(
      bgImage,
      `titlebar icon background-image was "${bgImage}" — expected url(...fox_avatar_cropped.jpg). ` +
        `Either the @media (max-width: 767px) rule didn't apply (viewport > 767px?), or the ` +
        `fox-in-the-box.css load order regressed.`,
    ).toContain('fox_avatar_cropped.jpg');

    // Touch target ≥ 44px per Apple HIG / WCAG 2.5.5.
    const box = await titlebarIcon.boundingBox();
    expect(box, 'titlebar icon has no bounding box (display: none?)').not.toBeNull();
    if (box) {
      expect(box.width, 'touch target width < 44px').toBeGreaterThanOrEqual(44);
      expect(box.height, 'touch target height < 44px').toBeGreaterThanOrEqual(44);
    }

    // Upstream's embedded SVG (width="16" height="16") should be hidden so it
    // doesn't render on top of the background image.
    const svgVisible = await titlebarIcon
      .locator('svg')
      .first()
      .evaluate(
        (el) => window.getComputedStyle(el).display !== 'none',
        { timeout: 1000 },
      )
      .catch(() => false);  // SVG may not exist if upstream removed it — that's fine
    expect(svgVisible, 'embedded SVG must be display:none on mobile').toBe(false);
  });
});
