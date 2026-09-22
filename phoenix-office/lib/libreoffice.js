// libreoffice.js — Phoenix Office (standalone)
//
// "Library" pattern, not "universal kernel": a fixed, named runtime asset
// the app locates once and caches locally, never a live dependency on
// Phoenix being installed or running. Two ways this resolves:
//   1. Already installed on this machine (checked first, no network at all).
//   2. Not installed -> fetched ONCE from this product's own R2
//      (GET /runtime/libreoffice-portable-win64.zip), extracted into a
//      local cache dir, and reused from disk on every later run.
// Either way, once resolved, conversion is a plain local subprocess call —
// no daemon, no Phoenix kernel, no network per-conversion.

const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawn } = require('child_process');

const RUNTIME_ASSET_NAME = 'libreoffice-portable-win64.zip';

// Common install locations, checked before anything is downloaded.
function knownInstallPaths() {
    if (process.platform === 'win32') {
        return [
            'C:\\Program Files\\LibreOffice\\program\\soffice.exe',
            'C:\\Program Files (x86)\\LibreOffice\\program\\soffice.exe',
        ];
    }
    if (process.platform === 'darwin') {
        return ['/Applications/LibreOffice.app/Contents/MacOS/soffice'];
    }
    return ['/usr/bin/soffice', '/usr/lib/libreoffice/program/soffice'];
}

function cacheDir(appDataDir) {
    const dir = path.join(appDataDir, 'libreoffice-portable');
    fs.mkdirSync(dir, { recursive: true });
    return dir;
}

function cachedSofficePath(appDataDir) {
    const dir = cacheDir(appDataDir);
    const candidates = process.platform === 'win32'
        ? [path.join(dir, 'program', 'soffice.exe')]
        : [path.join(dir, 'program', 'soffice')];
    return candidates.find(p => { try { return fs.existsSync(p); } catch (_) { return false; } }) || null;
}

// Find a working soffice binary without touching the network. Checks known
// installs first, then a previously-extracted local cache.
function findLocalSoffice(appDataDir) {
    for (const p of knownInstallPaths()) {
        try { if (fs.existsSync(p)) return p; } catch (_) {}
    }
    return cachedSofficePath(appDataDir);
}

// Download + extract the runtime asset from this product's own worker.
// onProgress(receivedBytes, totalBytes) is called as chunks arrive — real
// progress, not a spinner, since this is a genuinely large one-time fetch.
async function fetchAndExtract({ workerUrl, auth, appDataDir, onProgress }) {
    if (process.platform !== 'win32') {
        throw new Error(`no runtime asset packaged for platform "${process.platform}" yet — install LibreOffice manually`);
    }
    const base = String(workerUrl).replace(/\/+$/, '');
    const res = await fetch(`${base}/runtime/${RUNTIME_ASSET_NAME}`, {
        headers: { Authorization: `Bearer ${auth}` },
    });
    if (!res.ok) throw new Error(`runtime fetch failed: ${res.status}`);
    const total = Number(res.headers.get('content-length')) || 0;

    const tmpZip = path.join(os.tmpdir(), `${RUNTIME_ASSET_NAME}.${process.pid}`);
    const fileStream = fs.createWriteStream(tmpZip);
    let received = 0;
    const reader = res.body.getReader();
    for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        received += value.byteLength;
        fileStream.write(Buffer.from(value));
        if (typeof onProgress === 'function') onProgress(received, total);
    }
    await new Promise((resolve, reject) => fileStream.end(err => err ? reject(err) : resolve()));

    const dir = cacheDir(appDataDir);
    await new Promise((resolve, reject) => {
        const p = spawn('powershell.exe', [
            '-NoProfile', '-NonInteractive', '-Command',
            `Expand-Archive -Path "${tmpZip}" -DestinationPath "${dir}" -Force`,
        ], { windowsHide: true });
        let errOut = '';
        p.stderr.on('data', d => { errOut += d; });
        p.on('error', reject);
        p.on('close', code => code === 0 ? resolve() : reject(new Error(`extract failed: ${errOut.trim() || code}`)));
    });
    try { fs.unlinkSync(tmpZip); } catch (_) {}

    const found = cachedSofficePath(appDataDir);
    if (!found) throw new Error('extracted runtime, but soffice was not where expected — layout may have changed');
    return found;
}

// The single entry point: resolve a working soffice path, downloading only
// if genuinely nothing local is usable. Never silently no-ops — throws with
// a clear reason on failure, since a fake "conversion worked" would be
// exactly the kind of demo this codebase's standing rule forbids.
async function ensureSoffice({ workerUrl, auth, appDataDir, onProgress } = {}) {
    const local = findLocalSoffice(appDataDir);
    if (local) return { path: local, downloaded: false };
    if (!workerUrl || !auth) {
        throw new Error('LibreOffice is not installed and no runtime worker is configured (PHOENIX_OFFICE_AUTH) to fetch it');
    }
    const fetched = await fetchAndExtract({ workerUrl, auth, appDataDir, onProgress });
    return { path: fetched, downloaded: true };
}

// General-purpose conversion: move a file from one process's format to
// another's. Not scoped to Office's own document model — this takes any
// file soffice can open (docx, odt, xlsx, pptx, html, csv, txt, rtf, …) and
// converts it into any of the formats below, for use in a different
// process (e.g. Word -> a design tool that only takes HTML/PDF/ODT). A
// curated whitelist, not passthrough of an arbitrary filter string — every
// token here is one soffice actually recognizes without extra filter
// disambiguation.
const SUPPORTED_TARGET_FORMATS = ['pdf', 'docx', 'odt', 'rtf', 'txt', 'html', 'xlsx', 'ods', 'csv', 'pptx', 'odp', 'png'];

function convertFile({ sofficePath, inputPath, outputDir, targetFormat }) {
    if (!SUPPORTED_TARGET_FORMATS.includes(targetFormat)) {
        throw new Error(`unsupported target format "${targetFormat}" — supported: ${SUPPORTED_TARGET_FORMATS.join(', ')}`);
    }
    if (!fs.existsSync(inputPath)) throw new Error(`input file not found: ${inputPath}`);
    fs.mkdirSync(outputDir, { recursive: true });

    return new Promise((resolve, reject) => {
        const p = spawn(sofficePath, ['--headless', '--convert-to', targetFormat, '--outdir', outputDir, inputPath], { windowsHide: true, timeout: 90000 });
        let errOut = '';
        p.stderr.on('data', d => { errOut += d; });
        p.on('error', reject);
        p.on('close', code => {
            if (code !== 0) return reject(new Error(errOut.trim() || `soffice exited ${code}`));
            const base = path.basename(inputPath, path.extname(inputPath));
            const outPath = path.join(outputDir, `${base}.${targetFormat}`);
            if (!fs.existsSync(outPath)) return reject(new Error('conversion ran but the expected output file was not produced'));
            resolve(outPath);
        });
    });
}

// The real LibreOffice apps this product can hand off to — the entry
// screen's "what process are you opening" choices, everything soffice can
// launch directly into via a blank/new document. Base and Math deliberately
// left out for now: Base needs its own DB-engine setup wizard and doesn't
// fit "launch straight into a new document," and Math is a niche
// formula-editor most Office users won't reach for — flag if wanted, easy
// to add (same shape as the four below).
const LAUNCHABLE_APPS = [
    { id: 'writer', flag: '--writer', label: 'Writer', kind: 'text document', ext: 'odt' },
    { id: 'calc', flag: '--calc', label: 'Calc', kind: 'spreadsheet', ext: 'ods' },
    { id: 'impress', flag: '--impress', label: 'Impress', kind: 'slides', ext: 'odp' },
    { id: 'draw', flag: '--draw', label: 'Draw', kind: 'design / diagramming', ext: 'odg' },
];

// Launch a real LibreOffice app in its own window — detached, so it's a
// genuinely independent process, not a child this app waits on or that
// dies when this app closes. filePath is optional: omit it to open a blank
// new document of that app's kind.
function launchApp({ sofficePath, appId, filePath }) {
    const app = LAUNCHABLE_APPS.find(a => a.id === appId);
    if (!app) throw new Error(`unknown app "${appId}" — supported: ${LAUNCHABLE_APPS.map(a => a.id).join(', ')}`);
    const args = [app.flag];
    if (filePath) args.push(filePath);
    const child = spawn(sofficePath, args, { detached: true, stdio: 'ignore', windowsHide: false });
    child.unref();
    return { app: app.id, label: app.label };
}

module.exports = {
    ensureSoffice, findLocalSoffice, convertFile, launchApp,
    SUPPORTED_TARGET_FORMATS, LAUNCHABLE_APPS, RUNTIME_ASSET_NAME,
};
