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
//   GET  /ack/:token                   confirm page (a GET alone never acknowledges)
//   POST /ack/:token                   counterparty acknowledges (token IS the auth)
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
//   GET  /jobs?author_id=...           list saved job profiles for the dropdown (Bearer)
//   POST /jobs                         create/update a saved job profile (Bearer)
//                                      body: { job_id?, author_id, label, fields, counterparty? }
//   DELETE /jobs/:job_id                remove a saved job profile (Bearer)
//   GET  /runtime/:name                fetch a shared runtime asset, e.g. a
//                                      portable LibreOffice zip (Bearer)
//   HEAD /runtime/:name                check size/existence without downloading
//
// scheduled()  cron (* * * * *) — re-send every unacknowledged notification
//              whose last send is stale, escalating the subject, level capped at 5.

const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, PUT, PATCH, OPTIONS',
  'Access-Control-Allow-Headers': 'Authorization, Content-Type',
};

const RESEND_STALE_MS = 45 * 1000; // re-send once a send is older than this (cron fires every 60s)
const MAX_LEVEL = 5;
// Hard stop on total sends per notification. Without it the cron re-sent
// every unacknowledged notice every minute FOREVER (the level caps at 5, the
// sends didn't) — the 2026-09-23 "sent 50 times in an hour" incident; a
// wrong or hostile address would be mailed indefinitely and burn the Resend
// quota. Past this many sends the row stays recorded (audit), just quiet.
const MAX_SENDS = 12;
// Back off per level too (same schedule as office-notify-worker's fix):
// gap before the next send by current level = 45s, ~4m, ~19m, ~1.6h, ~7.8h.
const RESEND_BACKOFF = 5;
function resendGapMs(level) {
  return RESEND_STALE_MS * Math.pow(RESEND_BACKOFF, Math.max(0, (level || 1) - 1));
}

function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...CORS },
  });
}
function err(message, status = 400) {
  return json({ status: 'error', message }, status);
}

// Constant-time compare — a plain === leaks how many leading characters
// matched through response timing.
function timingSafeEqualStr(a, b) {
  const x = new TextEncoder().encode(String(a));
  const y = new TextEncoder().encode(String(b));
  let diff = x.length ^ y.length;
  for (let i = 0; i < Math.max(x.length, y.length); i++) diff |= (x[i] || 0) ^ (y[i] || 0);
  return diff === 0;
}

function isAuthorized(req, env) {
  const token = req.headers.get('Authorization')?.replace('Bearer ', '').trim();
  const expected = (env.OFFICE_AUTH || '').trim();
  return !!token && !!expected && timingSafeEqualStr(token, expected);
}

// Raw bytes of an R2 get() result (real R2ObjectBody or the test mock).
async function objectBytes(obj) {
  if (obj && typeof obj.arrayBuffer === 'function') return new Uint8Array(await obj.arrayBuffer());
  const b = obj && obj.body;
  if (b instanceof ArrayBuffer) return new Uint8Array(b);
  if (ArrayBuffer.isView(b)) return new Uint8Array(b.buffer, b.byteOffset, b.byteLength);
  if (typeof b === 'string') return new TextEncoder().encode(b);
  return new Uint8Array(await new Response(b).arrayBuffer());
}
function sameBytes(a, b) {
  if (a.byteLength !== b.byteLength) return false;
  for (let i = 0; i < a.byteLength; i++) if (a[i] !== b[i]) return false;
  return true;
}

// Strip CR/LF so a caller-supplied value can never inject extra MIME headers.
function headerSafe(v) {
  return String(v == null ? '' : v).replace(/[\r\n]+/g, ' ');
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
      `From: ${headerSafe(from)}\r\n` +
      `To: ${headerSafe(to)}\r\n` +
      `Subject: ${headerSafe(subject)}\r\n` +
      `MIME-Version: 1.0\r\n` +
      `Content-Type: text/plain; charset=utf-8\r\n\r\n` +
      `${body}\r\n`;
    await env.ISSUER_COPY.send(new EmailMessage(headerSafe(fromAddr), headerSafe(to), mime));
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

// GET only shows a confirm button; the POST acknowledges. SMS/iMessage link
// previews and mail scanners GET every URL in a message — if GET acknowledged,
// a preview bot would silently stop the customer's notices.
function ackConfirmPage() {
  return `<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Phoenix Office</title>
<div style="font:16px/1.5 system-ui,sans-serif;max-width:34rem;margin:18vh auto;padding:0 1.25rem;color:#1a1a1a">
  <p style="margin:0 0 1.25rem">Confirm you have seen the notice about your signed document. This stops the reminders.</p>
  <form method="POST"><button type="submit" style="font:inherit;padding:.7rem 1.6rem;border:0;border-radius:.5rem;background:#1a1a1a;color:#fff">I have seen it</button></form>
</div>`;
}

async function handleAck(token, env, method = 'GET') {
  if (!token) return err('token required', 400);
  const row = await env.OFFICE_DB.prepare(
    'SELECT id, acknowledged_at FROM office_notifications WHERE ack_token = ?'
  ).bind(token).first();

  if (!row) {
    return new Response(ackPage('This link is not valid.', false), {
      status: 404, headers: { 'Content-Type': 'text/html; charset=utf-8', ...CORS },
    });
  }
  if (method !== 'POST' && !row.acknowledged_at) {
    return new Response(ackConfirmPage(), {
      status: 200, headers: { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store', ...CORS },
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

// ── jobs — saved customer/job profiles for the "pick one, it autofills" ─────
// dropdown (Jerry, 2026-09-24). Scoped per author_id, same as documents.
// job_id is client-generated (crypto.randomUUID in main.js) so renaming a
// label is just an upsert, never a new row.
function genJobId() {
  const b = new Uint8Array(16);
  crypto.getRandomValues(b);
  return Array.from(b, x => x.toString(16).padStart(2, '0')).join('');
}
const genId = genJobId; // same shape, generic name for project/phase/checklist-item ids

async function handleListJobs(req, env) {
  if (!isAuthorized(req, env)) return err('unauthorized', 401);
  const url = new URL(req.url);
  const authorId = url.searchParams.get('author_id');
  if (!authorId) return err('author_id required', 400);
  const rows = await env.OFFICE_DB.prepare(
    'SELECT job_id, label, fields, counterparty, created_at, updated_at FROM office_jobs WHERE author_id = ? ORDER BY COALESCE(updated_at, created_at) DESC LIMIT 200'
  ).bind(authorId).all();
  const items = (rows.results || []).map(r => ({
    job_id: r.job_id, label: r.label,
    fields: JSON.parse(r.fields || '{}'),
    counterparty: r.counterparty ? JSON.parse(r.counterparty) : null,
    created_at: r.created_at, updated_at: r.updated_at,
  }));
  return json({ ok: true, items });
}

async function handleSaveJob(req, env) {
  if (!isAuthorized(req, env)) return err('unauthorized', 401);
  let body;
  try { body = await req.json(); } catch { return err('body must be JSON', 400); }
  const { author_id, label, fields, counterparty } = body || {};
  if (!author_id) return err('author_id required', 400);
  if (!label || !String(label).trim()) return err('label required', 400);
  if (!fields || typeof fields !== 'object') return err('fields (object) required', 400);
  const jobId = (body.job_id && String(body.job_id)) || genJobId();
  const now = new Date().toISOString();
  await env.OFFICE_DB.prepare(
    `INSERT INTO office_jobs (job_id, author_id, label, fields, counterparty, created_at, updated_at)
     VALUES (?, ?, ?, ?, ?, ?, ?)
     ON CONFLICT(job_id) DO UPDATE SET
       label = excluded.label, fields = excluded.fields, counterparty = excluded.counterparty, updated_at = excluded.updated_at`
  ).bind(jobId, author_id, String(label).trim(), JSON.stringify(fields), counterparty ? JSON.stringify(counterparty) : null, now, now).run();
  return json({ ok: true, job_id: jobId, label: String(label).trim() });
}

async function handleDeleteJob(jobId, req, env) {
  if (!isAuthorized(req, env)) return err('unauthorized', 401);
  if (!jobId) return err('job_id required', 400);
  await env.OFFICE_DB.prepare('DELETE FROM office_jobs WHERE job_id = ?').bind(jobId).run();
  return json({ ok: true });
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

async function handleHeadRuntime(name, req, env) {
  if (!isAuthorized(req, env)) return err('unauthorized', 401);
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
  // project_id/phase_id/doc_role: optional, present only when the document
  // was created via create_project_document (Project Assist) — additive,
  // same soft-tagging idiom as supersedes_hex. A plain standalone document
  // (work order, invoice, etc. made outside a project) leaves these NULL.
  return env.OFFICE_DB.prepare(
    `INSERT INTO office_documents
       (hex, b58, state, author_id, counterparty_phone, counterparty_carrier, counterparty_email,
        hash_sha3, hash_blake2, supersedes_hex, title, signed_at, created_at, updated_at,
        project_id, phase_id, doc_role)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
     ON CONFLICT(hex) DO UPDATE SET
       state = excluded.state, hash_sha3 = excluded.hash_sha3, hash_blake2 = excluded.hash_blake2,
       title = excluded.title, signed_at = excluded.signed_at, updated_at = excluded.updated_at,
       project_id = COALESCE(excluded.project_id, office_documents.project_id),
       phase_id = COALESCE(excluded.phase_id, office_documents.phase_id),
       doc_role = COALESCE(excluded.doc_role, office_documents.doc_role)`
  ).bind(
    hex, null, doc.state || 'DRAFT',
    (doc.history && doc.history[0] && doc.history[0].by) || 'unknown',
    cp.phone || null, cp.carrier || null, cp.email || null,
    hash.sha3 || null, hash.blake2 || null,
    doc.supersedes_hex || null, title,
    doc.signed_at || null,
    now, now,
    doc.project_id || null, doc.phase_id || null, doc.doc_role || null
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

  // Sealed records are write-once. Re-sealing the identical bytes is an
  // idempotent no-op (a retried upload); anything else under an existing
  // hex is refused — before this, any bearer holder could silently replace
  // a signed document, including one under legal hold.
  const prev = await env.OFFICE_DOCS.get(hex);
  if (prev) {
    const prevBytes = await objectBytes(prev);
    if (sameBytes(prevBytes, new Uint8Array(bytes))) return json({ ok: true, hex, bytes: bytes.byteLength, already: true });
    return err('a different document is already sealed under this hex — sealed documents are immutable', 409);
  }

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

// ══════════════════════════════════════════════════════════════════════════
// PROJECT ASSIST — projects, phases, guided-choice checklist engine.
// See phoenix-office/worker/schema.sql for table shapes and the design
// rationale (bid_factors as JSON, phase_type left open, the append-only
// office_checklist_decisions audit trail). Segment-based dispatch
// (routeProjects below) rather than the startsWith/endsWith chains used
// elsewhere in this file — the nesting here (project -> phase -> checklist
// item -> decision) gets unreadable that way past 2 levels.
// ══════════════════════════════════════════════════════════════════════════

async function handleCreateProject(req, env) {
  if (!isAuthorized(req, env)) return err('unauthorized', 401);
  let body;
  try { body = await req.json(); } catch { return err('body must be JSON', 400); }
  const { author_id, name, bid_factors, counterparty, job_id } = body || {};
  if (!author_id) return err('author_id required', 400);
  if (!name || !String(name).trim()) return err('name required', 400);
  const projectId = (body.project_id && String(body.project_id)) || genId();
  const now = new Date().toISOString();
  await env.OFFICE_DB.prepare(
    `INSERT INTO office_projects (project_id, author_id, job_id, name, status, bid_factors, counterparty, created_at, updated_at)
     VALUES (?, ?, ?, ?, 'BID', ?, ?, ?, ?)
     ON CONFLICT(project_id) DO UPDATE SET
       name = excluded.name, bid_factors = excluded.bid_factors, counterparty = excluded.counterparty, updated_at = excluded.updated_at`
  ).bind(
    projectId, author_id, job_id || null, String(name).trim(),
    JSON.stringify(bid_factors || {}), counterparty ? JSON.stringify(counterparty) : null,
    now, now
  ).run();
  return json({ ok: true, project_id: projectId, name: String(name).trim() });
}

async function handleListProjects(req, env) {
  if (!isAuthorized(req, env)) return err('unauthorized', 401);
  const url = new URL(req.url);
  const authorId = url.searchParams.get('author_id');
  if (!authorId) return err('author_id required', 400);
  const rows = await env.OFFICE_DB.prepare(
    'SELECT project_id, job_id, name, status, bid_factors, counterparty, created_at, updated_at FROM office_projects WHERE author_id = ? ORDER BY COALESCE(updated_at, created_at) DESC LIMIT 200'
  ).bind(authorId).all();
  const items = (rows.results || []).map(r => ({
    ...r, bid_factors: JSON.parse(r.bid_factors || '{}'),
    counterparty: r.counterparty ? JSON.parse(r.counterparty) : null,
  }));
  return json({ ok: true, items });
}

// Aggregate compliance/safety/cost/risk into one consultation_summary block,
// computed fresh on every fetch (small dataset per project — no caching
// needed). This is the "justify our role" surface: not a separate report,
// riding along on the normal project-fetch call.
async function computeConsultationSummary(projectId, env) {
  const bySource = await env.OFFICE_DB.prepare(
    `SELECT ci.source_type,
            SUM(CASE WHEN ci.disposition = 'satisfied' THEN 1 ELSE 0 END) AS satisfied,
            COUNT(*) AS total
       FROM office_phase_checklist_items ci
       JOIN office_project_phases p ON p.phase_id = ci.phase_id
      WHERE p.project_id = ?
      GROUP BY ci.source_type`
  ).bind(projectId).all();

  const compliance = {};
  for (const row of bySource.results || []) {
    compliance[row.source_type] = { satisfied: row.satisfied, total: row.total };
  }
  const oshaOpen = await env.OFFICE_DB.prepare(
    `SELECT COUNT(*) AS n FROM office_phase_checklist_items ci
       JOIN office_project_phases p ON p.phase_id = ci.phase_id
      WHERE p.project_id = ? AND ci.source_type = 'OSHA' AND ci.disposition = 'open'`
  ).bind(projectId).first();

  const costs = await env.OFFICE_DB.prepare(
    `SELECT COALESCE(SUM(estimated_cost),0) AS est, COALESCE(SUM(actual_cost),0) AS act,
            SUM(CASE WHEN actual_cost IS NOT NULL AND estimated_cost IS NOT NULL AND actual_cost > estimated_cost THEN 1 ELSE 0 END) AS over_budget
       FROM office_project_phases WHERE project_id = ?`
  ).bind(projectId).first();

  const risk = await env.OFFICE_DB.prepare(
    `SELECT phase_type, label, risk_level FROM office_project_phases
      WHERE project_id = ? AND risk_level IS NOT NULL
      ORDER BY CASE risk_level WHEN 'high' THEN 3 WHEN 'medium' THEN 2 WHEN 'low' THEN 1 ELSE 0 END DESC`
  ).bind(projectId).all();
  const riskRows = risk.results || [];

  return {
    compliance,
    safety: { open_osha_items: (oshaOpen && oshaOpen.n) || 0, status: (oshaOpen && oshaOpen.n) > 0 ? 'attention_needed' : 'clear' },
    cost: { estimated_total: costs?.est ?? 0, actual_total: costs?.act ?? 0, phases_over_budget: costs?.over_budget ?? 0 },
    risk: { highest_phase_risk: riskRows[0]?.risk_level || null, flagged_phases: riskRows.filter(r => r.risk_level !== 'low').map(r => r.label) },
  };
}

async function handleGetProject(projectId, req, env) {
  if (!isAuthorized(req, env)) return err('unauthorized', 401);
  const row = await env.OFFICE_DB.prepare('SELECT * FROM office_projects WHERE project_id = ?').bind(projectId).first();
  if (!row) return err('not found', 404);
  const consultation_summary = await computeConsultationSummary(projectId, env);
  return json({
    ok: true,
    ...row,
    bid_factors: JSON.parse(row.bid_factors || '{}'),
    counterparty: row.counterparty ? JSON.parse(row.counterparty) : null,
    consultation_summary,
  });
}

async function handlePatchProject(projectId, req, env) {
  if (!isAuthorized(req, env)) return err('unauthorized', 401);
  let body;
  try { body = await req.json(); } catch { return err('body must be JSON', 400); }
  const existing = await env.OFFICE_DB.prepare('SELECT project_id FROM office_projects WHERE project_id = ?').bind(projectId).first();
  if (!existing) return err('not found', 404);
  const now = new Date().toISOString();
  await env.OFFICE_DB.prepare(
    `UPDATE office_projects SET
       name = COALESCE(?, name),
       status = COALESCE(?, status),
       bid_factors = COALESCE(?, bid_factors),
       updated_at = ?
     WHERE project_id = ?`
  ).bind(
    body.name ? String(body.name).trim() : null,
    body.status || null,
    body.bid_factors ? JSON.stringify(body.bid_factors) : null,
    now, projectId
  ).run();
  return json({ ok: true, project_id: projectId });
}

async function handleCreatePhases(projectId, req, env) {
  if (!isAuthorized(req, env)) return err('unauthorized', 401);
  let body;
  try { body = await req.json(); } catch { return err('body must be JSON', 400); }
  const phases = Array.isArray(body?.phases) ? body.phases : (body?.phase_type ? [body] : null);
  if (!phases || !phases.length) return err('phases (array) or a single phase object required', 400);
  const now = new Date().toISOString();
  // Sequential awaits, not .batch() — keeps this exercisable against the
  // test suite's plain mock D1 (no batch() there), and phase counts per
  // project are small (8-ish) so there's no real performance reason to
  // prefer batching here.
  for (const p of phases) {
    await env.OFFICE_DB.prepare(
      `INSERT INTO office_project_phases
         (phase_id, project_id, phase_type, lifecycle_stage, label, sequence, state, estimated_cost, estimated_duration_weeks, created_at, updated_at)
       VALUES (?, ?, ?, ?, ?, ?, 'NOT_STARTED', ?, ?, ?, ?)`
    ).bind(
      p.phase_id || genId(), projectId, p.phase_type, p.lifecycle_stage || 'EXECUTION',
      p.label || p.phase_type, p.sequence || 0, p.estimated_cost ?? null,
      Number.isFinite(Number(p.estimated_duration_weeks)) && p.estimated_duration_weeks !== null ? Number(p.estimated_duration_weeks) : null,
      now, now
    ).run();
  }
  return json({ ok: true, project_id: projectId, created: phases.length });
}

async function handleListPhases(projectId, req, env) {
  if (!isAuthorized(req, env)) return err('unauthorized', 401);
  const rows = await env.OFFICE_DB.prepare(
    'SELECT * FROM office_project_phases WHERE project_id = ? ORDER BY sequence ASC'
  ).bind(projectId).all();
  return json({ ok: true, items: rows.results || [] });
}

async function handlePatchPhase(projectId, phaseId, req, env) {
  if (!isAuthorized(req, env)) return err('unauthorized', 401);
  let body;
  try { body = await req.json(); } catch { return err('body must be JSON', 400); }
  const existing = await env.OFFICE_DB.prepare('SELECT * FROM office_project_phases WHERE phase_id = ? AND project_id = ?').bind(phaseId, projectId).first();
  if (!existing) return err('not found', 404);
  const now = new Date().toISOString();
  const startedAt = (body.state === 'IN_PROGRESS' && !existing.started_at) ? now : existing.started_at;
  const completedAt = body.state === 'COMPLETE' ? now : existing.completed_at;
  await env.OFFICE_DB.prepare(
    `UPDATE office_project_phases SET
       state = COALESCE(?, state), estimated_cost = COALESCE(?, estimated_cost), actual_cost = COALESCE(?, actual_cost),
       estimated_duration_weeks = COALESCE(?, estimated_duration_weeks),
       schedule_notes = CASE WHEN ? THEN ? ELSE schedule_notes END,
       risk_level = COALESCE(?, risk_level), risk_notes = COALESCE(?, risk_notes),
       started_at = ?, completed_at = ?, updated_at = ?
     WHERE phase_id = ?`
  ).bind(
    body.state || null, body.estimated_cost ?? null, body.actual_cost ?? null,
    Number.isFinite(Number(body.estimated_duration_weeks)) && body.estimated_duration_weeks != null ? Number(body.estimated_duration_weeks) : null,
    // schedule_notes can be cleared (""), so presence decides, not COALESCE
    Object.prototype.hasOwnProperty.call(body, 'schedule_notes') ? 1 : 0,
    typeof body.schedule_notes === 'string' ? body.schedule_notes.slice(0, 500) : null,
    body.risk_level || null, body.risk_notes || null,
    startedAt, completedAt, now, phaseId
  ).run();
  return json({ ok: true, phase_id: phaseId });
}

// Instantiate checklist items onto a real phase — either the full matching
// catalog (from_catalog:true, the normal path when a phase is created) or
// one ad-hoc item. Copies catalog rows rather than referencing them live,
// so a later catalog edit never silently changes an in-progress checklist.
async function handleSeedOrAddChecklistItem(projectId, phaseId, req, env) {
  if (!isAuthorized(req, env)) return err('unauthorized', 401);
  let body;
  try { body = await req.json(); } catch { return err('body must be JSON', 400); }
  const phase = await env.OFFICE_DB.prepare('SELECT phase_type FROM office_project_phases WHERE phase_id = ? AND project_id = ?').bind(phaseId, projectId).first();
  if (!phase) return err('phase not found', 404);
  const now = new Date().toISOString();

  if (body.from_catalog) {
    const catalog = await env.OFFICE_DB.prepare(
      'SELECT * FROM office_checklist_catalog WHERE (phase_type = ? OR phase_type = ?) AND active = 1'
    ).bind(phase.phase_type, 'general').all();
    const rows = catalog.results || [];
    if (!rows.length) return json({ ok: true, created: 0 });
    for (let i = 0; i < rows.length; i++) {
      const c = rows[i];
      await env.OFFICE_DB.prepare(
        `INSERT INTO office_phase_checklist_items (item_id, phase_id, catalog_id, source_type, source_ref, label, sequence, created_at)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?)`
      ).bind(genId(), phaseId, c.catalog_id, c.source_type, c.source_ref, c.label, i, now).run();
    }
    return json({ ok: true, created: rows.length });
  }

  const item = body.item;
  if (!item || !item.label || !item.source_type) return err('item (with label, source_type) required when not seeding from_catalog', 400);
  const itemId = genId();
  await env.OFFICE_DB.prepare(
    `INSERT INTO office_phase_checklist_items (item_id, phase_id, catalog_id, source_type, source_ref, label, sequence, created_at)
     VALUES (?, ?, NULL, ?, ?, ?, ?, ?)`
  ).bind(itemId, phaseId, item.source_type, item.source_ref || null, item.label, item.sequence || 0, now).run();
  return json({ ok: true, item_id: itemId, created: 1 });
}

async function handleListChecklist(projectId, phaseId, req, env) {
  if (!isAuthorized(req, env)) return err('unauthorized', 401);
  const rows = await env.OFFICE_DB.prepare(
    'SELECT * FROM office_phase_checklist_items WHERE phase_id = ? ORDER BY sequence ASC'
  ).bind(phaseId).all();
  return json({ ok: true, items: rows.results || [] });
}

// The guided-choice determination itself — a two-write, same pattern as
// legal-hold place/release: update the fast-render current-status row AND
// append to the immutable audit trail. This IS the SBA/HUBZone evidence.
async function handleChecklistDecision(itemId, req, env) {
  if (!isAuthorized(req, env)) return err('unauthorized', 401);
  let body;
  try { body = await req.json(); } catch { return err('body must be JSON', 400); }
  const { disposition, by, rationale, linked_doc_hex } = body || {};
  if (!['satisfied', 'not_applicable', 'open'].includes(disposition)) return err('disposition must be satisfied, not_applicable, or open', 400);
  if (!by) return err('by (author_id) required', 400);
  if (!rationale || !String(rationale).trim()) return err('rationale required — a determination must be documented', 400);
  const rationaleText = String(rationale).trim();

  const item = await env.OFFICE_DB.prepare('SELECT item_id FROM office_phase_checklist_items WHERE item_id = ?').bind(itemId).first();
  if (!item) return err('checklist item not found', 404);

  const now = new Date().toISOString();
  await env.OFFICE_DB.prepare(
    `UPDATE office_phase_checklist_items SET disposition = ?, decided_by = ?, decided_at = ?, rationale = ?, linked_doc_hex = ? WHERE item_id = ?`
  ).bind(disposition, by, now, rationaleText, linked_doc_hex || null, itemId).run();
  await env.OFFICE_DB.prepare(
    `INSERT INTO office_checklist_decisions (item_id, disposition, by, rationale, linked_doc_hex, at) VALUES (?, ?, ?, ?, ?, ?)`
  ).bind(itemId, disposition, by, rationaleText, linked_doc_hex || null, now).run();

  return json({ ok: true, item_id: itemId, disposition });
}

async function handleChecklistItemHistory(itemId, req, env) {
  if (!isAuthorized(req, env)) return err('unauthorized', 401);
  const rows = await env.OFFICE_DB.prepare(
    'SELECT disposition, by, rationale, linked_doc_hex, at FROM office_checklist_decisions WHERE item_id = ? ORDER BY at ASC'
  ).bind(itemId).all();
  return json({ ok: true, events: rows.results || [] });
}

async function handleChecklistCatalog(req, env) {
  if (!isAuthorized(req, env)) return err('unauthorized', 401);
  const url = new URL(req.url);
  const phaseType = url.searchParams.get('phase_type');
  const q = phaseType
    ? env.OFFICE_DB.prepare('SELECT * FROM office_checklist_catalog WHERE active = 1 AND (phase_type = ? OR phase_type = ?) ORDER BY phase_type').bind(phaseType, 'general')
    : env.OFFICE_DB.prepare('SELECT * FROM office_checklist_catalog WHERE active = 1 ORDER BY phase_type');
  const rows = await q.all();
  return json({ ok: true, items: rows.results || [] });
}

async function handleProjectDocuments(projectId, req, env) {
  if (!isAuthorized(req, env)) return err('unauthorized', 401);
  const url = new URL(req.url);
  const phaseId = url.searchParams.get('phase_id');
  const q = phaseId
    ? env.OFFICE_DB.prepare('SELECT hex, b58, state, title, doc_role, phase_id, signed_at, created_at FROM office_documents WHERE project_id = ? AND phase_id = ? ORDER BY created_at DESC').bind(projectId, phaseId)
    : env.OFFICE_DB.prepare('SELECT hex, b58, state, title, doc_role, phase_id, signed_at, created_at FROM office_documents WHERE project_id = ? ORDER BY created_at DESC').bind(projectId);
  const rows = await q.all();
  return json({ ok: true, items: rows.results || [] });
}

// Segment-based dispatch for the whole /projects/... tree — see the section
// comment above for why (the nesting is 5-7 segments deep in places).
async function routeProjects(path, req, env) {
  const seg = path.split('/').filter(Boolean); // 'projects', ':id', 'phases', ...

  if (seg.length === 1) {
    if (req.method === 'GET') return handleListProjects(req, env);
    if (req.method === 'POST') return handleCreateProject(req, env);
  }
  if (seg.length === 2) {
    if (req.method === 'GET') return handleGetProject(decodeURIComponent(seg[1]), req, env);
    if (req.method === 'PATCH') return handlePatchProject(decodeURIComponent(seg[1]), req, env);
  }
  if (seg.length === 3 && seg[2] === 'phases') {
    if (req.method === 'GET') return handleListPhases(decodeURIComponent(seg[1]), req, env);
    if (req.method === 'POST') return handleCreatePhases(decodeURIComponent(seg[1]), req, env);
  }
  if (seg.length === 3 && seg[2] === 'documents' && req.method === 'GET') {
    return handleProjectDocuments(decodeURIComponent(seg[1]), req, env);
  }
  if (seg.length === 4 && seg[2] === 'phases' && req.method === 'PATCH') {
    return handlePatchPhase(decodeURIComponent(seg[1]), decodeURIComponent(seg[3]), req, env);
  }
  if (seg.length === 5 && seg[2] === 'phases' && seg[4] === 'checklist') {
    const [, projectId, , phaseId] = seg;
    if (req.method === 'GET') return handleListChecklist(decodeURIComponent(projectId), decodeURIComponent(phaseId), req, env);
    if (req.method === 'POST') return handleSeedOrAddChecklistItem(decodeURIComponent(projectId), decodeURIComponent(phaseId), req, env);
  }
  if (seg.length === 7 && seg[2] === 'phases' && seg[4] === 'checklist' && seg[6] === 'decision' && req.method === 'POST') {
    return handleChecklistDecision(decodeURIComponent(seg[5]), req, env);
  }
  if (seg.length === 7 && seg[2] === 'phases' && seg[4] === 'checklist' && seg[6] === 'history' && req.method === 'GET') {
    return handleChecklistItemHistory(decodeURIComponent(seg[5]), req, env);
  }

  return err('not found', 404);
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
    `SELECT id, ack_token, escalation_level, send_count, to_address, doc_hash, attempt_field, attempt_at, last_sent_at
       FROM office_notifications
      WHERE acknowledged_at IS NULL
        AND send_count < ?
        AND (last_sent_at IS NULL OR last_sent_at < ?)
      ORDER BY last_sent_at ASC NULLS FIRST
      LIMIT 50`
  ).bind(MAX_SENDS, cutoff).all();

  let resent = 0;
  for (const r of open.results || []) {
    if (r.last_sent_at && Date.now() - new Date(r.last_sent_at).getTime() < resendGapMs(r.escalation_level)) continue;
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
      let token;
      try { token = decodeURIComponent(path.slice('/ack/'.length)); } catch { token = ''; }
      return handleAck(token, env, req.method);
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

    if (path === '/jobs' && req.method === 'GET') return handleListJobs(req, env);
    if (path === '/jobs' && req.method === 'POST') return handleSaveJob(req, env);
    if (path.startsWith('/jobs/') && req.method === 'DELETE') {
      return handleDeleteJob(decodeURIComponent(path.slice('/jobs/'.length)), req, env);
    }

    if (path.startsWith('/runtime/')) {
      const name = decodeURIComponent(path.slice('/runtime/'.length));
      if (req.method === 'GET') return handleGetRuntime(name, req, env);
      if (req.method === 'HEAD') return handleHeadRuntime(name, req, env);
    }

    if (path === '/documents' && req.method === 'GET') return handleListDocuments(req, env);
    if (path === '/legal-holds' && req.method === 'GET') return handleLegalHoldsReport(req, env);

    if (path === '/checklist-catalog' && req.method === 'GET') return handleChecklistCatalog(req, env);
    if (path === '/projects' || path.startsWith('/projects/')) return routeProjects(path, req, env);

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
