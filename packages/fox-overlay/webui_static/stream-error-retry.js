/*
 * stream-error-retry.js — Fox in the Box v0.6.1
 *
 * Universal "Something went wrong, please try again" + Retry panel for any
 * streaming-time error from the server. Replaces FITB#89 (mid-stream break
 * detection) + FITB#129b (silent auto-failover on auth/quota) — both lost
 * in v0.6.0 when upstream refactored streaming. Closes FITB#254 + #255.
 *
 * Strategy: subscribe to upstream's stable `apperror` SSE event as a
 * downstream consumer. We do not patch upstream code; we just attach a
 * second listener to every EventSource the page creates and run AFTER
 * upstream's own handler. This means upstream can refactor its handler
 * however it likes — as long as the `apperror` event name + payload
 * shape (`{type, message, hint}`) stay stable, we work.
 *
 * The static asset overlay is loaded via HERMES_WEBUI_EXTENSION_DIR and
 * runs after the bundle. Globals available at runtime: S, send, $,
 * renderMessages.
 */
(function () {
  'use strict';

  // Error types we react to. Every type the server emits goes through
  // put('apperror', _provider_error_payload(...)) — see streaming.py:4102
  // and 4924. The handler in messages.js at line 1727 enumerates these
  // types in its label-mapping. We intentionally OMIT `cancelled`
  // because the user clicked Stop and doesn't need a retry prompt.
  // `unknown` catches any new type upstream introduces in the future.
  var RETRY_ELIGIBLE_TYPES = {
    auth_mismatch: true,
    quota_exhausted: true,
    rate_limit: true,
    model_not_found: true,
    interrupted: true,
    no_response: true,
    silent_failure: true,
    unknown: true
  };

  // Only react when the SSE stream is the main chat stream. The "BTW"
  // sub-stream + any future SSE endpoint should not pop our panel.
  function isMainChatStream(url) {
    if (!url) return false;
    var s = String(url);
    return s.indexOf('/api/chat/stream') !== -1 || s.indexOf('/api/chat/start') !== -1;
  }

  function $$(id) {
    return typeof document !== 'undefined' ? document.getElementById(id) : null;
  }

  function escapeHtml(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function removeExistingPanel() {
    if (typeof document === 'undefined') return;
    var existing = document.querySelectorAll('[data-fitb-retry-panel]');
    for (var i = 0; i < existing.length; i++) {
      existing[i].parentNode && existing[i].parentNode.removeChild(existing[i]);
    }
  }

  // Find the messages container in the DOM. Upstream renders into #chat
  // (the main scroll area). Fall back to body if the structure shifts —
  // the panel still renders, just less visually anchored.
  function findChatContainer() {
    return $$('chat') || (typeof document !== 'undefined' && document.querySelector('main')) || (typeof document !== 'undefined' && document.body) || null;
  }

  // Pull the last user message text from S.messages so Retry can re-send
  // it. Returns null if no user message exists (shouldn't happen in
  // practice — the apperror only fires after a user message).
  function lastUserText() {
    try {
      if (!window.S || !Array.isArray(window.S.messages)) return null;
      for (var i = window.S.messages.length - 1; i >= 0; i--) {
        var m = window.S.messages[i];
        if (m && m.role === 'user' && typeof m.content === 'string') return m.content;
      }
    } catch (_) {}
    return null;
  }

  // Pop the trailing apperror assistant message + the prior user message
  // from S.messages, then re-render. Wipes partial assistant text + lets
  // send() re-push the user message cleanly without duplicating it.
  function rewindForRetry() {
    try {
      if (!window.S || !Array.isArray(window.S.messages)) return;
      // The apperror handler in messages.js just pushed the error
      // assistant message; pop it.
      var last = window.S.messages[window.S.messages.length - 1];
      if (last && last.role === 'assistant') window.S.messages.pop();
      // Now pop the prior user message so send() can re-push it.
      var prev = window.S.messages[window.S.messages.length - 1];
      if (prev && prev.role === 'user') window.S.messages.pop();
      if (typeof window.renderMessages === 'function') {
        window.renderMessages({ preserveScroll: true });
      }
    } catch (_) {}
  }

  // Render the Fox retry panel just below the chat area. Idempotent —
  // calling twice replaces the prior panel.
  function renderRetryPanel() {
    var container = findChatContainer();
    if (!container || typeof document === 'undefined') return;
    removeExistingPanel();
    var panel = document.createElement('div');
    panel.setAttribute('data-fitb-retry-panel', '1');
    panel.className = 'fitb-retry-panel';
    panel.innerHTML =
      '<div class="fitb-retry-panel-title">Something went wrong</div>' +
      '<div class="fitb-retry-panel-body">Please try again. Your last message will be re-sent.</div>' +
      '<div class="fitb-retry-panel-actions">' +
        '<button type="button" class="fitb-btn fitb-btn-primary" data-fitb-retry-action="retry">Retry</button>' +
        '<button type="button" class="fitb-btn fitb-btn-link" data-fitb-retry-action="dismiss">Dismiss</button>' +
      '</div>';
    container.appendChild(panel);

    var retryBtn = panel.querySelector('[data-fitb-retry-action="retry"]');
    var dismissBtn = panel.querySelector('[data-fitb-retry-action="dismiss"]');

    if (retryBtn) retryBtn.addEventListener('click', function () {
      var text = lastUserText();
      if (text == null) { removeExistingPanel(); return; }
      rewindForRetry();
      var input = $$('msg');
      if (input) {
        input.value = text;
        // The composer's autoResize() fires on input event; nudge it.
        try { input.dispatchEvent(new Event('input', { bubbles: true })); } catch (_) {}
      }
      removeExistingPanel();
      // send() reads from $('msg').value and re-pushes the user message.
      try { if (typeof window.send === 'function') window.send(); } catch (_) {}
    });

    if (dismissBtn) dismissBtn.addEventListener('click', removeExistingPanel);
  }

  // Handler attached to every EventSource. Defers via setTimeout(0) so
  // upstream's own handler runs first and completes its DOM mutations.
  function onAppError(e) {
    setTimeout(function () {
      var d = null;
      try { d = JSON.parse(e && e.data); } catch (_) { d = {}; }
      var type = d && d.type ? String(d.type) : 'unknown';
      if (!RETRY_ELIGIBLE_TYPES[type]) {
        // Cancelled / anything else we deliberately ignore.
        return;
      }
      renderRetryPanel();
    }, 0);
  }

  // Wrap window.EventSource so every new EventSource(url, init) the page
  // creates auto-attaches our apperror listener (only when the URL is
  // the main chat stream). Idempotent — calling install() twice is a
  // no-op after the first call.
  var INSTALLED = false;
  function install() {
    if (INSTALLED) return;
    if (typeof window === 'undefined' || typeof window.EventSource === 'undefined') {
      // Browser doesn't expose EventSource (or upstream switched to
      // fetch+ReadableStream). Surface a one-time console warning so we
      // notice during smoke; do nothing further.
      try { console.warn('[fitb] stream-error-retry: EventSource not available; panel will not fire'); } catch (_) {}
      return;
    }
    INSTALLED = true;
    var NativeEventSource = window.EventSource;
    function WrappedEventSource(url, init) {
      var es = new NativeEventSource(url, init);
      if (isMainChatStream(url)) {
        try { es.addEventListener('apperror', onAppError); } catch (_) {}
      }
      return es;
    }
    // Preserve the static constants + prototype chain so anything that
    // does `instanceof EventSource` or reads CONNECTING/OPEN/CLOSED keeps
    // working.
    WrappedEventSource.prototype = NativeEventSource.prototype;
    WrappedEventSource.CONNECTING = NativeEventSource.CONNECTING;
    WrappedEventSource.OPEN = NativeEventSource.OPEN;
    WrappedEventSource.CLOSED = NativeEventSource.CLOSED;
    window.EventSource = WrappedEventSource;
  }

  // Install once the DOM is ready. messages.js may already have run by
  // then; that's fine — we wrap the constructor, so the NEXT EventSource
  // creation picks up our listener (every send() creates a new one).
  if (typeof document !== 'undefined' && document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', install);
  } else {
    install();
  }
})();
