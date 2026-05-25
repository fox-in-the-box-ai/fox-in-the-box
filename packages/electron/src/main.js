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
let _setupInProgress = false;

/** Set when Fox is launched via HKCU RunOnce after a Docker-install reboot. */
const resumeAfterReboot = process.platform === 'win32'
  && process.argv.some((arg) => arg === '--resume-setup' || arg === '--resume-setup=true');

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

const INSTALL_STEPS = [
  { label: 'Checking system',             match: 'Initialize app' },
  { label: 'Setting up Docker',           match: 'Prepare Docker' },
  { label: 'Pulling container image',     match: 'Ensure container image' },
  { label: 'Starting container',          match: 'Prepare container' },
  { label: 'Waiting for Fox to be ready', match: 'Wait for services' },
  { label: 'Opening Fox',                 match: 'Open setup wizard' },
];

function _activeStepIndex(title) {
  if (!title) return -1;
  for (let i = INSTALL_STEPS.length - 1; i >= 0; i--) {
    if (title.includes(INSTALL_STEPS[i].match)) return i;
  }
  if (title.includes('image') || title.includes('pull')) return 2;
  if (title.includes('Docker')) return 1;
  if (title.includes('container') || title.includes('Container')) return 3;
  if (title.includes('health') || title.includes('ready') || title.includes('healthy')) return 4;
  return 0;
}

/** Human-readable line for the diagnostics pane (strip orchestrator step prefix). */
function progressDiagnosticsLine(title, explicitDetail) {
  if (typeof explicitDetail === 'string' && explicitDetail.trim().length > 0) {
    return explicitDetail.trim();
  }
  const m = String(title || '').match(/^Step \d+\/\d+ - [^:]+: (.+)$/);
  return m ? m[1].trim() : String(title || '').trim();
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

  const idx = _activeStepIndex(_progressState.title);
  const logLine = progressDiagnosticsLine(_progressState.title, update.detail);

  if (_progressWin) {
    _progressWin.webContents.send('progress:step', idx);
    if (logLine) {
      _progressWin.webContents.send('progress:log', logLine);
    }
    return;
  }

  _progressWin = new BrowserWindow({
    width: 620,
    height: 560,
    resizable: false,
    minimizable: false,
    maximizable: false,
    closable: true,
    alwaysOnTop: true,
    frame: true,
    title: 'Fox in the Box — Setting up',
    icon: APP_ICON,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload-progress.js'),
    },
  });

  _progressWin.on('closed', async () => {
    _progressWin = null;
    if (_setupInProgress && !_fatalStartup) {
      log.info('[startup] Setup progress window closed during installation');
      const parent = getDialogParent();
      const { response } = await dialog.showMessageBox(parent, {
        type: 'warning',
        title: 'Quit setup?',
        message: 'Fox in the box setup is still in progress.',
        detail:
          'Docker may still be starting in the background. If you quit now, reopen Fox from the Start menu to continue.',
        buttons: ['Quit setup', 'Keep waiting'],
        defaultId: 1,
        cancelId: 1,
      });
      if (response !== 0) {
        showProgress(_progressState.title || 'Setting up…');
        return;
      }
    }
    app.quit();
  });

  _progressWin.loadFile(path.join(__dirname, '..', 'assets', 'progress.html'));
  _progressWin.setMenu(null);

  // Send current state once the page is ready. Use _progressState at fire time,
  // not the idx captured at window-creation time (startup may have advanced).
  _progressWin.webContents.once('did-finish-load', () => {
    if (!_progressWin || _progressWin.isDestroyed()) return;
    const currentIdx = _activeStepIndex(_progressState.title);
    _progressWin.webContents.send('progress:step', currentIdx);
    const logLine = progressDiagnosticsLine(_progressState.title, _progressState.detail);
    if (logLine) {
      _progressWin.webContents.send('progress:log', logLine);
    }
  });
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

// Error data stored here so the preload's ipcMain.handle can return it synchronously.
let _errorData = null;

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

  _errorData = {
    sessionId, phase, code, message, remediation, diagnosticsText,
    logPath: path.join(app.getPath('logs'), 'main.log'),
  };

  const win = new BrowserWindow({
    width: 560,
    height: 400,
    resizable: false,
    minimizable: false,
    maximizable: false,
    closable: true,
    alwaysOnTop: true,
    frame: true,
    title: 'Fox in the Box — Error',
    icon: APP_ICON,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload-error.js'),
    },
  });

  ipcMain.handleOnce('error:get-data', () => _errorData);
  ipcMain.once('error:copy', () => {
    clipboard.writeText(diagnosticsText);
    dialog.showMessageBox(win, {
      type: 'info',
      message: 'Diagnostics copied to clipboard.',
      buttons: ['OK'],
    });
  });
  ipcMain.once('error:close', () => win.close());

  win.loadFile(path.join(__dirname, '..', 'assets', 'error.html'));
  win.setMenu(null);

  win.on('closed', () => {
    _errorData = null;
    if (_fatalStartup) app.exit(1);
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
      await dialog.showMessageBox(getDialogParent(), {
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
    waitForDaemon: (ms, sp, phaseStartedAt) => _waitForDaemon(
      () => docker.isDaemonRunning(),
      ms || 90_000,
      1_000,
      Date.now,
      (t) => new Promise((r) => setTimeout(r, t)),
      sp || progressCb,
      phaseStartedAt
    ),
    runCommand: (cmd, opts) => _runCommandVerbose(cmd, { windowsHide: true, ...opts }, (line) => {
      showProgress({ detail: line });
    }),
    spawnDetached,
    showProgress: progressCb,
    showRebootRequired: () => showDaemonRecoveryRequired('win32'),
    showError,
    setForegroundYield,
    resumeAfterReboot,
  });
}

// ─── macOS Docker install (kept separate) ────────────────────────────────────

async function installDockerMac(progressCb = showProgress) {
  const { response } = await dialog.showMessageBox(getDialogParent(), {
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
    const { response } = await dialog.showMessageBox(getDialogParent(), {
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
    const { response } = await dialog.showMessageBox(getDialogParent(), {
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
      const { response } = await dialog.showMessageBox(getDialogParent(), {
        type: 'info',
        title: 'Fox in the box — Ready',
        message: 'Fox in the box is ready!',
        detail: lines + '\n\nClick OK to open Fox.',
        buttons: ['OK', 'Copy Tailscale URL'],
        defaultId: 0,
      });
      if (response === 1) clipboard.writeText(tailnetUrl);
    } else {
      await dialog.showMessageBox(getDialogParent(), {
        type: 'info',
        title: 'Fox in the box — Tailscale not connected yet',
        message: 'Tailscale hasn\'t connected yet.',
        detail: 'Open the Tailscale app, sign in if prompted, and wait until it shows "Connected".\n\nFox is opening locally in the meantime. Once Tailscale connects, your tailnet URL will be available from the Tailscale menu.',
        buttons: ['OK'],
        defaultId: 0,
      });
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
  if (resumeAfterReboot) {
    log.info('[startup] Post-reboot resume (--resume-setup)');
  }

  _setupInProgress = true;
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
      _setupInProgress = false;
      app.quit();
      return;
    }
  } catch (err) {
    _setupInProgress = false;
    await handleStartupError(err);
    return;
  }
  _setupInProgress = false;

  createTray(true, {
    startFlow: startFromTray,
    openApp: () => shell.openExternal(APP_HOME_URL),
  });
  setRunning(true);

  updater.init(null);
  updateWindow.init();
}
