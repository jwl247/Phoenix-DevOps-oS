// hud-layout-backend.js
// Backend for the HUD restructure: external app launchers, dropdown-slot
// persistence, venv auto-detect against the active slot, and a real
// (not faked) glossary fetch against the worker.
//
// Wire into main.js with:
//   require('./hud-layout-backend').register({ ipcMain, spawn, dialog });
//
// All state persisted to ~/.phoenix/, same convention as phoenix.env and
// ai_auth.json — no new config directory invented.

const fs = require('fs');
const path = require('path');
const os = require('os');

const PHOENIX_CONF_DIR = path.join(os.homedir(), '.phoenix');
const SLOTS_FILE = path.join(PHOENIX_CONF_DIR, 'hud-dropdown-slots.json');
const EXTERNAL_APPS_FILE = path.join(PHOENIX_CONF_DIR, 'hud-external-apps.json');

function ensureConfDir() {
    if (!fs.existsSync(PHOENIX_CONF_DIR)) fs.mkdirSync(PHOENIX_CONF_DIR, { recursive: true });
}

function loadJson(filePath, fallback) {
    try {
        if (!fs.existsSync(filePath)) return fallback;
        return JSON.parse(fs.readFileSync(filePath, 'utf8'));
    } catch (e) {
        console.warn(`[hud-layout-backend] ${filePath} unreadable, using fallback:`, e.message);
        return fallback;
    }
}

function saveJson(filePath, data) {
    ensureConfDir();
    fs.writeFileSync(filePath, JSON.stringify(data, null, 2), 'utf8');
}

// Default: unconfigured. Real paths must come from you, once, via
// set-external-app-path — never guessed at.
const DEFAULT_EXTERNAL_APPS = {
    ps7: { exe: null, args: [] },
    bash: { exe: null, args: [] },
    githubDesktop: { exe: null, args: [] }
};

// pwsh.exe is the one exception worth a real default check, since its
// install location is standardized by the PowerShell 7 MSI installer —
// but we still verify the file exists before trusting it, never assume.
function tryDefaultPs7Path() {
    const candidate = 'C:\\Program Files\\PowerShell\\7\\pwsh.exe';
    try {
        return fs.existsSync(candidate) ? candidate : null;
    } catch (_) {
        return null;
    }
}

const DEFAULT_SLOTS = [null, null, null, null, null, null];

function register({ ipcMain, spawn, dialog }) {
    // ── External app launchers (PS7 / Bash / GitHub Desktop) ──────────────
    ipcMain.handle('get-external-app-paths', async () => {
        const saved = loadJson(EXTERNAL_APPS_FILE, {});
        const merged = { ...DEFAULT_EXTERNAL_APPS, ...saved };
        if (!merged.ps7.exe) {
            const autoPs7 = tryDefaultPs7Path();
            if (autoPs7) merged.ps7 = { exe: autoPs7, args: [] };
        }
        return merged;
    });

    ipcMain.handle('set-external-app-path', async (event, { key, exePath }) => {
        if (!['ps7', 'bash', 'githubDesktop'].includes(key)) {
            return { success: false, error: `Unknown app key: ${key}` };
        }
        if (!exePath || !fs.existsSync(exePath)) {
            return { success: false, error: `Path does not exist: ${exePath}` };
        }
        const current = loadJson(EXTERNAL_APPS_FILE, {});
        current[key] = { exe: exePath, args: [] };
        saveJson(EXTERNAL_APPS_FILE, current);
        return { success: true };
    });

    // Native picker for choosing an .exe — same consent-gate pattern as
    // the clonepool target-directory picker.
    ipcMain.handle('open-exe-dialog', async (event, options = {}) => {
        const result = await dialog.showOpenDialog({
            properties: ['openFile'],
            filters: [{ name: 'Executable', extensions: ['exe', 'cmd', 'bat'] }],
            title: options.title || 'Locate application'
        });
        if (result.canceled || !result.filePaths.length) return { success: false, canceled: true };
        return { success: true, exePath: result.filePaths[0] };
    });

    ipcMain.handle('launch-external-app', async (event, { key }) => {
        const apps = { ...DEFAULT_EXTERNAL_APPS, ...loadJson(EXTERNAL_APPS_FILE, {}) };
        if (!apps.ps7.exe) {
            const autoPs7 = tryDefaultPs7Path();
            if (autoPs7) apps.ps7 = { exe: autoPs7, args: [] };
        }
        const app = apps[key];
        if (!app || !['ps7', 'bash', 'githubDesktop'].includes(key)) {
            return { success: false, error: `Unknown app key: ${key}` };
        }
        if (!app.exe || !fs.existsSync(app.exe)) {
            return {
                success: false,
                error: `${key} not configured. Set its path first.`,
                needsConfig: true
            };
        }
        try {
            const proc = spawn(app.exe, app.args || [], { detached: true, stdio: 'ignore' });
            proc.unref();
            return { success: true };
        } catch (e) {
            return { success: false, error: e.message };
        }
    });

    // ── Dropdown slots (6 assignable working-directory shortcuts) ─────────
    ipcMain.handle('get-dropdown-slots', async () => {
        const state = loadJson(SLOTS_FILE, { slots: DEFAULT_SLOTS, activeIndex: null });
        return state;
    });

    ipcMain.handle('set-dropdown-slot', async (event, { index, dirPath }) => {
        if (typeof index !== 'number' || index < 0 || index > 5) {
            return { success: false, error: 'Slot index must be 0-5.' };
        }
        if (!dirPath || !fs.existsSync(dirPath) || !fs.statSync(dirPath).isDirectory()) {
            return { success: false, error: `Not a valid directory: ${dirPath}` };
        }
        const state = loadJson(SLOTS_FILE, { slots: [...DEFAULT_SLOTS], activeIndex: null });
        state.slots[index] = dirPath;
        saveJson(SLOTS_FILE, state);
        return { success: true, slots: state.slots };
    });

    ipcMain.handle('set-active-slot', async (event, { index }) => {
        const state = loadJson(SLOTS_FILE, { slots: [...DEFAULT_SLOTS], activeIndex: null });
        if (index !== null && (!state.slots[index])) {
            return { success: false, error: 'That slot is empty — assign a folder first.' };
        }
        const previousIndex = state.activeIndex;
        state.activeIndex = index;
        saveJson(SLOTS_FILE, state);
        return { success: true, activeIndex: index, previousIndex };
    });

    // ── Venv auto-detect against the active slot ───────────────────────────
    ipcMain.handle('detect-venv', async (event, { dirPath }) => {
        if (!dirPath || !fs.existsSync(dirPath)) {
            return { success: false, error: 'No active working directory to check.' };
        }
        const candidates = [
            path.join(dirPath, 'venv', 'Scripts', 'Activate.ps1'),
            path.join(dirPath, '.venv', 'Scripts', 'Activate.ps1'),
            path.join(dirPath, 'venv', 'bin', 'activate'),
            path.join(dirPath, '.venv', 'bin', 'activate')
        ];
        const found = candidates.find(c => fs.existsSync(c));
        if (!found) {
            return { success: false, found: false, error: `No venv found in ${dirPath} (checked venv/ and .venv/).` };
        }
        return { success: true, found: true, activateScript: found };
    });

    ipcMain.handle('activate-venv', async (event, { activateScript }) => {
        if (!activateScript || !fs.existsSync(activateScript)) {
            return { success: false, error: 'Activate script not found.' };
        }
        const apps = { ...DEFAULT_EXTERNAL_APPS, ...loadJson(EXTERNAL_APPS_FILE, {}) };
        const ps7Exe = apps.ps7.exe || tryDefaultPs7Path();
        if (!ps7Exe) {
            return { success: false, error: 'PS7 not configured — needed to launch an activated shell.' };
        }
        try {
            const proc = spawn(ps7Exe, ['-NoExit', '-Command', `. '${activateScript}'`], {
                detached: true,
                stdio: 'ignore'
            });
            proc.unref();
            return { success: true };
        } catch (e) {
            return { success: false, error: e.message };
        }
    });

    // ── Glossary — real fetch against the worker, honest on failure ───────
    ipcMain.handle('get-glossary', async () => {
        const workerUrl = process.env.PHOENIX_WORKER_URL || 'https://packages-worker.phoenix-jwl.workers.dev';
        const auth = process.env.PHOENIX_AUTH || '';
        try {
            const res = await fetch(`${workerUrl}/glossary`, {
                headers: auth ? { 'Authorization': `Bearer ${auth}` } : {}
            });
            if (!res.ok) {
                return {
                    success: false,
                    error: `Worker returned ${res.status} for /glossary — that route may not be deployed yet.`
                };
            }
            const data = await res.json();
            return { success: true, ...data };
        } catch (e) {
            return { success: false, error: e.message };
        }
    });
}

module.exports = { register };
