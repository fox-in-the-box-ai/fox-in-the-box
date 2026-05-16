/* Fox in the Box — post-wizard hostname prompt (issue #68).
 *
 * Once after onboarding finishes, if Tailscale is running and the user has
 * not explicitly set FOX_HOSTNAME, surface a one-time modal that lets them
 * pick a friendly tailnet name. Both Save and Skip persist
 * settings.json:hostname_prompted=true so the modal never re-fires.
 *
 * Reuses the existing #44 endpoints:
 *   GET  /api/settings/hostname               → state + prompted flag
 *   POST /api/settings/hostname               → save + auto-marks prompted
 *   POST /api/settings/hostname/dismiss-prompt → mark prompted, no save
 */

(function () {
  'use strict';

  function escapeHtml(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  async function fetchJson(url) {
    const res = await fetch(url, { credentials: 'same-origin' });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    return res.json();
  }

  async function postJson(url, body) {
    const res = await fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {}),
    });
    return { ok: res.ok, data: await res.json().catch(() => ({})) };
  }

  function shouldShow(state) {
    if (!state) return false;
    if (state.prompted) return false;            // already answered
    if (state.configured) return false;          // user already set it (Settings or env)
    // QA fix: don't fire while Tailscale is NeedsLogin / NeedsMachineAuth /
    // Starting / Stopped / NoState. Self.HostName is populated as soon as
    // the daemon knows its own preferred name, well before BackendState
    // becomes Running. Firing pre-Running confused users into clicking
    // Skip ("why are you asking? I haven't even connected yet"), and
    // because Skip persists prompted=true, they never got the prompt
    // again after they actually joined the tailnet.
    if (state.backend_state !== 'Running') return false;
    return true;
  }

  function buildModal(suggestion) {
    const wrap = document.createElement('div');
    wrap.className = 'fitb-hostname-modal-backdrop';
    wrap.setAttribute('role', 'dialog');
    wrap.setAttribute('aria-modal', 'true');
    wrap.setAttribute('aria-labelledby', 'fitbHostnameTitle');
    wrap.innerHTML = `
      <div class="fitb-hostname-modal">
        <h2 id="fitbHostnameTitle">Name this Fox</h2>
        <p>It'll show up on your tailnet so you can recognize this device. You can change it any time in Settings.</p>
        <label for="fitbHostnameInput">Hostname</label>
        <input id="fitbHostnameInput" type="text" value="${escapeHtml(suggestion || '')}" autocomplete="off" spellcheck="false">
        <div class="fitb-hostname-status" id="fitbHostnameStatus"></div>
        <div class="fitb-hostname-actions">
          <button type="button" class="fitb-btn fitb-btn-link" id="fitbHostnameSkip">Skip</button>
          <button type="button" class="fitb-btn fitb-btn-primary" id="fitbHostnameSave">Save</button>
        </div>
      </div>
    `;
    return wrap;
  }

  function close(wrap) {
    if (wrap && wrap.parentNode) wrap.parentNode.removeChild(wrap);
  }

  async function onSave(wrap) {
    const input = wrap.querySelector('#fitbHostnameInput');
    const status = wrap.querySelector('#fitbHostnameStatus');
    const save = wrap.querySelector('#fitbHostnameSave');
    const skip = wrap.querySelector('#fitbHostnameSkip');
    const raw = (input && input.value || '').trim();
    if (!raw) {
      if (status) status.textContent = 'Pick a name or click Skip.';
      return;
    }
    if (status) status.textContent = 'Applying…';
    if (save) save.disabled = true;
    if (skip) skip.disabled = true;
    const r = await postJson('/api/settings/hostname', { hostname: raw });
    if (!r.ok || !r.data || !r.data.ok) {
      if (status) status.textContent = (r.data && r.data.error) || 'Failed to apply hostname.';
      if (save) save.disabled = false;
      if (skip) skip.disabled = false;
      return;
    }
    close(wrap);
  }

  async function onSkip(wrap) {
    const skip = wrap.querySelector('#fitbHostnameSkip');
    const save = wrap.querySelector('#fitbHostnameSave');
    if (skip) skip.disabled = true;
    if (save) save.disabled = true;
    // Best-effort — even if the dismiss call fails, close the modal so the
    // user isn't trapped. They can re-trigger by clearing settings.json,
    // and they always have the Settings → Hostname tile.
    try { await postJson('/api/settings/hostname/dismiss-prompt', {}); } catch (e) {}
    close(wrap);
  }

  async function maybePrompt() {
    let state;
    try {
      state = await fetchJson('/api/settings/hostname');
    } catch (e) {
      return;  // network or 4xx — silent, this is non-critical UX
    }
    if (!shouldShow(state)) return;

    const wrap = buildModal(state.default_suggestion || '');
    document.body.appendChild(wrap);
    const input = wrap.querySelector('#fitbHostnameInput');
    if (input) {
      input.focus();
      input.setSelectionRange(0, input.value.length);
    }
    wrap.querySelector('#fitbHostnameSave').addEventListener('click', () => onSave(wrap));
    wrap.querySelector('#fitbHostnameSkip').addEventListener('click', () => onSkip(wrap));
    if (input) {
      input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') onSave(wrap);
      });
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', maybePrompt);
  } else {
    maybePrompt();
  }
})();
