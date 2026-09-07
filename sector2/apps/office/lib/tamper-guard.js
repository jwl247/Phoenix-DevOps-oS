// tamper-guard.js — Phoenix Office, Module 3 (2026-09-07)
//
// The composition point. document.js detects tampering (verifyIntegrity /
// attemptEdit) but stays a pure state machine — no network. notify.js
// builds notification payloads but stays transport-blind. This module is
// the seam that wires them together: check a SIGNED document, and on a
// real alteration, fire the standalone notification through
// office-notify-worker (which owns the escalate-until-acknowledged loop).
//
// Kept separate so document.js never has to require('./notify') or know a
// worker URL — matches how the rest of Phoenix keeps detection and
// delivery decoupled.
//
// Usage (author side, where Phoenix + config are available):
//   const { checkAndAlert } = require('./lib/tamper-guard');
//   const r = await checkAndAlert(doc, {
//     attempt: { field: 'total', at: new Date().toISOString() },
//     notifyWorkerUrl: process.env.OFFICE_NOTIFY_WORKER_URL
//                   || 'https://office-notify-worker.phoenix-jwl.workers.dev',
//     phoenixAuth: process.env.PHOENIX_AUTH,
//   });
//   // r.integrity  -> verifyIntegrity() result
//   // r.notified   -> notifyAlterationAttempt() result, or null if nothing was wrong

const { verifyIntegrity } = require('./document');
const { notifyAlterationAttempt, workerTransport } = require('./notify');
const { documentIdentityHash } = require('./file-format');

// Check a document's integrity. If (and only if) a SIGNED document has been
// altered since signing, send the counterparty notice. Never throws — a
// failed notification must not corrupt or block the operation that found
// the tampering; the failure is reported in the return value instead.
async function checkAndAlert(doc, opts = {}) {
  const integrity = verifyIntegrity(doc);

  if (!integrity.signed || !integrity.tampered) {
    return { integrity, notified: null };
  }

  const { notifyWorkerUrl, phoenixAuth, attempt, fetchImpl, send: sendOverride } = opts;

  let send = sendOverride;
  if (!send) {
    if (!notifyWorkerUrl) {
      return {
        integrity,
        notified: { sent: false, error: 'tamper detected but no notifyWorkerUrl / send given — cannot notify' },
      };
    }
    send = workerTransport({
      workerUrl: notifyWorkerUrl,
      auth: phoenixAuth,
      docHex: documentIdentityHash(doc),
      fetchImpl,
    });
  }

  const notified = await notifyAlterationAttempt(doc, attempt || {}, send);
  return { integrity, notified };
}

module.exports = { checkAndAlert };
