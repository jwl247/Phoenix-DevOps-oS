// slot-transfer.js
// Drag and drop between the folder slots across the top of the dashboard.
// Every request is checked here in the main process, not in the page:
//   - The destination must be inside one of the explicit places (HOME, the Phoenix
//     repo) or one of your slot folders. ROOT (every drive) is for browsing only:
//     it is never a destination and never the source of a move or rename (DASH-S19).
//   - Anything whose source is NOT inside a place or slot (an Explorer drop, a
//     ../ trick, a mesh share) is only ever COPIED. Main decides that from the
//     resolved path; the page's `external` flag can only make a request safer
//     (external:true forces copy), never looser (external:false is ignored).
//   - Nothing is overwritten. If the name is taken, that item is skipped and you're told.
//   - A folder can't go inside itself.
//   - Nothing is ever MOVED or RENAMED off breach_coms4 (CRITICAL RULE 8). The drive
//     is found by its VOLUME LABEL (Windows: the drive letter's label; Linux: findmnt),
//     plus the old path-text match. If the label can't be read, the move is refused
//     (fails closed). Copying out of it is fine. (DASH-F26)
//   - The operating system's own folders (C:\Windows, Program Files, ProgramData,
//     /bin /etc /usr ...) are read-only here: copy out of them, never into or out by move.
//     A drive root itself can't be moved.
//   - A move across drives is copy, verify (size + SHA-256 of every file, streamed and
//     async, source and target hashed in parallel), then remove the original. If the
//     copy or the check fails or throws, the copy is removed and the original stays
//     where it was. (DASH-F27)
//
// Wire into main.js:
//   require('./slot-transfer').register({ ipcMain, getSlots, phoenixRoot });   // getSlots() -> the 6 slot folders

const fs = require('fs');
const fsp = fs.promises;
const path = require('path');
const crypto = require('crypto');
const os = require('os');
const { execFile } = require('child_process');

const VAULT_LABEL = 'breach_coms4';
const PROTECTED_MOVE = /(^|[\\/])breach_coms4([\\/]|$)/i;
const SYSTEM_DIRS = process.platform === 'win32'
    ? [/^[a-z]:\\windows(\\|$)/i, /^[a-z]:\\program files( \(x86\))?(\\|$)/i, /^[a-z]:\\programdata(\\|$)/i,
       /^[a-z]:\\\$recycle\.bin(\\|$)/i, /^[a-z]:\\system volume information(\\|$)/i]
    : [/^\/(bin|boot|dev|etc|lib|lib32|lib64|proc|run|sbin|sys|usr|var)(\/|$)/];
const isSystem = (p) => SYSTEM_DIRS.some((re) => re.test(p));
const isDriveRoot = (p) => path.parse(p).root === p;

function real(p) {
    try { return fs.realpathSync.native(p); } catch { return path.resolve(p); }
}

function inside(child, parent) {
    const rel = path.relative(parent, child);
    return rel === '' || (!!rel && !rel.startsWith('..') && !path.isAbsolute(rel));
}

// ── Volume labels (DASH-F26) ────────────────────────────────────────────────
// labelsUnder(absPath) -> Promise<string[] | null>
//   the label of the volume holding absPath, plus (Linux) any volume mounted
//   beneath it; null = could not tell (the caller refuses the move).
const LABEL_TTL_MS = 10000;     // drives get plugged in and swapped: re-read after 10 s
const run = (cmd, args) => new Promise((resolve, reject) =>
    execFile(cmd, args, { windowsHide: true, timeout: 8000, maxBuffer: 1 << 20 },
        (err, out) => (err ? reject(err) : resolve(String(out)))));

const WIN_LABELS_PS = "Get-CimInstance Win32_LogicalDisk | ForEach-Object { $_.DeviceID + '|' + $_.VolumeName }";
let winCache = { at: 0, map: null, pending: null };
function winLabels(force) {
    if (!force && winCache.map && Date.now() - winCache.at < LABEL_TTL_MS) return Promise.resolve(winCache.map);
    if (winCache.pending) return winCache.pending;
    // One call reads every drive letter, local and network (Get-Volume misses mapped shares).
    winCache.pending = run('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', WIN_LABELS_PS])
        .then((out) => {
            const map = new Map();
            for (const line of out.split(/\r?\n/)) {
                const m = /^([A-Za-z]):\|(.*)$/.exec(line.trim());
                if (m) map.set(m[1].toUpperCase(), m[2].trim());
            }
            winCache = { at: Date.now(), map, pending: null };
            return map;
        }, (e) => { winCache.pending = null; throw e; });
    return winCache.pending;
}

let mntCache = { at: 0, list: null };
async function linuxMounts() {
    if (mntCache.list && Date.now() - mntCache.at < LABEL_TTL_MS) return mntCache.list;
    const out = await run('findmnt', ['-rn', '-o', 'TARGET,LABEL']);
    const unesc = (s) => s.replace(/\\x([0-9a-f]{2})/gi, (_, h) => String.fromCharCode(parseInt(h, 16)));
    const list = out.split('\n').filter(Boolean).map((l) => {
        const [t, lab = ''] = l.split(' ');
        return { target: unesc(t), label: unesc(lab) };
    });
    mntCache = { at: Date.now(), list };
    return list;
}

async function defaultLabelsUnder(abs) {
    try {
        if (process.platform === 'win32') {
            const m = /^([A-Za-z]):/.exec(abs);
            if (!m) return null;                                 // UNC / no drive letter: can't tell
            const letter = m[1].toUpperCase();
            let map = await winLabels(false);
            if (!map.has(letter)) map = await winLabels(true);   // just plugged in
            return map.has(letter) ? [map.get(letter)] : null;
        }
        const mounts = await linuxMounts();
        let best = null;
        for (const mt of mounts) if (inside(abs, mt.target) && (!best || mt.target.length > best.target.length)) best = mt;
        if (!best) return null;
        // A folder being moved may hold another volume's mount point.
        return [best.label, ...mounts.filter((mt) => mt !== best && inside(mt.target, abs)).map((mt) => mt.label)];
    } catch { return null; }
}

// null = fine to move/rename; otherwise the reason it's refused.
async function vaultBlock(src, labelsUnder) {
    if (PROTECTED_MOVE.test(src)) return 'breach_coms4 is the master vault — copy from it, never move or rename';
    let labels = null;
    try { labels = await labelsUnder(src); } catch { labels = null; }
    if (!Array.isArray(labels)) return "couldn't read the drive's label to rule out breach_coms4 — copy it instead";
    if (labels.some((l) => String(l || '').trim().toLowerCase() === VAULT_LABEL)) {
        return 'that drive is breach_coms4, the master vault — copy from it, never move or rename';
    }
    return null;
}

// ── Streamed SHA-256 (DASH-F27): any size, never blocks the main process ────
function sha256(file) {
    return new Promise((resolve, reject) => {
        const h = crypto.createHash('sha256');
        fs.createReadStream(file, { highWaterMark: 1 << 20 })
            .on('data', (c) => h.update(c))
            .on('error', reject)
            .on('end', () => resolve(h.digest('hex')));
    });
}

// Every file under `p` (or p itself) as relative path -> "size:sha".
async function fingerprint(p) {
    const out = new Map();
    const walk = async (abs, rel) => {
        const st = await fsp.lstat(abs);
        if (st.isDirectory()) { for (const n of await fsp.readdir(abs)) await walk(path.join(abs, n), path.join(rel, n)); }
        else if (st.isFile()) out.set(rel, `${st.size}:${await sha256(abs)}`);
        else out.set(rel, `link:${st.isSymbolicLink() ? await fsp.readlink(abs) : 'other'}`);
    };
    await walk(p, '.');
    return out;
}

async function sameTree(a, b) {
    const [fa, fb] = await Promise.all([fingerprint(a), fingerprint(b)]);   // two drives: read both at once
    if (fa.size !== fb.size) return false;
    for (const [k, v] of fa) if (fb.get(k) !== v) return false;
    return true;
}

// Cross-drive move: copy, verify, and only then remove the original. Any failure
// after the copy started removes the copy (the caller checked the target did not
// exist) and leaves the source alone.
async function crossDriveMove(src, target) {
    try {
        await fsp.cp(src, target, { recursive: true, errorOnExist: true, force: false, preserveTimestamps: true });
        if (!(await sameTree(src, target))) throw new Error('copy did not verify — original left in place');
    } catch (e) {
        await fsp.rm(target, { recursive: true, force: true }).catch(() => {});
        if (!/did not verify/.test(e.message)) e.message = `copy failed (${e.message}) — copy removed, original left in place`;
        throw e;
    }
    await fsp.rm(src, { recursive: true });                    // only reached once the target verified
}

/**
 * sources:  absolute paths
 * toDir:    absolute destination folder
 * mode:     'move' | 'copy'
 * external: true = the page says it came from outside (forces copy). false is NOT
 *           trusted: a source outside every root is copy-only regardless.
 * roots0:   every allowed root (HOME, Phoenix repo, slots) — never "every drive"
 * opts.labelsUnder: volume-label lookup (tests inject one)
 */
async function transfer({ sources, toDir, mode, external }, roots0, opts = {}) {
    const labelsUnder = opts.labelsUnder || defaultLabelsUnder;
    const roots = (roots0 || []).filter(Boolean).map(real);
    if (!roots.length) return { success: false, error: 'No slot folders set.' };
    if (!Array.isArray(sources) || !sources.length) return { success: false, error: 'Nothing to transfer.' };
    if (typeof toDir !== 'string' || !fs.existsSync(toDir) || !fs.statSync(toDir).isDirectory()) {
        return { success: false, error: `Destination is not a folder: ${toDir}` };
    }
    const dest = real(toDir);
    if (!roots.some((r) => inside(dest, r))) return { success: false, error: 'Destination is not inside one of your places or slot folders.' };
    if (isSystem(dest)) return { success: false, error: `${dest} is an operating-system folder — nothing is put there from the dashboard.` };
    const asked = external === true ? 'copy' : (mode === 'copy' ? 'copy' : 'move');

    const done = [], skipped = [];
    for (const src0 of sources) {
        const name = path.basename(String(src0));
        if (typeof src0 !== 'string' || !fs.existsSync(src0)) { skipped.push({ name, reason: 'no longer exists' }); continue; }
        const src = real(src0);
        // Decided here, from the resolved path: outside every root = copy only.
        const how = asked === 'move' && roots.some((r) => inside(src, r)) ? 'move' : 'copy';
        if (path.dirname(src) === dest) { skipped.push({ name, reason: 'already in that folder' }); continue; }
        const isDir = fs.statSync(src).isDirectory();
        if (isDir && inside(dest, src)) { skipped.push({ name, reason: "a folder can't go inside itself" }); continue; }
        const target = path.join(dest, name);
        if (fs.existsSync(target)) { skipped.push({ name, reason: `"${name}" already exists there — nothing overwritten` }); continue; }
        if (how === 'move' && (isSystem(src) || isDriveRoot(src))) { skipped.push({ name, reason: 'operating-system folder — copy it, never move it' }); continue; }
        if (how === 'move') {
            const why = await vaultBlock(src, labelsUnder);
            if (why) { skipped.push({ name, reason: why }); continue; }
        }
        try {
            if (how === 'move') {
                try {
                    await fsp.rename(src, target);                  // same drive: instant, atomic
                } catch (e) {
                    if (e.code !== 'EXDEV') throw e;
                    await crossDriveMove(src, target);
                }
            } else {
                await fsp.cp(src, target, { recursive: true, errorOnExist: true, force: false, preserveTimestamps: true });
            }
            done.push({ name, to: target, mode: how });
        } catch (e) {
            skipped.push({ name, reason: e.message });
        }
    }
    const modes = new Set(done.map((d) => d.mode));
    const overall = modes.size === 1 ? [...modes][0] : (modes.size ? 'mixed' : asked);
    return { success: done.length > 0 || skipped.length === 0, mode: overall, done, skipped };
}

// Rename in place. Same checks as a move: inside a place or slot, never over an
// existing name, never on breach_coms4 or in an OS folder, a plain name only (no / or \).
async function rename({ path: src0, newName }, roots0, opts = {}) {
    const labelsUnder = opts.labelsUnder || defaultLabelsUnder;
    const roots = (roots0 || []).filter(Boolean).map(real);
    if (typeof src0 !== 'string' || !fs.existsSync(src0)) return { success: false, error: 'That item no longer exists.' };
    const name = String(newName || '').trim();
    if (!name || name === '.' || name === '..' || /[\\/]/.test(name) || (process.platform === 'win32' && /[<>:"|?*]/.test(name))) {
        return { success: false, error: 'Not a valid name.' };
    }
    const src = real(src0);
    if (!roots.some((r) => inside(src, r))) return { success: false, error: 'Not inside one of your places or slot folders.' };
    if (isSystem(src) || isDriveRoot(src)) return { success: false, error: 'Operating-system folder — not renamed.' };
    const why = await vaultBlock(src, labelsUnder);
    if (why) return { success: false, error: `Not renamed: ${why}.` };
    const target = path.join(path.dirname(src), name);
    if (target === src) return { success: true, path: src };
    // A case-only change (a.txt -> A.txt) on Windows is the same file, not a clash.
    const caseOnly = target.toLowerCase() === src.toLowerCase();
    if (fs.existsSync(target) && !caseOnly) return { success: false, error: `"${name}" already exists there — nothing overwritten.` };
    try { await fsp.rename(src, target); } catch (e) { return { success: false, error: e.message }; }
    return { success: true, path: target };
}

// Every entry in a folder — hidden files included, nothing filtered — folders first.
function listFull(dir) {
    const out = [];
    for (const d of fs.readdirSync(dir, { withFileTypes: true })) {
        const p = path.join(dir, d.name);
        let size = null, mtime = null, isDir = d.isDirectory(), link = d.isSymbolicLink();
        try {
            const st = fs.statSync(p);                    // follows links: a link to a folder opens like a folder
            size = st.isFile() ? st.size : null; mtime = st.mtimeMs; isDir = st.isDirectory();
        } catch { /* broken link or no access: still listed */ }
        out.push({ name: d.name, path: p, isDir, size, mtime, link, hidden: d.name.startsWith('.') });
    }
    out.sort((a, b) => (b.isDir - a.isDir) || a.name.localeCompare(b.name, undefined, { sensitivity: 'base', numeric: true }));
    return out;
}

function drives() {
    if (process.platform !== 'win32') return ['/'];
    const out = [];
    for (let c = 65; c <= 90; c++) {
        const d = String.fromCharCode(c) + ':\\';
        try { fs.accessSync(d); out.push(d); } catch { /* no such drive */ }
    }
    return out;
}

// The fixed places across the top: HOME, ROOT (every drive on Windows, / elsewhere), PHOENIX.
// ROOT is for browsing only — it is not a transfer or rename root (see moveRoots).
function places(phoenixRoot) {
    const list = [
        { key: 'home', label: 'HOME', path: os.homedir() },
        { key: 'root', label: 'ROOT', path: process.platform === 'win32' ? null : '/', drives: drives() },
    ];
    if (phoenixRoot && fs.existsSync(phoenixRoot)) list.push({ key: 'phoenix', label: 'PHOENIX', path: phoenixRoot });
    return list;
}

// Where things may land, and the only places a move or rename may start from:
// HOME, the Phoenix repo, and the slot folders. Never ROOT / every drive (DASH-S19).
function moveRoots(phoenixRoot, slots) {
    return [...places(phoenixRoot).filter((p) => p.key !== 'root').map((p) => p.path), ...(slots || [])].filter(Boolean);
}

function register({ ipcMain, getSlots, phoenixRoot }) {
    const getRoots = () => moveRoots(phoenixRoot, getSlots() || []);
    ipcMain.handle('slot-transfer', async (_e, req = {}) => transfer(req, getRoots()));
    ipcMain.handle('slot-places', async () => places(phoenixRoot));
    ipcMain.handle('slot-rename', async (_e, req = {}) => rename(req, getRoots()));
    ipcMain.handle('slot-list', async (_e, { dir } = {}) => {
        try { return { success: true, dir, items: listFull(dir) }; }
        catch (e) { return { success: false, dir, error: e.code === 'EPERM' || e.code === 'EACCES' ? 'No access to this folder.' : e.message }; }
    });
}

module.exports = { register, transfer, rename, inside, isSystem, listFull, places, moveRoots, sha256, defaultLabelsUnder };
