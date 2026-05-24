'use strict';

const { app, BrowserWindow, dialog, shell, clipboard, ipcMain } = require('electron');
const { spawn, exec } = require('child_process');
const path = require('path');
const fs = require('fs');
const os = require('os');
const log = require('electron-log');
const docker = require('./docker-manager');
const { waitUntilHealthy } = require('./health-check');
const { createTray, setRunning } = require('./tray-manager');
const updater = require('./updater');
const updateWindow = require('./update-window');
const {
  waitForDaemon: _waitForDaemon,
  ensureDockerWindows: _ensureDockerWindows,
  runCommandVerbose: _runCommandVerbose,
} = require('./startup');
const { runStartup, ensureContainerHealthy, StartupPhaseError } = require('./startup-orchestrator');
const { registerWindowsRunOnceResume } = require('./windows-run-once');
const { APP_HOME_URL } = require('./app-urls');
const APP_ICON = process.platform === 'win32'
  ? path.join(__dirname, '..', 'assets', 'icon.ico')
  : path.join(__dirname, '..', 'assets', 'icon.png');
let _fatalStartup = false;

// Prevent multiple instances
if (!app.requestSingleInstanceLock()) {
  app.quit();
  process.exit(0);
}

// Keep app alive when all windows are closed (tray-only)
app.on('window-all-closed', (e) => {
  if (_fatalStartup) return;
  e.preventDefault();
});

// v0.7.19: one-time migration from the legacy `@fox-in-the-box` userData
// dir (npm-scope-leaked-into-Electron path; package.json had no productName)
// to the new `fox-in-the-box` path (productName added in v0.7.19). Runs
// BEFORE app.whenReady() so the rename happens before Electron's session/
// LevelDB layer creates the new path. If the rename fails (perms, file
// locks), we log and continue — Electron will create a fresh `fox-in-the-box`
// dir and the user can manually salvage `@fox-in-the-box` via Tray → Reset.
function migrateLegacyUserData() {
  const newPath = app.getPath('userData');  // resolves to .../fox-in-the-box
  let legacyPath;
  switch (process.platform) {
    case 'win32':
      legacyPath = path.join(os.homedir(), 'AppData', 'Roaming', '@fox-in-the-box');
      break;
    case 'darwin':
      legacyPath = path.join(os.homedir(), 'Library', 'Application Support', '@fox-in-the-box');
      break;
    default:
      legacyPath = path.join(os.homedir(), '.config', '@fox-in-the-box');
      break;
  }
  if (!fs.existsSync(legacyPath)) return;
  if (fs.existsSync(newPath)) {
    log.info(
      `[migration] Both legacy (${legacyPath}) and new (${newPath}) userData dirs exist — ` +
      `keeping new, leaving legacy alone for manual review.`,
    );
    return;
  }
  try {
    fs.renameSync(legacyPath, newPath);
    log.info(`[migration] Renamed legacy userData ${legacyPath} -> ${newPath}`);
  } catch (err) {
    log.warn(
      `[migration] Failed to rename legacy userData (${legacyPath} -> ${newPath}): ` +
      `${err.message}. Manual cleanup may be needed via Tray → Reset Fox completely…`,
    );
  }
}

migrateLegacyUserData();

app.whenReady().then(main).catch(handleStartupError);
app.setAppUserModelId('io.foxinthebox.desktop');
// v0.7.19: `app.setName('Fox in the box')` removed — `productName: fox-in-the-box`
// in package.json now drives the userData path, which is what we want
// (drops the `@` prefix that came from the npm scope `@fox-in-the-box/electron`).

// ─── Progress window ─────────────────────────────────────────────────────────

let _progressWin = null;
let _progressState = { title: '', detail: '' };

// Step-based install UX (#362). Steps map to startup-orchestrator phases.
// showProgress is called with "Step N/M - Phase label: message" strings;
// we detect the active step by matching the Phase label segment.
const INSTALL_STEPS = [
  { label: 'Checking system',            match: 'Initialize app' },
  { label: 'Setting up Docker',          match: 'Prepare Docker' },
  { label: 'Pulling container image',    match: 'Ensure container image' },
  { label: 'Starting container',         match: 'Prepare container' },
  { label: 'Waiting for Fox to be ready', match: 'Wait for services' },
  { label: 'Opening Fox',               match: 'Open setup wizard' },
];

function _activeStepIndex(title) {
  if (!title) return -1;
  // title looks like "Step 2/6 - Prepare Docker daemon: Setting up Docker…"
  // or a freeform string like "Starting Docker Desktop…"
  for (let i = INSTALL_STEPS.length - 1; i >= 0; i--) {
    if (title.includes(INSTALL_STEPS[i].match)) return i;
  }
  // Freeform fallback: map common strings to steps
  if (title.includes('Docker')) return 1;
  if (title.includes('image') || title.includes('pull')) return 2;
  if (title.includes('container') || title.includes('Container')) return 3;
  if (title.includes('health') || title.includes('ready') || title.includes('healthy')) return 4;
  return 0;
}

function _buildStepsHtml(activeIdx, escapeForJs = false) {
  const Q = escapeForJs ? '\\"' : '"';
  return INSTALL_STEPS.map((s, i) => {
    let icon, cls;
    if (i < activeIdx)       { icon = '&#x2713;'; cls = 'done'; }
    else if (i === activeIdx) { icon = `<span class=${Q}spin${Q}></span>`; cls = 'active'; }
    else                     { icon = '&#x25cb;'; cls = 'pending'; }
    return `<div class=${Q}step ${cls}${Q}><span class=${Q}icon${Q}>${icon}</span><span class=${Q}label${Q}>${s.label}</span></div>`;
  }).join('');
}

function _buildProgressHtml(title, detail) {
  const activeIdx = _activeStepIndex(title);
  const stepsHtml = _buildStepsHtml(activeIdx);
  return `<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: "Segoe UI", system-ui, sans-serif;
         background: #0D0D1A; color: #FFF8DC; height: 100vh;
         display: flex; align-items: center; justify-content: center; padding: 32px; }
  .wrap { width: 100%; max-width: 400px; }
  .brand { font-size: 16px; font-weight: 600; letter-spacing: -0.01em;
           margin-bottom: 6px; }
  .gold-bar { height: 2px; background: #FFD700; border-radius: 1px; margin-bottom: 24px; }
  .steps { display: flex; flex-direction: column; gap: 10px; margin-bottom: 16px; }
  .step { display: flex; align-items: center; gap: 10px; font-size: 13px; }
  .step.done    { color: #4CAF50; }
  .step.active  { color: #FFF8DC; font-weight: 600; }
  .step.pending { color: rgba(255,248,220,0.3); }
  .icon { width: 18px; text-align: center; flex-shrink: 0; font-size: 13px; }
  .spin { display: inline-block; width: 12px; height: 12px;
          border: 2px solid rgba(255,215,0,0.25); border-top-color: #FFD700;
          border-radius: 50%; animation: s 0.7s linear infinite; vertical-align: middle; }
  @keyframes s { to { transform: rotate(360deg); } }
  .detail { font-size: 11px; color: rgba(255,248,220,0.4); min-height: 28px;
            white-space: pre-wrap; word-break: break-all;
            border-top: 1px solid rgba(255,255,255,0.06); padding-top: 10px; }
</style></head>
<body><div class="wrap">
  <div class="brand">Fox in the Box</div>
  <div class="gold-bar"></div>
  <div class="steps" id="steps">${stepsHtml}</div>
  <div class="detail" id="detail">${(detail || '').replace(/</g,'&lt;')}</div>
</div></body></html>`;
}

function showProgress(message) {
  const update = (typeof message === 'object' && message !== null)
    ? message
    : { title: String(message || '') };
  if (typeof update.title === 'string' && update.title.trim().length > 0) {
    _progressState.title = update.title;
  }
  if (typeof update.detail === 'string') {
    _progressState.detail = update.detail;
  }

  if (_progressWin) {
    const activeIdx = _activeStepIndex(_progressState.title);
    const stepsHtml = _buildStepsHtml(activeIdx, true);
    _progressWin.webContents.executeJavaScript(
      `document.getElementById('steps').innerHTML = ${JSON.stringify(stepsHtml)};
       document.getElementById('detail').textContent = ${JSON.stringify(_progressState.detail || '')};`
    ).catch(() => {});
    return;
  }

  _progressWin = new BrowserWindow({
    width: 480,
    height: 360,
    resizable: false,
    minimizable: false,
    maximizable: false,
    closable: true,
    alwaysOnTop: true,
    frame: true,
    title: 'Fox in the Box — Setting up',
    icon: APP_ICON,
    webPreferences: { nodeIntegration: false, contextIsolation: true },
  });

  _progressWin.on('closed', () => {
    _progressWin = null;
    app.quit();
  });

  _progressWin.loadURL(
    'data:text/html;charset=utf-8,' +
    encodeURIComponent(_buildProgressHtml(_progressState.title, _progressState.detail))
  );
  _progressWin.setMenu(null);
}

function closeProgress() {
  if (_progressWin) {
    _progressWin.removeAllListeners('closed');
    _progressWin.destroy();
    _progressWin = null;
  }
  _progressState = { title: '', detail: '' };
}

// v0.7.16 #324: when external installers (Docker Desktop, winget, UAC) are
// about to surface their own GUI, the FITB progress window's `alwaysOnTop`
// flag covers them up and the user sees a frozen spinner instead of the
// dialog they need to interact with. Drop alwaysOnTop while yielded;
// reclaim it once Docker's window has had its turn.
function setForegroundYield(shouldYield) {
  if (!_progressWin || _progressWin.isDestroyed()) return;
  try {
    _progressWin.setAlwaysOnTop(!shouldYield);
  } catch (err) {
    log.debug('setForegroundYield failed:', err.message);
  }
}

function getDialogParent() {
  return _progressWin && !_progressWin.isDestroyed() ? _progressWin : null;
}

function buildDiagnosticsText({
  sessionId,
  phase,
  code,
  message,
  remediation,
  diagnostics,
}) {
  return [
    `Session ID: ${sessionId || 'n/a'}`,
    `Phase: ${phase || 'unknown'}`,
    `Error code: ${code || 'UNSPECIFIED'}`,
    `Message: ${message || 'Unknown error'}`,
    `Remediation: ${remediation}`,
    `Log path: ${path.join(app.getPath('logs'), 'main.log')}`,
    '',
    'Docker diagnostics:',
    JSON.stringify(diagnostics || {}, null, 2),
  ].join('\n');
}

function showError(details) {
  if (typeof details === 'string') {
    details = {
      message: details,
      remediation: 'Install Docker Desktop manually and relaunch Fox in the box.',
      diagnosticsText: details,
    };
  }
  const {
    sessionId = 'n/a',
    phase = 'unknown',
    code = 'UNSPECIFIED',
    message = 'Unknown startup error',
    remediation = 'Check diagnostics and retry.',
    diagnosticsText = '',
  } = details;
  closeProgress();

  const win = new BrowserWindow({
    width: 560,
    height: 340,
    resizable: false,
    minimizable: false,
    maximizable: false,
    closable: true,
    alwaysOnTop: true,
    frame: true,
    title: 'Fox in the box — Error',
    icon: APP_ICON,
    webPreferences: { nodeIntegration: true, contextIsolation: false },
  });

  const escaped = String(message)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/\n/g, '<br>');
  const escapedRemediation = String(remediation)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/\n/g, '<br>');
  const escapedDiag = String(diagnosticsText)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/\n/g, '<br>');
  const copyChannel = `copy-diagnostics-${Date.now()}`;

  const html = `<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
  body { font-family: "Segoe UI", sans-serif; margin: 0; display: flex;
         align-items: center; justify-content: center; height: 100vh;
         background: #fff; }
  .wrap { text-align: left; padding: 24px; max-width: 520px; }
  .logo { font-size: 32px; margin-bottom: 12px; }
  h2 { font-size: 15px; margin: 0 0 10px; color: #c0392b; }
  p  { font-size: 12px; color: #555; margin: 0 0 12px; line-height: 1.5; text-align: left; }
  .meta { background:#f7f7f7; border:1px solid #ddd; border-radius:8px; padding:8px; margin-bottom:12px; font-size:12px; }
  .diag { font-size:11px; max-height:95px; overflow:auto; background:#fafafa; border:1px solid #eee; padding:8px; border-radius:6px; }
  .actions { display:flex; gap:8px; justify-content:flex-end; margin-top:12px; }
  button { background: #444; color: #fff; border: none; padding: 8px 14px;
           font-size: 13px; border-radius: 6px; cursor: pointer; }
  button:hover { background: #222; }
</style></head>
<body><div class="wrap">
  <div class="logo">🦊</div>
  <h2>Startup failed</h2>
  <div class="meta">
    <div><b>Session:</b> ${sessionId}</div>
    <div><b>Phase:</b> ${phase}</div>
    <div><b>Error code:</b> ${code}</div>
  </div>
  <p>${escaped}</p>
  <p><b>Try:</b> ${escapedRemediation}</p>
  <p><b>Log file:</b> ${path.join(app.getPath('logs'), 'main.log')}</p>
  <div class="diag">${escapedDiag}</div>
  <div class="actions">
    <button onclick="require('electron').ipcRenderer.send('${copyChannel}')">Copy diagnostics</button>
    <button onclick="window.close()">Close</button>
  </div>
</div></body></html>`;

  win.loadURL('data:text/html;charset=utf-8,' + encodeURIComponent(html));
  win.setMenu(null);
  ipcMain.once(copyChannel, () => {
    clipboard.writeText(diagnosticsText);
    dialog.showMessageBox({
      type: 'info',
      message: 'Diagnostics copied to clipboard.',
      buttons: ['OK'],
    });
  });

  win.on('closed', () => {
    if (_fatalStartup) {
      app.exit(1);
    }
  });
}

// ─── Docker setup (Windows) ──────────────────────────────────────────────────
// Logic extracted to startup.js for testability.
// main.js wires up the Electron-specific deps (showProgress, showRebootRequired, spawn).

function spawnDetached(exe) {
  spawn(exe, [], { detached: true, stdio: 'ignore', shell: true }).unref();
}

async function ensureDockerWindows(progressCb = showProgress) {
  // #356: Show a one-time heads-up before Docker Desktop's first launch.
  // Docker requires ToS acceptance + free account sign-up on first run,
  // which pops up unexpectedly and confuses users into thinking Fox broke.
  const dockerTosFlag = path.join(app.getPath('userData'), '.docker-tos-shown');
  if (!fs.existsSync(dockerTosFlag)) {
    const dockerConfigPath = path.join(os.homedir(), 'AppData', 'Roaming', 'Docker', 'settings.json');
    const dockerAlreadyConfigured = fs.existsSync(dockerConfigPath);
    if (!dockerAlreadyConfigured) {
      await dialog.showMessageBox({
        type: 'info',
        title: 'Fox in the Box — Docker setup',
        message: 'Docker Desktop is about to start.',
        detail:
          'Docker Desktop will ask you to accept their Terms of Service and sign up for a free Docker account.\n\n'
          + 'This is normal — just follow the Docker window that appears. '
          + 'Once you\'re done, Fox will continue automatically.',
        buttons: ['Got it'],
        defaultId: 0,
      });
      try { fs.writeFileSync(dockerTosFlag, '1'); } catch (_) {}
    }
  }

  return _ensureDockerWindows({
    isDaemonRunning: () => docker.isDaemonRunning(),
    waitForDaemon: (ms, sp) => _waitForDaemon(
      () => docker.isDaemonRunning(),
      ms || 90_000,
      1_000,
      Date.now,
      (t) => new Promise((r) => setTimeout(r, t)),
      sp || progressCb
    ),
    runCommand: (cmd, opts) => _runCommandVerbose(cmd, opts, (line) => showProgress({ detail: line })),
    spawnDetached,
    showProgress: progressCb,
    showRebootRequired: () => showDaemonRecoveryRequired('win32'),
    showError,
    setForegroundYield,
  });
}

// ─── macOS Docker install (kept separate) ────────────────────────────────────

async function installDockerMac(progressCb = showProgress) {
  const { response } = await dialog.showMessageBox({
    type: 'question',
    buttons: ['Install Docker', 'Cancel'],
    defaultId: 0,
    cancelId: 1,
    title: 'Docker not found',
    message: 'Docker Desktop is required but was not found.',
    detail: 'Fox in the box will install it via Homebrew.\n\nThis may take a few minutes.',
  });

  if (response !== 0) throw new Error('User cancelled Docker installation');

  try {
    await _runCommandVerbose('brew --version', { timeout: 20_000 });
  } catch (err) {
    const brewErr = new Error(
      'Homebrew is not installed or not available in PATH.\nInstall Homebrew from https://brew.sh, then relaunch Fox in the box.'
    );
    brewErr.code = 'BREW_NOT_FOUND';
    brewErr.cause = err;
    throw brewErr;
  }

  log.info('Installing Docker via Homebrew');
  try {
    await _runCommandVerbose('brew install --cask docker', { timeout: 15 * 60 * 1000 }, (line) => showProgress({ detail: line }));
  } catch (err) {
    const brewInstallErr = new Error(
      'Failed to install Docker Desktop via Homebrew. Check your network/proxy settings and Homebrew health, then retry.'
    );
    brewInstallErr.code = 'BREW_INSTALL_FAILED';
    brewInstallErr.cause = err;
    throw brewInstallErr;
  }

  try {
    await _runCommandVerbose('open -a Docker', { timeout: 20_000 }, (line) => showProgress({ detail: line }));
  } catch (err) {
    const openErr = new Error(
      'Docker Desktop installed but could not be opened automatically. Open Docker Desktop manually and approve any security/helper prompts.'
    );
    openErr.code = 'MAC_DOCKER_LAUNCH_FAILED';
    openErr.cause = err;
    throw openErr;
  }

  await new Promise((r) => setTimeout(r, 1000));
}

async function showDaemonRecoveryRequired(platform) {
  // Native message boxes are not parented to our always-on-top progress window;
  // close it first so the prompt is visible and not stacked underneath.
  closeProgress();

  if (platform === 'win32') {
    // v0.7.16 #325: register the RunOnce resume BEFORE the user sees the
    // dialog, so the "will continue automatically after restart" line is
    // truthful at the moment we make the promise. If the registration
    // fails, the dialog copy below would be a lie — registerWindowsRunOnceResume
    // logs but does not throw, so detect that we have an exe path at least.
    await registerWindowsRunOnceResume(app.getPath('exe'));
    const { response } = await dialog.showMessageBox({
      type: 'warning',
      title: 'Restart required to finish Docker setup',
      message: 'Docker Desktop needs a restart before Fox in the box can continue.',
      detail:
        'Fox in the box will resume installation automatically after your PC restarts — '
        + 'you do not need to re-launch the installer manually.\n\n'
        + 'Save any unsaved work in other apps before clicking Restart now.',
      buttons: ['Restart now', 'I\'ll restart later'],
      defaultId: 0,
      cancelId: 1,
    });
    if (response === 0) {
      exec('shutdown /r /t 3 /c "Restarting to finish Docker setup"');
      setTimeout(() => app.quit(), 500);
    }
    return;
  }

  if (platform === 'darwin') {
    const { response } = await dialog.showMessageBox({
      type: 'warning',
      title: 'Docker not ready',
      message: 'Docker Desktop is installed but daemon is not ready yet.',
      detail: 'Open Docker Desktop and wait until it says it is running. Approve any helper/Gatekeeper prompts in System Settings, then reopen Fox in the box.',
      buttons: ['Open Docker Desktop', 'Close'],
      defaultId: 0,
      cancelId: 1,
    });
    if (response === 0) {
      try {
        await shell.openExternal('docker-desktop://dashboard');
      } catch (_) {
        exec('open -a Docker');
      }
    }
  }
}

function getRemediationForCode(code, platform) {
  if (code === 'DAEMON_LOST_DURING_HEALTH') {
    return 'Docker daemon stopped while services were starting. Restart Docker Desktop and relaunch Fox in the box.';
  }
  if (code === 'CONTAINER_MISSING_DURING_HEALTH' || code === 'CONTAINER_NOT_RUNNING_DURING_HEALTH') {
    return 'Container stopped unexpectedly during startup. Check Docker Desktop container logs and retry.';
  }
  if (code === 'BREW_NOT_FOUND') {
    return 'Install Homebrew from https://brew.sh, then relaunch Fox in the box.';
  }
  if (code === 'BREW_INSTALL_FAILED') {
    return 'Run brew doctor and brew install --cask docker manually, then relaunch Fox in the box.';
  }
  if (code === 'MAC_DOCKER_LAUNCH_FAILED') {
    return 'Open Docker Desktop manually from Applications and approve security/helper prompts.';
  }
  if (code === 'WSL_NOT_INITIALIZED' || code === 'WSL_BACKEND_MISSING') {
    return 'Open an elevated PowerShell and run: wsl --install --no-distribution && wsl --update, reboot, then launch Docker Desktop and retry.';
  }
  if (code === 'DOCKER_DESKTOP_NOT_RUNNING') {
    return 'Open Docker Desktop manually and wait until it shows Docker Engine running, then relaunch Fox in the box.';
  }
  if (code === 'DOCKER_DESKTOP_LAUNCH_FAILED') {
    return 'Docker Desktop launch failed. Start Docker Desktop manually (as Administrator if needed), then retry.';
  }
  if (code === 'DAEMON_NOT_READY') {
    if (platform === 'win32') return 'Start Docker Desktop manually, wait until it reports running, then relaunch Fox in the box.';
    return 'Open Docker Desktop and wait for daemon readiness, then relaunch Fox in the box.';
  }
  if (code === 'DOCKER_WINDOWS_CONTAINERS_MODE') {
    // v0.7.11 #291: Docker IS running but in the wrong mode. There's no
    // recovery to attempt — the user has to flip the switch themselves.
    return 'Docker Desktop is in Windows-containers mode. Fox needs Linux containers. Right-click the Docker Desktop tray icon → "Switch to Linux containers..." → wait for it to finish, then relaunch Fox in the box.';
  }
  if (code === 'IMAGE_PULL_TIMEOUT') return 'Check network connectivity and retry. Corporate proxies/firewalls can block container pulls.';
  if (code === 'HEALTH_TIMEOUT') return 'Container started but app is not healthy yet. Wait a bit longer or restart Docker and try again.';
  if (code === 'ACCESS_MODE_CANCELLED') return 'Relaunch Fox in the box and pick a network option, or set FOX_ACCESS_MODE=1|2|3 before starting.';
  return 'Check diagnostics and logs, then retry.';
}

// Poll /api/tailscale/status until it returns a tailnet_url or we time out.
// Returns the HTTPS tailnet URL string, or null if not available in time.
async function pollTailscaleUrl(timeoutMs = 30_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const res = await fetch('http://127.0.0.1:8787/api/tailscale/status');
      if (res.ok) {
        const data = await res.json();
        if (data && data.tailnet_url) return data.tailnet_url;
      }
    } catch (_) { /* not yet */ }
    await new Promise((r) => setTimeout(r, 2_000));
  }
  return null;
}

// Opens Fox after container is healthy. If Tailscale mode is active (mode 2 or 3),
// polls for the tailnet URL and shows a dialog surfacing it (#358).
async function openFox() {
  const mode = docker.getEffectiveAccessMode();
  if (mode === '2' || mode === '3') {
    showProgress('Waiting for Tailscale to connect…');
    const tailnetUrl = await pollTailscaleUrl(30_000);
    closeProgress();
    if (tailnetUrl) {
      const lines = mode === '3'
        ? `Local access: http://localhost:8787\nFrom other devices: ${tailnetUrl}`
        : `From other devices: ${tailnetUrl}`;
      const { response } = await dialog.showMessageBox({
        type: 'info',
        title: 'Fox in the box — Ready',
        message: 'Fox in the box is ready!',
        detail: lines + '\n\nClick OK to open Fox.',
        buttons: ['OK', 'Copy Tailscale URL'],
        defaultId: 0,
      });
      if (response === 1) clipboard.writeText(tailnetUrl);
    }
  }
  shell.openExternal(APP_HOME_URL);
}

async function startFromTray() {
  showProgress('Starting Fox in the box…');
  try {
    if (typeof docker.ensureDockerAccessModeChosen === 'function') {
      await docker.ensureDockerAccessModeChosen({ parent: getDialogParent() });
    }
    await ensureContainerHealthy({
      docker,
      waitUntilHealthy,
      showProgress,
      openOnboarding: openFox,
    });
  } finally {
    closeProgress();
  }
}

async function handleStartupError(err) {
  _fatalStartup = true;
  closeProgress();
  log.error('Fatal startup error:', err);

  const phase = err instanceof StartupPhaseError ? err.phase : 'unknown';
  const code = err.code || (err.cause && err.cause.code) || 'UNSPECIFIED';
  const sessionId = err.details && err.details.sessionId ? err.details.sessionId : 'n/a';
  const diagnostics = await docker.getDiagnostics().catch(() => ({}));
  if (err.meta) diagnostics.startupDiagnostics = err.meta;
  const remediation = getRemediationForCode(code, process.platform);
  const diagnosticsText = buildDiagnosticsText({
    sessionId,
    phase,
    code,
    message: err.message,
    remediation,
    diagnostics,
  });

  showError({
    sessionId,
    phase,
    code,
    message: err.message || String(err),
    remediation,
    diagnosticsText,
  });
}

// ─── Main startup sequence ───────────────────────────────────────────────────

async function main() {
  log.info('Fox in the box starting up');

  try {
    const startupOutcome = await runStartup({
      docker,
      waitUntilHealthy,
      ensureDockerWindows,
      installDockerMac,
      waitForDaemon: (ms, sp) => _waitForDaemon(
        () => docker.isDaemonRunning(),
        ms || 180_000,
        1_000,
        Date.now,
        (t) => new Promise((r) => setTimeout(r, t)),
        sp || showProgress
      ),
      showProgress,
      closeProgress,
      openOnboarding: openFox,
      onDaemonNotReady: ({ platform }) => showDaemonRecoveryRequired(platform),
      getDialogParent,
      platform: process.platform,
    });
    if (startupOutcome && startupOutcome.outcome === 'reboot-required') {
      app.quit();
      return;
    }
  } catch (err) {
    await handleStartupError(err);
    return;
  }

  createTray(true, {
    startFlow: startFromTray,
    openApp: () => shell.openExternal(APP_HOME_URL),
  });
  setRunning(true);

  updater.init(null);
  updateWindow.init();
}
