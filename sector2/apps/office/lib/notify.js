// notify.js — Phoenix Office
// Builds the alteration-attempt notification: who to reach and what to
// say. Deliberately NOT Life First's Module 6 engine — a customer has no
// reason to be a Life First user, and this exists to protect them, so it
// can't require them to already be in Phoenix's ecosystem. See DESIGN.md
// "Alteration attempts trigger a standalone notification".
//
// Delivery (the actual send) is intentionally pluggable — this module only
// builds correct, testable payloads. Wiring a real transport (Cloudflare
// Email Workers, per DESIGN.md) is an infrastructure step, not a code gap:
// pass a `send(message)` function in and this module stays transport-blind.

const CARRIER_GATEWAYS = {
  verizon: 'vtext.com',
  att: 'txt.att.net',
  tmobile: 'tmomail.net',
  sprint: 'messaging.sprintpcs.com',
  boost: 'sms.myboostmobile.com',
  cricket: 'sms.cricketwireless.net',
  metropcs: 'mymetropcs.com',
  uscellular: 'email.uscc.net',
};

// Resolves the document's counterparty contact into a single send target.
// Prefers the SMS gateway (phone + known carrier); falls back to plain
// email when there's no carrier on file — per Jerry (2026-09-05), carrier
// collection itself isn't expected to be a real blocker since the
// customer benefits from providing it.
function resolveTarget(counterparty) {
  if (!counterparty) {
    throw new Error('no counterparty contact info on this document');
  }
  const { phone, carrier, email } = counterparty;
  if (phone && carrier) {
    const domain = CARRIER_GATEWAYS[String(carrier).toLowerCase()];
    if (domain) {
      const digits = String(phone).replace(/\D/g, '');
      if (digits.length >= 10) {
        return { via: 'sms-gateway', address: `${digits}@${domain}` };
      }
    }
  }
  if (email) {
    return { via: 'email', address: email };
  }
  throw new Error('no usable contact info on this document — need (phone + a known carrier) or an email');
}

function buildAlterationNotice(doc, attempt) {
  const target = resolveTarget(doc.counterparty);
  const detectedAt = (attempt && attempt.at) || new Date().toISOString();
  return {
    to: target.address,
    via: target.via,
    subject: 'Alteration attempt on your signed document',
    body:
      'An attempt was made to change a document that was already signed and ' +
      `locked on ${doc.signed_at || 'an earlier date'}. ` +
      'The original content is unaffected — it cannot be altered. ' +
      'If you did not expect this, contact the issuer directly. ' +
      `(detected ${detectedAt})`,
    doc_hash: doc.hash,
    field: attempt && attempt.field,
  };
}

// Convenience wrapper: build the notice and hand it to a caller-supplied
// transport. Never throws on transport failure — returns a result object
// instead, since a failed notification must never block or corrupt the
// document operation that triggered it.
async function notifyAlterationAttempt(doc, attempt, send) {
  let notice;
  try {
    notice = buildAlterationNotice(doc, attempt);
  } catch (e) {
    return { sent: false, error: e.message };
  }
  if (typeof send !== 'function') {
    return { sent: false, error: 'no send() transport provided', notice };
  }
  try {
    await send(notice);
    return { sent: true, notice };
  } catch (e) {
    return { sent: false, error: e.message, notice };
  }
}

module.exports = { CARRIER_GATEWAYS, resolveTarget, buildAlterationNotice, notifyAlterationAttempt };
