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
// require TEST INFRASTRUCTURE we don't have yet:
//   1. The empty-state branch loads `/` but a fresh container redirects to
//      `/setup` (v0.7.13 patch 003 onboarding redirect). No #composerModelLabel
//      element exists on /setup. Need a `/test/skip-onboarding` or
//      `/test/seed-onboarding-complete` hook.
//   2. The with-provider branch needs a `/test/seed-provider` hook to
//      configure exactly one provider with a known key so the assertion
//      runs deterministically.
// Filed as v0.7.22+ work (separate issue for the seed-provider/skip-onboarding
// hooks). Unskip THEN — not until the infrastructure exists.
test.describe.skip('Phase 1 — #344 chat auto-preselect (fix shipped v0.7.20; unskip pending test infrastructure)', () => {
  test('with NO providers configured, picker chip shows explicit empty state', async ({
    page,
    baseURL,
  }) => {
    // Failure mode: pre-v0.7.20, opening / on a fresh container without any
    // configured provider leaves the model chip label empty — users see a
    // bare chevron and don't know why nothing happens when they hit send.
    // The v0.7.20 fix must surface explicit copy so users know to go to
    // Settings → Providers.
    const api = await request.newContext({ baseURL });
    await api.post('/test/reset');

    // Skip onboarding-redirect by visiting / and letting the wizard
    // auto-dismiss. (Implementation detail of v0.7.20 — this spec needs
    // a way to land on the chat view with zero providers configured.
    // The v0.7.20 PR will need to either expose a /test/skip-onboarding
    // hook or change the redirect to allow chat-with-empty-providers.)
    await page.goto('/');
    // Composer model chip is the user-visible model picker label.
    const chip = page.locator('#composerModelLabel');
    await expect(
      chip,
      'composerModelLabel must contain explicit empty-state copy (e.g. ' +
        '"Model not selected") when no providers are configured. A blank label ' +
        'is the v0.7.19 bug #344 is filed against.',
    ).toContainText(/model not selected|no model|select.*model/i, { timeout: 5000 });
  });

  test('with at least one provider configured, picker auto-selects a usable model', async ({
    page,
    baseURL,
  }) => {
    // Failure mode: pre-v0.7.20, even after the user finishes onboarding
    // and configures a provider, the picker can show blank until they
    // manually click and pick a model. #344 is the bug where the chip
    // is empty on first chat render despite an active_provider being set.
    //
    // PRECONDITION: this spec needs a way to seed a configured provider
    // from the test side. The v0.7.20 fix will likely include a
    // /test/seed-provider hook (or equivalent) — verify the seeding
    // approach against the v0.7.20 PR before unskipping. Without that
    // hook this assertion can't run deterministically.
    const api = await request.newContext({ baseURL });
    await api.post('/test/reset');
    // TODO(v0.7.20): POST to a /test/seed-provider hook (or equivalent)
    // to configure exactly one provider with a known API key, so the
    // assertion below is deterministic.

    await page.goto('/');
    const chip = page.locator('#composerModelLabel');
    await expect(
      chip,
      'composerModelLabel must be non-empty after page load when a provider ' +
        'is configured. Empty chip = #344 regressed.',
    ).not.toHaveText('', { timeout: 5000 });
  });
});

// ── Phase 1 — #278 Ollama dedup across groups (fix shipped v0.7.20; infra pending) ──
// v0.7.21 STATUS: the #278 fix shipped in v0.7.20 via
// fox_overlay/webui_modules/ollama.py:459,492 (provider: "ollama" instead
// of "custom"). However this test still requires either:
//   (a) /test/seed-provider hook with a known dup model id, OR
//   (b) a mock Ollama daemon process the CI smoke job spins up alongside
//       the container.
// Without one of those, the assertion passes trivially (no real models →
// no dup possible). Unskip when the test harness exists — v0.7.22+ work.
test.describe.skip('Phase 1 — #278 Ollama dedup across groups (fix shipped v0.7.20; unskip pending test infrastructure)', () => {
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
