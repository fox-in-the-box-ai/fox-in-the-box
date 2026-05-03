'use strict';

const { app, BrowserWindow, dialog } = require('electron');
const { spawn }                       = require('child_process');
const path                            = require('path');
const log                             = require('electron-log');
const docker                          = require('./docker-manager');
const { waitUntilHealthy }            = require('./health-check');
const { createTray, setRunning }      = require('./tray-manager');
const { shell }                       = require('electron');
const updater                         = require('./updater');
const updateWindow                    = require('./update-window');
const {
  waitForDaemon:          _waitForDaemon,
  ensureDockerWindows:    _ensureDockerWindows,
} = require('./startup');

// Prevent multiple instances
if (!app.requestSingleInstanceLock()) {
  app.quit();
  process.exit(0);
}

// Keep app alive when all windows are closed (tray-only)
app.on('window-all-closed', (e) => e.preventDefault());

app.whenReady().then(main).catch((err) => {
  log.error('Fatal startup error:', err);
  showError(err.message || String(err));
});

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
    closable: true,
    alwaysOnTop: true,
    frame: true,
    title: 'Fox in the Box — Setting up',
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
  if (_progressWin) {
    _progressWin.removeAllListeners('closed');
    _progressWin.destroy();
    _progressWin = null;
  }
}

/**
 * Replace the progress window with an error screen.
 * Window is closable so the user is never stuck.
 */
function showError(message) {
  closeProgress();

  const win = new BrowserWindow({
    width: 480,
    height: 240,
    resizable: false,
    minimizable: false,
    maximizable: false,
    closable: true,
    alwaysOnTop: true,
    frame: true,
    title: 'Fox in the Box — Error',
    webPreferences: { nodeIntegration: false, contextIsolation: true },
  });

  const escaped = message
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/\n/g, '<br>');

  const html = `<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
  body { font-family: "Segoe UI", sans-serif; margin: 0; display: flex;
         align-items: center; justify-content: center; height: 100vh;
         background: #fff; }
  .wrap { text-align: center; padding: 32px; max-width: 400px; }
  .logo { font-size: 32px; margin-bottom: 12px; }
  h2 { font-size: 15px; margin: 0 0 10px; color: #c0392b; }
  p  { font-size: 13px; color: #555; margin: 0 0 20px; line-height: 1.6; text-align: left; }
  button { background: #444; color: #fff; border: none; padding: 8px 24px;
           font-size: 13px; border-radius: 6px; cursor: pointer; }
  button:hover { background: #222; }
</style></head>
<body><div class="wrap">
  <div class="logo">🦊</div>
  <h2>Something went wrong</h2>
  <p>${escaped}</p>
  <button onclick="window.close()">Close</button>
</div></body></html>`;

  win.loadURL('data:text/html;charset=utf-8,' + encodeURIComponent(html));
  win.setMenu(null);
}

/**
 * Replace the progress window with a "please restart" screen.
 * Shows a friendly message with a Restart Now button.
 * App exits after restart is triggered (or user closes the window).
 */
function showRebootRequired() {
  closeProgress();

  const win = new BrowserWindow({
    width: 480,
    height: 220,
    resizable: false,
    minimizable: false,
    maximizable: false,
    alwaysOnTop: true,
    frame: true,
    title: 'Fox in the Box — Restart required',
    webPreferences: { nodeIntegration: true, contextIsolation: false },
  });

  const html = `<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
  body { font-family: "Segoe UI", sans-serif; margin: 0; display: flex;
         align-items: center; justify-content: center; height: 100vh;
         background: #fff; }
  .wrap { text-align: center; padding: 32px; }
  .logo { font-size: 32px; margin-bottom: 12px; }
  h2 { font-size: 16px; margin: 0 0 8px; color: #111; }
  p  { font-size: 13px; color: #555; margin: 0 0 20px; line-height: 1.5; }
  button { background: #C8743A; color: #fff; border: none; padding: 10px 28px;
           font-size: 14px; border-radius: 6px; cursor: pointer; }
  button:hover { background: #A85A32; }
</style></head>
<body><div class="wrap">
  <div class="logo">🦊</div>
  <h2>One restart required</h2>
  <p>Docker was just installed. A quick restart is needed<br>before Fox in the Box can run.</p>
  <button onclick="require('electron').ipcRenderer.send('do-reboot')">Restart now</button>
</div></body></html>`;

  win.loadURL('data:text/html;charset=utf-8,' + encodeURIComponent(html));
  win.setMenu(null);

  const { ipcMain } = require('electron');
  ipcMain.once('do-reboot', () => {
    require('child_process').exec('shutdown /r /t 3 /c "Restarting to finish Docker setup"');
    setTimeout(() => app.quit(), 500);
  });
}

// ─── Docker setup (Windows) ──────────────────────────────────────────────────
// Logic extracted to startup.js for testability.
// main.js wires up the Electron-specific deps (showProgress, showRebootRequired, spawn).

function spawnDetached(exe) {
  spawn(exe, [], { detached: true, stdio: 'ignore', shell: true }).unref();
}

async function ensureDockerWindows() {
  await _ensureDockerWindows({
    isDaemonRunning:     () => docker.isDaemonRunning(),
    waitForDaemon:       (ms, sp) => _waitForDaemon(() => docker.isDaemonRunning(), ms || 90_000, 3_000, Date.now, (t) => new Promise(r => setTimeout(r, t)), sp || showProgress),
    runCommand:          (cmd, opts) => require('./startup').runCommandVerbose(cmd, opts, showProgress),
    spawnDetached,
    showProgress,
    showRebootRequired,
    showError,
  });
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
      showRebootRequired();
      return;
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
