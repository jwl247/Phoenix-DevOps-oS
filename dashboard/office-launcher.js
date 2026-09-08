// office-launcher.js — Phoenix Office, Module 6 (2026-09-07)
// UnitedSys — United Systems | jwl247 | GPL-3.0
//
// Opens Phoenix Office in its own Electron window — same shape as
// scriptforge-launcher.js, but Office needs a real backend (filesystem +
// the lib functions + the Claude copilot), so it ships a narrow preload
// and a set of `office:*` IPC handlers. The renderer stays sandboxed:
// contextIsolation on, nodeIntegration off, no Node in the page — every
// privileged action goes through one allow-listed channel.
//
// Wire into main.js next to the other launchers:
//   require('./office-launcher').register({
//     ipcMain, BrowserWindow, dialog,
//     phoenixRoot: resolvePhoenixRoot(),
//     askAI: _runClaudeCli,               // (prompt) => Promise<string>  — optional
//   });

const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawn } = require('child_process');

let officeWindow = null;
let libs = null;         // lazily required from the repo copy
let officeRoot = null;
let phoenixRootRef = null;

// Where autosaved documents live. Not the source of truth — the clone pool
// is (see office:sign auto-intake). This is the always-persisted working copy
// so there is never a Save button to forget.
const WORKDIR = path.join(os.homedir(), 'PhoenixOffice');
const REFDIR = path.join(WORKDIR, '.references');

function bashExe() {
    const candidates = [
        'bash',
        'C:\\Program Files\\Git\\bin\\bash.exe',
        'C:\\Program Files\\Git\\usr\\bin\\bash.exe',
    ];
    for (const c of candidates) {
        if (c === 'bash') return c;
        try { if (fs.existsSync(c)) return c; } catch (_) {}
    }
    return 'bash';
}

// Forward-slash CLONEPOOL_DIR keeps intake.sh's sidecar JSON valid (a raw
// C:\ path aborts the run — see phoenix-drive-layout memory / 2026-09-06).
function intakeEnv() {
    const cp = process.env.CLONEPOOL_DIR || (process.env.HOME || os.homedir()) + '/Phoenix/clonepool';
    return {
        ...process.env,
        CLONEPOOL_DIR: cp.replace(/\\/g, '/'),
        PHOENIX_WORKER_URL: process.env.PHOENIX_WORKER_URL || 'https://packages-worker.phoenix-jwl.workers.dev',
    };
}

function loadLibs(phoenixRoot) {
    if (libs) return libs;
    phoenixRootRef = phoenixRoot;
    officeRoot = path.join(phoenixRoot, 'sector2', 'apps', 'office');
    libs = {
        document: require(path.join(officeRoot, 'lib', 'document')),
        fileFormat: require(path.join(officeRoot, 'lib', 'file-format')),
        identity: require(path.join(officeRoot, 'lib', 'identity')),
        tamperGuard: require(path.join(officeRoot, 'lib', 'tamper-guard')),
        notify: require(path.join(officeRoot, 'lib', 'notify')),
    };
    return libs;
}

function listTemplates() {
    const dir = path.join(officeRoot, 'templates');
    try {
        return fs.readdirSync(dir).filter(f => f.endsWith('.json')).map(f => {
            const t = JSON.parse(fs.readFileSync(path.join(dir, f), 'utf8'));
            return { template: t.template, label: t.label, fields: t.fields || [] };
        });
    } catch (_) { return []; }
}

// Autosave target for a document — stable for the document's whole life
// (identity is fixed at forge time).
function docPath(doc) {
    fs.mkdirSync(WORKDIR, { recursive: true });
    const b58 = libs.fileFormat.shortAddress(libs.fileFormat.documentIdentityHash(doc));
    return path.join(WORKDIR, `${b58}.office.json`);
}

// Seal the finished document into the clone pool: hex identity, custody, R2.
// This is what "saved" means. Runs bash intake.sh on the autosaved file.
function intakeToPool(filePath) {
    return new Promise((resolve) => {
        const script = path.join(phoenixRootRef, 'sector2', 'package-handler', 'intake.sh');
        if (!fs.existsSync(script)) return resolve({ ok: false, error: 'intake.sh not found' });
        const p = spawn(bashExe(), [script, filePath], { env: intakeEnv(), timeout: 45000 });
        let out = '';
        p.stdout.on('data', d => { out += d; });
        p.stderr.on('data', d => { out += d; });
        p.on('error', e => resolve({ ok: false, error: e.message }));
        p.on('close', code => {
            const hex = (out.match(/hex:\s*([0-9a-f]+)/i) || [])[1] || null;
            const ver = (out.match(/clonepool (v\d+)/) || [])[1] || null;
            resolve({ ok: code === 0, hex, version: ver, raw: out.slice(-400) });
        });
    });
}

// Optional D1-backed identity store — only if the worker + token are set.
function authStore() {
    const url = process.env.OFFICE_NOTIFY_WORKER_URL
        || 'https://office-notify-worker.phoenix-jwl.workers.dev';
    const auth = process.env.PHOENIX_AUTH;
    if (!auth) return undefined;
    try { return libs.identity.workerAuthStore({ workerUrl: url, auth }); }
    catch (_) { return undefined; }
}

function register({ ipcMain, BrowserWindow, dialog, phoenixRoot, askAI }) {
    const L = () => loadLibs(phoenixRoot);

    // ── window ───────────────────────────────────────────────────────────────
    ipcMain.handle('launch-office', async () => {
        const indexPath = path.join(phoenixRoot, 'sector2', 'apps', 'office', 'index.html');
        if (!fs.existsSync(indexPath)) {
            return { success: false, error: `Phoenix Office not found at ${indexPath}` };
        }
        if (officeWindow && !officeWindow.isDestroyed()) {
            officeWindow.show(); officeWindow.focus();
            return { success: true, refocused: true };
        }
        officeWindow = new BrowserWindow({
            width: 1400, height: 900, minWidth: 1000, minHeight: 640,
            title: 'Phoenix Office',
            backgroundColor: '#0a0c10',
            autoHideMenuBar: true,
            webPreferences: {
                preload: path.join(phoenixRoot, 'sector2', 'apps', 'office', 'preload.js'),
                sandbox: true,
                contextIsolation: true,
                nodeIntegration: false,
            },
        });
        officeWindow.loadFile(indexPath);
        officeWindow.on('closed', () => { officeWindow = null; });
        return { success: true, refocused: false };
    });

    // ── identity ─────────────────────────────────────────────────────────────
    ipcMain.handle('office:whoami', async (_e, { prefer } = {}) => {
        try {
            const me = await L().identity.resolveAuthor({ prefer: prefer || 'fingerprint', store: authStore() });
            return { ok: true, author_id: me.author_id, via: me.credential.type, source: me.source };
        } catch (e) { return { ok: false, error: e.message }; }
    });

    // ── templates ────────────────────────────────────────────────────────────
    ipcMain.handle('office:templates', () => { L(); return { ok: true, templates: listTemplates() }; });

    // ── document state machine ───────────────────────────────────────────────
    ipcMain.handle('office:new', async (_e, { template, fieldNames, counterparty, authorId } = {}) => {
        try {
            L();
            let fields = fieldNames;
            if (template) {
                const t = listTemplates().find(x => x.template === template);
                if (!t) return { ok: false, error: `unknown template: ${template}` };
                fields = t.fields.slice();
            }
            if (!fields || !fields.length) return { ok: false, error: 'no fields — pick a template or name at least one field' };
            const d = libs.document.createDocument({
                fieldNames: fields,
                authorFingerprint: authorId || undefined,
                counterparty: counterparty || null,
            });
            const p = docPath(d);
            libs.fileFormat.saveOfficeFile(p, d);   // persisted from the first moment
            return { ok: true, document: d, path: p };
        } catch (e) { return { ok: false, error: e.message }; }
    });

    // Autosave — the only "save" there is. No dialog, no button.
    ipcMain.handle('office:autosave', (_e, { document, path: p } = {}) => {
        try {
            L();
            const target = p || docPath(document);
            libs.fileFormat.saveOfficeFile(target, document);
            return { ok: true, path: target };
        } catch (e) { return { ok: false, error: e.message }; }
    });

    ipcMain.handle('office:fill', (_e, { document, field, value, by }) => {
        L();
        const r = libs.document.fillField(document, field, value, by);
        if (!r.allowed) return { ok: false, reason: r.reason, error: r.detail };
        try { libs.fileFormat.saveOfficeFile(docPath(r.document), r.document); } catch (_) {}
        return { ok: true, document: r.document, path: docPath(r.document) };
    });

    ipcMain.handle('office:hand', (_e, { document }) => {
        try {
            L();
            const d = libs.document.handToClient(document);
            libs.fileFormat.saveOfficeFile(docPath(d), d);
            return { ok: true, document: d };
        } catch (e) { return { ok: false, error: e.message }; }
    });

    // Sign = the custody handoff that locks it. Then SEAL it into the clone
    // pool (hex identity, custody ledger, R2). "Saved" means the pool has it.
    ipcMain.handle('office:sign', async (_e, { document, by }) => {
        try {
            L();
            const d = libs.document.sign(document, by);
            const p = docPath(d);
            libs.fileFormat.saveOfficeFile(p, d);
            const sealed = await intakeToPool(p);   // best-effort — never blocks the sign
            return { ok: true, document: d, path: p, sealed };
        } catch (e) { return { ok: false, error: e.message }; }
    });

    ipcMain.handle('office:reject', (_e, { document, by, reason }) => {
        try { return { ok: true, document: L().document.reject(document, by, reason) }; }
        catch (e) { return { ok: false, error: e.message }; }
    });

    ipcMain.handle('office:change-order', (_e, { document, fieldNames, authorId }) => {
        try { return { ok: true, document: L().document.createChangeOrder(document, fieldNames, authorId) }; }
        catch (e) { return { ok: false, error: e.message }; }
    });

    // ── integrity + notify ───────────────────────────────────────────────────
    ipcMain.handle('office:verify', async (_e, { document, attempt } = {}) => {
        const workerUrl = process.env.OFFICE_NOTIFY_WORKER_URL
            || 'https://office-notify-worker.phoenix-jwl.workers.dev';
        const phoenixAuth = process.env.PHOENIX_AUTH;
        try {
            const r = await L().tamperGuard.checkAndAlert(document, {
                attempt,
                notifyWorkerUrl: phoenixAuth ? workerUrl : undefined,
                phoenixAuth,
            });
            return { ok: true, integrity: r.integrity, notified: r.notified };
        } catch (e) { return { ok: false, error: e.message }; }
    });

    // ── QR strings ───────────────────────────────────────────────────────────
    ipcMain.handle('office:qr', (_e, { document }) => {
        try {
            return {
                ok: true,
                header: L().fileFormat.buildHeader(document),
                footer: L().fileFormat.buildFooter(document),
            };
        } catch (e) { return { ok: false, error: e.message }; }
    });

    // ── open / recent ────────────────────────────────────────────────────────
    ipcMain.handle('office:open', async () => {
        const res = await dialog.showOpenDialog(officeWindow, {
            title: 'Open Phoenix Office document',
            defaultPath: WORKDIR,
            filters: [{ name: 'Office document', extensions: ['office', 'office.json', 'json'] }],
            properties: ['openFile'],
        });
        if (res.canceled || !res.filePaths[0]) return { ok: false, canceled: true };
        try {
            const loaded = L().fileFormat.loadOfficeFile(res.filePaths[0]);
            return { ok: true, filePath: res.filePaths[0], ...loaded };
        } catch (e) { return { ok: false, error: e.message }; }
    });

    // Reopen a specific autosaved file by path (Recent dropdown). Restricted
    // to the Office workdir so the renderer can't ask main to read anywhere.
    ipcMain.handle('office:open-path', (_e, { path: p } = {}) => {
        try {
            L();
            const resolved = path.resolve(p || '');
            if (!resolved.startsWith(path.resolve(WORKDIR))) return { ok: false, error: 'outside the Office workdir' };
            const loaded = libs.fileFormat.loadOfficeFile(resolved);
            return { ok: true, filePath: resolved, ...loaded };
        } catch (e) { return { ok: false, error: e.message }; }
    });

    // Recent autosaved documents in the workdir (for a one-click "reopen").
    ipcMain.handle('office:recent', () => {
        try {
            fs.mkdirSync(WORKDIR, { recursive: true });
            const items = fs.readdirSync(WORKDIR)
                .filter(f => f.endsWith('.office.json'))
                .map(f => {
                    const p = path.join(WORKDIR, f);
                    const st = fs.statSync(p);
                    let state = '?', title = f;
                    try {
                        const d = JSON.parse(fs.readFileSync(p, 'utf8'));
                        const body = d.body || d;
                        state = body.state || '?';
                        title = Object.values(body.fields || {}).find(v => v) || f;
                    } catch (_) {}
                    return { path: p, name: f, title, state, mtime: st.mtimeMs };
                })
                .sort((a, b) => b.mtime - a.mtime);
            return { ok: true, items };
        } catch (e) { return { ok: false, error: e.message }; }
    });

    // ── reference-pull from the clone pool ───────────────────────────────────
    // "I need to reference these documents" -> Phoenix clones them from the
    // pool into a scratch dir. Use them, delete them freely — the pool is
    // the source of truth.
    ipcMain.handle('office:reference', async (_e, { names } = {}) => {
        L();
        if (!Array.isArray(names) || !names.length) return { ok: false, error: 'give one or more document names' };
        fs.mkdirSync(REFDIR, { recursive: true });
        const script = path.join(phoenixRootRef, 'sector2', 'package-handler', 'intake.sh');
        const pulled = [];
        for (const raw of names) {
            const name = String(raw).trim();
            if (!name) continue;
            const got = await new Promise((resolve) => {
                const p = spawn(bashExe(), [script, 'clone', name], { cwd: REFDIR, env: intakeEnv(), timeout: 30000 });
                let out = '';
                p.stdout.on('data', d => { out += d; });
                p.stderr.on('data', d => { out += d; });
                p.on('error', () => resolve(null));
                p.on('close', () => {
                    const hit = fs.existsSync(path.join(REFDIR, name)) ? path.join(REFDIR, name) : null;
                    resolve(hit ? { name, path: hit } : { name, error: (out.match(/\[intake:MISS\][^\n]*/) || ['not found in the pool'])[0] });
                });
            });
            if (got) pulled.push(got);
        }
        return { ok: true, dir: REFDIR, pulled };
    });

    ipcMain.handle('office:reference-clear', () => {
        try { fs.rmSync(REFDIR, { recursive: true, force: true }); return { ok: true }; }
        catch (e) { return { ok: false, error: e.message }; }
    });

    // ── Claude copilot ───────────────────────────────────────────────────────
    ipcMain.handle('office:copilot', async (_e, { document } = {}) => {
        if (typeof askAI !== 'function') {
            return { ok: false, error: 'Copilot offline — no AI backend wired. Set up AI in the dashboard.' };
        }
        const fieldLines = Object.entries(document.fields || {})
            .map(([k, v]) => `  ${k}: ${v === null ? '(empty)' : JSON.stringify(v)}`).join('\n');
        const cp = document.counterparty || {};
        const prompt =
            `You are the standing copilot pane inside Phoenix Office, a tamper-evident document app ` +
            `(work orders, invoices, filled forms). The document below is being filled out. Give the author ` +
            `2-4 short, concrete suggestions: fields that look missing or inconsistent, a line item that ` +
            `seems absent, a total that doesn't add up, or contact info needed for the tamper-notification ` +
            `path (needs phone+carrier OR email). Be terse. Bullet points. No preamble.\n\n` +
            `STATE: ${document.state}\n` +
            `COUNTERPARTY CONTACT: phone=${cp.phone || '-'} carrier=${cp.carrier || '-'} email=${cp.email || '-'}\n` +
            `FIELDS:\n${fieldLines}\n`;
        try {
            const reply = await askAI(prompt);
            return { ok: true, suggestions: (reply || '').trim() };
        } catch (e) {
            return { ok: false, error: e.message };
        }
    });
}

module.exports = { register };
