// phoenix-office-worker — Phoenix Office (standalone)
// UnitedSys — United Systems | jwl247 | GPL-3.0
//
// This product's OWN worker. Cloned from sector2/apps/office/notify-worker/
// (2026-09-22) — the routing/notify/escalation logic is unchanged, just
// renamed off PHOENIX_AUTH/PHOENIX_DB onto this product's own OFFICE_AUTH/
// OFFICE_DB so it shares nothing with Phoenix's fleet of workers. Deploys
// under its own name (phoenix-office-worker), its own D1 database
// (phoenix_office_db), its own R2 bucket (phoenix-office-documents) — see
// README.md. Phoenix's live office-notify-worker is untouched by this file.
//
// New here (not in office-notify-worker): document storage.
//   PUT /documents/:hex   store a signed .office file's bytes in R2, keyed
//                         by the document's OWN content-identity hash
//                         (file-format.js's documentIdentityHash) — never a
//                         filename. Two different customers' "invoice.json"
//                         can never collide, because nothing is keyed by
//                         filename in the first place. No tiering, no
//                         eviction — R2 is the durable store, period; these
//                         are legal records, not a fast local dev cache.
//   GET  /documents/:hex  fetch it back (reopen from a different machine,
//                         recover after local loss).
//
// Routes
//   GET  /health                       worker + bindings status (no auth)
//   GET  /whoami                       auth round-trip (Bearer OFFICE_AUTH)
//   POST /notify                       create + send a notification (Bearer)
//                                      body: { doc_hex, notice }
//   GET  /ack/:token                   counterparty acknowledges (token IS the auth)
//   GET  /author/:type/:value          canonical author_id for a credential (Bearer)
//   POST /author/link                  link a credential to an author_id (Bearer)
//                                      body: { author_id, credential_type, credential_value }
//   PUT  /documents/:hex               store a signed document's bytes (Bearer)
//   GET  /documents/:hex               fetch a stored document's bytes (Bearer)
//   GET  /documents                    browse recent documents, newest first (Bearer)
//                                      query: ?limit=30&state=SIGNED
//   GET  /documents/:hex/history       the full supersedes_hex chain, oldest first (Bearer)
//   POST /documents/:hex/legal-hold           place a legal hold (Bearer)
//                                              body: { by, reason } — reason doubles as the matter/case reference
//   POST /documents/:hex/legal-hold/release   release a legal hold (Bearer)
//                                              body: { by, reason? }
//   GET  /documents/:hex/legal-hold           place/release audit trail for one document (Bearer)
//   GET  /legal-holds                         every document currently on hold, for a discovery/subpoena response (Bearer)
//   GET  /runtime/:name                fetch a shared runtime asset, e.g. a
//                                      portable LibreOffice zip (Bearer)
//   HEAD /runtime/:name                check size/existence without downloading
//
// scheduled()  cron (* * * * *) — re-send every unacknowledged notification
//              whose last send is stale, escalating the subject, level capped at 5.

const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, PUT, OPTIONS',
  'Access-Control-Allow-Headers': 'Authorization, Content-Type',
};

const RESEND_STALE_MS = 45 * 1000; // re-send once a send is older than this (cron fires every 60s)
const MAX_LEVEL = 5;

function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...CORS },
  });
}
function err(message, status = 400) {
  return json({ status: 'error', message }, status);
}

function isAuthorized(req, env) {
  const token = req.headers.get('Authorization')?.replace('Bearer ', '').trim();
  return token && token === (env.OFFICE_AUTH || '').trim();
}

// URL-safe, single-use. 32 bytes of randomness -> 43-char base64url.
function genToken() {
  const b = new Uint8Array(32);
  crypto.getRandomValues(b);
  return btoa(String.fromCharCode(...b)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

// Louder the longer it goes unacknowledged. Level 1 is the plain notice.
function escalationSubject(level, base) {
  if (level <= 1) return base;
  const prefix = ['', '', 'REMINDER: ', 'SECOND REMINDER: ', 'URGENT: ', 'URGENT — PLEASE RESPOND: '][level] || 'URGENT — PLEASE RESPOND: ';
  return prefix + base;
}

function ackUrl(env, origin, token) {
  const baseRaw = origin || env.WORKER_PUBLIC_URL || '';
  const base = baseRaw.replace(/\/+$/, '');
  return `${base}/ack/${token}`;
}

// ── Transport ────────────────────────────────────────────────────────────────
// Same as office-notify-worker: Resend is the working path (arbitrary
// recipients: carrier SMS gateways + plain email). send_email is a
// Cloudflare-native fallback that only reaches VERIFIED addresses — usable
// for an issuer copy, not the customer. Throws if neither is configured.
async function sendNotice(env, { to, subject, body }) {
  const from = env.NOTIFY_FROM || 'Phoenix Office <office@authenticcoder.com>';

  if (env.RESEND_API_KEY) {
    const r = await fetch('https://api.resend.com/emails', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${env.RESEND_API_KEY}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ from, to: [to], subject, text: body }),
    });
    if (!r.ok) throw new Error(`resend ${r.status}: ${(await r.text()).slice(0, 300)}`);
    return { transport: 'resend' };
  }

  if (env.ISSUER_COPY) {
    const { EmailMessage } = await import('cloudflare:email');
    const fromAddr = from.match(/<([^>]+)>/)?.[1] || from;
    const mime =
      `From: ${from}\r\n` +
      `To: ${to}\r\n` +
      `Subject: ${subject}\r\n` +
      `MIME-Version: 1.0\r\n` +
      `Content-Type: text/plain; charset=utf-8\r\n\r\n` +
      `${body}\r\n`;
    await env.ISSUER_COPY.send(new EmailMessage(fromAddr, to, mime));
    return { transport: 'cloudflare-email-routing' };
  }

  throw new Error('no send transport configured — set the RESEND_API_KEY secret (or an ISSUER_COPY send_email binding)');
}

// ── One send + row update ────────────────────────────────────────────────────
async function deliver(env, row, origin) {
  const link = ackUrl(env, origin, row.ack_token);
  const bodyWithLink =
    `${row.body_text}\n\n` +
    `Confirm you have seen this (stops the reminders): ${link}`;
  const subject = escalationSubject(row.escalation_level, row.subject_text);

  let lastError = null;
  try {
    await sendNotice(env, { to: row.to_address, subject, body: bodyWithLink });
  } catch (e) {
    lastError = String(e && e.message || e).slice(0, 400);
  }
  await env.OFFICE_DB.prepare(
    `UPDATE office_notifications
       SET send_count = send_count + 1,
           last_sent_at = ?,
           last_error = ?
     WHERE id = ?`
  ).bind(new Date().toISOString(), lastError, row.id).run();
  return { sent: !lastError, error: lastError };
}

// ── HTTP: notify ─────────────────────────────────────────────────────────────
async function handleNotify(req, env) {
  if (!isAuthorized(req, env)) return err('unauthorized', 401);
  let payload;
  try {
    payload = await req.json();
  } catch {
    return err('body must be JSON', 400);
  }
  const { doc_hex, notice } = payload || {};
  if (!doc_hex) return err('doc_hex required', 400);
  if (!notice || !notice.to || !notice.via) return err('notice must include { to, via, subject, body } (notify.js buildAlterationNotice output)', 400);
  if (notice.via !== 'sms-gateway' && notice.via !== 'email') return err('notice.via must be "sms-gateway" or "email"', 400);

  const token = genToken();
  const attemptAt = notice.detected_at || new Date().toISOString();
  const docHashStr = notice.doc_hash == null
    ? null
    : (typeof notice.doc_hash === 'object' ? JSON.stringify(notice.doc_hash) : String(notice.doc_hash));

  const ins = await env.OFFICE_DB.prepare(
    `INSERT INTO office_notifications
       (doc_hex, doc_hash, attempt_field, attempt_at, to_address, via, ack_token, escalation_level)
     VALUES (?, ?, ?, ?, ?, ?, ?, 1)
     RETURNING id`
  ).bind(
    doc_hex,
    docHashStr,
    notice.field || null,
    attemptAt,
    notice.to,
    notice.via,
    token
  ).first();

  const row = {
    id: ins.id,
    ack_token: token,
    escalation_level: 1,
    to_address: notice.to,
    subject_text: notice.subject || 'Alteration attempt on your signed document',
    body_text: notice.body || 'A signed document was altered. The original content is unaffected.',
  };
  const origin = new URL(req.url).origin;
  const result = await deliver(env, row, origin);

  // Always 200: the notification IS recorded and the cron will keep
  // retrying delivery — a non-2xx here would make a retrying client
  // re-POST and double-insert. `sent`/`error` carry the real outcome.
  return json({
    ok: true,
    recorded: true,
    notification_id: ins.id,
    ack_token: token,
    ack_url: ackUrl(env, origin, token),
    sent: result.sent,
    error: result.error,
  }, 200);
}

async function handleAck(token, env) {
  if (!token) return err('token required', 400);
  const row = await env.OFFICE_DB.prepare(
    'SELECT id, acknowledged_at FROM office_notifications WHERE ack_token = ?'
  ).bind(token).first();

  if (!row) {
    return new Response(ackPage('This link is not valid.', false), {
      status: 404, headers: { 'Content-Type': 'text/html; charset=utf-8', ...CORS },
    });
  }
  if (!row.acknowledged_at) {
    await env.OFFICE_DB.prepare(
      'UPDATE office_notifications SET acknowledged_at = ? WHERE id = ? AND acknowledged_at IS NULL'
    ).bind(new Date().toISOString(), row.id).run();
  }
  return new Response(ackPage("Got it — you won't be contacted about this again.", true), {
    status: 200, headers: { 'Content-Type': 'text/html; charset=utf-8', ...CORS },
  });
}

// ── office_authors ───────────────────────────────────────────────────────────
const CRED_TYPES = ['fingerprint', 'windows', 'google'];

async function handleAuthorLookup(type, value, env) {
  if (!CRED_TYPES.includes(type)) return err(`credential_type must be one of ${CRED_TYPES.join(', ')}`, 400);
  if (!value) return err('credential value required', 400);
  const row = await env.OFFICE_DB.prepare(
    'SELECT author_id, linked_at FROM office_authors WHERE credential_type = ? AND credential_value = ?'
  ).bind(type, value).first();
  if (!row) return err('not linked', 404);
  return json({ author_id: row.author_id, linked_at: row.linked_at });
}

async function handleAuthorLink(req, env) {
  let body;
  try { body = await req.json(); } catch { return err('body must be JSON', 400); }
  const { author_id, credential_type, credential_value } = body || {};
  if (!author_id) return err('author_id required', 400);
  if (!CRED_TYPES.includes(credential_type)) return err(`credential_type must be one of ${CRED_TYPES.join(', ')}`, 400);
  if (!credential_value) return err('credential_value required', 400);

  const existing = await env.OFFICE_DB.prepare(
    'SELECT author_id, linked_at FROM office_authors WHERE credential_type = ? AND credential_value = ?'
  ).bind(credential_type, credential_value).first();
  if (existing) {
    return json({
      author_id: existing.author_id,
      linked_at: existing.linked_at,
      already: true,
      conflict: existing.author_id !== author_id,
    });
  }

  const now = new Date().toISOString();
  await env.OFFICE_DB.prepare(
    'INSERT INTO office_authors (author_id, credential_type, credential_value, linked_at) VALUES (?, ?, ?, ?)'
  ).bind(author_id, credential_type, credential_value, now).run();
  return json({ author_id, linked_at: now, already: false });
}

// ── runtime assets — large shared binaries (e.g. a portable LibreOffice) ────
// Separate bucket from OFFICE_DOCS on purpose: these are big, infrequently-
// changed shared blobs, not per-customer documents, and have a totally
// different access/lifecycle pattern. "Library" pattern, not "universal
// kernel" — a fixed named asset the app fetches once and caches locally,
// not a dynamic capability-import system.
const RUNTIME_NAME_RE = /^[a-zA-Z0-9._-]+$/;

async function handleGetRuntime(name, req, env) {
  if (!isAuthorized(req, env)) return err('unauthorized', 401);
  if (!RUNTIME_NAME_RE.test(name)) return err('invalid runtime asset name', 400);
  const obj = await env.OFFICE_RUNTIME.get(name);
  if (!obj) return err('not found', 404);
  return new Response(obj.body, {
    status: 200,
    headers: {
      'Content-Type': 'application/octet-stream',
      'Content-Length': String(obj.size),
      ...CORS,
    },
  });
}

async function handleHeadRuntime(name, env) {
  if (!RUNTIME_NAME_RE.test(name)) return err('invalid runtime asset name', 400);
  const obj = await env.OFFICE_RUNTIME.head(name);
  if (!obj) return err('not found', 404);
  return json({ ok: true, name, size: obj.size, uploaded: obj.uploaded });
}

// ── documents — content-addressed R2 storage ─────────────────────────────────
// hex is the document's OWN identity hash (file-format.js's
// documentIdentityHash), computed client-side and passed as the URL param.
// A basic shape check here is just sanity, not identity computation — this
// worker never derives or trusts a filename for anything.
const HEX_RE = /^[0-9a-f]{16,}$/i;

// Human-readable label, NOT identity — hex/b58 stay the real address, this
// is purely for a person scanning the browse list. Same rule the client
// side's docTitle() uses (index.html): first non-empty field value, since
// no template name is ever stored on the document itself.
function deriveTitle(fields) {
  const val = Object.values(fields || {}).find(v => v);
  return val ? String(val).slice(0, 80) : null;
}

function upsertDocumentRecord(env, hex, doc) {
  const now = new Date().toISOString();
  const fields = doc.fields || {};
  const cp = doc.counterparty || {};
  const hash = doc.hash || {};
  const title = deriveTitle(fields);
  return env.OFFICE_DB.prepare(
    `INSERT INTO office_documents
       (hex, b58, state, author_id, counterparty_phone, counterparty_carrier, counterparty_email,
        hash_sha3, hash_blake2, supersedes_hex, title, signed_at, created_at, updated_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
     ON CONFLICT(hex) DO UPDATE SET
       state = excluded.state, hash_sha3 = excluded.hash_sha3, hash_blake2 = excluded.hash_blake2,
       title = excluded.title, signed_at = excluded.signed_at, updated_at = excluded.updated_at`
  ).bind(
    hex, null, doc.state || 'DRAFT',
    (doc.history && doc.history[0] && doc.history[0].by) || 'unknown',
    cp.phone || null, cp.carrier || null, cp.email || null,
    hash.sha3 || null, hash.blake2 || null,
    doc.supersedes_hex || null, title,
    doc.signed_at || null,
    now, now
  ).run();
}

async function handlePutDocument(hex, req, env) {
  if (!isAuthorized(req, env)) return err('unauthorized', 401);
  if (!HEX_RE.test(hex)) return err('invalid document hex', 400);
  const bytes = await req.arrayBuffer();
  if (!bytes.byteLength) return err('empty body', 400);

  // Parse the .office envelope just to log a real custody row — storage
  // itself doesn't depend on this succeeding; a malformed body still gets
  // stored byte-for-byte (the document's own format.js is what verifies it
  // on load, not this worker).
  let doc = null;
  try {
    const record = JSON.parse(new TextDecoder().decode(bytes));
    doc = record.body || null;
  } catch (_) { /* stored as opaque bytes either way */ }

  await env.OFFICE_DOCS.put(hex, bytes);
  if (doc) {
    try { await upsertDocumentRecord(env, hex, doc); } catch (_) { /* R2 write already succeeded — the D1 row is a custody reference, not the source of truth */ }
  }
  return json({ ok: true, hex, bytes: bytes.byteLength });
}

async function handleGetDocument(hex, req, env) {
  if (!isAuthorized(req, env)) return err('unauthorized', 401);
  if (!HEX_RE.test(hex)) return err('invalid document hex', 400);
  const obj = await env.OFFICE_DOCS.get(hex);
  if (!obj) return err('not found', 404);
  return new Response(obj.body, {
    status: 200,
    headers: { 'Content-Type': 'application/json', ...CORS },
  });
}

// List documents for the "pull into your workspace" browser — reference
// material or continued editing. Ordered newest-first. Full field contents
// still live only in R2, per-document — `title` is just a one-line human
// label (first filled field's value, see deriveTitle), enough to recognize
// a document without an R2 round-trip per row in the list.
async function handleListDocuments(req, env) {
  if (!isAuthorized(req, env)) return err('unauthorized', 401);
  const url = new URL(req.url);
  const limit = Math.min(parseInt(url.searchParams.get('limit') || '30', 10) || 30, 100);
  const state = url.searchParams.get('state');
  const rows = state
    ? await env.OFFICE_DB.prepare(
        'SELECT hex, b58, state, author_id, counterparty_email, supersedes_hex, title, created_at, signed_at, updated_at FROM office_documents WHERE state = ? ORDER BY updated_at DESC LIMIT ?'
      ).bind(state, limit).all()
    : await env.OFFICE_DB.prepare(
        'SELECT hex, b58, state, author_id, counterparty_email, supersedes_hex, title, created_at, signed_at, updated_at FROM office_documents ORDER BY updated_at DESC LIMIT ?'
      ).bind(limit).all();
  return json({ ok: true, items: rows.results || [] });
}

// Version history — walk the supersedes_hex chain both directions. A change
// order never edits the original (DESIGN.md); instead it's a new document
// with its own hex whose supersedes_hex points at the one it corrects. This
// surfaces the whole linked chain, oldest first, so "versioned documents"
// means something concrete: you can always see what a signed record has
// been superseded by, and what it superseded.
async function handleDocumentHistory(hex, req, env) {
  if (!isAuthorized(req, env)) return err('unauthorized', 401);
  if (!HEX_RE.test(hex)) return err('invalid document hex', 400);

  const getRow = (h) => env.OFFICE_DB.prepare(
    'SELECT hex, state, supersedes_hex, created_at, signed_at FROM office_documents WHERE hex = ?'
  ).bind(h).first();

  const start = await getRow(hex);
  if (!start) return json({ ok: true, chain: [] }); // not sealed yet — nothing to show

  // walk up to the root (oldest ancestor)
  let root = start;
  const seen = new Set([root.hex]);
  while (root.supersedes_hex && !seen.has(root.supersedes_hex)) {
    const parent = await getRow(root.supersedes_hex);
    if (!parent) break;
    root = parent;
    seen.add(root.hex);
  }

  // walk down from the root, breadth-first, collecting every descendant
  const chain = [root];
  const chainSeen = new Set([root.hex]);
  let frontier = [root.hex];
  while (frontier.length) {
    const placeholders = frontier.map(() => '?').join(',');
    const children = await env.OFFICE_DB.prepare(
      `SELECT hex, state, supersedes_hex, created_at, signed_at FROM office_documents WHERE supersedes_hex IN (${placeholders})`
    ).bind(...frontier).all();
    const next = [];
    for (const c of children.results || []) {
      if (chainSeen.has(c.hex)) continue;
      chainSeen.add(c.hex);
      chain.push(c);
      next.push(c.hex);
    }
    frontier = next;
  }

  chain.sort((a, b) => (a.created_at || '').localeCompare(b.created_at || ''));
  return json({ ok: true, chain });
}

// Legal hold — modeled after Microsoft 365's eDiscovery hold (see
// schema.sql's office_legal_holds comment). Scoped to sealed documents
// only: a document has no office_documents row at all until it's PUT here
// on signing, so there's nothing to hold before that point. Two writes per
// action on purpose: the append-only office_legal_holds row is the real
// audit record (who, when, why — never overwritten), office_documents'
// legal_hold/legal_hold_reason columns are a denormalized "current status"
// for fast filtering (GET /legal-holds, and the browse list's flag).
async function handleLegalHoldPlace(hex, req, env) {
  if (!isAuthorized(req, env)) return err('unauthorized', 401);
  if (!HEX_RE.test(hex)) return err('invalid document hex', 400);
  let body;
  try { body = await req.json(); } catch (_) { return err('invalid JSON body', 400); }
  const by = body && body.by;
  const reason = (body && body.reason) || null;
  if (!by) return err('by (author_id) required', 400);

  const doc = await env.OFFICE_DB.prepare('SELECT hex FROM office_documents WHERE hex = ?').bind(hex).first();
  if (!doc) return err('document not found — only sealed documents can be placed on hold', 404);

  const now = new Date().toISOString();
  await env.OFFICE_DB.prepare(
    'UPDATE office_documents SET legal_hold = 1, legal_hold_reason = ?, updated_at = ? WHERE hex = ?'
  ).bind(reason, now, hex).run();
  await env.OFFICE_DB.prepare(
    'INSERT INTO office_legal_holds (doc_hex, action, by, reason, at) VALUES (?, ?, ?, ?, ?)'
  ).bind(hex, 'placed', by, reason, now).run();

  return json({ ok: true, hex, legal_hold: true, reason });
}

async function handleLegalHoldRelease(hex, req, env) {
  if (!isAuthorized(req, env)) return err('unauthorized', 401);
  if (!HEX_RE.test(hex)) return err('invalid document hex', 400);
  let body;
  try { body = await req.json(); } catch (_) { body = {}; }
  const by = body && body.by;
  const reason = (body && body.reason) || null;
  if (!by) return err('by (author_id) required', 400);

  const doc = await env.OFFICE_DB.prepare('SELECT hex FROM office_documents WHERE hex = ?').bind(hex).first();
  if (!doc) return err('document not found', 404);

  const now = new Date().toISOString();
  await env.OFFICE_DB.prepare(
    'UPDATE office_documents SET legal_hold = 0, legal_hold_reason = NULL, updated_at = ? WHERE hex = ?'
  ).bind(now, hex).run();
  await env.OFFICE_DB.prepare(
    'INSERT INTO office_legal_holds (doc_hex, action, by, reason, at) VALUES (?, ?, ?, ?, ?)'
  ).bind(hex, 'released', by, reason, now).run();

  return json({ ok: true, hex, legal_hold: false });
}

// The report/export: every document currently under hold, for a real
// discovery/subpoena response — not just a per-document status check.
async function handleLegalHoldsReport(req, env) {
  if (!isAuthorized(req, env)) return err('unauthorized', 401);
  const rows = await env.OFFICE_DB.prepare(
    'SELECT hex, b58, state, author_id, title, legal_hold_reason, signed_at, created_at, updated_at FROM office_documents WHERE legal_hold = 1 ORDER BY updated_at DESC'
  ).all();
  return json({ ok: true, items: rows.results || [] });
}

// Full place/release audit trail for one document — the actual history
// behind the current legal_hold flag, same relationship handleDocumentHistory
// has to a document's version chain.
async function handleLegalHoldHistory(hex, req, env) {
  if (!isAuthorized(req, env)) return err('unauthorized', 401);
  if (!HEX_RE.test(hex)) return err('invalid document hex', 400);
  const rows = await env.OFFICE_DB.prepare(
    'SELECT action, by, reason, at FROM office_legal_holds WHERE doc_hex = ? ORDER BY at ASC'
  ).bind(hex).all();
  return json({ ok: true, events: rows.results || [] });
}

function ackPage(message, ok) {
  return `<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Phoenix Office</title>
<div style="font:16px/1.5 system-ui,sans-serif;max-width:34rem;margin:18vh auto;padding:0 1.25rem;color:#1a1a1a">
  <div style="font-size:2rem">${ok ? '&#10003;' : '&#9888;'}</div>
  <p style="margin:.75rem 0 0">${message}</p>
  <p style="color:#666;margin-top:1.5rem;font-size:.9rem">
    The original document cannot be altered &mdash; this only confirms you saw the notice.
  </p>
</div>`;
}

// ── scheduled re-scan ────────────────────────────────────────────────────────
async function runEscalation(env) {
  const cutoff = new Date(Date.now() - RESEND_STALE_MS).toISOString();
  const open = await env.OFFICE_DB.prepare(
    `SELECT id, ack_token, escalation_level, to_address, doc_hash, attempt_field, attempt_at
       FROM office_notifications
      WHERE acknowledged_at IS NULL
        AND (last_sent_at IS NULL OR last_sent_at < ?)
      ORDER BY last_sent_at ASC NULLS FIRST
      LIMIT 50`
  ).bind(cutoff).all();

  let resent = 0;
  for (const r of open.results || []) {
    const nextLevel = Math.min(r.escalation_level + 1, MAX_LEVEL);
    if (nextLevel !== r.escalation_level) {
      await env.OFFICE_DB.prepare(
        'UPDATE office_notifications SET escalation_level = ? WHERE id = ?'
      ).bind(nextLevel, r.id).run();
    }
    const row = {
      id: r.id,
      ack_token: r.ack_token,
      escalation_level: nextLevel,
      to_address: r.to_address,
      subject_text: 'Alteration attempt on your signed document',
      body_text:
        'An attempt was made to change a document that was already signed and locked. ' +
        'The original content is unaffected — it cannot be altered. ' +
        'If you did not expect this, contact the issuer directly.' +
        (r.attempt_at ? ` (first detected ${r.attempt_at})` : ''),
    };
    const res = await deliver(env, row, null);
    if (res.sent) resent++;
  }
  return { scanned: (open.results || []).length, resent };
}

// ── entry ────────────────────────────────────────────────────────────────────
export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    const path = url.pathname.replace(/\/+$/, '') || '/';

    if (req.method === 'OPTIONS') return new Response(null, { status: 204, headers: CORS });

    if (path === '/health') {
      return json({
        status: 'ok',
        worker: 'phoenix-office-worker',
        db_bound: !!env.OFFICE_DB,
        r2_bound: !!env.OFFICE_DOCS,
        runtime_bound: !!env.OFFICE_RUNTIME,
        transport: env.RESEND_API_KEY ? 'resend' : (env.ISSUER_COPY ? 'cloudflare-email-routing' : 'NONE'),
      });
    }

    if (path === '/whoami') {
      if (!isAuthorized(req, env)) return err('unauthorized', 401);
      return json({ ok: true, worker: 'phoenix-office-worker' });
    }

    if (path === '/notify' && req.method === 'POST') return handleNotify(req, env);

    if (path.startsWith('/ack/')) {
      return handleAck(decodeURIComponent(path.slice('/ack/'.length)), env);
    }

    if (path === '/author/link' && req.method === 'POST') {
      if (!isAuthorized(req, env)) return err('unauthorized', 401);
      return handleAuthorLink(req, env);
    }
    if (path.startsWith('/author/') && req.method === 'GET') {
      if (!isAuthorized(req, env)) return err('unauthorized', 401);
      const rest = path.slice('/author/'.length).split('/');
      return handleAuthorLookup(
        decodeURIComponent(rest[0] || ''),
        decodeURIComponent(rest.slice(1).join('/') || ''),
        env
      );
    }

    if (path.startsWith('/runtime/')) {
      const name = decodeURIComponent(path.slice('/runtime/'.length));
      if (req.method === 'GET') return handleGetRuntime(name, req, env);
      if (req.method === 'HEAD') return handleHeadRuntime(name, env);
    }

    if (path === '/documents' && req.method === 'GET') return handleListDocuments(req, env);
    if (path === '/legal-holds' && req.method === 'GET') return handleLegalHoldsReport(req, env);

    if (path.startsWith('/documents/') && path.endsWith('/history')) {
      const hex = decodeURIComponent(path.slice('/documents/'.length, -'/history'.length));
      return handleDocumentHistory(hex, req, env);
    }
    if (path.startsWith('/documents/') && path.endsWith('/legal-hold/release') && req.method === 'POST') {
      const hex = decodeURIComponent(path.slice('/documents/'.length, -'/legal-hold/release'.length));
      return handleLegalHoldRelease(hex, req, env);
    }
    if (path.startsWith('/documents/') && path.endsWith('/legal-hold') && req.method === 'POST') {
      const hex = decodeURIComponent(path.slice('/documents/'.length, -'/legal-hold'.length));
      return handleLegalHoldPlace(hex, req, env);
    }
    if (path.startsWith('/documents/') && path.endsWith('/legal-hold') && req.method === 'GET') {
      const hex = decodeURIComponent(path.slice('/documents/'.length, -'/legal-hold'.length));
      return handleLegalHoldHistory(hex, req, env);
    }

    if (path.startsWith('/documents/')) {
      const hex = decodeURIComponent(path.slice('/documents/'.length));
      if (req.method === 'PUT') return handlePutDocument(hex, req, env);
      if (req.method === 'GET') return handleGetDocument(hex, req, env);
    }

    return err('not found', 404);
  },

  async scheduled(event, env, ctx) {
    ctx.waitUntil(runEscalation(env));
  },
};
