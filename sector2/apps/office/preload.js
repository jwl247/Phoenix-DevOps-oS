// preload.js — Phoenix Office, Module 6 (2026-09-07)
// Narrow renderer bridge. The Office window is sandboxed (no Node in the
// page); every privileged action goes through one of these allow-listed
// channels to the handlers in dashboard/office-launcher.js.

const { contextBridge, ipcRenderer } = require('electron');

const CHANNELS = new Set([
  'office:whoami',
  'office:new', 'office:fill', 'office:hand', 'office:sign', 'office:reject',
  'office:change-order',
  'office:verify', 'office:qr',
  'office:open', 'office:save',
  'office:copilot',
]);

contextBridge.exposeInMainWorld('office', {
  invoke(channel, payload) {
    if (!CHANNELS.has(channel)) {
      return Promise.reject(new Error(`IPC channel not allowed: ${channel}`));
    }
    return ipcRenderer.invoke(channel, payload);
  },
});
