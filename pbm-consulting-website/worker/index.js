// pbm-leads-worker — PBM Consulting Service
//
// Lead-capture backend for pbmconsultingservice.com. A visitor submits
// their business info, gets a one-time code emailed to them, and has to
// enter it back to be considered a verified lead. Deliberately "official"
// in tone throughout (the email, the reference number) — this is a
// federal-compliance consulting business; the intake experience should
// feel as careful as the actual certification process it's selling.
//
// Own D1, own secrets (RESEND_API_KEY, and later TURNSTILE_SECRET /
// HUBSPOT_PRIVATE_APP_TOKEN) — same segmentation pattern as every other
// worker in this project (office-notify-worker, phoenix-office-worker),
// not because PBM Consulting is a different company from Phoenix (it
// isn't — see project memory), but because each public-facing surface
// gets its own blast radius regardless of ownership.

function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': 'https://pbmconsultingservice.com' },
  });
}

async function sha256Hex(text) {
  const data = new TextEncoder().encode(text);
  const digest = await crypto.subtle.digest('SHA-256', data);
  return Array.from(new Uint8Array(digest)).map(b => b.toString(16).padStart(2, '0')).join('');
}

function generateCode() {
  // 6 digits, zero-padded — a real verification code, not a UUID fragment
  // that looks like a bug report.
  const n = crypto.getRandomValues(new Uint32Array(1))[0] % 1000000;
  return String(n).padStart(6, '0');
}

function referenceNumber(leadId) {
  // "Official"-feeling case reference, not a raw DB id in the email.
  const year = new Date().getUTCFullYear();
  return `PBM-${year}-${String(leadId).padStart(6, '0')}`;
}

function isValidEmail(email) {
  return typeof email === 'string' && email.length <= 254 && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

// Visitor-supplied text goes into an HTML email sent from PBM's own domain
// to an address the visitor also chose — unescaped, that's a free branded
// phishing relay (arbitrary links/markup under PBM's letterhead).
function escapeHtml(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

// Plain length caps so a scripted client can't park megabytes per row in D1
// or in the HubSpot contact.
const MAX_FIELD = { name: 120, business_name: 200, phone: 40 };
function tooLong(v, max) {
  return v != null && (typeof v !== 'string' || v.length > max);
}

// Turnstile enforcement is off until TURNSTILE_SECRET is actually set
// (the cloudflare:turnstile-spin skill wires this properly once the
// widget exists) — logs a warning rather than silently pretending to
// have checked something it didn't. Once the secret is set, this is a
// real, enforced check, fail-closed on any error.
async function verifyTurnstile(token, ip, env) {
  if (!env.TURNSTILE_SECRET) {
    console.warn('[pbm-leads] TURNSTILE_SECRET not set — bot check is NOT enforced yet');
    return { ok: true, enforced: false };
  }
  if (typeof token !== 'string' || token.length === 0 || token.length > 2048) {
    return { ok: false, enforced: true, error: 'missing or malformed token' };
  }
  const expectedAction = 'lead';
  // Production only — localhost/127.0.0.1 are registered on the widget
  // for local testing but must never be trusted as a valid frontend
  // hostname on the deployed backend.
  const expectedHostnames = new Set((env.TURNSTILE_HOSTNAMES || 'pbmconsultingservice.com').split(',').map(h => h.trim()).filter(Boolean));
  try {
    const res = await fetch('https://challenges.cloudflare.com/turnstile/v0/siteverify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      signal: AbortSignal.timeout(10000),
      body: new URLSearchParams({ secret: env.TURNSTILE_SECRET, response: token, remoteip: ip || '' }),
    });
    if (!res.ok) return { ok: false, enforced: true, error: `siteverify ${res.status}` };
    const result = await res.json();
    if (!result.success) return { ok: false, enforced: true, error: (result['error-codes'] || []).join(',') };
    if (result.action !== expectedAction) return { ok: false, enforced: true, error: `unexpected action: ${result.action}` };
    if (!expectedHostnames.has(result.hostname)) return { ok: false, enforced: true, error: `unexpected hostname: ${result.hostname}` };
    return { ok: true, enforced: true, error: null };
  } catch (e) {
    // Network error, timeout, or non-JSON body — fail closed, not open.
    return { ok: false, enforced: true, error: e.message };
  }
}

function officialEmailHtml({ name, referenceNo, code }) {
  return `<!doctype html><html><body style="margin:0;background:#EFEAD9;font-family:Georgia,serif;color:#2B2620;">
  <div style="max-width:520px;margin:0 auto;padding:32px 28px;background:#fff;border:1px solid #CFC6A8;margin-top:24px;">
    <div style="border-bottom:2px solid #1F3D2B;padding-bottom:14px;margin-bottom:20px;">
      <div style="font-size:18px;font-weight:bold;color:#1F3D2B;">PBM Consulting Service</div>
      <div style="font-size:12px;color:#5a5346;">6814 Chris Madsen Rd, Guthrie, OK 73044</div>
    </div>
    <p style="font-size:13px;color:#5a5346;margin:0 0 4px;">Reference No. ${referenceNo}</p>
    <p>Dear ${name ? escapeHtml(name) : 'Sir or Madam'},</p>
    <p>You have requested a federal set-aside eligibility review with PBM
    Consulting Service. To confirm this request came from you, enter the
    verification code below where you submitted your information.</p>
    <p style="font-size:32px;letter-spacing:6px;font-weight:bold;color:#8C2F1B;text-align:center;margin:28px 0;">${code}</p>
    <p style="font-size:14px;">This code expires 15 minutes from when it was issued and can only be
    used once. If you did not request this review, no action is needed —
    disregard this message.</p>
    <p style="font-size:12px;color:#5a5346;margin-top:28px;">This is an automated message from PBM Consulting Service
    regarding reference ${referenceNo}. Do not reply to this email.</p>
  </div>
</body></html>`;
}

async function sendVerificationEmail(env, { to, name, referenceNo, code }) {
  if (!env.RESEND_API_KEY) return { ok: false, error: 'no send transport configured (RESEND_API_KEY unset)' };
  try {
    const res = await fetch('https://api.resend.com/emails', {
      method: 'POST',
      headers: { Authorization: `Bearer ${env.RESEND_API_KEY}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({
        from: env.RESEND_FROM || 'PBM Consulting Service <onboarding@resend.dev>',
        to: [to],
        subject: `Verification code — reference ${referenceNo}`,
        html: officialEmailHtml({ name, referenceNo, code }),
      }),
    });
    if (!res.ok) return { ok: false, error: `resend ${res.status}: ${(await res.text()).slice(0, 300)}` };
    return { ok: true };
  } catch (e) {
    return { ok: false, error: e.message };
  }
}

async function handleLead(req, env) {
  let body;
  try { body = await req.json(); } catch (_) { return jsonResponse({ ok: false, error: 'invalid JSON body' }, 400); }

  const { name, business_name, email, phone, turnstile_token } = body || {};
  if (!business_name || typeof business_name !== 'string') return jsonResponse({ ok: false, error: 'business_name required' }, 400);
  if (!isValidEmail(email)) return jsonResponse({ ok: false, error: 'a valid email is required' }, 400);
  if (tooLong(name, MAX_FIELD.name) || tooLong(business_name, MAX_FIELD.business_name) || tooLong(phone, MAX_FIELD.phone)) {
    return jsonResponse({ ok: false, error: 'one of the fields is too long' }, 400);
  }

  const ip = req.headers.get('CF-Connecting-IP');
  const turnstile = await verifyTurnstile(turnstile_token, ip, env);
  if (!turnstile.ok) return jsonResponse({ ok: false, error: 'verification failed — please try again' }, 403);

  const code = generateCode();
  const codeHash = await sha256Hex(code);
  const expiresAt = new Date(Date.now() + 15 * 60 * 1000).toISOString();

  // One row per email in flight — a re-submission before verifying just
  // gets a fresh code on the same row rather than piling up duplicates.
  const existing = await env.DB.prepare('SELECT id FROM leads WHERE email = ? AND verified_at IS NULL ORDER BY id DESC LIMIT 1').bind(email).first();
  let leadId;
  if (existing) {
    leadId = existing.id;
    await env.DB.prepare('UPDATE leads SET name=?, business_name=?, phone=?, code_hash=?, code_expires_at=?, attempt_count=0 WHERE id=?')
      .bind(name || null, business_name, phone || null, codeHash, expiresAt, leadId).run();
  } else {
    const inserted = await env.DB.prepare('INSERT INTO leads (name, business_name, email, phone, code_hash, code_expires_at) VALUES (?,?,?,?,?,?)')
      .bind(name || null, business_name, email, phone || null, codeHash, expiresAt).run();
    leadId = inserted.meta.last_row_id;
  }

  const refNo = referenceNumber(leadId);
  const sent = await sendVerificationEmail(env, { to: email, name, referenceNo: refNo, code });

  return jsonResponse({ ok: true, reference: refNo, sent: sent.ok, sendError: sent.ok ? undefined : sent.error, turnstileEnforced: turnstile.enforced });
}

async function handleVerify(req, env) {
  let body;
  try { body = await req.json(); } catch (_) { return jsonResponse({ ok: false, error: 'invalid JSON body' }, 400); }
  const { email, code } = body || {};
  if (!isValidEmail(email) || !code) return jsonResponse({ ok: false, error: 'email and code required' }, 400);

  const row = await env.DB.prepare('SELECT * FROM leads WHERE email = ? AND verified_at IS NULL ORDER BY id DESC LIMIT 1').bind(email).first();
  if (!row) return jsonResponse({ ok: false, error: 'no pending verification for this email' }, 404);

  if (row.attempt_count >= 5) return jsonResponse({ ok: false, error: 'too many attempts — request a new code' }, 429);
  await env.DB.prepare('UPDATE leads SET attempt_count = attempt_count + 1 WHERE id = ?').bind(row.id).run();

  if (new Date(row.code_expires_at).getTime() < Date.now()) return jsonResponse({ ok: false, error: 'code expired — request a new one' }, 410);

  const candidateHash = await sha256Hex(String(code));
  if (candidateHash !== row.code_hash) return jsonResponse({ ok: false, error: 'incorrect code' }, 401);

  await env.DB.prepare("UPDATE leads SET verified_at = datetime('now') WHERE id = ?").bind(row.id).run();

  let hubspotSynced = false;
  if (env.HUBSPOT_PRIVATE_APP_TOKEN) {
    try {
      const res = await fetch('https://api.hubapi.com/crm/v3/objects/contacts', {
        method: 'POST',
        headers: { Authorization: `Bearer ${env.HUBSPOT_PRIVATE_APP_TOKEN}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ properties: { email: row.email, firstname: row.name || '', company: row.business_name, phone: row.phone || '' } }),
      });
      if (res.ok) {
        hubspotSynced = true;
        await env.DB.prepare("UPDATE leads SET hubspot_synced_at = datetime('now') WHERE id = ?").bind(row.id).run();
      }
    } catch (_) { /* best-effort — the verified lead is already safe in D1 either way */ }
  }

  return jsonResponse({ ok: true, reference: referenceNumber(row.id), hubspotSynced });
}

export { isValidEmail, referenceNumber, sha256Hex, generateCode, escapeHtml };

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    if (req.method === 'OPTIONS') {
      return new Response(null, { headers: {
        'Access-Control-Allow-Origin': 'https://pbmconsultingservice.com',
        'Access-Control-Allow-Methods': 'POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type',
      } });
    }
    if (url.pathname === '/health') {
      return jsonResponse({
        status: 'ok', worker: 'pbm-leads-worker',
        db_bound: !!env.DB,
        transport: env.RESEND_API_KEY ? 'resend' : 'NONE',
        turnstile_enforced: !!env.TURNSTILE_SECRET,
        hubspot_wired: !!env.HUBSPOT_PRIVATE_APP_TOKEN,
      });
    }
    if (url.pathname === '/lead' && req.method === 'POST') return handleLead(req, env);
    if (url.pathname === '/verify' && req.method === 'POST') return handleVerify(req, env);
    return jsonResponse({ ok: false, error: 'not found' }, 404);
  },
};
