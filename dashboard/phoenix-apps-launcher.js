// phoenix-apps-launcher.js
// The dashboard starts the other two Phoenix front ends:
//   CONSOLE  portal/server.py on :8470 — machines, links, services, hands.
//            Started through its own logon task (PhoenixPortal) when that
//            exists, so it runs exactly as it does at boot (as the user, with
//            vault access); otherwise pythonw directly. Opened in a locked-down
//            dashboard window: no Node, no preload, nothing but :8470.
//   HUD      hud/bin/<Release|Debug>/net9.0-windows/Hud.exe (WPF, Windows only).
//            The newest build wins; a build older than the HUD's own source is
//            reported, because it would run yesterday's code.
//
// Wire into main.js:
//   require('./phoenix-apps-launcher').register({ ipcMain, BrowserWindow, shell, phoenixRoot: resolvePhoenixRoot() });

const fs = require('fs');
const path = require('path');
const http = require('http');
const { execFile, spawn } = require('child_process');

const CONSOLE_PORT = Number(process.env.PHOENIX_CONSOLE_PORT) || 8470;
const CONSOLE_URL = `http://127.0.0.1:${CONSOLE_PORT}/`;
const IS_WIN = process.platform === 'win32';

let consoleWin = null;

// ── Console ──────────────────────────────────────────────────────────────
function consoleUp(timeoutMs = 1500) {
    return new Promise((resolve) => {
        // /api/state is what the page itself loads; a 200 means the server is
        // up AND answering for this Host (it refuses unknown Host headers).
        const req = http.get({ host: '127.0.0.1', port: CONSOLE_PORT, path: '/api/state', timeout: timeoutMs,
                               headers: { Host: '127.0.0.1' } }, (res) => {
            res.resume();
            resolve(res.statusCode === 200);
        });
        req.on('timeout', () => { req.destroy(); resolve(false); });
        req.on('error', () => resolve(false));
    });
}

function run(file, args, opts = {}) {
    return new Promise((resolve) => {
        execFile(file, args, { windowsHide: true, timeout: 15000, ...opts }, (err, stdout, stderr) =>
            resolve({ ok: !err, code: err ? (err.code ?? 1) : 0, stdout: String(stdout || ''), stderr: String(stderr || '') }));
    });
}

async function findPythonw() {
    if (process.env.PHOENIX_PYTHONW && fs.existsSync(process.env.PHOENIX_PYTHONW)) return process.env.PHOENIX_PYTHONW;
    if (IS_WIN) {
        const w = await run('where.exe', ['pythonw']);
        // The WindowsApps entries are Store stubs, not Python.
        const hit = w.stdout.split(/\r?\n/).map((s) => s.trim()).find((p) => p && !/\\WindowsApps\\/i.test(p));
        if (hit) return hit;
        const py = await run('py', ['-3', '-c', 'import sys,os;print(os.path.join(os.path.dirname(sys.executable),"pythonw.exe"))']);
        const cand = py.stdout.trim();
        if (py.ok && cand && fs.existsSync(cand)) return cand;
        return null;
    }
    for (const c of ['/usr/bin/python3', '/usr/local/bin/python3']) if (fs.existsSync(c)) return c;
    return null;
}

async function startConsole(phoenixRoot) {
    const server = path.join(phoenixRoot, 'portal', 'server.py');
    if (!fs.existsSync(server)) return { ok: false, error: `Console not found: ${server}` };
    if (IS_WIN) {
        const t = await run('schtasks.exe', ['/Run', '/TN', 'PhoenixPortal']);
        if (t.ok) return { ok: true, via: 'task PhoenixPortal' };
    }
    const py = await findPythonw();
    if (!py) return { ok: false, error: 'No Python found to start the Console (set PHOENIX_PYTHONW to pythonw.exe).' };
    const child = spawn(py, [server], { cwd: path.dirname(server), detached: true, stdio: 'ignore', windowsHide: true });
    child.unref();
    return { ok: true, via: path.basename(py) };
}

async function waitUp(ms) {
    const end = Date.now() + ms;
    while (Date.now() < end) {
        if (await consoleUp(1000)) return true;
        await new Promise((r) => setTimeout(r, 500));
    }
    return false;
}

function openConsoleWindow(BrowserWindow, shell) {
    if (consoleWin && !consoleWin.isDestroyed()) {
        if (consoleWin.isMinimized()) consoleWin.restore();
        consoleWin.focus();
        return;
    }
    consoleWin = new BrowserWindow({
        width: 1400, height: 900, title: 'Phoenix Console', backgroundColor: '#14171a',
        webPreferences: { nodeIntegration: false, contextIsolation: true, sandbox: true },   // a web page, nothing more
    });
    const wc = consoleWin.webContents;
    const sameOrigin = (u) => { try { return new URL(u).origin === new URL(CONSOLE_URL).origin; } catch { return false; } };
    wc.setWindowOpenHandler(({ url }) => {
        if (!sameOrigin(url) && /^https?:/i.test(url)) shell.openExternal(url);
        return { action: 'deny' };
    });
    wc.on('will-navigate', (e, url) => {
        if (!sameOrigin(url)) { e.preventDefault(); if (/^https?:/i.test(url)) shell.openExternal(url); }
    });
    consoleWin.on('closed', () => { consoleWin = null; });
    consoleWin.loadURL(CONSOLE_URL);
}

// ── HUD ──────────────────────────────────────────────────────────────────
function newestMtime(dir, exts, depth = 0) {
    let newest = 0;
    let entries = [];
    try { entries = fs.readdirSync(dir, { withFileTypes: true }); } catch { return 0; }
    for (const e of entries) {
        if (e.isDirectory()) {
            if (['bin', 'obj', '.vs', 'node_modules'].includes(e.name) || depth > 3) continue;
            newest = Math.max(newest, newestMtime(path.join(dir, e.name), exts, depth + 1));
        } else if (exts.includes(path.extname(e.name).toLowerCase())) {
            try { newest = Math.max(newest, fs.statSync(path.join(dir, e.name)).mtimeMs); } catch { /* gone */ }
        }
    }
    return newest;
}

function findHud(phoenixRoot) {
    const hudDir = path.join(phoenixRoot, 'hud');
    const builds = ['Release', 'Debug']
        .map((cfg) => path.join(hudDir, 'bin', cfg, 'net9.0-windows', 'Hud.exe'))
        .filter((p) => fs.existsSync(p))
        .map((p) => {
            const dll = path.join(path.dirname(p), 'Hud.dll');           // the code lives in the dll; the exe is a stub
            return { exe: p, mtime: fs.statSync(fs.existsSync(dll) ? dll : p).mtimeMs };
        })
        .sort((a, b) => b.mtime - a.mtime);
    if (!builds.length) return { hudDir, exe: null };
    const src = newestMtime(hudDir, ['.cs', '.xaml', '.csproj']);
    return { hudDir, exe: builds[0].exe, stale: src > builds[0].mtime + 1000 };
}

async function hudRunning() {
    if (!IS_WIN) return false;
    const r = await run('tasklist.exe', ['/FI', 'IMAGENAME eq Hud.exe', '/FO', 'CSV', '/NH']);
    return /"Hud\.exe"/i.test(r.stdout);
}

// ── IPC ──────────────────────────────────────────────────────────────────
function register({ ipcMain, BrowserWindow, shell, phoenixRoot }) {
    ipcMain.handle('launch-console', async () => {
        try {
            let started = null;
            if (!(await consoleUp())) {
                const s = await startConsole(phoenixRoot);
                if (!s.ok) return { success: false, error: s.error };
                started = s.via;
                if (!(await waitUp(15000))) {
                    return { success: false, error: `Started the Console (${s.via}) but it is not answering on :${CONSOLE_PORT} after 15 s. Check the PhoenixPortal task, or run: python portal\\server.py` };
                }
            }
            openConsoleWindow(BrowserWindow, shell);
            return { success: true, url: CONSOLE_URL, started };
        } catch (e) {
            return { success: false, error: e.message };
        }
    });

    ipcMain.handle('launch-hud', async () => {
        try {
            if (!IS_WIN) return { success: false, error: 'The HUD is a Windows (WPF) app.' };
            if (await hudRunning()) return { success: true, alreadyRunning: true };
            const h = findHud(phoenixRoot);
            if (!h.exe) return { success: false, error: `HUD not built. In PS7: dotnet build "${h.hudDir}" -c Release` };
            const child = spawn(h.exe, [], { cwd: path.dirname(h.exe), detached: true, stdio: 'ignore' });
            child.unref();
            return { success: true, exe: h.exe, stale: !!h.stale,
                     warning: h.stale ? `The HUD's source is newer than this build. To run the current code: dotnet build "${h.hudDir}" -c Release` : null };
        } catch (e) {
            return { success: false, error: e.message };
        }
    });

    ipcMain.handle('get-phoenix-apps-status', async () => {
        const h = findHud(phoenixRoot);
        return { console: { up: await consoleUp(), url: CONSOLE_URL },
                 hud: { running: await hudRunning(), built: !!h.exe, stale: !!h.stale, exe: h.exe } };
    });
}

module.exports = { register, consoleUp, findHud, CONSOLE_URL };
