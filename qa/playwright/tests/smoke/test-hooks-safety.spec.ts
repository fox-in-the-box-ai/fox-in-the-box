/**
 * Phase 1 spec — test_hooks production-safety verification (from the outside).
 *
 * The `packages/fox-overlay/tests/test_test_hooks.py` unit tests already
 * verify the FITB_TEST_MODE gate works at the module level. This spec
 * verifies it from the OUTSIDE — actually hitting POST /test/reset
 * against the running container.
 *
 * Two scenarios are theoretically possible depending on how this spec
 * is run:
 *
 * 1. CI's `smoke` job runs the container WITH `FITB_TEST_MODE=1`
 *    (per playwright.yml `docker run` args). In that mode the route IS
 *    registered → /test/reset returns 200 with the {removed: ...} body.
 *    This proves the test_hooks module loads + registers correctly
 *    when the env var is set.
 *
 * 2. A production-mode container (FITB_TEST_MODE unset) would return
 *    a 404 / similar non-200 from upstream's default-path handler,
 *    proving the gate works. We can't easily test this from CI without
 *    spinning up a second container; the unit tests cover that case.
 *
 * For now we test scenario 1 only — assert the route IS available when
 * the env var IS set. The unit-level prod-safety check covers the
 * inverse.
 */
import { test, expect, request } from '@playwright/test';

test.describe('Phase 1 — test_hooks (FITB_TEST_MODE=1)', () => {
  test('POST /test/reset returns ok=true when FITB_TEST_MODE=1', async ({ baseURL }) => {
    const api = await request.newContext({ baseURL });
    const res = await api.post('/test/reset');

    // CI's smoke job sets FITB_TEST_MODE=1 explicitly. If the route returns
    // 404 the test_hooks module failed to register — either the env var
    // didn't propagate, or webui_modules/__init__.py doesn't import
    // test_hooks.
    expect(
      res.status(),
      `POST /test/reset returned ${res.status()}. CI sets FITB_TEST_MODE=1 in the docker run env. ` +
        `404 means the route didn't register — check webui_modules/__init__.py imports test_hooks AND ` +
        `test_hooks.py module-level if-_ENABLED guard saw the env var.`,
    ).toBe(200);

    const body = await res.json();
    expect(body.ok, '/test/reset must return {ok: true}').toBe(true);
    expect(body.removed, '/test/reset response missing "removed" key').toBeTruthy();
    expect(typeof body.removed.json_files, '"removed.json_files" must be a number').toBe(
      'number',
    );
    expect(typeof body.removed.session_dirs, '"removed.session_dirs" must be a number').toBe(
      'number',
    );
  });
});
