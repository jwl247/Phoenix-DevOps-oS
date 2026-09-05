// file-format.js — Phoenix Office
// Serializes an in-memory document (document.js) to/from an actual file on
// disk — the embedded-truth format DESIGN.md calls for, extending
// Phoenix's existing TAV address system (CLAUDE.md) rather than inventing
// a new one. Header QR is written before the signing hash exists; footer
// QR only exists once the document is SIGNED — same non-negotiable
// ordering as the rest of Phoenix (CLAUDE.md rule 7: header before
// hashing, footer after, never swapped).
//
// Base58 ported from phoenix-core/tools/intake.py's _base58() (the one
// place this algorithm has actually worked end-to-end in this repo) —
// plain bignum-division-by-58 over the same alphabet, done here with
// BigInt instead of shelling out to Python.

const fs = require('fs');
const crypto = require('crypto');
const { contentHash, hashesMatch } = require('./document');

const B58_ALPHABET = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz';

function base58FromBytes(buf) {
  let n = 0n;
  for (const byte of buf) {
    n = (n << 8n) + BigInt(byte);
  }
  let result = '';
  while (n > 0n) {
    const r = Number(n % 58n);
    n = n / 58n;
    result = B58_ALPHABET[r] + result;
  }
  for (const byte of buf) {
    if (byte === 0) result = B58_ALPHABET[0] + result;
    else break;
  }
  return result;
}

// CLAUDE.md's TAV system: filename -> SHA3-512 -> first 8 bytes -> base58.
// Same shortening here, applied to whichever hash is passed in.
function shortAddress(sha3Hex) {
  const first8 = Buffer.from(sha3Hex.slice(0, 16), 'hex'); // 16 hex chars = 8 bytes
  return base58FromBytes(first8);
}

// Stable identity, fixed at creation. The FORGED history entry (event: 1)
// never changes once written, so this address never changes either — even
// though the document's own content does, as fields fill in pre-signature.
// This is deliberately NOT derived from doc.fields; an address that shifted
// on every fill would make "which file is this" a moving target.
function documentIdentityHash(doc) {
  const forged = doc.history[0];
  const s = JSON.stringify({ at: forged.at, by: forged.by });
  return crypto.createHash('sha3-512').update(s, 'utf8').digest('hex');
}

function buildHeader(doc) {
  return `USYS:${shortAddress(documentIdentityHash(doc))}:HEADER`;
}

// Footer only exists once the document is SIGNED — it's the integrity
// proof, not a descriptive label, and there's nothing to prove before a
// hash baseline exists.
function buildFooter(doc) {
  if (!doc.hash) return null;
  return `USYS:${shortAddress(doc.hash.sha3)}:FOOTER:${doc.hash.sha3}`;
}

function saveOfficeFile(filePath, doc) {
  const header = buildHeader(doc);
  const footer = buildFooter(doc);
  const record = { header, footer, body: doc };
  fs.writeFileSync(filePath, JSON.stringify(record, null, 2), 'utf8');
  return { header, footer };
}

// Loading a SIGNED document always re-verifies it against the footer and
// the recomputed field hash — this is what makes tamper-evidence real
// instead of theoretical. Never throws on tamper; returns it so the
// caller can route to notify.js.
function loadOfficeFile(filePath) {
  const raw = fs.readFileSync(filePath, 'utf8');
  const record = JSON.parse(raw);
  const doc = record.body;

  const result = { document: doc, header: record.header, footer: record.footer, tampered: false, reason: null };

  if (doc.state !== 'SIGNED') {
    return result; // nothing to verify yet — DRAFT/PENDING_REVIEW have no baseline
  }

  if (!doc.hash) {
    result.reason = 'signed document has no hash baseline — pre-format-fix legacy file';
    return result;
  }

  const actualFieldHash = contentHash(doc.fields);
  if (!hashesMatch(actualFieldHash, doc.hash)) {
    result.tampered = true;
    result.reason = 'field content does not match the hash baseline recorded at signing';
    return result;
  }

  const expectedFooter = buildFooter(doc);
  if (record.footer !== expectedFooter) {
    result.tampered = true;
    result.reason = 'footer QR does not match the recomputed hash — file may have been edited directly';
    return result;
  }

  return result;
}

module.exports = {
  base58FromBytes, shortAddress, documentIdentityHash,
  buildHeader, buildFooter, saveOfficeFile, loadOfficeFile,
};
