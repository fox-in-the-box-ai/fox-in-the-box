'use strict';

/**
 * update-window.js — update notification UI window
 *
 * Shows a small always-on-top window when a new version is available.
 * The user can dismiss, download, or install from here.
 * This is the "in-UI" surface since the web UI runs in the default browser
 * (not a BrowserWindow with a preload).
 */

const { BrowserWindow, ipcMain, app } = require('electron');
const path    = require('path');
const log     = require('electron-log');
const updater = require('./updater');

let _win        = null;
let _downloaded = false;

function close() {
  if (_win && !_win.isDestroyed()) _win.close();
  _win = null;
}

function show({ version, releaseNotes }) {
  if (_win && !_win.isDestroyed()) {
    _win.focus();
    return;
  }

  _win = new BrowserWindow({
    width: 400,
    height: 220,
    resizable: false,
    minimizable: false,
    maximizable: false,
    alwaysOnTop: true,
    title: 'Fox in the Box — Update available',
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js'),
    },
  });

  _win.loadURL('data:text/html;charset=utf-8,' + encodeURIComponent(buildHtml(version)));
  _win.on('closed', () => { _win = null; });
}

function showDownloaded({ version }) {
  if (_win && !_win.isDestroyed()) _win.close();
  _downloaded = true;

  _win = new BrowserWindow({
    width: 400,
    height: 200,
    resizable: false,
    minimizable: false,
    maximizable: false,
    alwaysOnTop: true,
    title: 'Fox in the Box — Ready to install',
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js'),
    },
  });

  _win.loadURL('data:text/html;charset=utf-8,' + encodeURIComponent(buildReadyHtml(version)));
  _win.on('closed', () => { _win = null; });
}

// ─── HTML templates ──────────────────────────────────────────────────────────

function buildHtml(version) {
  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'self' 'unsafe-inline'">
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, "Segoe UI", sans-serif;
    font-size: 14px;
    background: #ffffff;
    color: #111;
    display: flex;
    flex-direction: column;
    height: 100vh;
    padding: 24px;
    gap: 12px;
  }
  h2 { font-size: 16px; font-weight: 600; }
  p  { color: #444; line-height: 1.5; }
  .version { font-weight: 600; color: #111; }
  .actions { display: flex; gap: 8px; margin-top: auto; }
  button {
    flex: 1;
    padding: 8px 0;
    border: none;
    border-radius: 6px;
    cursor: pointer;
    font-size: 13px;
    font-weight: 500;
  }
  .primary { background: #111; color: #fff; }
  .primary:hover { background: #333; }
  .secondary { background: #f0f0f0; color: #333; }
  .secondary:hover { background: #e0e0e0; }
  #progress { display: none; height: 4px; background: #e0e0e0; border-radius: 2px; }
  #progress-bar { height: 100%; background: #111; border-radius: 2px; width: 0%; transition: width 0.3s; }
</style>
</head>
<body>
<h2>Update available</h2>
<p>Version <span class="version">${version}</span> is ready to download.</p>
<div id="progress"><div id="progress-bar"></div></div>
<div class="actions">
  <button class="secondary" id="btn-later">Later</button>
  <button class="primary"   id="btn-download">Download update</button>
</div>
<script>
  const later    = document.getElementById('btn-later');
  const download = document.getElementById('btn-download');
  const progress = document.getElementById('progress');
  const bar      = document.getElementById('progress-bar');

  later.onclick = () => window.close();

  download.onclick = async () => {
    download.disabled = true;
    download.textContent = 'Downloading…';
    later.disabled = true;
    progress.style.display = 'block';

    const unsub = window.foxUpdater.on('update:progress', ({ percent }) => {
      bar.style.width = percent + '%';
    });

    window.foxUpdater.on('update:downloaded', () => {
      unsub();
      window.close();
    });

    window.foxUpdater.on('update:error', ({ message }) => {
      unsub();
      download.disabled = false;
      download.textContent = 'Retry';
      later.disabled = false;
      alert('Download failed: ' + message);
    });

    await window.foxUpdater.download();
  };
</script>
</body>
</html>`;
}

function buildReadyHtml(version) {
  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'self' 'unsafe-inline'">
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, "Segoe UI", sans-serif;
    font-size: 14px;
    background: #ffffff;
    color: #111;
    display: flex;
    flex-direction: column;
    height: 100vh;
    padding: 24px;
    gap: 12px;
  }
  h2 { font-size: 16px; font-weight: 600; }
  p  { color: #444; line-height: 1.5; }
  .version { font-weight: 600; color: #111; }
  .actions { display: flex; gap: 8px; margin-top: auto; }
  button {
    flex: 1;
    padding: 8px 0;
    border: none;
    border-radius: 6px;
    cursor: pointer;
    font-size: 13px;
    font-weight: 500;
  }
  .primary { background: #111; color: #fff; }
  .primary:hover { background: #333; }
  .secondary { background: #f0f0f0; color: #333; }
  .secondary:hover { background: #e0e0e0; }
</style>
</head>
<body>
<h2>Ready to install</h2>
<p>Version <span class="version">${version}</span> has been downloaded. Restart Fox in the Box to apply the update.</p>
<div class="actions">
  <button class="secondary" id="btn-later">Restart later</button>
  <button class="primary"   id="btn-install">Restart and install</button>
</div>
<script>
  document.getElementById('btn-later').onclick   = () => window.close();
  document.getElementById('btn-install').onclick = () => window.foxUpdater.install();
</script>
</body>
</html>`;
}

// ─── Wire updater events → windows ──────────────────────────────────────────

function init() {
  const { autoUpdater } = require('electron-updater');

  autoUpdater.on('update-available', (info) => {
    show({ version: info.version, releaseNotes: info.releaseNotes });
  });

  autoUpdater.on('update-downloaded', (info) => {
    showDownloaded({ version: info.version });
  });
}

module.exports = { init, close };
