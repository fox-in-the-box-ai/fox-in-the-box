/* Fox in the Box — model picker filter (#304, v0.7.29).
 *
 * Upstream populates the model picker with the full static catalog: every
 * Anthropic, OpenAI, Cohere, Groq, etc. model, regardless of whether the
 * user has a key for any of them. New users see dozens of models they can't
 * use; selecting one fails silently with a 401.
 *
 * This extension hides optgroups for providers the user hasn't configured,
 * leaving only:
 *   (A) Groups for providers with a configured key (from window._configuredModelBadges)
 *   (B) The Ollama group (always visible — #337, free/keyless)
 *   (C) The active provider's group (window._activeProvider)
 *
 * A "Show all models" link is appended to the picker so power users can
 * reveal the full catalog. The preference is persisted in sessionStorage
 * so a page refresh respects it within the same session.
 *
 * Implementation notes:
 * - Runs after a settle delay so upstream's populateModelDropdown has
 *   already built the optgroups (same pattern as chat-model-preselect.js).
 * - Uses a MutationObserver to re-apply the filter when the picker is
 *   repopulated (live-model fetch can replace the optgroup list).
 * - Fallback: if _configuredModelBadges is empty and _activeProvider is
 *   null (truly fresh install), no hiding happens — the full catalog is
 *   shown so the user can discover what providers exist.
 */

(function () {
  'use strict';

  const HINT_PREFIX = '__ollama_hint:';
  const SHOW_ALL_KEY = 'fitb-model-picker-show-all';
  const SETTLE_MS = 600;

  // Providers always visible regardless of key state.
  const ALWAYS_VISIBLE = new Set(['ollama']);

  function getConfiguredProviders() {
    const badges = window._configuredModelBadges || {};
    const providers = new Set();
    for (const [, badge] of Object.entries(badges)) {
      const p = badge && badge.provider;
      if (p && typeof p === 'string') providers.add(p.toLowerCase());
    }
    const active = window._activeProvider;
    if (active && typeof active === 'string') providers.add(active.toLowerCase());
    return providers;
  }

  function shouldShowAll() {
    return sessionStorage.getItem(SHOW_ALL_KEY) === '1';
  }

  function applyFilter(sel) {
    const configured = getConfiguredProviders();
    // If nothing is configured yet, show everything — user is in discovery mode.
    if (configured.size === 0) return;
    if (shouldShowAll()) return;

    let hiddenCount = 0;
    for (const og of sel.querySelectorAll('optgroup')) {
      const providerId = (og.dataset.provider || og.label || '').toLowerCase();
      const isAlwaysVisible = ALWAYS_VISIBLE.has(providerId);
      const isConfigured = configured.has(providerId);

      // Also show if any option inside has a configured model id.
      const hasConfiguredModel = Array.from(og.options).some(
        opt => opt.value && !opt.value.startsWith(HINT_PREFIX)
          && window._configuredModelBadges
          && Object.prototype.hasOwnProperty.call(window._configuredModelBadges, opt.value),
      );

      if (!isAlwaysVisible && !isConfigured && !hasConfiguredModel) {
        og.hidden = true;
        hiddenCount++;
      } else {
        og.hidden = false;
      }
    }

    // Append "Show all" link if any groups were hidden and it isn't there yet.
    if (hiddenCount > 0 && !sel.parentElement.querySelector('.fitb-show-all-models')) {
      const link = document.createElement('div');
      link.className = 'fitb-show-all-models';
      link.style.cssText = 'font-size:11px;text-align:center;padding:4px;cursor:pointer;opacity:0.6;';
      link.textContent = 'Show all models';
      link.title = 'Show models for providers you haven\'t configured yet';
      link.addEventListener('click', function () {
        sessionStorage.setItem(SHOW_ALL_KEY, '1');
        link.remove();
        applyFilter(sel); // re-run with show-all = true
      });
      sel.parentElement.appendChild(link);
    } else if (hiddenCount === 0) {
      sel.parentElement.querySelector('.fitb-show-all-models')?.remove();
    }
  }

  let _observer = null;

  function attachObserver(sel) {
    if (_observer) { _observer.disconnect(); _observer = null; }
    _observer = new MutationObserver(() => applyFilter(sel));
    _observer.observe(sel, { childList: true, subtree: true });
  }

  function init() {
    const sel = document.getElementById('modelSelect');
    if (!sel) return;
    applyFilter(sel);
    attachObserver(sel);
  }

  function setup() {
    setTimeout(init, SETTLE_MS);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', setup, { once: true });
  } else {
    setup();
  }
})();
