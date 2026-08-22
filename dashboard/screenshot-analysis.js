// screenshot-analysis.js
// Single-shot capture + Claude API image analysis, plus a live capture loop
// (periodic capture only — see live-capture-start below for why that
// deliberately doesn't mean "periodic API call too").
//
// Wire into main.js with:
//   require('./screenshot-analysis').register({ ipcMain, desktopCapturer });
//
// Reuses the exact same key resolution as _chatClaudeApi in main.js
// (PHOENIX_AI_KEY || ANTHROPIC_API_KEY) — no new auth system.

const fs = require('fs');
const path = require('path');
const os = require('os');

const SCREENSHOT_DIR = path.join(os.homedir(), '.phoenix', 'hud-screenshots');
// Deliberately a DIFFERENT directory from SCREENSHOT_DIR, and a fixed
// filename that gets overwritten every tick rather than a new timestamped
// file per capture. The manual SCREENSHOT button and the live loop are two
// different instances of "capture" with two different consumers: a manual
// shot is a deliberate one-off a human is watching for and Claude's file-
// watcher should push-notify on immediately; a live-loop frame is a
// background tick nobody asked to be interrupted for. Writing live frames
// into the same watched folder would fire one Claude notification per tick
// (every 5-60s, indefinitely) — that's a notification storm, not "watching
// the screen." Keeping it in its own directory with one overwritten
// filename makes it a pull ("check the current frame when you actually
// want to"), not a push.
const LIVE_DIR = path.join(os.homedir(), '.phoenix', 'hud-screenshots', 'live');
const LIVE_FILE = path.join(LIVE_DIR, 'latest.png');

// Keep this in sync with main.js's own default. Current as of this build —
// verify against your PHOENIX_AI_MODEL setting before relying on it.
const DEFAULT_MODEL = 'claude-sonnet-5';

function ensureScreenshotDir() {
    if (!fs.existsSync(SCREENSHOT_DIR)) {
        fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
    }
}

function ensureLiveDir() {
    if (!fs.existsSync(LIVE_DIR)) {
        fs.mkdirSync(LIVE_DIR, { recursive: true });
    }
}

// "What's happening in the dash" — the app's own window, not the whole
// desktop. Match by window title rather than assuming index 0; falls back
// to the full screen if the window can't be found (e.g. minimized, or the
// title changes) so live capture degrades instead of silently going dark.
const APP_WINDOW_TITLE = 'Phoenix DevOps OS - Command Center';

async function _captureLiveFrame(desktopCapturer) {
    ensureLiveDir();
    let sources;
    try {
        sources = await desktopCapturer.getSources({
            types: ['window', 'screen'],
            thumbnailSize: { width: 1920, height: 1080 }
        });
    } catch (_) {
        return; // best-effort — a live tick failing silently isn't worth surfacing
    }
    if (!sources.length) return;
    const appWindow = sources.find(s => s.name === APP_WINDOW_TITLE);
    const target = appWindow || sources.find(s => s.id.startsWith('screen:')) || sources[0];
    try {
        fs.writeFileSync(LIVE_FILE, target.thumbnail.toPNG());
    } catch (_) { /* best-effort */ }
}

async function _captureOnce(desktopCapturer) {
    ensureScreenshotDir();

    let sources;
    try {
        sources = await desktopCapturer.getSources({
            types: ['screen'],
            thumbnailSize: { width: 1920, height: 1080 }
        });
    } catch (e) {
        return { success: false, error: `Capture failed: ${e.message}` };
    }

    if (!sources.length) {
        return { success: false, error: 'No screen sources available.' };
    }

    // Primary display — first source. Multi-monitor picker is a real
    // feature to add later if you need it; not faking a choice now.
    const primary = sources[0];
    const pngBuffer = primary.thumbnail.toPNG();

    const fileName = `screenshot-${new Date().toISOString().replace(/[:.]/g, '-')}.png`;
    const filePath = path.join(SCREENSHOT_DIR, fileName);

    try {
        fs.writeFileSync(filePath, pngBuffer);
    } catch (e) {
        return { success: false, error: `Save failed: ${e.message}` };
    }

    return {
        success: true,
        filePath,
        dataUrl: `data:image/png;base64,${pngBuffer.toString('base64')}`
    };
}

function register({ ipcMain, desktopCapturer }) {
    // Single-shot capture. No interval, no repeat, no background timer.
    ipcMain.handle('capture-screenshot', async () => _captureOnce(desktopCapturer));

    // ── Live capture loop — periodic capture ONLY, no per-frame API call,
    // separate file from the manual/watched path (see LIVE_DIR comment
    // above for why). No license gate, no manual key entry, no second AI
    // provider — just the minimum needed to keep a current frame available.
    let liveTimer = null;
    let liveIntervalMs = 10000;

    ipcMain.handle('live-capture-start', async (event, { intervalMs } = {}) => {
        if (liveTimer) return { success: true, alreadyRunning: true, intervalMs: liveIntervalMs };
        liveIntervalMs = Math.max(5000, Math.min(60000, intervalMs || 10000));
        liveTimer = setInterval(() => { _captureLiveFrame(desktopCapturer); }, liveIntervalMs);
        _captureLiveFrame(desktopCapturer); // capture one immediately, don't wait a full interval
        return { success: true, intervalMs: liveIntervalMs };
    });

    ipcMain.handle('live-capture-stop', async () => {
        if (liveTimer) { clearInterval(liveTimer); liveTimer = null; }
        return { success: true };
    });

    ipcMain.handle('live-capture-status', async () => ({
        running: !!liveTimer,
        intervalMs: liveIntervalMs
    }));

    // On-demand pull of whatever the live loop most recently captured —
    // this is the "check now" path, not a push notification.
    ipcMain.handle('live-capture-get-latest', async () => {
        if (!fs.existsSync(LIVE_FILE)) {
            return { success: false, error: 'No live frame captured yet — start live capture first.' };
        }
        try {
            const pngBuffer = fs.readFileSync(LIVE_FILE);
            return {
                success: true,
                filePath: LIVE_FILE,
                mtimeMs: fs.statSync(LIVE_FILE).mtimeMs,
                dataUrl: `data:image/png;base64,${pngBuffer.toString('base64')}`
            };
        } catch (e) {
            return { success: false, error: `Could not read live frame: ${e.message}` };
        }
    });

    // One image, one prompt, one API call. Not a loop.
    ipcMain.handle('analyze-screenshot', async (event, { filePath, prompt }) => {
        const apiKey = process.env.PHOENIX_AI_KEY || process.env.ANTHROPIC_API_KEY || '';
        if (!apiKey) {
            return {
                success: false,
                error: 'No Anthropic API key configured. Screenshot analysis requires the API — set one via the auth modal or ANTHROPIC_API_KEY.'
            };
        }
        if (!filePath || !fs.existsSync(filePath)) {
            return { success: false, error: `Screenshot not found: ${filePath}` };
        }

        let base64Image;
        try {
            base64Image = fs.readFileSync(filePath).toString('base64');
        } catch (e) {
            return { success: false, error: `Could not read screenshot: ${e.message}` };
        }

        const model = process.env.PHOENIX_AI_MODEL || DEFAULT_MODEL;

        try {
            const res = await fetch('https://api.anthropic.com/v1/messages', {
                method: 'POST',
                headers: {
                    'x-api-key': apiKey,
                    'anthropic-version': '2023-06-01',
                    'content-type': 'application/json'
                },
                body: JSON.stringify({
                    model,
                    max_tokens: 1024,
                    messages: [{
                        role: 'user',
                        content: [
                            {
                                type: 'image',
                                source: { type: 'base64', media_type: 'image/png', data: base64Image }
                            },
                            {
                                type: 'text',
                                text: prompt || 'Describe what is on screen and note anything that looks like an error, warning, or something worth flagging.'
                            }
                        ]
                    }]
                }),
                signal: AbortSignal.timeout(120000)
            });

            if (!res.ok) {
                const errText = await res.text();
                return { success: false, error: `Claude API ${res.status}: ${errText.slice(0, 300)}` };
            }

            const data = await res.json();
            const reply = data.content?.[0]?.text || '';
            if (!reply) {
                return { success: false, error: 'Claude API returned an empty response.' };
            }

            return { success: true, reply, model };
        } catch (e) {
            return { success: false, error: `Request failed: ${e.message}` };
        }
    });
}

module.exports = { register };
