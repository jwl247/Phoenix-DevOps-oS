// clonepool-workdir.js
// "Call any intaked file to your working directory" — clone (always copy) or
// sync (copy only if changed) a file OUT of the clonepool into a folder you pick.
//
// Additive module. Wire into main.js with:
//   require('./clonepool-workdir').register({ ipcMain, dialog, app });
//
// Does not touch, redefine, or duplicate any existing handler in main.js.
// Reuses the same realpath-containment pattern main.js already uses for run-file.

const fs = require('fs');
const path = require('path');
const os = require('os');

const PHOENIX_CONF_DIR = path.join(os.homedir(), '.phoenix');
const MANIFEST_PATH = path.join(PHOENIX_CONF_DIR, 'clone-manifest.json');

function resolveClonepoolDir() {
    return process.env.CLONEPOOL_DIR || path.join(os.homedir(), 'Phoenix', 'clonepool');
}

function ensureConfDir() {
    if (!fs.existsSync(PHOENIX_CONF_DIR)) {
        fs.mkdirSync(PHOENIX_CONF_DIR, { recursive: true });
    }
}

function loadManifest() {
    try {
        if (!fs.existsSync(MANIFEST_PATH)) return {};
        return JSON.parse(fs.readFileSync(MANIFEST_PATH, 'utf8'));
    } catch (e) {
        console.warn('[clonepool-workdir] manifest unreadable, starting fresh:', e.message);
        return {};
    }
}

function saveManifest(manifest) {
    ensureConfDir();
    fs.writeFileSync(MANIFEST_PATH, JSON.stringify(manifest, null, 2), 'utf8');
}

// Strict containment check — mirrors run-file's executionRoots pattern in main.js.
function isInside(parentDir, targetPath) {
    try {
        const realParent = fs.realpathSync(parentDir);
        const realTarget = fs.realpathSync(targetPath);
        const rel = path.relative(realParent, realTarget);
        return rel === '' || (!rel.startsWith('..') && !path.isAbsolute(rel));
    } catch (_) {
        return false;
    }
}

// Recursive clonepool listing. Depth-bounded (doesn't help much once a pool
// is wide rather than deep — see below) AND async: every fs call goes
// through fs.promises so each await yields back to Electron's event loop.
// The clonepool crossed 15k files after a large intake pass and the old
// fs.readdirSync/statSync version blocked the ENTIRE app (not just this
// panel) for ~2s per open — this fixes the freeze, not just this panel's
// slowness. Still walks every file to sort by recency, so still takes a
// couple seconds on a large pool, but the rest of the app stays responsive
// while it runs.
const fsp = fs.promises;

async function walkClonepool(dir, baseDir, depth, maxDepth, out) {
    if (depth > maxDepth) return;
    let entries;
    try {
        entries = await fsp.readdir(dir, { withFileTypes: true });
    } catch (_) {
        return;
    }
    for (const entry of entries) {
        const abs = path.join(dir, entry.name);
        if (entry.isDirectory()) {
            await walkClonepool(abs, baseDir, depth + 1, maxDepth, out);
        } else if (entry.isFile()) {
            let stats;
            try { stats = await fsp.stat(abs); } catch (_) { continue; }
            out.push({
                relPath: path.relative(baseDir, abs),
                absPath: abs,
                size: stats.size,
                mtimeMs: stats.mtimeMs,
                suite: path.relative(baseDir, dir).split(path.sep)[0] || null
            });
        }
    }
}

function register({ ipcMain, dialog }) {
    // List everything currently in the clonepool, real filesystem read, no cache.
    // `query` filters by substring on relPath before capping — so searching
    // for an older file still finds it even though the unfiltered list only
    // shows the most-recent LIST_CAP files. `limit` overrides LIST_CAP.
    const LIST_CAP = 200;
    ipcMain.handle('list-clonepool-files', async (event, { query, limit } = {}) => {
        const clonepoolDir = resolveClonepoolDir();
        if (!fs.existsSync(clonepoolDir)) {
            return { success: false, error: `Clonepool not found at ${clonepoolDir}`, files: [] };
        }
        const out = [];
        await walkClonepool(clonepoolDir, clonepoolDir, 0, 6, out);

        const q = (query || '').trim().toLowerCase();
        const matched = q ? out.filter(f => f.relPath.toLowerCase().includes(q)) : out;
        matched.sort((a, b) => b.mtimeMs - a.mtimeMs);

        const cap = limit || LIST_CAP;
        const files = matched.slice(0, cap);
        return {
            success: true,
            clonepoolDir,
            files,
            total: out.length,
            matched: matched.length,
            truncated: matched.length > files.length
        };
    });

    // Native directory picker — the target-selection gate. No hardcoded destination.
    ipcMain.handle('open-directory-dialog', async (event, options = {}) => {
        const result = await dialog.showOpenDialog({
            properties: ['openDirectory', 'createDirectory'],
            title: options.title || 'Choose working directory'
        });
        if (result.canceled || !result.filePaths.length) {
            return { success: false, canceled: true };
        }
        return { success: true, dir: result.filePaths[0] };
    });

    // The actual clone/sync action.
    ipcMain.handle('clone-file-to-workdir', async (event, { sourcePath, targetDir, mode }) => {
        const clonepoolDir = resolveClonepoolDir();

        if (!sourcePath || !fs.existsSync(sourcePath)) {
            return { success: false, error: `Source file not found: ${sourcePath}` };
        }
        if (!isInside(clonepoolDir, sourcePath)) {
            return { success: false, error: 'Source must be inside the clonepool. Refusing to clone from outside it.' };
        }
        if (!targetDir || !fs.existsSync(targetDir) || !fs.statSync(targetDir).isDirectory()) {
            return { success: false, error: `Target directory does not exist: ${targetDir}` };
        }
        if (isInside(clonepoolDir, targetDir)) {
            return { success: false, error: 'Refusing to clone a file back into the clonepool itself.' };
        }

        const fileName = path.basename(sourcePath);
        const destPath = path.join(targetDir, fileName);
        const srcStats = fs.statSync(sourcePath);

        const manifest = loadManifest();
        const manifestKey = `${sourcePath}::${targetDir}`;

        if (mode === 'sync') {
            const prior = manifest[manifestKey];
            const destExists = fs.existsSync(destPath);
            if (prior && destExists &&
                prior.size === srcStats.size &&
                prior.mtimeMs === srcStats.mtimeMs) {
                return {
                    success: true,
                    copied: false,
                    reason: 'up-to-date',
                    destPath,
                    lastSynced: prior.syncedAt
                };
            }
        }

        try {
            fs.copyFileSync(sourcePath, destPath);
        } catch (e) {
            return { success: false, error: `Copy failed: ${e.message}` };
        }

        manifest[manifestKey] = {
            size: srcStats.size,
            mtimeMs: srcStats.mtimeMs,
            syncedAt: new Date().toISOString()
        };
        saveManifest(manifest);

        return { success: true, copied: true, destPath };
    });
}

module.exports = { register };
