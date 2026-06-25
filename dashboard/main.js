// Phoenix Dashboard - Electron Main Process
// Handles window creation, IPC communication, and Phoenix command execution

const { app, BrowserWindow, ipcMain, dialog } = require('electron');
const { exec } = require('child_process');
const path = require('path');
const fs = require('fs');
const os = require('os');

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
            nodeIntegration: true,
            contextIsolation: false,
            enableRemoteModule: true
        },
        frame: true,
        autoHideMenuBar: true
    });

    // Load the dashboard
    mainWindow.loadFile('index.html');

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
app.whenReady().then(() => {
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

// Execute Phoenix usys command
ipcMain.handle('execute-command', async (event, command) => {
    return new Promise((resolve) => {
        console.log(`Executing: ${command}`);
        
        // Determine shell based on platform
        const shell = process.platform === 'win32' ? 'pwsh.exe' : 'bash';
        const shellArgs = process.platform === 'win32' 
            ? ['-NoProfile', '-Command', command]
            : ['-c', command];

        exec(`${shell} ${shellArgs.join(' ')}`, {
            cwd: process.env.PHOENIX_ROOT || process.cwd(),
            timeout: 30000, // 30 second timeout
            maxBuffer: 1024 * 1024 * 10 // 10MB buffer
        }, (error, stdout, stderr) => {
            if (error) {
                console.error(`Command error: ${error.message}`);
                resolve({
                    success: false,
                    error: error.message,
                    stderr: stderr,
                    stdout: stdout
                });
            } else {
                resolve({
                    success: true,
                    output: stdout,
                    stderr: stderr
                });
            }
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
