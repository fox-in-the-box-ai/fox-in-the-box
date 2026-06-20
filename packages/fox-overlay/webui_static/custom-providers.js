/* Fox in the Box — custom OpenAI-compatible provider management (#144, v0.7.53).
 *
 * Injects an "Add Custom Provider" button and edit/delete controls into
 * Settings → Providers.  Talks to /api/settings/custom-providers/*.
 */

(function () {
  'use strict';

  var API_BASE = '/api/settings/custom-providers';
  var _initialized = false;
  var _formVisible = false;
  var _editingName = null;

  // ── Helpers ────────────────────────────────────────────────────────────

  function esc(s) {
    var d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
  }

  function $(id) { return document.getElementById(id); }

  function _api(path, body) {
    var opts = { credentials: 'same-origin', headers: { 'Content-Type': 'application/json' } };
    if (body !== undefined) {
      opts.method = 'POST';
      opts.body = JSON.stringify(body);
    }
    return fetch(API_BASE + (path || ''), opts).then(function (r) { return r.json(); });
  }

  // ── Container & injection point ────────────────────────────────────────

  function _getProvidersList() { return $('providersList'); }

  function _getOrCreateContainer() {
    var existing = $('foxCustomProviders');
    if (existing) return existing;
    var list = _getProvidersList();
    if (!list) return null;
    var container = document.createElement('div');
    container.id = 'foxCustomProviders';
    container.style.cssText = 'margin-top:16px;';
    list.parentNode.insertBefore(container, list.nextSibling);
    return container;
  }

  // ── Render ─────────────────────────────────────────────────────────────

  function _renderAll() {
    var container = _getOrCreateContainer();
    if (!container) return;

    _api().then(function (data) {
      if (!data || !data.ok) return;
      var providers = data.providers || [];
      var html = '';

      // Section header with add button
      html += '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">';
      html += '<div style="font-size:13px;font-weight:600;color:var(--text)">Custom Providers</div>';
      html += '<button type="button" id="foxCpAddBtn" style="' + _btnStyle('var(--accent)', 'white') + '">+ Add Provider</button>';
      html += '</div>';

      // Form area (hidden by default)
      html += '<div id="foxCpFormArea"></div>';

      // Provider cards
      if (providers.length === 0 && !_formVisible) {
        html += '<div style="text-align:center;padding:16px 0;color:var(--muted);font-size:13px">';
        html += 'No custom providers configured. Add one to connect Fox to llama.cpp, LM Studio, vLLM, or any OpenAI-compatible endpoint.';
        html += '</div>';
      }

      for (var i = 0; i < providers.length; i++) {
        html += _renderProviderCard(providers[i]);
      }

      container.innerHTML = html;

      // Wire add button
      var addBtn = $('foxCpAddBtn');
      if (addBtn) {
        addBtn.onclick = function () {
          _editingName = null;
          _formVisible = true;
          _showForm(null);
        };
      }

      if (_formVisible) {
        _showForm(_editingName ? _findProvider(providers, _editingName) : null);
      }

      // Wire edit/delete buttons
      var cards = container.querySelectorAll('[data-fox-cp-name]');
      for (var j = 0; j < cards.length; j++) {
        (function (card) {
          var name = card.getAttribute('data-fox-cp-name');
          var editBtn = card.querySelector('.fox-cp-edit');
          var deleteBtn = card.querySelector('.fox-cp-delete');
          var headerBtn = card.querySelector('.fox-cp-header');

          if (headerBtn) {
            headerBtn.onclick = function () { card.classList.toggle('open'); };
          }
          if (editBtn) {
            editBtn.onclick = function () {
              _editingName = name;
              _formVisible = true;
              var p = _findProvider(data.providers, name);
              _showForm(p);
            };
          }
          if (deleteBtn) {
            deleteBtn.onclick = function () {
              if (!confirm('Delete custom provider "' + name + '"?')) return;
              _api('/delete', { name: name }).then(function (r) {
                if (r && r.ok) {
                  _formVisible = false;
                  _editingName = null;
                  _renderAll();
                  _refreshUpstreamProviders();
                } else {
                  alert((r && r.error) || 'Delete failed.');
                }
              });
            };
          }
        })(cards[j]);
      }
    });
  }

  function _findProvider(list, name) {
    for (var i = 0; i < list.length; i++) {
      if (list[i].name === name) return list[i];
    }
    return null;
  }

  function _renderProviderCard(p) {
    var modelCount = Array.isArray(p.models) ? p.models.length : 0;
    var meta = modelCount + (modelCount === 1 ? ' model' : ' models');
    if (p.api_key) meta += ' · Key configured';

    var html = '<div class="provider-card" data-fox-cp-name="' + esc(p.name) + '">';
    html += '<button type="button" class="provider-card-header fox-cp-header">';
    html += '<div class="provider-card-info">';
    html += '<div class="provider-card-name">' + esc(p.name) + '</div>';
    html += '<div class="provider-card-meta">' + esc(meta) + '</div>';
    html += '</div>';
    html += '<svg class="provider-card-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" width="16" height="16"><path d="M6 9l6 6 6-6"/></svg>';
    html += '</button>';

    html += '<div class="provider-card-body">';
    html += '<div style="font-size:12px;color:var(--muted);margin-bottom:8px">';
    html += '<span style="font-weight:500">URL:</span> ' + esc(p.base_url);
    html += '</div>';
    if (modelCount > 0) {
      html += '<div style="font-size:12px;color:var(--muted);margin-bottom:8px">';
      html += '<span style="font-weight:500">Models:</span> ' + esc(p.models.join(', '));
      html += '</div>';
    }
    html += '<div style="display:flex;gap:8px;margin-top:8px">';
    html += '<button type="button" class="fox-cp-edit" style="' + _btnStyle('var(--accent)', 'white') + '">Edit</button>';
    html += '<button type="button" class="fox-cp-delete" style="' + _btnStyle('var(--error,#e53e3e)', 'white') + '">Delete</button>';
    html += '</div>';
    html += '</div>';
    html += '</div>';
    return html;
  }

  // ── Form ───────────────────────────────────────────────────────────────

  function _showForm(provider) {
    var area = $('foxCpFormArea');
    if (!area) return;

    var isEdit = provider !== null && provider !== undefined;

    var html = '<div style="background:var(--code-bg);border:1px solid var(--border2);border-radius:8px;padding:16px;margin-bottom:12px">';
    html += '<div style="font-size:13px;font-weight:600;margin-bottom:12px">' + (isEdit ? 'Edit Provider' : 'Add Custom Provider') + '</div>';

    html += _formField('foxCpName', 'Display Name', 'e.g. Home llama.cpp', isEdit ? provider.name : '', isEdit);
    html += _formField('foxCpUrl', 'Base URL', 'e.g. http://192.168.1.50:8080/v1', isEdit ? provider.base_url : '', false);
    html += _formField('foxCpKey', 'API Key (optional)', 'Leave empty if not required', '', false, true);
    html += _formField('foxCpModels', 'Models (comma-separated)', 'e.g. llama-3.1-8b-instruct, phi4-mini', isEdit ? (provider.models || []).join(', ') : '', false);

    // Test connection
    html += '<div style="display:flex;align-items:center;gap:8px;margin-top:12px">';
    html += '<button type="button" id="foxCpTestBtn" style="' + _btnStyle('var(--border2)', 'var(--text)') + '">Test Connection</button>';
    html += '<span id="foxCpTestResult" style="font-size:12px"></span>';
    html += '</div>';

    // Save / Cancel
    html += '<div style="display:flex;gap:8px;margin-top:12px">';
    html += '<button type="button" id="foxCpSaveBtn" style="' + _btnStyle('var(--accent)', 'white') + '">Save</button>';
    html += '<button type="button" id="foxCpCancelBtn" style="' + _btnStyle('var(--border2)', 'var(--text)') + '">Cancel</button>';
    html += '</div>';
    html += '</div>';

    area.innerHTML = html;

    // Wire buttons
    $('foxCpTestBtn').onclick = _doTest;
    $('foxCpSaveBtn').onclick = _doSave;
    $('foxCpCancelBtn').onclick = function () {
      _formVisible = false;
      _editingName = null;
      _renderAll();
    };
  }

  function _formField(id, label, placeholder, value, disabled, isPassword) {
    var type = isPassword ? 'password' : 'text';
    var disabledAttr = disabled ? ' disabled' : '';
    var autocomplete = isPassword ? ' autocomplete="off"' : '';
    return '<div style="margin-bottom:8px">' +
      '<label style="font-size:12px;color:var(--muted);display:block;margin-bottom:4px">' + esc(label) + '</label>' +
      '<input type="' + type + '" id="' + id + '" placeholder="' + esc(placeholder) + '" value="' + esc(value || '') + '"' + disabledAttr + autocomplete +
      ' style="width:100%;padding:8px;background:var(--bg);color:var(--text);border:1px solid var(--border2);border-radius:6px;font-size:13px;box-sizing:border-box">' +
      '</div>';
  }

  function _getFormValues() {
    return {
      name: ($('foxCpName') || {}).value || '',
      base_url: ($('foxCpUrl') || {}).value || '',
      api_key: ($('foxCpKey') || {}).value || '',
      models: (($('foxCpModels') || {}).value || '').split(',').map(function (s) { return s.trim(); }).filter(Boolean),
    };
  }

  function _doTest() {
    var vals = _getFormValues();
    var result = $('foxCpTestResult');
    var btn = $('foxCpTestBtn');
    if (!result || !btn) return;
    if (!vals.base_url) {
      result.textContent = 'Enter a Base URL first.';
      result.style.color = 'var(--error,#e53e3e)';
      return;
    }
    btn.disabled = true;
    btn.textContent = 'Testing...';
    result.textContent = '';

    _api('/test', { base_url: vals.base_url, api_key: vals.api_key || '' })
      .then(function (r) {
        btn.disabled = false;
        btn.textContent = 'Test Connection';
        if (r && r.ok) {
          var msg = 'Reachable';
          if (typeof r.models_found === 'number') {
            msg += ', ' + r.models_found + ' model' + (r.models_found === 1 ? '' : 's') + ' discovered';
          }
          result.textContent = msg;
          result.style.color = 'var(--success,#38a169)';
        } else {
          result.textContent = (r && r.error) || 'Connection failed.';
          result.style.color = 'var(--error,#e53e3e)';
        }
      })
      .catch(function () {
        btn.disabled = false;
        btn.textContent = 'Test Connection';
        result.textContent = 'Request failed.';
        result.style.color = 'var(--error,#e53e3e)';
      });
  }

  function _doSave() {
    var vals = _getFormValues();
    var btn = $('foxCpSaveBtn');
    if (!btn) return;
    btn.disabled = true;
    btn.textContent = 'Saving...';

    _api('', vals)
      .then(function (r) {
        btn.disabled = false;
        btn.textContent = 'Save';
        if (r && r.ok) {
          _formVisible = false;
          _editingName = null;
          _renderAll();
          _refreshUpstreamProviders();
        } else {
          alert((r && r.error) || 'Save failed.');
        }
      })
      .catch(function () {
        btn.disabled = false;
        btn.textContent = 'Save';
        alert('Save failed — network error.');
      });
  }

  // ── Refresh upstream provider list ─────────────────────────────────────

  function _refreshUpstreamProviders() {
    if (typeof window.loadProvidersPanel === 'function') {
      window.loadProvidersPanel();
    }
  }

  // ── Button style helper ────────────────────────────────────────────────

  function _btnStyle(bg, color) {
    return 'padding:6px 12px;border:none;border-radius:6px;font-size:12px;font-weight:600;cursor:pointer;background:' + bg + ';color:' + color;
  }

  // ── Injection: detect when Settings → Providers is visible ─────────────

  function _tryInit() {
    var pane = $('settingsPaneProviders');
    if (!pane) return;

    if (_initialized) return;
    _initialized = true;

    var observer = new MutationObserver(function () {
      var container = $('foxCustomProviders');
      var list = _getProvidersList();
      if (list && list.offsetParent !== null && !container) {
        _renderAll();
      }
    });

    observer.observe(pane, { childList: true, subtree: true });
    _renderAll();
  }

  // Poll until the settings pane exists, then inject
  var _pollCount = 0;
  var _pollTimer = setInterval(function () {
    _pollCount++;
    var pane = $('settingsPaneProviders');
    if (pane) {
      clearInterval(_pollTimer);
      _tryInit();
      return;
    }
    if (_pollCount > 300) clearInterval(_pollTimer);
  }, 500);

  // Also listen for settings panel switches
  var _origSwitchSettingsSection = window.switchSettingsSection;
  if (typeof _origSwitchSettingsSection === 'function') {
    window.switchSettingsSection = function (section) {
      _origSwitchSettingsSection.apply(this, arguments);
      if (section === 'providers') {
        setTimeout(function () {
          _initialized = false;
          _tryInit();
        }, 100);
      }
    };
  }
})();
