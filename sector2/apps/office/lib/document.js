// document.js — Phoenix Office
// Core document engine. See DESIGN.md for the full spec this implements —
// summarized:
//   - Fields are read+fill, not write: once a field is filled, it can
//     never be overwritten, even pre-signature, even by the same author.
//   - State machine: DRAFT -> PENDING_REVIEW -> SIGNED. Signing is a
//     custody handoff (the client signing / handing back), not a button.
//   - SIGNED is a full-document freeze: hash baseline set over every
//     field at that moment, zero fills or edits accepted afterward, by
//     anyone, ever.
//   - A real-world correction after signing is a new, separate document
//     (a change order) that references the original — never an edit to it.

const crypto = require('crypto');
const { machineFingerprint } = require('./fingerprint');

const STATES = ['DRAFT', 'PENDING_REVIEW', 'SIGNED'];

function nowIso() { return new Date().toISOString(); }

function deepClone(x) { return JSON.parse(JSON.stringify(x)); }

// Same double-hash shape as fingerprint.js/phoenix_auth.py, applied to the
// document's field content instead of hardware signals.
function contentHash(fields) {
  const s = JSON.stringify(fields, Object.keys(fields).sort());
  const sha3 = crypto.createHash('sha3-512').update(s, 'utf8').digest('hex');
  const blake2b = crypto.createHash('blake2b512').update(s, 'utf8').digest('hex');
  return { sha3, blake2b };
}

function hashesMatch(a, b) {
  return !!a && !!b && a.sha3 === b.sha3 && a.blake2b === b.blake2b;
}

// fieldNames: the document's defined slots, e.g. ['customer_name', 'parts',
// 'labor_hours', 'total']. All start unfilled (null) — DRAFT is not "freely
// editable," it's "every field currently empty."
function createDocument({ fieldNames, authorFingerprint, counterparty }) {
  if (!Array.isArray(fieldNames) || fieldNames.length === 0) {
    throw new Error('createDocument requires a non-empty fieldNames array');
  }
  const fp = authorFingerprint || machineFingerprint();
  const fields = {};
  fieldNames.forEach(name => { fields[name] = null; });

  return {
    version: 1,
    state: 'DRAFT',
    author_fingerprint: fp,
    counterparty: counterparty || null, // { phone, carrier, email }
    fields,
    hash: null,
    signed_at: null,
    supersedes: null, // set on a change order — { hash, signed_at } of the original
    history: [
      { at: nowIso(), event: 'FORGED', by: fp, state: 'DRAFT' }
    ],
  };
}

// Fill a currently-empty field. Rejects (does not throw) on: signed
// document, unknown field name, or a field that's already filled — all
// three are the same class of problem (an attempt to write where only
// read+fill is allowed), just at different scopes.
function fillField(doc, fieldName, value, byFingerprint) {
  if (doc.state === 'SIGNED') {
    return { allowed: false, reason: 'DOCUMENT_SIGNED', detail: 'document is fully immutable — no fills or edits, to any field, ever' };
  }
  if (!(fieldName in doc.fields)) {
    return { allowed: false, reason: 'UNKNOWN_FIELD', detail: `'${fieldName}' is not a defined field on this document` };
  }
  if (doc.fields[fieldName] !== null) {
    return { allowed: false, reason: 'FIELD_ALREADY_FILLED', detail: `'${fieldName}' was already filled and cannot be overwritten before signing` };
  }
  const next = deepClone(doc);
  next.fields[fieldName] = value;
  next.history.push({ at: nowIso(), event: 'FIELD_FILLED', field: fieldName, by: byFingerprint || doc.author_fingerprint, state: doc.state });
  return { allowed: true, document: next };
}

function assertState(doc, expected) {
  if (doc.state !== expected) {
    throw new Error(`expected state ${expected}, document is ${doc.state}`);
  }
}

function handToClient(doc) {
  assertState(doc, 'DRAFT');
  const next = deepClone(doc);
  next.state = 'PENDING_REVIEW';
  next.history.push({ at: nowIso(), event: 'HANDED_TO_CLIENT', by: doc.author_fingerprint, state: 'PENDING_REVIEW' });
  return next;
}

// The custody handoff that actually locks the document: client signs and
// hands it back. Hash baseline covers every field as they stand right now.
function sign(doc, signerFingerprint) {
  assertState(doc, 'PENDING_REVIEW');
  const next = deepClone(doc);
  next.state = 'SIGNED';
  next.hash = contentHash(doc.fields);
  next.signed_at = nowIso();
  next.history.push({ at: next.signed_at, event: 'SIGNED', by: signerFingerprint || 'unknown', state: 'SIGNED' });
  return next;
}

// Client sends it back for changes without signing — already-filled
// fields stay filled (no erasing progress), the document just goes back
// to DRAFT so the author can fill whatever remaining fields address the
// feedback.
function reject(doc, byFingerprint, reason) {
  assertState(doc, 'PENDING_REVIEW');
  const next = deepClone(doc);
  next.state = 'DRAFT';
  next.history.push({ at: nowIso(), event: 'REJECTED', by: byFingerprint || 'unknown', state: 'DRAFT', reason: reason || null });
  return next;
}

// Detect whether a SIGNED document's fields have been altered since
// signing. This is the tamper check — call it whenever a signed document
// is loaded/opened, not just on demand.
function verifyIntegrity(doc) {
  if (doc.state !== 'SIGNED') {
    return { signed: false, tampered: false, reason: 'document is not SIGNED, no baseline to check' };
  }
  if (!doc.hash) {
    return { signed: true, tampered: false, reason: 'no hash baseline recorded — pre-signing-fix legacy document' };
  }
  const actual = contentHash(doc.fields);
  return { signed: true, tampered: !hashesMatch(actual, doc.hash), expected: doc.hash, actual };
}

// A signed document can never be edited or filled directly — this always
// fails and reports what would have been an alteration attempt, for the
// caller to route to notify.js.
function attemptEdit(doc, fieldName, attemptedByFingerprint) {
  if (doc.state !== 'SIGNED') {
    return { allowed: false, reason: 'NOT_SIGNED_USE_FILL', detail: 'document is not signed yet — use fillField() instead' };
  }
  return {
    allowed: false,
    reason: 'ALTERATION_ATTEMPT',
    field: fieldName,
    attempted_by: attemptedByFingerprint || 'unknown',
    document_hash: doc.hash,
    at: nowIso(),
  };
}

// A correction on a SIGNED document must be its own new linked document,
// never an edit to the original.
function createChangeOrder(originalDoc, fieldNames, authorFingerprint) {
  if (originalDoc.state !== 'SIGNED') {
    throw new Error('change orders only apply to SIGNED documents — fill the draft directly instead');
  }
  const changeOrder = createDocument({ fieldNames, authorFingerprint, counterparty: originalDoc.counterparty });
  changeOrder.supersedes = { hash: originalDoc.hash, signed_at: originalDoc.signed_at };
  changeOrder.history.push({ at: nowIso(), event: 'CHANGE_ORDER_LINKED', by: changeOrder.author_fingerprint, state: 'DRAFT' });
  return changeOrder;
}

module.exports = {
  STATES, createDocument, fillField, handToClient, sign, reject,
  verifyIntegrity, attemptEdit, createChangeOrder, contentHash, hashesMatch,
};
