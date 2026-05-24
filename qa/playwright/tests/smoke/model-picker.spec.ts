/**
 * Phase 1 spec — model picker + Ollama provider tile coverage.
 *
 * Closes three SWE C audit gaps that the existing 7 smoke specs miss:
 *
 *   #337 (shipped v0.7.18) — Ollama provider group must ALWAYS appear in
 *     /api/models output, regardless of whether the local daemon is
 *     running. Before v0.7.18, _splice_ollama_group() short-circuited when
 *     the daemon wasn't reachable, so users who hadn't installed Ollama
 *     had no way to discover Fox supports it. Phase 1: live spec.
 *
 *   #344 (v0.7.20 work, NOT shipped on :stable yet) — opening chat after a
 *     fresh /test/reset must auto-preselect a usable model when at least
 *     one provider is configured, or fall back to an explicit empty state
 *     when no providers are configured. Chicken-and-egg: this PR's :stable
 *     is v0.7.19, which still has the bug, so the spec is describe.skip
 *     until v0.7.20 ships. Same pattern as wizard-renders.spec.ts'
 *     Phase 1 v0.7.13 redirect block was, pre-v0.7.17.
 *
 *   #278 (v0.7.20 work, NOT shipped) — each Ollama model must appear in
 *     the picker exactly ONCE. Today, locally-pulled Ollama models can
 *     show up under both the "Ollama" group (Fox's #337 splice) AND a
 *     "Custom" group (if the user added a custom OpenAI-compat endpoint
 *     pointing at the same daemon). Dedup belongs in
 *     _splice_ollama_group. Skip until v0.7.20.
 *
 * All assertions target the `/api/models` JSON shape because (a) it's the
 * single source of truth that the DOM `<select id="modelSelect">`
 * mirrors via populateModelDropdown() in static/ui.js, (b) it's invariant
 * to upstream HTML refactors, and (c) it parallels the endpoints-sweep
 * pattern this file is a sibling of. A DOM-level assertion would catch
 * the same regressions but be more brittle.
 */
import { test, expect, request } from '@playwright/test';

// ── Phase 1 — #337 Ollama tile always present (v0.7.18+, LIVE) ─────────────
// Unskipped in v0.7.28: :stable is now v0.7.27+, which has the /api/models
// whitelist added in v0.7.21. The chicken-and-egg is resolved.
test.describe('Phase 1 — #337 Ollama tile always present (v0.7.18+)', () => {
  test('GET /api/models always returns an Ollama provider group', async ({ baseURL }) => {
    // Fresh-install state via /test/reset (FITB_TEST_MODE=1 in CI).
    // We reset so the spec is invariant to whatever provider config a
    // previous test left behind.
    const api = await request.newContext({ baseURL });
    const resetRes = await api.post('/test/reset');
    expect(resetRes.status(), '/test/reset must be available — CI sets FITB_TEST_MODE=1').toBe(
      200,
    );

    const res = await api.get('/api/models');
    expect(res.status(), '/api/models must return 200').toBe(200);
    const data = await res.json();

    expect(
      Array.isArray(data.groups),
      '/api/models response missing "groups" array. Upstream contract broke or the ' +
        'Fox wrap in fox_overlay/webui_patches/config.py:_wrap_get_available_models() ' +
        'returned a non-dict.',
    ).toBe(true);

    const ollamaGroup = data.groups.find(
      (g: { provider_id?: string; provider?: string }) =>
        g.provider_id === 'ollama' || (g.provider || '').toLowerCase() === 'ollama',
    );
    expect(
      ollamaGroup,
      'No Ollama group in /api/models. v0.7.18 #337 fix asserts _splice_ollama_group() ' +
        'ALWAYS appends an Ollama group regardless of daemon state. If this is ' +
        'undefined: either the splice no-op\'d (regression of pre-v0.7.18 behavior), ' +
        'the wrap sentinel was tripped without applying the patch, or get_available_models() ' +
        'signature drifted and the wrap declined to apply.',
    ).toBeDefined();
  });

  test('Ollama group includes install hint when daemon is not running', async ({ baseURL }) => {
    // This spec runs against the CI container, which does NOT have an Ollama
    // daemon installed — so the splice should produce the no_daemon branch
    // with the "Install Ollama from ollama.com/download" hint. If a future
    // CI image ships with Ollama bundled, this assertion needs the inverse
    // branch (models present, no status_message) and the test gains a
    // conditional.
    const api = await request.newContext({ baseURL });
    await api.post('/test/reset');
    const res = await api.get('/api/models');
    const data = await res.json();

    const ollamaGroup = data.groups.find(
      (g: { provider_id?: string }) => g.provider_id === 'ollama',
    );
    expect(ollamaGroup, 'Ollama group missing — see prior test').toBeDefined();

    // No daemon → synthetic placeholder entry with `__ollama_hint:no_daemon`
    // id + state-aware copy. This is the literal copy users see in the
    // picker; if it changes, update both this spec and the i18n copy in
    // fox_overlay/webui_patches/config.py:_splice_ollama_group().
    const models = ollamaGroup.models || [];
    const hint = models.find(
      (m: { id?: string }) => typeof m?.id === 'string' && m.id.startsWith('__ollama_hint:'),
    );
    expect(
      hint,
      'Ollama group has no __ollama_hint:* synthetic entry. CI container has no ' +
        'daemon, so the splice should emit a hint placeholder. If the group ships ' +
        'real models instead, either CI bundled Ollama (update the assertion) or ' +
        '_splice_ollama_group() lost its no_daemon branch.',
    ).toBeDefined();
    expect(
      hint.label,
      'Ollama install hint label does not mention ollama.com/download. ' +
        'Users rely on this exact URL to find the installer; if it changes, ' +
        'update both this spec and webui_patches/config.py.',
    ).toMatch(/ollama\.com\/download/i);
  });
});

// ── Phase 1 — #344 chat auto-preselect (v0.7.20+, SKIPPED) ─────────────────
// v0.7.21 STATUS: the #344 FIX shipped in v0.7.20 via the
// chat-model-preselect.js extension (which uses exactly "Model not selected"
// for empty state — matches the regex below). However these tests still
// Hooks landed in v0.7.29 but CI :stable is pre-v0.7.29 — returning 404.
// Unskip once :stable advances to v0.7.29+.
test.describe.skip('Phase 1 — #344 chat auto-preselect (unskip when :stable >= v0.7.29)', () => {
  test('with NO providers configured, picker chip shows explicit empty state', async ({
    page,
    baseURL,
  }) => {
    const api = await request.newContext({ baseURL });
    await api.post('/test/reset');

    // Use /test/skip-onboarding so / lands on chat, not /setup.
    const skipRes = await api.post('/test/skip-onboarding');
    expect(
      skipRes.status(),
      '/test/skip-onboarding must return 200 — FITB_TEST_MODE=1 required in CI',
    ).toBe(200);

    await page.goto('/');
    const chip = page.locator('#composerModelLabel');
    await expect(
      chip,
      'composerModelLabel must contain explicit empty-state copy when no providers configured. ' +
        'A blank label is the v0.7.19 bug #344 is filed against.',
    ).toContainText(/model not selected|no model|select.*model/i, { timeout: 8000 });
  });

  test('with at least one provider configured, picker auto-selects a usable model', async ({
    page,
    baseURL,
  }) => {
    const api = await request.newContext({ baseURL });
    await api.post('/test/reset');

    // Seed a provider so the picker has something to auto-select.
    const seedRes = await api.post('/test/seed-provider', {
      data: { provider: 'openrouter', api_key: 'sk-or-test-placeholder' },
    });
    expect(seedRes.status(), '/test/seed-provider must return 200').toBe(200);

    // Skip onboarding redirect so / lands on chat.
    await api.post('/test/skip-onboarding');

    await page.goto('/');
    const chip = page.locator('#composerModelLabel');
    await expect(
      chip,
      'composerModelLabel must be non-empty after page load when a provider is configured. ' +
        'Empty chip = #344 regressed.',
    ).not.toHaveText('', { timeout: 8000 });
  });
});

// ── Phase 1 — #278 Ollama dedup across groups ────────────────────────────────
// /test/seed-provider is now available (v0.7.29) but seeding a Custom provider
// that ALSO exposes an Ollama model id requires a mock Ollama daemon or a custom
// endpoint — more than /test/seed-provider alone can provide. Kept skipped
// until a mock-daemon approach is decided. The dedup code at ollama.py:459,492
// shipped in v0.7.20 and is correct; this spec exercises the regression path.
test.describe.skip('Phase 1 — #278 Ollama dedup (unskip pending mock-Ollama-daemon in CI)', () => {
  test('each Ollama model id appears at most once across all groups', async ({ baseURL }) => {
    // Failure mode: when the user adds a Custom provider (Settings →
    // Providers → Add Custom) pointing at their local Ollama daemon, the
    // SAME model winds up in both:
    //   - the "Ollama" group (Fox #337 splice in _splice_ollama_group)
    //   - the "Custom" group (upstream's get_available_models pulls from
    //     the custom endpoint's /v1/models list)
    // Users see "llama3.2:3b" twice in the dropdown, pick the wrong one,
    // hit a routing error. The fix dedups by canonical model id at splice
    // time, preferring the Ollama-group entry (since it's the more
    // reliable code path).
    //
    // PRECONDITION: this spec needs a way to seed a Custom provider
    // pointing at a mock Ollama endpoint. v0.7.20 will need either:
    //   (a) /test/seed-provider hook with a known dup model id, OR
    //   (b) a mock Ollama daemon process the CI smoke job spins up
    //       alongside the container (more involved).
    // Until the seeding approach is decided in the v0.7.20 PR, the
    // assertion below is a placeholder shape.
    const api = await request.newContext({ baseURL });
    await api.post('/test/reset');
    // TODO(v0.7.20): seed a Custom provider that exposes a model id
    // also expected from the Ollama daemon, so the dedup path is
    // actually exercised. As written, the assertion passes trivially
    // when no real Ollama models are present (CI container has no
    // daemon) — the spec ships in this skipped state as a contract
    // skeleton for the v0.7.20 implementation.

    const res = await api.get('/api/models');
    const data = await res.json();

    const idCounts = new Map<string, number>();
    for (const g of data.groups || []) {
      for (const m of g.models || []) {
        if (typeof m?.id !== 'string') continue;
        // Skip Fox's synthetic __ollama_hint:* entries — they're never
        // selectable and dedup doesn't apply.
        if (m.id.startsWith('__ollama_hint:')) continue;
        idCounts.set(m.id, (idCounts.get(m.id) || 0) + 1);
      }
    }
    const dupes = [...idCounts.entries()].filter(([, n]) => n > 1);
    expect(
      dupes,
      `Found duplicate model ids across /api/models groups: ${JSON.stringify(dupes)}. ` +
        `Each model id must appear exactly once. #278 dedup logic in ` +
        `fox_overlay/webui_patches/config.py:_splice_ollama_group regressed.`,
    ).toEqual([]);
  });
});
