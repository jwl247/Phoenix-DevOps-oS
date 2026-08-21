// screenshot-analysis.js
// "Just the screenshot" — single-shot capture + Claude API image analysis.
// Deliberately NOT continuous/real-time: one button press, one capture, one
// API call. That's the affordable version. True real-time streaming is a
// separate, later feature once the budget's there — this module doesn't
// pretend to be that.
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

// Keep this in sync with main.js's own default. Current as of this build —
// verify against your PHOENIX_AI_MODEL setting before relying on it.
const DEFAULT_MODEL = 'claude-sonnet-5';

function ensureScreenshotDir() {
    if (!fs.existsSync(SCREENSHOT_DIR)) {
        fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
    }
}

function register({ ipcMain, desktopCapturer }) {
    // Single-shot capture. No interval, no repeat, no background timer.
    ipcMain.handle('capture-screenshot', async () => {
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
