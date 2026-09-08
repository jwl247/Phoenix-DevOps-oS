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
const path = require('path');

let officeWindow = null;
let libs = null;         // lazily required from the repo copy
let officeRoot = null;

function loadLibs(phoenixRoot) {
    if (libs) return libs;
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

    // ── document state machine ───────────────────────────────────────────────
    ipcMain.handle('office:new', async (_e, { fieldNames, counterparty, authorId } = {}) => {
        try {
            const d = L().document.createDocument({
                fieldNames: fieldNames || [],
                authorFingerprint: authorId || undefined,
                counterparty: counterparty || null,
            });
            return { ok: true, document: d };
        } catch (e) { return { ok: false, error: e.message }; }
    });

    ipcMain.handle('office:fill', (_e, { document, field, value, by }) => {
        const r = L().document.fillField(document, field, value, by);
        return r.allowed ? { ok: true, document: r.document } : { ok: false, reason: r.reason, error: r.detail };
    });

    ipcMain.handle('office:hand', (_e, { document }) => {
        try { return { ok: true, document: L().document.handToClient(document) }; }
        catch (e) { return { ok: false, error: e.message }; }
    });

    ipcMain.handle('office:sign', (_e, { document, by }) => {
        try { return { ok: true, document: L().document.sign(document, by) }; }
        catch (e) { return { ok: false, error: e.message }; }
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

    // ── open / save ──────────────────────────────────────────────────────────
    ipcMain.handle('office:open', async () => {
        const res = await dialog.showOpenDialog(officeWindow, {
            title: 'Open Phoenix Office document',
            filters: [{ name: 'Office document', extensions: ['office', 'office.json', 'json'] }],
            properties: ['openFile'],
        });
        if (res.canceled || !res.filePaths[0]) return { ok: false, canceled: true };
        try {
            const loaded = L().fileFormat.loadOfficeFile(res.filePaths[0]);
            return { ok: true, filePath: res.filePaths[0], ...loaded };
        } catch (e) { return { ok: false, error: e.message }; }
    });

    ipcMain.handle('office:save', async (_e, { document, filePath } = {}) => {
        let target = filePath;
        if (!target) {
            const res = await dialog.showSaveDialog(officeWindow, {
                title: 'Save Phoenix Office document',
                defaultPath: 'document.office.json',
                filters: [{ name: 'Office document', extensions: ['office.json', 'office', 'json'] }],
            });
            if (res.canceled || !res.filePath) return { ok: false, canceled: true };
            target = res.filePath;
        }
        try {
            L().fileFormat.saveOfficeFile(target, document);
            return { ok: true, filePath: target };
        } catch (e) { return { ok: false, error: e.message }; }
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
