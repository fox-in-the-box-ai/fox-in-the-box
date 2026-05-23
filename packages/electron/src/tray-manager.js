'use strict';

const { app, Tray, Menu, shell, dialog } = require('electron');
const { spawn } = require('child_process');
const path    = require('path');
const log     = require('electron-log');
const docker  = require('./docker-manager');
const updater = require('./updater');
const { APP_HOME_URL } = require('./app-urls');

const ICON_PATH = process.platform === 'win32'
  ? path.join(__dirname, '..', 'assets', 'icon.ico')
  : path.join(__dirname, '..', 'assets', 'icon.png');

let tray       = null;
let isRunning  = false;
let startFlow  = null;
let openApp    = null;

function setRunning(state) {
  isRunning = state;
  if (tray) buildMenu();
}

/**
 * v0.7.18 #341: complete uninstall flow for Fox's runtime state.
 *
 * Today users have to docker-stop, docker-rm, docker-rmi, and `rd /s /q`
 * the userData dir by hand to get a clean slate after an upgrade gone
 * wrong (we lived this exact dance debugging v0.7.16→v0.7.17 on
 * @roadhero's Win11 box). This puts it behind one tray click.
 *
 * Sequence:
 *   1. Confirm dialog (defaultId=cancel, destructive)
 *   2. Stop + remove the container, remove the :stable image
 *   3. Spawn a detached cleanup process that:
 *      - waits a few seconds for Electron to fully exit (release LevelDB
 *        locks Chromium holds on userData)
 *      - recursively deletes userData
 *      - exits
 *   4. app.quit() — Electron exits, the spawned process picks up
 *
 * The spawned cleanup is detached/unref'd so it survives app.quit().
 * The deletion happens AFTER Electron releases its file locks; if it
 * fired inline before quit, it would fail on Win11 with file-in-use.
 */
async function resetFoxCompletely() {
  const { response } = await dialog.showMessageBox({
    type: 'warning',
    title: 'Reset Fox completely?',
    message: 'This deletes all Fox state and starts over.',
    detail:
      'Removes:\n'
      + '  • Container "fox-in-the-box" and its image\n'
      + '  • All onboarding state, settings, profiles, and conversations\n'
      + '  • Local AI models bundled in /data (Phi-4-mini etc.)\n\n'
      + 'Your Ollama installation and host-side data are NOT touched.\n'
      + 'Fox will exit immediately after; relaunch from Start Menu to begin fresh.',
    buttons: ['Cancel', 'Yes, reset everything'],
    defaultId: 0,
    cancelId: 0,
  });
  if (response !== 1) return;

  // Docker side first — synchronous, while Electron is alive.
  try {
    await docker.removeContainerAndImage();
  } catch (err) {
    log.warn('[reset] docker cleanup failed (proceeding anyway):', err.message);
  }

  // userData deletion has to wait until Electron releases the LevelDB locks
  // Chromium holds in userData/Local Storage etc. — those release on exit.
  // Spawn a detached process that polls for app exit then deletes.
  const userDataPath = app.getPath('userData');
  spawnDetachedCleanup(userDataPath);

  log.info('[reset] cleanup spawned, quitting app');
  app.quit();
}

function spawnDetachedCleanup(userDataPath) {
  if (process.platform === 'win32') {
    // ping waits — more reliable than `timeout` for detached cmd processes.
    // `start "" /B` runs the cleanup without a console window.
    const cmd =
      `ping 127.0.0.1 -n 6 > nul && rd /s /q "${userDataPath}" 2> nul`;
    spawn('cmd.exe', ['/c', cmd], {
      detached: true,
      stdio: 'ignore',
      windowsHide: true,
    }).unref();
  } else {
    spawn('sh', ['-c', `sleep 4 && rm -rf "${userDataPath}"`], {
      detached: true,
      stdio: 'ignore',
    }).unref();
  }
}

function buildMenu() {
  const statusLabel = isRunning ? '🟢 Fox is running' : '🔴 Fox is stopped';

  const menu = Menu.buildFromTemplate([
    { label: statusLabel, enabled: false },
    { type: 'separator' },
    {
      label: 'Open Fox',
      click: () => {
        if (openApp) openApp();
        else shell.openExternal(APP_HOME_URL);
      },
    },
    {
      label: 'Restart Fox',
      click: async () => {
        try {
          await docker.restartContainer();
        } catch (err) {
          log.error('Restart failed:', err.message);
          dialog.showErrorBox('Restart failed', err.message);
        }
      },
    },
    {
      label: isRunning ? 'Stop Fox' : 'Start Fox',
      click: async () => {
        try {
          if (isRunning) {
            await docker.stopContainer();
            setRunning(false);
          } else {
            if (startFlow) await startFlow();
            else await docker.startContainer();
            setRunning(true);
          }
        } catch (err) {
          log.error('Toggle failed:', err.message);
          dialog.showErrorBox('Error', err.message);
        }
      },
    },
    { type: 'separator' },
    {
      label: 'Check for updates',
      click: () => updater.checkForUpdatesManual(),
    },
    {
      label: 'Reset Fox completely…',
      click: resetFoxCompletely,
    },
    { type: 'separator' },
    {
      label: 'Quit',
      click: async () => {
        log.info('Quit requested — stopping container');
        try {
          await docker.stopContainer();
        } catch (err) {
          log.warn('Stop on quit failed (container may already be stopped):', err.message);
        }
        app.quit();
      },
    },
  ]);

  tray.setContextMenu(menu);
}

/**
 * Create the system tray icon and initial menu.
 * @param {boolean} running  Initial running state.
 */
function createTray(running, options = {}) {
  tray      = new Tray(ICON_PATH);
  isRunning = running;
  startFlow = options.startFlow || null;
  openApp = options.openApp || null;

  tray.setToolTip('Fox in the box');
  buildMenu();

  log.info('Tray created');
}

module.exports = { createTray, setRunning };
