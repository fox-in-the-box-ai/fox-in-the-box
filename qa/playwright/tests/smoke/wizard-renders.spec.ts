/**
 * v0.7.13 #331 — Wizard renders for fresh-install users.
 *
 * The bug this spec exists to prevent from re-shipping: between v0.6.0
 * and v0.7.12, the onboarding redirect middleware was silently missing
 * from upstream's `server.py`. New users hit `/`, got upstream's chat
 * shell instead of Fox's wizard, hit a JS reference error mid-boot
 * (`loadOnboardingWizard` undefined because `.fox-removals` deleted the
 * file but upstream's `index.html` + `boot.js` still referenced it),
 * and ended up with a half-styled chat UI and no first-run guidance.
 *
 * NO PLAYWRIGHT SPEC IN THE EXISTING SUITE WOULD HAVE CAUGHT THIS.
 *
 * Spec ships in two halves:
 *
 * - **NOW (v0.7.13):** asset-served checks for setup.css + setup.js.
 *   Works against ANY :stable from v0.6.0+ because the assets have been
 *   in MANIFEST.toml + the extension dir since the migration; only the
 *   redirect that USES them is new in v0.7.13.
 *
 * - **NEXT (v0.7.14+):** the redirect-fires + wizard-DOM-renders checks
 *   that depend on patch 003 being in `:stable`. Can't run on v0.7.13's
 *   own PR CI because that pulls `:stable` (= v0.7.12 at PR-CI time)
 *   which still has the redirect missing. Once v0.7.13 ships and
 *   `:stable` advances, the v0.7.14 PR's CI will run against v0.7.13 +
 *   the redirect assertions can land then.
 *
 * Same chicken-and-egg pattern as v0.7.10's mobile-avatar.spec.ts split.
 */
import { test, expect, request } from '@playwright/test';

test.describe('Phase 1 — v0.7.13 #331 wizard assets shipping', () => {
  test('/extensions/setup.css is served (wizard styling)', async ({ baseURL }) => {
    const api = await request.newContext({ baseURL });
    const res = await api.get('/extensions/setup.css');
    expect(
      res.status(),
      '/extensions/setup.css must return 200. Check HERMES_WEBUI_EXTENSION_DIR ' +
        'env in supervisord.conf + Dockerfile COPY of webui_static/. If this 404s, ' +
        'the wizard renders unstyled even if the redirect fires.',
    ).toBe(200);
    const body = await res.text();
    expect(body.length, 'setup.css body suspiciously small').toBeGreaterThan(100);
  });

  test('/extensions/setup.js is served (wizard logic)', async ({ baseURL }) => {
    const api = await request.newContext({ baseURL });
    const res = await api.get('/extensions/setup.js');
    expect(res.status()).toBe(200);
    const body = await res.text();
    expect(body.length, 'setup.js body suspiciously small').toBeGreaterThan(100);
    // Anchor on a string the v0.5.x setup.js definitely emits — a regression
    // where the file is served but contents are wrong (cache poisoning,
    // wrong asset path) would slip past a pure length check.
    expect(
      body,
      'setup.js content does not look like the Fox wizard (missing "progress" or "step" tokens).',
    ).toMatch(/step|progress/i);
  });
});

// ── v0.7.14+ work (chicken-and-egg with this PR's CI pulling pre-v0.7.13 :stable) ─
// Add these once :stable advances to v0.7.13:
//
//   test('fresh container redirects / → /setup with Fox wizard DOM', async ({page, baseURL}) => {
//     const api = await request.newContext({ baseURL });
//     await api.post('/test/reset');                 // wipe onboarding state
//     await page.goto('/', { waitUntil: 'domcontentloaded' });
//     expect(page.url()).toMatch(/\/setup$/);        // PROVES patch 003 fired
//     await expect(page.locator('#wizard')).toBeVisible();
//     await expect(page.locator('#progress-bar')).toBeVisible();
//   });
//
// Plus a fox-styling-applied.spec.ts that asserts `getComputedStyle(:root).
// getPropertyValue('--fitb-app-scale')` is non-empty — catches the
// downstream-cascade "styling lost" symptom of #331.
