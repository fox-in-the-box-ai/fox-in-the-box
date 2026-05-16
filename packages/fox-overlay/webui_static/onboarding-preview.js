/**
 * Client-only replay of the first-run onboarding wizard for UI/CSS/i18n work.
 * Trigger: ?onboarding=1|true|yes|preview or ?preview_onboarding=1|true|yes
 * Simplified 3-step flow (system → provider → optional password); no workspace/model UI.
 * Skip / final action closes the overlay and strips those query params.
 */
(function () {
  'use strict';

  /** OpenRouter default used across the guided preview (matches product default). */
  const PREVIEW_DEFAULT_MODEL = 'moonshotai/kimi-k2.6';
  const PREVIEW_STEPS = ['system', 'setup', 'password'];

  function _truthy(v) {
    const s = String(v || '').trim().toLowerCase();
    return s === '1' || s === 'true' || s === 'yes' || s === 'preview';
  }

  function _wantsOnboardingPreview() {
    try {
      const q = new URLSearchParams(location.search || '');
      return _truthy(q.get('onboarding')) || _truthy(q.get('preview_onboarding'));
    } catch (_) {
      return false;
    }
  }

  function _stripOnboardingQueryParams() {
    try {
      const u = new URL(location.href);
      if (!u.searchParams.has('onboarding') && !u.searchParams.has('preview_onboarding')) return;
      u.searchParams.delete('onboarding');
      u.searchParams.delete('preview_onboarding');
      const qs = u.searchParams.toString();
      history.replaceState({}, '', u.pathname + (qs ? '?' + qs : '') + u.hash);
    } catch (_) { /* ignore */ }
  }

  function _mockStatus() {
    return {
      system: {
        hermes_found: true,
        imports_ok: true,
        chat_ready: true,
        provider_configured: true,
        config_path: '~/.hermes/config.yaml',
        env_path: '~/.hermes/.env',
        current_provider: 'openrouter',
        current_model: PREVIEW_DEFAULT_MODEL,
        provider_note: '',
        missing_modules: [],
      },
      settings: {
        password_enabled: false,
        default_workspace: '/home/you/workspace',
        default_model: PREVIEW_DEFAULT_MODEL,
      },
      setup: {
        current: { provider: 'openrouter', model: PREVIEW_DEFAULT_MODEL, base_url: '' },
        current_is_oauth: false,
        unsupported_note: '',
        providers: [
          {
            id: 'openrouter',
            label: 'OpenRouter',
            quick: true,
            env_var: 'OPENROUTER_API_KEY',
            key_optional: false,
            requires_base_url: false,
            default_model: PREVIEW_DEFAULT_MODEL,
            models: [
              { id: PREVIEW_DEFAULT_MODEL, label: PREVIEW_DEFAULT_MODEL },
              { id: 'openai/gpt-5', label: 'openai/gpt-5' },
            ],
          },
          {
            id: 'anthropic',
            label: 'Anthropic',
            quick: true,
            env_var: 'ANTHROPIC_API_KEY',
            key_optional: false,
            requires_base_url: false,
            default_model: 'claude-sonnet-4-6',
            models: [
              { id: 'claude-sonnet-4-6', label: 'claude-sonnet-4-6' },
            ],
          },
          {
            id: 'custom',
            label: 'Custom (OpenAI-compatible)',
            quick: false,
            env_var: 'OPENAI_API_KEY',
            key_optional: true,
            requires_base_url: true,
            default_base_url: 'http://127.0.0.1:11434/v1',
            default_model: 'llama3.2',
            models: [],
          },
        ],
        categories: [
          { id: 'easy_start', label: 'Easy Start', providers: ['openrouter', 'anthropic'] },
          { id: 'self_hosted', label: 'Self-hosted', providers: ['custom'] },
        ],
      },
      workspaces: {
        items: [
          { name: 'Workspace', path: '/home/you/workspace' },
          { name: 'Documents', path: '/home/you/Documents' },
        ],
        last: '/home/you/workspace',
      },
    };
  }

  window.ONBOARDING = window.ONBOARDING || {
    status: null,
    step: 0,
    steps: PREVIEW_STEPS,
    form: {
      provider: 'openrouter',
      workspace: '',
      model: PREVIEW_DEFAULT_MODEL,
      password: '',
      apiKey: '',
      baseUrl: '',
    },
    probe: { status: 'idle', error: null, detail: '', models: null, probedKey: '' },
    active: false,
  };

  const ONBOARDING = window.ONBOARDING;

  function _getOnboardingCurrentSetup() {
    return (((ONBOARDING.status || {}).setup || {}).current) || {};
  }

  function _getOnboardingSetupProviders() {
    return (((ONBOARDING.status || {}).setup || {}).providers) || [];
  }

  function _getOnboardingSetupCategories() {
    return (((ONBOARDING.status || {}).setup || {}).categories) || [];
  }

  function _getOnboardingSetupProvider(id) {
    return _getOnboardingSetupProviders().find((p) => p.id === id) || null;
  }

  function _onboardingStepMeta(key) {
    return ({
      system: { title: t('onboarding_step_system_title'), desc: t('onboarding_step_system_desc') },
      setup: { title: t('onboarding_step_setup_title'), desc: t('onboarding_step_setup_desc') },
      password: { title: t('onboarding_step_password_title'), desc: t('onboarding_step_password_desc') },
    })[key];
  }

  function _renderOnboardingSteps() {
    const wrap = $('onboardingSteps');
    if (!wrap) return;
    wrap.innerHTML = '';
    ONBOARDING.steps.forEach((key, idx) => {
      const meta = _onboardingStepMeta(key);
      const item = document.createElement('div');
      item.className = 'onboarding-step' + (idx === ONBOARDING.step ? ' active' : idx < ONBOARDING.step ? ' done' : '');
      item.innerHTML =
        '<div class="onboarding-step-index">' +
        (idx + 1) +
        '</div><div><div class="onboarding-step-title">' +
        meta.title +
        '</div><div class="onboarding-step-desc">' +
        meta.desc +
        '</div></div>';
      wrap.appendChild(item);
    });
  }

  function _setOnboardingNotice(msg, kind) {
    const el = $('onboardingNotice');
    if (!el) return;
    if (!msg) {
      el.style.display = 'none';
      el.textContent = '';
      el.className = 'onboarding-status';
      return;
    }
    el.style.display = 'block';
    el.className = 'onboarding-status ' + kind;
    el.textContent = msg;
  }

  function _onboardingProbePreviewMessage(probe) {
    if (!probe || probe.status === 'idle') return '';
    if (probe.status === 'probing') return t('onboarding_probe_probing') || '';
    if (probe.status === 'ok') {
      const n = (probe.models || []).length;
      const tmpl = t('onboarding_probe_ok') || 'Connected. {n} model(s) available.';
      return tmpl.replace('{n}', String(n));
    }
    const errKey = 'onboarding_probe_error_' + (probe.error || 'generic');
    const localized = t(errKey);
    const heading = localized && localized !== errKey ? localized : t('onboarding_probe_error_generic') || '';
    const detail = probe.detail ? ' (' + probe.detail + ')' : '';
    return heading + detail;
  }

  function _renderOnboardingBaseUrlField(showBaseUrl) {
    if (!showBaseUrl) return '';
    const probe = ONBOARDING.probe || { status: 'idle' };
    const msg = _onboardingProbePreviewMessage(probe);
    let banner = '';
    if (msg) {
      const cls = { ok: 'onboarding-probe-ok', probing: 'onboarding-probe-probing', error: 'onboarding-probe-error' }[probe.status] || '';
      banner = '<p class="onboarding-copy onboarding-probe-banner ' + cls + '">' + esc(msg) + '</p>';
    }
    const testBtnLabel = t('onboarding_probe_test_button') || 'Test connection';
    const testBtnDisabled = probe.status === 'probing' ? 'disabled' : '';
    return (
      '<label class="onboarding-field"><span>' +
      esc(t('onboarding_base_url_label')) +
      '</span><input id="onboardingBaseUrlInput" value="' +
      esc(ONBOARDING.form.baseUrl || '') +
      '" placeholder="' +
      esc(t('onboarding_base_url_placeholder')) +
      '" oninput="ONBOARDING.form.baseUrl=this.value"></label><div class="onboarding-probe-row"><button type="button" class="onboarding-probe-btn" ' +
      testBtnDisabled +
      ' onclick="if(typeof _previewOnboardingProbe===\"function\")_previewOnboardingProbe()">' +
      esc(testBtnLabel) +
      '</button></div>' +
      banner
    );
  }

  function _renderOnboardingApiKeyField() {
    const provider = _getOnboardingSetupProvider(ONBOARDING.form.provider);
    const keyOptional = !!(provider && provider.key_optional);
    const labelKey = keyOptional ? 'onboarding_api_key_label_optional' : 'onboarding_api_key_label';
    const placeholderKey = keyOptional ? 'onboarding_api_key_placeholder_optional' : 'onboarding_api_key_placeholder';
    const helpHtml = keyOptional
      ? '<p class="onboarding-copy onboarding-api-key-help">' + esc(t('onboarding_api_key_help_keyless') || '') + '</p>'
      : '';
    return (
      '<label class="onboarding-field" id="onboardingApiKeyField"><span>' +
      esc(t(labelKey)) +
      '</span><input id="onboardingApiKeyInput" type="password" value="' +
      esc(ONBOARDING.form.apiKey || '') +
      '" placeholder="' +
      esc(t(placeholderKey)) +
      '" oninput="ONBOARDING.form.apiKey=this.value"></label>' +
      helpHtml
    );
  }

  function _renderOnboardingFixedModelNote() {
    const msg = t('onboarding_fixed_model_note');
    const text =
      msg && msg !== 'onboarding_fixed_model_note'
        ? msg
        : 'New chats use moonshotai/kimi-k2.6 by default. You can change the model anytime in Settings.';
    return '<p class="onboarding-copy onboarding-fixed-model-note">' + esc(text) + '</p>';
  }

  function _providerStatusLabel(system) {
    if (system.chat_ready) return t('onboarding_check_provider_ready');
    if (system.provider_configured) return t('onboarding_check_provider_partial');
    return t('onboarding_check_provider_pending');
  }

  function _renderProviderSelectOptions(selectedId) {
    const providers = _getOnboardingSetupProviders();
    const categories = _getOnboardingSetupCategories();
    const provMap = {};
    providers.forEach((p) => {
      provMap[p.id] = p;
    });
    if (!categories.length) {
      return providers
        .map((p) => {
          const sel = p.id === selectedId ? ' selected' : '';
          return (
            '<option value="' +
            esc(p.id) +
            '"' +
            sel +
            '>' +
            esc(p.label) +
            (p.quick ? ' — ' + esc(t('onboarding_quick_setup_badge')) : '') +
            '</option>'
          );
        })
        .join('');
    }
    return categories
      .map((cat) => {
        const opts = cat.providers
          .map((pid) => {
            const p = provMap[pid];
            if (!p) return '';
            const sel = p.id === selectedId ? ' selected' : '';
            return (
              '<option value="' +
              esc(p.id) +
              '"' +
              sel +
              '>' +
              esc(p.label) +
              (p.quick ? ' — ' + esc(t('onboarding_quick_setup_badge')) : '') +
              '</option>'
            );
          })
          .join('');
        const ogLabel = esc(t('provider_category_' + cat.id) || cat.label);
        return '<optgroup label="' + ogLabel + '">' + opts + '</optgroup>';
      })
      .join('');
  }

  function _renderOnboardingBody() {
    const body = $('onboardingBody');
    if (!body || !ONBOARDING.status) return;
    const key = ONBOARDING.steps[ONBOARDING.step];
    const system = ONBOARDING.status.system || {};
    const settings = ONBOARDING.status.settings || {};
    const setup = ONBOARDING.status.setup || {};
    const nextBtn = $('onboardingNextBtn');
    const backBtn = $('onboardingBackBtn');
    const isLast = key === 'password';
    if (backBtn) backBtn.style.display = ONBOARDING.step > 0 ? '' : 'none';
    if (nextBtn) nextBtn.textContent = isLast ? t('onboarding_open') : t('onboarding_continue');

    if (key === 'system') {
      const hermesOk = system.hermes_found && system.imports_ok;
      const setupOk = !!system.chat_ready;
      _setOnboardingNotice(
        system.provider_note || (setupOk ? t('onboarding_notice_system_ready') : t('onboarding_notice_system_unavailable')),
        setupOk ? 'success' : hermesOk ? 'info' : 'warn'
      );
      body.innerHTML =
        '<div class="onboarding-panel-grid">' +
        '<div class="onboarding-check ' +
        (hermesOk ? 'ok' : 'warn') +
        '"><strong>' +
        esc(t('onboarding_check_agent')) +
        '</strong><span>' +
        esc(hermesOk ? t('onboarding_check_agent_ready') : t('onboarding_check_agent_missing')) +
        '</span></div>' +
        '<div class="onboarding-check ' +
        (setupOk ? 'ok' : system.provider_configured ? 'warn' : 'muted') +
        '"><strong>' +
        esc(t('onboarding_check_provider')) +
        '</strong><span>' +
        esc(_providerStatusLabel(system)) +
        '</span></div>' +
        '<div class="onboarding-check ' +
        (settings.password_enabled ? 'ok' : 'muted') +
        '"><strong>' +
        esc(t('onboarding_check_password')) +
        '</strong><span>' +
        esc(settings.password_enabled ? t('onboarding_check_password_enabled') : t('onboarding_check_password_disabled')) +
        '</span></div></div>' +
        '<div class="onboarding-copy">' +
        '<p><strong>' +
        esc(t('onboarding_config_file')) +
        '</strong> ' +
        esc(system.config_path || t('onboarding_unknown')) +
        '</p>' +
        '<p><strong>' +
        esc(t('onboarding_env_file')) +
        '</strong> ' +
        esc(system.env_path || t('onboarding_unknown')) +
        '</p>' +
        (system.provider_note ? '<p>' + esc(system.provider_note) + '</p>' : '') +
        (system.current_provider
          ? '<p><strong>' +
            esc(t('onboarding_current_provider')) +
            '</strong> ' +
            esc(system.current_provider) +
            (system.current_model ? ' — ' + esc(system.current_model) : '') +
            '</p>'
          : '') +
        (system.current_base_url
          ? '<p><strong>' + esc(t('onboarding_base_url_label')) + '</strong> ' + esc(system.current_base_url) + '</p>'
          : '') +
        (system.missing_modules && system.missing_modules.length
          ? '<p><strong>' + esc(t('onboarding_missing_imports')) + '</strong> ' + esc(system.missing_modules.join(', ')) + '</p>'
          : '') +
        '</div>';
      return;
    }

    if (key === 'setup') {
      const selectedId = ONBOARDING.form.provider;
      const groupedOptions = _renderProviderSelectOptions(selectedId);
      const provider = _getOnboardingSetupProvider(selectedId) || _getOnboardingSetupProviders()[0] || null;
      const showBaseUrl = provider && provider.requires_base_url;
      const keyHelp = provider ? t('onboarding_api_key_help_prefix') + ' ' + esc(provider.env_var) + '.' : '';

      const currentIsOauth = !!(ONBOARDING.status.setup || {}).current_is_oauth;
      const currentProviderName = ((ONBOARDING.status.setup || {}).current || {}).provider || '';
      if (currentIsOauth) {
        const isReady = !!(ONBOARDING.status.system || {}).chat_ready;
        const providerLabel = esc(currentProviderName);
        if (isReady) {
          _setOnboardingNotice(t('onboarding_notice_setup_already_ready'), 'success');
          body.innerHTML =
            '<div class="onboarding-oauth-card onboarding-oauth-ready">' +
            '<div class="onboarding-oauth-icon">✓</div><div><strong>' +
            esc(t('onboarding_oauth_provider_ready_title')) +
            '</strong><p>' +
            t('onboarding_oauth_provider_ready_body').replace('{provider}', providerLabel) +
            '</p></div></div>' +
            '<p class="onboarding-copy" style="margin-top:20px">' +
            t('onboarding_oauth_switch_hint') +
            '</p>' +
            '<label class="onboarding-field"><span>' +
            esc(t('onboarding_provider_label')) +
            '</span><select id="onboardingProviderSelect" onchange="syncOnboardingProvider(this.value)">' +
            groupedOptions +
            '</select></label>' +
            _renderOnboardingApiKeyField() +
            _renderOnboardingBaseUrlField(showBaseUrl) +
            '<p class="onboarding-copy">' +
            keyHelp +
            '</p>' +
            _renderOnboardingFixedModelNote();
        } else {
          _setOnboardingNotice(t('onboarding_notice_setup_required'), 'warn');
          body.innerHTML =
            '<div class="onboarding-oauth-card onboarding-oauth-pending">' +
            '<div class="onboarding-oauth-icon">⚠</div><div><strong>' +
            esc(t('onboarding_oauth_provider_not_ready_title')) +
            '</strong><p>' +
            t('onboarding_oauth_provider_not_ready_body').replace('{provider}', providerLabel) +
            '</p></div></div>' +
            '<p class="onboarding-copy" style="margin-top:20px">' +
            t('onboarding_oauth_switch_hint') +
            '</p>' +
            '<label class="onboarding-field"><span>' +
            esc(t('onboarding_provider_label')) +
            '</span><select id="onboardingProviderSelect" onchange="syncOnboardingProvider(this.value)">' +
            groupedOptions +
            '</select></label>' +
            _renderOnboardingApiKeyField() +
            _renderOnboardingBaseUrlField(showBaseUrl) +
            '<p class="onboarding-copy">' +
            keyHelp +
            '</p>' +
            _renderOnboardingFixedModelNote();
        }
        return;
      }

      _setOnboardingNotice(
        system.chat_ready ? t('onboarding_notice_setup_already_ready') : t('onboarding_notice_setup_required'),
        system.chat_ready ? 'success' : 'info'
      );
      body.innerHTML =
        '<label class="onboarding-field"><span>' +
        esc(t('onboarding_provider_label')) +
        '</span><select id="onboardingProviderSelect" onchange="syncOnboardingProvider(this.value)">' +
        groupedOptions +
        '</select></label>' +
        _renderOnboardingApiKeyField() +
        _renderOnboardingBaseUrlField(showBaseUrl) +
        '<p class="onboarding-copy">' +
        keyHelp +
        '</p>' +
        _renderOnboardingFixedModelNote() +
        '<div class="onboarding-oauth-card" id="codexOAuthCard">' +
        '<div class="onboarding-oauth-icon">🔑</div>' +
        '<div style="flex:1"><strong>' +
        esc(t('oauth_login_codex')) +
        '</strong><p style="margin:6px 0 0;font-size:13px;color:var(--muted);line-height:1.5">' +
        t('onboarding_oauth_switch_hint') +
        '</p></div>' +
        '<button class="sm-btn" id="codexOAuthBtn" onclick="startCodexOAuth()" style="margin-left:auto;flex-shrink:0">' +
        esc(t('oauth_login_codex')) +
        '</button></div>' +
        '<div id="codexOAuthFlow" style="display:none;margin-top:12px"></div>' +
        (showBaseUrl ? '<p class="onboarding-copy">' + esc(t('onboarding_base_url_help')) + '</p>' : '') +
        (setup.unsupported_note ? '<p class="onboarding-copy">' + esc(setup.unsupported_note) + '</p>' : '');
      return;
    }

    if (key === 'password') {
      _setOnboardingNotice(
        settings.password_enabled ? t('onboarding_notice_password_enabled') : t('onboarding_notice_password_recommended'),
        settings.password_enabled ? 'success' : 'info'
      );
      body.innerHTML =
        '<label class="onboarding-field"><span>' +
        esc(t('onboarding_password_label')) +
        '</span><input id="onboardingPasswordInput" type="password" value="' +
        esc(ONBOARDING.form.password || '') +
        '" placeholder="' +
        esc(t('onboarding_password_placeholder')) +
        '" oninput="ONBOARDING.form.password=this.value"></label>' +
        '<p class="onboarding-copy">' +
        esc(t('onboarding_password_help')) +
        '</p>';
    }
  }

  window.syncOnboardingProvider = function (value) {
    const provider = _getOnboardingSetupProvider(value);
    ONBOARDING.form.provider = value;
    ONBOARDING.form.model = PREVIEW_DEFAULT_MODEL;
    if (provider) {
      if (provider.requires_base_url) {
        ONBOARDING.form.baseUrl = ONBOARDING.form.baseUrl || provider.default_base_url || '';
      } else {
        ONBOARDING.form.baseUrl = provider.default_base_url || '';
      }
    }
    ONBOARDING.probe = { status: 'idle', error: null, detail: '', models: null, probedKey: '' };
    _renderOnboardingSteps();
    _renderOnboardingBody();
  };

  window.startCodexOAuth = function () {
    if (typeof showToast === 'function') {
      showToast(t('onboarding_notice_setup_required') || 'OAuth requires the full Web UI.');
    }
  };

  /** Cosmetic probe for custom base URL (no network). */
  window._previewOnboardingProbe = function () {
    if (ONBOARDING.form.provider !== 'custom') return;
    const base = (ONBOARDING.form.baseUrl || '').trim();
    if (!/^https?:\/\//i.test(base)) {
      ONBOARDING.probe = {
        status: 'error',
        error: 'invalid_url',
        detail: '',
        models: null,
        probedKey: '',
      };
    } else {
      ONBOARDING.probe = {
        status: 'ok',
        error: null,
        detail: '',
        models: [
          { id: 'llama3.2', label: 'llama3.2' },
          { id: 'mistral', label: 'mistral' },
        ],
        probedKey: 'preview',
      };
    }
    ONBOARDING.form.model = PREVIEW_DEFAULT_MODEL;
    _renderOnboardingBody();
  };

  async function loadOnboardingWizard() {
    if (!_wantsOnboardingPreview()) return false;
    ONBOARDING.status = _mockStatus();
    ONBOARDING.steps = PREVIEW_STEPS;
    ONBOARDING.step = 0;
    ONBOARDING.active = true;
    ONBOARDING.probe = { status: 'idle', error: null, detail: '', models: null, probedKey: '' };
    const current = _getOnboardingCurrentSetup();
    ONBOARDING.form.provider = current.provider || 'openrouter';
    ONBOARDING.form.workspace =
      (ONBOARDING.status.workspaces && ONBOARDING.status.workspaces.last) ||
      ONBOARDING.status.settings.default_workspace ||
      '';
    ONBOARDING.form.model = PREVIEW_DEFAULT_MODEL;
    ONBOARDING.form.password = '';
    ONBOARDING.form.apiKey = '';
    ONBOARDING.form.baseUrl = current.base_url || '';
    const ov = $('onboardingOverlay');
    if (!ov) return false;
    ov.style.display = 'flex';
    _renderOnboardingSteps();
    _renderOnboardingBody();
    if (typeof applyLocaleToDOM === 'function') {
      try {
        applyLocaleToDOM();
      } catch (_) { /* ignore */ }
    }
    return true;
  }

  function prevOnboardingStep() {
    if (!ONBOARDING.active) return;
    if (ONBOARDING.step === 0) return;
    ONBOARDING.step--;
    _renderOnboardingSteps();
    _renderOnboardingBody();
  }

  function nextOnboardingStep() {
    if (!ONBOARDING.active) return;
    if (ONBOARDING.step >= ONBOARDING.steps.length - 1) {
      skipOnboarding();
      return;
    }
    ONBOARDING.step++;
    _renderOnboardingSteps();
    _renderOnboardingBody();
  }

  function skipOnboarding() {
    if (ONBOARDING.active) {
      ONBOARDING.active = false;
      _stripOnboardingQueryParams();
    }
    const ov = $('onboardingOverlay');
    if (ov) ov.style.display = 'none';
    _setOnboardingNotice('', 'info');
  }

  window.loadOnboardingWizard = loadOnboardingWizard;
  window.prevOnboardingStep = prevOnboardingStep;
  window.nextOnboardingStep = nextOnboardingStep;
  window.skipOnboarding = skipOnboarding;
})();
