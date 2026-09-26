// test-agent.js — Phoenix Office (standalone) — Secretariat agent tests.
// New for the tool-using agent (ai-provider / agent-tools / agent-loop).
// Kept SEPARATE from test.js on purpose — that suite is the proven,
// byte-identical-to-Office engine suite; this one covers only the new,
// additive agent layer, so a failure here never gets confused with a
// regression in the document engine itself.
// Run: node test/test-agent.js

const assert = require('assert');
const { tryOllama, tryAnthropic } = require('../lib/ai-provider');
const { createAgentTools } = require('../lib/agent-tools');
const { createAgentLoop, parseModelReply } = require('../lib/agent-loop');
const { renderDocumentHtml } = require('../lib/document-html');
const documentLib = require('../lib/document');
const projectLib = require('../lib/project');
const fileFormat = require('../lib/file-format');

const tests = [];
function test(name, fn) { tests.push({ name, fn }); }

// ── ai-provider.js ────────────────────────────────────────────────────────
test('tryOllama resolves with text + via on a successful chat response', async () => {
    global.fetch = async (url) => {
        assert.ok(String(url).includes('/api/chat'));
        return { ok: true, json: async () => ({ message: { content: 'hello from ollama' } }) };
    };
    const r = await tryOllama({ system: 's', messages: [{ role: 'user', content: 'hi' }] });
    assert.strictEqual(r.text, 'hello from ollama');
    assert.ok(r.via.startsWith('ollama:'));
});

test('tryOllama rejects when Ollama is unreachable', async () => {
    global.fetch = async () => { throw new Error('ECONNREFUSED'); };
    await assert.rejects(() => tryOllama({ system: 's', messages: [] }));
});

test('tryOllama rejects on a non-ok HTTP status', async () => {
    global.fetch = async () => ({ ok: false, status: 500, json: async () => ({}) });
    await assert.rejects(() => tryOllama({ system: 's', messages: [] }), /ollama 500/);
});

test('tryAnthropic rejects immediately with no API key configured', async () => {
    delete process.env.PHOENIX_OFFICE_ANTHROPIC_KEY;
    delete process.env.ANTHROPIC_API_KEY;
    await assert.rejects(() => tryAnthropic({ system: 's', messages: [] }), /no API key/);
});

test('tryAnthropic resolves with text + via when a key is set and the call succeeds', async () => {
    process.env.PHOENIX_OFFICE_ANTHROPIC_KEY = 'test-key';
    global.fetch = async (url, opts) => {
        assert.ok(String(url).includes('api.anthropic.com'));
        assert.strictEqual(JSON.parse(opts.body).system, 's');
        return { ok: true, json: async () => ({ content: [{ text: 'hello from claude' }] }) };
    };
    const r = await tryAnthropic({ system: 's', messages: [{ role: 'user', content: 'hi' }] });
    assert.strictEqual(r.text, 'hello from claude');
    assert.ok(r.via.startsWith('api:'));
    delete process.env.PHOENIX_OFFICE_ANTHROPIC_KEY;
});

// ── agent-tools.js ─────────────────────────────────────────────────────────
function makeTools(overrides = {}) {
    return createAgentTools({
        lib: { document: documentLib, project: projectLib },
        listTemplates: overrides.listTemplates || (() => [
            { template: 'work-order', label: 'Work Order', fields: ['customer', 'description', 'total'] },
        ]),
        browseWorker: overrides.browseWorker || (async () => ({ ok: true, items: [] })),
        aiComplete: overrides.aiComplete || (async () => ({ text: 'drafted value', via: 'test' })),
    });
}

test('agent tool catalog only exposes the intended tools, correctly tiered', () => {
    const tools = makeTools();
    const names = tools.list.map(t => t.name).sort();
    assert.deepStrictEqual(names, [
        'advance_phase', 'award_project', 'check_phase_checklist', 'create_project',
        'create_project_document', 'draft_checklist_rationale', 'draft_field', 'export_pdf',
        'fill_field', 'hand_to_client', 'new_document', 'open_project', 'print_phase',
        'search_checklist_catalog', 'search_templates', 'search_workspace', 'set_bid_factor',
        'set_checklist_item', 'sign_document',
    ]);
    const tierOf = n => tools.get(n).tier;
    ['search_workspace', 'search_templates', 'new_document', 'draft_field', 'fill_field', 'export_pdf',
        'create_project', 'open_project', 'set_bid_factor', 'create_project_document',
        'check_phase_checklist', 'search_checklist_catalog', 'draft_checklist_rationale', 'print_phase']
        .forEach(n => assert.strictEqual(tierOf(n), 'base', `${n} should be base tier`));
    ['hand_to_client', 'sign_document', 'advance_phase', 'set_checklist_item', 'award_project']
        .forEach(n => assert.strictEqual(tierOf(n), 'deviation', `${n} should be deviation tier`));
});

test('never-exposed actions are simply absent from the catalog', () => {
    const tools = makeTools();
    ['delete_document', 'edit_signed_document', 'run_shell', 'send_notification', 'bypass_fill_once',
        'delete_project', 'ai_decides_compliance', 'bypass_checklist']
        .forEach(n => assert.strictEqual(tools.get(n), undefined, `${n} must not exist as a tool`));
});

test('new_document from a template creates a DRAFT with the template fields', async () => {
    const tools = makeTools();
    const r = await tools.get('new_document').execute({ template: 'work-order' }, {});
    assert.strictEqual(r.ok, true);
    assert.strictEqual(r.document.state, 'DRAFT');
    assert.deepStrictEqual(Object.keys(r.document.fields), ['customer', 'description', 'total']);
});

test('new_document rejects an unknown template', async () => {
    const tools = makeTools();
    const r = await tools.get('new_document').execute({ template: 'nope' }, {});
    assert.strictEqual(r.ok, false);
});

test('fill_field fills an empty field on the session document', async () => {
    const tools = makeTools();
    const state = { document: documentLib.createDocument({ fieldNames: ['customer'], authorFingerprint: 'FP' }) };
    const r = await tools.get('fill_field').execute({ field: 'customer', value: 'Dave' }, state);
    assert.strictEqual(r.ok, true);
    assert.strictEqual(r.document.fields.customer, 'Dave');
});

test('fill_field refuses to overwrite an already-filled field', async () => {
    const tools = makeTools();
    let doc = documentLib.createDocument({ fieldNames: ['customer'], authorFingerprint: 'FP' });
    doc = documentLib.fillField(doc, 'customer', 'Dave', 'FP').document;
    const state = { document: doc };
    const r = await tools.get('fill_field').execute({ field: 'customer', value: 'Someone Else' }, state);
    assert.strictEqual(r.ok, false);
    assert.match(r.message, /FIELD_ALREADY_FILLED/);
});

test('fill_field refuses to touch a SIGNED document', async () => {
    const tools = makeTools();
    let doc = documentLib.createDocument({ fieldNames: ['customer'], authorFingerprint: 'FP' });
    doc = documentLib.fillField(doc, 'customer', 'Dave', 'FP').document;
    doc = documentLib.handToClient(doc);
    doc = documentLib.sign(doc, 'FP');
    const r = await tools.get('fill_field').execute({ field: 'customer', value: 'x' }, { document: doc });
    assert.strictEqual(r.ok, false);
    assert.match(r.message, /DOCUMENT_SIGNED/);
});

test('search_workspace filters the worker\'s items by a case-insensitive query', async () => {
    const tools = makeTools({
        browseWorker: async () => ({ ok: true, items: [{ hex: 'aaa', state: 'SIGNED', counterparty: 'Miller Farms' }, { hex: 'bbb', state: 'DRAFT' }] }),
    });
    const r = await tools.get('search_workspace').execute({ query: 'miller' }, {});
    assert.strictEqual(r.ok, true);
    assert.strictEqual(r.data.length, 1);
    assert.strictEqual(r.data[0].hex, 'aaa');
});

test('search_workspace reports the worker error cleanly', async () => {
    const tools = makeTools({ browseWorker: async () => ({ ok: false, error: 'no worker configured' }) });
    const r = await tools.get('search_workspace').execute({}, {});
    assert.strictEqual(r.ok, false);
});

test('draft_field never writes — it only returns a suggested value', async () => {
    const tools = makeTools({ aiComplete: async () => ({ text: '"Replace worn brake pads"', via: 'test' }) });
    const state = { document: documentLib.createDocument({ fieldNames: ['description'], authorFingerprint: 'FP' }) };
    const r = await tools.get('draft_field').execute({ field: 'description' }, state);
    assert.strictEqual(r.ok, true);
    assert.strictEqual(r.data.value, 'Replace worn brake pads');
    assert.strictEqual(state.document.fields.description, null); // untouched
});

test('sign_document tier is deviation and calls ctx.sealDocument', async () => {
    const tools = makeTools();
    let doc = documentLib.createDocument({ fieldNames: ['customer'], authorFingerprint: 'FP' });
    doc = documentLib.fillField(doc, 'customer', 'Dave', 'FP').document;
    doc = documentLib.handToClient(doc);
    let sealed = false;
    const r = await tools.get('sign_document').execute({ by: 'FP' }, { document: doc }, { sealDocument: async () => { sealed = true; return { ok: true }; } });
    assert.strictEqual(r.ok, true);
    assert.strictEqual(r.document.state, 'SIGNED');
    assert.strictEqual(sealed, true);
});

test('sign_document ignores the model-supplied `by` when a signer resolver is wired (audit 2026-09-25)', async () => {
    const tools = makeTools();
    let doc = documentLib.createDocument({ fieldNames: ['customer'], authorFingerprint: 'FP' });
    doc = documentLib.fillField(doc, 'customer', 'Dave', 'FP').document;
    doc = documentLib.handToClient(doc);
    const ctx = { sealDocument: async () => ({ ok: true }), resolveSigner: async () => ({ author_id: 'a_gVERIFIED', email: 'v@example.com' }) };
    const r = await tools.get('sign_document').execute({ by: 'Dave the client' }, { document: doc }, ctx);
    assert.strictEqual(r.ok, true);
    const last = r.document.history[r.document.history.length - 1];
    assert.strictEqual(last.by, 'a_gVERIFIED');
});

test('sign_document refuses (never signs) when the signer resolver rejects — no Google sign-in', async () => {
    const tools = makeTools();
    let doc = documentLib.createDocument({ fieldNames: ['customer'], authorFingerprint: 'FP' });
    doc = documentLib.fillField(doc, 'customer', 'Dave', 'FP').document;
    doc = documentLib.handToClient(doc);
    let sealed = false;
    const ctx = { sealDocument: async () => { sealed = true; return { ok: true }; }, resolveSigner: async () => { throw new Error('Google sign-in required'); } };
    await assert.rejects(() => tools.get('sign_document').execute({ by: 'FP' }, { document: doc }, ctx), /Google sign-in required/);
    assert.strictEqual(sealed, false);
});

// ── Project Assist tools ─────────────────────────────────────────────────────
function makeMockProjectStore() {
    const projects = new Map();
    const checklists = new Map(); // phase_id -> items[]
    const decisions = [];
    return {
        calls: { createPhases: [], seedChecklist: [] },
        store: { projects, checklists, decisions },
        async createProject({ name, authorId, jobId }) {
            const project_id = `proj_${projects.size + 1}`;
            projects.set(project_id, { project_id, author_id: authorId, job_id: jobId, name, status: 'BID', bid_factors: {}, counterparty: null });
            return { ok: true, project_id };
        },
        async getProject(id) {
            const p = projects.get(id);
            if (!p) return { ok: false, error: 'not found' };
            return { ok: true, ...p };
        },
        async patchProject(id, patch) {
            const p = projects.get(id);
            if (!p) return { ok: false, error: 'not found' };
            Object.assign(p, patch);
            return { ok: true };
        },
        async createPhases(id, phases) {
            this.calls.createPhases.push({ id, phases });
            for (const p of phases) checklists.set(p.phase_id, []);
            return { ok: true, created: phases.length };
        },
        async seedChecklist(id, phaseId) {
            this.calls.seedChecklist.push({ id, phaseId });
            checklists.set(phaseId, [{ item_id: `item_${phaseId}_1`, label: 'PPE on site', source_type: 'OSHA', disposition: 'open' }]);
            return { ok: true, created: 1 };
        },
        async listChecklist(_id, phaseId) {
            return { ok: true, items: checklists.get(phaseId) || [] };
        },
        async searchChecklistCatalog() {
            return { ok: true, items: [{ catalog_id: 'x', phase_type: 'erection', source_type: 'OSHA', label: 'Fall protection plan' }] };
        },
        async decideChecklistItem(itemId, decision) {
            decisions.push({ itemId, ...decision });
            return { ok: true };
        },
        async patchPhase() { return { ok: true }; },
    };
}

test('create_project starts a new project and open_project loads it back', async () => {
    const tools = makeTools();
    const projectStore = makeMockProjectStore();
    const ctx = { projectStore, authorId: 'a_test' };
    const r1 = await tools.get('create_project').execute({ name: 'Smith Warehouse' }, {}, ctx);
    assert.strictEqual(r1.ok, true);
    assert.strictEqual(r1.project.name, 'Smith Warehouse');
    assert.strictEqual(r1.project.status, 'BID');

    const r2 = await tools.get('open_project').execute({ project_id: r1.project.project_id }, {}, ctx);
    assert.strictEqual(r2.ok, true);
    assert.strictEqual(r2.project.project_id, r1.project.project_id);
});

test('set_bid_factor merges the answer and returns the next unanswered question', async () => {
    const tools = makeTools();
    const projectStore = makeMockProjectStore();
    const ctx = { projectStore, authorId: 'a_test' };
    const created = await tools.get('create_project').execute({ name: 'Test Job' }, {}, ctx);
    const state = { project: created.project };

    const r = await tools.get('set_bid_factor').execute({ key: 'project_type', value: 'commercial' }, state, ctx);
    assert.strictEqual(r.ok, true);
    assert.strictEqual(r.project.bid_factors.project_type, 'commercial');
    assert.ok(r.data.next && r.data.next.key !== 'project_type', 'should advance past the just-answered question');
});

test('create_project_document auto-fills project_name and tags project/phase ids, never invents other fields', async () => {
    const tools = makeTools({
        listTemplates: () => [{ template: 'proposal', label: 'Proposal', fields: ['project_name', 'scope_of_work'] }],
    });
    const state = { project: { project_id: 'proj_1', name: 'Smith Warehouse', counterparty: null, phases: [] } };
    const r = await tools.get('create_project_document').execute({ template: 'proposal', phase_id: 'phase_1' }, state, {});
    assert.strictEqual(r.ok, true);
    assert.strictEqual(r.document.fields.project_name, 'Smith Warehouse');
    assert.strictEqual(r.document.fields.scope_of_work, null, 'unfillable field must stay null, never guessed');
    assert.strictEqual(r.document.project_id, 'proj_1');
    assert.strictEqual(r.document.phase_id, 'phase_1');
    assert.strictEqual(r.document.doc_role, 'proposal');
});

test('award_project derives phases from PM-doctrine template, seeds each checklist, and flips status to AWARDED', async () => {
    const tools = makeTools();
    const projectStore = makeMockProjectStore();
    const ctx = { projectStore, authorId: 'a_test' };
    const created = await tools.get('create_project').execute({ name: 'Test Job' }, {}, ctx);
    const state = { project: created.project };

    const r = await tools.get('award_project').execute({}, state, ctx);
    assert.strictEqual(r.ok, true);
    assert.strictEqual(r.project.status, 'AWARDED');
    assert.strictEqual(r.data.phases.length, projectLib.STANDARD_PHASE_TEMPLATE.length);
    assert.strictEqual(projectStore.calls.seedChecklist.length, projectLib.STANDARD_PHASE_TEMPLATE.length, 'every phase should get its checklist seeded');
    // No 'MONITORING_CONTROLLING' lifecycle stage — deliberate PMBOK-doctrine call (concurrent with Execution, not a phase of its own)
    assert.ok(!r.data.phases.some(p => p.lifecycle_stage === 'MONITORING_CONTROLLING'));
});

test('award_project refuses to re-award an already-awarded project', async () => {
    const tools = makeTools();
    const state = { project: { project_id: 'proj_1', status: 'AWARDED', bid_factors: {} } };
    const r = await tools.get('award_project').execute({}, state, { projectStore: makeMockProjectStore(), authorId: 'a_test' });
    assert.strictEqual(r.ok, false);
});

test('set_checklist_item requires a rationale — no silent/blank determinations', async () => {
    const tools = makeTools();
    const r = await tools.get('set_checklist_item').execute({ item_id: 'item_1', disposition: 'satisfied' }, {}, { projectStore: makeMockProjectStore(), authorId: 'a_test' });
    assert.strictEqual(r.ok, false);
});

test('set_checklist_item records a real determination with attribution', async () => {
    const tools = makeTools();
    const projectStore = makeMockProjectStore();
    const r = await tools.get('set_checklist_item').execute(
        { item_id: 'item_1', disposition: 'satisfied', rationale: 'Verified PPE on site by site walk 9/25.' },
        {}, { projectStore, authorId: 'a_field_super' }
    );
    assert.strictEqual(r.ok, true);
    assert.strictEqual(projectStore.store.decisions.length, 1);
    assert.strictEqual(projectStore.store.decisions[0].by, 'a_field_super');
});

// ── agent-loop.js ──────────────────────────────────────────────────────────
function scriptedAi(replies) {
    let i = 0;
    return async () => {
        if (i >= replies.length) throw new Error('scriptedAi ran out of replies');
        const text = replies[i++];
        return { text, via: 'test' };
    };
}

test('runTurn returns a final answer directly when the model gives one', async () => {
    const tools = makeTools();
    const loop = createAgentLoop({ tools, aiComplete: scriptedAi(['{"final":"hello there"}']) });
    const session = loop.newSession(null);
    const r = await loop.runTurn(session, 'hi');
    assert.strictEqual(r.state, 'done');
    assert.strictEqual(r.message, 'hello there');
});

test('a base-tier tool call executes immediately and the loop continues to a final answer', async () => {
    const tools = makeTools();
    const loop = createAgentLoop({ tools, aiComplete: scriptedAi([
        '{"tool":"new_document","args":{"fieldNames":["customer"]}}',
        '{"final":"started a new document for you"}',
    ]) });
    const session = loop.newSession(null);
    const r = await loop.runTurn(session, 'start a blank document');
    assert.strictEqual(r.state, 'done');
    assert.ok(r.document);
    assert.strictEqual(r.document.state, 'DRAFT');
    assert.ok(r.transcript.some(t => t.role === 'tool' && t.tool === 'new_document'));
});

test('a deviation-tier tool call pauses for confirmation instead of running', async () => {
    const tools = makeTools();
    const loop = createAgentLoop({ tools, aiComplete: scriptedAi([
        '{"tool":"hand_to_client","args":{}}',
    ]) });
    let doc = documentLib.createDocument({ fieldNames: ['customer'], authorFingerprint: 'FP' });
    const session = loop.newSession(doc);
    const r = await loop.runTurn(session, 'send it to the client');
    assert.strictEqual(r.state, 'confirm');
    assert.strictEqual(r.pending.toolName, 'hand_to_client');
    assert.strictEqual(r.document.state, 'DRAFT'); // not executed yet
});

test('approving a paused confirmation executes the tool and resumes the loop', async () => {
    const tools = makeTools();
    const loop = createAgentLoop({ tools, aiComplete: scriptedAi([
        '{"tool":"hand_to_client","args":{}}',
        '{"final":"handed off"}',
    ]) });
    const doc = documentLib.createDocument({ fieldNames: ['customer'], authorFingerprint: 'FP' });
    const session = loop.newSession(doc);
    await loop.runTurn(session, 'send it to the client');
    const r = await loop.resolveConfirm(session, true);
    assert.strictEqual(r.state, 'done');
    assert.strictEqual(r.document.state, 'PENDING_REVIEW');
});

test('denying a paused confirmation leaves the document untouched and tells the model', async () => {
    const tools = makeTools();
    const loop = createAgentLoop({ tools, aiComplete: scriptedAi([
        '{"tool":"sign_document","args":{}}',
        '{"final":"ok, not signing"}',
    ]) });
    const doc = documentLib.createDocument({ fieldNames: ['customer'], authorFingerprint: 'FP' });
    const session = loop.newSession(doc);
    await loop.runTurn(session, 'sign it');
    const r = await loop.resolveConfirm(session, false);
    assert.strictEqual(r.state, 'done');
    assert.strictEqual(r.document.state, 'DRAFT'); // sign never ran
    assert.ok(session.transcript.some(t => t.role === 'system' && /declined/.test(t.content)));
});

test('an unknown tool name does not crash the loop — it is reported back to the model', async () => {
    const tools = makeTools();
    const loop = createAgentLoop({ tools, aiComplete: scriptedAi([
        '{"tool":"delete_everything","args":{}}',
        '{"final":"my mistake — that tool does not exist"}',
    ]) });
    const session = loop.newSession(null);
    const r = await loop.runTurn(session, 'do something destructive');
    assert.strictEqual(r.state, 'done');
});

test('the loop reports a stall instead of looping forever when the model never finalizes', async () => {
    const tools = makeTools();
    const alwaysSearch = async () => ({ text: '{"tool":"search_templates","args":{}}', via: 'test' });
    const loop = createAgentLoop({ tools, aiComplete: alwaysSearch });
    const session = loop.newSession(null);
    const r = await loop.runTurn(session, 'keep searching forever');
    assert.strictEqual(r.state, 'error');
    assert.match(r.message, /stalled/);
});

test('plain non-JSON model text is treated as a final answer, not a crash', async () => {
    const tools = makeTools();
    const loop = createAgentLoop({ tools, aiComplete: scriptedAi(['Sure, I can help with that.']) });
    const session = loop.newSession(null);
    const r = await loop.runTurn(session, 'hi');
    assert.strictEqual(r.state, 'done');
    assert.strictEqual(r.message, 'Sure, I can help with that.');
});

test('a provider outage surfaces as a clean error state, not a throw', async () => {
    const tools = makeTools();
    const loop = createAgentLoop({ tools, aiComplete: async () => { throw new Error('no AI provider available'); } });
    const session = loop.newSession(null);
    const r = await loop.runTurn(session, 'hi');
    assert.strictEqual(r.state, 'error');
    assert.match(r.message, /no AI provider available/);
});

// ── document-html.js letterhead (brand.json is real on this checkout) ─────
test('renderDocumentHtml includes the letterhead when brand.json is present', () => {
    const html = renderDocumentHtml({ state: 'DRAFT', fields: { customer: 'Dave' }, counterparty: {} });
    assert.ok(html.includes('PBM Consulting Service'));
    assert.ok(html.includes('Chris Madsen'));
    // logo as an image LibreOffice renders (inline <svg> printed as text in a real PDF export)
    assert.match(html, /<img src="data:image\/svg\+xml;base64,[A-Za-z0-9+/=]+" width="\d+" height="\d+" alt="PBM/);
});

// ── parseModelReply — small-model failure modes found live 2026-09-22 ─────
test('parseModelReply flags near-miss JSON (missing brace) as malformed, not final', () => {
    const r = parseModelReply('{"tool": "new_document", "args": {"template": "work-order"}');
    assert.strictEqual(r.malformed, true);
});

test('parseModelReply flags valid JSON with the wrong shape as malformed, not final', () => {
    const r = parseModelReply('{"new_document": {"template": "work-order"}}');
    assert.strictEqual(r.malformed, true);
});

test('parseModelReply still treats genuine plain-text replies as final', () => {
    const r = parseModelReply('Sure, happy to help with that.');
    assert.strictEqual(r.final, 'Sure, happy to help with that.');
});

test('the loop repairs a malformed reply by re-prompting instead of surfacing broken JSON', async () => {
    const tools = makeTools();
    const loop = createAgentLoop({ tools, aiComplete: scriptedAi([
        '{"tool": "search_templates", "args": {}', // malformed — missing closing brace
        '{"final":"found your templates"}',
    ]) });
    const session = loop.newSession(null);
    const r = await loop.runTurn(session, 'what templates do you have?');
    assert.strictEqual(r.state, 'done');
    assert.strictEqual(r.message, 'found your templates');
});

// ── schedule timeline + chart (2026-09-26) ───────────────────────────────
const gantt = require('../lib/schedule-gantt');
const TL_PHASES = [
    { phase_id: 'a', label: 'Foundation', phase_type: 'foundation', sequence: 1, state: 'COMPLETE',
      estimated_duration_weeks: 2, started_at: '2026-10-01T08:00:00Z', completed_at: '2026-10-14T16:00:00Z' },
    { phase_id: 'b', label: 'Steel Erection', phase_type: 'erection', sequence: 2, state: 'IN_PROGRESS',
      estimated_duration_weeks: 2, started_at: '2026-10-15T08:00:00Z', schedule_notes: 'columns then beams' },
    { phase_id: 'c', label: 'Decking', phase_type: 'decking', sequence: 3, state: 'NOT_STARTED', estimated_duration_weeks: 1 },
];
const TL_OPTS = { bidFactors: { time_of_year: { start_month: '2026-10' } } };

test('timeline: baseline runs phases back to back from the bid start month', () => {
    const tl = projectLib.scheduleTimeline(TL_PHASES, { ...TL_OPTS, today: '2026-10-05' });
    assert.strictEqual(tl.start, '2026-10-01');
    assert.deepStrictEqual(tl.rows.map(r => [r.planned_start, r.planned_end]),
        [['2026-10-01', '2026-10-15'], ['2026-10-15', '2026-10-29'], ['2026-10-29', '2026-11-05']]);
    assert.strictEqual(tl.rows[1].notes, 'columns then beams');
});

test('timeline: green when done on time and running within plan', () => {
    const tl = projectLib.scheduleTimeline(TL_PHASES, { ...TL_OPTS, today: '2026-10-20' });
    assert.deepStrictEqual(tl.rows.map(r => r.status), ['green', 'green', 'green']);
});

test('timeline: yellow when a running phase is past its planned end by up to 25%', () => {
    const tl = projectLib.scheduleTimeline(TL_PHASES, { ...TL_OPTS, today: '2026-11-01' });   // erection planned end 10-29, 3 days over of 14
    assert.strictEqual(tl.rows[1].status, 'yellow');
    assert.strictEqual(tl.rows[1].days_over, 3);
});

test('timeline: red when more than 25% over', () => {
    const tl = projectLib.scheduleTimeline(TL_PHASES, { ...TL_OPTS, today: '2026-11-06' });   // 8 days over of 14
    assert.strictEqual(tl.rows[1].status, 'red');
});

test('timeline: red when it pushes past the target finish, even if barely late', () => {
    const tl = projectLib.scheduleTimeline(TL_PHASES, {
        bidFactors: { time_of_year: { start_month: '2026-10' }, schedule: { target_duration_weeks: 4 } }, today: '2026-10-30' });
    assert.strictEqual(tl.rows[1].status, 'red');                // target end 10-29, projected 10-30
});

test('timeline: a phase that should have started and has not turns yellow', () => {
    const tl = projectLib.scheduleTimeline([TL_PHASES[2]], { ...TL_OPTS, today: '2026-10-02' });
    assert.strictEqual(tl.rows[0].status, 'yellow');
});

test('timeline: phases saved without a duration fall back to the template weeks', () => {
    const tl = projectLib.scheduleTimeline([{ ...TL_PHASES[1], estimated_duration_weeks: null, state: 'NOT_STARTED', started_at: null }],
        { ...TL_OPTS, today: '2026-09-01' });
    assert.strictEqual(tl.rows[0].planned_weeks, 3);             // erection base_weeks
});

test('schedule chart: parses one line per trade and reports bad lines, never guesses', () => {
    const r = gantt.parseBreakdown('Steel | 2026-10-05 | 2026-10-23 | critical | bolt-up\nDeck | 10/26/2026 | 10/30/2026\nbroken line\nX | 2026-10-10 | 2026-10-01 | on');
    assert.strictEqual(r.rows.length, 2);
    assert.deepStrictEqual(r.rows.map(x => x.status), ['red', 'green']);
    assert.strictEqual(r.problems.length, 2);
});

test('schedule chart: export draws it for a Master schedule, as an image LibreOffice renders', () => {
    const html = renderDocumentHtml({ state: 'DRAFT', fields: {
        project_name: 'Test', phase_breakdown: 'Steel | 2026-10-05 | 2026-10-23 | over | bolt-up', date: '2026-10-20' } });
    assert.match(html, /<img src="data:image\/svg\+xml;base64,[A-Za-z0-9+/=]+" width="\d+" height="\d+"/);
    assert.doesNotMatch(html, /display:\s*flex/, 'LibreOffice ignores flexbox');
    const svg = gantt.scheduleSvg({ phase_breakdown: 'Steel | 2026-10-05 | 2026-10-23 | over | bolt-up' });
    assert.match(svg, new RegExp(gantt.COLORS.yellow));
    assert.match(svg, /bolt-up/);
});

test('schedule chart: other documents get no chart', () => {
    const html = renderDocumentHtml({ state: 'DRAFT', fields: { customer: 'Dave', total: '100' } });
    assert.doesNotMatch(html, /alt="Schedule by trade"/);
});

test('schedule chart: Project Assist timeline converts to the chart line format', () => {
    const tl = projectLib.scheduleTimeline(TL_PHASES, { ...TL_OPTS, today: '2026-11-01' });
    const text = gantt.breakdownFromTimeline(tl);
    const parsed = gantt.parseBreakdown(text);
    assert.strictEqual(parsed.problems.length, 0);
    assert.strictEqual(parsed.rows.length, 3);
    assert.strictEqual(parsed.rows[1].status, 'yellow');
});

// ── run ──────────────────────────────────────────────────────────────────
(async () => {
    let pass = 0, fail = 0;
    for (const t of tests) {
        try { await t.fn(); pass++; console.log(`  ok  ${t.name}`); }
        catch (e) { fail++; console.log(`FAIL  ${t.name}\n      ${e.message}`); }
    }
    console.log(`\n${pass} passed, ${fail} failed`);
    process.exit(fail ? 1 : 0);
})();
