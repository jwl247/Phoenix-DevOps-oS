// agent-tools.js — Phoenix Office (standalone)
//
// The declared, callable tool catalog for the tool-using Secretariat agent.
// This is CLAUDE.md's "Phoenix as an agent, not an app" interaction model
// applied here: the model is never handed a shell or filesystem access
// (see ai-provider.js's header) — it can only name one of the tools below,
// with the exact args the tool declares, and OUR code decides whether that
// runs immediately or needs a human to confirm it first.
//
// Three tiers, same shape as CLAUDE.md's permission tiers:
//   'base'      — runs without asking. Search, draft, fill, export — nothing
//                 here leaves the local draft or touches another person.
//   'deviation' — the caller (agent-loop.js) must pause and get an explicit
//                 yes before executing. Hand-off and signing both leave the
//                 local draft and touch shared/external state.
//   (never exposed at all — not a tier, just tools that don't exist here):
//                 no delete-signed-document, no bypass-fill-once, no
//                 free-form notification send outside tamper-guard's own
//                 path, no arbitrary file/shell access. If it's not in
//                 TOOLS below, the agent cannot do it, full stop.

function createAgentTools({ lib, listTemplates, browseWorker, aiComplete }) {
    const TOOLS = [
        {
            name: 'search_workspace',
            tier: 'base',
            description: "Search this product's own sealed documents (not Phoenix's clone pool — this app's isolated store). Use to find a past work order/invoice/inspection by title, counterparty, or state.",
            args: '{ query?: string, state?: "DRAFT"|"PENDING_REVIEW"|"SIGNED", limit?: number }',
            async execute(args) {
                const r = await browseWorker({ limit: args.limit || 20, state: args.state });
                if (!r.ok) return { ok: false, message: `search failed: ${r.error}` };
                const q = (args.query || '').toLowerCase();
                const items = !q ? r.items : r.items.filter(it => JSON.stringify(it).toLowerCase().includes(q));
                return { ok: true, message: `found ${items.length} document(s)`, data: items };
            },
        },
        {
            name: 'search_templates',
            tier: 'base',
            description: 'Search the local template catalog (work-order, invoice, inspection, change-order, blank) by name or field.',
            args: '{ query?: string }',
            async execute(args) {
                const all = listTemplates();
                const q = (args.query || '').toLowerCase();
                const items = !q ? all : all.filter(t => JSON.stringify(t).toLowerCase().includes(q));
                return { ok: true, message: `found ${items.length} template(s)`, data: items };
            },
        },
        {
            name: 'new_document',
            tier: 'base',
            description: 'Start a new local draft from a template or an explicit field list. Becomes the current working document. Does not touch any existing document.',
            args: '{ template?: string, fieldNames?: string[], counterparty?: { phone?, carrier?, email? } }',
            async execute(args) {
                let fields = args.fieldNames;
                if (args.template) {
                    const t = listTemplates().find(x => x.template === args.template);
                    if (!t) return { ok: false, message: `unknown template: ${args.template}` };
                    fields = t.fields.slice();
                }
                if (!fields || !fields.length) return { ok: false, message: 'no fields — name a template or at least one field' };
                const d = lib.document.createDocument({ fieldNames: fields, counterparty: args.counterparty || null });
                return { ok: true, message: `started a new ${args.template || 'blank'} document`, document: d };
            },
        },
        {
            name: 'draft_field',
            tier: 'base',
            description: "Suggest text for ONE field on the current document. Returns a suggestion only — never writes it. The author still has to accept it via fill_field.",
            args: '{ field: string, instruction?: string }',
            async execute(args, state) {
                if (!state.document) return { ok: false, message: 'no current document — start one with new_document first' };
                if (!(args.field in state.document.fields)) return { ok: false, message: `'${args.field}' is not a field on this document` };
                const otherFields = Object.entries(state.document.fields)
                    .filter(([k, v]) => k !== args.field && v !== null)
                    .map(([k, v]) => `${k}: ${v}`).join('\n');
                const system =
                    'You are drafting ONE field\'s content for a Phoenix Office document (a tamper-evident ' +
                    'work order/invoice/inspection/change-order record). Reply with ONLY the value for the field ' +
                    `"${args.field}" — no field name, no quotes, no markdown, no preamble, just the value itself.`;
                const userMsg =
                    (args.instruction ? `Instruction: ${args.instruction}\n` : '') +
                    `Other fields already on this document:\n${otherFields || '(none yet)'}`;
                const { text } = await aiComplete({ system, messages: [{ role: 'user', content: userMsg }] });
                return { ok: true, message: `drafted "${args.field}"`, data: { field: args.field, value: text.trim().replace(/^["']|["']$/g, '') } };
            },
        },
        {
            name: 'fill_field',
            tier: 'base',
            description: 'Fill a currently-empty field on the current document with an exact value. Fields are fill-once — this fails cleanly if the field is already filled or the document is signed.',
            args: '{ field: string, value: string }',
            async execute(args, state) {
                if (!state.document) return { ok: false, message: 'no current document — start one with new_document first' };
                const r = lib.document.fillField(state.document, args.field, args.value, state.document.author_fingerprint);
                if (!r.allowed) return { ok: false, message: `${r.reason}: ${r.detail}` };
                return { ok: true, message: `filled "${args.field}"`, document: r.document };
            },
        },
        {
            name: 'hand_to_client',
            tier: 'deviation',
            description: 'Move the current document from DRAFT to PENDING_REVIEW — the custody handoff to the counterparty for review/signature. Leaves the local draft state.',
            args: '{}',
            async execute(_args, state) {
                if (!state.document) return { ok: false, message: 'no current document' };
                const d = lib.document.handToClient(state.document);
                return { ok: true, message: 'handed to client for review', document: d };
            },
        },
        {
            name: 'sign_document',
            tier: 'deviation',
            description: 'Sign the current PENDING_REVIEW document, permanently hash-locking it, then seal it into this product\'s own storage. Irreversible — a later correction is a separate change-order document, never an edit to this one.',
            args: '{ by?: string }',
            async execute(args, state, ctx) {
                if (!state.document) return { ok: false, message: 'no current document' };
                const d = lib.document.sign(state.document, args.by);
                const sealed = ctx && ctx.sealDocument ? await ctx.sealDocument(d) : { ok: false, error: 'no seal handler wired' };
                return { ok: true, message: sealed.ok ? 'signed and sealed' : `signed (seal pending: ${sealed.error})`, document: d, data: { sealed } };
            },
        },
        {
            name: 'export_pdf',
            tier: 'base',
            description: 'Export the current document to a local PDF via LibreOffice. Purely local — no network egress beyond a one-time LibreOffice fetch if not already installed.',
            args: '{}',
            async execute(_args, state, ctx) {
                if (!state.document) return { ok: false, message: 'no current document' };
                if (!ctx || !ctx.exportPdf) return { ok: false, message: 'export not wired' };
                const r = await ctx.exportPdf(state.document);
                if (!r.ok) return { ok: false, message: `export failed: ${r.error}` };
                return { ok: true, message: `exported to ${r.path}`, data: { path: r.path } };
            },
        },
    ];

    return {
        list: TOOLS,
        get(name) { return TOOLS.find(t => t.name === name); },
        catalogForPrompt() {
            return TOOLS.map(t => `- ${t.name} [${t.tier}] ${t.args} — ${t.description}`).join('\n');
        },
    };
}

module.exports = { createAgentTools };
