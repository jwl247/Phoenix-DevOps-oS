// worker.test.mjs — sacrifice-worker against real SQLite (what D1 runs)
// Phoenix DevOps OS | jwl247 | GPL v3
//
//   node game/worker/test/worker.test.mjs [fixture.json]
//
// The fixture (written by game/tests/test_phase5.py) is a chain made by the
// Python WorldHistory — proving the two languages agree on every hash.

import { DatabaseSync } from 'node:sqlite';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { route } from '../index.mjs';
import { sha3_512 } from '../sha3.mjs';

const here = dirname(fileURLToPath(import.meta.url));
let pass = 0, fail = 0;
const ok = (label, cond) => { if (cond) pass++; else { fail++; console.log('FAIL', label); } };

// ── a D1-shaped adapter over node:sqlite ──
class Stmt {
  constructor(db, sql) { this.db = db; this.sql = sql; this.args = []; }
  bind(...a) { this.args = a; return this; }
  async first() { return this.db.prepare(this.sql).get(...this.args) ?? null; }
  async all() { return { results: this.db.prepare(this.sql).all(...this.args) }; }
  async run() { return this._run(); }
  _run() { return this.db.prepare(this.sql).run(...this.args); }
}
class D1 {
  constructor() {
    this.db = new DatabaseSync(':memory:');
    this.db.exec(readFileSync(join(here, '..', 'schema.sql'), 'utf8'));
  }
  prepare(sql) { return new Stmt(this.db, sql); }
  async batch(stmts) {
    this.db.exec('BEGIN');
    try { const r = stmts.map(s => s._run()); this.db.exec('COMMIT'); return r; }
    catch (e) { this.db.exec('ROLLBACK'); throw e; }
  }
}

const TOKEN = 'f'.repeat(48);
const fresh = () => ({ DB: new D1(), FRANK_TOKEN: TOKEN, MAPTILER_API_KEY: 'test-key' });
const call = (env, method, path, body, auth = TOKEN) => route(new Request(`https://w${path}`, {
  method, body: body ? JSON.stringify(body) : undefined,
  headers: auth ? { Authorization: `Bearer ${auth}` } : {},
}), env, { waitUntil() {} });

// ── build a chain the way Python does ──
const canon = (o) => JSON.stringify(Object.keys(o).sort().reduce((a, k) => (a[k] = o[k], a), {}));
function chain(bodies, start = 0, prev = '0'.repeat(128)) {
  return bodies.map((b, i) => {
    const c = canon({ ...b, seq: start + i + 1, prev_hash: prev, recorded_ts: 1 });
    const h = sha3_512(c);
    prev = h;
    return { seq: start + i + 1, canonical: c, entry_hash: h };
  });
}
const AO = { type: 'territory', event: 'ao_defined', ao_id: 'AO-1', theater: 'Ardennes', name: 'Hill 400',
  control: 'neutral', polygon: [[5.9, 49.8], [6.1, 49.8], [6.1, 50.0], [5.9, 49.8]] };
const NG = (id, kind, replaced = []) => ({ type: 'named_ground', ground_id: id, ao_id: 'AO-1', theater: 'Ardennes',
  name: `Ground ${id}`, lon: 6.0, lat: 49.85, kind, player_id: 'p', callsign: 'Reaper', battle_id: `b-${id}`,
  casualties: 3, ts: 1, replaced });

// ── health, auth ──
{
  const env = fresh();
  const h = await (await call(env, 'GET', '/health')).json();
  ok('health', h.ok && h.history === 0);
  ok('no token → 401', (await call(env, 'POST', '/history', { entries: chain([AO]) }, null)).status === 401);
  ok('wrong token → 401', (await call(env, 'POST', '/history', { entries: chain([AO]) }, 'x'.repeat(48))).status === 401);
  const weak = { ...env, FRANK_TOKEN: 'short' };
  ok('weak server token → nobody writes', (await call(weak, 'POST', '/history', { entries: chain([AO]) }, 'short')).status === 401);
}

// ── append, idempotent re-send, projections ──
{
  const env = fresh();
  const rows = chain([AO, NG('g1', 'player_named')]);
  const r = await call(env, 'POST', '/history', { entries: rows });
  ok('append 2', r.status === 200 && (await r.json()).accepted_through === 2);
  const again = await call(env, 'POST', '/history', { entries: rows });
  ok('re-send same rows = ack', again.status === 200 && (await again.json()).accepted_through === 2);
  const terr = await (await call(env, 'GET', '/territory?theater=Ardennes')).json();
  ok('territory projected', terr.features.length === 1 && terr.features[0].properties.control === 'neutral');
  ok('polygon kept', terr.features[0].geometry.coordinates[0].length === 4);
  const held = chain([{ ...AO, event: 'taken', control: 'held', controller_id: 'p', polygon: undefined }], 2, rows[1].entry_hash);
  await call(env, 'POST', '/history', { entries: held });
  const t2 = await (await call(env, 'GET', '/territory')).json();
  ok('control updated, polygon survives', t2.features[0].properties.control === 'held'
     && t2.features[0].geometry.coordinates[0].length === 4);
  const hist = await (await call(env, 'GET', '/history?type=named_ground')).json();
  ok('history filter', hist.entries.length === 1 && hist.entries[0].ground_id === 'g1');
  const page = await (await call(env, 'GET', '/history?since=1&limit=1')).json();
  ok('history paging', page.entries.length === 1 && page.entries[0].seq === 2 && page.next === 2);
}

// ── the chain is enforced ──
{
  const env = fresh();
  const rows = chain([AO, NG('g1', 'player_named')]);
  ok('gap refused', (await call(env, 'POST', '/history', { entries: [rows[1]] })).status === 409);
  const tampered = { ...rows[0], canonical: rows[0].canonical.replace('Hill 400', 'Hill 401') };
  ok('altered bytes refused', (await call(env, 'POST', '/history', { entries: [tampered] })).status === 422);
  await call(env, 'POST', '/history', { entries: [rows[0]] });
  const fork = chain([NG('gX', 'player_named')], 1, 'a'.repeat(128));
  ok('fork (wrong prev) refused', (await call(env, 'POST', '/history', { entries: fork })).status === 409);
  const rewrite = chain([{ ...AO, name: 'Rewritten' }]);
  ok('rewriting seq 1 refused', (await call(env, 'POST', '/history', { entries: rewrite })).status === 409);
  let threw = '';
  try { env.DB.db.exec('UPDATE world_history SET type = \'x\''); } catch (e) { threw = e.message; }
  ok('DB refuses UPDATE', /append-only/.test(threw));
  threw = '';
  try { env.DB.db.exec('DELETE FROM world_history'); } catch (e) { threw = e.message; }
  ok('DB refuses DELETE', /append-only/.test(threw));
}

// ── named ground: player names superseded, officers never ──
{
  const env = fresh();
  const rows = chain([AO, NG('g1', 'player_named'), NG('o1', 'officer_fallen', ['g1'])]);
  ok('officer supersedes player name', (await call(env, 'POST', '/history', { entries: rows })).status === 200);
  const ng = await (await call(env, 'GET', '/named-ground?theater=Ardennes')).json();
  ok('only officer ground active', ng.features.length === 1 && ng.features[0].id === 'o1'
     && ng.features[0].properties.kind === 'named_ground' && ng.features[0].properties.ground_kind === 'officer_fallen');
  const bad = chain([NG('g2', 'player_named', ['o1'])], 3, rows[2].entry_hash);
  const refused = await call(env, 'POST', '/history', { entries: bad });
  ok('renaming an officer refused (whole batch rolls back)',
     refused.status === 409 && /never renamed/.test((await refused.json()).error));
  const h = await (await call(env, 'GET', '/health')).json();
  ok('rolled back — history still 3', h.history === 3);
}

// ── tiles ──
{
  const env = fresh();
  const realFetch = globalThis.fetch;
  let asked = '';
  globalThis.fetch = async (u) => { asked = String(u); return new Response(new Uint8Array([137, 80, 78, 71]), { status: 200 }); };
  const r = await call(env, 'GET', '/tiles/5/16/10.png', null, null);
  ok('tile proxied', r.status === 200 && r.headers.get('Content-Type') === 'image/png');
  ok('key added server-side', asked.includes('key=test-key') && asked.includes('/256/5/16/10.png'));
  ok('out-of-range tile 404', (await call(env, 'GET', '/tiles/2/9/0.png', null, null)).status === 404);
  globalThis.fetch = async () => new Response('denied key=test-key', { status: 403 });
  const bad = await call(env, 'GET', '/tiles/5/16/10.png', null, null);
  const badBody = await bad.text();
  ok('upstream failure hides the key, shows the status', bad.status === 502 && !badBody.includes('test-key')
     && JSON.parse(badBody).upstream_status === 403);
  globalThis.fetch = async (u) => { asked = String(u); return new Response(new Uint8Array([1]), { status: 200 }); };
  await call({ ...env, MAPTILER_API_KEY: '  test-key
' }, 'GET', '/tiles/5/16/10.png', null, null);
  ok('key trimmed', asked.includes('key=test-key&') || asked.endsWith('key=test-key'));
  ok('no key configured → 503', (await call({ ...env, MAPTILER_API_KEY: '' }, 'GET', '/tiles/1/0/0.png', null, null)).status === 503);
  globalThis.fetch = realFetch;
}

// ── cross-language: a chain written by Python's WorldHistory ──
if (process.argv[2]) {
  const fixture = JSON.parse(readFileSync(process.argv[2], 'utf8'));
  const env = fresh();
  const r = await call(env, 'POST', '/history', { entries: fixture.rows });
  const body = await r.json();
  ok(`python chain accepted (${fixture.rows.length} rows)`, r.status === 200 && body.accepted_through === fixture.rows.length);
  const ng = await (await call(env, 'GET', '/named-ground')).json();
  ok('python named ground projected', ng.features.length === fixture.active_grounds);
  const terr = await (await call(env, 'GET', '/territory')).json();
  ok('python territory projected', terr.features.length === fixture.aos);
}

console.log(`${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
