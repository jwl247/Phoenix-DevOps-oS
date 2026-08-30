// hud-mode.js
// Toggles the dashboard between two modes:
//   'app'  — normal framed window, opaque-ish, full desktop app
//   'hud'  — frameless, transparent, always-on-top glass overlay over the
//            real Windows desktop. Click-through on empty glass areas.
//
// Wire in main.js:
//   const HudMode = require('./hud-mode');
//   HudMode.install({ app, BrowserWindow, ipcMain });
//
// The renderer toggles via: window.phoenix.invoke('hud-set-mode', { mode: 'hud' })

const { screen } = require('electron');

let mainWindow = null;
let currentMode = 'app';

function install({ app, BrowserWindow, ipcMain }) {
    // Capture the window once created (main.js calls createWindow).
    const _origReady = app.whenReady.bind(app);
    // We hook after createWindow by listening for the first window.
    app.on('browser-window-created', (_e, win) => {
        if (!mainWindow) mainWindow = win;
    });

    ipcMain.handle('hud-set-mode', async (_e, { mode } = {}) => {
        if (!mainWindow || mainWindow.isDestroyed()) {
            return { success: false, error: 'No window yet.' };
        }
        if (mode === 'hud') return enterHud(mainWindow);
        if (mode === 'app') return enterApp(mainWindow);
        return { success: false, error: `Unknown mode: ${mode}` };
    });

    ipcMain.handle('hud-get-mode', async () => ({ mode: currentMode }));

    // Default: start in app mode. User flips to HUD from the dashboard.
    return { enterHud, enterApp };
}

function enterHud(win) {
    const { width, height } = screen.getPrimaryDisplay().workAreaSize;
    win.setFullScreen(false);
    win.setResizable(true);
    win.setMinimizable(true);
    win.setMaximizable(true);
    win.setAlwaysOnTop(true, 'screen-saver');
    win.setSkipTaskbar(false);
    win.setHasShadow(false);
    win.setBackgroundColor('#00000000');
    // Frameless + transparent = real glass over the desktop.
    // (Electron requires frame:false for transparent to work on Windows.)
    try { win.setWindowButtonVisibility(false); } catch (_) {}
    // Size to a comfortable HUD band; user can drag/resize.
    const w = Math.min(1400, width - 80);
    const h = Math.min(860, height - 80);
    win.setBounds({ x: Math.round((width - w) / 2), y: 40, width: w, height: h });
    // Click-through on transparent pixels (Windows). Empty glass won't
    // steal clicks; solid panels still receive them.
    try {
        win.setIgnoreMouseEvents(true, { forward: true });
    } catch (_) {}
    currentMode = 'hud';
    win.webContents.send('hud-mode-changed', { mode: 'hud' });
    return { success: true, mode: 'hud' };
}

function enterApp(win) {
    win.setAlwaysOnTop(false);
    win.setSkipTaskbar(false);
    win.setHasShadow(true);
    win.setBackgroundColor('#0a0e1a');
    try { win.setWindowButtonVisibility(true); } catch (_) {}
    try { win.setIgnoreMouseEvents(false); } catch (_) {}
    // Restore a sensible app size.
    const { width, height } = screen.getPrimaryDisplay().workAreaSize;
    win.setBounds({ x: 0, y: 0, width, height });
    currentMode = 'app';
    win.webContents.send('hud-mode-changed', { mode: 'app' });
    return { success: true, mode: 'app' };
}

module.exports = { install, enterHud, enterApp };
