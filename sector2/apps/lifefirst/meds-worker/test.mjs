// Smoke test for meds-worker: mock D1 + captured fetch, drive the lifecycle.
import worker from './index.js';

// ---- tiny in-memory D1 shim (only the shapes the worker uses) ----
const db = { medication_state: [], medication_log: [], med_alerts: [], _alertId: 0, _logId: 0 };
const sent = [];

globalThis.fetch = async (url, opts) => {
  sent.push({ url: String(url), body: opts?.body?.toString?.() ?? null });
  return { ok: true, status: 200, text: async () => 'ok' };
};

function prepare(sql) {
  const s = sql.replace(/\s+/g, ' ').trim();
  let binds = [];
  const api = {
    bind: (...a) => { binds = a; return api; },
    async run() { return exec(s, binds); },
    async first() { const r = exec(s, binds); return r.rows[0] ?? null; },
    async all() { const r = exec(s, binds); return { results: r.rows }; },
  };
  return api;
}
function exec(s, b) {
  // medication_state
  if (s.startsWith('SELECT * FROM medication_state WHERE user_id = ?'))
    return { rows: db.medication_state.filter(r => r.user_id === b[0]) };
  if (s.startsWith('SELECT * FROM medication_state WHERE active = 1'))
    return { rows: db.medication_state.filter(r => r.active === 1) };
  if (s.startsWith('INSERT INTO medication_state')) {
    const [user_id, med_label, window_hours, grace_minutes, active, next_check_at, updated_at] = b;
    const ex = db.medication_state.find(r => r.user_id === user_id);
    if (ex) Object.assign(ex, { med_label, window_hours, grace_minutes, active, updated_at });
    else db.medication_state.push({ user_id, med_label, window_hours, grace_minutes, active, next_check_at, updated_at, last_dose_at: null });
    return { rows: [] };
  }
  if (s.startsWith('UPDATE medication_state SET last_dose_at')) {
    const [last_dose_at, next_check_at, updated_at, user_id] = b;
    const r = db.medication_state.find(x => x.user_id === user_id);
    Object.assign(r, { last_dose_at, next_check_at, updated_at });
    return { rows: [] };
  }
  // medication_log
  if (s.startsWith('INSERT INTO medication_log')) {
    db.medication_log.push({ id: ++db._logId, user_id: b[0], dose_at: b[1], recorded_via: b[2], note: b[3] });
    return { rows: [] };
  }
  if (s.includes('FROM medication_log'))
    return { rows: db.medication_log.slice(-2).reverse() };
  // med_alerts
  if (s.startsWith('SELECT id FROM med_alerts WHERE user_id = ? AND acknowledged_at IS NULL AND due_at = ?'))
    return { rows: db.med_alerts.filter(r => r.user_id === b[0] && !r.acknowledged_at && r.due_at === b[1]).map(r => ({ id: r.id })) };
  if (s.startsWith('INSERT INTO med_alerts')) {
    const a = { id: ++db._alertId, user_id: b[0], due_at: b[1], ack_token: b[2], escalation_level: 1, send_count: 0, channels_last: null, last_sent_at: null, acknowledged_at: null, acknowledged_via: null, caregiver_notified_at: null, created_at: new Date().toISOString() };
    db.med_alerts.push(a);
    return { rows: [{ id: a.id, created_at: a.created_at }] };
  }
  if (s.startsWith('SELECT id, user_id, acknowledged_at FROM med_alerts WHERE ack_token = ?'))
    return { rows: db.med_alerts.filter(r => r.ack_token === b[0]).map(r => ({ id: r.id, user_id: r.user_id, acknowledged_at: r.acknowledged_at })) };
  if (s.startsWith('SELECT id, escalation_level, send_count, created_at, last_sent_at, caregiver_notified_at FROM med_alerts'))
    return { rows: db.med_alerts.filter(r => r.user_id === b[0] && !r.acknowledged_at).slice(-1) };
  if (s.startsWith('UPDATE med_alerts SET acknowledged_at = ?, acknowledged_via = ? WHERE user_id = ?')) {
    db.med_alerts.filter(r => r.user_id === b[2] && !r.acknowledged_at).forEach(r => { r.acknowledged_at = b[0]; r.acknowledged_via = b[1]; });
    return { rows: [] };
  }
  if (s.startsWith('UPDATE med_alerts SET escalation_level = ? WHERE id = ?')) {
    const r = db.med_alerts.find(x => x.id === b[1]); if (r) r.escalation_level = b[0];
    return { rows: [] };
  }
  if (s.startsWith('UPDATE med_alerts SET send_count = send_count + 1')) {
    const r = db.med_alerts.find(x => x.id === b[3]);
    if (r) { r.send_count++; r.channels_last = b[0]; r.last_sent_at = b[1]; r.caregiver_notified_at = r.caregiver_notified_at ?? b[2]; }
    return { rows: [] };
  }
  if (s.includes('FROM med_alerts a JOIN medication_state s')) {
    return { rows: db.med_alerts.filter(r => !r.acknowledged_at).map(r => {
      const st = db.medication_state.find(x => x.user_id === r.user_id);
      return { ...r, med_label: st.med_label, window_hours: st.window_hours, grace_minutes: st.grace_minutes };
    }) };
  }
  throw new Error('unhandled SQL: ' + s);
}

const env = {
  DB: { prepare },
  PHOENIX_AUTH: 'test-token',
  WORKER_PUBLIC_URL: 'https://meds-worker.test',
  PUSHOVER_TOKEN: 'ptok', PUSHOVER_USER_LAURIE: 'laurie-key', PUSHOVER_USER_JERRY: 'jerry-key',
};
const _pending = [];
const ctx = { waitUntil: (p) => _pending.push(p) };
const cron = async () => { await worker.scheduled({}, env, ctx); await Promise.all(_pending.splice(0)); };
const H = { Authorization: 'Bearer test-token', 'Content-Type': 'application/json' };
const B = 'https://meds-worker.test';
let pass = 0, fail = 0;
const ok = (c, m) => { c ? (pass++, console.log('  ok  ' + m)) : (fail++, console.log('  FAIL ' + m)); };

// 1. configure Laurie (never dosed -> next_check_at = now)
let r = await worker.fetch(new Request(B + '/configure', { method: 'POST', headers: H, body: JSON.stringify({ user_id: 2, med_label: 'your morning pills', window_hours: 24 }) }), env);
let j = await r.json();
ok(r.status === 200 && j.state.user_id === 2, 'configure creates guardrail');
ok(j.state.active === 1, 'guardrail active');

// 2. status -> ask true (never dosed)
r = await worker.fetch(new Request(B + '/status?user_id=2', { headers: H }), env);
j = await r.json();
ok(j.ask === true && j.due === true, 'status: ask+due true before first dose');

// 3. cron pass 1 opens a check-in and sends
await cron();
ok(db.med_alerts.length === 1, 'cron opened exactly one alert');
ok(db.med_alerts[0].send_count === 1, 'alert sent once');
ok(sent.some(s => s.url.includes('pushover')), 'pushover fired');
const tok = db.med_alerts[0].ack_token;

// 4. cron again immediately -> no duplicate alert, no re-send (not stale)
sent.length = 0;
await cron();
ok(db.med_alerts.length === 1, 'no duplicate alert on next tick');
ok(db.med_alerts[0].send_count === 1, 'no premature re-send');

// 5. simulate staleness -> escalate
db.med_alerts[0].last_sent_at = new Date(Date.now() - 20 * 60 * 1000).toISOString();
await cron();
ok(db.med_alerts[0].escalation_level === 2, 'escalated to level 2 when stale');
ok(db.med_alerts[0].send_count === 2, 're-sent on escalation');

// 6. simulate 1h old -> caregiver looped in
db.med_alerts[0].last_sent_at = new Date(Date.now() - 20 * 60 * 1000).toISOString();
db.med_alerts[0].created_at = new Date(Date.now() - 70 * 60 * 1000).toISOString();
sent.length = 0;
await cron();
ok(!!db.med_alerts[0].caregiver_notified_at, 'caregiver_notified_at stamped past threshold');
ok(sent.some(s => s.body && s.body.includes('jerry-key')), 'pushover sent to Jerry');

// 7. ack link -> dose logged, cycle closed, window advanced
r = await worker.fetch(new Request(B + '/ack/' + tok), env);
ok(r.status === 200, 'ack page 200');
ok(db.medication_log.length === 1 && db.medication_log[0].recorded_via === 'link-ack', 'dose logged via link-ack');
ok(db.med_alerts[0].acknowledged_at != null, 'alert cycle closed');
const st = db.medication_state[0];
const adv = new Date(st.next_check_at).getTime() - Date.now();
ok(adv > 23 * 3600 * 1000 && adv < 25 * 3600 * 1000, 'next_check_at advanced ~24h');

// 8. status now -> ask false
r = await worker.fetch(new Request(B + '/status?user_id=2', { headers: H }), env);
j = await r.json();
ok(j.ask === false && j.due === false, 'status: ask false after dose');

// 9. cron after ack -> nothing new
const beforeCount = db.med_alerts.length;
await cron();
ok(db.med_alerts.length === beforeCount, 'no new alert while covered');

// 10. unauthorized
r = await worker.fetch(new Request(B + '/status?user_id=2'), env);
ok(r.status === 401, 'status requires auth');

// 11. Laurie cannot disable via record-dose spoof of "active" — no such path
r = await worker.fetch(new Request(B + '/record-dose', { method: 'POST', headers: H, body: JSON.stringify({ user_id: 2, active: 0 }) }), env);
j = await r.json();
ok(db.medication_state[0].active === 1, 'record-dose never touches active flag');

console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
