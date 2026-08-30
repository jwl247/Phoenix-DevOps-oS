// google-launcher.js
// Adds a GOOGLE button to the right-side action panel that launches
// Chrome pointed at google.com (or a custom URL) through Phoenix.
//
// Wire into main.js alongside the other action buttons:
//   require('./google-launcher').register({ ipcMain, shell, BrowserWindow });
//
// Keeps the surface narrow: one IPC channel, one button, one action.

const fs = require('fs');
const path = require('path');
const { execFile } = require('child_process');

const DEFAULT_URL = 'https://www.google.com';

// Common Chrome install locations on Windows. First one that exists wins.
const CHROME_CANDIDATES = [
    'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
    path.join(process.env.LOCALAPPDATA || '', 'Google\\Chrome\\Application\\chrome.exe')
];

function findChrome() {
    for (const c of CHROME_CANDIDATES) {
        try {
            if (c && fs.existsSync(c)) return c;
        } catch (_) { /* ignore */ }
    }
    return null;
}

function register({ ipcMain, shell }) {
    ipcMain.handle('launch-google', async (event, { url } = {}) => {
        const target = (url && String(url).trim()) || DEFAULT_URL;
        const chrome = findChrome();

        try {
            if (chrome) {
                // Real Chrome window, detached so the dashboard stays responsive.
                const proc = execFile(chrome, [target], { detached: true, stdio: 'ignore' });
                proc.unref();
                return { success: true, via: 'chrome', url: target, exe: chrome };
            }

            // Fallback: open the default browser (Edge / whatever is registered).
            if (shell && typeof shell.openExternal === 'function') {
                await shell.openExternal(target);
                return { success: true, via: 'default-browser', url: target };
            }

            return {
                success: false,
                error: 'Chrome not found and no shell.openExternal available. Install Chrome or set a default browser.'
            };
        } catch (e) {
            return { success: false, error: e.message };
        }
    });

    ipcMain.handle('get-google-status', async () => {
        const chrome = findChrome();
        return {
            chromeInstalled: !!chrome,
            chromePath: chrome,
            defaultUrl: DEFAULT_URL
        };
    });
}

module.exports = { register, findChrome, DEFAULT_URL };
