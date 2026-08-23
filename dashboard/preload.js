// Narrow, audited renderer bridge. Keep Node APIs out of the dashboard page.
const { contextBridge, ipcRenderer } = require('electron');

const ALLOWED_CHANNELS = new Set([
  'ai-chat', 'check-claude-cli', 'check-ollama', 'ensure-ollama',
  'execute-command', 'get-ai-status', 'get-drives', 'get-env-vars',
  'get-laurie-guide', 'get-os-metrics', 'get-phoenix-stats',
  'get-root-tree', 'get-sector-paths', 'get-user-dirs',
  'get-user-manual', 'list-directory', 'open-file-dialog', 'open-path',
  'run-file', 'set-ai-auth',
  // clonepool-workdir.js
  'clone-file-to-workdir', 'list-clonepool-files', 'open-directory-dialog',
  // screenshot-analysis.js
  'analyze-screenshot', 'capture-screenshot',
  'live-capture-start', 'live-capture-stop', 'live-capture-status', 'live-capture-get-latest',
  // hud-layout-backend.js
  'activate-venv', 'detect-venv', 'get-dropdown-slots',
  'get-categories', 'get-custody', 'get-external-app-paths', 'get-glossary', 'launch-external-app',
  'open-exe-dialog', 'set-active-slot', 'set-dropdown-slot',
  'set-external-app-path',
  // ps7-shell.js
  'ps7-shell-get-cwd', 'ps7-shell-run',
  // pagefile management
  'get-pagefile-status', 'move-pagefile', 'delete-pagefile'
]);

// Main → renderer push events (streaming chat deltas). Separate allowlist
// from invoke's request/response channels — these are one-way and don't
// take a renderer-supplied argument, so the surface is narrower by design.
const ALLOWED_EVENTS = new Set(['ai-chat-stream-chunk']);

contextBridge.exposeInMainWorld('phoenix', {
  invoke(channel, ...args) {
    if (!ALLOWED_CHANNELS.has(channel)) {
      return Promise.reject(new Error(`IPC channel not allowed: ${channel}`));
    }
    return ipcRenderer.invoke(channel, ...args);
  },
  // Returns an unsubscribe function. `callback` receives only the payload,
  // never the raw ipcRenderer event (which carries a sender reference).
  onStream(channel, callback) {
    if (!ALLOWED_EVENTS.has(channel)) {
      throw new Error(`IPC event channel not allowed: ${channel}`);
    }
    const handler = (_event, payload) => callback(payload);
    ipcRenderer.on(channel, handler);
    return () => ipcRenderer.removeListener(channel, handler);
  }
});
