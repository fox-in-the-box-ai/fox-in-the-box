'use strict';

/**
 * updater.js — electron-updater integration for Fox in the Box
 *
 * Responsibilities:
 *  - Check GitHub Releases for a newer version on startup (after a short delay)
 *  - Expose IPC handlers so the web UI can trigger a check or install
 *  - Emit progress events back to the renderer via the main window's webContents
 *  - Add "Check for updates" to the tray menu
 *
 * IPC channels (main → renderer, via webContents.send):
 *  'update:checking'            — check started
 *  'update:available'  { version, releaseNotes }
 *  'update:not-available'
 *  'update:progress'   { percent }
 *  'update:downloaded' { version }
 *  'update:error'      { message }
 *
 * IPC channels (renderer → main, via ipcRenderer.invoke):
 *  'update:check'    — trigger a manual check
 *  'update:install'  — quit and install the downloaded update
 */

const { ipcMain, dialog, app } = require('electron');
const { autoUpdater }          = require('electron-updater');
const log                      = require('electron-log');

autoUpdater.logger = log;
autoUpdater.logger.transports.file.level = 'info';

// Do not auto-download — let the user decide after seeing the notification
autoUpdater.autoDownload = false;
autoUpdater.autoInstallOnAppQuit = true;

let _mainWindow = null;   // set via init()
let _checking   = false;

// ─── Internal helpers ────────────────────────────────────────────────────────

function send(channel, payload) {
  if (_mainWindow && !_mainWindow.isDestroyed()) {
    _mainWindow.webContents.send(channel, payload);
  }
}

// ─── autoUpdater event wiring ────────────────────────────────────────────────

autoUpdater.on('checking-for-update', () => {
  log.info('[updater] Checking for update…');
  send('update:checking');
});

autoUpdater.on('update-available', (info) => {
  log.info('[updater] Update available:', info.version);
  _checking = false;
  send('update:available', { version: info.version, releaseNotes: info.releaseNotes });
});

autoUpdater.on('update-not-available', () => {
  log.info('[updater] Already up to date');
  _checking = false;
  send('update:not-available');
});

autoUpdater.on('download-progress', (progress) => {
  log.info(`[updater] Download progress: ${Math.round(progress.percent)}%`);
  send('update:progress', { percent: Math.round(progress.percent) });
});

autoUpdater.on('update-downloaded', (info) => {
  log.info('[updater] Update downloaded:', info.version);
  send('update:downloaded', { version: info.version });
});

autoUpdater.on('error', (err) => {
  log.error('[updater] Error:', err.message);
  _checking = false;
  send('update:error', { message: err.message });
});

// ─── IPC handlers (called from renderer / web UI via preload) ────────────────

ipcMain.handle('update:check', async () => {
  if (_checking) return { status: 'already-checking' };
  _checking = true;
  try {
    await autoUpdater.checkForUpdates();
    return { status: 'ok' };
  } catch (err) {
    _checking = false;
    return { status: 'error', message: err.message };
  }
});

ipcMain.handle('update:download', async () => {
  try {
    await autoUpdater.downloadUpdate();
    return { status: 'ok' };
  } catch (err) {
    return { status: 'error', message: err.message };
  }
});

ipcMain.handle('update:install', () => {
  autoUpdater.quitAndInstall(false, true);
});

// ─── Public API ──────────────────────────────────────────────────────────────

/**
 * Initialise the updater.
 *
 * @param {BrowserWindow} mainWindow  The window to receive update events.
 *                                    Pass null if using tray-only mode.
 * @param {object}        opts
 * @param {number}        opts.startupDelayMs  ms to wait before first check (default 10000)
 */
function init(mainWindow, { startupDelayMs = 10_000 } = {}) {
  _mainWindow = mainWindow;

  // Delay the startup check so it does not slow down initial render
  setTimeout(async () => {
    log.info('[updater] Running startup update check');
    try {
      await autoUpdater.checkForUpdates();
    } catch (err) {
      log.warn('[updater] Startup check failed (offline?):', err.message);
    }
  }, startupDelayMs);
}

/**
 * Trigger a manual update check. Suitable for calling from the tray menu.
 * Shows a dialog if no update is found (so the user gets feedback).
 */
async function checkForUpdatesManual() {
  _checking = true;
  try {
    const result = await autoUpdater.checkForUpdates();
    if (!result || !result.updateInfo) {
      _checking = false;
      dialog.showMessageBox({
        type: 'info',
        title: 'Fox in the Box',
        message: 'You are running the latest version.',
      });
    }
    // If an update is available, the 'update-available' event fires and the UI handles it
  } catch (err) {
    _checking = false;
    log.error('[updater] Manual check failed:', err.message);
    dialog.showErrorBox('Update check failed', err.message);
  }
}

module.exports = { init, checkForUpdatesManual };
