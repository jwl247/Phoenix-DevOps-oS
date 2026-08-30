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
    app.on('browser-window-created', (_e, win) => {
        if (!mainWindow) mainWindow = win;
        // Apply glass material as soon as the window exists so the first
        // paint is already translucent instead of flashing opaque.
        applyGlass(win);
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

    // Convenience toggle — flips between app and hud.
    ipcMain.handle('hud-toggle', async () => {
        if (!mainWindow || mainWindow.isDestroyed()) {
            return { success: false, error: 'No window yet.' };
        }
        return currentMode === 'hud' ? enterApp(mainWindow) : enterHud(mainWindow);
    });

    // Default: start in app mode. User flips to HUD from the dashboard.
    return { enterHud, enterApp, applyGlass };
}

// ── Glass material ───────────────────────────────────────────────────────
// On Windows 11 22H2+ we use the native DWM acrylic/mica backdrop so the
// blur is real (not a CSS approximation) and the window stays click-through
// on transparent pixels. On older Windows we fall back to transparent:true
// + CSS backdrop-filter (hud-glass.css).
function applyGlass(win) {
    if (!win || win.isDestroyed()) return;
    try {
        if (typeof win.setBackgroundMaterial === 'function') {
            // acrylic = transient overlay feel; mica = long-lived. Acrylic
            // reads more like a HUD floating over the desktop.
            win.setBackgroundMaterial('acrylic');
        }
    } catch (e) {
        console.warn('[hud-mode] setBackgroundMaterial failed:', e.message);
    }
    try {
        win.setBackgroundColor('#00000000');
    } catch (_) {}
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
    applyGlass(win);
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

module.exports = { install, enterHud, enterApp, applyGlass };
