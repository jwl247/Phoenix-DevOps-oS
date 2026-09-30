// Tests for pbm-radar-worker. Real SQLite (node:sqlite) behind a D1-shaped
// adapter, so schema.sql and every query the worker runs are exercised for
// real — no hand-written SQL shim. SAM.gov and Resend are faked via fetch.
import { readFileSync } from 'node:fs';
import { DatabaseSync } from 'node:sqlite';
import worker, {
  normalize, matches, stateFromText, realCity, isOpen, normSub, eligibleSetAsides, ptypeOf, toSamDate, redact,
  fetchPosted, runRadar, validateSubscriber,
} from './index.js';

// ---------------------------------------------------------------- D1 adapter
function makeD1() {
  const db = new DatabaseSync(':memory:');
  db.exec(readFileSync(new URL('./schema.sql', import.meta.url), 'utf8'));
  const stmt = (sql, binds = []) => ({
    bind: (...a) => stmt(sql, a),
    async run() { const r = db.prepare(sql).run(...binds); return { meta: { last_row_id: Number(r.lastInsertRowid), changes: Number(r.changes) } }; },
    async first() { return db.prepare(sql).get(...binds) ?? null; },
    async all() { return { results: db.prepare(sql).all(...binds) }; },
  });
  return {
    raw: db,
    prepare: sql => stmt(sql),
    async batch(list) { const out = []; for (const s of list) out.push(await s.run()); return out; },
  };
}

// ---------------------------------------------------------------- fake SAM + Resend
const KEY = 'SAMKEY-supersecret-123';
let SAM_NOTICES = [];
let samCalls = [];
let samFail = null;
let emails = [];

function notice(o) {
  return {
    noticeId: o.id, title: o.title || `Bid ${o.id}`, solicitationNumber: `SOL-${o.id}`,
    fullParentPathName: o.agency || 'DEPT OF DEFENSE.DEPT OF THE ARMY.W076 ENDIST TULSA',
    postedDate: '2026-09-28', type: o.type || 'Solicitation',
    responseDeadLine: o.deadline === undefined ? '2099-10-05T14:00:00-05:00' : o.deadline,
    naicsCode: o.naics || '238120', typeOfSetAside: o.sa === undefined ? 'SBA' : o.sa,
    typeOfSetAsideDescription: o.sa || null, active: o.active || 'Yes',
    placeOfPerformance: o.state === null ? undefined : { city: { name: o.city || 'Tulsa' }, state: { code: o.state || 'OK' } },
    uiLink: `https://sam.gov/opp/${o.id}/view`,
  };
}

globalThis.fetch = async (url, opts = {}) => {
  const u = new URL(String(url));
  if (u.hostname === 'api.sam.gov') {
    samCalls.push(u);
    if (samFail) return { ok: false, status: samFail, text: async () => `bad key ${u.searchParams.get('api_key')}` };
    const off = Number(u.searchParams.get('offset')), lim = Number(u.searchParams.get('limit'));
    return { ok: true, status: 200, json: async () => ({ totalRecords: SAM_NOTICES.length, opportunitiesData: SAM_NOTICES.slice(off, off + lim) }) };
  }
  if (u.hostname === 'challenges.cloudflare.com') {
    const tok = new URLSearchParams(String(opts.body)).get('response');
    const v = { good: { success: true, action: 'radar_apply', hostname: 'pbmconsultingservice.com' },
      'wrong-action': { success: true, action: 'lead', hostname: 'pbmconsultingservice.com' },
      'wrong-host': { success: true, action: 'radar_apply', hostname: 'evil.example' } }[tok] || { success: false };
    return { ok: true, status: 200, json: async () => v };
  }
  if (u.hostname === 'api.resend.com') {
    emails.push({ headers: opts.headers, body: JSON.parse(opts.body) });
    return { ok: true, status: 200, text: async () => '{"id":"x"}' };
  }
  throw new Error('unexpected fetch ' + url);
};

function freshEnv(extra = {}) {
  samCalls = []; emails = []; samFail = null;
  return { DB: makeD1(), SAM_API_KEY: KEY, RESEND_API_KEY: 're_test', PHOENIX_AUTH: 'admintok', WORKER_PUBLIC_URL: 'https://radar.test', ...extra };
}

// 2,500 filler notices with no set-aside (dropped) + the real set of cases.
const FILLER = Array.from({ length: 2500 }, (_, i) => notice({ id: `F${i}`, sa: '' }));
const CASES = [
  notice({ id: 'A1', naics: '238120', sa: 'SBA', state: 'OK', title: 'Steel erection <script>x</script>' }),       // match (small)
  notice({ id: 'A2', naics: '238190', sa: 'WOSB', state: 'TX', deadline: '2099-10-01T12:00:00-05:00' }),           // match via edwosb->WOSB, sooner deadline
  notice({ id: 'A3', naics: '238120', sa: 'HZC', state: null }),                                                   // match: no place -> allowed
  notice({ id: 'A4', naics: '238120', sa: 'SDVOSBC', state: 'OK' }),                                               // no: not eligible
  notice({ id: 'A5', naics: '541330', sa: 'SBA', state: 'OK' }),                                                   // no: NAICS
  notice({ id: 'A6', naics: '238120', sa: 'SBA', state: 'CA' }),                                                   // no: state
  notice({ id: 'A7', naics: '238120', sa: 'SBA', state: 'OK', type: 'Award Notice' }),                             // no: ptype
  notice({ id: 'A8', naics: '238120', sa: 'SBA', state: 'OK', active: 'No' }),                                     // dropped: inactive
  notice({ id: 'A9', naics: '238120', sa: '8A', state: 'KS', type: 'Some New SAM Wording' }),                      // match: unknown type passes
  notice({ id: 'B1', naics: '238120', sa: 'SBA', state: 'OK', deadline: '2026-09-20T12:00:00-05:00' }),            // no: closed before the run
];
SAM_NOTICES = [...FILLER, ...CASES];

const PBM = { email: 'pbm@example.com', name: 'PBM', naics: ['2381', '332312'], certs: ['small', 'wosb', 'edwosb', 'hubzone', '8a'], states: ['OK', 'TX', 'KS'], mode: 'planning' };
const TUE = new Date('2026-09-29T12:00:00Z');   // Chicago 2026-09-29 (Tue) -> posted 2026-09-28
const MON = new Date('2026-09-28T12:00:00Z');

const admin = (env, path, method = 'GET', body) => worker.fetch(new Request('https://radar.test' + path, {
  method, headers: { Authorization: 'Bearer admintok', 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined,
}), env);

async function addSub(env, s = PBM) {
  const r = await admin(env, '/subscribers', 'POST', s);
  return (await r.json()).id;
}

// ---------------------------------------------------------------- runner
let pass = 0, fail = 0;
async function t(name, fn) {
  try { await fn(); pass++; console.log('  ok  ' + name); }
  catch (e) { fail++; console.log('  FAIL ' + name + '\n       ' + e.message); }
}
function eq(a, b, m) { if (JSON.stringify(a) !== JSON.stringify(b)) throw new Error(`${m || ''} expected ${JSON.stringify(b)} got ${JSON.stringify(a)}`); }
function ok(c, m) { if (!c) throw new Error(m || 'assertion failed'); }

// ---------------------------------------------------------------- pure logic
await t('normalize drops notices with no set-aside and inactive ones', () => {
  eq(normalize(notice({ id: 'x', sa: '' })), null);
  eq(normalize(notice({ id: 'x', active: 'No' })), null);
  eq(normalize(notice({ id: 'x' })).set_aside, 'SBA');
});
await t('notice type text -> ptype code, unknown -> ?', () => {
  eq(ptypeOf('Combined Synopsis/Solicitation'), 'k');
  eq(ptypeOf('Sources Sought'), 'r');
  eq(ptypeOf('brand new wording'), '?');
});
await t('cert mapping: edwosb also qualifies for WOSB; small -> SBA/SBP', () => {
  const s = eligibleSetAsides(['edwosb']);
  ok(s.has('EDWOSB') && s.has('WOSB') && !s.has('SBA'));
  eq([...eligibleSetAsides(['small'])], ['SBA', 'SBP']);
});
await t('matching: NAICS prefix, state, nationwide, no place, ptype', () => {
  const sub = normSub({ ...PBM, naics: JSON.stringify(PBM.naics), certs: JSON.stringify(PBM.certs), states: JSON.stringify(PBM.states), ptypes: '[]' });
  const got = CASES.map(normalize).filter(Boolean).filter(o => matches(sub, o) && isOpen(o, TUE)).map(o => o.notice_id).sort();
  eq(got, ['A1', 'A2', 'A3', 'A9']);
  const nationwide = { ...sub, states: [] };
  ok(matches(nationwide, normalize(CASES[5])), 'nationwide should take CA');
});
await t('real SAM quirks: state from address text, "0" city, closed bids (seen live 2026-09-27)', () => {
  eq(stateFromText('Yuma Proving Ground (YPG) in Yuma, Arizona'), 'AZ');
  eq(stateFromText('Fort Sill, OK 73503'), 'OK');
  eq(stateFromText('Charleston, West Virginia'), 'WV');
  eq(stateFromText('Building 12, Main Gate'), null);
  eq(realCity('0'), null); eq(realCity('Tulsa'), 'Tulsa');
  const raw = notice({ id: 'Y', state: null });
  raw.placeOfPerformance = { streetAddress: 'Yuma Proving Ground (YPG) in Yuma, Arizona', zip: '' };
  eq(normalize(raw).pop_state, 'AZ');
  const now = new Date('2026-09-27T12:00:00Z');
  eq(isOpen({ response_deadline: '2026-09-26T00:00:00-05:00' }, now), false);
  eq(isOpen({ response_deadline: '2026-10-07T14:00:00-05:00' }, now), true);
  eq(isOpen({ response_deadline: null }, now), true);
});
await t('SAM date format MM/dd/yyyy', () => eq(toSamDate('2026-09-28'), '09/28/2026'));
await t('validateSubscriber rejects bad input', () => {
  ok(validateSubscriber({ email: 'nope', naics: [], certs: ['x'] }).length >= 3);
  eq(validateSubscriber(PBM), []);
  ok(validateSubscriber({ ...PBM, ptypes: ['z'] }).length === 1);
});
await t('redact strips the key everywhere', () => {
  const s = redact(`GET https://api.sam.gov/x?api_key=${KEY}&a=1 failed (${KEY})`, { SAM_API_KEY: KEY });
  ok(!s.includes(KEY), s);
});

// ---------------------------------------------------------------- SAM fetch
await t('fetchPosted pages to totalRecords (2,510 notices = 3 requests), keeps 9 set-asides', async () => {
  const env = freshEnv();
  const f = await fetchPosted(env, '2026-09-28', 8);
  eq(f.requests, 3); eq(f.seen, 2510); eq(f.kept.length, 9); eq(f.capped, false);
  eq(samCalls[0].searchParams.get('postedFrom'), '09/28/2026');
  eq(samCalls[2].searchParams.get('offset'), '2000');
});
await t('fetchPosted stops at the request budget and says so', async () => {
  const f = await fetchPosted(freshEnv(), '2026-09-28', 2);
  eq(f.requests, 2); eq(f.capped, true);
});
await t('SAM error text never carries the key', async () => {
  const env = freshEnv(); samFail = 403;
  const f = await fetchPosted(env, '2026-09-28', 8);
  ok(f.error && f.error.includes('403') && !f.error.includes(KEY), f.error);
});

// ---------------------------------------------------------------- full run
await t('run: fetch, store, match, one digest email with the right content', async () => {
  const env = freshEnv();
  const id = await addSub(env);
  const s = await runRadar(env, { now: TUE });
  eq(s.posted, '2026-09-28'); eq(s.requests_used, 3); eq(s.kept, 9);
  eq(emails.length, 1);
  const m = emails[0].body;
  eq(m.to, ['pbm@example.com']);
  eq(m.subject, 'Radar · 4 set-aside bids for PBM · Tue Sep 29');
  ok(m.text.includes('Checked 2,510 notices posted Mon Sep 28 · 9 were set-asides · 4 matched you.'), 'footer');
  ok(m.text.indexOf('A2') < m.text.indexOf('A1'), 'soonest deadline first');
  ok(m.text.includes('Planning mode'), 'planning banner');
  ok(m.html.includes('&lt;script&gt;') && !m.html.includes('<script>x'), 'SAM text escaped in HTML');
  eq(m.headers['List-Unsubscribe-Post'], 'List-Unsubscribe=One-Click');
  const sent = env.DB.raw.prepare('SELECT notice_id FROM sent_matches WHERE subscriber_id=? ORDER BY notice_id').all(id).map(r => r.notice_id);
  eq(sent, ['A1', 'A2', 'A3', 'A9']);
  const run = env.DB.raw.prepare('SELECT * FROM runs').get();
  eq([run.requests_used, run.notices_seen, run.set_asides_kept, run.error], [3, 2510, 9, null]);
});
await t('same bid is never sent twice; budget counts across runs', async () => {
  const env = freshEnv();
  await addSub(env);
  await runRadar(env, { now: TUE });
  emails = [];
  const s2 = await runRadar(env, { now: TUE });
  eq(emails.length, 0, 'no repeat email');
  eq(s2.requests_used, 3);
  const s3 = await runRadar(env, { now: TUE }); // 6 used, 2 left -> capped
  eq(s3.capped, true);
  const s4 = await runRadar(env, { now: TUE }); // 8 used -> refuses
  ok(s4.error.includes('budget'), s4.error);
  eq(samCalls.length, 3 + 3 + 2);
});
await t('dry run: builds the digest, sends nothing, marks nothing', async () => {
  const env = freshEnv();
  await addSub(env);
  const s = await runRadar(env, { now: TUE, dry: true });
  eq(emails.length, 0);
  eq(s.subscribers[0].sent, 'dry');
  ok(s.subscribers[0].preview.subject.startsWith('Radar · 4'));
  eq(env.DB.raw.prepare('SELECT COUNT(*) n FROM sent_matches').get().n, 0);
  eq(env.DB.raw.prepare('SELECT COUNT(*) n FROM runs').get().n, 1, 'dry run that spent SAM requests is still logged');
});
await t('fetch=0 re-uses stored bids and costs no SAM request', async () => {
  const env = freshEnv();
  await addSub(env);
  await runRadar(env, { now: TUE, dry: true });
  samCalls = [];
  const s = await runRadar(env, { now: TUE, dry: true, fetch: false });
  eq(samCalls.length, 0); eq(s.subscribers[0].matched, 4);
  ok(s.subscribers[0].preview.text.includes('Re-checked 9 stored set-asides'), 'reuse footer');
});
await t('zero matches on a weekday: no email', async () => {
  const env = freshEnv();
  await addSub(env, { ...PBM, email: 'none@example.com', naics: ['111110'] });
  await runRadar(env, { now: TUE });
  eq(emails.length, 0);
});
await t('zero matches on a Monday: short weekly check-in', async () => {
  const env = freshEnv();
  await addSub(env, { ...PBM, email: 'none@example.com', naics: ['111110'] });
  await runRadar(env, { now: MON });
  eq(emails.length, 1);
  ok(emails[0].body.subject.includes('weekly check-in'));
});
await t('no Resend key: run still logged, send = skip, nothing marked sent', async () => {
  const env = freshEnv({ RESEND_API_KEY: undefined });
  await addSub(env);
  const s = await runRadar(env, { now: TUE });
  eq(s.subscribers[0].sent, 'skip');
  eq(env.DB.raw.prepare('SELECT COUNT(*) n FROM sent_matches').get().n, 0);
});
await t('the SAM key never lands in runs, /runs, or /health', async () => {
  const env = freshEnv(); samFail = 500;
  await addSub(env);
  await runRadar(env, { now: TUE });
  const all = JSON.stringify(env.DB.raw.prepare('SELECT * FROM runs').all())
    + await (await admin(env, '/runs')).text()
    + await (await worker.fetch(new Request('https://radar.test/health'), env)).text();
  ok(!all.includes(KEY), 'key leaked');
});

// ---------------------------------------------------------------- HTTP surface
await t('admin routes refuse without / with the wrong token', async () => {
  const env = freshEnv();
  eq((await worker.fetch(new Request('https://radar.test/subscribers'), env)).status, 401);
  eq((await worker.fetch(new Request('https://radar.test/run', { method: 'POST', headers: { Authorization: 'Bearer nope' } }), env)).status, 401);
  eq((await worker.fetch(new Request('https://radar.test/runs'), freshEnv({ PHOENIX_AUTH: undefined }))).status, 401);
});
await t('subscriber upsert by email, bad input 400', async () => {
  const env = freshEnv();
  const id = await addSub(env);
  const r = await (await admin(env, '/subscribers', 'POST', { ...PBM, email: 'PBM@example.com', states: [] })).json();
  eq([r.id, r.updated], [id, true]);
  eq((await admin(env, '/subscribers', 'POST', { email: 'x' })).status, 400);
});
await t('preview returns matches for a stored day without spending SAM requests', async () => {
  const env = freshEnv();
  const id = await addSub(env);
  await runRadar(env, { now: TUE, dry: true });
  samCalls = [];
  const p = await (await admin(env, `/preview?subscriber=${id}&date=2026-09-28`)).json();
  eq(p.matched, 4); eq(samCalls.length, 0);
});
await t('unsubscribe: GET only asks, POST acts, bad token 404', async () => {
  const env = freshEnv();
  await addSub(env);
  const tok = env.DB.raw.prepare('SELECT unsub_token FROM subscribers').get().unsub_token;
  const g = await worker.fetch(new Request(`https://radar.test/unsub/${tok}`), env);
  ok((await g.text()).includes('Unsubscribe me'));
  eq(env.DB.raw.prepare('SELECT active FROM subscribers').get().active, 1, 'GET must not act');
  await worker.fetch(new Request(`https://radar.test/unsub/${tok}`, { method: 'POST' }), env);
  eq(env.DB.raw.prepare('SELECT active FROM subscribers').get().active, 0);
  eq((await worker.fetch(new Request('https://radar.test/unsub/nope'), env)).status, 404);
  eq((await worker.fetch(new Request('https://radar.test/unsub/%E0%A4%A'), env)).status, 404);
});
await t('scheduled() runs the radar via waitUntil', async () => {
  const env = freshEnv();
  await addSub(env);
  const pending = [];
  await worker.scheduled({}, env, { waitUntil: p => pending.push(p) });
  await Promise.all(pending);
  eq(env.DB.raw.prepare('SELECT COUNT(*) n FROM runs').get().n, 1);
});
await t('/health reports what is wired, no secrets', async () => {
  const h = await (await worker.fetch(new Request('https://radar.test/health'), freshEnv())).json();
  eq([h.db_bound, h.sam_key, h.transport, h.admin_auth], [true, 'set', 'resend', 'set']);
});

// ---------------------------------------------------------------- applications (public form)
const SITE = 'https://pbmconsultingservice.com';
const appEnv = (extra = {}) => freshEnv({ TURNSTILE_SECRET: 'ts-secret', TURNSTILE_HOSTNAMES: 'pbmconsultingservice.com', ADMIN_NOTIFY_EMAIL: 'boss@example.com, laurie@example.com', ...extra });
const APP = { name: 'Dana', business_name: 'Red Dirt Steel LLC', email: 'Dana@RedDirt.example', naics: '238120, 332312', certs: ['wosb', 'small'], states: 'ok, tx', mode: 'planning', turnstile_token: 'good' };
const post = (env, path, body, headers = {}) => worker.fetch(new Request('https://radar.test' + path, {
  method: 'POST', headers: { 'Content-Type': 'application/json', Origin: SITE, ...headers }, body: JSON.stringify(body),
}), env);
const codeFrom = () => { const m = emails.map(e => e.body.subject).join(' ').match(/code: (\d{6})/); return m && m[1]; };
const reviewLink = () => { const e = emails.find(x => x.body.subject.startsWith('New Radar application')); return e && e.body.text.match(/\/review\/([A-Za-z0-9_-]+)/)[1]; };
async function applyAndVerify(env, body = APP) {
  const r = await post(env, '/apply', body);
  const code = codeFrom();
  const v = await post(env, '/apply/verify', { email: body.email, code });
  return { r, v, code };
}

await t('apply: bot check + code email, then verify -> review + notices to reviewers and applicant', async () => {
  const env = appEnv();
  const r = await post(env, '/apply', APP);
  eq(r.status, 200);
  eq(r.headers.get('Access-Control-Allow-Origin'), SITE);
  const code = codeFrom();
  ok(/^\d{6}$/.test(code), 'code emailed');
  eq(emails[0].body.to, ['dana@reddirt.example']);
  ok(!emails[0].body.headers, 'no unsubscribe header on a code email');
  const row = env.DB.raw.prepare('SELECT * FROM applications').get();
  eq([row.status, row.naics, row.states, row.certs], ['email', '["238120","332312"]', '["OK","TX"]', '["wosb","small"]']);
  ok(row.code_hash && row.code_hash !== code, 'only the hash is stored');
  emails = [];
  const v = await post(env, '/apply/verify', { email: APP.email, code });
  eq(v.status, 200);
  eq(env.DB.raw.prepare('SELECT status FROM applications').get().status, 'review');
  const notice = emails.find(e => e.body.subject === 'New Radar application: Red Dirt Steel LLC');
  ok(notice, 'reviewer notice');
  eq(notice.body.to, ['boss@example.com', 'laurie@example.com']);
  ok(notice.body.text.includes('https://radar.test/review/'), 'review link');
  ok(emails.some(e => e.body.subject === 'We got your Set-Aside Radar application'), 'applicant confirmation');
});
await t('apply: bot check fails closed (bad token, wrong action, wrong host, no secret)', async () => {
  for (const [tok, extra] of [['bad', {}], ['wrong-action', {}], ['wrong-host', {}], ['good', { TURNSTILE_SECRET: undefined }], ['good', { TURNSTILE_HOSTNAMES: '' }]]) {
    const env = appEnv(extra);
    const r = await post(env, '/apply', { ...APP, turnstile_token: tok });
    eq(r.status, 403, `token ${tok}`);
    eq(env.DB.raw.prepare('SELECT COUNT(*) n FROM applications').get().n, 0);
    eq(emails.length, 0);
  }
});
await t('apply: validation messages a real person can act on', async () => {
  const env = appEnv();
  const bad = async (patch, needle) => {
    const r = await post(env, '/apply', { ...APP, ...patch });
    eq(r.status, 400);
    const body = await r.json();
    ok(body.errors.some(e => e.includes(needle)), `${needle} in ${JSON.stringify(body.errors)}`);
  };
  await bad({ email: 'nope' }, 'valid email');
  await bad({ business_name: '' }, 'business name');
  await bad({ naics: '', work_desc: '' }, 'kind of work');
  await bad({ naics: '23812x' }, '2 to 6 digits');
  await bad({ certs: [] }, 'certification');
  await bad({ certs: ['kernel'] }, 'certification');
  await bad({ states: '' }, 'Anywhere');
  await bad({ states: 'Oklahoma' }, '2-letter');
  eq(samCalls.length + emails.length, 0, 'nothing sent on invalid input');
});
await t('verify: wrong code 401, 5 tries then 429, expired 410', async () => {
  const env = appEnv();
  await post(env, '/apply', APP);
  eq((await post(env, '/apply/verify', { email: APP.email, code: '000000' })).status, 401);
  for (let i = 0; i < 4; i++) await post(env, '/apply/verify', { email: APP.email, code: '000000' });
  eq((await post(env, '/apply/verify', { email: APP.email, code: codeFrom() })).status, 429, 'locked even with the right code');
  const env2 = appEnv();
  await post(env2, '/apply', APP);
  env2.DB.raw.prepare("UPDATE applications SET code_expires_at = '2000-01-01T00:00:00Z'").run();
  eq((await post(env2, '/apply/verify', { email: APP.email, code: codeFrom() })).status, 410);
  eq((await post(env2, '/apply/verify', { email: 'nobody@x.example', code: '123456' })).status, 404);
});
await t('review link: GET only shows, POST approve -> subscriber + welcome email, link then dead', async () => {
  const env = appEnv();
  await applyAndVerify(env);
  const tok = reviewLink();
  const g = await worker.fetch(new Request(`https://radar.test/review/${tok}`), env);
  const page = await g.text();
  ok(page.includes('Red Dirt Steel LLC') && page.includes('Approve'), 'shows the application');
  eq(env.DB.raw.prepare('SELECT COUNT(*) n FROM subscribers').get().n, 0, 'GET must not act');
  emails = [];
  const p = await worker.fetch(new Request(`https://radar.test/review/${tok}`, { method: 'POST', body: new URLSearchParams({ action: 'approve' }) }), env);
  eq(p.status, 200);
  const sub = env.DB.raw.prepare('SELECT * FROM subscribers').get();
  eq([sub.email, sub.name, sub.mode, sub.active, sub.states], ['dana@reddirt.example', 'Red Dirt Steel LLC', 'planning', 1, '["OK","TX"]']);
  const welcome = emails.find(e => e.body.subject.startsWith("You're in"));
  ok(welcome && welcome.body.headers['List-Unsubscribe'].includes(sub.unsub_token), 'welcome with unsubscribe');
  eq(env.DB.raw.prepare('SELECT status, subscriber_id FROM applications').get().status, 'approved');
  eq((await worker.fetch(new Request(`https://radar.test/review/${tok}`), env)).status, 404, 'link is single-use');
});
await t('review link: decline sends the applicant nothing', async () => {
  const env = appEnv();
  await applyAndVerify(env);
  const tok = reviewLink();
  emails = [];
  await worker.fetch(new Request(`https://radar.test/review/${tok}`, { method: 'POST', body: new URLSearchParams({ action: 'reject' }) }), env);
  eq(env.DB.raw.prepare('SELECT status FROM applications').get().status, 'rejected');
  eq(emails.length, 0);
  eq(env.DB.raw.prepare('SELECT COUNT(*) n FROM subscribers').get().n, 0);
});
await t('work description only: no Approve button until a reviewer supplies NAICS via the admin API', async () => {
  const env = appEnv();
  await applyAndVerify(env, { ...APP, naics: '', work_desc: 'We erect structural steel for metal buildings' });
  const tok = reviewLink();
  const page = await (await worker.fetch(new Request(`https://radar.test/review/${tok}`), env)).text();
  ok(!page.includes('value="approve"') && page.includes('No NAICS codes yet'), 'no approve button');
  const id = env.DB.raw.prepare('SELECT id FROM applications').get().id;
  eq((await admin(env, `/applications/approve?id=${id}`, 'POST', {})).status, 400, 'refused without NAICS');
  const ok2 = await (await admin(env, `/applications/approve?id=${id}`, 'POST', { naics: ['238120'] })).json();
  ok(ok2.ok && ok2.subscriber_id, 'approved with NAICS supplied');
  eq(env.DB.raw.prepare('SELECT naics FROM subscribers').get().naics, '["238120"]');
});
await t('admin applications API needs the token; list works', async () => {
  const env = appEnv();
  await applyAndVerify(env);
  eq((await worker.fetch(new Request('https://radar.test/applications'), env)).status, 401);
  eq((await worker.fetch(new Request('https://radar.test/applications/approve?id=1', { method: 'POST' }), env)).status, 401);
  const list = await (await admin(env, '/applications?status=review')).json();
  eq(list.applications.length, 1);
  ok(!('code_hash' in list.applications[0]) && !('review_token' in list.applications[0]), 'no secrets in the list');
});
await t('applying again while in review does not create a second application', async () => {
  const env = appEnv();
  await applyAndVerify(env);
  emails = [];
  const r = await (await post(env, '/apply', APP)).json();
  ok(r.ok && r.already);
  eq(env.DB.raw.prepare('SELECT COUNT(*) n FROM applications').get().n, 1);
  eq(emails.length, 0);
});
await t('CORS preflight allows only the PBM site', async () => {
  const r = await worker.fetch(new Request('https://radar.test/apply', { method: 'OPTIONS', headers: { Origin: 'https://evil.example' } }), appEnv());
  eq(r.headers.get('Access-Control-Allow-Origin'), SITE);
  eq(r.headers.get('Access-Control-Allow-Methods'), 'POST, OPTIONS');
});

// ---------------------------------------------------------------- billing (Stripe)
const WHSEC = 'whsec_test_secret';
const LINK = 'https://buy.stripe.com/test_abc123';
const billEnv = (extra = {}) => freshEnv({ STRIPE_PAYMENT_LINK: LINK, STRIPE_WEBHOOK_SECRET: WHSEC, ...extra });
async function stripeSig(body, t = Math.floor(Date.now() / 1000), secret = WHSEC) {
  const key = await crypto.subtle.importKey('raw', new TextEncoder().encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  const mac = new Uint8Array(await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(`${t}.${body}`)));
  return `t=${t},v1=${Array.from(mac).map(b => b.toString(16).padStart(2, '0')).join('')}`;
}
async function hook(env, ev, sig) {
  const body = JSON.stringify(ev);
  return worker.fetch(new Request('https://radar.test/stripe/webhook', { method: 'POST', headers: { 'Stripe-Signature': sig || await stripeSig(body) }, body }), env);
}
const billingOf = (env, id) => env.DB.raw.prepare('SELECT * FROM billing WHERE subscriber_id = ?').get(id);

await t('ask-to-pay: admin only, emails the link with the subscriber prefilled, marks asked', async () => {
  const env = billEnv();
  const id = await addSub(env);
  eq((await worker.fetch(new Request(`https://radar.test/subscribers/ask-to-pay?id=${id}`, { method: 'POST' }), env)).status, 401);
  emails = [];
  const r = await (await admin(env, `/subscribers/ask-to-pay?id=${id}`, 'POST')).json();
  ok(r.ok, JSON.stringify(r));
  eq(emails.length, 1);
  const txt = emails[0].body.text;
  ok(txt.includes(`${LINK}?client_reference_id=radar-${id}&prefilled_email=`), 'pay link with reference');
  ok(txt.includes('/unsub/'), 'way out included');
  eq(billingOf(env, id).status, 'asked');
  const list = await (await admin(env, '/subscribers')).json();
  eq(list.subscribers[0].billing, 'asked');
});
await t('ask-to-pay refuses with no payment link configured', async () => {
  const env = freshEnv();
  const id = await addSub(env);
  emails = [];
  eq((await admin(env, `/subscribers/ask-to-pay?id=${id}`, 'POST')).status, 503);
  eq(emails.length, 0);
});
await t('webhook: checkout completed -> active; updated/deleted follow; retries apply once', async () => {
  const env = billEnv();
  const id = await addSub(env);
  const done = { id: 'evt_1', type: 'checkout.session.completed', data: { object: { client_reference_id: `radar-${id}`, payment_status: 'paid', customer: 'cus_1', subscription: 'sub_1' } } };
  const r = await (await hook(env, done)).json();
  ok(r.ok && r.matched, JSON.stringify(r));
  eq(billingOf(env, id).status, 'active');
  eq(billingOf(env, id).stripe_subscription, 'sub_1');
  eq((await (await hook(env, done)).json()).duplicate, true);
  await hook(env, { id: 'evt_2', type: 'customer.subscription.updated', data: { object: { id: 'sub_1', status: 'past_due' } } });
  eq(billingOf(env, id).status, 'past_due');
  await hook(env, { id: 'evt_3', type: 'customer.subscription.deleted', data: { object: { id: 'sub_1', status: 'canceled' } } });
  eq(billingOf(env, id).status, 'canceled');
  eq(billingOf(env, id).stripe_customer, 'cus_1', 'customer kept');
});
await t('webhook: falls back to email when there is no reference', async () => {
  const env = billEnv();
  const id = await addSub(env);
  const email = env.DB.raw.prepare('SELECT email FROM subscribers WHERE id = ?').get(id).email;
  await hook(env, { id: 'evt_9', type: 'checkout.session.completed', data: { object: { payment_status: 'paid', customer_details: { email: email.toUpperCase() }, subscription: 'sub_9' } } });
  eq(billingOf(env, id).status, 'active');
});
await t('webhook: bad, stale, missing signature or no secret -> 400, nothing recorded', async () => {
  const env = billEnv();
  const id = await addSub(env);
  const ev = { id: 'evt_x', type: 'checkout.session.completed', data: { object: { client_reference_id: `radar-${id}`, payment_status: 'paid', subscription: 'sub_x' } } };
  const body = JSON.stringify(ev);
  eq((await hook(env, ev, await stripeSig(body, undefined, 'whsec_wrong'))).status, 400);
  eq((await hook(env, ev, await stripeSig(body, Math.floor(Date.now() / 1000) - 3600))).status, 400);
  eq((await worker.fetch(new Request('https://radar.test/stripe/webhook', { method: 'POST', body }), env)).status, 400);
  eq((await hook(freshEnv(), ev)).status, 400);
  eq(billingOf(env, id), undefined);
  eq(env.DB.raw.prepare('SELECT COUNT(*) n FROM stripe_events').get().n, 0);
});
await t('ask-to-pay never downgrades someone already paying', async () => {
  const env = billEnv();
  const id = await addSub(env);
  await hook(env, { id: 'evt_p', type: 'checkout.session.completed', data: { object: { client_reference_id: `radar-${id}`, payment_status: 'paid', subscription: 'sub_p' } } });
  await admin(env, `/subscribers/ask-to-pay?id=${id}`, 'POST');
  eq(billingOf(env, id).status, 'active');
});
await t('health reports stripe link mode + webhook without values', async () => {
  const h = await (await worker.fetch(new Request('https://radar.test/health'), billEnv())).json();
  eq(h.stripe_payment_link, 'test');
  eq(h.stripe_webhook, 'set');
  ok(!JSON.stringify(h).includes(WHSEC));
});

console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
