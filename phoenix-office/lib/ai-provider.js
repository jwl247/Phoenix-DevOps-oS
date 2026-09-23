// ai-provider.js — Phoenix Office (standalone)
// Provider-agnostic text completion for the tool-using Secretariat agent.
//
// Offline-first on purpose: the documents this app handles are often
// confidential business records (customer info, pricing, inspection
// findings) — filling one out shouldn't require anything to leave the
// machine by default. Order: local Ollama -> a configured API key ->
// the restricted Claude CLI (dev-only — that binary isn't installed on
// the machines this product ships to, so it's a fallback for Jerry's own
// machine while this is being proven, not a general-purpose tier).
//
// Every candidate here is a plain text-completion call. None of them are
// ever given filesystem or tool access directly — same posture as the
// existing askAI() in main.js, just more sources feeding the same shape
// of answer. Real actions only ever happen through agent-tools.js's own
// whitelist, dispatched by our code after the model names a tool.

const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');
const os = require('os');

// Read live, not cached at require() time — a key entered into Settings
// after the app has already started (or set for a single test) must take
// effect on the very next call, not after a restart.
function ollamaHost() { return (process.env.PHOENIX_OFFICE_OLLAMA_HOST || process.env.OLLAMA_HOST || 'http://127.0.0.1:11434').replace(/\/+$/, ''); }
function ollamaModel() { return process.env.PHOENIX_OFFICE_OLLAMA_MODEL || process.env.OLLAMA_MODEL || 'llama3'; }
function anthropicKey() { return process.env.PHOENIX_OFFICE_ANTHROPIC_KEY || process.env.ANTHROPIC_API_KEY || ''; }
function anthropicModel() { return process.env.PHOENIX_OFFICE_ANTHROPIC_MODEL || 'claude-sonnet-5'; }

function findClaudeCli() {
    const home = os.homedir();
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

// Ollama's /api/chat, non-streaming. A short probe timeout so an absent/
// stopped Ollama fails fast instead of stalling the whole chain.
async function tryOllama({ system, messages }) {
    const controller = new AbortController();
    const t = setTimeout(() => controller.abort(), 20000);
    const model = ollamaModel();
    try {
        const res = await fetch(`${ollamaHost()}/api/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                model,
                stream: false,
                // Grammar-constrained decoding — forces syntactically valid JSON
                // out of the model. Doesn't fix a wrong tool name or a
                // hallucinated field value, but it does fix the small-model
                // failure mode of near-miss JSON (a missing brace, wrong
                // shape) that would otherwise silently fall through
                // agent-loop.js's parser as if it were a real chat reply.
                format: 'json',
                messages: [{ role: 'system', content: system }, ...messages],
            }),
            signal: controller.signal,
        });
        if (!res.ok) throw new Error(`ollama ${res.status}`);
        const body = await res.json();
        const text = body && body.message && body.message.content;
        if (!text) throw new Error('ollama returned no content');
        return { text, via: `ollama:${model}` };
    } finally {
        clearTimeout(t);
    }
}

async function tryAnthropic({ system, messages }) {
    const key = anthropicKey();
    if (!key) throw new Error('no API key configured');
    const model = anthropicModel();
    const res = await fetch('https://api.anthropic.com/v1/messages', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'x-api-key': key,
            'anthropic-version': '2023-06-01',
        },
        body: JSON.stringify({
            model,
            max_tokens: 1024,
            system,
            messages: messages.map(m => ({ role: m.role, content: m.content })),
        }),
    });
    const body = await res.json();
    if (!res.ok) throw new Error(`anthropic ${res.status}: ${body && body.error && body.error.message}`);
    const text = (body.content || []).map(b => b.text || '').join('').trim();
    if (!text) throw new Error('anthropic returned no content');
    return { text, via: `api:${model}` };
}

function tryClaudeCli({ system, messages }) {
    return new Promise((resolve, reject) => {
        const bin = findClaudeCli();
        if (!bin) return reject(new Error('Claude CLI not found on this machine'));
        const last = messages[messages.length - 1];
        const transcript = messages.slice(0, -1).map(m => `${m.role.toUpperCase()}: ${m.content}`).join('\n\n');
        const prompt = `${system}\n\n${transcript ? transcript + '\n\n' : ''}${last ? last.content : ''}`;
        const p = spawn(bin, ['--print', prompt], { timeout: 30000, windowsHide: true });
        let out = '', errOut = '';
        p.stdout.on('data', d => { out += d; });
        p.stderr.on('data', d => { errOut += d; });
        p.on('error', reject);
        p.on('close', code => {
            if (code === 0 && out.trim()) resolve({ text: out.trim(), via: 'cli:restricted' });
            else reject(new Error(errOut.trim() || `claude exited ${code}`));
        });
    });
}

// complete({ system, messages }) -> { text, via }. Tries each candidate in
// order, offline-first; throws only if every candidate fails, with all
// their errors attached so the caller can show something useful.
async function complete({ system, messages }) {
    const attempts = [
        ['ollama', tryOllama],
        ['api', tryAnthropic],
        ['cli', tryClaudeCli],
    ];
    const errors = [];
    for (const [name, fn] of attempts) {
        try {
            return await fn({ system, messages });
        } catch (e) {
            errors.push(`${name}: ${e.message}`);
        }
    }
    const err = new Error(`no AI provider available — ${errors.join(' | ')}`);
    err.attempts = errors;
    throw err;
}

module.exports = { complete, tryOllama, tryAnthropic, tryClaudeCli, findClaudeCli };
