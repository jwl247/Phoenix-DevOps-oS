// agent-loop.js — Phoenix Office (standalone)
//
// A provider-agnostic ReAct-style loop: the model never gets a native
// function-calling API (Ollama's tool support is inconsistent across
// models, and the restricted Claude CLI has none at --print) — instead it
// is told the tool catalog in plain text and must reply with exactly one
// JSON object, either a tool call or a final answer. Our code parses that,
// executes 'base' tier tools immediately, and pauses on 'deviation' tier
// tools until resolveConfirm() is called with the user's decision. This is
// the whole safety boundary: the model can only ever name a tool that
// already exists in agent-tools.js's catalog, with args that tool itself
// validates — never a shell, never a raw file path outside that catalog.

const DEFAULT_PERSONA =
    'You are Secretariat, Phoenix Office\'s standing assistant — in the spirit of ' +
    'K.I.T.T. from Knight Rider: calm, precise, one step at a time, working alongside ' +
    'the author rather than instead of them. You help draft, fill, and move real ' +
    'business documents (work orders, invoices, inspections, change orders) through ' +
    'their lifecycle. NEVER invent a value for a field, a phone number, an email, or any ' +
    'other contact detail you were not actually given — omit it or ask, never guess or ' +
    'fabricate a plausible-looking one. You act ONLY through the tools below; you have ' +
    'no other way to touch the document or the world. NEVER reply with {"final":...} ' +
    'claiming something was created, filled, handed off, or signed unless you actually ' +
    'called the matching tool first and it succeeded — a false "done" is worse than an ' +
    'honest failure. Once the user\'s request is actually satisfied, stop and reply with ' +
    '{"final":...} immediately — do not keep calling more tools "to be thorough."';

const MAX_STEPS = 6;
const MAX_HISTORY = 20;

function docSummary(doc) {
    if (!doc) return 'none — no document open yet';
    const entries = Object.entries(doc.fields || {});
    const filled = entries.filter(([, v]) => v !== null).length;
    return `state=${doc.state}, fields ${filled}/${entries.length} filled, counterparty=${doc.counterparty ? 'set' : 'none'}`;
}

function trimForModel(data) {
    if (Array.isArray(data) && data.length > 10) return { truncated: true, count: data.length, sample: data.slice(0, 10) };
    return data;
}

function parseModelReply(text) {
    const cleaned = String(text || '').trim().replace(/^```(json)?/i, '').replace(/```$/, '').trim();
    let obj;
    try {
        obj = JSON.parse(cleaned);
    } catch (_) {
        // A real, observed small-model failure mode: it clearly attempted
        // JSON (starts with a brace) but botched the syntax (missing a
        // closing brace, wrong quoting). Flag for a repair retry instead of
        // dumping the broken JSON to the user as if it were a real reply.
        if (/^[{[]/.test(cleaned)) return { malformed: true, raw: cleaned };
        return { final: String(text || '').trim() || '(no reply)' };
    }
    if (obj && (obj.tool || obj.final)) return obj;
    // Syntactically valid JSON, but not our contract's shape (e.g.
    // {"new_document": {...}} instead of {"tool":"new_document","args":{...}})
    // — same repair path, not a silent pass-through as a "final" answer.
    return { malformed: true, raw: cleaned };
}

function createAgentLoop({ tools, aiComplete, persona, sealDocument, exportPdf }) {
    const SYSTEM_PERSONA = persona || DEFAULT_PERSONA;

    function newSession(document) {
        return { modelMessages: [], transcript: [], document: document || null, pending: null, lastToolData: null };
    }

    function systemPrompt(doc) {
        return [
            SYSTEM_PERSONA,
            '',
            'Reply with EXACTLY one JSON object and nothing else — no markdown fences, no prose outside it.',
            'To call a tool:  {"tool":"<name>","args":{...}}',
            'To speak to the user instead of calling a tool:  {"final":"<one short message>"}',
            '',
            'Tools:',
            tools.catalogForPrompt(),
            '',
            `Current document: ${docSummary(doc)}`,
        ].join('\n');
    }

    async function runTool(session, name, args) {
        const tool = tools.get(name);
        if (!tool) return { ok: false, message: `unknown tool: ${name}` };
        let result;
        try {
            result = await tool.execute(args || {}, session, { sealDocument, exportPdf });
        } catch (e) {
            result = { ok: false, message: e.message };
        }
        if (result && result.document) session.document = result.document;
        session.transcript.push({ role: 'tool', tool: name, args, result: { ok: result.ok, message: result.message } });
        session.modelMessages.push({
            role: 'user',
            content: `[tool result: ${name}] ${JSON.stringify({ ok: result.ok, message: result.message, data: trimForModel(result.data) })}`,
        });
        // Untrimmed — for the renderer to surface real results into the
        // workspace/reference pane (DB-backed), separate from the
        // token-economical version the model itself sees above.
        if (result && result.ok && result.data !== undefined) {
            session.lastToolData = { tool: name, data: result.data };
        }
        return result;
    }

    async function drive(session) {
        for (let i = 0; i < MAX_STEPS; i++) {
            const sys = systemPrompt(session.document);
            const messages = session.modelMessages.slice(-MAX_HISTORY);
            let replyText, via;
            try {
                const r = await aiComplete({ system: sys, messages });
                replyText = r.text; via = r.via;
            } catch (e) {
                session.transcript.push({ role: 'assistant', content: `offline — ${e.message}` });
                return { state: 'error', message: e.message, document: session.document, transcript: session.transcript, lastToolData: session.lastToolData };
            }
            session.modelMessages.push({ role: 'assistant', content: replyText });
            const parsed = parseModelReply(replyText);

            if (parsed.final) {
                session.transcript.push({ role: 'assistant', content: parsed.final, via });
                return { state: 'done', message: parsed.final, document: session.document, transcript: session.transcript, via, lastToolData: session.lastToolData };
            }

            const tool = tools.get(parsed.tool);
            if (!tool) {
                session.modelMessages.push({ role: 'user', content: `[tool result] unknown tool "${parsed.tool}" — pick one from the catalog exactly as named.` });
                continue;
            }
            if (tool.tier === 'deviation') {
                session.pending = { toolName: parsed.tool, args: parsed.args || {} };
                session.transcript.push({ role: 'confirm', tool: parsed.tool, args: parsed.args || {} });
                return { state: 'confirm', pending: session.pending, document: session.document, transcript: session.transcript, via, lastToolData: session.lastToolData };
            }
            await runTool(session, parsed.tool, parsed.args || {});
            // loop continues — the tool result is now in modelMessages for the next completion
        }
        return { state: 'error', message: `stalled after ${MAX_STEPS} steps without a final answer`, document: session.document, transcript: session.transcript, lastToolData: session.lastToolData };
    }

    async function runTurn(session, userMessage) {
        if (session.pending) throw new Error('a tool call is awaiting confirmation — resolve it first');
        session.transcript.push({ role: 'user', content: userMessage });
        session.modelMessages.push({ role: 'user', content: userMessage });
        return drive(session);
    }

    async function resolveConfirm(session, approve) {
        if (!session.pending) throw new Error('nothing awaiting confirmation');
        const { toolName, args } = session.pending;
        session.pending = null;
        if (!approve) {
            session.transcript.push({ role: 'system', content: `declined: ${toolName}` });
            session.modelMessages.push({ role: 'user', content: `[tool result: ${toolName}] NOT approved by the user. Do not retry it — ask what they'd like instead.` });
            return drive(session);
        }
        await runTool(session, toolName, args);
        return drive(session);
    }

    return { newSession, runTurn, resolveConfirm, DEFAULT_PERSONA: SYSTEM_PERSONA };
}

module.exports = { createAgentLoop, DEFAULT_PERSONA, docSummary, parseModelReply };
