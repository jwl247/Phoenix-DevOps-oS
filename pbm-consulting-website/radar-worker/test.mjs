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

console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
