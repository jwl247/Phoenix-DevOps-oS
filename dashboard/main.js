// Phoenix Dashboard - Electron Main Process
// Handles window creation, IPC communication, and Phoenix command execution

const { app, BrowserWindow, ipcMain, dialog, shell, desktopCapturer } = require('electron');
const { exec, spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const os = require('os');
const http = require('http');

const OLLAMA_EXE = path.join(os.homedir(), 'AppData', 'Local', 'Programs', 'Ollama', 'ollama.exe');
let _resolvedOllamaModel = null;

let mainWindow;

// Create the main application window
function createWindow() {
    mainWindow = new BrowserWindow({
        width: 1920,
        height: 1080,
        minWidth: 1280,
        minHeight: 720,
        backgroundColor: '#0a0e1a',
        title: 'Phoenix DevOps OS - Command Center',
        icon: path.join(__dirname, 'assets', 'icon.png'),
        webPreferences: {
            preload: path.join(__dirname, 'preload.js'),
            nodeIntegration: false,
            contextIsolation: true,
            sandbox: true
        },
        frame: true,
        autoHideMenuBar: true
    });

    // Load the dashboard
    mainWindow.loadFile('index.html');
    mainWindow.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
    mainWindow.webContents.on('will-navigate', (event, targetUrl) => {
        if (targetUrl !== mainWindow.webContents.getURL()) event.preventDefault();
    });

    // Open DevTools in development (comment out for production)
    // mainWindow.webContents.openDevTools();

    mainWindow.on('closed', () => {
        mainWindow = null;
    });

    // Set up window title
    mainWindow.on('page-title-updated', (event) => {
        event.preventDefault();
    });
}

// App lifecycle
app.whenReady().then(async () => {
    // Only auto-start Ollama (spawning a whole extra server process) when
    // it's actually the configured provider. Doing this unconditionally
    // meant every launch — even in dedicated 'claude'/'subscription' mode,
    // where Ollama is never touched by the chat routing — still forced an
    // ollama.exe process into existence nobody asked for. loadSavedAuth()
    // already ran (top-level, before whenReady fires), so PHOENIX_AI_PROVIDER
    // reflects the real saved choice here.
    const bootProvider = (process.env.PHOENIX_AI_PROVIDER || 'helpdesk').toLowerCase();
    if (bootProvider === 'helpdesk' || bootProvider === 'ollama') {
        ensureOllamaRunning().then(r => {
            if (r.online) console.log(`[Ollama] online at ${r.url}${r.started ? ' (auto-started)' : ''}`);
            else console.warn(`[Ollama] offline: ${r.reason || 'unknown'}`);
        });
    } else {
        console.log(`[Ollama] skipped auto-start — provider is '${bootProvider}', not helpdesk/ollama`);
    }
    createWindow();

    app.on('activate', () => {
        if (BrowserWindow.getAllWindows().length === 0) {
            createWindow();
        }
    });
});

app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') {
        app.quit();
    }
});

// ============================================================================
// IPC HANDLERS - Communication between renderer and main process
// ============================================================================

// Run a file from the RUNIT drawer (.ps1, .sh, .py, .exe, etc.)
ipcMain.handle('run-file', async (event, { filePath, args }) => {
    if (!filePath || !fs.existsSync(filePath)) {
        return { success: false, error: `File not found: ${filePath}` };
    }
    const actualPath = fs.realpathSync(filePath);
    const executionRoots = [resolvePhoenixRoot(), process.env.CLONEPOOL_DIR]
        .filter(root => root && fs.existsSync(root))
        .map(root => fs.realpathSync(root));
    if (!executionRoots.some(root => {
        const relative = path.relative(root, actualPath);
        return relative && !relative.startsWith('..') && !path.isAbsolute(relative);
    })) {
        return { success: false, error: 'Only files inside PHOENIX_ROOT or CLONEPOOL_DIR can be run.' };
    }
    const ext = path.extname(filePath).toLowerCase();
    const argStr = (args || '').trim();
    const cwd = path.dirname(filePath);
    let shell, shellArgs;
    if (ext === '.ps1') {
        shell = 'pwsh.exe';
        shellArgs = ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', filePath];
        if (argStr) shellArgs.push(...argStr.split(/\s+/));
    } else if (ext === '.sh') {
        shell = process.platform === 'win32' ? 'bash' : 'bash';
        shellArgs = [filePath];
        if (argStr) shellArgs.push(...argStr.split(/\s+/));
    } else if (ext === '.py') {
        shell = 'python';
        shellArgs = [filePath];
        if (argStr) shellArgs.push(...argStr.split(/\s+/));
    } else if (['.js', '.mjs', '.cjs'].includes(ext)) {
        shell = 'node';
        shellArgs = [filePath];
        if (argStr) shellArgs.push(...argStr.split(/\s+/));
    } else if (process.platform === 'win32' && ['.exe', '.com'].includes(ext)) {
        shell = filePath;
        shellArgs = argStr ? argStr.split(/\s+/) : [];
    } else if (process.platform === 'win32' && ['.cmd', '.bat'].includes(ext)) {
        return { success: false, error: 'Batch files are not supported by the secure runner; use a PowerShell script instead.' };
    } else {
        return { success: false, error: `Unsupported file type: ${ext || '(none)'}` };
    }

    return new Promise(resolve => {
        const proc = spawn(shell, shellArgs, { cwd, shell: false });
        let stdout = '';
        let stderr = '';
        proc.stdout.on('data', d => { stdout += d; });
        proc.stderr.on('data', d => { stderr += d; });
        proc.on('error', err => resolve({ success: false, error: err.message, command: `${shell} ${shellArgs.join(' ')}` }));
        proc.on('close', code => {
            resolve({
                success: code === 0,
                output: stdout,
                stderr,
                exitCode: code,
                error: code !== 0 ? `exit ${code}` : null,
                command: `${shell} ${shellArgs.join(' ')}`
            });
        });
    });
});

// Sector folder paths for control panel "open" action
ipcMain.handle('get-sector-paths', async () => {
    const root = process.env.PHOENIX_ROOT || path.join(os.homedir(), 'Phoenix', 'Phoenix-DevOps-oS');
    const sectors = {
        '1': path.join(root, 'sector1'),
        '2': path.join(root, 'sector2'),
        '3': path.join(root, 'sector3'),
        '4': path.join(root, 'SECTOR4'),
        helix: path.join(root, 'phoenix-core')
    };
    return Object.fromEntries(
        Object.entries(sectors).map(([k, p]) => [k, fs.existsSync(p) ? p : null])
    );
});

function resolvePhoenixRoot() {
    return process.env.PHOENIX_ROOT || path.join(os.homedir(), 'Phoenix', 'Phoenix-DevOps-oS');
}

function resolvePhoenixCommand(command) {
    const root = resolvePhoenixRoot();
    const trimmed = (command || '').trim();
    if (!trimmed) return trimmed;

    if (trimmed === 'help') {
        const manual = path.join(__dirname, 'manual', 'PHOENIX_MANUAL.md');
        if (fs.existsSync(manual)) {
            return process.platform === 'win32'
                ? `Get-Content -Path '${manual.replace(/'/g, "''")}' -TotalCount 50`
                : `head -50 '${manual.replace(/'/g, "'\\''")}'`;
        }
        return process.platform === 'win32'
            ? `& '${path.join(root, 'scripts', 'usys.ps1').replace(/'/g, "''")}'`
            : `usys help 2>/dev/null || echo 'Phoenix help: usys status | intake status | help'`;
    }

    if (/^intake\b/i.test(trimmed)) {
        const args = trimmed.replace(/^intake\s*/i, '');
        const intakePs1 = path.join(root, 'scripts', 'intake.ps1');
        if (process.platform === 'win32' && fs.existsSync(intakePs1)) {
            return `& '${intakePs1.replace(/'/g, "''")}' ${args}`;
        }
        const intakeSh = path.join(root, 'SECTOR4', 'intake', 'intake.sh');
        if (fs.existsSync(intakeSh)) {
            return `bash '${intakeSh.replace(/'/g, "'\\''")}' ${args}`;
        }
    }

    if (/^usys\b/i.test(trimmed)) {
        const args = trimmed.replace(/^usys\s*/i, '');
        const usysPs1 = path.join(root, 'scripts', 'usys.ps1');
        if (process.platform === 'win32' && fs.existsSync(usysPs1)) {
            return `& '${usysPs1.replace(/'/g, "''")}' ${args}`;
        }
        return trimmed;
    }

    return trimmed;
}

// Open a folder in the OS file manager
ipcMain.handle('open-path', async (event, targetPath) => {
    if (!targetPath || !fs.existsSync(targetPath)) {
        return { success: false, error: `Path not found: ${targetPath}` };
    }
    const err = await shell.openPath(targetPath);
    return err ? { success: false, error: err } : { success: true, path: targetPath };
});

function isAllowedPhoenixCommand(command) {
    if (typeof command !== 'string' || !command.trim()) return false;
    if (/[\r\n;&|`$<>()[\]{}]/.test(command)) return false;
    return command.trim() === 'help' || /^(usys|intake)(?:\s+[A-Za-z0-9_./:\\-]+)*$/i.test(command.trim());
}

// Execute only the dashboard's structured Phoenix commands. Never accept shell
// syntax from the renderer, even though this is a local desktop application.
ipcMain.handle('execute-command', async (event, command) => {
    return new Promise((resolve) => {
        if (!isAllowedPhoenixCommand(command)) {
            resolve({ success: false, error: 'Only help, usys, and intake commands with plain arguments are allowed.' });
            return;
        }
        const resolved = resolvePhoenixCommand(command);
        console.log(`Executing: ${resolved}`);

        // Determine shell based on platform
        const shellCmd = process.platform === 'win32' ? 'pwsh.exe' : 'bash';
        const shellArgs = process.platform === 'win32'
            ? ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', resolved]
            : ['-c', resolved];

        const proc = spawn(shellCmd, shellArgs, {
            cwd: resolvePhoenixRoot(),
            shell: false
        });
        let stdout = '';
        let stderr = '';
        const timeout = setTimeout(() => proc.kill(), 30000);
        proc.stdout.on('data', data => { stdout += data; });
        proc.stderr.on('data', data => { stderr += data; });
        proc.on('error', error => {
            clearTimeout(timeout);
            resolve({ success: false, error: error.message, stderr, stdout });
        });
        proc.on('close', code => {
            clearTimeout(timeout);
            resolve({ success: code === 0, output: stdout, stderr, error: code === 0 ? null : `Command exited ${code}` });
        });
    });
});

// Get system information
ipcMain.handle('get-system-info', async () => {
    return {
        platform: process.platform,
        arch: process.arch,
        hostname: os.hostname(),
        homedir: os.homedir(),
        username: os.userInfo().username,
        cpus: os.cpus().length,
        totalMemory: os.totalmem(),
        freeMemory: os.freemem(),
        uptime: os.uptime(),
        phoenixRoot: process.env.PHOENIX_ROOT || 'Not set',
        clonepoolDir: process.env.CLONEPOOL_DIR || 'Not set'
    };
});

// Get environment variables
ipcMain.handle('get-env-vars', async () => {
    return {
        PHOENIX_ROOT: process.env.PHOENIX_ROOT || null,
        PHOENIX_AUTH: process.env.PHOENIX_AUTH ? '***SET***' : null,
        PHOENIX_WORKER_URL: process.env.PHOENIX_WORKER_URL || null,
        CLONEPOOL_DIR: process.env.CLONEPOOL_DIR || null,
        PHOENIX_INTAKE: process.env.PHOENIX_INTAKE || null,
        PHOENIX_INTAKE_SECTOR4: process.env.PHOENIX_INTAKE_SECTOR4 || null
    };
});

// Read file contents
ipcMain.handle('read-file', async (event, filePath) => {
    try {
        const content = fs.readFileSync(filePath, 'utf8');
        return { success: true, content };
    } catch (error) {
        return { success: false, error: error.message };
    }
});

// Write file contents
ipcMain.handle('write-file', async (event, filePath, content) => {
    try {
        fs.writeFileSync(filePath, content, 'utf8');
        return { success: true };
    } catch (error) {
        return { success: false, error: error.message };
    }
});

// List directory contents
ipcMain.handle('list-directory', async (event, dirPath) => {
    try {
        const items = fs.readdirSync(dirPath, { withFileTypes: true });
        const result = items.map(item => ({
            name: item.name,
            isDirectory: item.isDirectory(),
            isFile: item.isFile(),
            path: path.join(dirPath, item.name)
        }));
        return { success: true, items: result };
    } catch (error) {
        return { success: false, error: error.message };
    }
});

// Get file stats
ipcMain.handle('get-file-stats', async (event, filePath) => {
    try {
        const stats = fs.statSync(filePath);
        return {
            success: true,
            stats: {
                size: stats.size,
                created: stats.birthtime,
                modified: stats.mtime,
                accessed: stats.atime,
                isDirectory: stats.isDirectory(),
                isFile: stats.isFile()
            }
        };
    } catch (error) {
        return { success: false, error: error.message };
    }
});

// Open file dialog
ipcMain.handle('open-file-dialog', async (event, options) => {
    const result = await dialog.showOpenDialog(mainWindow, options);
    return result;
});

// Save file dialog
ipcMain.handle('save-file-dialog', async (event, options) => {
    const result = await dialog.showSaveDialog(mainWindow, options);
    return result;
});

// Get sector file counts
ipcMain.handle('get-sector-counts', async () => {
    const phoenixRoot = process.env.PHOENIX_ROOT || path.join(os.homedir(), 'Phoenix', 'Phoenix-DevOps-oS');
    const sectors = ['sector1', 'sector2', 'sector3', 'SECTOR4'];
    const counts = {};

    for (const sector of sectors) {
        const sectorPath = path.join(phoenixRoot, sector);
        try {
            if (fs.existsSync(sectorPath)) {
                counts[sector] = countFiles(sectorPath);
            } else {
                counts[sector] = 0;
            }
        } catch (error) {
            counts[sector] = 0;
        }
    }

    return counts;
});

// User home directories (Documents, Desktop, etc.)
ipcMain.handle('get-user-dirs', async () => {
    const home = os.homedir();
    const isWin = process.platform === 'win32';
    const candidates = {
        home,
        documents: path.join(home, 'Documents'),
        desktop:   path.join(home, 'Desktop'),
        pictures:  path.join(home, 'Pictures'),
        music:     path.join(home, 'Music'),
        downloads: path.join(home, 'Downloads'),
        phoenix:   process.env.PHOENIX_ROOT || path.join(home, 'Phoenix', 'Phoenix-DevOps-oS'),
    };
    if (!isWin) {
        Object.assign(candidates, {
            root: '/',
            bin: '/bin', sbin: '/sbin', boot: '/boot', dev: '/dev',
            opt: '/opt', etc: '/etc', usr: '/usr', mnt: '/mnt',
            home_root: '/home', var: '/var', tmp: '/tmp', srv: '/srv', media: '/media'
        });
    } else {
        const sysDrive = (process.env.SystemDrive || 'C:').replace(/\\$/, '');
        const root = sysDrive.endsWith(':') ? `${sysDrive}\\` : `${sysDrive}:\\`;
        Object.assign(candidates, {
            root,
            users: path.join(root, 'Users'),
            program_files: path.join(root, 'Program Files'),
            program_files_x86: path.join(root, 'Program Files (x86)'),
            windows: path.join(root, 'Windows')
        });
    }
    return Object.fromEntries(
        Object.entries(candidates).filter(([, p]) => { try { return fs.existsSync(p); } catch { return false; } })
    );
});

// Agnostic root tree — real top-level directories on this machine
ipcMain.handle('get-root-tree', async () => {
    const entries = [];
    const SKIP = new Set(['.Trash', '.Trash-1000', 'System Volume Information', '$Recycle.Bin', 'Recovery']);

    if (process.platform === 'win32') {
        for (let i = 65; i <= 90; i++) {
            const letter = String.fromCharCode(i);
            const drivePath = `${letter}:\\`;
            try {
                fs.accessSync(drivePath);
                entries.push({ label: `${letter}:`, path: drivePath, group: 'drive' });
            } catch (_) {}
        }
        const systemDrive = (process.env.SystemDrive || 'C:').replace(/\\$/, '');
        const root = systemDrive.endsWith(':') ? `${systemDrive}\\` : `${systemDrive}:\\`;
        try {
            fs.readdirSync(root, { withFileTypes: true })
                .filter(e => e.isDirectory() && !SKIP.has(e.name) && !e.name.startsWith('$'))
                .sort((a, b) => a.name.localeCompare(b.name))
                .forEach(e => {
                    entries.push({
                        label: e.name,
                        path: path.join(root, e.name),
                        group: 'root'
                    });
                });
        } catch (_) {}
        // WSL mount if present
        const wslRoot = '\\\\wsl$\\';
        try {
            fs.accessSync(wslRoot);
            entries.push({ label: 'wsl$', path: wslRoot, group: 'wsl' });
        } catch (_) {}
    } else {
        try {
            fs.readdirSync('/', { withFileTypes: true })
                .filter(e => e.isDirectory() && !e.name.startsWith('.'))
                .sort((a, b) => a.name.localeCompare(b.name))
                .forEach(e => {
                    entries.push({
                        label: `/${e.name}`,
                        path: `/${e.name}`,
                        group: 'root'
                    });
                });
        } catch (_) {}
    }

    const phoenixRoot = process.env.PHOENIX_ROOT || path.join(os.homedir(), 'Phoenix', 'Phoenix-DevOps-oS');
    if (fs.existsSync(phoenixRoot)) {
        entries.unshift({ label: 'PHOENIX', path: phoenixRoot, group: 'phoenix' });
    }

    return entries;
});

// Available drives / mount points
ipcMain.handle('get-drives', async () => {
    if (process.platform === 'win32') {
        const drives = [];
        for (let i = 67; i <= 90; i++) {
            const letter = String.fromCharCode(i);
            const p = letter + ':\\';
            try { fs.accessSync(p); drives.push({ name: letter + ':', path: p }); } catch {}
        }
        return drives;
    }
    const mounts = [];
    for (const base of ['/mnt', '/media']) {
        try {
            fs.readdirSync(base, { withFileTypes: true })
                .filter(i => i.isDirectory())
                .forEach(i => mounts.push({ name: i.name, path: path.join(base, i.name) }));
        } catch {}
    }
    return mounts;
});

// Helper function to count files recursively
function countFiles(dir) {
    let count = 0;
    try {
        const items = fs.readdirSync(dir, { withFileTypes: true });
        for (const item of items) {
            if (item.isFile()) {
                count++;
            } else if (item.isDirectory()) {
                count += countFiles(path.join(dir, item.name));
            }
        }
    } catch (error) {
        // Ignore permission errors
    }
    return count;
}

// Get clonepool information
ipcMain.handle('get-clonepool-info', async () => {
    const clonepoolDir = process.env.CLONEPOOL_DIR || path.join(os.homedir(), 'Phoenix', 'clonepool');
    
    try {
        if (!fs.existsSync(clonepoolDir)) {
            return {
                totalFiles: 0,
                suites: 0,
                totalSize: 0,
                lastModified: null
            };
        }

        let totalFiles = 0;
        let suites = 0;
        let totalSize = 0;
        let lastModified = null;

        const items = fs.readdirSync(clonepoolDir, { withFileTypes: true });
        
        for (const item of items) {
            const itemPath = path.join(clonepoolDir, item.name);
            
            if (item.isDirectory()) {
                // Check if it's a suite
                const manifestPath = path.join(itemPath, '.suite.json');
                if (fs.existsSync(manifestPath)) {
                    suites++;
                }
                
                // Count files in directory
                totalFiles += countFiles(itemPath);
                totalSize += getDirectorySize(itemPath);
            } else if (item.isFile()) {
                totalFiles++;
                const stats = fs.statSync(itemPath);
                totalSize += stats.size;
                
                if (!lastModified || stats.mtime > lastModified) {
                    lastModified = stats.mtime;
                }
            }
        }

        return {
            totalFiles,
            suites,
            totalSize,
            lastModified: lastModified ? lastModified.toISOString() : null
        };
    } catch (error) {
        console.error('Error getting clonepool info:', error);
        return {
            totalFiles: 0,
            suites: 0,
            totalSize: 0,
            lastModified: null
        };
    }
});

// Helper function to get directory size
function getDirectorySize(dir) {
    let size = 0;
    try {
        const items = fs.readdirSync(dir, { withFileTypes: true });
        for (const item of items) {
            const itemPath = path.join(dir, item.name);
            if (item.isFile()) {
                const stats = fs.statSync(itemPath);
                size += stats.size;
            } else if (item.isDirectory()) {
                size += getDirectorySize(itemPath);
            }
        }
    } catch (error) {
        // Ignore permission errors
    }
    return size;
}

// Get real Phoenix stats from the worker (glossary + custody counts from D1, R2 object count)
ipcMain.handle('get-phoenix-stats', async () => {
    const workerUrl = process.env.PHOENIX_WORKER_URL || 'https://packages-worker.phoenix-jwl.workers.dev';
    const auth = process.env.PHOENIX_AUTH || '';
    try {
        const res = await fetch(`${workerUrl}/stats`, {
            headers: auth ? { 'Authorization': `Bearer ${auth}` } : {}
        });
        if (!res.ok) return { success: false, error: `Worker returned ${res.status}` };
        const data = await res.json();
        return { success: true, ...data };
    } catch (e) {
        return { success: false, error: e.message };
    }
});

// Get real OS metrics (RAM, CPU load)
ipcMain.handle('get-os-metrics', async () => {
    const total = os.totalmem();
    const free  = os.freemem();
    const used  = total - free;
    const memPct = Math.round((used / total) * 100);

    // CPU: two 100ms samples to get actual usage %
    function cpuTimes() {
        return os.cpus().map(c => ({ idle: c.times.idle, total: Object.values(c.times).reduce((a, b) => a + b, 0) }));
    }
    const t1 = cpuTimes();
    await new Promise(r => setTimeout(r, 100));
    const t2 = cpuTimes();
    let idleDelta = 0, totalDelta = 0;
    t1.forEach((c, i) => {
        idleDelta  += t2[i].idle  - c.idle;
        totalDelta += t2[i].total - c.total;
    });
    const cpuPct = totalDelta > 0 ? Math.round((1 - idleDelta / totalDelta) * 100) : 0;

    // Disk: check PHOENIX_CACHE or home directory
    let diskPct = 0;
    try {
        const checkPath = process.env.PHOENIX_CACHE || os.homedir();
        const stats = fs.statfsSync(checkPath);
        if (stats && stats.blocks > 0) {
            diskPct = Math.round(((stats.blocks - stats.bfree) / stats.blocks) * 100);
        }
    } catch (_) {}

    return {
        cpu: cpuPct,
        memory: memPct,
        memoryUsed: Math.round(used / 1024 / 1024),
        memoryTotal: Math.round(total / 1024 / 1024),
        disk: diskPct,
        uptime: Math.round(os.uptime())
    };
});

// ── Pagefile management (sector4/paging_windows.py's WMI approach, exposed
//    to the dashboard so pagefile placement lives in Phoenix's own UI
//    instead of a separate standalone HTTP server) ─────────────────────────
function runPowerShell(script, timeoutMs = 30000) {
    return new Promise((resolve) => {
        const proc = spawn('pwsh.exe', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', script], { shell: false });
        let stdout = '', stderr = '';
        const timeout = setTimeout(() => proc.kill(), timeoutMs);
        proc.stdout.on('data', d => { stdout += d; });
        proc.stderr.on('data', d => { stderr += d; });
        proc.on('error', error => { clearTimeout(timeout); resolve({ success: false, error: error.message, stdout, stderr }); });
        proc.on('close', code => { clearTimeout(timeout); resolve({ success: code === 0, output: stdout.trim(), stderr: stderr.trim(), error: code === 0 ? null : `Exited ${code}` }); });
    });
}

async function isElevated() {
    const r = await runPowerShell(
        `([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)`
    );
    return r.success && r.output.trim().toLowerCase() === 'true';
}

// Read-only — safe to call anytime, no elevation needed.
// Uses Get-CimInstance, not Get-WmiObject -- the latter only exists in
// legacy Windows PowerShell 5.1, not pwsh (PowerShell 7), which is what
// this dashboard shells out to everywhere else. Caught by testing this
// standalone before wiring it up -- Get-WmiObject silently errored under
// pwsh and would have made every one of these handlers a no-op.
ipcMain.handle('get-pagefile-status', async () => {
    const script = `
$auto = (Get-CimInstance -ClassName Win32_ComputerSystem).AutomaticManagedPagefile
$settings = Get-CimInstance -ClassName Win32_PageFileSetting | Select-Object Name, InitialSize, MaximumSize
$usage = Get-CimInstance -ClassName Win32_PageFileUsage | Select-Object Name, AllocatedBaseSize, CurrentUsage
[PSCustomObject]@{ automaticManaged = $auto; settings = $settings; usage = $usage } | ConvertTo-Json -Depth 4 -Compress
`;
    const r = await runPowerShell(script);
    if (!r.success) return { success: false, error: r.error || r.stderr };
    try { return { success: true, ...JSON.parse(r.output) }; }
    catch (e) { return { success: false, error: `Could not parse WMI output: ${e.message}` }; }
});

// Moves the pagefile to a different drive. Consequential + needs a reboot
// to fully apply (same caveat as paging_windows.py) — requires Administrator
// and an explicit confirm:true from the caller. Does not run unattended.
ipcMain.handle('move-pagefile', async (event, { targetDrive, sizeGB, confirm }) => {
    if (!confirm) return { success: false, error: 'Refused: confirm:true required for a pagefile move.' };
    if (!targetDrive || !/^[A-Za-z]:$/.test(targetDrive)) return { success: false, error: 'targetDrive must look like "D:"' };
    if (!(await isElevated())) return { success: false, error: 'Requires Administrator — relaunch the dashboard elevated.' };
    const sizeMB = Math.round((sizeGB || 4) * 1024);
    const script = `
$targetName = "${targetDrive}\\pagefile.sys"
Get-CimInstance -ClassName Win32_ComputerSystem | Set-CimInstance -Property @{ AutomaticManagedPagefile = $false }
Get-CimInstance -ClassName Win32_PageFileSetting | Where-Object { $_.Name -ne $targetName } | Remove-CimInstance
$existing = Get-CimInstance -ClassName Win32_PageFileSetting | Where-Object { $_.Name -eq $targetName }
if ($existing) {
    $existing | Set-CimInstance -Property @{ InitialSize = ${sizeMB}; MaximumSize = ${sizeMB} }
} else {
    New-CimInstance -ClassName Win32_PageFileSetting -Property @{ Name = $targetName; InitialSize = ${sizeMB}; MaximumSize = ${sizeMB} } | Out-Null
}
"OK"
`;
    const r = await runPowerShell(script, 45000);
    return r.success
        ? { success: true, message: `Pagefile moved to ${targetDrive}\\pagefile.sys (${sizeGB}GB) — reboot required to fully apply.` }
        : { success: false, error: r.error || r.stderr };
});

// Removes an explicit pagefile setting for one drive. If nothing else is
// configured afterward, re-enables Windows' automatic management as a
// safety net rather than leaving the system with no pagefile at all and
// no auto-manage. Requires Administrator + explicit confirm:true.
ipcMain.handle('delete-pagefile', async (event, { targetDrive, confirm }) => {
    if (!confirm) return { success: false, error: 'Refused: confirm:true required to delete a pagefile.' };
    if (!targetDrive || !/^[A-Za-z]:$/.test(targetDrive)) return { success: false, error: 'targetDrive must look like "D:"' };
    if (!(await isElevated())) return { success: false, error: 'Requires Administrator — relaunch the dashboard elevated.' };
    const script = `
$targetName = "${targetDrive}\\pagefile.sys"
Get-CimInstance -ClassName Win32_PageFileSetting | Where-Object { $_.Name -eq $targetName } | Remove-CimInstance
$remaining = Get-CimInstance -ClassName Win32_PageFileSetting
if (-not $remaining) {
    Get-CimInstance -ClassName Win32_ComputerSystem | Set-CimInstance -Property @{ AutomaticManagedPagefile = $true }
    "OK: no pagefile settings remained, re-enabled automatic management"
} else {
    "OK"
}
`;
    const r = await runPowerShell(script, 45000);
    return r.success
        ? { success: true, message: `${r.output} — reboot required to fully apply.` }
        : { success: false, error: r.error || r.stderr };
});

// ── Phoenix env + AI auth ─────────────────────────────────────────────────────
const PHOENIX_CONF_DIR  = path.join(os.homedir(), '.phoenix');
const PHOENIX_ENV_FILE  = path.join(PHOENIX_CONF_DIR, 'phoenix.env');
const PHOENIX_AUTH_FILE = path.join(PHOENIX_CONF_DIR, 'ai_auth.json');

const PHOENIX_ENV_BOOT_KEYS = new Set([
    'PHOENIX_ROOT', 'PHOENIX_AI_PROVIDER', 'PHOENIX_OLLAMA_URL',
    'PHOENIX_SKIP_AUTH_MODAL',
    'CLONEPOOL_DIR', 'PHOENIX_WORKER_URL'
]);

function loadPhoenixEnv() {
    if (!fs.existsSync(PHOENIX_ENV_FILE)) return;
    try {
        const lines = fs.readFileSync(PHOENIX_ENV_FILE, 'utf8').split('\n');
        for (const raw of lines) {
            const line = raw.trim();
            if (!line || line.startsWith('#')) continue;
            const eq = line.indexOf('=');
            if (eq < 1) continue;
            const key = line.slice(0, eq).trim();
            let val = line.slice(eq + 1).trim();
            if ((val.startsWith('"') && val.endsWith('"')) ||
                (val.startsWith("'") && val.endsWith("'"))) {
                val = val.slice(1, -1);
            }
            if (PHOENIX_ENV_BOOT_KEYS.has(key) || !process.env[key]) {
                process.env[key] = val;
            }
        }
        console.log(`[Phoenix] loaded env from ${PHOENIX_ENV_FILE}`);
    } catch (e) {
        console.warn('[Phoenix] could not load phoenix.env:', e.message);
    }
}

function loadSavedAuth() {
    try {
        if (fs.existsSync(PHOENIX_AUTH_FILE)) {
            const saved = JSON.parse(fs.readFileSync(PHOENIX_AUTH_FILE, 'utf8'));
            if (saved.provider) process.env.PHOENIX_AI_PROVIDER = saved.provider;
            if (saved.key)      process.env.PHOENIX_AI_KEY      = saved.key;
            if (saved.model)    process.env.PHOENIX_AI_MODEL    = saved.model;
            if (saved.ollamaUrl) process.env.PHOENIX_OLLAMA_URL = saved.ollamaUrl;
            console.log(`[Phoenix AI] loaded saved auth — provider=${saved.provider || 'helpdesk'}`);
        }
    } catch (e) {
        console.warn('[Phoenix AI] could not load saved auth:', e.message);
    }
    if (!process.env.PHOENIX_AI_PROVIDER) {
        process.env.PHOENIX_AI_PROVIDER = 'helpdesk';
    }
}

loadSavedAuth();
loadPhoenixEnv(); // phoenix.env overrides saved auth for boot settings

// Check if the Claude Code CLI is installed and logged in
ipcMain.handle('check-claude-cli', async () => {
    return new Promise(resolve => {
        const cliName = process.platform === 'win32' ? 'claude.cmd' : 'claude';
        exec(`${cliName} --version`, { timeout: 6000 }, (err, stdout) => {
            if (err) return resolve({ available: false, reason: 'claude CLI not found — install with: npm install -g @anthropic-ai/claude-code' });
            // Check auth by running a no-op to see if we get an auth error
            exec(`${cliName} --print "ping"`, { timeout: 10000 }, (err2, stdout2, stderr2) => {
                const output = (stdout2 || '') + (stderr2 || '');
                const needsLogin = output.toLowerCase().includes('login') || output.toLowerCase().includes('auth') || output.toLowerCase().includes('not logged');
                resolve({
                    available: true,
                    version: stdout.trim(),
                    loggedIn: !err2 && !needsLogin,
                    reason: needsLogin ? 'not logged in — run: claude login' : null
                });
            });
        });
    });
});

// Get current AI auth status — sent to the modal on boot
ipcMain.handle('get-ai-status', async () => {
    const provider = process.env.PHOENIX_AI_PROVIDER || 'helpdesk';
    const hasKey   = !!(process.env.PHOENIX_AI_KEY || process.env.ANTHROPIC_API_KEY);
    const model    = process.env.PHOENIX_AI_MODEL || '';
    const ollamaUrl = process.env.PHOENIX_OLLAMA_URL || 'http://localhost:11434';
    const savedExists = fs.existsSync(PHOENIX_AUTH_FILE);
    const skipAuthModal = process.env.PHOENIX_SKIP_AUTH_MODAL === '1' ||
                          process.env.PHOENIX_SKIP_AUTH_MODAL === 'true';
    return { provider, hasKey, model, ollamaUrl, savedExists, skipAuthModal };
});

// Set AI credentials at runtime (called from auth modal)
ipcMain.handle('set-ai-auth', async (event, { provider, key, model, ollamaUrl, save }) => {
    process.env.PHOENIX_AI_PROVIDER = provider || 'helpdesk';
    if (key)       process.env.PHOENIX_AI_KEY      = key;
    if (model)     process.env.PHOENIX_AI_MODEL    = model;
    if (ollamaUrl) process.env.PHOENIX_OLLAMA_URL  = ollamaUrl;

    if (save) {
        try {
            const dir = path.dirname(PHOENIX_AUTH_FILE);
            if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
            // Merge over the existing saved file rather than overwriting it —
            // the modal deliberately sends '' for key/model/ollamaUrl when a
            // field is untouched (e.g. still showing the masked placeholder),
            // to avoid saving the mask string itself. Without merging here,
            // every save that doesn't retype every field silently drops
            // whatever was already saved, including a previously-set key.
            let existing = {};
            if (fs.existsSync(PHOENIX_AUTH_FILE)) {
                try { existing = JSON.parse(fs.readFileSync(PHOENIX_AUTH_FILE, 'utf8')); } catch (_) { existing = {}; }
            }
            const payload = {
                provider: provider || existing.provider || 'helpdesk',
                model: model || existing.model || '',
                ollamaUrl: ollamaUrl || existing.ollamaUrl || ''
            };
            const effectiveKey = key || existing.key;
            if (effectiveKey) payload.key = effectiveKey;
            fs.writeFileSync(PHOENIX_AUTH_FILE, JSON.stringify(payload, null, 2), { mode: 0o600 });
        } catch (e) {
            return { success: false, error: `Could not save auth file: ${e.message}` };
        }
    }
    return { success: true, provider: process.env.PHOENIX_AI_PROVIDER };
});

// Clear saved auth file
ipcMain.handle('clear-ai-auth', async () => {
    try {
        if (fs.existsSync(PHOENIX_AUTH_FILE)) fs.unlinkSync(PHOENIX_AUTH_FILE);
        return { success: true };
    } catch (e) {
        return { success: false, error: e.message };
    }
});

// ── Claude / Ollama AI Chat ───────────────────────────────────────────────────
// JS-side Helix memory — HelixMemoryJS (helix-packet.js).
// Same QuadralingualPacket format as Python coms1/freewheeling.py.
// NOSQL hot; VECTOR/RELATIONAL/TIMESERIES lazy. Push syncs to Python daemon when live.
const { HelixMemoryJS } = require('./helix-packet');
require('./clonepool-workdir').register({ ipcMain, dialog });
require('./screenshot-analysis').register({ ipcMain, desktopCapturer });
require('./hud-layout-backend').register({ ipcMain, spawn, dialog });
require('./ps7-shell').register({ ipcMain, spawn });
const _helixMem = new HelixMemoryJS(40);   // SectorID.CLAUDE, 40-turn rolling window

const PHOENIX_MANUAL_PATH = path.join(__dirname, 'manual', 'PHOENIX_MANUAL.md');
const LAURIE_GUIDE_PATH   = path.join(__dirname, 'manual', 'LAURIE_GUIDE.md');

function _phoenixSystemPrompt(stats) {
    const statsLine = stats
        ? `System state: ${stats.glossary_total} files in glossary, ${stats.custody_total} custody events, ${stats.r2_objects} R2 objects.`
        : 'System state: offline (D1 not reachable right now).';
    return [
        'You are the Phoenix DevOps OS Help Desk operator — built into every Phoenix desktop.',
        'Phoenix is a deterministic, self-healing, versioned OS built on Debian/Ubuntu.',
        'It is structured in four sectors: Sector 1 (Boot/Kernel), Sector 2 (Package handler/clone pool),',
        'Sector 3 (Comms/networking: romeo/juliet/quadengine), Sector 4 (Helix engine/Frank orchestrator).',
        'Helix is a double-strand memory engine, quadralingual (NOSQL/VECTOR/RELATIONAL/TIMESERIES).',
        'Frank is the import authority and audit logger — never moves.',
        'The clone pool is D1-backed + R2-backed: D1 = glossary/custody, R2 = raw file bytes.',
        'Help Desk chain: Ollama (local primary) → Claude (fallback).',
        'The operator manual is in the HUD MANUAL tab. Direct users there for reference material.',
        statsLine,
        'The user is Jerry Leftwich (jwl247), systems builder. His wife Laurie has a protected share in Phoenix.',
        'Co-founder Jerilynn handles UX, switches, and InfoSec/red team.',
        'Be direct, technical, and specific. No fluff. When something is wrong or missing, say so and say why.',
        'You have memory of this session via the Helix warm tier (in-process key/value store).',
    ].join(' ');
}

ipcMain.handle('get-user-manual', async () => {
    try {
        if (!fs.existsSync(PHOENIX_MANUAL_PATH)) {
            return { success: false, error: 'Manual not found at dashboard/manual/PHOENIX_MANUAL.md' };
        }
        const content = fs.readFileSync(PHOENIX_MANUAL_PATH, 'utf8');
        return { success: true, content, path: PHOENIX_MANUAL_PATH };
    } catch (e) {
        return { success: false, error: e.message };
    }
});

ipcMain.handle('get-laurie-guide', async () => {
    try {
        if (!fs.existsSync(LAURIE_GUIDE_PATH)) {
            return { success: false, error: 'Guide not found at dashboard/manual/LAURIE_GUIDE.md' };
        }
        const content = fs.readFileSync(LAURIE_GUIDE_PATH, 'utf8');
        return { success: true, content, path: LAURIE_GUIDE_PATH };
    } catch (e) {
        return { success: false, error: e.message };
    }
});

function _sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

function _httpJson(method, urlStr, body, timeoutMs = 8000) {
    return new Promise((resolve, reject) => {
        const url = new URL(urlStr);
        const payload = body ? JSON.stringify(body) : null;
        const req = http.request({
            hostname: url.hostname,
            port: url.port || 80,
            path: url.pathname + url.search,
            method,
            headers: payload ? {
                'Content-Type': 'application/json',
                'Content-Length': Buffer.byteLength(payload)
            } : {}
        }, res => {
            let data = '';
            res.on('data', chunk => { data += chunk; });
            res.on('end', () => {
                if (res.statusCode < 200 || res.statusCode >= 300) {
                    return reject(new Error(`HTTP ${res.statusCode}: ${data.slice(0, 200)}`));
                }
                try {
                    resolve(data ? JSON.parse(data) : {});
                } catch (e) {
                    reject(new Error(`Invalid JSON from Ollama: ${e.message}`));
                }
            });
        });
        req.on('error', reject);
        req.setTimeout(timeoutMs, () => req.destroy(new Error('Ollama request timed out')));
        if (payload) req.write(payload);
        req.end();
    });
}

async function _fetchJson(url, options = {}) {
    const timeoutMs = options.timeoutMs || 8000;
    try {
        const res = await fetch(url, {
            ...options,
            signal: AbortSignal.timeout(timeoutMs)
        });
        if (!res.ok) {
            const text = await res.text();
            throw new Error(`HTTP ${res.status}: ${text.slice(0, 200)}`);
        }
        return await res.json();
    } catch (e) {
        if (options.method === 'POST' && options.body) {
            return _httpJson('POST', url, JSON.parse(options.body), timeoutMs);
        }
        return _httpJson('GET', url, null, timeoutMs);
    }
}

async function _pingOllama(ollamaUrl) {
    try {
        const data = await _fetchJson(`${ollamaUrl}/api/tags`, { timeoutMs: 4000 });
        return { ok: true, models: (data.models || []).map(m => m.name) };
    } catch (e) {
        return { ok: false, reason: e.message };
    }
}

async function ensureOllamaRunning() {
    const ollamaUrl = process.env.PHOENIX_OLLAMA_URL || 'http://localhost:11434';
    let ping = await _pingOllama(ollamaUrl);
    if (ping.ok) return { started: false, online: true, url: ollamaUrl, models: ping.models };

    if (!fs.existsSync(OLLAMA_EXE)) {
        return { started: false, online: false, url: ollamaUrl, reason: 'Ollama not installed' };
    }

    try {
        spawn(OLLAMA_EXE, ['serve'], { detached: true, stdio: 'ignore', windowsHide: true }).unref();
    } catch (e) {
        return { started: false, online: false, url: ollamaUrl, reason: e.message };
    }

    for (let i = 0; i < 20; i++) {
        await _sleep(500);
        ping = await _pingOllama(ollamaUrl);
        if (ping.ok) {
            return { started: true, online: true, url: ollamaUrl, models: ping.models };
        }
    }
    return { started: true, online: false, url: ollamaUrl, reason: ping.reason || 'Ollama did not start' };
}

async function _resolveOllamaModel(ollamaUrl) {
    if (_resolvedOllamaModel) return _resolvedOllamaModel;
    const preferred = process.env.PHOENIX_AI_MODEL || 'llama3.2';
    const ping = await _pingOllama(ollamaUrl);
    if (!ping.ok) return preferred;

    const names = ping.models || [];
    if (names.includes(preferred)) {
        _resolvedOllamaModel = preferred;
        return preferred;
    }
    const partial = names.find(n => n.startsWith(preferred));
    if (partial) {
        _resolvedOllamaModel = partial;
        return partial;
    }
    if (names.length) {
        _resolvedOllamaModel = names[0];
        return names[0];
    }
    _resolvedOllamaModel = preferred;
    return preferred;
}

ipcMain.handle('ensure-ollama', async () => ensureOllamaRunning());

ipcMain.handle('check-ollama', async () => {
    const ollamaUrl = process.env.PHOENIX_OLLAMA_URL || 'http://localhost:11434';
    const ping = await _pingOllama(ollamaUrl);
    if (!ping.ok) {
        return { online: false, url: ollamaUrl, reason: ping.reason };
    }
    const model = await _resolveOllamaModel(ollamaUrl);
    return { online: true, url: ollamaUrl, models: ping.models, model };
});

async function _chatOllama(systemPrompt, messages) {
    await ensureOllamaRunning();
    const ollamaUrl = process.env.PHOENIX_OLLAMA_URL || 'http://localhost:11434';
    const model = await _resolveOllamaModel(ollamaUrl);
    const data = await _fetchJson(`${ollamaUrl}/api/chat`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
            model,
            stream: false,
            messages: [{ role: 'system', content: systemPrompt }, ...messages]
        }),
        timeoutMs: 180000
    });
    const reply = data.message?.content || '';
    if (!reply) throw new Error('Ollama returned empty response');
    return { provider: `ollama/${model}`, reply };
}

async function _chatClaudeApi(systemPrompt, messages) {
    const apiKey = process.env.PHOENIX_AI_KEY || process.env.ANTHROPIC_API_KEY || '';
    if (!apiKey) throw new Error('No Anthropic API key');
    const model = process.env.PHOENIX_AI_MODEL || 'claude-sonnet-5';
    const res = await fetch('https://api.anthropic.com/v1/messages', {
        method: 'POST',
        headers: {
            'x-api-key': apiKey,
            'anthropic-version': '2023-06-01',
            'content-type': 'application/json'
        },
        body: JSON.stringify({
            model,
            max_tokens: 1024,
            system: systemPrompt,
            messages
        }),
        signal: AbortSignal.timeout(120000)
    });
    if (!res.ok) {
        const err = await res.text();
        throw new Error(`Claude API ${res.status}: ${err.slice(0, 200)}`);
    }
    const data = await res.json();
    const reply = data.content?.[0]?.text || '';
    if (!reply) throw new Error('Claude API returned empty response');
    return { provider: `claude/${model}`, reply };
}

// Real token-by-token streaming via Anthropic's SSE endpoint. `onChunk` is
// called with each text delta as it arrives — the caller pushes those to
// the renderer over IPC so the HUD can render incrementally instead of
// waiting for the full reply.
async function _chatClaudeApiStream(systemPrompt, messages, onChunk) {
    const apiKey = process.env.PHOENIX_AI_KEY || process.env.ANTHROPIC_API_KEY || '';
    if (!apiKey) throw new Error('No Anthropic API key');
    const model = process.env.PHOENIX_AI_MODEL || 'claude-sonnet-5';
    const res = await fetch('https://api.anthropic.com/v1/messages', {
        method: 'POST',
        headers: {
            'x-api-key': apiKey,
            'anthropic-version': '2023-06-01',
            'content-type': 'application/json'
        },
        body: JSON.stringify({
            model,
            max_tokens: 1024,
            system: systemPrompt,
            messages,
            stream: true
        }),
        signal: AbortSignal.timeout(120000)
    });
    if (!res.ok) {
        const err = await res.text();
        throw new Error(`Claude API ${res.status}: ${err.slice(0, 200)}`);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let full = '';
    let sawError = null;

    while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop(); // last line may be incomplete — carry it over
        for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed.startsWith('data:')) continue;
            const jsonStr = trimmed.slice(5).trim();
            if (!jsonStr) continue;
            let evt;
            try { evt = JSON.parse(jsonStr); } catch (_) { continue; }
            if (evt.type === 'content_block_delta' && evt.delta?.text) {
                full += evt.delta.text;
                onChunk(evt.delta.text);
            } else if (evt.type === 'error') {
                sawError = evt.error?.message || 'stream error';
            }
        }
    }

    if (sawError) throw new Error(`Claude API stream error: ${sawError}`);
    if (!full) throw new Error('Claude API returned empty response');
    return { provider: `claude/${model}`, reply: full };
}

// Find the Claude Code CLI on Windows — tries PATH then npm global bin
function _findClaudeCli() {
    if (process.platform !== 'win32') return 'claude';
    const npmGlobal = path.join(os.homedir(), 'AppData', 'Roaming', 'npm', 'claude.cmd');
    if (fs.existsSync(npmGlobal)) return `"${npmGlobal}"`;
    return 'claude.cmd';
}

// Run Claude Code CLI — spawn so we can write the full prompt to stdin
// NOTE: child_process.exec() ignores the `input` option; spawn is required.
function _runClaudeCli(prompt) {
    return new Promise((resolve, reject) => {
        const isWin = process.platform === 'win32';
        const npmGlobal = path.join(os.homedir(), 'AppData', 'Roaming', 'npm', 'claude.cmd');
        const cliResolved = (isWin && fs.existsSync(npmGlobal)) ? npmGlobal : (isWin ? 'claude.cmd' : 'claude');

        // Strip API-key auth from the child's env so this call cannot silently
        // fall back to pay-per-token billing when the whole point of this tier
        // is to spend subscription usage, not API credit.
        const subscriptionOnlyEnv = { ...process.env };
        delete subscriptionOnlyEnv.ANTHROPIC_API_KEY;
        delete subscriptionOnlyEnv.ANTHROPIC_AUTH_TOKEN;

        // Explicit no-tools: this is a chat answer, not a coding-agent turn.
        // Nothing here should touch Bash, Write, or Edit without you asking
        // for that separately, through a path that actually shows you what
        // it's about to do.
        const args = ['--print', '--disallowedTools', 'Bash,Write,Edit,WebFetch,WebSearch'];
        const spawnOpts = { timeout: 60000, env: subscriptionOnlyEnv };
        const proc = isWin
            ? spawn('cmd.exe', ['/c', cliResolved, ...args], spawnOpts)
            : spawn(cliResolved, args, spawnOpts);

        let stdout = '';
        let stderr = '';
        proc.stdout.on('data', d => { stdout += d; });
        proc.stderr.on('data', d => { stderr += d; });
        proc.on('error', reject);
        proc.on('close', code => {
            if (code !== 0) return reject(new Error(stderr || `claude exited ${code}`));
            resolve(stdout.trim());
        });

        proc.stdin.write(prompt, 'utf8');
        proc.stdin.end();
    });
}

// Dedicated, full-capability Claude — the CLAUDE tab specifically, not the
// Ollama-failure fallback. Full Bash/Write/Edit/WebFetch/WebSearch access,
// no Ollama involvement, no shared fallback chain. `--print` is non-
// interactive so there's no permission prompt to answer — a tool call would
// otherwise just be silently denied, so --dangerously-skip-permissions is
// required for tools to actually run here, not merely be allowed in theory.
// Streams stdout chunks as they arrive, same shape as the API streaming path.
function _runClaudeCliFull(prompt, onChunk) {
    return new Promise((resolve, reject) => {
        const isWin = process.platform === 'win32';
        const npmGlobal = path.join(os.homedir(), 'AppData', 'Roaming', 'npm', 'claude.cmd');
        const cliResolved = (isWin && fs.existsSync(npmGlobal)) ? npmGlobal : (isWin ? 'claude.cmd' : 'claude');

        const subscriptionOnlyEnv = { ...process.env };
        delete subscriptionOnlyEnv.ANTHROPIC_API_KEY;
        delete subscriptionOnlyEnv.ANTHROPIC_AUTH_TOKEN;

        const args = ['--print', '--dangerously-skip-permissions'];
        const spawnOpts = { timeout: 120000, env: subscriptionOnlyEnv };
        const proc = isWin
            ? spawn('cmd.exe', ['/c', cliResolved, ...args], spawnOpts)
            : spawn(cliResolved, args, spawnOpts);

        let stdout = '';
        let stderr = '';
        proc.stdout.on('data', d => {
            const text = d.toString('utf8');
            stdout += text;
            if (onChunk) onChunk(text);
        });
        proc.stderr.on('data', d => { stderr += d; });
        proc.on('error', reject);
        proc.on('close', code => {
            if (code !== 0) return reject(new Error(stderr || `claude exited ${code}`));
            resolve(stdout.trim());
        });

        proc.stdin.write(prompt, 'utf8');
        proc.stdin.end();
    });
}

ipcMain.handle('ai-chat', async (event, { message, history, phoenixStats }) => {
    const provider = (process.env.PHOENIX_AI_PROVIDER || 'helpdesk').toLowerCase();
    const systemPrompt = _phoenixSystemPrompt(phoenixStats);

    _helixMem.pushTurn('user', message);
    const chatMessages = _helixMem.getHistory(20);

    const historyText = chatMessages.slice(0, -1)
        .map(m => `${m.role === 'user' ? 'User' : 'Assistant'}: ${m.content}`).join('\n');
    const fullPrompt = `${systemPrompt}\n\n${historyText ? historyText + '\n\n' : ''}User: ${message}`;

    const errors = [];

    // ── Help Desk mode: Ollama → Claude (automatic chain) ──────────────────
    if (provider === 'helpdesk' || provider === 'ollama') {
        try {
            const result = await _chatOllama(systemPrompt, chatMessages);
            _helixMem.pushTurn('assistant', result.reply);
            return { success: true, ...result, fallback: false };
        } catch (e) {
            errors.push(`ollama: ${e.message}`);
            console.log(`[Help Desk] Ollama unavailable (${e.message}), trying Claude`);
        }
    }

    // ── Claude API (explicit API key) — real token-by-token streaming ──────
    if (provider === 'claude') {
        try {
            const result = await _chatClaudeApiStream(systemPrompt, chatMessages, (delta) => {
                event.sender.send('ai-chat-stream-chunk', { delta });
            });
            _helixMem.pushTurn('assistant', result.reply);
            return { success: true, ...result, fallback: false, streamed: true };
        } catch (e) {
            return { success: false, provider: 'claude', error: e.message };
        }
    }

    // ── Claude subscription (CLAUDE tab) — dedicated, not a fallback ───────
    // No Ollama in this chain at all, full tool access (Bash/Write/Edit/
    // WebFetch/WebSearch), streamed. This is "ask for Claude, get Claude" —
    // separate from the Ollama-failure safety net below, which deliberately
    // stays restricted.
    if (provider === 'subscription') {
        try {
            const reply = await _runClaudeCliFull(fullPrompt, (chunk) => {
                event.sender.send('ai-chat-stream-chunk', { delta: chunk });
            });
            _helixMem.pushTurn('assistant', reply);
            return { success: true, provider: 'claude/subscription', reply, fallback: false, streamed: true };
        } catch (e) {
            const msg = e.message.toLowerCase();
            const error = (msg.includes('login') || msg.includes('auth') || msg.includes('not logged'))
                ? 'Not logged in to Claude Code — run: claude login'
                : `Claude CLI: ${e.message}`;
            return { success: false, provider: 'claude/subscription', error };
        }
    }

    // ── Ollama-failure fallback — restricted-tool Claude CLI, safety net ───
    // Only reached from the helpdesk/ollama branch above failing. Kept
    // deliberately chat-only: this is "Ollama's down, get me any answer,"
    // not "I asked for Claude" — it shouldn't inherit full tool access.
    try {
        const reply = await _runClaudeCli(fullPrompt);
        _helixMem.pushTurn('assistant', reply);
        return {
            success: true,
            provider: 'claude/subscription',
            reply,
            fallback: true,
            fallbackFrom: 'ollama'
        };
    } catch (e) {
        errors.push(`claude: ${e.message}`);
        const msg = e.message.toLowerCase();
        const claudeHint = (msg.includes('login') || msg.includes('auth') || msg.includes('not logged'))
            ? 'Not logged in to Claude Code — run: claude login'
            : `Claude CLI: ${e.message}`;
        return {
            success: false,
            provider: 'helpdesk',
            error: `All Help Desk providers unavailable.\n${errors.join('\n')}\n${claudeHint}\n\nStart Ollama (ollama serve) or set ANTHROPIC_API_KEY for Claude.`
        };
    }
});

// Show notification
ipcMain.handle('show-notification', async (event, title, body) => {
    const { Notification } = require('electron');
    if (Notification.isSupported()) {
        new Notification({ title, body }).show();
        return { success: true };
    }
    return { success: false, error: 'Notifications not supported' };
});

// Log to console (for debugging)
ipcMain.on('log', (event, ...args) => {
    console.log('[Renderer]', ...args);
});

console.log('Phoenix Dashboard Electron app started');
console.log('Platform:', process.platform);
console.log('PHOENIX_ROOT:', process.env.PHOENIX_ROOT || 'Not set');
console.log('CLONEPOOL_DIR:', process.env.CLONEPOOL_DIR || 'Not set');

// Made with Bob
