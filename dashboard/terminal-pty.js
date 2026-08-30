// terminal-pty.js
// REAL embedded terminals for the HUD — persistent ConPTY (Windows) / pty
// (Linux) sessions behind xterm.js. Not the old spawn-one-command fake:
// each is one long-lived shell that keeps cwd, env, vars, history for the
// life of the window, launched with the user's full profile so usys / bash /
// git / claude / python all resolve.
//
// Two named sessions:
//   'shell'  — a plain interactive shell
//   'claude' — the same shell, dropped straight into `claude` (the hotline).
//              If claude exits you're left at the shell, not a dead pane.
//
// Both open in the ACTIVE WORKING DIRECTORY (the active folder slot), so the
// shell and the Claude hotline are always sitting where your work is. When
// the active slot changes, live sessions `cd` there automatically.
//
// Wire into main.js:
//   const terminal = require('./terminal-pty');
//   terminal.register({ ipcMain });
//   // on active-slot change:  terminal.setWorkingDir(dirPath)
//
// IPC (scoped to sender webContents id + session name):
//   term-start   {session, cols, rows} -> { started, pid, shell }  (idempotent)
//   term-input   {session, data}
//   term-resize  {session, cols, rows}
//   term-kill    {session}
// Renderer push:
//   term-data    {session, data}   -> raw ANSI, feed to xterm

const os = require('os');
const path = require('path');
const fs = require('fs');

let pty;
try {
    pty = require('@homebridge/node-pty-prebuilt-multiarch');
} catch (e) {
    console.warn('[terminal-pty] node-pty not available:', e.message);
    pty = null;
}

// key = `${webContents.id}:${sessionName}` -> { term, shell, sender }
const sessions = new Map();

const SLOTS_FILE = path.join(os.homedir(), '.phoenix', 'hud-dropdown-slots.json');

function resolveShell() {
    if (process.platform === 'win32') {
        const candidates = [
            'C:\\Program Files\\PowerShell\\7\\pwsh.exe',
            path.join(process.env.LOCALAPPDATA || '', 'Microsoft\\WindowsApps\\pwsh.exe'),
            'powershell.exe'
        ];
        for (const c of candidates) {
            try { if (c === 'powershell.exe' || fs.existsSync(c)) return c; } catch (_) {}
        }
        return 'powershell.exe';
    }
    return process.env.SHELL || '/bin/bash';
}

// The one working directory everything pivots around: active folder slot,
// else PHOENIX_ROOT, else home.
function workingDir() {
    try {
        const state = JSON.parse(fs.readFileSync(SLOTS_FILE, 'utf8'));
        const p = state && state.activeIndex != null ? state.slots[state.activeIndex] : null;
        if (p && fs.existsSync(p)) return p;
    } catch (_) {}
    const root = process.env.PHOENIX_ROOT;
    if (root) { try { if (fs.existsSync(root)) return root; } catch (_) {} }
    return os.homedir();
}

function quoteForShell(p) {
    return process.platform === 'win32'
        ? `'${String(p).replace(/'/g, "''")}'`
        : `'${String(p).replace(/'/g, "'\\''")}'`;
}

function cleanEnv() {
    const env = { ...process.env, TERM: 'xterm-256color' };
    // If the dashboard itself was launched from inside a Claude Code session,
    // these leak in and make the CLAUDE hotline think it's a nested child
    // (transcript saving off, odd markers). Strip them so the pane's `claude`
    // is a clean top-level session.
    for (const k of Object.keys(env)) {
        if (k.startsWith('CLAUDE_CODE_') || k === 'CLAUDECODE') delete env[k];
    }
    return env;
}

function spawnSession(sessionName, cols, rows) {
    const shell = resolveShell();
    const args = process.platform === 'win32' ? ['-NoLogo'] : [];
    const term = pty.spawn(shell, args, {
        name: 'xterm-256color',
        cols: cols || 120,
        rows: rows || 30,
        cwd: workingDir(),
        env: cleanEnv()
    });
    // The claude hotline: run claude straight away in the working dir. If it
    // exits, the shell stays.
    if (sessionName === 'claude') {
        const cli = process.platform === 'win32' ? 'claude.cmd' : 'claude';
        setTimeout(() => { try { term.write(`${cli}\r`); } catch (_) {} }, 300);
    }
    return { term, shell };
}

function register({ ipcMain }) {
    ipcMain.handle('term-start', async (event, { session = 'shell', cols, rows } = {}) => {
        if (!pty) {
            return { started: false, error: 'node-pty native module failed to load — terminal unavailable.' };
        }
        const key = `${event.sender.id}:${session}`;
        const existing = sessions.get(key);
        if (existing) {
            return { started: true, pid: existing.term.pid, shell: existing.shell, reused: true };
        }

        let s;
        try {
            s = spawnSession(session, cols, rows);
        } catch (e) {
            return { started: false, error: `Could not start ${session}: ${e.message}` };
        }
        s.sender = event.sender;

        s.term.onData((data) => {
            if (!event.sender.isDestroyed()) event.sender.send('term-data', { session, data });
        });
        s.term.onExit(({ exitCode }) => {
            if (!event.sender.isDestroyed()) {
                event.sender.send('term-data', { session, data: `\r\n\x1b[90m[${session} exited ${exitCode}]\x1b[0m\r\n` });
            }
            sessions.delete(key);
        });

        sessions.set(key, s);
        event.sender.once('destroyed', () => {
            for (const [k, sess] of sessions) {
                if (k.startsWith(`${event.sender.id}:`)) {
                    try { sess.term.kill(); } catch (_) {}
                    sessions.delete(k);
                }
            }
        });

        return { started: true, pid: s.term.pid, shell: s.shell };
    });

    ipcMain.on('term-input', (event, { session = 'shell', data } = {}) => {
        const s = sessions.get(`${event.sender.id}:${session}`);
        if (s && typeof data === 'string') { try { s.term.write(data); } catch (_) {} }
    });

    ipcMain.on('term-resize', (event, { session = 'shell', cols, rows } = {}) => {
        const s = sessions.get(`${event.sender.id}:${session}`);
        if (s && cols > 0 && rows > 0) { try { s.term.resize(cols, rows); } catch (_) {} }
    });

    ipcMain.handle('term-kill', async (event, { session = 'shell' } = {}) => {
        const s = sessions.get(`${event.sender.id}:${session}`);
        if (s) { try { s.term.kill(); } catch (_) {} sessions.delete(`${event.sender.id}:${session}`); }
        return { ok: true };
    });

    ipcMain.handle('term-working-dir', async () => ({ dir: workingDir() }));
}

// Called by main.js when the active folder slot changes: cd every live
// session to the new working directory so the shell and the Claude hotline
// follow the work.
function setWorkingDir(dir) {
    if (!dir || !fs.existsSync(dir)) return;
    for (const s of sessions.values()) {
        try { s.term.write(`cd ${quoteForShell(dir)}\r`); } catch (_) {}
    }
}

module.exports = { register, setWorkingDir, workingDir };
