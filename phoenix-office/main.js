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
    project: require('./lib/project'),
    phaseHtml: require('./lib/phase-html'),
    bidFactors: require('./lib/bid-factors'),
};

const aiProvider = require('./lib/ai-provider');
const { createAgentTools } = require('./lib/agent-tools');
const { createAgentLoop } = require('./lib/agent-loop');

// One live Secretariat-agent session at a time — this is a single-window
// desktop app, not a multi-tenant server. Reset on office:agent-reset or
// a fresh app launch. Holds the model's message history + whichever
// document it's currently working, so a deviation-tier tool can pause
// mid-turn and resume later without losing context.
let agentSession = null;

// ── config ───────────────────────────────────────────────────────────────────
// This product's own worker — not office-notify-worker, not packages-worker.
// Own deploy, own D1, own R2, own auth secret. See worker/README.md.
const WORKER_URL = process.env.PHOENIX_OFFICE_WORKER_URL || 'https://phoenix-office-worker.phoenix-jwl.workers.dev';
const WORKER_AUTH = process.env.PHOENIX_OFFICE_AUTH || '';
const GOOGLE_CLIENT_ID = process.env.PHOENIX_OFFICE_GOOGLE_CLIENT_ID || '';
const GOOGLE_CLIENT_SECRET = process.env.PHOENIX_OFFICE_GOOGLE_CLIENT_SECRET || '';

let mainWindow = null;
let splashWindow = null;

// Session-scoped only, never written to disk — the whole point of requiring
// Google identity for Sign/Legal-hold is a real verified person, re-proven
// each app launch, not a cached credential sitting in a file. Cleared by
// simply never persisting it in the first place.
let googleIdentity = null;      // { idToken, email, sub } once a device-flow completes
let pendingDeviceCode = null;   // in flight between office:google-signin-start and -poll

// A minimum on-screen time for the splash so it reads as a real branded
// loading moment rather than a one-frame flash — this app loads fast
// enough locally that without a floor, "ready-to-show" would fire almost
// immediately and the bird would never actually be seen.
const SPLASH_MIN_MS = 1200;

function createSplash() {
    splashWindow = new BrowserWindow({
        width: 520, height: 340, frame: false, resizable: false, movable: false,
        center: true, alwaysOnTop: true, backgroundColor: '#0a0c10', show: true,
        webPreferences: { contextIsolation: true, nodeIntegration: false },
    });
    splashWindow.loadFile(path.join(__dirname, 'splash.html'));
    return Date.now();
}

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

// Shared by the office:browse IPC handler AND the Secretariat agent's
// search_workspace tool — one code path, so the agent can never see a
// different result set than the "Browse sealed documents" button does.
async function browseDocuments({ limit, state } = {}) {
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
}

// Shared by the office:export-pdf IPC handler AND the Secretariat agent's
// export_pdf tool.
async function exportDocumentPdf(document) {
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
}

// Sign + seal in one step, for the Secretariat agent's sign_document tool
// (lib.document.sign() itself is called by the tool — this just handles
// the same "save locally, then seal to this product's own worker" tail
// that office:sign's IPC handler does).
async function signAndSeal(signedDocument) {
    const p = docPath(signedDocument);
    lib.fileFormat.saveOfficeFile(p, signedDocument);
    const hex = lib.fileFormat.documentIdentityHash(signedDocument);
    const bytes = fs.readFileSync(p);
    return sealToWorker(hex, bytes);
}

// ── Project Assist — worker client ──────────────────────────────────────────
// One thin fetch wrapper, one place the /projects/* API shape is known —
// both the office:project-* IPC handlers (plain UI) AND the Secretariat
// agent tools (agent-tools.js) call through THIS SAME object, so typing
// into the agent chat and clicking through the UI never diverge (same
// principle as bid-factors.js being the one source of truth for the
// question catalog itself).
async function officeWorkerFetch(pathAndQuery, opts = {}) {
    if (!WORKER_AUTH) return { ok: false, error: 'no worker configured (PHOENIX_OFFICE_AUTH not set)' };
    try {
        const res = await fetch(`${WORKER_URL.replace(/\/+$/, '')}${pathAndQuery}`, {
            method: opts.method || 'GET',
            headers: { Authorization: `Bearer ${WORKER_AUTH}`, ...(opts.body ? { 'Content-Type': 'application/json' } : {}) },
            body: opts.body ? JSON.stringify(opts.body) : undefined,
        });
        const body = await res.json().catch(() => ({}));
        if (!res.ok) return { ok: false, error: body.message || `worker ${res.status}` };
        return { ok: true, ...body };
    } catch (e) { return { ok: false, error: e.message }; }
}

const projectStore = {
    createProject: ({ name, authorId, jobId, bidFactors, counterparty }) =>
        officeWorkerFetch('/projects', { method: 'POST', body: { name, author_id: authorId, job_id: jobId || null, bid_factors: bidFactors || {}, counterparty: counterparty || null } }),
    listProjects: (authorId) => officeWorkerFetch(`/projects?author_id=${encodeURIComponent(authorId)}`),
    getProject: (projectId) => officeWorkerFetch(`/projects/${encodeURIComponent(projectId)}`),
    patchProject: (projectId, patch) => officeWorkerFetch(`/projects/${encodeURIComponent(projectId)}`, { method: 'PATCH', body: patch }),
    createPhases: (projectId, phases) => officeWorkerFetch(`/projects/${encodeURIComponent(projectId)}/phases`, { method: 'POST', body: { phases } }),
    listPhases: (projectId) => officeWorkerFetch(`/projects/${encodeURIComponent(projectId)}/phases`),
    patchPhase: (projectId, phaseId, patch) => officeWorkerFetch(`/projects/${encodeURIComponent(projectId)}/phases/${encodeURIComponent(phaseId)}`, { method: 'PATCH', body: patch }),
    seedChecklist: (projectId, phaseId) => officeWorkerFetch(`/projects/${encodeURIComponent(projectId)}/phases/${encodeURIComponent(phaseId)}/checklist`, { method: 'POST', body: { from_catalog: true } }),
    addChecklistItem: (projectId, phaseId, item) => officeWorkerFetch(`/projects/${encodeURIComponent(projectId)}/phases/${encodeURIComponent(phaseId)}/checklist`, { method: 'POST', body: { item } }),
    listChecklist: (projectId, phaseId) => officeWorkerFetch(`/projects/${encodeURIComponent(projectId)}/phases/${encodeURIComponent(phaseId)}/checklist`),
    // item_id is globally unique (worker/schema.sql) and the worker's decision/
    // history handlers key purely off it, ignoring the project/phase segments
    // in the URL — the '_' placeholders keep the route's REST shape consistent
    // with the rest of this tree without needing callers to look up ids they
    // don't otherwise need for this call.
    decideChecklistItem: (itemId, decision) => officeWorkerFetch(`/projects/_/phases/_/checklist/${encodeURIComponent(itemId)}/decision`, { method: 'POST', body: decision }),
    checklistItemHistory: (itemId) => officeWorkerFetch(`/projects/_/phases/_/checklist/${encodeURIComponent(itemId)}/history`),
    searchChecklistCatalog: ({ phase_type } = {}) => officeWorkerFetch(`/checklist-catalog${phase_type ? `?phase_type=${encodeURIComponent(phase_type)}` : ''}`),
    listProjectDocuments: (projectId, phaseId) => officeWorkerFetch(`/projects/${encodeURIComponent(projectId)}/documents${phaseId ? `?phase_id=${encodeURIComponent(phaseId)}` : ''}`),
};

// Print a completed phase — reuses the exact same ensureSoffice/convertFile
// path exportDocumentPdf already uses above, per the plan's "zero new
// export code" requirement. The letterhead/report HTML is the only new
// piece (lib/phase-html.js).
async function exportPhasePdf(projectId, phaseId) {
    try {
        const [project, checklist, docs] = await Promise.all([
            projectStore.getProject(projectId),
            projectStore.listChecklist(projectId, phaseId),
            projectStore.listProjectDocuments(projectId, phaseId),
        ]);
        if (!project.ok) return { ok: false, error: `project lookup failed: ${project.error}` };
        const phases = await projectStore.listPhases(projectId);
        const phase = (phases.items || []).find(p => p.phase_id === phaseId);
        if (!phase) return { ok: false, error: 'phase not found' };

        const { path: sofficePath } = await lib.libreoffice.ensureSoffice({
            workerUrl: WORKER_URL, auth: WORKER_AUTH, appDataDir: app.getPath('userData'),
            onProgress: (received, total) => { if (mainWindow) mainWindow.webContents.send('office:export-progress', { received, total }); },
        });
        const html = lib.phaseHtml.renderPhaseHtml({ project, phase, checklistItems: checklist.items || [], linkedDocs: docs.items || [] });
        const outDir = workdir();
        const htmlPath = path.join(require('os').tmpdir(), `phoenix-office-phase-${phaseId}.html`);
        fs.writeFileSync(htmlPath, html, 'utf8');
        const pdfPath = await lib.libreoffice.convertFile({ sofficePath, inputPath: htmlPath, outputDir: outDir, targetFormat: 'pdf' });
        try { fs.unlinkSync(htmlPath); } catch (_) {}
        return { ok: true, path: pdfPath };
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
function createWindow(splashStartedAt) {
    mainWindow = new BrowserWindow({
        width: 1400, height: 900, minWidth: 1000, minHeight: 640,
        title: 'Phoenix Office',
        backgroundColor: '#0a0c10',
        autoHideMenuBar: true,
        show: !splashStartedAt, // if there's no splash to hand off from, just show immediately
        webPreferences: {
            preload: path.join(__dirname, 'preload.js'),
            sandbox: true,
            contextIsolation: true,
            nodeIntegration: false,
        },
    });
    mainWindow.loadFile(path.join(__dirname, 'index.html'));
    mainWindow.on('closed', () => { mainWindow = null; });

    if (splashStartedAt) {
        let handed = false;
        const handOff = () => {
            if (handed) return;
            handed = true;
            if (splashWindow) { splashWindow.close(); splashWindow = null; }
            if (mainWindow && !mainWindow.isDestroyed()) mainWindow.show();
        };
        mainWindow.once('ready-to-show', () => {
            const elapsed = Date.now() - splashStartedAt;
            setTimeout(handOff, Math.max(0, SPLASH_MIN_MS - elapsed));
        });
        // Safety net — if the main window never fires ready-to-show (a load
        // error, a hung renderer), don't leave the user staring at the
        // splash screen forever. Must stay longer than SPLASH_MIN_MS itself
        // or it silently cuts the intended minimum short (caught live —
        // this was hardcoded to 8000 independent of SPLASH_MIN_MS, so
        // raising the minimum for a visual check didn't actually work).
        setTimeout(handOff, SPLASH_MIN_MS + 8000);
    }
}

app.whenReady().then(() => {
    registerIpc();
    const splashStartedAt = createSplash();
    createWindow(splashStartedAt);
    app.on('activate', () => { if (BrowserWindow.getAllWindows().length === 0) createWindow(); });
});
app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit(); });

// Resolved once at startup, in the background — never blocks IPC
// registration (identity resolution is normally fast/local, but a Google-
// backed identity or an unreachable D1 lookup shouldn't be able to delay
// every other handler in this app from registering). Project Assist tools
// that need attribution (set_checklist_item, create_project, award_project)
// read this via the () => resolvedAuthorId getter passed into
// createAgentLoop below; it degrades to 'a_unknown' rather than throwing if
// resolution is still pending or fails.
let resolvedAuthorId = 'a_unknown';
(async () => {
    try {
        const me = await lib.identity.resolveAuthor({ prefer: 'fingerprint', fallback: true, store: authStore() });
        resolvedAuthorId = me.author_id;
    } catch (_) { /* stays 'a_unknown' — agent tools still work, just without real attribution until this resolves */ }
})();

// ── IPC ──────────────────────────────────────────────────────────────────────
function registerIpc() {
    // requireGoogle pins prefer:'google' AND turns off fallback — a caller
    // asking "am I Google-verified" must get a real answer, not a silent
    // drop to the weaker fingerprint credential (which defeats the entire
    // point of requiring it for Sign/Legal-hold — see office:sign below).
    ipcMain.handle('office:whoami', async (_e, { prefer, requireGoogle } = {}) => {
        try {
            const me = await lib.identity.resolveAuthor({
                prefer: requireGoogle ? 'google' : (prefer || 'fingerprint'),
                fallback: !requireGoogle,
                googleIdToken: googleIdentity && googleIdentity.idToken,
                store: authStore(),
            });
            return { ok: true, author_id: me.author_id, via: me.credential.type, source: me.source, email: (me.credential && me.credential.email) || null };
        } catch (e) { return { ok: false, error: e.message }; }
    });

    // ── Google sign-in (device-code flow) ───────────────────────────────
    // Needed for the eIDAS AdES / ESIGN Act hardening on Sign + Legal hold
    // specifically (see README) — a hardware fingerprint identifies a
    // *machine*, not a verified person; AdES Article 26 requires the
    // latter. No browser embedding, no popup window: the classic
    // device-code flow (show a short code, the user enters it at
    // google.com/device in their own browser, this polls until they do).
    ipcMain.handle('office:google-signin-start', async () => {
        if (!GOOGLE_CLIENT_ID) return { ok: false, error: 'Google sign-in is not configured on this install (PHOENIX_OFFICE_GOOGLE_CLIENT_ID not set)' };
        try {
            const r = await lib.identity.googleDeviceCodeStart({ clientId: GOOGLE_CLIENT_ID, scope: 'openid email' });
            pendingDeviceCode = r.device_code;
            return { ok: true, user_code: r.user_code, verification_url: r.verification_url, interval: r.interval || 5, expires_in: r.expires_in };
        } catch (e) { return { ok: false, error: e.message }; }
    });

    ipcMain.handle('office:google-signin-poll', async () => {
        if (!pendingDeviceCode) return { ok: false, error: 'no sign-in in progress' };
        try {
            const token = await lib.identity.googleDeviceCodePoll({
                clientId: GOOGLE_CLIENT_ID, clientSecret: GOOGLE_CLIENT_SECRET, deviceCode: pendingDeviceCode,
            });
            const claims = lib.identity.googleSubFromIdToken(token.id_token, { clientId: GOOGLE_CLIENT_ID });
            googleIdentity = { idToken: token.id_token, email: claims.email, sub: claims.sub };
            pendingDeviceCode = null;
            return { ok: true, done: true, email: claims.email };
        } catch (e) {
            if (e.code === 'authorization_pending' || e.code === 'slow_down') return { ok: true, done: false };
            pendingDeviceCode = null;
            return { ok: false, error: e.message };
        }
    });

    ipcMain.handle('office:google-signin-cancel', () => { pendingDeviceCode = null; return { ok: true }; });

    ipcMain.handle('office:templates', () => ({ ok: true, templates: listTemplates() }));

    // First-run visibility, not a system-requirements gate — this app has no
    // real hardware/OS floor beyond what Electron itself needs. The one
    // thing worth surfacing upfront: whether the first PDF export/convert
    // is going to silently trigger a ~300MB LibreOffice download. Cheap and
    // synchronous (findLocalSoffice just checks known install paths), so
    // it's fine to call on every boot rather than caching a result.
    ipcMain.handle('office:libreoffice-status', () => {
        try {
            const local = lib.libreoffice.findLocalSoffice(app.getPath('userData'));
            return { ok: true, found: !!local };
        } catch (e) { return { ok: false, error: e.message }; }
    });

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
    ipcMain.handle('office:sign', async (_e, { document, by, signatureImage, signerEmail }) => {
        try {
            const d = lib.document.sign(document, by, signatureImage, signerEmail);
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
    ipcMain.handle('office:export-pdf', async (_e, { document } = {}) => exportDocumentPdf(document));

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
    ipcMain.handle('office:browse', async (_e, { limit, state } = {}) => browseDocuments({ limit, state }));

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

    // Legal hold — see worker/index.js and worker/schema.sql's
    // office_legal_holds comment. Only meaningful for a sealed document
    // (a DRAFT has no worker row to hold at all), so these always resolve
    // the hex from the document the same way office:history does.
    ipcMain.handle('office:legal-hold', async (_e, { document, by, reason } = {}) => {
        if (!WORKER_AUTH) return { ok: false, error: 'no worker configured (PHOENIX_OFFICE_AUTH not set)' };
        try {
            const hex = lib.fileFormat.documentIdentityHash(document);
            const res = await fetch(`${WORKER_URL.replace(/\/+$/, '')}/documents/${encodeURIComponent(hex)}/legal-hold`, {
                method: 'POST',
                headers: { Authorization: `Bearer ${WORKER_AUTH}`, 'Content-Type': 'application/json' },
                body: JSON.stringify({ by, reason }),
            });
            const body = await res.json();
            if (!res.ok) return { ok: false, error: body.error || `worker ${res.status}` };
            return { ok: true, legal_hold: body.legal_hold, reason: body.reason };
        } catch (e) { return { ok: false, error: e.message }; }
    });

    ipcMain.handle('office:legal-hold-release', async (_e, { document, by, reason } = {}) => {
        if (!WORKER_AUTH) return { ok: false, error: 'no worker configured (PHOENIX_OFFICE_AUTH not set)' };
        try {
            const hex = lib.fileFormat.documentIdentityHash(document);
            const res = await fetch(`${WORKER_URL.replace(/\/+$/, '')}/documents/${encodeURIComponent(hex)}/legal-hold/release`, {
                method: 'POST',
                headers: { Authorization: `Bearer ${WORKER_AUTH}`, 'Content-Type': 'application/json' },
                body: JSON.stringify({ by, reason }),
            });
            const body = await res.json();
            if (!res.ok) return { ok: false, error: body.error || `worker ${res.status}` };
            return { ok: true, legal_hold: body.legal_hold };
        } catch (e) { return { ok: false, error: e.message }; }
    });

    // Current status + full audit trail in one call — the render() path
    // needs to know "is this on hold right now" every time a document
    // opens, and the About-style detail (who/when/why) is cheap to include
    // alongside it rather than a second round-trip.
    ipcMain.handle('office:legal-hold-status', async (_e, { document } = {}) => {
        if (!WORKER_AUTH) return { ok: false, error: 'no worker configured (PHOENIX_OFFICE_AUTH not set)' };
        try {
            const hex = lib.fileFormat.documentIdentityHash(document);
            const res = await fetch(`${WORKER_URL.replace(/\/+$/, '')}/documents/${encodeURIComponent(hex)}/legal-hold`, {
                headers: { Authorization: `Bearer ${WORKER_AUTH}` },
            });
            if (!res.ok) return { ok: false, error: `worker ${res.status}` };
            const body = await res.json();
            const events = body.events || [];
            const last = events[events.length - 1];
            return { ok: true, held: !!(last && last.action === 'placed'), events };
        } catch (e) { return { ok: false, error: e.message }; }
    });

    // The report/export — every document currently on hold, for an actual
    // discovery/subpoena response, not just a per-document status check.
    ipcMain.handle('office:legal-holds-report', async () => {
        if (!WORKER_AUTH) return { ok: false, error: 'no worker configured (PHOENIX_OFFICE_AUTH not set)' };
        try {
            const res = await fetch(`${WORKER_URL.replace(/\/+$/, '')}/legal-holds`, {
                headers: { Authorization: `Bearer ${WORKER_AUTH}` },
            });
            if (!res.ok) return { ok: false, error: `worker ${res.status}` };
            const body = await res.json();
            return { ok: true, items: body.items || [] };
        } catch (e) { return { ok: false, error: e.message }; }
    });

    // ── saved job profiles ───────────────────────────────────────────────────
    // "picking a saved profile at the top that auto fills" (Jerry, 2026-09-24):
    // a dropdown of previously-saved customer/job info, shown when starting a
    // new document, so the same customer name/job site/contact doesn't get
    // retyped every time. Server-side (worker + D1), not a local file — same
    // "recoverable from any machine" principle as documents. See
    // worker/index.js's /jobs routes + worker/schema.sql's office_jobs table.
    ipcMain.handle('office:jobs-list', async (_e, { authorId } = {}) => {
        if (!authorId) return { ok: false, error: 'authorId required' };
        if (!WORKER_AUTH) return { ok: true, items: [] }; // no worker configured — dropdown is just empty, not an error the user needs to see
        try {
            const res = await fetch(`${WORKER_URL.replace(/\/+$/, '')}/jobs?author_id=${encodeURIComponent(authorId)}`, {
                headers: { Authorization: `Bearer ${WORKER_AUTH}` },
            });
            if (!res.ok) return { ok: false, error: `worker ${res.status}` };
            const body = await res.json();
            return { ok: true, items: body.items || [] };
        } catch (e) { return { ok: false, error: e.message }; }
    });

    ipcMain.handle('office:jobs-save', async (_e, { jobId, authorId, label, fields, counterparty } = {}) => {
        if (!authorId) return { ok: false, error: 'authorId required' };
        if (!label || !String(label).trim()) return { ok: false, error: 'label required' };
        if (!WORKER_AUTH) return { ok: false, error: 'no worker configured (PHOENIX_OFFICE_AUTH not set) — saved jobs need the worker' };
        try {
            const res = await fetch(`${WORKER_URL.replace(/\/+$/, '')}/jobs`, {
                method: 'POST',
                headers: { Authorization: `Bearer ${WORKER_AUTH}`, 'Content-Type': 'application/json' },
                body: JSON.stringify({ job_id: jobId || undefined, author_id: authorId, label, fields: fields || {}, counterparty: counterparty || undefined }),
            });
            const body = await res.json();
            if (!res.ok) return { ok: false, error: body.error || `worker ${res.status}` };
            return { ok: true, job_id: body.job_id, label: body.label };
        } catch (e) { return { ok: false, error: e.message }; }
    });

    ipcMain.handle('office:jobs-delete', async (_e, { jobId } = {}) => {
        if (!jobId) return { ok: false, error: 'jobId required' };
        if (!WORKER_AUTH) return { ok: false, error: 'no worker configured (PHOENIX_OFFICE_AUTH not set)' };
        try {
            const res = await fetch(`${WORKER_URL.replace(/\/+$/, '')}/jobs/${encodeURIComponent(jobId)}`, {
                method: 'DELETE',
                headers: { Authorization: `Bearer ${WORKER_AUTH}` },
            });
            return { ok: res.ok };
        } catch (e) { return { ok: false, error: e.message }; }
    });

    // ── Project Assist — plain-UI IPC (same projectStore the agent tools
    // use above, so the form and the agent chat can never diverge) ─────────
    ipcMain.handle('office:project-new', (_e, { name, bidFactors, counterparty, jobId } = {}) =>
        projectStore.createProject({ name, authorId: resolvedAuthorId, bidFactors, counterparty, jobId }));
    ipcMain.handle('office:project-list', () => projectStore.listProjects(resolvedAuthorId));
    ipcMain.handle('office:project-get', (_e, { projectId } = {}) => projectStore.getProject(projectId));
    ipcMain.handle('office:project-update', (_e, { projectId, patch } = {}) => projectStore.patchProject(projectId, patch || {}));

    ipcMain.handle('office:project-set-bid-factor', async (_e, { projectId, key, value } = {}) => {
        if (!projectId || !key) return { ok: false, error: 'projectId and key required' };
        const current = await projectStore.getProject(projectId);
        if (!current.ok) return current;
        const updated = lib.bidFactors.setFactor(current.bid_factors, key, value);
        const patched = await projectStore.patchProject(projectId, { bid_factors: updated });
        if (!patched.ok) return patched;
        return { ok: true, bid_factors: updated, next: lib.bidFactors.nextQuestion(updated) };
    });
    ipcMain.handle('office:project-next-bid-question', async (_e, { projectId } = {}) => {
        const current = await projectStore.getProject(projectId);
        if (!current.ok) return current;
        return { ok: true, next: lib.bidFactors.nextQuestion(current.bid_factors) };
    });

    ipcMain.handle('office:project-phases-list', (_e, { projectId } = {}) => projectStore.listPhases(projectId));
    ipcMain.handle('office:project-phase-create', (_e, { projectId, phases } = {}) => projectStore.createPhases(projectId, phases));
    ipcMain.handle('office:project-phase-advance', (_e, { projectId, phaseId, state } = {}) =>
        projectStore.patchPhase(projectId, phaseId, { state }));

    // The "award" milestone in the plain UI (not routed through the agent) —
    // same deterministic derivation the agent's award_project tool uses,
    // via lib.project directly, so both paths produce the identical phase
    // set for the same bid_factors.
    ipcMain.handle('office:project-award', async (_e, { projectId } = {}) => {
        const current = await projectStore.getProject(projectId);
        if (!current.ok) return current;
        if (current.status !== 'BID') return { ok: false, error: `project is ${current.status}, not BID` };
        const phases = lib.project.deriveScheduleFromBidFactors(current.bid_factors);
        const created = await projectStore.createPhases(projectId, phases);
        if (!created.ok) return created;
        for (const p of phases) await projectStore.seedChecklist(projectId, p.phase_id);
        const patched = await projectStore.patchProject(projectId, { status: 'AWARDED' });
        if (!patched.ok) return patched;
        return { ok: true, phases };
    });

    ipcMain.handle('office:project-checklist-list', (_e, { projectId, phaseId } = {}) => projectStore.listChecklist(projectId, phaseId));
    ipcMain.handle('office:project-checklist-seed', (_e, { projectId, phaseId } = {}) => projectStore.seedChecklist(projectId, phaseId));
    ipcMain.handle('office:project-checklist-decide', (_e, { itemId, disposition, rationale, linkedDocHex } = {}) =>
        projectStore.decideChecklistItem(itemId, { disposition, by: resolvedAuthorId, rationale, linked_doc_hex: linkedDocHex || null }));
    ipcMain.handle('office:project-checklist-history', (_e, { itemId } = {}) => projectStore.checklistItemHistory(itemId));
    ipcMain.handle('office:checklist-catalog', (_e, { phaseType } = {}) => projectStore.searchChecklistCatalog({ phase_type: phaseType }));

    ipcMain.handle('office:project-documents-list', (_e, { projectId, phaseId } = {}) => projectStore.listProjectDocuments(projectId, phaseId));

    ipcMain.handle('office:project-print-phase', async (_e, { projectId, phaseId } = {}) => {
        const r = await exportPhasePdf(projectId, phaseId);
        return r;
    });

    // Plain-UI path to create a project-tied document (the "Documents" tab's
    // own "new" button, as opposed to asking Secretariat for one) — same
    // auto-fill logic as the agent's create_project_document tool, kept as
    // its own small function here since agent-tools.js can't reach into
    // main.js's project (the current project object) directly.
    ipcMain.handle('office:project-document-new', async (_e, { project, template, phaseId } = {}) => {
        const t = listTemplates().find(x => x.template === template);
        if (!t) return { ok: false, error: `unknown template: ${template}` };
        let doc = lib.document.createDocument({ fieldNames: t.fields.slice(), counterparty: project?.counterparty || null });
        doc.project_id = project?.project_id || null;
        doc.phase_id = phaseId || null;
        doc.doc_role = template;
        if ('project_name' in doc.fields && project?.name) {
            const r = lib.document.fillField(doc, 'project_name', project.name, doc.author_fingerprint);
            if (r.allowed) doc = r.document;
        }
        if (phaseId && 'phase_breakdown' in doc.fields) {
            const phasesRes = await projectStore.listPhases(project.project_id);
            if (phasesRes.ok) {
                const breakdown = (phasesRes.items || []).map(p => `${p.label} (${p.lifecycle_stage}) — est. ${p.estimated_duration_weeks || '?'} wk`).join('\n');
                const r = lib.document.fillField(doc, 'phase_breakdown', breakdown, doc.author_fingerprint);
                if (r.allowed) doc = r.document;
            }
        }
        return { ok: true, document: doc };
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
    // ── Secretariat agent (tool-using) ─────────────────────────────────────────
    // Additive, next to office:copilot/office:compose above — those stay
    // exactly as they were (proven, still the fallback). This is the new,
    // real-actions path: offline-first (Ollama -> API key -> restricted CLI,
    // see lib/ai-provider.js), acting only through the fixed tool catalog in
    // lib/agent-tools.js, pausing on anything tier'd 'deviation' until the
    // renderer calls office:agent-confirm with the user's decision.
    const agentTools = createAgentTools({
        lib,
        listTemplates,
        browseWorker: browseDocuments,
        aiComplete: aiProvider.complete,
    });
    const agentLoop = createAgentLoop({
        tools: agentTools,
        aiComplete: aiProvider.complete,
        sealDocument: signAndSeal,
        exportPdf: exportDocumentPdf,
        projectStore,
        printPhase: exportPhasePdf,
        authorId: () => resolvedAuthorId,
    });

    ipcMain.handle('office:agent-message', async (_e, { document, project, message } = {}) => {
        if (!message) return { ok: false, error: 'message required' };
        if (!agentSession) agentSession = agentLoop.newSession(document || null, project || null);
        else {
            if (document) agentSession.document = document;
            if (project) agentSession.project = project;
        }
        try { return { ok: true, ...(await agentLoop.runTurn(agentSession, message)) }; }
        catch (e) { return { ok: false, error: e.message }; }
    });

    ipcMain.handle('office:agent-confirm', async (_e, { approve } = {}) => {
        if (!agentSession) return { ok: false, error: 'no active Secretariat session' };
        try { return { ok: true, ...(await agentLoop.resolveConfirm(agentSession, !!approve)) }; }
        catch (e) { return { ok: false, error: e.message }; }
    });

    ipcMain.handle('office:agent-reset', () => { agentSession = null; return { ok: true }; });

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
