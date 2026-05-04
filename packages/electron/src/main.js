'use strict';

const { app, BrowserWindow, dialog, shell, clipboard, ipcMain } = require('electron');
const { spawn, exec } = require('child_process');
const path = require('path');
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

app.whenReady().then(main).catch(handleStartupError);
app.setAppUserModelId('io.foxinthebox.desktop');
app.setName('Fox in the box');

// ─── Progress window ─────────────────────────────────────────────────────────

let _progressWin = null;
let _progressState = { title: '', detail: '' };

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
    _progressWin.webContents.executeJavaScript(
      `document.getElementById('msg-title').textContent = ${JSON.stringify(_progressState.title)};
       document.getElementById('msg-detail').textContent = ${JSON.stringify(_progressState.detail || '')};`
    );
    return;
  }

  _progressWin = new BrowserWindow({
    width: 500,
    height: 500,
    resizable: false,
    minimizable: false,
    maximizable: false,
    closable: true,
    alwaysOnTop: true,
    frame: true,
    title: 'Fox in the box — Setting up',
    icon: APP_ICON,
    webPreferences: { nodeIntegration: false, contextIsolation: true },
  });

  _progressWin.on('closed', () => {
    _progressWin = null;
    app.quit();
  });

  const html = `<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
  body { font-family: "Segoe UI", sans-serif; margin: 0; display: flex;
         align-items: center; justify-content: center; height: 100vh;
         background: #fff; }
  .wrap { text-align: center; padding: 24px; width: 100%; }
  .logo { font-size: 28px; margin-bottom: 8px; }
  #msg-title  { font-size: 15px; color: #222; margin-top: 8px; font-weight: 600; }
  #msg-detail { font-size: 12px; color: #666; margin-top: 8px; min-height: 42px; white-space: pre-wrap; }
  .spinner { width: 32px; height: 32px; border: 3px solid #eee;
             border-top-color: #0078d4; border-radius: 50%;
             animation: spin 0.8s linear infinite; margin: 12px auto 0; }
  @keyframes spin { to { transform: rotate(360deg); } }
</style></head>
<body><div class="wrap">
  <div class="logo">🦊</div>
  <div id="msg-title">${_progressState.title}</div>
  <div id="msg-detail">${_progressState.detail}</div>
  <div class="spinner"></div>
</div></body></html>`;

  _progressWin.loadURL('data:text/html;charset=utf-8,' + encodeURIComponent(html));
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
    await registerWindowsRunOnceResume(app.getPath('exe'));
    const { response } = await dialog.showMessageBox({
      type: 'warning',
      title: 'Restart required',
      message: 'Docker was installed/started but is not ready yet.',
      detail: 'A restart is recommended before trying Fox in the box again.',
      buttons: ['Restart now', 'Close'],
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
  if (code === 'IMAGE_PULL_TIMEOUT') return 'Check network connectivity and retry. Corporate proxies/firewalls can block container pulls.';
  if (code === 'HEALTH_TIMEOUT') return 'Container started but app is not healthy yet. Wait a bit longer or restart Docker and try again.';
  if (code === 'ACCESS_MODE_CANCELLED') return 'Relaunch Fox in the box and pick a network option, or set FOX_ACCESS_MODE=1|2|3 before starting.';
  return 'Check diagnostics and logs, then retry.';
}

async function startFromTray() {
  showProgress('Starting Fox in the box…');
  try {
    if (typeof docker.ensureDockerAccessModeChosen === 'function') {
      await docker.ensureDockerAccessModeChosen();
    }
    await ensureContainerHealthy({
      docker,
      waitUntilHealthy,
      showProgress,
      openOnboarding: () => shell.openExternal(APP_HOME_URL),
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
      openOnboarding: () => shell.openExternal(APP_HOME_URL),
      onDaemonNotReady: ({ platform }) => showDaemonRecoveryRequired(platform),
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
