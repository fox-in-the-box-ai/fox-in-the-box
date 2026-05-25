'use strict';
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('fitb', {
  // Receives step index (0-based) from main process.
  onStepUpdate: (cb) => ipcRenderer.on('progress:step', (_e, idx) => cb(idx)),
  // Receives a single log line to append to the diagnostics area.
  onLogLine: (cb) => ipcRenderer.on('progress:log', (_e, line) => cb(line)),
});
