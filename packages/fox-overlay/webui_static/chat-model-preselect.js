/* Fox in the Box — chat model auto-preselect (#344, v0.7.20).
 *
 * Upstream's `populateModelDropdown` (forks/hermes-webui/static/ui.js:998)
 * applies `data.default_model` to the picker blindly. If the default doesn't
 * match any group (fresh install with only local Ollama, or only one provider
 * configured), the picker ends up with NO selection — user opens chat, can't
 * send a message, has to manually open the picker to discover that even one
 * model is available. @bsgdigital flagged this as a first-impression UX wart
 * in v0.7.18 smoke.
 *
 * Upstream already has `_applySessionModelFallback` (ui.js:886) that picks
 * the first selectable option, but only calls it from `syncTopbar` — not
 * from the initial-load / new-session path. Rather than patch upstream code
 * (anchor-drift risk + this is purely additive UX polish), this overlay
 * extension runs after DOM ready, checks if a model is selected, and if not
 * triggers the fallback.
 *
 * Non-selectable synthetic entries (the v0.7.18 #337 Ollama hint placeholders
 * with `__ollama_hint:` ID prefix) are skipped — picking one would have the
 * user "select" the install hint and then fail to send.
 *
 * If literally zero selectable models exist (no providers, no Ollama, no
 * local fallback), shows an explicit empty-state in the composer chip so
 * the user understands why the send button is disabled.
 */

(function () {
  'use strict';

  // Wait for DOM + a brief settle so upstream's populateModelDropdown has run.
  // Using a fixed delay rather than a MutationObserver because the picker
  // hydration is multi-pass (preselect → fetch /api/models → repaint) and
  // observing every mutation is more complex than just waiting it out.
  const SETTLE_MS = 400;

  // Synthetic entry prefix from packages/fox-overlay/fox_overlay/webui_patches/config.py:120+
  // (v0.7.18 #337 Ollama hint placeholders). These IDs are non-selectable.
  const HINT_PREFIX = '__ollama_hint:';

  function isUsableModelOption(opt) {
    if (!opt || !opt.value) return false;
    if (opt.disabled) return false;
    if (opt.value.startsWith(HINT_PREFIX)) return false;
    if (opt.value.startsWith('__')) return false;  // any sentinel
    return true;
  }

  function findFirstUsableModel() {
    const sel = document.getElementById('modelSelect');
    if (!sel) return null;
    for (const opt of sel.options) {
      if (isUsableModelOption(opt)) return opt;
    }
    return null;
  }

  function showEmptyStateInChip() {
    const chip = document.getElementById('composerModelLabel')
      || document.getElementById('composerModelChip');
    if (!chip) return;
    chip.textContent = 'Model not selected';
    chip.title = 'Add a provider key in Settings → Providers, or install Ollama on your host';
    // Visual hint via title attribute; no CSS class change to avoid clashing
    // with upstream styling. The text itself is the signal.
  }

  function autoPreselect() {
    const sel = document.getElementById('modelSelect');
    if (!sel) return;

    // Already has a real selection? Honor it.
    const currentOpt = sel.selectedOptions[0];
    if (currentOpt && isUsableModelOption(currentOpt)) return;

    const firstUsable = findFirstUsableModel();
    if (!firstUsable) {
      showEmptyStateInChip();
      return;
    }

    // Pick the first usable option + fire a change event so upstream's
    // session-state machinery records the selection.
    sel.value = firstUsable.value;
    sel.dispatchEvent(new Event('change', { bubbles: true }));
  }

  function init() {
    setTimeout(autoPreselect, SETTLE_MS);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, { once: true });
  } else {
    init();
  }
})();
