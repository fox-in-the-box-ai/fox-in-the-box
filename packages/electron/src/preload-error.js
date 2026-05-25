'use strict';
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('fitbError', {
  getData: () => ipcRenderer.invoke('error:get-data'),
  copyDiagnostics: () => ipcRenderer.send('error:copy'),
  close: () => ipcRenderer.send('error:close'),
});
