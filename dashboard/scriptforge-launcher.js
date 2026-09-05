// scriptforge-launcher.js
// Opens ScriptForge (sector2/apps/scriptforge/index.html) in its own Electron
// window — a real Entourage app launch, not a kick-out to the OS default
// browser. Same shape as steam-launcher.js/google-launcher.js: one IPC
// channel, one action.
//
// Wire into main.js alongside the other launchers:
//   require('./scriptforge-launcher').register({ ipcMain, BrowserWindow, phoenixRoot: resolvePhoenixRoot() });

const fs = require('fs');
const path = require('path');

let scriptforgeWindow = null;

function register({ ipcMain, BrowserWindow, phoenixRoot }) {
    ipcMain.handle('launch-scriptforge', async () => {
        const filePath = path.join(phoenixRoot, 'sector2', 'apps', 'scriptforge', 'index.html');
        if (!fs.existsSync(filePath)) {
            return { success: false, error: `ScriptForge not found at ${filePath}` };
        }

        if (scriptforgeWindow && !scriptforgeWindow.isDestroyed()) {
            scriptforgeWindow.show();
            scriptforgeWindow.focus();
            return { success: true, refocused: true };
        }

        scriptforgeWindow = new BrowserWindow({
            width: 1280,
            height: 860,
            minWidth: 900,
            minHeight: 600,
            title: 'ScriptForge — Phoenix DevOps OS',
            backgroundColor: '#0a0c10',
            autoHideMenuBar: true,
            webPreferences: {
                // ScriptForge's own CONSOLE tab already sandboxes pasted code in a
                // no-same-origin iframe; keeping Node fully out of this window too
                // means that sandbox isn't the only thing standing between pasted
                // code and the rest of the machine.
                sandbox: true,
                contextIsolation: true,
                nodeIntegration: false
            }
        });

        scriptforgeWindow.loadFile(filePath);
        scriptforgeWindow.on('closed', () => { scriptforgeWindow = null; });

        return { success: true, refocused: false, filePath };
    });
}

module.exports = { register };
