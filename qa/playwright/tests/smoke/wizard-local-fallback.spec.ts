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

// ── #336 error UX — LIVE (v0.7.29+, /test/inject-failure now available) ──────
// /test/inject-failure arms local_fallback._INJECTED_FAILURE so enable() returns
// an error dict without actually failing. Unskipped in v0.7.29 once the hook
// ships (test_hooks.py Phase 1 landed in this same PR).
test.describe('Phase 1 — #336 local-fallback error UX (inject-failure hook available v0.7.29+)', () => {
  test('enable() failure response includes a non-empty `error` string', async ({ baseURL }) => {
    const api = await request.newContext({ baseURL });
    // Reset state first, then arm the failure injection.
    await api.post('/test/reset');
    const injectRes = await api.post('/test/inject-failure', {
      data: { target: 'local_fallback.enable', kind: 'supervisor-unavailable' },
    });
    expect(
      injectRes.status(),
      '/test/inject-failure must return 200 — FITB_TEST_MODE=1 is required in CI.',
    ).toBe(200);
    const injectBody = await injectRes.json();
    expect(injectBody.ok, '/test/inject-failure response must be ok:true').toBe(true);

    const res = await api.post('/api/local-fallback/enable', { data: {} });
    const body = await res.json();

    expect(
      typeof body.error,
      'failure response must include a string `error` field — the whole point of #336 is to ' +
        'replace "unknown error" with a real diagnostic.',
    ).toBe('string');
    expect(body.error.length, 'error must not be empty').toBeGreaterThan(0);
    expect(
      body.error.toLowerCase(),
      'server must not return the literal "unknown error" string — that is the pre-#336 bug.',
    ).not.toContain('unknown error');

    // Cleanup — reset clears the injected failure flag.
    await api.post('/test/reset');
  });

  test('enable() failure response error matches the injected kind', async ({ baseURL }) => {
    const api = await request.newContext({ baseURL });
    await api.post('/test/reset');
    await api.post('/test/inject-failure', {
      data: { target: 'local_fallback.enable', kind: 'supervisor-unavailable' },
    });

    const res = await api.post('/api/local-fallback/enable', { data: {} });
    const body = await res.json();

    expect(
      body.error,
      'injected failure kind must be surfaced in the error field',
    ).toContain('supervisor-unavailable');

    await api.post('/test/reset');
  });
});
