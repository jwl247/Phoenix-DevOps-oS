// Smoke test for phoenix-office-worker: mock D1 + R2, drive the real
// fetch() handler. Same style as sector2/apps/lifefirst/meds-worker/test.mjs.
import worker from './index.js';

// ---- tiny in-memory D1 shim ----
const db = { office_notifications: [], office_authors: [], office_documents: [], _notifId: 0 };
const sent = [];

globalThis.fetch = async (url, opts) => {
  sent.push({ url: String(url), body: opts?.body?.toString?.() ?? null });
  return { ok: true, status: 200, text: async () => 'ok' };
};

function prepare(sql) {
  const s = sql.replace(/\s+/g, ' ').trim();
  let binds = [];
  const api = {
    bind: (...a) => { binds = a; return api; },
    async run() { return exec(s, binds); },
    async first() { const r = exec(s, binds); return r.rows[0] ?? null; },
    async all() { const r = exec(s, binds); return { results: r.rows }; },
  };
  return api;
}
function exec(s, b) {
  if (s.startsWith('INSERT INTO office_notifications')) {
    const row = {
      id: ++db._notifId, doc_hex: b[0], doc_hash: b[1], attempt_field: b[2], attempt_at: b[3],
      to_address: b[4], via: b[5], ack_token: b[6], escalation_level: b[7],
      send_count: 0, last_sent_at: null, last_error: null, acknowledged_at: null,
    };
    db.office_notifications.push(row);
    return { rows: [{ id: row.id }] };
  }
  if (s.startsWith('UPDATE office_notifications SET send_count')) {
    const r = db.office_notifications.find(x => x.id === b[2]);
    if (r) { r.send_count++; r.last_sent_at = b[0]; r.last_error = b[1]; }
    return { rows: [] };
  }
  if (s.startsWith('SELECT id, acknowledged_at FROM office_notifications WHERE ack_token'))
    return { rows: db.office_notifications.filter(r => r.ack_token === b[0]).map(r => ({ id: r.id, acknowledged_at: r.acknowledged_at })) };
  if (s.startsWith('UPDATE office_notifications SET acknowledged_at'))
    { const r = db.office_notifications.find(x => x.id === b[1]); if (r && !r.acknowledged_at) r.acknowledged_at = b[0]; return { rows: [] }; }

  if (s.startsWith('SELECT author_id, linked_at FROM office_authors'))
    return { rows: db.office_authors.filter(r => r.credential_type === b[0] && r.credential_value === b[1]) };
  if (s.startsWith('INSERT INTO office_authors')) {
    db.office_authors.push({ author_id: b[0], credential_type: b[1], credential_value: b[2], linked_at: b[3] });
    return { rows: [] };
  }

  if (s.startsWith('INSERT INTO office_documents')) {
    const hex = b[0];
    const existing = db.office_documents.find(r => r.hex === hex);
    const row = { hex, b58: b[1], state: b[2], author_id: b[3], counterparty_phone: b[4], counterparty_carrier: b[5], counterparty_email: b[6], hash_sha3: b[7], hash_blake2: b[8], supersedes_hex: b[9], signed_at: b[10], created_at: b[11], updated_at: b[12] };
    if (existing) Object.assign(existing, row);
    else db.office_documents.push(row);
    return { rows: [] };
  }
  if (s.startsWith('SELECT hex, b58, state, author_id, counterparty_email, supersedes_hex, created_at, signed_at, updated_at FROM office_documents WHERE state = ?')) {
    return { rows: db.office_documents.filter(r => r.state === b[0]).sort((a,c) => (c.updated_at||'').localeCompare(a.updated_at||'')).slice(0, b[1]) };
  }
  if (s.startsWith('SELECT hex, b58, state, author_id, counterparty_email, supersedes_hex, created_at, signed_at, updated_at FROM office_documents ORDER BY')) {
    return { rows: [...db.office_documents].sort((a,c) => (c.updated_at||'').localeCompare(a.updated_at||'')).slice(0, b[0]) };
  }
  if (s.startsWith('SELECT hex, state, supersedes_hex, created_at, signed_at FROM office_documents WHERE hex = ?')) {
    return { rows: db.office_documents.filter(r => r.hex === b[0]) };
  }
  if (s.startsWith('SELECT hex, state, supersedes_hex, created_at, signed_at FROM office_documents WHERE supersedes_hex IN')) {
    return { rows: db.office_documents.filter(r => b.includes(r.supersedes_hex)) };
  }

  throw new Error('unhandled SQL: ' + s);
}

const r2 = new Map();
const OFFICE_DOCS = {
  async put(key, bytes) { r2.set(key, bytes); },
  async get(key) {
    if (!r2.has(key)) return null;
    const bytes = r2.get(key);
    return { body: bytes };
  },
};

const runtime = new Map();
const OFFICE_RUNTIME = {
  async put(key, bytes) { runtime.set(key, bytes); },
  async get(key) {
    if (!runtime.has(key)) return null;
    const bytes = runtime.get(key);
    return { body: bytes, size: bytes.length || bytes.byteLength };
  },
  async head(key) {
    if (!runtime.has(key)) return null;
    const bytes = runtime.get(key);
    return { size: bytes.length || bytes.byteLength, uploaded: new Date() };
  },
};

const env = {
  OFFICE_DB: { prepare },
  OFFICE_DOCS,
  OFFICE_RUNTIME,
  OFFICE_AUTH: 'test-office-token',
  WORKER_PUBLIC_URL: 'https://phoenix-office-worker.test',
};
const H = { Authorization: 'Bearer test-office-token', 'Content-Type': 'application/json' };
const B = 'https://phoenix-office-worker.test';
let pass = 0, fail = 0;
const ok = (c, m) => { c ? (pass++, console.log('  ok  ' + m)) : (fail++, console.log('  FAIL ' + m)); };

// 1. health — no auth needed
{
  const r = await worker.fetch(new Request(B + '/health'), env);
  const j = await r.json();
  ok(r.status === 200 && j.db_bound === true && j.r2_bound === true, 'GET /health reports db_bound and r2_bound true');
}

// 2. documents: PUT rejects unauthorized
{
  const hexBad = 'deadbeefcafef00d1234567890abcdef';
  const r = await worker.fetch(new Request(B + '/documents/' + hexBad, { method: 'PUT', body: JSON.stringify({ body: { state: 'SIGNED' } }) }), env);
  ok(r.status === 401, 'PUT /documents/:hex without a bearer is rejected');
}

// 3. documents: PUT rejects a malformed hex
{
  const r = await worker.fetch(new Request(B + '/documents/not-hex!', { method: 'PUT', headers: H, body: JSON.stringify({ body: { state: 'SIGNED' } }) }), env);
  ok(r.status === 400, 'PUT /documents/:hex rejects a non-hex identity');
}

// 4. documents: real PUT stores bytes in R2 and upserts office_documents
const hex = 'a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2';
const envelope = JSON.stringify({
  header: 'USYS:xyz:HEADER', footer: 'USYS:xyz:FOOTER:abc',
  body: {
    state: 'SIGNED', signed_at: '2026-09-22T00:00:00.000Z',
    history: [{ at: '2026-09-21T00:00:00.000Z', by: 'a_f1234' }],
    fields: { customer: 'Jane Doe', total: '450' },
    counterparty: { phone: '5551234567', carrier: 'verizon', email: null },
    hash: { sha3: 'abc123', blake2: 'def456' },
  },
});
{
  const r = await worker.fetch(new Request(B + '/documents/' + hex, { method: 'PUT', headers: H, body: envelope }), env);
  const j = await r.json();
  ok(r.status === 200 && j.ok && j.bytes === envelope.length, 'PUT /documents/:hex stores the real byte count');
  ok(r2.has(hex), 'the document bytes actually landed in the mock R2 store');
  const row = db.office_documents.find(x => x.hex === hex);
  ok(!!row && row.state === 'SIGNED' && row.hash_sha3 === 'abc123', 'office_documents row was upserted from the envelope');
}

// 5. documents: GET without auth is rejected
{
  const r = await worker.fetch(new Request(B + '/documents/' + hex), env);
  ok(r.status === 401, 'GET /documents/:hex without a bearer is rejected');
}

// 6. documents: GET fetches the same bytes back
{
  const r = await worker.fetch(new Request(B + '/documents/' + hex, { headers: H }), env);
  const text = await r.text();
  ok(r.status === 200 && text === envelope, 'GET /documents/:hex round-trips the exact bytes that were PUT');
}

// 7. documents: GET on a hex nobody ever stored is a 404
{
  const missing = 'ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff';
  const r = await worker.fetch(new Request(B + '/documents/' + missing, { headers: H }), env);
  ok(r.status === 404, 'GET /documents/:hex on an unstored hash is 404, not a silent empty body');
}

// 8. two different documents never collide — this is the entire point of
// content-addressing instead of filename-hex. Store a second, unrelated
// document and confirm the first one's bytes are untouched.
const hex2 = 'b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3';
const envelope2 = JSON.stringify({ header: 'x', footer: 'y', body: { state: 'SIGNED', fields: { customer: 'A Totally Different Customer' }, history: [{ at: 't', by: 'a_x' }] } });
{
  await worker.fetch(new Request(B + '/documents/' + hex2, { method: 'PUT', headers: H, body: envelope2 }), env);
  const r1 = await worker.fetch(new Request(B + '/documents/' + hex, { headers: H }), env);
  const r2text = await r1.text();
  ok(r2text === envelope, 'storing a second, unrelated document leaves the first document\'s bytes untouched (no filename-keyed collision)');
}

// 9. notify still works end to end (unchanged logic, renamed env vars)
{
  const r = await worker.fetch(new Request(B + '/notify', {
    method: 'POST', headers: H,
    body: JSON.stringify({ doc_hex: hex, notice: { to: '5551234567@vtext.com', via: 'sms-gateway', subject: 'x', body: 'y' } }),
  }), env);
  const j = await r.json();
  ok(r.status === 200 && j.recorded === true, 'POST /notify still records a notification row under the renamed OFFICE_DB binding');
}

// 10. browse: lists both sealed documents, newest first
{
  const r = await worker.fetch(new Request(B + '/documents?limit=10', { headers: H }), env);
  const j = await r.json();
  ok(r.status === 200 && j.ok && j.items.length === 2, 'GET /documents lists both sealed documents');
  ok(j.items[0].hex === hex2, 'GET /documents orders newest-first by updated_at');
}

// 11. browse: state filter narrows the list
{
  const r = await worker.fetch(new Request(B + '/documents?state=SIGNED', { headers: H }), env);
  const j = await r.json();
  ok(j.items.length === 2, 'GET /documents?state=SIGNED matches both (both are SIGNED)');
}

// 12. history: an unknown/unsealed hex returns an empty chain, not an error
{
  const unknown = 'c'.repeat(64);
  const r = await worker.fetch(new Request(B + '/documents/' + unknown + '/history', { headers: H }), env);
  const j = await r.json();
  ok(r.status === 200 && j.ok && j.chain.length === 0, 'GET /documents/:hex/history on an unsealed hex returns an empty chain, not a 404');
}

// 13. history: a real change-order chain — hex3 supersedes hex
const hex3 = 'd3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4';
const envelope3 = JSON.stringify({ header: 'x', footer: 'y', body: {
  state: 'SIGNED', supersedes_hex: hex, history: [{ at: 't2', by: 'a_x' }],
  fields: { reason_for_change: 'price correction' },
} });
{
  await worker.fetch(new Request(B + '/documents/' + hex3, { method: 'PUT', headers: H, body: envelope3 }), env);
  const r = await worker.fetch(new Request(B + '/documents/' + hex + '/history', { headers: H }), env);
  const j = await r.json();
  ok(j.chain.length === 2 && j.chain[0].hex === hex && j.chain[1].hex === hex3,
    'GET /documents/:hex/history walks the supersedes_hex chain, original then the change order');
  const r2h = await worker.fetch(new Request(B + '/documents/' + hex3 + '/history', { headers: H }), env);
  const j2 = await r2h.json();
  ok(j2.chain.length === 2 && j2.chain[0].hex === hex,
    'the same chain is returned when asking from either end (change order or original)');
}

// 14. runtime assets: auth + round trip (upload happens out-of-band via
// `wrangler r2 object put`, not through this worker — seed the mock directly)
{
  const r = await worker.fetch(new Request(B + '/runtime/libreoffice-portable-win64.zip'), env);
  ok(r.status === 401, 'GET /runtime/:name without a bearer is rejected');
}
{
  await runtime.set('libreoffice-portable-win64.zip', new TextEncoder().encode('fake-zip-bytes'));
  const r = await worker.fetch(new Request(B + '/runtime/libreoffice-portable-win64.zip', { headers: H }), env);
  const text = await r.text();
  ok(r.status === 200 && text === 'fake-zip-bytes', 'GET /runtime/:name streams back the stored asset');
}
{
  const r = await worker.fetch(new Request(B + '/runtime/does-not-exist.zip', { headers: H }), env);
  ok(r.status === 404, 'GET /runtime/:name on a missing asset is a real 404');
}
{
  // A literal "../" collapses during URL parsing before this worker ever
  // sees it (browsers/undici normalize dot-segments), so that shape never
  // reaches the route at all — it 404s upstream of the regex, which is a
  // stronger guarantee, not a weaker one. What the regex actually guards
  // against is an encoded slash smuggled through as a "name" so it can't
  // be used to address something outside the flat runtime-asset namespace.
  const r = await worker.fetch(new Request(B + '/runtime/foo%2Fbar', { headers: H }), env);
  ok(r.status === 400, 'GET /runtime/:name rejects a name containing an (encoded) slash');
}

console.log(`\n${pass} passing, ${fail} failing`);
if (fail > 0) process.exit(1);
