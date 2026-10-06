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
    ps7:          { exe: null, args: [] },
    bash:         { exe: null, args: [] },
    githubDesktop:{ exe: null, args: [] },
    // KITT WPF HUD — exe path auto-resolved from repo on first launch.
    // Set via set-external-app-path once a Release build exists; falls back
    // to `dotnet run` against the hud/ project while in development.
    hud:          { exe: null, args: [] }
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

// Same header set as scripts/usys.ps1 Get-UsysWorkerHeaders: PHOENIX_AUTH
// bearer + the usys-cli Cloudflare Access service token (User env vars).
function workerHeaders() {
    const h = { Accept: 'application/json' };
    if (process.env.PHOENIX_AUTH) h.Authorization = `Bearer ${process.env.PHOENIX_AUTH}`;
    if (process.env.CF_ACCESS_CLIENT_ID) h['CF-Access-Client-Id'] = process.env.CF_ACCESS_CLIENT_ID;
    if (process.env.CF_ACCESS_CLIENT_SECRET) h['CF-Access-Client-Secret'] = process.env.CF_ACCESS_CLIENT_SECRET;
    return h;
}

// A real worker response never redirects; a redirect means Cloudflare Access
// bounced us to its login page (missing/invalid service token).
async function workerGet(url) {
    const res = await fetch(url, { headers: workerHeaders(), redirect: 'manual' });
    if (res.type === 'opaqueredirect' || (res.status >= 300 && res.status < 400)) {
        const e = new Error('Cloudflare Access redirected to login — set CF_ACCESS_CLIENT_ID / CF_ACCESS_CLIENT_SECRET and PHOENIX_AUTH.');
        e.accessRedirect = true;
        throw e;
    }
    return res;
}

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
        if (!['ps7', 'bash', 'githubDesktop', 'hud'].includes(key)) {
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
        if (!app || !['ps7', 'bash', 'githubDesktop', 'hud'].includes(key)) {
            return { success: false, error: `Unknown app key: ${key}` };
        }

        // ── HUD: KITT WPF app — exe or dotnet run fallback ───────────────────
        if (key === 'hud') {
            // Prefer a configured Release exe; fall back to `dotnet run` so
            // the button works in development before the first build.
            if (app.exe && fs.existsSync(app.exe)) {
                try {
                    // direct launch — see the `start ""` note under Standard apps
                    const proc = spawn(app.exe, app.args || [], { detached: true, stdio: 'ignore', windowsHide: false });
                    proc.unref();
                    return { success: true };
                } catch (e) {
                    return { success: false, error: e.message };
                }
            }
            // No exe configured — try dotnet run from the repo's hud/ directory.
            const hudDir = path.join(__dirname, '..', 'hud');
            if (!fs.existsSync(hudDir)) {
                return {
                    success: false,
                    error: 'HUD directory not found at ' + hudDir + '. Configure the exe path via the file picker.',
                    needsConfig: true
                };
            }
            try {
                const proc = spawn('dotnet', ['run', '--project', hudDir], {
                    detached: true, stdio: 'ignore', cwd: hudDir, windowsHide: false
                });
                proc.unref();
                return { success: true };
            } catch (e) {
                return { success: false, error: 'dotnet run failed: ' + e.message + ' — configure the HUD exe path instead.', needsConfig: true };
            }
        }

        // ── Standard apps ────────────────────────────────────────────────────
        if (!app.exe || !fs.existsSync(app.exe)) {
            return {
                success: false,
                error: `${key} not configured. Set its path first.`,
                needsConfig: true
            };
        }
        try {
            // For PS7: launch with the user's real profile so usys, MCP server,
            // skills, and all env vars from usys init are available immediately.
            // `-NoExit` keeps the window open after the profile loads.
            // Launched directly, never via `cmd /c start "" <exe>`: Node escapes
            // the empty "" title so cmd misparses the line, and `start` then
            // opened File Explorer instead of PS7 (2026-10-02). A detached
            // process gets its own console window on Windows.
            const args = key === 'ps7' ? ['-NoExit', '-NoLogo'] : (app.args || []);
            const proc = spawn(app.exe, args, { detached: true, stdio: 'ignore', windowsHide: false });
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
        // The active slot IS the working directory — point the live shell +
        // Claude hotline sessions at it so everything follows the work.
        if (index !== null) {
            try { require('./terminal-pty').setWorkingDir(state.slots[index]); } catch (_) {}
        }
        return { success: true, activeIndex: index, previousIndex, dir: index !== null ? state.slots[index] : null };
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
        // Only ever dot-source a real venv activation script (what
        // detect-venv returns) — never an arbitrary renderer-supplied file.
        if (!/^activate(\.ps1)?$/i.test(path.basename(activateScript))) {
            return { success: false, error: 'Not a venv activate script.' };
        }
        const apps = { ...DEFAULT_EXTERNAL_APPS, ...loadJson(EXTERNAL_APPS_FILE, {}) };
        const ps7Exe = apps.ps7.exe || tryDefaultPs7Path();
        if (!ps7Exe) {
            return { success: false, error: 'PS7 not configured — needed to launch an activated shell.' };
        }
        try {
            const proc = spawn(ps7Exe, ['-NoExit', '-Command', `. '${String(activateScript).replace(/'/g, "''")}'`], {
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
    // Every packages-worker route (reads included) sits behind Cloudflare
    // Access + PHOENIX_AUTH since the Gap 1 fix (2026-09-21). Unauthenticated
    // GETs get a 302 to the Access login page, which fetch() would follow to
    // a 200 HTML page — so send the same header set usys.ps1's
    // Get-UsysWorkerHeaders sends, and refuse to follow redirects.
    ipcMain.handle('get-glossary', async (event, { q, category } = {}) => {
        const workerUrl = process.env.PHOENIX_WORKER_URL || 'https://packages-worker.phoenix-jwl.workers.dev';
        const params = new URLSearchParams();
        if (q) params.set('q', q);
        if (category) params.set('category', category);
        const qs = params.toString();
        try {
            const res = await workerGet(`${workerUrl}/glossary${qs ? `?${qs}` : ''}`);
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

    // ── Atlas — one thing + what it really connects to (docs/ATLAS.md) ──
    // /connections/<q>/related first; if that misses, search with ?q= and
    // use the best hit, same order the atlas skill uses.
    ipcMain.handle('get-atlas', async (event, { q } = {}) => {
        const workerUrl = process.env.PHOENIX_WORKER_URL || 'https://packages-worker.phoenix-jwl.workers.dev';
        const term = String(q || '').trim();
        if (!term) return { success: false, error: 'Type what you want to look up.' };
        try {
            let res = await workerGet(`${workerUrl}/connections/${encodeURIComponent(term)}/related`);
            if (res.status === 404) {
                const s = await workerGet(`${workerUrl}/connections?q=${encodeURIComponent(term)}`);
                if (!s.ok) return { success: false, error: `Worker returned ${s.status} for /connections` };
                const hits = (await s.json()).connections || [];
                if (!hits.length) return { success: false, error: `Atlas has nothing called "${term}".` };
                hits.sort((a, b) => a.path.length - b.path.length);
                res = await workerGet(`${workerUrl}/connections/${encodeURIComponent(hits[0].path)}/related`);
                if (res.ok) {
                    const data = await res.json();
                    // the search's other hits become "did you mean" choices
                    const more = hits.slice(1, 7).map(h => ({ hex: h.hex, name: h.name, path: h.path, description: h.description }));
                    return { success: true, ...data, candidates: [...(data.candidates || []), ...more].slice(0, 6) };
                }
            }
            if (!res.ok) return { success: false, error: `Worker returned ${res.status} for /connections` };
            return { success: true, ...(await res.json()) };
        } catch (e) {
            return { success: false, error: e.message };
        }
    });

    ipcMain.handle('get-custody', async (event, { hex, limit } = {}) => {
        const workerUrl = process.env.PHOENIX_WORKER_URL || 'https://packages-worker.phoenix-jwl.workers.dev';
        const params = new URLSearchParams();
        if (hex)   params.set('hex', hex);
        if (limit) params.set('limit', String(limit));
        try {
            const res = await workerGet(`${workerUrl}/custody?${params.toString()}`);
            if (!res.ok) return { success: false, error: `Worker returned ${res.status} for /custody` };
            const data = await res.json();
            return { success: true, ...data };
        } catch (e) {
            return { success: false, error: e.message };
        }
    });

    ipcMain.handle('get-categories', async () => {
        const workerUrl = process.env.PHOENIX_WORKER_URL || 'https://packages-worker.phoenix-jwl.workers.dev';
        try {
            const res = await workerGet(`${workerUrl}/categories`);
            if (!res.ok) {
                return { success: false, error: `Worker returned ${res.status} for /categories.` };
            }
            const data = await res.json();
            return { success: true, ...data };
        } catch (e) {
            return { success: false, error: e.message };
        }
    });
}

module.exports = { register };
