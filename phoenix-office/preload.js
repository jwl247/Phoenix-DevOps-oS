// preload.js — Phoenix Office (standalone)
// Narrow renderer bridge. The Office window is sandboxed (no Node in the
// page); every privileged action goes through one of these allow-listed
// channels to the handlers in main.js.

const { contextBridge, ipcRenderer } = require('electron');

const CHANNELS = new Set([
  'office:whoami', 'office:templates', 'office:libreoffice-status',
  'office:google-signin-start', 'office:google-signin-poll', 'office:google-signin-cancel',
  'office:new', 'office:fill', 'office:hand', 'office:sign', 'office:reject',
  'office:change-order',
  'office:verify', 'office:qr',
  'office:legal-hold', 'office:legal-hold-release', 'office:legal-hold-status', 'office:legal-holds-report',
  'office:jobs-list', 'office:jobs-save', 'office:jobs-delete',
  'office:autosave', 'office:open', 'office:open-path', 'office:recent',
  'office:browse', 'office:reference', 'office:reference-clear', 'office:history',
  'office:copilot', 'office:compose', 'office:export-pdf',
  'office:convert', 'office:convert-formats',
  'office:apps', 'office:launch-app',
  'office:agent-message', 'office:agent-confirm', 'office:agent-reset',
  'office:project-new', 'office:project-list', 'office:project-get', 'office:project-update',
  'office:project-set-bid-factor', 'office:project-next-bid-question',
  'office:project-phases-list', 'office:project-phase-create', 'office:project-phase-advance', 'office:project-award',
  'office:project-checklist-list', 'office:project-checklist-seed', 'office:project-checklist-decide', 'office:project-checklist-history',
  'office:checklist-catalog',
  'office:project-documents-list', 'office:project-document-new', 'office:project-print-phase',
]);

const EVENTS = new Set(['office:export-progress']);

contextBridge.exposeInMainWorld('office', {
  invoke(channel, payload) {
    if (!CHANNELS.has(channel)) {
      return Promise.reject(new Error(`IPC channel not allowed: ${channel}`));
    }
    return ipcRenderer.invoke(channel, payload);
  },
  on(event, cb) {
    if (!EVENTS.has(event)) return () => {};
    const handler = (_e, payload) => cb(payload);
    ipcRenderer.on(event, handler);
    return () => ipcRenderer.removeListener(event, handler);
  },
});
