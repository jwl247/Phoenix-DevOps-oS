#!/usr/bin/env node
// fix-electron.js — Phoenix Office
//
// electron@28.3.3's own postinstall (node_modules/electron/install.js)
// silently fails to extract its binary on this environment — confirmed
// live 2026-09-22 on Node v26.7.0: it exits 0, prints nothing, and never
// writes dist/ or path.txt, even after npm's newer install-scripts gate
// (`allowScripts`, now set in package.json) correctly lets it run. Root
// cause not fully isolated (most likely an @electron/get/extract-zip
// incompatibility with this Node version) — not worth blocking a real
// install on chasing further. This is the self-healing fallback: runs
// automatically after every `npm install` (see package.json's
// "postinstall"), and repairs the electron binary if it's missing —
// from a local download cache first (fast, no network), or a direct
// GitHub-releases download as a last resort for a genuinely fresh
// machine (e.g. Laurie's, which has never had Electron installed before
// and so has nothing cached).
//
// Never fatal to `npm install` itself — if this fails, it logs why and
// exits 0; the only consequence is `npm start` won't work until fixed,
// same as the underlying bug it's working around would have caused anyway.

const fs = require('fs');
const path = require('path');
const os = require('os');
const https = require('https');
const { execFileSync } = require('child_process');

const ELECTRON_DIR = path.join(__dirname, '..', 'node_modules', 'electron');

function platformBinaryName() {
    if (process.platform === 'win32') return 'electron.exe';
    if (process.platform === 'darwin') return 'Electron.app/Contents/MacOS/Electron';
    return 'electron';
}

function alreadyInstalled(version) {
    try {
        const dv = fs.readFileSync(path.join(ELECTRON_DIR, 'dist', 'version'), 'utf8').replace(/^v/, '');
        const pt = fs.readFileSync(path.join(ELECTRON_DIR, 'path.txt'), 'utf8');
        if (dv !== version) return false;
        if (pt !== platformBinaryName()) return false;
        return fs.existsSync(path.join(ELECTRON_DIR, 'dist', platformBinaryName()));
    } catch (_) {
        return false;
    }
}

function writeMarkers(version) {
    // No trailing newline — a real bug this session hit the hard way:
    // `echo "x" > path.txt` embeds a \n that then gets baked straight
    // into the spawn() path electron/index.js hands to child_process.
    fs.writeFileSync(path.join(ELECTRON_DIR, 'path.txt'), platformBinaryName());
    fs.writeFileSync(path.join(ELECTRON_DIR, 'dist', 'version'), `v${version}`);
}

function cacheDirCandidates() {
    if (process.env.electron_config_cache) return [process.env.electron_config_cache];
    if (process.platform === 'win32') return [path.join(os.homedir(), 'AppData', 'Local', 'electron', 'Cache')];
    if (process.platform === 'darwin') return [path.join(os.homedir(), 'Library', 'Caches', 'electron')];
    return [path.join(os.homedir(), '.cache', 'electron')];
}

function findCachedZip(zipName) {
    for (const dir of cacheDirCandidates()) {
        if (!fs.existsSync(dir)) continue;
        for (const sub of fs.readdirSync(dir)) {
            const candidate = path.join(dir, sub, zipName);
            if (fs.existsSync(candidate)) return candidate;
        }
    }
    return null;
}

// Shelling out to a real OS unzip tool instead of the `extract-zip` npm
// package — confirmed live 2026-09-22 that extract-zip itself silently
// no-ops on this Node version (v26.7.0): no error, no extraction, just a
// resolved promise that did nothing. That's the actual root cause behind
// electron's own broken postinstall too, not something specific to
// electron's wrapper code around it. A real system unzip (verified
// working via Git Bash's `unzip -t` during diagnosis) sidesteps the
// broken JS dependency entirely.
function extractZip(zipPath, destDir) {
    if (process.platform === 'win32') {
        // The bare command name 'tar' is genuinely ambiguous on this OS:
        // if a shell with Git-for-Windows/MSYS tools earlier on PATH
        // invokes this script (confirmed live 2026-09-22), 'tar' resolves
        // to MSYS's tar instead of Windows' own System32\tar.exe (real
        // bsdtar, handles .zip natively) — MSYS tar then misparses a
        // Windows drive-letter path like "C:\Users\..." as a remote-host
        // spec ("cannot connect to C: resolve failed"). Referencing the
        // native binary by full path sidesteps PATH order entirely.
        const nativeTar = path.join(process.env.SystemRoot || 'C:\\Windows', 'System32', 'tar.exe');
        // -m: don't try to restore each file's original modification time.
        // Without it, bsdtar extracts every file correctly but still exits
        // non-zero ("Can't restore time: Invalid argument" per file,
        // confirmed live 2026-09-22 against this exact electron zip) —
        // which would make this look like a real failure when it isn't.
        execFileSync(nativeTar, ['-xf', zipPath, '-C', destDir, '-m'], { stdio: 'inherit' });
        return;
    }
    try {
        execFileSync('tar', ['-xf', zipPath, '-C', destDir], { stdio: 'inherit' });
        return;
    } catch (tarErr) { /* fall through to unzip/ditto below */ }
    try {
        execFileSync('unzip', ['-q', '-o', zipPath, '-d', destDir], { stdio: 'inherit' });
    } catch (_) {
        // macOS ships ditto everywhere unzip might be missing/old
        execFileSync('ditto', ['-xk', zipPath, destDir], { stdio: 'inherit' });
    }
}

function download(url, destPath, redirects = 0) {
    return new Promise((resolve, reject) => {
        if (redirects > 5) return reject(new Error('too many redirects'));
        const file = fs.createWriteStream(destPath);
        https.get(url, { headers: { 'User-Agent': 'phoenix-office-electron-fix' } }, (res) => {
            if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
                file.close();
                fs.unlinkSync(destPath);
                return download(res.headers.location, destPath, redirects + 1).then(resolve, reject);
            }
            if (res.statusCode !== 200) {
                file.close();
                return reject(new Error(`download failed: HTTP ${res.statusCode} for ${url}`));
            }
            res.pipe(file);
            file.on('finish', () => file.close(resolve));
        }).on('error', reject);
    });
}

async function main() {
    const version = require(path.join(ELECTRON_DIR, 'package.json')).version;
    if (alreadyInstalled(version)) {
        console.log('[fix-electron] electron already installed correctly, nothing to do');
        return;
    }

    const zipName = `electron-v${version}-${process.platform}-${process.arch}.zip`;
    let zipPath = findCachedZip(zipName);
    if (zipPath) {
        console.log(`[fix-electron] repairing from local cache: ${zipName}`);
    } else {
        console.log(`[fix-electron] no local cache for ${zipName} — downloading from GitHub releases`);
        zipPath = path.join(os.tmpdir(), zipName);
        await download(`https://github.com/electron/electron/releases/download/v${version}/${zipName}`, zipPath);
    }

    const distDir = path.join(ELECTRON_DIR, 'dist');
    fs.rmSync(distDir, { recursive: true, force: true });
    fs.mkdirSync(distDir, { recursive: true });

    extractZip(zipPath, distDir);

    writeMarkers(version);

    if (!fs.existsSync(path.join(distDir, platformBinaryName()))) {
        throw new Error('extraction completed but the electron binary is still missing');
    }
    console.log('[fix-electron] electron repaired successfully');
}

main().catch(e => {
    console.error('[fix-electron] could not auto-repair electron:', e.message);
    console.error('[fix-electron] `npm start` will not work until this is resolved — not blocking npm install itself.');
    process.exit(0);
});
