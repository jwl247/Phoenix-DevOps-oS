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

        // ── Project Assist ──────────────────────────────────────────────────
        // Same base/deviation split as above, applied to a project instead of
        // a single document: read/suggest/export = base, anything that
        // changes real operational state a human should own = deviation.
        // ctx.projectStore is the injected worker-fetch layer (main.js) —
        // these tools never talk to the worker directly, same separation
        // sealDocument/exportPdf already establish above.
        {
            name: 'create_project',
            tier: 'base',
            description: 'Start a new project (a bid, eventually a job with phases/documents). Becomes the current project. Does not touch any existing project.',
            args: '{ name: string, job_id?: string }',
            async execute(args, _state, ctx) {
                if (!args.name) return { ok: false, message: 'name required' };
                if (!ctx || !ctx.projectStore) return { ok: false, message: 'project store not wired' };
                const r = await ctx.projectStore.createProject({ name: args.name, authorId: ctx.authorId, jobId: args.job_id || null });
                if (!r.ok) return { ok: false, message: `create failed: ${r.error}` };
                const full = await ctx.projectStore.getProject(r.project_id);
                return { ok: true, message: `started project "${args.name}"`, project: full };
            },
        },
        {
            name: 'open_project',
            tier: 'base',
            description: 'Load an existing project (by project_id) into the session.',
            args: '{ project_id: string }',
            async execute(args, _state, ctx) {
                if (!args.project_id) return { ok: false, message: 'project_id required' };
                if (!ctx || !ctx.projectStore) return { ok: false, message: 'project store not wired' };
                const full = await ctx.projectStore.getProject(args.project_id);
                if (!full.ok) return { ok: false, message: `not found: ${args.project_id}` };
                return { ok: true, message: `opened "${full.name}"`, project: full };
            },
        },
        {
            name: 'set_bid_factor',
            tier: 'base',
            description: 'Record one answered bid-influencing factor on the current project, then report the next unanswered question — this is the anticipatory-Q&A mechanism, ask exactly the returned next question, not something else. Use bid-factors keys like "project_type", "dimensions.length_ft", "schedule.tightness".',
            args: '{ key: string, value: string|number|boolean }',
            async execute(args, state, ctx) {
                if (!state.project) return { ok: false, message: 'no current project — start one with create_project first' };
                if (!args.key) return { ok: false, message: 'key required' };
                const bidFactors = require('./bid-factors');
                const updated = bidFactors.setFactor(state.project.bid_factors, args.key, args.value);
                const r = await ctx.projectStore.patchProject(state.project.project_id, { bid_factors: updated });
                if (!r.ok) return { ok: false, message: `save failed: ${r.error}` };
                const next = bidFactors.nextQuestion(updated);
                const project = { ...state.project, bid_factors: updated };
                return {
                    ok: true,
                    message: next ? `recorded. Next: ${next.label}` : 'all bid factors answered — ready to award the project when the client confirms.',
                    project,
                    data: { next },
                };
            },
        },
        {
            name: 'create_project_document',
            tier: 'base',
            description: 'Spawn a new document (proposal, safety-plan, schedule, work-order, invoice, inspection, change-order, or blank) tied to the current project, auto-filling what it can from the project. Becomes the current document.',
            args: '{ template: string, phase_id?: string }',
            async execute(args, state, ctx) {
                if (!state.project) return { ok: false, message: 'no current project — start one with create_project first' };
                const t = listTemplates().find(x => x.template === args.template);
                if (!t) return { ok: false, message: `unknown template: ${args.template}` };
                const d = lib.document.createDocument({ fieldNames: t.fields.slice(), counterparty: state.project.counterparty || null });
                d.project_id = state.project.project_id;
                d.phase_id = args.phase_id || null;
                d.doc_role = args.template;
                // Best-effort auto-fill — only fields we actually have a real
                // source for. Never guesses a value (same rule draft_field's
                // persona follows) — everything else stays for fill_field/
                // draft_field the normal way.
                let doc = d;
                if ('project_name' in doc.fields) {
                    const r = lib.document.fillField(doc, 'project_name', state.project.name, doc.author_fingerprint);
                    if (r.allowed) doc = r.document;
                }
                if (args.phase_id && 'phase_breakdown' in doc.fields && Array.isArray(state.project.phases)) {
                    const breakdown = state.project.phases.map(p => `${p.label} (${p.lifecycle_stage}) — est. ${p.estimated_duration_weeks || '?'} wk`).join('\n');
                    const r = lib.document.fillField(doc, 'phase_breakdown', breakdown, doc.author_fingerprint);
                    if (r.allowed) doc = r.document;
                }
                return { ok: true, message: `started a new ${args.template} document for this project`, document: doc };
            },
        },
        {
            name: 'check_phase_checklist',
            tier: 'base',
            description: "Read a phase's checklist — items, source (OSHA/OK_STATE/CLIENT_SPEC/PM_BEST_PRACTICE), and current disposition. Read-only.",
            args: '{ phase_id: string }',
            async execute(args, state, ctx) {
                if (!state.project) return { ok: false, message: 'no current project' };
                const r = await ctx.projectStore.listChecklist(state.project.project_id, args.phase_id);
                if (!r.ok) return { ok: false, message: `lookup failed: ${r.error}` };
                return { ok: true, message: `${r.items.length} checklist item(s)`, data: r.items };
            },
        },
        {
            name: 'search_checklist_catalog',
            tier: 'base',
            description: 'Search the standing checklist catalog (real OSHA/state/PM-best-practice reference items) by phase type or keyword — use to find what a phase should be checked against before it starts.',
            args: '{ phase_type?: string, query?: string }',
            async execute(args, _state, ctx) {
                const r = await ctx.projectStore.searchChecklistCatalog({ phase_type: args.phase_type });
                if (!r.ok) return { ok: false, message: `search failed: ${r.error}` };
                const q = (args.query || '').toLowerCase();
                const items = !q ? r.items : r.items.filter(it => JSON.stringify(it).toLowerCase().includes(q));
                return { ok: true, message: `found ${items.length} catalog item(s)`, data: items };
            },
        },
        {
            name: 'draft_checklist_rationale',
            tier: 'base',
            description: 'Suggest rationale text for one checklist item\'s determination. Returns a suggestion only — never records it. The human still has to accept it via set_checklist_item.',
            args: '{ label: string, instruction?: string }',
            async execute(args) {
                if (!args.label) return { ok: false, message: 'label required' };
                const system =
                    'You are drafting a short, professional rationale for a construction-project checklist ' +
                    'determination (why an item is satisfied, not applicable, or still open). Reply with ONLY the ' +
                    'rationale text — no preamble, no quotes, no markdown.';
                const userMsg = `Checklist item: "${args.label}"` + (args.instruction ? `\nContext: ${args.instruction}` : '');
                const { text } = await aiComplete({ system, messages: [{ role: 'user', content: userMsg }] });
                return { ok: true, message: 'drafted a rationale', data: { rationale: text.trim().replace(/^["']|["']$/g, '') } };
            },
        },
        {
            name: 'print_phase',
            tier: 'base',
            description: 'Export a completed phase (its checklist, decisions, cost, and risk) to a local PDF — the same oversight-record artifact a client would see. Purely local/export, no state change.',
            args: '{ phase_id: string }',
            async execute(args, state, ctx) {
                if (!state.project) return { ok: false, message: 'no current project' };
                if (!ctx || !ctx.printPhase) return { ok: false, message: 'print not wired' };
                const r = await ctx.printPhase(state.project.project_id, args.phase_id);
                if (!r.ok) return { ok: false, message: `print failed: ${r.error}` };
                return { ok: true, message: `exported to ${r.path}`, data: { path: r.path } };
            },
        },
        {
            name: 'advance_phase',
            tier: 'deviation',
            description: 'Move a phase to a new state (NOT_STARTED, IN_PROGRESS, COMPLETE) — a real operational milestone the human should confirm, not something to do silently.',
            args: '{ phase_id: string, to_state: "NOT_STARTED"|"IN_PROGRESS"|"COMPLETE" }',
            async execute(args, state, ctx) {
                if (!state.project) return { ok: false, message: 'no current project' };
                if (!args.phase_id || !args.to_state) return { ok: false, message: 'phase_id and to_state required' };
                const r = await ctx.projectStore.patchPhase(state.project.project_id, args.phase_id, { state: args.to_state });
                if (!r.ok) return { ok: false, message: `update failed: ${r.error}` };
                return { ok: true, message: `phase moved to ${args.to_state}` };
            },
        },
        {
            name: 'set_checklist_item',
            tier: 'deviation',
            description: "Record the human's determination on one checklist item (satisfied, not_applicable, or open) with a rationale — this IS the documented decision, the point of the whole checklist engine. Never call this to guess a determination on the human's behalf; only after they've actually told you what to record.",
            args: '{ item_id: string, disposition: "satisfied"|"not_applicable"|"open", rationale: string, linked_doc_hex?: string }',
            async execute(args, _state, ctx) {
                if (!args.item_id || !args.disposition || !args.rationale) return { ok: false, message: 'item_id, disposition, and rationale are all required' };
                const r = await ctx.projectStore.decideChecklistItem(args.item_id, {
                    disposition: args.disposition, by: ctx.authorId, rationale: args.rationale, linked_doc_hex: args.linked_doc_hex || null,
                });
                if (!r.ok) return { ok: false, message: `record failed: ${r.error}` };
                return { ok: true, message: `recorded: ${args.disposition}` };
            },
        },
        {
            name: 'award_project',
            tier: 'deviation',
            description: 'Move the project from BID to AWARDED and derive its phase schedule from the recorded bid factors — the concrete "bid data already carries the schedule" step. A real business milestone; confirm with the human before calling.',
            args: '{}',
            async execute(_args, state, ctx) {
                if (!state.project) return { ok: false, message: 'no current project' };
                if (state.project.status !== 'BID') return { ok: false, message: `project is ${state.project.status}, not BID — already awarded?` };
                const phases = lib.project.deriveScheduleFromBidFactors(state.project.bid_factors);
                const created = await ctx.projectStore.createPhases(state.project.project_id, phases);
                if (!created.ok) return { ok: false, message: `phase creation failed: ${created.error}` };
                for (const p of phases) {
                    await ctx.projectStore.seedChecklist(state.project.project_id, p.phase_id);
                }
                const patched = await ctx.projectStore.patchProject(state.project.project_id, { status: 'AWARDED' });
                if (!patched.ok) return { ok: false, message: `status update failed: ${patched.error}` };
                const full = await ctx.projectStore.getProject(state.project.project_id);
                full.phases = phases;
                return { ok: true, message: `awarded — ${phases.length} phases scheduled, each with its checklist seeded`, project: full, data: { phases } };
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
