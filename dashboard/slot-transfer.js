// slot-transfer.js
// Drag and drop between the folder slots across the top of the dashboard.
// Every request is checked here in the main process, not in the page:
//   - The destination must be inside one of the places (Home, Root = every drive,
//     Phoenix) or one of your slot folders.
//   - Items dragged between slots must come from inside a slot. Files dropped in
//     from Explorer can come from anywhere, but are only ever COPIED.
//   - Nothing is overwritten. If the name is taken, that item is skipped and you're told.
//   - A folder can't go inside itself.
//   - Nothing is ever MOVED out of breach_coms4 (the master vault never loses a file).
//   - The operating system's own folders (C:\Windows, Program Files, ProgramData,
//     /bin /etc /usr ...) are read-only here: copy out of them, never into or out by move.
//     A drive root itself can't be moved.
//   - A move across drives is copy, verify (size + SHA-256 of every file), then
//     remove the original. If the check fails, the original stays where it was.
//
// Wire into main.js:
//   require('./slot-transfer').register({ ipcMain, getSlots, phoenixRoot });   // getSlots() -> the 6 slot folders

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const os = require('os');

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

function sha256(file) {
    return crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
}

// Every file under `p` (or p itself) as relative path -> {size, sha}.
function fingerprint(p) {
    const out = new Map();
    const walk = (abs, rel) => {
        const st = fs.lstatSync(abs);
        if (st.isDirectory()) for (const n of fs.readdirSync(abs)) walk(path.join(abs, n), path.join(rel, n));
        else if (st.isFile()) out.set(rel, `${st.size}:${sha256(abs)}`);
        else out.set(rel, `link:${st.isSymbolicLink() ? fs.readlinkSync(abs) : 'other'}`);
    };
    walk(p, '.');
    return out;
}

function sameTree(a, b) {
    const fa = fingerprint(a), fb = fingerprint(b);
    if (fa.size !== fb.size) return false;
    for (const [k, v] of fa) if (fb.get(k) !== v) return false;
    return true;
}

/**
 * sources:  absolute paths
 * toDir:    absolute destination folder
 * mode:     'move' | 'copy'
 * external: true = dropped in from outside the dashboard (forced to copy)
 * slots:    the slot root folders (from the saved slot state)
 */
function transfer({ sources, toDir, mode, external }, slots) {   // slots = every allowed root (places + slots)
    const roots = (slots || []).filter(Boolean).map(real);
    if (!roots.length) return { success: false, error: 'No slot folders set.' };
    if (!Array.isArray(sources) || !sources.length) return { success: false, error: 'Nothing to transfer.' };
    if (typeof toDir !== 'string' || !fs.existsSync(toDir) || !fs.statSync(toDir).isDirectory()) {
        return { success: false, error: `Destination is not a folder: ${toDir}` };
    }
    const dest = real(toDir);
    if (!roots.some((r) => inside(dest, r))) return { success: false, error: 'Destination is not inside one of your places or slot folders.' };
    if (isSystem(dest)) return { success: false, error: `${dest} is an operating-system folder — nothing is put there from the dashboard.` };
    const how = external ? 'copy' : (mode === 'copy' ? 'copy' : 'move');

    const done = [], skipped = [];
    for (const src0 of sources) {
        const name = path.basename(String(src0));
        if (typeof src0 !== 'string' || !fs.existsSync(src0)) { skipped.push({ name, reason: 'no longer exists' }); continue; }
        const src = real(src0);
        if (!external && !roots.some((r) => inside(src, r))) { skipped.push({ name, reason: 'not from a slot folder' }); continue; }
        if (path.dirname(src) === dest) { skipped.push({ name, reason: 'already in that folder' }); continue; }
        const isDir = fs.statSync(src).isDirectory();
        if (isDir && inside(dest, src)) { skipped.push({ name, reason: "a folder can't go inside itself" }); continue; }
        const target = path.join(dest, name);
        if (fs.existsSync(target)) { skipped.push({ name, reason: `"${name}" already exists there — nothing overwritten` }); continue; }
        if (how === 'move' && PROTECTED_MOVE.test(src)) { skipped.push({ name, reason: 'breach_coms4 is the master vault — copy from it, never move' }); continue; }
        if (how === 'move' && (isSystem(src) || isDriveRoot(src))) { skipped.push({ name, reason: 'operating-system folder — copy it, never move it' }); continue; }
        try {
            if (how === 'move') {
                try {
                    fs.renameSync(src, target);                       // same drive: instant, atomic
                } catch (e) {
                    if (e.code !== 'EXDEV') throw e;
                    fs.cpSync(src, target, { recursive: true, errorOnExist: true, force: false, preserveTimestamps: true });
                    if (!sameTree(src, target)) {
                        fs.rmSync(target, { recursive: true, force: true });
                        throw new Error('copy did not verify — original left in place');
                    }
                    fs.rmSync(src, { recursive: true });
                }
            } else {
                fs.cpSync(src, target, { recursive: true, errorOnExist: true, force: false, preserveTimestamps: true });
            }
            done.push({ name, to: target });
        } catch (e) {
            skipped.push({ name, reason: e.message });
        }
    }
    return { success: done.length > 0 || skipped.length === 0, mode: how, done, skipped };
}

// Rename in place. Same checks as a move: inside a place or slot, never over an
// existing name, never in breach_coms4 or an OS folder, a plain name only (no / or \).
function rename({ path: src0, newName }, roots0) {
    const roots = (roots0 || []).filter(Boolean).map(real);
    if (typeof src0 !== 'string' || !fs.existsSync(src0)) return { success: false, error: 'That item no longer exists.' };
    const name = String(newName || '').trim();
    if (!name || name === '.' || name === '..' || /[\\/]/.test(name) || (process.platform === 'win32' && /[<>:"|?*]/.test(name))) {
        return { success: false, error: 'Not a valid name.' };
    }
    const src = real(src0);
    if (!roots.some((r) => inside(src, r))) return { success: false, error: 'Not inside one of your places or slot folders.' };
    if (PROTECTED_MOVE.test(src)) return { success: false, error: 'breach_coms4 is the master vault — nothing is renamed there.' };
    if (isSystem(src) || isDriveRoot(src)) return { success: false, error: 'Operating-system folder — not renamed.' };
    const target = path.join(path.dirname(src), name);
    if (target === src) return { success: true, path: src };
    // A case-only change (a.txt -> A.txt) on Windows is the same file, not a clash.
    const caseOnly = target.toLowerCase() === src.toLowerCase();
    if (fs.existsSync(target) && !caseOnly) return { success: false, error: `"${name}" already exists there — nothing overwritten.` };
    try { fs.renameSync(src, target); } catch (e) { return { success: false, error: e.message }; }
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
function places(phoenixRoot) {
    const list = [
        { key: 'home', label: 'HOME', path: os.homedir() },
        { key: 'root', label: 'ROOT', path: process.platform === 'win32' ? null : '/', drives: drives() },
    ];
    if (phoenixRoot && fs.existsSync(phoenixRoot)) list.push({ key: 'phoenix', label: 'PHOENIX', path: phoenixRoot });
    return list;
}

function register({ ipcMain, getSlots, phoenixRoot }) {
    const getRoots = () => [...places(phoenixRoot).flatMap((p) => p.path ? [p.path] : p.drives), ...(getSlots() || [])];
    ipcMain.handle('slot-transfer', async (_e, req = {}) => transfer(req, getRoots()));
    ipcMain.handle('slot-places', async () => places(phoenixRoot));
    ipcMain.handle('slot-rename', async (_e, req = {}) => rename(req, getRoots()));
    ipcMain.handle('slot-list', async (_e, { dir } = {}) => {
        try { return { success: true, dir, items: listFull(dir) }; }
        catch (e) { return { success: false, dir, error: e.code === 'EPERM' || e.code === 'EACCES' ? 'No access to this folder.' : e.message }; }
    });
}

module.exports = { register, transfer, rename, inside, isSystem, listFull, places };
