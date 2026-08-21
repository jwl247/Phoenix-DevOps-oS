// ps7-shell.js
// Embedded PowerShell 7 shell for the dashboard HUD — full, unrestricted
// commands (unlike the gated PHOENIX CLI drawer, which only allows
// help/usys/intake). This is a real shell: you typed it, it runs.
//
// Not a PTY (no node-pty/xterm — no native build dependency). Each command
// is a fresh `pwsh.exe -Command` spawn in a tracked working directory, so
// interactive full-screen programs (vim, top) won't work, but everything
// else — scripts, usys, git, intake — runs exactly as it would in a real
// PS7 window.
//
// Wire into main.js with:
//   require('./ps7-shell').register({ ipcMain, spawn });

const fs = require('fs');
const path = require('path');

function resolvePs7Exe() {
    const candidate = 'C:\\Program Files\\PowerShell\\7\\pwsh.exe';
    if (process.platform === 'win32' && fs.existsSync(candidate)) return candidate;
    return process.platform === 'win32' ? 'pwsh.exe' : 'pwsh';
}

function register({ ipcMain, spawn }) {
    // One tracked cwd per dashboard session — starts wherever the process
    // itself started (matches opening a real PS7 window from Explorer).
    let cwd = process.cwd();

    ipcMain.handle('ps7-shell-get-cwd', async () => ({ cwd }));

    ipcMain.handle('ps7-shell-run', async (event, { command }) => {
        const trimmed = (command || '').trim();
        if (!trimmed) return { success: true, output: '', cwd };

        // `cd`/`Set-Location` needs special handling — each spawn is a
        // fresh process, so a real `cd` inside it wouldn't survive to the
        // next command. Track it here instead, same trick every web-shell
        // that isn't a real PTY has to use.
        const cdMatch = trimmed.match(/^(?:cd|Set-Location|sl)\s+(.+)$/i);
        if (cdMatch) {
            let target = cdMatch[1].trim().replace(/^["']|["']$/g, '');
            const resolved = path.isAbsolute(target) ? target : path.resolve(cwd, target);
            if (!fs.existsSync(resolved) || !fs.statSync(resolved).isDirectory()) {
                return { success: false, error: `Cannot find path '${resolved}' because it does not exist.`, cwd };
            }
            cwd = resolved;
            return { success: true, output: '', cwd };
        }

        return new Promise((resolve) => {
            const ps7Exe = resolvePs7Exe();
            const proc = spawn(ps7Exe, ['-NoProfile', '-NoLogo', '-Command', trimmed], {
                cwd,
                shell: false
            });
            let stdout = '';
            let stderr = '';
            const timeout = setTimeout(() => proc.kill(), 60000);
            proc.stdout.on('data', d => { stdout += d; });
            proc.stderr.on('data', d => { stderr += d; });
            proc.on('error', error => {
                clearTimeout(timeout);
                resolve({ success: false, error: error.message, cwd });
            });
            proc.on('close', code => {
                clearTimeout(timeout);
                resolve({
                    success: code === 0,
                    output: stdout,
                    error: code === 0 ? null : (stderr || `Command exited ${code}`),
                    cwd
                });
            });
        });
    });
}

module.exports = { register };
