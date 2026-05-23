/**
 * v0.7.20 #336 — Wizard local-fallback error UX.
 *
 * The bug this spec exists to prevent from re-shipping (and to verify the
 * v0.7.20 fix when it lands):
 *
 *   When the wizard's "Use local model" tile fails to enable local fallback
 *   (network glitch, supervisor not ready, model directory write-failed,
 *   etc.), the wizard alerts the literal string "Could not enable local
 *   fallback: unknown error". @roadhero hit this on Win11 — the actual cause
 *   was the supervisor not having llama-server in its program list yet, but
 *   the wizard never surfaced anything diagnosable. See
 *   packages/fox-overlay/webui_static/setup.js:447
 *     alert('Could not enable local fallback: ' +
 *           ((r.data && r.data.error) || 'unknown error'));
 *
 *   The handler at packages/fox-overlay/fox_overlay/webui_modules/
 *   local_fallback.py:enable() currently always returns get_status() — no
 *   `error` field is plumbed through on failure. v0.7.20 will add structured
 *   error responses so the wizard alert reads "Could not enable local
 *   fallback: <reason>" instead of "unknown error".
 *
 * Spec ships in two halves:
 *
 *   1. **Live (interactivity)** — proves /api/local-fallback/enable is
 *      reachable + returns JSON + the wizard's expected fields are present.
 *      This part runs against :stable v0.7.19+ today; it pins the contract
 *      surface so any v0.7.20 changes to the response shape (adding error/
 *      reason) don't break the wizard read path.
 *
 *   2. **Skipped — unblock on v0.7.20 #336 fix** — asserts the response
 *      includes a meaningful `error` field when enable() can't actually
 *      enable local fallback (e.g. supervisor not running). Currently the
 *      module never returns ok:false — set_enabled(True) cannot fail in the
 *      current implementation. The v0.7.20 fix will introduce real failure
 *      paths (config-write-failed, supervisor-unavailable). Unskip when
 *      :stable >= v0.7.20.
 */
import { test, expect, request } from '@playwright/test';

test.describe('Phase 1 — wizard local-fallback API surface', () => {
  test('POST /api/local-fallback/enable returns JSON with the wizard-required fields', async ({
    baseURL,
  }) => {
    // The wizard's useLlamaCppFallback() reads r.data.enabled to decide
    // success/failure (see setup.js:446). If the API ever returns a non-JSON
    // body or omits `enabled`, the wizard alerts "unknown error" with no
    // diagnostic — the exact #336 symptom. Pin the contract here.
    const api = await request.newContext({ baseURL });

    // Reset state first — local-fallback enable is sticky across runs.
    const resetRes = await api.post('/test/reset');
    expect(
      resetRes.status(),
      '/test/reset is required to wipe the persisted enabled flag between runs. ' +
        'CI must run the container with FITB_TEST_MODE=1.',
    ).toBe(200);

    const res = await api.post('/api/local-fallback/enable', {
      data: {},
      headers: { 'content-type': 'application/json' },
    });

    expect(
      res.status(),
      '/api/local-fallback/enable must return 2xx. 404 means webui_modules/local_fallback.py ' +
        'failed to register its POST routes — check fox_overlay.dispatch.register_post wiring.',
    ).toBeLessThan(400);

    // Body must parse as JSON. setup.js does `r.data = JSON.parse(...)` and
    // crashes on non-JSON, which the user sees as a silent wizard freeze.
    const body = await res.json();
    expect(
      body,
      'enable() response must be a JSON object so setup.js can read .enabled / .error.',
    ).toBeTruthy();
    expect(
      typeof body.enabled,
      'response.enabled must be present — wizard branches on it at setup.js:446.',
    ).toBe('boolean');
  });

  test('GET /api/local-fallback/status returns a valid ui_state for wizard rendering', async ({
    baseURL,
  }) => {
    // setup.js polls /status for ui_state to render the progress strip
    // (downloading / installing / ready). Missing or non-string ui_state
    // freezes the wizard on "Please wait…" indefinitely.
    const api = await request.newContext({ baseURL });
    const res = await api.get('/api/local-fallback/status');
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(
      typeof body.ui_state,
      'response.ui_state must be a string — the wizard switches its progress UI on this value.',
    ).toBe('string');
  });
});

// ── v0.7.20 #336 — UNSKIP TARGET: :stable >= v0.7.20 ────────────────────────
// Tracking: https://github.com/fox-in-the-box-ai/fox-in-the-box/issues/336
//
// Today this would fail because local_fallback.enable() always returns
// get_status() with no `error` field. The v0.7.20 fix will plumb structured
// errors through the enable path so the wizard alert can show "<actual cause>"
// instead of "unknown error".
//
// When v0.7.20 ships, remove `.skip` and rebase against the implementation.
test.describe.skip('Phase 1 — v0.7.20 #336 local-fallback error UX (unskip after v0.7.20)', () => {
  test('enable() failure response includes a non-empty `error` string', async ({ baseURL }) => {
    // To exercise the failure path on demand, v0.7.20 should introduce a
    // FITB_TEST_MODE-only knob to force enable() to fail (e.g. a header
    // `x-fitb-test-fail: supervisor-unavailable`). If the v0.7.20 patch
    // takes a different shape, update this stimulus accordingly — what
    // matters is the assertion: failure responses MUST carry a meaningful
    // `error` field, not just `{ok: false}`.
    const api = await request.newContext({ baseURL });
    await api.post('/test/reset');

    const res = await api.post('/api/local-fallback/enable', {
      data: {},
      headers: {
        'content-type': 'application/json',
        'x-fitb-test-fail': 'supervisor-unavailable',  // v0.7.20 contract — adjust if the fix uses a different mechanism
      },
    });

    const body = await res.json();
    expect(
      body.ok,
      'failure response must set ok:false so setup.js takes the error branch.',
    ).toBe(false);
    expect(
      typeof body.error,
      'failure response must include a string `error` field. The whole point of #336 is to ' +
        'replace "unknown error" with a real diagnostic message — if this is undefined, the ' +
        'wizard regression is still live.',
    ).toBe('string');
    expect(
      body.error.length,
      'error message must not be empty — "" trips the `|| "unknown error"` fallback at setup.js:447 ' +
        'and we are right back where #336 started.',
    ).toBeGreaterThan(0);
    // Catch literally-the-bug regressions where someone hard-codes "unknown
    // error" as the server-side fallback (which would technically satisfy
    // the "non-empty string" check but defeats the entire fix).
    expect(
      body.error.toLowerCase(),
      'server must not return the literal string "unknown error" — that string is the wizard\'s ' +
        'fallback when no real error is provided. If the server returns it, the wizard shows ' +
        '"Could not enable local fallback: unknown error", which is exactly #336.',
    ).not.toContain('unknown error');
  });

  test('enable() failure response includes a structured `reason` code', async ({ baseURL }) => {
    // Beyond a human-readable `error`, the v0.7.20 fix should plumb a
    // machine-readable `reason` (config-write-failed, supervisor-unavailable,
    // download-failed, etc.) so the wizard can offer reason-specific
    // recovery actions instead of a generic alert. The disable()/activate()
    // paths already use `reason` (see local_fallback.py:449, 452, 485) —
    // this just asks enable() to match.
    const api = await request.newContext({ baseURL });
    await api.post('/test/reset');

    const res = await api.post('/api/local-fallback/enable', {
      data: {},
      headers: {
        'content-type': 'application/json',
        'x-fitb-test-fail': 'supervisor-unavailable',
      },
    });
    const body = await res.json();
    expect(typeof body.reason).toBe('string');
    expect(body.reason.length).toBeGreaterThan(0);
  });
});
