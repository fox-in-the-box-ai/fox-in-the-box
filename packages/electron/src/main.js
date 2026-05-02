'use strict';

const { app, BrowserWindow, dialog } = require('electron');
const { exec, spawn }  = require('child_process');
const path             = require('path');
const log              = require('electron-log');
const docker           = require('./docker-manager');
const { waitUntilHealthy } = require('./health-check');
const { createTray, setRunning } = require('./tray-manager');
const { shell }        = require('electron');
const updater          = require('./updater');
const updateWindow     = require('./update-window');

// Prevent multiple instances
if (!app.requestSingleInstanceLock()) {
  app.quit();
  process.exit(0);
}

// Keep app alive when all windows are closed (tray-only)
app.on('window-all-closed', (e) => e.preventDefault());

app.whenReady().then(main).catch((err) => {
  log.error('Fatal startup error:', err);
  dialog.showErrorBox('Fox in the Box — startup error', err.message);
  app.quit();
});

// ─── Helpers ────────────────────────────────────────────────────────────────

function runCommand(cmd, opts = {}) {
  return new Promise((resolve, reject) => {
    exec(cmd, opts, (error, stdout, stderr) => {
      if (error) reject(new Error(stderr || error.message));
      else resolve(stdout);
    });
  });
}

/**
 * Poll until the Docker daemon responds, up to timeoutMs.
 * Returns true if daemon came up, false on timeout.
 */
async function waitForDaemon(timeoutMs = 120_000, intervalMs = 3_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await docker.isDaemonRunning()) return true;
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  return false;
}

// ─── Progress window ─────────────────────────────────────────────────────────

let _progressWin = null;

function showProgress(message) {
  if (_progressWin) {
    _progressWin.webContents.executeJavaScript(
      `document.getElementById('msg').textContent = ${JSON.stringify(message)}`
    );
    return;
  }

  _progressWin = new BrowserWindow({
    width: 420,
    height: 160,
    resizable: false,
    minimizable: false,
    maximizable: false,
    closable: false,
    alwaysOnTop: true,
    frame: true,
    title: 'Fox in the Box — Setting up',
    webPreferences: { nodeIntegration: false, contextIsolation: true },
  });

  const html = `<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
  body { font-family: "Segoe UI", sans-serif; margin: 0; display: flex;
         align-items: center; justify-content: center; height: 100vh;
         background: #fff; }
  .wrap { text-align: center; padding: 24px; }
  .logo { font-size: 28px; margin-bottom: 8px; }
  #msg  { font-size: 14px; color: #444; margin-top: 8px; }
  .spinner { width: 32px; height: 32px; border: 3px solid #eee;
             border-top-color: #0078d4; border-radius: 50%;
             animation: spin 0.8s linear infinite; margin: 12px auto 0; }
  @keyframes spin { to { transform: rotate(360deg); } }
</style></head>
<body><div class="wrap">
  <div class="logo">🦊</div>
  <div id="msg">${message}</div>
  <div class="spinner"></div>
</div></body></html>`;

  _progressWin.loadURL('data:text/html;charset=utf-8,' + encodeURIComponent(html));
  _progressWin.setMenu(null);
}

function closeProgress() {
  if (_progressWin) { _progressWin.destroy(); _progressWin = null; }
}

// ─── Docker setup (Windows) ──────────────────────────────────────────────────

/**
 * Check if Docker Desktop is installed (but not running).
 * Returns the exe path or null.
 */
async function findDockerDesktopExe() {
  const candidates = [
    '%PROGRAMFILES%\\Docker\\Docker\\Docker Desktop.exe',
    '%LOCALAPPDATA%\\Programs\\Docker\\Docker\\Docker Desktop.exe',
  ];
  for (const c of candidates) {
    try {
      await runCommand(`if exist "${c}" (exit 0) else (exit 1)`, { shell: true });
      return c;
    } catch (_) { /* not here */ }
  }
  return null;
}

/**
 * Try to start Docker Desktop silently if installed but not running.
 * Returns true if daemon came up within timeout.
 */
async function tryStartDockerDesktop() {
  const exe = await findDockerDesktopExe();
  if (!exe) return false;

  log.info('Docker Desktop found but not running — launching it silently');
  showProgress('Starting Docker Desktop…');
  spawn(exe, [], { detached: true, stdio: 'ignore', shell: true }).unref();

  // Docker Desktop takes ~30-60s to start
  return waitForDaemon(90_000);
}

/**
 * Install Docker Engine (no GUI) via winget — silent, ~2 min, no restart needed.
 * winget installs: Docker CLI + Docker Engine (Mirantis container runtime).
 */
async function installDockerEngine() {
  log.info('Installing Docker Engine via winget (silent)');
  showProgress('Installing Docker Engine… this takes about 2 minutes.');

  // --silent suppresses all UI; --accept-* skips license prompts
  await runCommand(
    'winget install --id Docker.DockerDesktop --silent --accept-source-agreements --accept-package-agreements',
    { shell: true, timeout: 300_000 }
  ).catch(async () => {
    // winget may not be available on very old Windows 10 builds — fallback info
    log.warn('winget failed, trying direct Docker Engine install');
    showProgress('Installing Docker Engine via PowerShell…');
    // Install Docker Engine directly (no Desktop GUI)
    await runCommand(
      'powershell -NoProfile -NonInteractive -Command "' +
      'Invoke-WebRequest -UseBasicParsing https://get.docker.com/win/static/stable/x86_64/docker-24.0.9.zip -OutFile $env:TEMP\\docker.zip; ' +
      'Expand-Archive $env:TEMP\\docker.zip -DestinationPath $env:ProgramFiles\\Docker -Force; ' +
      '$env:Path += \';\' + $env:ProgramFiles + \'\\Docker\'; ' +
      'dockerd --register-service; Start-Service docker"',
      { shell: true, timeout: 300_000 }
    );
  });
}

/**
 * Full Windows Docker setup — no user steps required.
 * 1. If Docker Desktop is installed but not running → start it, wait
 * 2. If nothing → install Docker Engine silently, wait for daemon
 */
async function ensureDockerWindows() {
  // Step 1: maybe Docker Desktop is just sleeping
  const daemonUp = await tryStartDockerDesktop();
  if (daemonUp) {
    log.info('Docker Desktop started successfully');
    return;
  }

  // Step 2: nothing running → install silently
  showProgress('Docker not found — installing Docker Engine…');
  await installDockerEngine();
  showProgress('Waiting for Docker to start…');

  const ready = await waitForDaemon(120_000);
  if (!ready) {
    throw new Error(
      'Docker Engine was installed but the daemon did not start within 2 minutes.\n' +
      'Please restart your computer and reopen Fox in the Box.'
    );
  }
}

// ─── Main startup sequence ───────────────────────────────────────────────────

async function main() {
  log.info('Fox in the Box starting up');

  // 1. Initialise Docker client
  docker.init();

  // 2. Check Docker daemon — fix silently on Windows
  let dockerRunning = await docker.isDaemonRunning();
  if (!dockerRunning) {
    if (process.platform === 'win32') {
      showProgress('Setting up Docker…');
      await ensureDockerWindows();
    } else {
      // macOS: Homebrew install (synchronous, shows dialog)
      await installDockerMac();
    }

    dockerRunning = await docker.isDaemonRunning();
    if (!dockerRunning) {
      closeProgress();
      throw new Error(
        'Docker is not responding. Please restart your computer and reopen Fox in the Box.'
      );
    }
  }

  // 3. Pull image if not present
  if (!(await docker.isImagePresent())) {
    log.info('Image not found locally — pulling');
    showProgress('Downloading Fox in the Box… (this only happens once)');
    await docker.pullImage((pct) => {
      showProgress(`Downloading Fox in the Box… ${pct}%`);
      log.info(`Pull progress: ${pct}%`);
    });
    log.info('Image pull complete');
  }

  closeProgress();

  // 4. Start container if not already running
  const running = await docker.getRunningContainer();
  if (!running) {
    log.info('Container not running — starting');
    await docker.startContainer();
  } else {
    log.info('Container already running');
  }

  // 5. Wait for health
  log.info('Waiting for container to become healthy');
  await waitUntilHealthy();

  // 6. Open browser
  log.info('Opening browser at http://localhost:8787');
  await shell.openExternal('http://localhost:8787');

  // 7. Create tray icon
  createTray(true);
  setRunning(true);

  // 8. Initialise auto-updater (no BrowserWindow in tray-only mode — pass null)
  updater.init(null);
  updateWindow.init();
}

// ─── macOS Docker install (kept separate) ────────────────────────────────────

async function installDockerMac() {
  const { response } = await dialog.showMessageBox({
    type: 'question',
    buttons: ['Install Docker', 'Cancel'],
    defaultId: 0,
    cancelId: 1,
    title: 'Docker not found',
    message: 'Docker Desktop is required but was not found.',
    detail: 'Fox in the Box will install it via Homebrew.\n\nThis may take a few minutes.',
  });

  if (response !== 0) throw new Error('User cancelled Docker installation');

  log.info('Installing Docker via Homebrew');
  await runCommand('brew install --cask docker');
  log.info('Docker install command finished — waiting 5s for daemon');
  await new Promise((r) => setTimeout(r, 5000));
}
