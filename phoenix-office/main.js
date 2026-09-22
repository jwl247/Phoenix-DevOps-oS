// main.js — Phoenix Office (standalone)
// UnitedSys — United Systems | jwl247 | GPL-3.0
//
// This is the SISTER product, not Phoenix DevOps OS. Cloned from
// sector2/apps/office/ (2026-09-22) so it can ship to people who don't run
// Phoenix at all — Laurie, and the people she knows who need this. Phoenix
// itself (the dashboard, packages-worker, office-notify-worker, the clone
// pool) is completely unaffected by anything in this folder: nothing here
// calls intake.sh, nothing here shares Phoenix's D1/R2/auth token. See
// README.md for the full "why a sister, not a Phoenix feature" reasoning.
//
// lib/document.js, lib/file-format.js, lib/notify.js, lib/identity.js,
// lib/tamper-guard.js are BYTE-IDENTICAL copies of sector2/apps/office's —
// those libs never had any Phoenix-pipeline coupling to begin with (their
// document identity is already content-derived, not filename-derived).
// The one thing NOT carried over on purpose: the old "seal into the clone
// pool via intake.sh" step. Documents don't belong in a system built for
// deduping source files by filename (that system's hex_id = to_hex(basename)
// collides on any two same-named files, and its 4-day tier eviction is
// aimed at a fast local cache, not permanent legal records). Instead,
// sealing a signed document PUTs it straight to this product's own worker,
// keyed by the document's own content hash — see sealToWorker() below.

const { app, BrowserWindow, ipcMain, dialog } = require('electron');
const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');

const lib = {
    document: require('./lib/document'),
    fileFormat: require('./lib/file-format'),
    identity: require('./lib/identity'),
    tamperGuard: require('./lib/tamper-guard'),
    notify: require('./lib/notify'),
    libreoffice: require('./lib/libreoffice'),
    documentHtml: require('./lib/document-html'),
};

// ── config ───────────────────────────────────────────────────────────────────
// This product's own worker — not office-notify-worker, not packages-worker.
// Own deploy, own D1, own R2, own auth secret. See worker/README.md.
const WORKER_URL = process.env.PHOENIX_OFFICE_WORKER_URL || 'https://phoenix-office-worker.phoenix-jwl.workers.dev';
const WORKER_AUTH = process.env.PHOENIX_OFFICE_AUTH || '';

let mainWindow = null;

// Standard per-user documents location — a real product's save location,
// not a dotfile-style home-dir folder. Distinct from the Phoenix dashboard's
// own ~/PhoenixOffice/ autosave path on purpose, so running both on one
// machine (as Jerry will, for testing) never collides.
function workdir() {
    const dir = path.join(app.getPath('documents'), 'Phoenix Office');
    fs.mkdirSync(dir, { recursive: true });
    return dir;
}

function templatesDir() {
    return path.join(__dirname, 'templates');
}

function listTemplates() {
    try {
        return fs.readdirSync(templatesDir()).filter(f => f.endsWith('.json')).map(f => {
            const t = JSON.parse(fs.readFileSync(path.join(templatesDir(), f), 'utf8'));
            return { template: t.template, label: t.label, fields: t.fields || [] };
        });
    } catch (_) { return []; }
}

function docPath(doc) {
    const b58 = lib.fileFormat.shortAddress(lib.fileFormat.documentIdentityHash(doc));
    return path.join(workdir(), `${b58}.office.json`);
}

// Optional D1-backed identity store — degrades cleanly (fingerprint-only
// identity, per identity.js's own design) if the worker/auth isn't set.
function authStore() {
    if (!WORKER_AUTH) return undefined;
    try { return lib.identity.workerAuthStore({ workerUrl: WORKER_URL, auth: WORKER_AUTH }); }
    catch (_) { return undefined; }
}

// Seal the finished (SIGNED) document into this product's own storage: a
// plain PUT to the worker, keyed by the document's own identity hash. No
// shell-out, no filename-based addressing, no dependency on Phoenix being
// installed at all. Best-effort — a failed seal never blocks the sign; the
// local autosaved copy is still on disk either way.
async function sealToWorker(hex, fileBytes) {
    if (!WORKER_AUTH) return { ok: false, error: 'PHOENIX_OFFICE_AUTH not set — sealed locally only' };
    try {
        const res = await fetch(`${WORKER_URL.replace(/\/+$/, '')}/documents/${encodeURIComponent(hex)}`, {
            method: 'PUT',
            headers: { Authorization: `Bearer ${WORKER_AUTH}`, 'Content-Type': 'application/json' },
            body: fileBytes,
        });
        const text = await res.text();
        if (!res.ok) return { ok: false, error: `worker ${res.status}: ${text.slice(0, 300)}` };
        return { ok: true, ...JSON.parse(text) };
    } catch (e) {
        return { ok: false, error: e.message };
    }
}

// Restricted, read-only copilot — this product runs on other people's
// machines, so it never gets --dangerously-skip-permissions or tool access,
// unlike the dashboard's internal "subscription" chain. Just a text answer.
function findClaudeCli() {
    const home = require('os').homedir();
    const candidates = [path.join(home, '.local', 'bin', 'claude.exe'), 'claude.cmd', 'claude'];
    for (const c of candidates) {
        if (c.includes(path.sep) || c.includes('/')) {
            try { if (fs.existsSync(c)) return c; } catch (_) {}
        } else {
            return c; // let PATH resolution handle bare names
        }
    }
    return null;
}

function askAI(prompt) {
    return new Promise((resolve, reject) => {
        const bin = findClaudeCli();
        if (!bin) return reject(new Error('Claude CLI not found on this machine'));
        const p = spawn(bin, ['--print', prompt], { timeout: 30000, windowsHide: true });
        let out = '', errOut = '';
        p.stdout.on('data', d => { out += d; });
        p.stderr.on('data', d => { errOut += d; });
        p.on('error', reject);
        p.on('close', code => {
            if (code === 0) resolve(out.trim());
            else reject(new Error(errOut.trim() || `claude exited ${code}`));
        });
    });
}

// ── window ───────────────────────────────────────────────────────────────────
function createWindow() {
    mainWindow = new BrowserWindow({
        width: 1400, height: 900, minWidth: 1000, minHeight: 640,
        title: 'Phoenix Office',
        backgroundColor: '#0a0c10',
        autoHideMenuBar: true,
        webPreferences: {
            preload: path.join(__dirname, 'preload.js'),
            sandbox: true,
            contextIsolation: true,
            nodeIntegration: false,
        },
    });
    mainWindow.loadFile(path.join(__dirname, 'index.html'));
    mainWindow.on('closed', () => { mainWindow = null; });
}

app.whenReady().then(() => {
    registerIpc();
    createWindow();
    app.on('activate', () => { if (BrowserWindow.getAllWindows().length === 0) createWindow(); });
});
app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit(); });

// ── IPC ──────────────────────────────────────────────────────────────────────
function registerIpc() {
    ipcMain.handle('office:whoami', async (_e, { prefer } = {}) => {
        try {
            const me = await lib.identity.resolveAuthor({ prefer: prefer || 'fingerprint', store: authStore() });
            return { ok: true, author_id: me.author_id, via: me.credential.type, source: me.source };
        } catch (e) { return { ok: false, error: e.message }; }
    });

    ipcMain.handle('office:templates', () => ({ ok: true, templates: listTemplates() }));

    ipcMain.handle('office:new', async (_e, { template, fieldNames, counterparty, authorId } = {}) => {
        try {
            let fields = fieldNames;
            if (template) {
                const t = listTemplates().find(x => x.template === template);
                if (!t) return { ok: false, error: `unknown template: ${template}` };
                fields = t.fields.slice();
            }
            if (!fields || !fields.length) return { ok: false, error: 'no fields — pick a template or name at least one field' };
            const d = lib.document.createDocument({
                fieldNames: fields,
                authorFingerprint: authorId || undefined,
                counterparty: counterparty || null,
            });
            const p = docPath(d);
            lib.fileFormat.saveOfficeFile(p, d);
            return { ok: true, document: d, path: p };
        } catch (e) { return { ok: false, error: e.message }; }
    });

    ipcMain.handle('office:autosave', (_e, { document, path: p } = {}) => {
        try {
            const target = p || docPath(document);
            lib.fileFormat.saveOfficeFile(target, document);
            return { ok: true, path: target };
        } catch (e) { return { ok: false, error: e.message }; }
    });

    ipcMain.handle('office:fill', (_e, { document, field, value, by }) => {
        const r = lib.document.fillField(document, field, value, by);
        if (!r.allowed) return { ok: false, reason: r.reason, error: r.detail };
        try { lib.fileFormat.saveOfficeFile(docPath(r.document), r.document); } catch (_) {}
        return { ok: true, document: r.document, path: docPath(r.document) };
    });

    ipcMain.handle('office:hand', (_e, { document }) => {
        try {
            const d = lib.document.handToClient(document);
            lib.fileFormat.saveOfficeFile(docPath(d), d);
            return { ok: true, document: d };
        } catch (e) { return { ok: false, error: e.message }; }
    });

    // Sign = the custody handoff that locks it. Then seal it into THIS
    // product's own storage (worker + R2), keyed by the document's own hash.
    ipcMain.handle('office:sign', async (_e, { document, by }) => {
        try {
            const d = lib.document.sign(document, by);
            const p = docPath(d);
            lib.fileFormat.saveOfficeFile(p, d);
            const hex = lib.fileFormat.documentIdentityHash(d);
            const bytes = fs.readFileSync(p);
            const sealed = await sealToWorker(hex, bytes);
            return { ok: true, document: d, path: p, sealed };
        } catch (e) { return { ok: false, error: e.message }; }
    });

    ipcMain.handle('office:reject', (_e, { document, by, reason }) => {
        try { return { ok: true, document: lib.document.reject(document, by, reason) }; }
        catch (e) { return { ok: false, error: e.message }; }
    });

    // document.js's own `supersedes` field stores the ORIGINAL's content
    // hash ({sha3,blake2b} — the tamper-detection baseline), not its
    // identity hex — those are two different hashes over two different
    // inputs (content vs. the forge event). The worker's version-history
    // chain needs the identity hex to walk supersedes_hex, so it's attached
    // here as an extra field, outside document.js's own schema. deepClone
    // in fillField/handToClient/sign preserves it through every later state
    // transition, since those clone the whole object, not a fixed field list.
    ipcMain.handle('office:change-order', (_e, { document, fieldNames, authorId }) => {
        try {
            const co = lib.document.createChangeOrder(document, fieldNames, authorId);
            co.supersedes_hex = lib.fileFormat.documentIdentityHash(document);
            return { ok: true, document: co };
        } catch (e) { return { ok: false, error: e.message }; }
    });

    ipcMain.handle('office:verify', async (_e, { document, attempt } = {}) => {
        try {
            const r = await lib.tamperGuard.checkAndAlert(document, {
                attempt,
                notifyWorkerUrl: WORKER_AUTH ? WORKER_URL : undefined,
                phoenixAuth: WORKER_AUTH,
            });
            return { ok: true, integrity: r.integrity, notified: r.notified };
        } catch (e) { return { ok: false, error: e.message }; }
    });

    ipcMain.handle('office:qr', (_e, { document }) => {
        try {
            return { ok: true, header: lib.fileFormat.buildHeader(document), footer: lib.fileFormat.buildFooter(document) };
        } catch (e) { return { ok: false, error: e.message }; }
    });

    // ── entry-screen process launcher ────────────────────────────────────────
    // "Office should move processes, not docs" (Jerry, 2026-09-22): the
    // first question is which process you're opening — Writer/Calc/Impress/
    // Draw hand off to the real LibreOffice app; only "Phoenix" goes into
    // this product's own tamper-evident template picker.
    ipcMain.handle('office:apps', () => ({ ok: true, apps: lib.libreoffice.LAUNCHABLE_APPS }));

    ipcMain.handle('office:launch-app', async (_e, { appId, filePath } = {}) => {
        try {
            const { path: sofficePath, downloaded } = await lib.libreoffice.ensureSoffice({
                workerUrl: WORKER_URL,
                auth: WORKER_AUTH,
                appDataDir: app.getPath('userData'),
                onProgress: (received, total) => {
                    if (mainWindow) mainWindow.webContents.send('office:export-progress', { received, total });
                },
            });
            const result = lib.libreoffice.launchApp({ sofficePath, appId, filePath });
            return { ok: true, ...result, downloaded };
        } catch (e) { return { ok: false, error: e.message }; }
    });

    // Real LibreOffice-driven PDF export. "Library" pattern (see
    // lib/libreoffice.js): finds an already-installed soffice, or fetches
    // this product's own portable copy from its own worker on first use —
    // never a dependency on Phoenix's own kernel/orchestration being present.
    ipcMain.handle('office:export-pdf', async (_e, { document } = {}) => {
        try {
            const { path: sofficePath, downloaded } = await lib.libreoffice.ensureSoffice({
                workerUrl: WORKER_URL,
                auth: WORKER_AUTH,
                appDataDir: app.getPath('userData'),
                onProgress: (received, total) => {
                    if (mainWindow) mainWindow.webContents.send('office:export-progress', { received, total });
                },
            });
            const html = lib.documentHtml.renderDocumentHtml(document);
            const outDir = workdir();
            const b58 = lib.fileFormat.shortAddress(lib.fileFormat.documentIdentityHash(document));
            const htmlPath = path.join(require('os').tmpdir(), `phoenix-office-${b58}.html`);
            fs.writeFileSync(htmlPath, html, 'utf8');

            const pdfPath = await lib.libreoffice.convertFile({ sofficePath, inputPath: htmlPath, outputDir: outDir, targetFormat: 'pdf' });
            try { fs.unlinkSync(htmlPath); } catch (_) {}
            return { ok: true, path: pdfPath, downloaded };
        } catch (e) {
            return { ok: false, error: e.message };
        }
    });

    // General-purpose conversion: move a file from whatever process created
    // it into whatever format the NEXT process needs — not scoped to
    // Office's own document model. E.g. a .docx from Word needed as .html
    // for a design tool, or .xlsx -> .csv for something that only reads
    // plain rows. Same "library" resolution as export-pdf: local soffice
    // first, this product's own R2 copy only if nothing local is found.
    ipcMain.handle('office:convert', async (_e, { targetFormat, filePath } = {}) => {
        try {
            if (!targetFormat) return { ok: false, error: 'targetFormat required' };
            let inputPath = filePath;
            if (!inputPath) {
                const res = await dialog.showOpenDialog(mainWindow, {
                    title: 'Choose a file to convert',
                    properties: ['openFile'],
                });
                if (res.canceled || !res.filePaths[0]) return { ok: false, canceled: true };
                inputPath = res.filePaths[0];
            }
            const { path: sofficePath, downloaded } = await lib.libreoffice.ensureSoffice({
                workerUrl: WORKER_URL,
                auth: WORKER_AUTH,
                appDataDir: app.getPath('userData'),
                onProgress: (received, total) => {
                    if (mainWindow) mainWindow.webContents.send('office:export-progress', { received, total });
                },
            });
            const outPath = await lib.libreoffice.convertFile({
                sofficePath, inputPath, outputDir: path.dirname(inputPath), targetFormat,
            });
            return { ok: true, inputPath, path: outPath, downloaded };
        } catch (e) {
            return { ok: false, error: e.message };
        }
    });

    ipcMain.handle('office:convert-formats', () => ({ ok: true, formats: lib.libreoffice.SUPPORTED_TARGET_FORMATS }));

    ipcMain.handle('office:open', async () => {
        const res = await dialog.showOpenDialog(mainWindow, {
            title: 'Open Phoenix Office document',
            defaultPath: workdir(),
            filters: [{ name: 'Office document', extensions: ['office', 'office.json', 'json'] }],
            properties: ['openFile'],
        });
        if (res.canceled || !res.filePaths[0]) return { ok: false, canceled: true };
        try {
            const loaded = lib.fileFormat.loadOfficeFile(res.filePaths[0]);
            return { ok: true, filePath: res.filePaths[0], ...loaded };
        } catch (e) { return { ok: false, error: e.message }; }
    });

    ipcMain.handle('office:open-path', (_e, { path: p } = {}) => {
        try {
            const resolved = path.resolve(p || '');
            if (!resolved.startsWith(path.resolve(workdir()))) return { ok: false, error: 'outside the Office workdir' };
            const loaded = lib.fileFormat.loadOfficeFile(resolved);
            return { ok: true, filePath: resolved, ...loaded };
        } catch (e) { return { ok: false, error: e.message }; }
    });

    ipcMain.handle('office:recent', () => {
        try {
            const dir = workdir();
            const items = fs.readdirSync(dir)
                .filter(f => f.endsWith('.office.json'))
                .map(f => {
                    const p = path.join(dir, f);
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

    // ── browse / pull from this product's own store ─────────────────────────
    // Not Phoenix's clone pool — this product's own worker + D1 + R2. Browse
    // lists what's been sealed (signed) before; reference pulls one down
    // into a local scratch dir for reference or to continue working from.
    ipcMain.handle('office:browse', async (_e, { limit, state } = {}) => {
        if (!WORKER_AUTH) return { ok: false, error: 'no worker configured (PHOENIX_OFFICE_AUTH not set)' };
        try {
            const qs = new URLSearchParams();
            if (limit) qs.set('limit', String(limit));
            if (state) qs.set('state', state);
            const res = await fetch(`${WORKER_URL.replace(/\/+$/, '')}/documents?${qs}`, {
                headers: { Authorization: `Bearer ${WORKER_AUTH}` },
            });
            if (!res.ok) return { ok: false, error: `worker ${res.status}` };
            const body = await res.json();
            return { ok: true, items: body.items || [] };
        } catch (e) { return { ok: false, error: e.message }; }
    });

    ipcMain.handle('office:reference', async (_e, { hex } = {}) => {
        if (!hex) return { ok: false, error: 'hex required' };
        if (!WORKER_AUTH) return { ok: false, error: 'no worker configured (PHOENIX_OFFICE_AUTH not set)' };
        try {
            const res = await fetch(`${WORKER_URL.replace(/\/+$/, '')}/documents/${encodeURIComponent(hex)}`, {
                headers: { Authorization: `Bearer ${WORKER_AUTH}` },
            });
            if (!res.ok) return { ok: false, error: res.status === 404 ? 'not found' : `worker ${res.status}` };
            const buf = Buffer.from(await res.arrayBuffer());
            const record = JSON.parse(buf.toString('utf8'));
            const dir = path.join(workdir(), '.references');
            fs.mkdirSync(dir, { recursive: true });
            const b58 = lib.fileFormat.shortAddress(hex);
            const p = path.join(dir, `${b58}.office.json`);
            fs.writeFileSync(p, buf);
            return { ok: true, path: p, document: record.body, header: record.header, footer: record.footer };
        } catch (e) { return { ok: false, error: e.message }; }
    });

    ipcMain.handle('office:reference-clear', () => {
        try {
            fs.rmSync(path.join(workdir(), '.references'), { recursive: true, force: true });
            return { ok: true };
        } catch (e) { return { ok: false, error: e.message }; }
    });

    // ── version history ──────────────────────────────────────────────────────
    // The supersedes_hex chain (original + every change order that followed
    // it), oldest first. Empty until the document has been signed/sealed at
    // least once — there's nothing to chain before that.
    ipcMain.handle('office:history', async (_e, { document } = {}) => {
        if (!WORKER_AUTH) return { ok: false, error: 'no worker configured (PHOENIX_OFFICE_AUTH not set)' };
        try {
            const hex = lib.fileFormat.documentIdentityHash(document);
            const res = await fetch(`${WORKER_URL.replace(/\/+$/, '')}/documents/${encodeURIComponent(hex)}/history`, {
                headers: { Authorization: `Bearer ${WORKER_AUTH}` },
            });
            if (!res.ok) return { ok: false, error: `worker ${res.status}` };
            const body = await res.json();
            return { ok: true, chain: body.chain || [] };
        } catch (e) { return { ok: false, error: e.message }; }
    });

    ipcMain.handle('office:copilot', async (_e, { document } = {}) => {
        const fieldLines = Object.entries(document.fields || {})
            .map(([k, v]) => `  ${k}: ${v === null ? '(empty)' : JSON.stringify(v)}`).join('\n');
        const cp = document.counterparty || {};
        const prompt =
            `You are the standing secretary pane inside Phoenix Office, a tamper-evident document app ` +
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
            return { ok: false, error: `Copilot offline — ${e.message}` };
        }
    });

    // Draft ONE field's value. Returns text for the UI to place in the input
    // for review — never calls fillField itself. Fields are fill-once, so a
    // draft the author doesn't want must be editable/discardable before it's
    // committed, exactly like anything they'd have typed themselves.
    ipcMain.handle('office:compose', async (_e, { document, field, instruction } = {}) => {
        if (!field) return { ok: false, error: 'field required' };
        const otherFields = Object.entries(document.fields || {})
            .filter(([k, v]) => k !== field && v !== null)
            .map(([k, v]) => `${k}: ${v}`).join('\n');
        const prompt =
            `You are drafting ONE field's content for a Phoenix Office document (a tamper-evident ` +
            `work order/invoice/inspection/change-order record). Write ONLY the value for the field ` +
            `"${field}" — no field name, no quotes, no markdown, no preamble, just the value itself. ` +
            `Keep it concise and appropriate for a real business record someone will sign.\n` +
            (instruction ? `Specific instruction from the author: ${instruction}\n` : '') +
            `Other fields already on this document, for context:\n${otherFields || '(none yet)'}\n`;
        try {
            const reply = await askAI(prompt);
            return { ok: true, value: (reply || '').trim().replace(/^["']|["']$/g, '') };
        } catch (e) {
            return { ok: false, error: `Compose unavailable — ${e.message}` };
        }
    });
}
