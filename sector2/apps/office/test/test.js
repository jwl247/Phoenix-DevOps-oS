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

let passed = 0;
function test(name, fn) {
  fn();
  passed++;
  console.log('ok -', name);
}

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

console.log(`\n${passed} passing`);
