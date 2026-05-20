/* Fox in the Box — local-fallback polish (issue #9 deferred polish).
 *
 * Two pieces of UX layered on top of v0.4.1's silent failover:
 *
 *   1. Reactive modal — when a chat stream fails on a remote provider AND
 *      the user has NOT opted into local fallback, surface a one-time
 *      modal offering to enable it. Listens to `fitb:stream-error`
 *      dispatched from messages.js (apperror SSE handler).
 *
 *   2. Recovery banner — when local fallback IS enabled, periodically
 *      probe the user's primary remote provider's reachability via the
 *      backend's lightweight remote-health endpoint. If remote is back,
 *      show a top banner offering to switch off local fallback.
 *
 * Both use sessionStorage for "don't re-fire this session" flags so the
 * UI doesn't pester the user. State resets on page reload.
 */

(function () {
  'use strict';

  const MODAL_DISMISSED = 'fitb.fallback_modal_seen';
  // FITB#129d: separate dismiss flag for the download-confirm modal so
  // declining "download local model" doesn't also lock out the regular
  // "enable fallback" reactive modal (or vice versa).
  const UNPREPARED_DISMISSED = 'fitb.local_unprepared_dismissed';
  const BANNER_DISMISSED = 'fitb.recovery_banner_dismissed';
  const RECOVERY_POLL_MS = 90 * 1000;
  // Error types the modal reacts to. The original logic excluded auth /
  // quota errors on the rationale that "local fallback can't fix the
  // user's wrong key / empty wallet." That reasoning misread the value
  // proposition: local fallback REPLACES the broken cloud entirely so
  // the user can keep working, regardless of why cloud is broken. Auth
  // and quota errors are exactly when local fallback should be offered.
  // FITB#122 #6.
  //
  // Backend error types come from api/streaming.py: 'quota_exhausted',
  // 'auth_mismatch', 'stream_interrupted', 'no_response'. The previous
  // 'rate_limit' entry was dead — backend never emits it.
  const ELIGIBLE_TYPES = new Set([
    'auth_mismatch', 'quota_exhausted',
    'stream_interrupted', 'no_response', 'unknown',
  ]);

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

  // ── Reactive modal (offer enable when remote breaks) ────────────────────

  function buildModal() {
    const wrap = document.createElement('div');
    wrap.className = 'fitb-fb-modal-backdrop';
    wrap.setAttribute('role', 'dialog');
    wrap.setAttribute('aria-modal', 'true');
    wrap.setAttribute('aria-labelledby', 'fitbFbModalTitle');
    wrap.innerHTML = `
      <div class="fitb-fb-modal">
        <h2 id="fitbFbModalTitle">Your provider is having trouble</h2>
        <p>Want to enable a local AI model as a fallback? It runs on your computer, so chats keep working when your provider is rate-limited, down, or offline. ~2.5 GB download the first time.</p>
        <div class="fitb-fb-modal-status" id="fitbFbModalStatus"></div>
        <div class="fitb-fb-modal-actions">
          <button type="button" class="fitb-btn fitb-btn-link" id="fitbFbModalDismiss">Not now</button>
          <button type="button" class="fitb-btn fitb-btn-primary" id="fitbFbModalEnable">Enable local fallback</button>
        </div>
      </div>
    `;
    return wrap;
  }

  function closeNode(n) { if (n && n.parentNode) n.parentNode.removeChild(n); }

  // Module-level guard against duplicate concurrent renders. sessionStorage
  // is the cross-error/cross-reload guard; this is a tighter "is one open
  // RIGHT NOW in this tab" guard so two stream-errors firing 50ms apart
  // don't stack.
  let _modalOpen = false;

  async function showReactiveModal() {
    if (sessionStorage.getItem(MODAL_DISMISSED)) return;
    if (_modalOpen) return;
    if (document.querySelector('.fitb-fb-modal-backdrop')) return;  // safety
    _modalOpen = true;

    const wrap = buildModal();
    document.body.appendChild(wrap);

    const enable = wrap.querySelector('#fitbFbModalEnable');
    const dismiss = wrap.querySelector('#fitbFbModalDismiss');
    const status = wrap.querySelector('#fitbFbModalStatus');

    // QA fix v0.4.7-WaveF: removeEventListener inside closeAndDismiss too,
    // not just inside the Escape handler. Otherwise Dismiss/Enable paths
    // leave a `keydown` listener attached with a closed-over `wrap` node
    // for the rest of the session.
    const closeAndDismiss = (markSeen) => {
      _modalOpen = false;
      if (markSeen) sessionStorage.setItem(MODAL_DISMISSED, '1');
      document.removeEventListener('keydown', onKey);
      closeNode(wrap);
    };

    const onKey = (e) => {
      if (e.key === 'Escape') closeAndDismiss(true);
    };
    document.addEventListener('keydown', onKey);

    dismiss.addEventListener('click', () => closeAndDismiss(true));
    enable.addEventListener('click', async () => {
      enable.disabled = true;
      dismiss.disabled = true;
      status.textContent = 'Enabling…';
      const r = await postJson('/api/local-fallback/enable', {});
      if (!r.ok || !r.data || r.data.enabled === false) {
        // QA fix: previously sessionStorage MODAL_DISMISSED was set on entry,
        // so a failed enable left the modal locked-out for the rest of the
        // session even though the user never successfully enabled. Now we
        // only mark dismissed on explicit dismiss or success path — failure
        // re-enables the buttons so the user can retry.
        status.textContent = (r.data && r.data.error) || 'Failed to enable.';
        enable.disabled = false;
        dismiss.disabled = false;
        return;
      }
      status.textContent = 'Enabled. Your next failure will silently use local.';
      // Recovery banner can now start polling — it boots its own poll loop
      // by listening for storage events would be complex, so we just nudge
      // the next page load to start it. For this session, that's fine.
      setTimeout(() => closeAndDismiss(true), 1500);
    });
  }

  // FITB#128: provider-not-responding modal variant. Different copy +
  // action from showReactiveModal (which is for explicit error events).
  // This one fires when the SSE stream opens but no event arrives within
  // the configured window. Auto-dismisses if a real event arrives late.
  let _timeoutModalNode = null;
  async function showTimeoutModal() {
    if (_modalOpen) return;
    if (_timeoutModalNode) return;  // already showing

    const wrap = document.createElement('div');
    wrap.className = 'fitb-fb-modal-backdrop';
    wrap.innerHTML = `
      <div class="fitb-fb-modal" role="dialog" aria-modal="true" aria-labelledby="fitbTimeoutTitle">
        <div class="fitb-fb-modal-title" id="fitbTimeoutTitle">Provider isn't responding</div>
        <div class="fitb-fb-modal-body">Your AI provider hasn't sent a response yet. Switch to a local model to keep working — your message can be re-sent against the local model immediately.</div>
        <div class="fitb-fb-modal-status" id="fitbTimeoutStatus"></div>
        <div class="fitb-fb-modal-actions">
          <button type="button" class="fitb-btn fitb-btn-link" id="fitbTimeoutCancel">Keep waiting</button>
          <button type="button" class="fitb-btn fitb-btn-primary" id="fitbTimeoutSwitch">Switch to local now</button>
        </div>
      </div>
    `;
    document.body.appendChild(wrap);
    _timeoutModalNode = wrap;
    _modalOpen = true;

    const switchBtn = wrap.querySelector('#fitbTimeoutSwitch');
    const cancelBtn = wrap.querySelector('#fitbTimeoutCancel');
    const status = wrap.querySelector('#fitbTimeoutStatus');

    const dismiss = () => {
      _modalOpen = false;
      _timeoutModalNode = null;
      document.removeEventListener('keydown', onKey);
      window.removeEventListener('fitb:provider-resumed', onResume);
      closeNode(wrap);
    };

    const onKey = (e) => { if (e.key === 'Escape') dismiss(); };
    const onResume = () => dismiss();  // late SSE arrival → auto-dismiss
    document.addEventListener('keydown', onKey);
    window.addEventListener('fitb:provider-resumed', onResume);

    cancelBtn.addEventListener('click', dismiss);
    switchBtn.addEventListener('click', async () => {
      switchBtn.disabled = true;
      cancelBtn.disabled = true;
      status.textContent = 'Switching…';
      const r = await postJson('/api/local-fallback/activate', {});
      if (r.ok && r.data && r.data.ok) {
        status.textContent = 'Switched to local. Re-send your message to use it.';
        setTimeout(dismiss, 2500);
        return;
      }
      // Granular error reasons from #129a's activate(): translate each
      // into actionable user-facing copy. None re-enable Switch (the
      // condition won't change without user action elsewhere) — Cancel
      // re-enables to let them dismiss and act in Settings.
      const reason = (r.data && r.data.reason) || '';
      const errMsg = (r.data && r.data.error) || 'Could not switch to local.';
      if (reason === 'disabled') {
        status.innerHTML = 'Local fallback is off. Enable it in <strong>Settings → Providers → Local fallback</strong>, then try again.';
      } else if (reason === 'missing-model') {
        status.innerHTML = 'Local model not downloaded yet. Enable local fallback in <strong>Settings → Providers</strong> to start the ~2.5 GB download.';
      } else if (reason === 'unhealthy') {
        status.textContent = 'Local model is warming up. Try again in a few seconds.';
        switchBtn.disabled = false;  // unhealthy may resolve quickly
      } else {
        status.textContent = errMsg;
      }
      cancelBtn.disabled = false;
    });
  }

  async function maybeReactToError(detail) {
    if (sessionStorage.getItem(MODAL_DISMISSED)) return;
    if (!detail || !ELIGIBLE_TYPES.has(detail.type)) return;
    // Check current opt-in state. If already enabled, the modal has nothing
    // to offer — local fallback already attempted to handle this and the
    // user is seeing the error precisely because both paths failed.
    let s;
    try {
      s = await fetchJson('/api/local-fallback/status');
    } catch (e) {
      return;
    }
    if (!s) return;
    if (s.enabled) return;  // already opted in
    if (s.ui_state === 'no-supervisor') return;  // outside container, can't run local
    if (s.ui_state === 'missing-model-registry') return;  // config broken
    showReactiveModal();
  }

  // ── FITB#129d: download-on-demand modal for unprepared local fallback ──

  function _formatBytes(n) {
    if (!n || n <= 0) return '';
    const units = ['B', 'KB', 'MB', 'GB'];
    let i = 0;
    while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
    return (n < 10 ? n.toFixed(1) : Math.round(n)) + ' ' + units[i];
  }

  let _unpreparedNode = null;
  let _unpreparedPollTimer = null;

  async function showUnpreparedDownloadModal(detail) {
    if (_modalOpen) return;
    if (_unpreparedNode) return;

    const reason = (detail && detail.reason) || 'unknown';
    const sizeBytes = (detail && detail.model_size_bytes) || 0;
    const sizeStr = sizeBytes ? ' (~' + _formatBytes(sizeBytes) + ')' : '';

    const wrap = document.createElement('div');
    wrap.className = 'fitb-fb-modal-backdrop';
    wrap.innerHTML = `
      <div class="fitb-fb-modal" role="dialog" aria-modal="true" aria-labelledby="fitbUnprepTitle">
        <div class="fitb-fb-modal-title" id="fitbUnprepTitle">Download local model to keep working</div>
        <div class="fitb-fb-modal-body">Your cloud provider failed (${escapeHtml(reason)}). Local fallback is enabled but the model isn't downloaded yet. Download Phi-4-mini${escapeHtml(sizeStr)} to chat without the cloud — your data stays on this machine.</div>
        <div class="fitb-fb-modal-status" id="fitbUnprepStatus"></div>
        <div class="fitb-fb-modal-actions">
          <button type="button" class="fitb-btn fitb-btn-link" id="fitbUnprepDismiss">Not now</button>
          <button type="button" class="fitb-btn fitb-btn-primary" id="fitbUnprepDownload">Download &amp; continue</button>
        </div>
      </div>
    `;
    document.body.appendChild(wrap);
    _unpreparedNode = wrap;
    _modalOpen = true;

    const downloadBtn = wrap.querySelector('#fitbUnprepDownload');
    const dismissBtn = wrap.querySelector('#fitbUnprepDismiss');
    const status = wrap.querySelector('#fitbUnprepStatus');

    const dismiss = (markSeen) => {
      _modalOpen = false;
      _unpreparedNode = null;
      if (_unpreparedPollTimer) { clearTimeout(_unpreparedPollTimer); _unpreparedPollTimer = null; }
      document.removeEventListener('keydown', onKey);
      if (markSeen) sessionStorage.setItem(UNPREPARED_DISMISSED, '1');
      closeNode(wrap);
    };

    const onKey = (e) => { if (e.key === 'Escape') dismiss(true); };
    document.addEventListener('keydown', onKey);
    dismissBtn.addEventListener('click', () => dismiss(true));

    downloadBtn.addEventListener('click', async () => {
      downloadBtn.disabled = true;
      dismissBtn.disabled = true;
      status.textContent = 'Starting download…';

      // Kick off the download — /enable starts the supervisord-managed
      // download via #10's manager and returns the current snapshot.
      let snap;
      try {
        const r = await postJson('/api/local-fallback/enable', {});
        if (!r.ok || !r.data) {
          status.textContent = 'Could not start the download. Check Settings → Providers.';
          dismissBtn.disabled = false;
          return;
        }
        snap = r.data;
      } catch (e) {
        status.textContent = 'Network error starting the download.';
        dismissBtn.disabled = false;
        return;
      }

      // Poll status until ready (or failure). Same UI loop pattern the
      // wizard uses for #69's bundled-llama.cpp progress.
      const tick = async () => {
        let s;
        try {
          s = await fetchJson('/api/local-fallback/status');
        } catch (e) {
          _unpreparedPollTimer = setTimeout(tick, 2500);
          return;
        }
        const ms = (s && s.model_state) || {};
        const downloaded = ms.bytes_downloaded || 0;
        const total = ms.bytes_total || s.model_size_bytes || 0;
        const pct = total > 0 ? Math.min(100, Math.floor((downloaded / total) * 100)) : 0;
        const ui = s.ui_state || '';
        if (ui === 'downloading') {
          status.textContent = total > 0
            ? `Downloading… ${_formatBytes(downloaded)} / ${_formatBytes(total)} (${pct}%)`
            : `Downloading… ${_formatBytes(downloaded)}`;
        } else if (ui === 'starting' || ui === 'warming') {
          status.textContent = 'Starting local model…';
        } else if (ui === 'ready' || s.ready) {
          status.textContent = 'Activating…';
          // Flip the gateway's active model to local now that it's ready.
          try {
            const r = await postJson('/api/local-fallback/activate', {});
            if (r.ok && r.data && r.data.ok) {
              status.textContent = 'Ready. Re-send your message to use the local model.';
              setTimeout(() => dismiss(true), 2500);
              return;
            }
            status.textContent = (r.data && r.data.error) || 'Could not activate local model.';
            dismissBtn.disabled = false;
          } catch (e) {
            status.textContent = 'Network error during activation.';
            dismissBtn.disabled = false;
          }
          return;
        } else if (ui === 'needs-download') {
          // Edge case: download didn't actually start. Surface clearly.
          status.textContent = 'Download did not start. Try again from Settings → Providers.';
          dismissBtn.disabled = false;
          return;
        }
        _unpreparedPollTimer = setTimeout(tick, 2500);
      };
      tick();
    });
  }

  // ── Recovery banner (offer switch-off when remote is back) ──────────────

  let _bannerNode = null;
  let _recoveryPollTimer = null;
  let _tabVisibilityTimer = null;

  // The recovery banner is contextually relevant only when the user is on the
  // Chat panel — it's a chat-flow nudge ("your remote provider's back, switch
  // off local fallback?"). On other panels (Settings, Workspaces, Insights, …)
  // it blocks page headings + isn't actionable. Hide it on non-Chat panels;
  // re-show when the user returns to Chat (FITB #147 part 2).
  //
  // Upstream's panel router writes the active panel name to `window._currentPanel`
  // (see forks/hermes-webui/static/panels.js — values: 'chat' | 'tasks' |
  // 'skills' | 'memory' | 'workspaces' | 'profiles' | 'todos' | 'insights' |
  // 'logs' | 'settings'). We poll it on a slow tick (500ms) while the banner
  // exists; the visible toggle is just an inline display style on the banner
  // node, so the DOM tree + event handlers are preserved across hide/show.
  function _isChatPanelActive() {
    const p = (typeof window._currentPanel === 'string' && window._currentPanel) || 'chat';
    return p === 'chat';
  }

  function startTabVisibilityWatch() {
    if (_tabVisibilityTimer) return;
    const tick = () => {
      if (!_bannerNode) {
        _tabVisibilityTimer = null;
        return;
      }
      _bannerNode.style.display = _isChatPanelActive() ? '' : 'none';
      _tabVisibilityTimer = setTimeout(tick, 500);
    };
    tick();
  }

  function stopTabVisibilityWatch() {
    if (_tabVisibilityTimer) {
      clearTimeout(_tabVisibilityTimer);
      _tabVisibilityTimer = null;
    }
  }

  function buildBanner() {
    const wrap = document.createElement('div');
    wrap.className = 'fitb-fb-banner';
    wrap.setAttribute('role', 'status');
    wrap.innerHTML = `
      <div class="fitb-fb-banner-text">Your remote provider looks reachable again. Switch off local fallback to use it?</div>
      <div class="fitb-fb-banner-actions">
        <button type="button" class="fitb-btn fitb-btn-link" id="fitbFbBannerDismiss">Keep local</button>
        <button type="button" class="fitb-btn fitb-btn-primary" id="fitbFbBannerSwitch">Switch back</button>
      </div>
    `;
    return wrap;
  }

  async function showRecoveryBanner() {
    if (sessionStorage.getItem(BANNER_DISMISSED)) return;
    if (_bannerNode) return;
    _bannerNode = buildBanner();
    document.body.appendChild(_bannerNode);
    startTabVisibilityWatch();

    const dismiss = _bannerNode.querySelector('#fitbFbBannerDismiss');
    const switchBtn = _bannerNode.querySelector('#fitbFbBannerSwitch');

    dismiss.addEventListener('click', () => {
      sessionStorage.setItem(BANNER_DISMISSED, '1');
      stopTabVisibilityWatch();
      closeNode(_bannerNode);
      _bannerNode = null;
    });
    switchBtn.addEventListener('click', async () => {
      switchBtn.disabled = true;
      dismiss.disabled = true;
      const r = await postJson('/api/local-fallback/disable', {});
      if (!r.ok || !r.data || r.data.enabled === true) {
        switchBtn.disabled = false;
        dismiss.disabled = false;
        return;
      }
      sessionStorage.setItem(BANNER_DISMISSED, '1');
      stopTabVisibilityWatch();
      closeNode(_bannerNode);
      _bannerNode = null;
      stopRecoveryPolling();
    });
  }

  async function recoveryTick() {
    if (sessionStorage.getItem(BANNER_DISMISSED)) {
      stopRecoveryPolling();
      return;
    }
    // QA fix: previously this kept polling forever even after the banner
    // was visible — a 90s heartbeat to the probe URLs for the lifetime
    // of the open tab. Once the banner is up, polling has no purpose
    // until the user dismisses or switches; the dismiss/switch handlers
    // restart polling if appropriate.
    if (_bannerNode) {
      stopRecoveryPolling();
      return;
    }
    let s;
    try {
      s = await fetchJson('/api/local-fallback/status');
    } catch (e) {
      _recoveryPollTimer = setTimeout(recoveryTick, RECOVERY_POLL_MS);
      return;
    }
    if (!s || !s.enabled) {
      // User toggled off in Settings — no banner needed.
      stopRecoveryPolling();
      return;
    }
    let h;
    try {
      h = await fetchJson('/api/local-fallback/remote-health');
    } catch (e) {
      _recoveryPollTimer = setTimeout(recoveryTick, RECOVERY_POLL_MS);
      return;
    }
    if (h && h.remote_healthy) {
      showRecoveryBanner();
      return;  // showRecoveryBanner sets _bannerNode; next-tick guard kicks in
    }
    _recoveryPollTimer = setTimeout(recoveryTick, RECOVERY_POLL_MS);
  }

  function startRecoveryPolling() {
    if (_recoveryPollTimer) return;
    // First tick after a short delay so we don't fire during page-load
    // contention.
    _recoveryPollTimer = setTimeout(recoveryTick, 5000);
  }

  function stopRecoveryPolling() {
    if (_recoveryPollTimer) {
      clearTimeout(_recoveryPollTimer);
      _recoveryPollTimer = null;
    }
  }

  // ── Boot ────────────────────────────────────────────────────────────────

  async function boot() {
    // Wire reactive modal
    window.addEventListener('fitb:stream-error', (e) => {
      maybeReactToError(e && e.detail);
    });

    // FITB#122 #7: also start recovery polling when the user enables
    // fallback after page load. Pre-fix this only fired if fallback was
    // already enabled at boot, so the most common flow (user hits a
    // provider failure → enables fallback in Settings → corrects key →
    // expects banner) silently never started polling.
    window.addEventListener('fitb:fallback-enabled', () => {
      startRecoveryPolling();
    });

    // FITB#128: provider-not-responding timeout. messages.js arms a timer
    // when the SSE stream opens; if no event arrives within N seconds it
    // fires this event. Different modal variant from the eligibility one
    // (different copy + Switch-now action that calls #129a's activate
    // endpoint), but reuses the same _modalOpen guard so they don't stack.
    window.addEventListener('fitb:provider-timeout', () => {
      showTimeoutModal();
    });

    // FITB#129d: backend wanted to fail over to local but the model
    // isn't downloaded yet. Modal offers the download with progress UI,
    // then activates. Detail carries the upstream failure context so the
    // modal can explain WHY we're prompting.
    window.addEventListener('fitb:local-unprepared', (e) => {
      if (sessionStorage.getItem(UNPREPARED_DISMISSED)) return;
      showUnpreparedDownloadModal(e && e.detail || {});
    });

    // Decide whether to start recovery polling for the steady-state case
    // (fallback was already enabled when this page loaded).
    let s;
    try {
      s = await fetchJson('/api/local-fallback/status');
    } catch (e) {
      return;
    }
    if (s && s.enabled && s.ui_state !== 'no-supervisor') {
      startRecoveryPolling();
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
