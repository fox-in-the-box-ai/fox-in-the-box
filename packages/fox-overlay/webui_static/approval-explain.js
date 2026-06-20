/* Fox in the Box — approval card explanation overlay (#150, v0.7.53).
 *
 * When the approval card appears (a command flagged for user review),
 * this overlay fires an async request to /api/approval-explain/ which
 * uses the auxiliary LLM to generate a one-sentence plain-English
 * explanation of what the command does.
 *
 * The explanation renders between the description and the raw command in
 * the approval card. If the LLM call fails, times out, or the card is
 * dismissed before the response arrives, the explanation element is
 * silently hidden — the card behaves identically to before this overlay.
 */

(function () {
  'use strict';

  var _seq = 0;

  var _origShowApprovalCard = window.showApprovalCard;
  if (typeof _origShowApprovalCard !== 'function') return;

  function _ensureExplainEl() {
    var el = document.getElementById('approvalExplain');
    if (el) return el;
    var desc = document.getElementById('approvalDesc');
    var cmd = document.getElementById('approvalCmd');
    if (!desc || !cmd) return null;
    el = document.createElement('div');
    el.id = 'approvalExplain';
    el.className = 'approval-explain';
    el.setAttribute('aria-live', 'polite');
    desc.parentNode.insertBefore(el, cmd);
    return el;
  }

  function _fetchExplanation(command, description, seq) {
    var el = _ensureExplainEl();
    if (!el) return;
    el.textContent = '';
    el.classList.remove('loaded');
    el.classList.add('loading');

    fetch('/api/approval-explain/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({ command: command, description: description }),
    })
      .then(function (r) {
        if (!r.ok) throw new Error(r.status);
        return r.json();
      })
      .then(function (data) {
        if (seq !== _seq) return;
        el = document.getElementById('approvalExplain');
        if (!el) return;
        el.classList.remove('loading');
        if (data && data.explanation) {
          el.textContent = data.explanation;
          el.classList.add('loaded');
        }
      })
      .catch(function () {
        if (seq !== _seq) return;
        el = document.getElementById('approvalExplain');
        if (el) {
          el.classList.remove('loading');
          el.textContent = '';
        }
      });
  }

  window.showApprovalCard = function (pending, pendingCount) {
    _origShowApprovalCard.call(this, pending, pendingCount);

    var command = (pending && pending.command) || '';
    var description = (pending && pending.description) || '';
    if (!command) return;

    _seq++;
    _fetchExplanation(command, description, _seq);
  };
})();
