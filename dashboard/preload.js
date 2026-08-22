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
  // hud-layout-backend.js
  'activate-venv', 'detect-venv', 'get-dropdown-slots',
  'get-external-app-paths', 'get-glossary', 'launch-external-app',
  'open-exe-dialog', 'set-active-slot', 'set-dropdown-slot',
  'set-external-app-path',
  // ps7-shell.js
  'ps7-shell-get-cwd', 'ps7-shell-run',
  // pagefile management
  'get-pagefile-status', 'move-pagefile', 'delete-pagefile'
]);

contextBridge.exposeInMainWorld('phoenix', {
  invoke(channel, ...args) {
    if (!ALLOWED_CHANNELS.has(channel)) {
      return Promise.reject(new Error(`IPC channel not allowed: ${channel}`));
    }
    return ipcRenderer.invoke(channel, ...args);
  }
});
