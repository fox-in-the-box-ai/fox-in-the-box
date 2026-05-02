'use strict';

/**
 * preload.js — contextBridge between renderer (web UI) and main process
 *
 * Exposes a minimal `window.foxUpdater` API so the web UI can:
 *  - Trigger an update check
 *  - Download an available update
 *  - Install (quit and apply) a downloaded update
 *  - Listen for update lifecycle events
 */

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('foxUpdater', {
  /** Trigger a manual update check */
  check: () => ipcRenderer.invoke('update:check'),

  /** Download the available update */
  download: () => ipcRenderer.invoke('update:download'),

  /** Quit and install the downloaded update */
  install: () => ipcRenderer.invoke('update:install'),

  /** Subscribe to an update lifecycle event. Returns an unsubscribe function. */
  on: (channel, listener) => {
    const allowed = [
      'update:checking',
      'update:available',
      'update:not-available',
      'update:progress',
      'update:downloaded',
      'update:error',
    ];
    if (!allowed.includes(channel)) return () => {};
    const wrapped = (_event, payload) => listener(payload);
    ipcRenderer.on(channel, wrapped);
    return () => ipcRenderer.removeListener(channel, wrapped);
  },
});
