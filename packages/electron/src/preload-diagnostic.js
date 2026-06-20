'use strict';
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('fitbDiagnostic', {
  gather: () => ipcRenderer.invoke('diagnostic:gather'),
  copy: (text) => ipcRenderer.send('diagnostic:copy', text),
  close: () => ipcRenderer.send('diagnostic:close'),
});
