// steam-launcher.js
// Adds a STEAM button to the right-side action panel — launches the Steam
// client through Phoenix. Same shape as google-launcher.js on purpose: one
// IPC channel, one button, one action.
//
// Wire into main.js alongside the other action buttons:
//   require('./steam-launcher').register({ ipcMain, shell });
//
// This launches the client, not a specific game — "something both can run"
// (a title Laurie and Jerry can both play) is a separate decision. Once
// that's picked, its Steam app ID can be passed as `appId` to open straight
// into it: steam://rungameid/<appid>.

const fs = require('fs');
const path = require('path');
const { execFile } = require('child_process');

const STORE_URL = 'https://store.steampowered.com';

// Common Steam install locations on Windows. First one that exists wins.
const STEAM_CANDIDATES = [
    'C:\\Program Files (x86)\\Steam\\steam.exe',
    'C:\\Program Files\\Steam\\steam.exe'
];

function findSteam() {
    for (const c of STEAM_CANDIDATES) {
        try {
            if (c && fs.existsSync(c)) return c;
        } catch (_) { /* ignore */ }
    }
    return null;
}

function register({ ipcMain, shell }) {
    // appId (optional): a Steam app ID to launch straight into that game
    // via steam.exe's own -applaunch flag, instead of just opening the client.
    ipcMain.handle('launch-steam', async (event, { appId } = {}) => {
        const steam = findSteam();

        try {
            if (steam) {
                const args = appId ? ['-applaunch', String(appId)] : [];
                const proc = execFile(steam, args, { detached: true, stdio: 'ignore' });
                proc.unref();
                return { success: true, via: 'steam.exe', exe: steam, appId: appId || null };
            }

            // Fallback: open the Steam store page in the default browser so
            // there's always *something* useful to click, even without a
            // local install found.
            if (shell && typeof shell.openExternal === 'function') {
                await shell.openExternal(STORE_URL);
                return { success: true, via: 'default-browser', url: STORE_URL };
            }

            return {
                success: false,
                error: 'Steam not found and no shell.openExternal available. Install Steam or check the path.'
            };
        } catch (e) {
            return { success: false, error: e.message };
        }
    });

    ipcMain.handle('get-steam-status', async () => {
        const steam = findSteam();
        return { steamInstalled: !!steam, steamPath: steam };
    });
}

module.exports = { register, findSteam, STORE_URL };
