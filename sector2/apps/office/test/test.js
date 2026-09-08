// Phoenix Office — Phase 1 core engine tests. Plain Node + assert, no
// framework, matching the style already used for ScriptForge's converters.
// Run: node sector2/apps/office/test/test.js

const assert = require('assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const fingerprint = require('../lib/fingerprint');
const doc = require('../lib/document');
const notify = require('../lib/notify');
const fileFormat = require('../lib/file-format');
const tamperGuard = require('../lib/tamper-guard');
const identity = require('../lib/identity');

// Register-then-run so async tests are actually awaited (they weren't
// before — a rejected assertion in an async body just became an unhandled
// rejection and still counted as "ok"). Test bodies are unchanged.
const tests = [];
function test(name, fn) { tests.push({ name, fn }); }

// ── fingerprint.js ─────────────────────────────────────────────
test('machineFingerprint is a 128-char hex string (SHA3-512 output)', () => {
  const fp = fingerprint.machineFingerprint();
  assert.strictEqual(typeof fp, 'string');
  assert.strictEqual(fp.length, 128);
  assert.ok(/^[0-9a-f]{128}$/.test(fp), 'fingerprint must be lowercase hex');
});

test('machineFingerprint is stable across calls on the same machine', () => {
  const a = fingerprint.machineFingerprint();
  const b = fingerprint.machineFingerprint();
  assert.strictEqual(a, b);
});

test('doubleHash matches phoenix_auth.py\'s algorithm shape', () => {
  // sha3(combined), blake2b(combined), then sha3(sha3_hex + blake2b_hex) —
  // verify by reimplementing the three steps independently and comparing.
  const crypto = require('crypto');
  const signals = ['a', 'b', 'c'];
  const combined = signals.join('|');
  const sha3 = crypto.createHash('sha3-512').update(combined, 'utf8').digest('hex');
  const blake2b = crypto.createHash('blake2b512').update(combined, 'utf8').digest('hex');
  const expected = crypto.createHash('sha3-512').update(sha3 + blake2b, 'utf8').digest('hex');
  assert.strictEqual(fingerprint.doubleHash(signals), expected);
});

// ── document.js ────────────────────────────────────────────────
test('createDocument starts in DRAFT with all fields null', () => {
  const d = doc.createDocument({ fieldNames: ['customer_name', 'total'], authorFingerprint: 'AUTHOR_FP' });
  assert.strictEqual(d.state, 'DRAFT');
  assert.strictEqual(d.fields.customer_name, null);
  assert.strictEqual(d.fields.total, null);
  assert.strictEqual(d.history.length, 1);
  assert.strictEqual(d.history[0].event, 'FORGED');
});

test('fillField fills an empty field', () => {
  const d = doc.createDocument({ fieldNames: ['customer_name'], authorFingerprint: 'AUTHOR_FP' });
  const r = doc.fillField(d, 'customer_name', 'Jerry L.', 'AUTHOR_FP');
  assert.strictEqual(r.allowed, true);
  assert.strictEqual(r.document.fields.customer_name, 'Jerry L.');
});

test('fillField rejects overwriting an already-filled field, even pre-signature', () => {
  let d = doc.createDocument({ fieldNames: ['total'], authorFingerprint: 'AUTHOR_FP' });
  d = doc.fillField(d, 'total', '100', 'AUTHOR_FP').document;
  const r = doc.fillField(d, 'total', '999', 'AUTHOR_FP'); // same author, still DRAFT, still rejected
  assert.strictEqual(r.allowed, false);
  assert.strictEqual(r.reason, 'FIELD_ALREADY_FILLED');
  assert.strictEqual(d.fields.total, '100'); // original untouched
});

test('fillField rejects an unknown field name', () => {
  const d = doc.createDocument({ fieldNames: ['total'], authorFingerprint: 'AUTHOR_FP' });
  const r = doc.fillField(d, 'nonexistent', 'x', 'AUTHOR_FP');
  assert.strictEqual(r.allowed, false);
  assert.strictEqual(r.reason, 'UNKNOWN_FIELD');
});

test('handToClient requires DRAFT and moves to PENDING_REVIEW', () => {
  const d = doc.createDocument({ fieldNames: ['total'], authorFingerprint: 'AUTHOR_FP' });
  const pending = doc.handToClient(d);
  assert.strictEqual(pending.state, 'PENDING_REVIEW');
  assert.throws(() => doc.handToClient(pending)); // already past DRAFT
});

test('sign requires PENDING_REVIEW, sets hash + signed_at, freezes the document', () => {
  let d = doc.createDocument({ fieldNames: ['total'], authorFingerprint: 'AUTHOR_FP' });
  d = doc.fillField(d, 'total', '150', 'AUTHOR_FP').document;
  d = doc.handToClient(d);
  const signed = doc.sign(d, 'CLIENT_FP');
  assert.strictEqual(signed.state, 'SIGNED');
  assert.ok(signed.hash && signed.hash.sha3 && signed.hash.blake2b);
  assert.ok(signed.signed_at);
  assert.throws(() => doc.sign(signed, 'CLIENT_FP')); // can't sign twice
});

test('fillField rejects everything once SIGNED, even a previously-empty field', () => {
  let d = doc.createDocument({ fieldNames: ['total', 'notes'], authorFingerprint: 'AUTHOR_FP' });
  d = doc.fillField(d, 'total', '150', 'AUTHOR_FP').document;
  d = doc.handToClient(d);
  d = doc.sign(d, 'CLIENT_FP');
  const r = doc.fillField(d, 'notes', 'late addition', 'AUTHOR_FP'); // notes was still null
  assert.strictEqual(r.allowed, false);
  assert.strictEqual(r.reason, 'DOCUMENT_SIGNED');
});

test('verifyIntegrity is clean on an untouched signed document', () => {
  let d = doc.createDocument({ fieldNames: ['total'], authorFingerprint: 'AUTHOR_FP' });
  d = doc.fillField(d, 'total', '150', 'AUTHOR_FP').document;
  d = doc.handToClient(d);
  d = doc.sign(d, 'CLIENT_FP');
  const check = doc.verifyIntegrity(d);
  assert.strictEqual(check.signed, true);
  assert.strictEqual(check.tampered, false);
});

test('verifyIntegrity detects a direct mutation of a signed document\'s fields', () => {
  let d = doc.createDocument({ fieldNames: ['total'], authorFingerprint: 'AUTHOR_FP' });
  d = doc.fillField(d, 'total', '150', 'AUTHOR_FP').document;
  d = doc.handToClient(d);
  d = doc.sign(d, 'CLIENT_FP');
  // Simulate the exact "mechanic edits the file directly on disk" scenario —
  // bypassing fillField/attemptEdit entirely, straight at the data.
  const tampered = JSON.parse(JSON.stringify(d));
  tampered.fields.total = '999';
  const check = doc.verifyIntegrity(tampered);
  assert.strictEqual(check.tampered, true);
});

test('attemptEdit on a signed document always reports ALTERATION_ATTEMPT', () => {
  let d = doc.createDocument({ fieldNames: ['total'], authorFingerprint: 'AUTHOR_FP' });
  d = doc.fillField(d, 'total', '150', 'AUTHOR_FP').document;
  d = doc.handToClient(d);
  d = doc.sign(d, 'CLIENT_FP');
  const r = doc.attemptEdit(d, 'total', 'AUTHOR_FP');
  assert.strictEqual(r.allowed, false);
  assert.strictEqual(r.reason, 'ALTERATION_ATTEMPT');
  assert.strictEqual(r.attempted_by, 'AUTHOR_FP');
});

test('reject returns to DRAFT without erasing already-filled fields', () => {
  let d = doc.createDocument({ fieldNames: ['total', 'notes'], authorFingerprint: 'AUTHOR_FP' });
  d = doc.fillField(d, 'total', '150', 'AUTHOR_FP').document;
  d = doc.handToClient(d);
  d = doc.reject(d, 'CLIENT_FP', 'forgot the oil filter charge');
  assert.strictEqual(d.state, 'DRAFT');
  assert.strictEqual(d.fields.total, '150'); // not erased
  const r = doc.fillField(d, 'notes', 'added oil filter', 'AUTHOR_FP');
  assert.strictEqual(r.allowed, true); // still-empty field fillable after rejection
});

test('createChangeOrder requires SIGNED and links back to the original', () => {
  let d = doc.createDocument({ fieldNames: ['total'], authorFingerprint: 'AUTHOR_FP' });
  d = doc.fillField(d, 'total', '150', 'AUTHOR_FP').document;
  assert.throws(() => doc.createChangeOrder(d, ['total'], 'AUTHOR_FP')); // not signed yet
  d = doc.handToClient(d);
  d = doc.sign(d, 'CLIENT_FP');
  const co = doc.createChangeOrder(d, ['extra_charge'], 'AUTHOR_FP');
  assert.strictEqual(co.state, 'DRAFT');
  assert.deepStrictEqual(co.supersedes.hash, d.hash);
});

// ── notify.js ──────────────────────────────────────────────────
test('resolveTarget builds an SMS-gateway address from phone + known carrier', () => {
  const t = notify.resolveTarget({ phone: '(555) 123-4567', carrier: 'Verizon' });
  assert.strictEqual(t.via, 'sms-gateway');
  assert.strictEqual(t.address, '5551234567@vtext.com');
});

test('resolveTarget falls back to email when carrier is unknown/missing', () => {
  const t = notify.resolveTarget({ phone: '5551234567', carrier: 'some-unlisted-mvno', email: 'customer@example.com' });
  assert.strictEqual(t.via, 'email');
  assert.strictEqual(t.address, 'customer@example.com');
});

test('resolveTarget throws with no usable contact info', () => {
  assert.throws(() => notify.resolveTarget({}));
  assert.throws(() => notify.resolveTarget(null));
});

test('buildAlterationNotice produces a complete, correctly addressed notice', () => {
  let d = doc.createDocument({
    fieldNames: ['total'],
    authorFingerprint: 'AUTHOR_FP',
    counterparty: { phone: '5551234567', carrier: 'att' },
  });
  d = doc.fillField(d, 'total', '150', 'AUTHOR_FP').document;
  d = doc.handToClient(d);
  d = doc.sign(d, 'CLIENT_FP');
  const attempt = doc.attemptEdit(d, 'total', 'AUTHOR_FP');
  const notice = notify.buildAlterationNotice(d, attempt);
  assert.strictEqual(notice.to, '5551234567@txt.att.net');
  assert.strictEqual(notice.via, 'sms-gateway');
  assert.ok(notice.body.includes('cannot be altered'));
  assert.deepStrictEqual(notice.doc_hash, d.hash);
});

test('notifyAlterationAttempt calls the provided transport and reports success', async () => {
  let d = doc.createDocument({
    fieldNames: ['total'],
    authorFingerprint: 'AUTHOR_FP',
    counterparty: { email: 'customer@example.com' },
  });
  d = doc.fillField(d, 'total', '150', 'AUTHOR_FP').document;
  d = doc.handToClient(d);
  d = doc.sign(d, 'CLIENT_FP');
  const attempt = doc.attemptEdit(d, 'total', 'AUTHOR_FP');

  let sentNotice = null;
  const result = await notify.notifyAlterationAttempt(d, attempt, async (notice) => { sentNotice = notice; });
  assert.strictEqual(result.sent, true);
  assert.strictEqual(sentNotice.to, 'customer@example.com');
});

test('notifyAlterationAttempt reports failure without throwing when transport fails', async () => {
  let d = doc.createDocument({
    fieldNames: ['total'],
    authorFingerprint: 'AUTHOR_FP',
    counterparty: { email: 'customer@example.com' },
  });
  d = doc.fillField(d, 'total', '150', 'AUTHOR_FP').document;
  d = doc.handToClient(d);
  d = doc.sign(d, 'CLIENT_FP');
  const attempt = doc.attemptEdit(d, 'total', 'AUTHOR_FP');

  const result = await notify.notifyAlterationAttempt(d, attempt, async () => { throw new Error('SMTP down'); });
  assert.strictEqual(result.sent, false);
  assert.strictEqual(result.error, 'SMTP down');
});

// ── file-format.js ────────────────────────────────────────────
test('base58FromBytes matches phoenix-core/tools/intake.py\'s _base58() exactly', () => {
  // Cross-verified against a live Python run of the actual algorithm this
  // ports — see conversation record 2026-09-05. Hardcoding the vectors
  // here so the test doesn't require Python to be installed to run.
  const vectors = [
    ['deadbeefcafebabe', 'eFGDJTv8RoB'],
    ['0000000000000001', '11111112'],
    ['ffffffffffffffff', 'jpXCZedGfVQ'],
    ['00a1b2c3d4e5f607', '178QPGd5aEr'],
  ];
  for (const [hex, expected] of vectors) {
    assert.strictEqual(fileFormat.base58FromBytes(Buffer.from(hex, 'hex')), expected);
  }
});

test('buildHeader address is stable across field fills (identity, not content)', () => {
  let d = doc.createDocument({ fieldNames: ['total', 'notes'], authorFingerprint: 'AUTHOR_FP' });
  const headerBeforeFill = fileFormat.buildHeader(d);
  d = doc.fillField(d, 'total', '150', 'AUTHOR_FP').document;
  const headerAfterFill = fileFormat.buildHeader(d);
  assert.strictEqual(headerBeforeFill, headerAfterFill);
  assert.ok(headerBeforeFill.startsWith('USYS:') && headerBeforeFill.endsWith(':HEADER'));
});

test('buildFooter is null until signed, then matches the doc hash', () => {
  let d = doc.createDocument({ fieldNames: ['total'], authorFingerprint: 'AUTHOR_FP' });
  assert.strictEqual(fileFormat.buildFooter(d), null);
  d = doc.fillField(d, 'total', '150', 'AUTHOR_FP').document;
  d = doc.handToClient(d);
  d = doc.sign(d, 'CLIENT_FP');
  const footer = fileFormat.buildFooter(d);
  assert.ok(footer.startsWith('USYS:') && footer.includes(':FOOTER:') && footer.endsWith(d.hash.sha3));
});

test('saveOfficeFile -> loadOfficeFile round-trips a signed document cleanly', () => {
  let d = doc.createDocument({ fieldNames: ['total'], authorFingerprint: 'AUTHOR_FP' });
  d = doc.fillField(d, 'total', '150', 'AUTHOR_FP').document;
  d = doc.handToClient(d);
  d = doc.sign(d, 'CLIENT_FP');

  const tmpFile = path.join(os.tmpdir(), `office-test-${Date.now()}.office.json`);
  fileFormat.saveOfficeFile(tmpFile, d);
  const loaded = fileFormat.loadOfficeFile(tmpFile);
  fs.unlinkSync(tmpFile);

  assert.strictEqual(loaded.tampered, false);
  assert.strictEqual(loaded.document.fields.total, '150');
  assert.strictEqual(loaded.document.state, 'SIGNED');
});

test('loadOfficeFile detects a direct on-disk edit to a signed document (the real attack)', () => {
  let d = doc.createDocument({ fieldNames: ['total'], authorFingerprint: 'AUTHOR_FP' });
  d = doc.fillField(d, 'total', '150', 'AUTHOR_FP').document;
  d = doc.handToClient(d);
  d = doc.sign(d, 'CLIENT_FP');

  const tmpFile = path.join(os.tmpdir(), `office-test-tamper-${Date.now()}.office.json`);
  fileFormat.saveOfficeFile(tmpFile, d);

  // The actual attack this whole app exists to catch: someone opens the
  // saved file in a text editor and changes a number.
  const raw = JSON.parse(fs.readFileSync(tmpFile, 'utf8'));
  raw.body.fields.total = '999';
  fs.writeFileSync(tmpFile, JSON.stringify(raw, null, 2), 'utf8');

  const loaded = fileFormat.loadOfficeFile(tmpFile);
  fs.unlinkSync(tmpFile);

  assert.strictEqual(loaded.tampered, true);
  assert.ok(loaded.reason.includes('does not match'));
});

test('loadOfficeFile does not flag an unsigned (DRAFT) document as tampered', () => {
  const d = doc.createDocument({ fieldNames: ['total'], authorFingerprint: 'AUTHOR_FP' });
  const tmpFile = path.join(os.tmpdir(), `office-test-draft-${Date.now()}.office.json`);
  fileFormat.saveOfficeFile(tmpFile, d);
  const loaded = fileFormat.loadOfficeFile(tmpFile);
  fs.unlinkSync(tmpFile);
  assert.strictEqual(loaded.tampered, false);
  assert.strictEqual(loaded.footer, null);
});

// ── notify.js — worker transport (Module 3) ───────────────────
test('workerTransport POSTs { doc_hex, notice } with a bearer token to /notify', async () => {
  let captured = null;
  const fakeFetch = async (url, opts) => {
    captured = { url, opts };
    return { ok: true, status: 200, text: async () => JSON.stringify({ ok: true, notification_id: 1 }) };
  };
  const send = notify.workerTransport({
    workerUrl: 'https://office-notify-worker.example.dev/',
    auth: 'TESTTOKEN',
    docHex: 'abc123',
    fetchImpl: fakeFetch,
  });
  const res = await send({ to: 'x@y.com', via: 'email', subject: 's', body: 'b' });
  assert.strictEqual(captured.url, 'https://office-notify-worker.example.dev/notify');
  assert.strictEqual(captured.opts.method, 'POST');
  assert.strictEqual(captured.opts.headers.Authorization, 'Bearer TESTTOKEN');
  const body = JSON.parse(captured.opts.body);
  assert.strictEqual(body.doc_hex, 'abc123');
  assert.strictEqual(body.notice.to, 'x@y.com');
  assert.strictEqual(res.notification_id, 1);
});

test('workerTransport throws on a non-2xx worker response', async () => {
  const fakeFetch = async () => ({ ok: false, status: 500, text: async () => 'boom' });
  const send = notify.workerTransport({ workerUrl: 'https://w.dev', auth: 't', docHex: 'h', fetchImpl: fakeFetch });
  await assert.rejects(() => send({ to: 'a', via: 'email' }), /office-notify-worker 500/);
});

test('workerTransport requires workerUrl and docHex', () => {
  assert.throws(() => notify.workerTransport({ docHex: 'h', fetchImpl: () => {} }), /workerUrl/);
  assert.throws(() => notify.workerTransport({ workerUrl: 'x', fetchImpl: () => {} }), /docHex/);
});

// ── tamper-guard.js — detection + notification wired together ──
function signedDocWithCounterparty(counterparty) {
  let d = doc.createDocument({ fieldNames: ['total'], authorFingerprint: 'AUTHOR_FP', counterparty });
  d = doc.fillField(d, 'total', '150', 'AUTHOR_FP').document;
  d = doc.handToClient(d);
  return doc.sign(d, 'CLIENT_FP');
}

test('checkAndAlert on an untouched signed document sends nothing', async () => {
  const d = signedDocWithCounterparty({ email: 'c@x.com' });
  let called = false;
  const r = await tamperGuard.checkAndAlert(d, { send: async () => { called = true; } });
  assert.strictEqual(r.integrity.tampered, false);
  assert.strictEqual(r.notified, null);
  assert.strictEqual(called, false);
});

test('checkAndAlert on a DRAFT document sends nothing and does not throw', async () => {
  const d = doc.createDocument({ fieldNames: ['total'], authorFingerprint: 'AUTHOR_FP', counterparty: { email: 'c@x.com' } });
  const r = await tamperGuard.checkAndAlert(d, { send: async () => { throw new Error('should not be called'); } });
  assert.strictEqual(r.notified, null);
});

test('checkAndAlert on a tampered signed document fires the notification with the real doc identity', async () => {
  const d = signedDocWithCounterparty({ phone: '5551234567', carrier: 'verizon' });
  d.fields.total = '999'; // the mechanic edits the number after signing

  let payload = null;
  const send = async (notice) => { payload = notice; return { ok: true }; };
  const r = await tamperGuard.checkAndAlert(d, {
    attempt: { field: 'total', at: '2026-09-07T00:00:00Z' },
    send,
  });
  assert.strictEqual(r.integrity.tampered, true);
  assert.strictEqual(r.notified.sent, true);
  assert.strictEqual(payload.to, '5551234567@vtext.com');
  assert.strictEqual(payload.field, 'total');
});

test('checkAndAlert builds a worker transport from a URL when no send override is given', async () => {
  const d = signedDocWithCounterparty({ email: 'c@x.com' });
  d.fields.total = '999';
  let captured = null;
  const fakeFetch = async (url, opts) => {
    captured = { url, body: JSON.parse(opts.body) };
    return { ok: true, status: 200, text: async () => JSON.stringify({ ok: true, notification_id: 9 }) };
  };
  const r = await tamperGuard.checkAndAlert(d, {
    notifyWorkerUrl: 'https://office-notify-worker.phoenix-jwl.workers.dev',
    phoenixAuth: 'T',
    fetchImpl: fakeFetch,
    attempt: { field: 'total' },
  });
  assert.strictEqual(r.notified.sent, true);
  assert.strictEqual(captured.url, 'https://office-notify-worker.phoenix-jwl.workers.dev/notify');
  // doc_hex must be the file-format identity hash, not something ad hoc
  assert.strictEqual(captured.body.doc_hex, fileFormat.documentIdentityHash(d));
});

test('checkAndAlert reports a failed send without throwing', async () => {
  const d = signedDocWithCounterparty({ email: 'c@x.com' });
  d.fields.total = '999';
  const r = await tamperGuard.checkAndAlert(d, { send: async () => { throw new Error('carrier gateway 550'); } });
  assert.strictEqual(r.integrity.tampered, true);
  assert.strictEqual(r.notified.sent, false);
  assert.match(r.notified.error, /carrier gateway 550/);
});

test('checkAndAlert on a tampered doc with no transport at all reports the gap without throwing', async () => {
  const d = signedDocWithCounterparty({ email: 'c@x.com' });
  d.fields.total = '999';
  const r = await tamperGuard.checkAndAlert(d, { attempt: { field: 'total' } });
  assert.strictEqual(r.integrity.tampered, true);
  assert.strictEqual(r.notified.sent, false);
  assert.match(r.notified.error, /no notifyWorkerUrl/);
});

// ── identity.js — Module 5, pluggable author identity ─────────
test('credentialFor(fingerprint) returns the 128-hex hardware fingerprint', () => {
  const c = identity.credentialFor('fingerprint');
  assert.strictEqual(c.type, 'fingerprint');
  assert.ok(/^[0-9a-f]{128}$/.test(c.value));
});

test('credentialFor(windows) returns a SID on Windows, null elsewhere', () => {
  const c = identity.credentialFor('windows');
  if (process.platform === 'win32') {
    assert.ok(c && /^S-1-\d+(-\d+)+$/.test(c.value), 'expected a Windows SID');
  } else {
    assert.strictEqual(c, null);
  }
});

test('deriveAuthorId is deterministic and credential-specific', () => {
  const a = identity.deriveAuthorId({ type: 'fingerprint', value: 'abc' });
  const b = identity.deriveAuthorId({ type: 'fingerprint', value: 'abc' });
  const c = identity.deriveAuthorId({ type: 'fingerprint', value: 'xyz' });
  const d = identity.deriveAuthorId({ type: 'windows', value: 'abc' });
  assert.strictEqual(a, b);
  assert.notStrictEqual(a, c);
  assert.notStrictEqual(a, d); // same value, different type -> different id
  assert.ok(a.startsWith('a_f'));
});

test('resolveAuthor with no store derives a stable sovereign author_id from the fingerprint', async () => {
  const r1 = await identity.resolveAuthor();
  const r2 = await identity.resolveAuthor();
  assert.strictEqual(r1.source, 'derived');
  assert.strictEqual(r1.credential.type, 'fingerprint');
  assert.strictEqual(r1.author_id, r2.author_id);
  assert.strictEqual(r1.linked, false);
});

test('resolveAuthor uses the store author_id when the credential is already linked', async () => {
  const store = { lookup: async () => 'a_existing_person', link: async () => { throw new Error('should not link'); } };
  const r = await identity.resolveAuthor({ store });
  assert.strictEqual(r.author_id, 'a_existing_person');
  assert.strictEqual(r.source, 'd1');
  assert.strictEqual(r.linked, true);
});

test('resolveAuthor derives + links when the store has no match', async () => {
  let linked = null;
  const store = { lookup: async () => null, link: async (row) => { linked = row; return { ...row, already: false }; } };
  const r = await identity.resolveAuthor({ store });
  assert.strictEqual(r.source, 'derived');
  assert.strictEqual(r.linked, true);
  assert.strictEqual(linked.credential_type, 'fingerprint');
  assert.strictEqual(linked.author_id, r.author_id);
});

test('resolveAuthor never throws when the store is unreachable', async () => {
  const store = { lookup: async () => { throw new Error('D1 down'); }, link: async () => { throw new Error('D1 down'); } };
  const r = await identity.resolveAuthor({ store });
  assert.strictEqual(r.source, 'derived');
  assert.strictEqual(r.linked, false);
  assert.ok(r.author_id);
});

test('workerAuthStore.lookup hits GET /author/:type/:value with a bearer, maps 404 to null', async () => {
  const calls = [];
  const fakeFetch = async (url, o) => {
    calls.push({ url, o });
    if (url.includes('/author/fingerprint/')) return { status: 404, ok: false };
    return { status: 200, ok: true, json: async () => ({ author_id: 'a_x' }) };
  };
  const store = identity.workerAuthStore({ workerUrl: 'https://w.dev/', auth: 'T', fetchImpl: fakeFetch });
  assert.strictEqual(await store.lookup('fingerprint', 'deadbeef'), null);
  assert.strictEqual(calls[0].url, 'https://w.dev/author/fingerprint/deadbeef');
  assert.strictEqual(calls[0].o.headers.Authorization, 'Bearer T');
  assert.strictEqual(await store.lookup('windows', 'S-1-5-21'), 'a_x');
});

test('workerAuthStore.link POSTs /author/link', async () => {
  let body = null;
  const fakeFetch = async (url, o) => {
    body = JSON.parse(o.body);
    return { ok: true, status: 200, text: async () => JSON.stringify({ author_id: body.author_id, already: false }) };
  };
  const store = identity.workerAuthStore({ workerUrl: 'https://w.dev', auth: 'T', fetchImpl: fakeFetch });
  const out = await store.link({ author_id: 'a_1', credential_type: 'windows', credential_value: 'S-1-5-21-7' });
  assert.strictEqual(out.author_id, 'a_1');
  assert.strictEqual(body.credential_type, 'windows');
});

test('linkCredential requires a store and passes the right row shape', async () => {
  let row = null;
  const store = { link: async (r) => { row = r; return r; } };
  await identity.linkCredential({ authorId: 'a_1', type: 'google', value: '11576...', store });
  assert.deepStrictEqual(row, { author_id: 'a_1', credential_type: 'google', credential_value: '11576...' });
  await assert.rejects(() => identity.linkCredential({ authorId: 'a_1', type: 'google', value: 'x' }), /needs a store/);
});

test('googleSubFromIdToken decodes sub/email and rejects a wrong-audience token', () => {
  const mk = (payload) => {
    const b64 = (o) => Buffer.from(JSON.stringify(o)).toString('base64url');
    return `${b64({ alg: 'RS256' })}.${b64(payload)}.sig`;
  };
  const good = mk({ iss: 'https://accounts.google.com', aud: 'CID', sub: '11576', email: 'a@b.com', email_verified: true, exp: Math.floor(Date.now() / 1000) + 3600 });
  const claims = identity.googleSubFromIdToken(good, { clientId: 'CID' });
  assert.strictEqual(claims.sub, '11576');
  assert.strictEqual(claims.email, 'a@b.com');
  assert.strictEqual(claims.email_verified, true);
  assert.throws(() => identity.googleSubFromIdToken(good, { clientId: 'OTHER' }), /aud does not match/);
  const expired = mk({ iss: 'accounts.google.com', aud: 'CID', sub: '1', exp: 1 });
  assert.throws(() => identity.googleSubFromIdToken(expired, { clientId: 'CID' }), /expired/);
});

test('googleDeviceCodePoll surfaces authorization_pending as a coded error', async () => {
  const pending = async () => ({ ok: false, status: 428, json: async () => ({ error: 'authorization_pending' }) });
  await assert.rejects(
    () => identity.googleDeviceCodePoll({ clientId: 'C', deviceCode: 'D', fetchImpl: pending }),
    (e) => e.code === 'authorization_pending'
  );
  const done = async () => ({ ok: true, status: 200, json: async () => ({ id_token: 'x.y.z', access_token: 'a' }) });
  const tok = await identity.googleDeviceCodePoll({ clientId: 'C', deviceCode: 'D', fetchImpl: done });
  assert.strictEqual(tok.id_token, 'x.y.z');
});

test('an identity resolves cleanly into a document handoff (document.js unchanged)', async () => {
  const me = await identity.resolveAuthor();
  let d = doc.createDocument({ fieldNames: ['total'], authorFingerprint: me.author_id, counterparty: { email: 'c@x.com' } });
  assert.strictEqual(d.author_fingerprint, me.author_id);
  d = doc.fillField(d, 'total', '150', me.author_id).document;
  d = doc.handToClient(d);
  d = doc.sign(d, me.author_id);
  assert.strictEqual(d.history.find(h => h.event === 'SIGNED').by, me.author_id);
});

// ── Module 6 — the full lifecycle the dual-pane UI drives ─────
test('full UI lifecycle: whoami -> new -> fill -> hand -> sign -> save/open -> tamper -> verify+notify -> change order', async () => {
  const me = await identity.resolveAuthor({ prefer: 'fingerprint' });

  let d = doc.createDocument({
    fieldNames: ['customer', 'total'],
    authorFingerprint: me.author_id,
    counterparty: { email: 'cust@example.com' },
  });
  d = doc.fillField(d, 'customer', 'Acme Steel', me.author_id).document;
  d = doc.fillField(d, 'total', '1850.00', me.author_id).document;
  // the UI blocks an overwrite the same way document.js does
  assert.strictEqual(doc.fillField(d, 'total', '9999', me.author_id).allowed, false);

  d = doc.handToClient(d);
  assert.strictEqual(d.state, 'PENDING_REVIEW');
  d = doc.sign(d, me.author_id);
  assert.strictEqual(d.state, 'SIGNED');

  // office:qr
  assert.ok(fileFormat.buildHeader(d).startsWith('USYS:'));
  assert.ok(fileFormat.buildFooter(d).includes(':FOOTER:'));

  // office:save -> office:open round-trip
  const tmp = path.join(os.tmpdir(), `office-m6-${Date.now()}.office.json`);
  fileFormat.saveOfficeFile(tmp, d);
  assert.strictEqual(fileFormat.loadOfficeFile(tmp).tampered, false);

  // a mechanic edits the saved file; office:open flags it, office:verify notifies
  const raw = JSON.parse(fs.readFileSync(tmp, 'utf8'));
  raw.body.fields.total = '2850.00';
  fs.writeFileSync(tmp, JSON.stringify(raw, null, 2));
  const reopened = fileFormat.loadOfficeFile(tmp);
  assert.strictEqual(reopened.tampered, true);

  let alertedTo = null;
  const guard = await tamperGuard.checkAndAlert(reopened.document, {
    attempt: { field: 'total' },
    send: async (n) => { alertedTo = n.to; return { ok: true }; },
  });
  assert.strictEqual(guard.integrity.tampered, true);
  assert.strictEqual(guard.notified.sent, true);
  assert.strictEqual(alertedTo, 'cust@example.com');

  // office:change-order
  const co = doc.createChangeOrder(d, ['reason', 'new_total'], me.author_id);
  assert.strictEqual(co.state, 'DRAFT');
  assert.ok(co.supersedes && co.supersedes.hash);

  fs.unlinkSync(tmp);
});

// ── run ───────────────────────────────────────────────────────
(async () => {
  let passed = 0, failed = 0;
  for (const { name, fn } of tests) {
    try { await fn(); passed++; console.log('ok -', name); }
    catch (e) { failed++; console.error('FAIL -', name); console.error(e && e.stack || e); }
  }
  console.log(`\n${passed} passing${failed ? `, ${failed} FAILING` : ''}`);
  process.exit(failed ? 1 : 0);
})();
