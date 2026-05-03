'use strict';

const { app, Tray, Menu, shell, dialog } = require('electron');
const path    = require('path');
const log     = require('electron-log');
const docker  = require('./docker-manager');
const updater = require('./updater');

const ICON_PATH = process.platform === 'win32'
  ? path.join(__dirname, '..', 'assets', 'icon.ico')
  : path.join(__dirname, '..', 'assets', 'icon.png');
const APP_URL   = 'http://localhost:8787';

let tray       = null;
let isRunning  = false;
let startFlow  = null;

function setRunning(state) {
  isRunning = state;
  if (tray) buildMenu();
}

function buildMenu() {
  const statusLabel = isRunning ? '🟢 Fox is running' : '🔴 Fox is stopped';

  const menu = Menu.buildFromTemplate([
    { label: statusLabel, enabled: false },
    { type: 'separator' },
    {
      label: 'Open Fox',
      click: () => shell.openExternal(APP_URL),
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

  tray.setToolTip('Fox in the box');
  buildMenu();

  log.info('Tray created');
}

module.exports = { createTray, setRunning };
