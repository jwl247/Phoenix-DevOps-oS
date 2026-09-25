// test.mjs — pbm-leads-worker
// Run: node test.mjs

const assert = (await import('assert')).default;

// Deterministic RNG so we can drive the full lead -> verify flow without
// a real-world code leak in the test itself. generateCode() does
// `crypto.getRandomValues(new Uint32Array(1))[0] % 1000000` — pin the
// first random value so we can compute the exact expected code.
const FIXED_RANDOM = 123456;
// globalThis.crypto itself is a read-only accessor in Node — but its own
// properties are plain and mutable, so patch getRandomValues in place
// rather than replacing the whole object. subtle.digest (used by
// sha256Hex) is untouched.
globalThis.crypto.getRandomValues = (arr) => { arr[0] = FIXED_RANDOM; return arr; };
const EXPECTED_CODE = String(FIXED_RANDOM % 1000000).padStart(6, '0');

const worker = await import('./index.js');
const { isValidEmail, referenceNumber, sha256Hex } = worker;
const app = worker.default;

function makeFakeDB() {
    const leads = [];
    let nextId = 1;
    return {
        leads,
        prepare(sql) {
            let params = [];
            return {
                bind(...p) { params = p; return this; },
                async first() {
                    if (sql.includes('SELECT id FROM leads') || sql.includes('SELECT * FROM leads')) {
                        const [email] = params;
                        const rows = leads.filter(l => l.email === email && !l.verified_at).sort((a, b) => b.id - a.id);
                        return rows[0] || null;
                    }
                    return null;
                },
                async run() {
                    if (sql.startsWith('INSERT INTO leads')) {
                        const [name, business_name, email, phone, code_hash, code_expires_at] = params;
                        const row = { id: nextId++, name, business_name, email, phone, code_hash, code_expires_at, attempt_count: 0, verified_at: null, hubspot_synced_at: null };
                        leads.push(row);
                        return { meta: { last_row_id: row.id } };
                    }
                    if (sql.startsWith('UPDATE leads SET name=')) {
                        const [name, business_name, phone, code_hash, code_expires_at, id] = params;
                        Object.assign(leads.find(l => l.id === id), { name, business_name, phone, code_hash, code_expires_at, attempt_count: 0 });
                        return { meta: {} };
                    }
                    if (sql.startsWith('UPDATE leads SET attempt_count')) {
                        leads.find(l => l.id === params[0]).attempt_count++;
                        return { meta: {} };
                    }
                    if (sql.includes("SET verified_at")) {
                        leads.find(l => l.id === params[0]).verified_at = new Date().toISOString();
                        return { meta: {} };
                    }
                    if (sql.includes('SET hubspot_synced_at')) {
                        leads.find(l => l.id === params[0]).hubspot_synced_at = new Date().toISOString();
                        return { meta: {} };
                    }
                    return { meta: {} };
                },
            };
        },
    };
}

function req(path, method, body) {
    return new Request(`https://pbm-leads-worker.example/${path}`, {
        method, headers: { 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined,
    });
}

const tests = [];
function test(name, fn) { tests.push({ name, fn }); }

test('isValidEmail rejects garbage, accepts a real address', () => {
    assert.strictEqual(isValidEmail('not-an-email'), false);
    assert.strictEqual(isValidEmail('dave@example.com'), true);
});

test('referenceNumber is stable and year-prefixed', () => {
    const year = new Date().getUTCFullYear();
    assert.strictEqual(referenceNumber(7), `PBM-${year}-000007`);
});

test('POST /lead rejects a missing business_name', async () => {
    const env = { DB: makeFakeDB() };
    const res = await app.fetch(req('lead', 'POST', { email: 'a@b.com' }), env);
    assert.strictEqual(res.status, 400);
});

test('POST /lead HTML-escapes the visitor name in the verification email (audit 2026-09-25)', async () => {
    const env = { DB: makeFakeDB(), RESEND_API_KEY: 'test-key' };
    const realFetch = globalThis.fetch;
    let html = null;
    globalThis.fetch = async (url, opts) => { html = JSON.parse(opts.body).html; return new Response('{}', { status: 200 }); };
    try {
        const res = await app.fetch(req('lead', 'POST', { name: '<a href="https://evil.example">Click</a>', business_name: 'Acme', email: 'x@example.com' }), env);
        assert.strictEqual(res.status, 200);
    } finally { globalThis.fetch = realFetch; }
    assert.ok(html && !html.includes('<a href="https://evil.example">'), 'raw markup must not reach the email');
    assert.ok(html.includes('&lt;a href=&quot;https://evil.example&quot;&gt;'));
});

test('POST /lead rejects oversized fields', async () => {
    const env = { DB: makeFakeDB() };
    const res = await app.fetch(req('lead', 'POST', { business_name: 'A'.repeat(5000), email: 'a@b.com' }), env);
    assert.strictEqual(res.status, 400);
});

test('POST /lead rejects an invalid email', async () => {
    const env = { DB: makeFakeDB() };
    const res = await app.fetch(req('lead', 'POST', { business_name: 'Acme', email: 'nope' }), env);
    assert.strictEqual(res.status, 400);
});

test('POST /lead succeeds, reports send failure honestly with no RESEND_API_KEY', async () => {
    const env = { DB: makeFakeDB() };
    const res = await app.fetch(req('lead', 'POST', { business_name: 'Acme Roofing', email: 'dave@acme.com', name: 'Dave' }), env);
    const body = await res.json();
    assert.strictEqual(res.status, 200);
    assert.strictEqual(body.ok, true);
    assert.strictEqual(body.sent, false);
    assert.match(body.reference, /^PBM-\d{4}-\d{6}$/);
    assert.strictEqual(body.turnstileEnforced, false); // no TURNSTILE_SECRET configured
});

test('a resubmission before verifying reuses the same row, not a duplicate', async () => {
    const env = { DB: makeFakeDB() };
    await app.fetch(req('lead', 'POST', { business_name: 'Acme Roofing', email: 'dave@acme.com' }), env);
    await app.fetch(req('lead', 'POST', { business_name: 'Acme Roofing LLC', email: 'dave@acme.com' }), env);
    assert.strictEqual(env.DB.leads.length, 1);
    assert.strictEqual(env.DB.leads[0].business_name, 'Acme Roofing LLC');
});

test('full flow: /lead then /verify with the real code succeeds', async () => {
    const env = { DB: makeFakeDB() };
    const leadRes = await app.fetch(req('lead', 'POST', { business_name: 'Acme Roofing', email: 'dave@acme.com' }), env);
    assert.strictEqual((await leadRes.json()).ok, true);

    const verifyRes = await app.fetch(req('verify', 'POST', { email: 'dave@acme.com', code: EXPECTED_CODE }), env);
    const verifyBody = await verifyRes.json();
    assert.strictEqual(verifyRes.status, 200);
    assert.strictEqual(verifyBody.ok, true);
    assert.strictEqual(env.DB.leads[0].verified_at !== null, true);
});

test('/verify rejects a wrong code without revealing the real one', async () => {
    const env = { DB: makeFakeDB() };
    await app.fetch(req('lead', 'POST', { business_name: 'Acme Roofing', email: 'dave@acme.com' }), env);
    const res = await app.fetch(req('verify', 'POST', { email: 'dave@acme.com', code: '000000' }), env);
    const body = await res.json();
    assert.strictEqual(res.status, 401);
    assert.strictEqual(body.ok, false);
    assert.strictEqual(env.DB.leads[0].verified_at, null);
});

test('/verify locks out after 5 wrong attempts', async () => {
    const env = { DB: makeFakeDB() };
    await app.fetch(req('lead', 'POST', { business_name: 'Acme Roofing', email: 'dave@acme.com' }), env);
    for (let i = 0; i < 5; i++) {
        await app.fetch(req('verify', 'POST', { email: 'dave@acme.com', code: '000000' }), env);
    }
    const res = await app.fetch(req('verify', 'POST', { email: 'dave@acme.com', code: EXPECTED_CODE }), env);
    assert.strictEqual(res.status, 429);
});

test('/verify rejects an expired code', async () => {
    const env = { DB: makeFakeDB() };
    await app.fetch(req('lead', 'POST', { business_name: 'Acme Roofing', email: 'dave@acme.com' }), env);
    env.DB.leads[0].code_expires_at = new Date(Date.now() - 1000).toISOString(); // force expiry
    const res = await app.fetch(req('verify', 'POST', { email: 'dave@acme.com', code: EXPECTED_CODE }), env);
    assert.strictEqual(res.status, 410);
});

test('/verify with no pending lead for that email reports not found', async () => {
    const env = { DB: makeFakeDB() };
    const res = await app.fetch(req('verify', 'POST', { email: 'nobody@nowhere.com', code: '123456' }), env);
    assert.strictEqual(res.status, 404);
});

test('/health reports transport and enforcement state honestly', async () => {
    const env = { DB: makeFakeDB() };
    const res = await app.fetch(new Request('https://x/health'), env);
    const body = await res.json();
    assert.strictEqual(body.db_bound, true);
    assert.strictEqual(body.transport, 'NONE');
    assert.strictEqual(body.turnstile_enforced, false);
    assert.strictEqual(body.hubspot_wired, false);
});

test('verified lead syncs to HubSpot when a token is configured', async () => {
    let hubspotCalled = false;
    const realFetch = globalThis.fetch;
    globalThis.fetch = async (url, opts) => {
        if (String(url).includes('hubapi.com')) { hubspotCalled = true; return new Response('{}', { status: 200 }); }
        return realFetch(url, opts);
    };
    const env = { DB: makeFakeDB(), HUBSPOT_PRIVATE_APP_TOKEN: 'fake-token' };
    await app.fetch(req('lead', 'POST', { business_name: 'Acme Roofing', email: 'dave@acme.com' }), env);
    const res = await app.fetch(req('verify', 'POST', { email: 'dave@acme.com', code: EXPECTED_CODE }), env);
    const body = await res.json();
    globalThis.fetch = realFetch;
    assert.strictEqual(hubspotCalled, true);
    assert.strictEqual(body.hubspotSynced, true);
});

(async () => {
    let pass = 0, fail = 0;
    for (const t of tests) {
        try { await t.fn(); pass++; console.log(`  ok  ${t.name}`); }
        catch (e) { fail++; console.log(`FAIL  ${t.name}\n      ${e.message}`); }
    }
    console.log(`\n${pass} passed, ${fail} failed`);
    process.exit(fail ? 1 : 0);
})();
