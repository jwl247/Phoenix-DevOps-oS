// meds-worker — Laurie's medication guardrail (2026-09-09)
// UnitedSys — United Systems | jwl247 | GPL-3.0
//
// Adaptive once-a-day reminder anchored to when she LAST actually took the
// dose (last_dose_at + window_hours), not a fixed clock time. She can
// ACKNOWLEDGE a dose; she cannot turn the guardrail off, snooze it forever,
// or change the window — that control lives with Jerry (worker secrets are
// Jerry's Pushover / Resend / Twilio, and `medication_state.active` is a
// Jerry-only switch). See memory: laurie-medication-guardrail.
//
// Split out as its own worker on purpose (same call as Office's notify-worker
// vs packages-worker): the guardrail must keep working with ZERO Phoenix
// machine running. It shares the lifefirst-db D1 but owns only the 3
// medication_* tables (schema.sql). lifefirst-mcp's source is not local and
// is not touched here.
//
// Routes
//   GET  /health                 worker + binding + which transports are live (no auth)
//   GET  /whoami                 auth round-trip, no side effects (Bearer PHOENIX_AUTH)
//   GET  /status?user_id=2       current med state + whether a dose is due  (Bearer)
//   POST /configure              Jerry sets up / adjusts a user's guardrail (Bearer)
//                                body: { user_id, med_label?, window_hours?, grace_minutes?, active? }
//   POST /record-dose            log a confirmed dose, advance the window   (Bearer)
//                                body: { user_id, dose_at?, via?, note? }
//   GET  /ack/:token             Laurie taps the reminder link -> dose logged, cycle closed
//                                (the token itself is the auth; single-use per cycle)
//
// scheduled()  cron (*/5 * * * *) — three passes, all timestamp-gated:
//   1. open a new alert cycle for any active state whose dose is now due
//   2. re-send any open (unacknowledged) alert whose last send is stale,
//      escalating the message, level capped at 5
//   3. once an open alert is older than the caregiver threshold, loop Jerry in
//      and keep him looped in on every subsequent re-send

const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Authorization, Content-Type',
};

// Cadence. Cron granularity is 5 min; these are the thresholds it gates on.
const RESEND_STALE_MS     = 14 * 60 * 1000;   // re-send an open alert once its last send is older than this (~15 min cycle)
const CAREGIVER_AFTER_MS  = 55 * 60 * 1000;   // loop Jerry in once an alert has been open ~1 h with no ack
const DUE_GRACE_MS        = 0;                 // extra slack past next_check_at before the first alert (overridden per-user by grace_minutes)
const MAX_LEVEL           = 5;
const LAURIE_USER_ID      = 2;                 // lifefirst-db users.user_id — 'laurie'

// ── small helpers ────────────────────────────────────────────────────────────
function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...CORS },
  });
}
function err(message, status = 400) {
  return json({ status: 'error', message }, status);
}
function nowIso() {
  return new Date().toISOString();
}
function addHoursIso(iso, hours) {
  return new Date(new Date(iso).getTime() + hours * 3600 * 1000).toISOString();
}
function msSince(iso) {
  if (!iso) return Infinity;
  return Date.now() - new Date(iso).getTime();
}
function isAuthorized(req, env) {
  const token = req.headers.get('Authorization')?.replace('Bearer ', '').trim();
  return token && token === (env.PHOENIX_AUTH || '').trim();
}
// URL-safe, single-use. 32 bytes -> 43-char base64url.
function genToken() {
  const b = new Uint8Array(32);
  crypto.getRandomValues(b);
  return btoa(String.fromCharCode(...b)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

// ── message copy ─────────────────────────────────────────────────────────────
// Warm and plain. One thing at a time. Louder the longer it goes unanswered,
// but never scolding — she is high-functioning autistic and this is her cushion.
function laurieMessage(level, medLabel) {
  const link = '{{LINK}}'; // deliver() substitutes the real ack URL
  const base = `Hi Laurie — have you taken ${medLabel} today?\nIf yes, tap here and you're all set: ${link}`;
  if (level <= 1) return { title: 'Medication check-in', body: base };
  if (level === 2) return { title: 'Medication check-in', body: `Just checking back in.\n\n${base}` };
  if (level === 3) return { title: 'Please check in', body: `Still need to hear from you about ${medLabel} today.\n\n${base}` };
  if (level === 4) return { title: 'Please check in', body: `It's been a while. When you get a moment:\n\n${base}\n\nIf you've already taken them, tapping the link is all it needs.` };
  return { title: 'Please check in', body: `Checking on you, Laurie. Have you taken ${medLabel} today?\n${link}\n\nJerry is being let know too, just so someone can help if you need it.` };
}
function caregiverMessage(medLabel, openedAt, level) {
  return {
    title: 'Laurie — medication not confirmed',
    body:
      `Laurie hasn't confirmed ${medLabel} for today.\n` +
      `Reminder opened ${openedAt} (escalation level ${level}).\n` +
      `She's still being reminded on her phone. Reach out if you can.`,
  };
}

// ── transports ───────────────────────────────────────────────────────────────
// Each returns 'ok' | 'skip' | 'err:<reason>'. NEVER throws — a dead channel
// must not take the others down or crash the cron.
async function sendPushover(env, userKey, { title, body, emergency }) {
  if (!env.PUSHOVER_TOKEN || !userKey) return 'skip';
  try {
    const form = new URLSearchParams({
      token: env.PUSHOVER_TOKEN,
      user: userKey,
      title,
      message: body,
    });
    if (emergency) {
      // Pushover's own relentless-until-acknowledged mode — a second safety
      // net under our cron: retries every 15 min, gives up after 6 h.
      form.set('priority', '2');
      form.set('retry', '900');
      form.set('expire', '21600');
    } else {
      form.set('priority', '1');
    }
    const r = await fetch('https://api.pushover.net/1/messages.json', { method: 'POST', body: form });
    if (!r.ok) return `err:pushover ${r.status} ${(await r.text()).slice(0, 160)}`;
    return 'ok';
  } catch (e) {
    return `err:pushover ${String(e && e.message || e).slice(0, 160)}`;
  }
}
async function sendEmail(env, to, { title, body }) {
  if (!env.RESEND_API_KEY || !to) return 'skip';
  try {
    const from = env.MEDS_FROM || 'Life First <lifefirst@authenticcoder.com>';
    const r = await fetch('https://api.resend.com/emails', {
      method: 'POST',
      headers: { Authorization: `Bearer ${env.RESEND_API_KEY}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ from, to: [to], subject: title, text: body }),
    });
    if (!r.ok) return `err:resend ${r.status} ${(await r.text()).slice(0, 160)}`;
    return 'ok';
  } catch (e) {
    return `err:resend ${String(e && e.message || e).slice(0, 160)}`;
  }
}
async function sendSms(env, to, { body }) {
  if (!env.TWILIO_ACCOUNT_SID || !env.TWILIO_AUTH_TOKEN || !env.TWILIO_FROM || !to) return 'skip';
  try {
    const form = new URLSearchParams({ To: to, From: env.TWILIO_FROM, Body: body });
    const r = await fetch(
      `https://api.twilio.com/2010-04-01/Accounts/${env.TWILIO_ACCOUNT_SID}/Messages.json`,
      {
        method: 'POST',
        headers: {
          Authorization: 'Basic ' + btoa(`${env.TWILIO_ACCOUNT_SID}:${env.TWILIO_AUTH_TOKEN}`),
          'Content-Type': 'application/x-www-form-urlencoded',
        },
        body: form,
      }
    );
    if (!r.ok) return `err:twilio ${r.status} ${(await r.text()).slice(0, 160)}`;
    return 'ok';
  } catch (e) {
    return `err:twilio ${String(e && e.message || e).slice(0, 160)}`;
  }
}

function transportStatus(env) {
  return {
    pushover: env.PUSHOVER_TOKEN && env.PUSHOVER_USER_LAURIE ? 'ready' : 'unset',
    email: env.RESEND_API_KEY && env.LAURIE_EMAIL ? 'ready' : 'unset',
    sms: env.TWILIO_ACCOUNT_SID && env.TWILIO_AUTH_TOKEN && env.TWILIO_FROM && env.LAURIE_SMS ? 'ready' : 'unset',
    caregiver_pushover: env.PUSHOVER_TOKEN && env.PUSHOVER_USER_JERRY ? 'ready' : 'unset',
  };
}

// ── ack link ─────────────────────────────────────────────────────────────────
function ackUrl(env, origin, token) {
  const base = (origin || env.WORKER_PUBLIC_URL || '').replace(/\/+$/, '');
  return `${base}/ack/${token}`;
}

// ── one send of an open alert, + the row bookkeeping ─────────────────────────
async function deliverAlert(env, alert, state, origin, { toCaregiver } = {}) {
  const link = ackUrl(env, origin, alert.ack_token);
  const medLabel = state.med_label || 'your medication';

  const lm = laurieMessage(alert.escalation_level, medLabel);
  const laurieBody = lm.body.replace('{{LINK}}', link);

  const channels = {};
  channels.pushover = await sendPushover(env, env.PUSHOVER_USER_LAURIE, {
    title: lm.title, body: laurieBody, emergency: alert.escalation_level >= 3,
  });
  channels.email = await sendEmail(env, env.LAURIE_EMAIL, { title: lm.title, body: laurieBody });
  channels.sms = await sendSms(env, env.LAURIE_SMS, { body: laurieBody });

  if (toCaregiver) {
    const cm = caregiverMessage(medLabel, alert.created_at, alert.escalation_level);
    channels.caregiver_pushover = await sendPushover(env, env.PUSHOVER_USER_JERRY, { title: cm.title, body: cm.body });
    channels.caregiver_email = await sendEmail(env, env.CAREGIVER_EMAIL, { title: cm.title, body: cm.body });
    channels.caregiver_sms = await sendSms(env, env.CAREGIVER_SMS, { body: cm.body });
  }

  const delivered = Object.entries(channels).some(([, v]) => v === 'ok');

  await env.DB.prepare(
    `UPDATE med_alerts
        SET send_count = send_count + 1,
            channels_last = ?,
            last_sent_at = ?,
            caregiver_notified_at = COALESCE(caregiver_notified_at, ?)
      WHERE id = ?`
  ).bind(
    JSON.stringify(channels),
    nowIso(),
    toCaregiver ? nowIso() : null,
    alert.id
  ).run();

  return { delivered, channels };
}

// ── close an open cycle: log the dose, advance the window ────────────────────
async function recordDose(env, userId, { doseAt, via, note }) {
  const state = await env.DB.prepare('SELECT * FROM medication_state WHERE user_id = ?').bind(userId).first();
  if (!state) return { ok: false, reason: 'no guardrail configured for this user' };

  const when = doseAt || nowIso();
  const method = via || 'assistant';

  await env.DB.prepare(
    'INSERT INTO medication_log (user_id, dose_at, recorded_via, note) VALUES (?, ?, ?, ?)'
  ).bind(userId, when, method, note || null).run();

  const nextCheck = addHoursIso(when, state.window_hours || 24);
  await env.DB.prepare(
    `UPDATE medication_state
        SET last_dose_at = ?, next_check_at = ?, updated_at = ?
      WHERE user_id = ?`
  ).bind(when, nextCheck, nowIso(), userId).run();

  // close every open alert cycle for this user
  await env.DB.prepare(
    `UPDATE med_alerts
        SET acknowledged_at = ?, acknowledged_via = ?
      WHERE user_id = ? AND acknowledged_at IS NULL`
  ).bind(nowIso(), method, userId).run();

  return { ok: true, dose_at: when, next_check_at: nextCheck };
}

// ── HTTP handlers ────────────────────────────────────────────────────────────
async function handleStatus(url, env) {
  const userId = parseInt(url.searchParams.get('user_id') || `${LAURIE_USER_ID}`, 10);
  const state = await env.DB.prepare('SELECT * FROM medication_state WHERE user_id = ?').bind(userId).first();
  if (!state) return json({ configured: false, user_id: userId });

  const overdueMs = Date.now() - new Date(state.next_check_at).getTime();
  const grace = (state.grace_minutes || 0) * 60 * 1000 + DUE_GRACE_MS;
  const due = state.active === 1 && overdueMs >= grace;

  const openAlert = await env.DB.prepare(
    `SELECT id, escalation_level, send_count, created_at, last_sent_at, caregiver_notified_at
       FROM med_alerts
      WHERE user_id = ? AND acknowledged_at IS NULL
      ORDER BY created_at DESC LIMIT 1`
  ).bind(userId).first();

  return json({
    configured: true,
    user_id: userId,
    med_label: state.med_label,
    active: state.active === 1,
    window_hours: state.window_hours,
    last_dose_at: state.last_dose_at,
    next_check_at: state.next_check_at,
    due,
    overdue_minutes: due ? Math.round(overdueMs / 60000) : 0,
    // the assistant should open with "have you taken your pills today?" whenever this is true
    ask: due || !state.last_dose_at,
    open_alert: openAlert || null,
  });
}

async function handleConfigure(req, env) {
  let body;
  try { body = await req.json(); } catch { return err('body must be JSON'); }
  const userId = parseInt(body.user_id, 10);
  if (!userId) return err('user_id required');

  const existing = await env.DB.prepare('SELECT * FROM medication_state WHERE user_id = ?').bind(userId).first();
  const medLabel = body.med_label ?? existing?.med_label ?? 'your medication';
  const windowHours = body.window_hours ?? existing?.window_hours ?? 24;
  const graceMinutes = body.grace_minutes ?? existing?.grace_minutes ?? 0;
  const active = body.active === undefined ? (existing?.active ?? 1) : (body.active ? 1 : 0);
  // never-dosed -> next check is now, so the first cron opens a check-in immediately
  const nextCheck = existing?.next_check_at ?? nowIso();

  await env.DB.prepare(
    `INSERT INTO medication_state (user_id, med_label, window_hours, grace_minutes, active, next_check_at, updated_at)
     VALUES (?, ?, ?, ?, ?, ?, ?)
     ON CONFLICT(user_id) DO UPDATE SET
       med_label = excluded.med_label,
       window_hours = excluded.window_hours,
       grace_minutes = excluded.grace_minutes,
       active = excluded.active,
       updated_at = excluded.updated_at`
  ).bind(userId, medLabel, windowHours, graceMinutes, active, nextCheck, nowIso()).run();

  const state = await env.DB.prepare('SELECT * FROM medication_state WHERE user_id = ?').bind(userId).first();
  return json({ ok: true, state });
}

async function handleRecordDose(req, env) {
  let body;
  try { body = await req.json(); } catch { return err('body must be JSON'); }
  const userId = parseInt(body.user_id, 10);
  if (!userId) return err('user_id required');
  const allowed = ['assistant', 'manual'];
  const via = body.via && allowed.includes(body.via) ? body.via : 'assistant';
  const res = await recordDose(env, userId, { doseAt: body.dose_at, via, note: body.note });
  return res.ok ? json({ ok: true, ...res }) : err(res.reason, 404);
}

function ackPage(message, ok) {
  return `<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Life First</title>
<div style="font:17px/1.6 system-ui,-apple-system,sans-serif;max-width:32rem;margin:16vh auto;padding:0 1.25rem;color:#1a1a1a;text-align:center">
  <div style="font-size:2.4rem">${ok ? '&#10003;' : '&#9888;'}</div>
  <p style="margin:.9rem 0 0;font-size:1.15rem">${message}</p>
  <p style="color:#777;margin-top:1.75rem;font-size:.92rem">You can close this page.</p>
</div>`;
}

async function handleAck(token, env) {
  if (!token) return new Response(ackPage('This link is missing something.', false), {
    status: 400, headers: { 'Content-Type': 'text/html; charset=utf-8', ...CORS },
  });
  const alert = await env.DB.prepare(
    'SELECT id, user_id, acknowledged_at FROM med_alerts WHERE ack_token = ?'
  ).bind(token).first();

  if (!alert) return new Response(ackPage('This link is not valid.', false), {
    status: 404, headers: { 'Content-Type': 'text/html; charset=utf-8', ...CORS },
  });

  if (!alert.acknowledged_at) {
    await recordDose(env, alert.user_id, { via: 'link-ack', note: `ack link, alert ${alert.id}` });
  }
  return new Response(ackPage("Thank you, Laurie. You're all set for today.", true), {
    status: 200, headers: { 'Content-Type': 'text/html; charset=utf-8', ...CORS },
  });
}

// ── scheduled: open cycles, escalate, loop in the caregiver ──────────────────
async function runCron(env) {
  const origin = null; // no inbound request — deliver() falls back to WORKER_PUBLIC_URL
  const summary = { opened: 0, resent: 0, caregiver: 0 };

  // pass 1 — open a fresh cycle for any active guardrail whose dose is now due
  const states = await env.DB.prepare('SELECT * FROM medication_state WHERE active = 1').all();
  for (const state of states.results || []) {
    const overdueMs = Date.now() - new Date(state.next_check_at).getTime();
    const grace = (state.grace_minutes || 0) * 60 * 1000 + DUE_GRACE_MS;
    if (overdueMs < grace) continue;

    const open = await env.DB.prepare(
      'SELECT id FROM med_alerts WHERE user_id = ? AND acknowledged_at IS NULL AND due_at = ?'
    ).bind(state.user_id, state.next_check_at).first();
    if (open) continue;

    const token = genToken();
    const ins = await env.DB.prepare(
      `INSERT INTO med_alerts (user_id, due_at, ack_token, escalation_level, send_count)
       VALUES (?, ?, ?, 1, 0) RETURNING id, created_at`
    ).bind(state.user_id, state.next_check_at, token).first();

    await deliverAlert(env, {
      id: ins.id, ack_token: token, escalation_level: 1, created_at: ins.created_at,
    }, state, origin, { toCaregiver: false });
    summary.opened++;
  }

  // pass 2 + 3 — re-send stale open alerts, escalate, loop Jerry in past the threshold
  const openAlerts = await env.DB.prepare(
    `SELECT a.*, s.med_label, s.window_hours, s.grace_minutes
       FROM med_alerts a
       JOIN medication_state s ON s.user_id = a.user_id
      WHERE a.acknowledged_at IS NULL
      ORDER BY a.created_at ASC
      LIMIT 50`
  ).all();

  for (const a of openAlerts.results || []) {
    if (msSince(a.last_sent_at) < RESEND_STALE_MS) continue;

    const nextLevel = Math.min((a.escalation_level || 1) + 1, MAX_LEVEL);
    if (nextLevel !== a.escalation_level) {
      await env.DB.prepare('UPDATE med_alerts SET escalation_level = ? WHERE id = ?').bind(nextLevel, a.id).run();
    }
    const openMs = msSince(a.created_at);
    const toCaregiver = openMs >= CAREGIVER_AFTER_MS;

    const res = await deliverAlert(
      env,
      { id: a.id, ack_token: a.ack_token, escalation_level: nextLevel, created_at: a.created_at },
      { med_label: a.med_label, window_hours: a.window_hours },
      origin,
      { toCaregiver }
    );
    if (res.delivered) summary.resent++;
    if (toCaregiver) summary.caregiver++;
  }

  return summary;
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
        worker: 'meds-worker',
        db_bound: !!env.DB,
        transports: transportStatus(env),
      });
    }

    if (path === '/whoami') {
      if (!isAuthorized(req, env)) return err('unauthorized', 401);
      return json({ ok: true, worker: 'meds-worker' });
    }

    if (path.startsWith('/ack/')) {
      return handleAck(decodeURIComponent(path.slice('/ack/'.length)), env);
    }

    // everything below is Bearer PHOENIX_AUTH
    if (!isAuthorized(req, env)) return err('unauthorized', 401);

    if (path === '/status' && req.method === 'GET') return handleStatus(url, env);
    if (path === '/configure' && req.method === 'POST') return handleConfigure(req, env);
    if (path === '/record-dose' && req.method === 'POST') return handleRecordDose(req, env);

    return err('not found', 404);
  },

  async scheduled(event, env, ctx) {
    ctx.waitUntil(runCron(env));
  },
};
