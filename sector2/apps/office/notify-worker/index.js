// office-notify-worker — Phoenix Office, Module 3 (2026-09-07)
// UnitedSys — United Systems | jwl247 | GPL-3.0
//
// The standalone alteration-attempt notification path. When someone tampers
// with a SIGNED .office document, the counterparty (DESIGN.md's oil-change
// customer — no Phoenix account, no Life First) gets told, and keeps being
// told until they acknowledge.
//
// Split out on purpose: this worker must keep working with zero Phoenix
// machine running, so the protection never depends on the author's box.
// It does NOT touch packages-worker or phoenix-clonepool-r2.
//
// Routes
//   GET  /health          worker + bindings status (no auth)
//   GET  /whoami          auth round-trip, no side effects (Bearer PHOENIX_AUTH)
//   POST /notify          create + send a notification         (Bearer PHOENIX_AUTH)
//                         body: { doc_hex, notice }   notice = notify.js buildAlterationNotice() output
//   GET  /ack/:token      counterparty acknowledges; stops escalation (token IS the auth)
//
// scheduled()  cron (* * * * *) — re-send every unacknowledged notification
//              whose last send is stale, escalating the subject, level capped at 5.

const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
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
  return token && token === (env.PHOENIX_AUTH || '').trim();
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
// Resend is the working path (arbitrary recipients: carrier SMS gateways +
// plain email). send_email is a Cloudflare-native fallback that only reaches
// VERIFIED addresses — usable for an issuer copy, not the customer. Throws
// if neither is configured (a real failure, surfaced, not swallowed).
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
    // Cloudflare Email Routing send binding. Hand-rolled minimal MIME to keep
    // this worker dependency-free (matches phoenix-clonepool-r2). Recipient
    // must be the binding's verified destination_address.
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
  await env.PHOENIX_DB.prepare(
    `UPDATE office_notifications
       SET send_count = send_count + 1,
           last_sent_at = ?,
           last_error = ?
     WHERE id = ?`
  ).bind(new Date().toISOString(), lastError, row.id).run();
  return { sent: !lastError, error: lastError };
}

// ── HTTP ─────────────────────────────────────────────────────────────────────
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
  // doc.hash is { sha3, blake2 } (document.js contentHash) — flatten for the TEXT column
  const docHashStr = notice.doc_hash == null
    ? null
    : (typeof notice.doc_hash === 'object' ? JSON.stringify(notice.doc_hash) : String(notice.doc_hash));

  const ins = await env.PHOENIX_DB.prepare(
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

  return json({
    ok: true,
    notification_id: ins.id,
    ack_token: token,
    ack_url: ackUrl(env, origin, token),
    sent: result.sent,
    error: result.error,
  }, result.sent ? 200 : 502);
}

async function handleAck(token, env) {
  if (!token) return err('token required', 400);
  const row = await env.PHOENIX_DB.prepare(
    'SELECT id, acknowledged_at FROM office_notifications WHERE ack_token = ?'
  ).bind(token).first();

  if (!row) {
    return new Response(ackPage('This link is not valid.', false), {
      status: 404, headers: { 'Content-Type': 'text/html; charset=utf-8', ...CORS },
    });
  }
  if (!row.acknowledged_at) {
    await env.PHOENIX_DB.prepare(
      'UPDATE office_notifications SET acknowledged_at = ? WHERE id = ? AND acknowledged_at IS NULL'
    ).bind(new Date().toISOString(), row.id).run();
  }
  return new Response(ackPage("Got it — you won't be contacted about this again.", true), {
    status: 200, headers: { 'Content-Type': 'text/html; charset=utf-8', ...CORS },
  });
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
  const open = await env.PHOENIX_DB.prepare(
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
      await env.PHOENIX_DB.prepare(
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
        worker: 'office-notify-worker',
        db_bound: !!env.PHOENIX_DB,
        transport: env.RESEND_API_KEY ? 'resend' : (env.ISSUER_COPY ? 'cloudflare-email-routing' : 'NONE'),
      });
    }

    if (path === '/whoami') {
      if (!isAuthorized(req, env)) return err('unauthorized', 401);
      return json({ ok: true, worker: 'office-notify-worker' });
    }

    if (path === '/notify' && req.method === 'POST') return handleNotify(req, env);

    if (path.startsWith('/ack/')) {
      return handleAck(decodeURIComponent(path.slice('/ack/'.length)), env);
    }

    return err('not found', 404);
  },

  async scheduled(event, env, ctx) {
    ctx.waitUntil(runEscalation(env));
  },
};
