// test.mjs — phoenix-mesh-worker against a REAL SQLite database (node:sqlite),
// schema.sql applied as-is, so every SQL statement the worker sends is really
// executed. Run: node test.mjs
import { DatabaseSync } from 'node:sqlite';
import { readFileSync } from 'node:fs';
import { randomBytes } from 'node:crypto';
import worker from './index.js';

const sqlite = new DatabaseSync(':memory:');
sqlite.exec(readFileSync(new URL('./schema.sql', import.meta.url), 'utf8'));

// D1-shaped wrapper over node:sqlite
const MESH_DB = {
  prepare(sql) {
    let binds = [];
    const st = () => sqlite.prepare(sql);
    const api = {
      bind: (...a) => { binds = a.map(v => (v === undefined ? null : v)); return api; },
      async run() { const r = st().run(...binds); return { meta: { changes: Number(r.changes) } }; },
      async first() { return st().get(...binds) ?? null; },
      async all() { return { results: st().all(...binds) }; },
    };
    return api;
  },
};
const ADMIN = 'a'.repeat(64);
const env = { MESH_DB, MESH_ADMIN: ADMIN };

const call = async (method, path, { token, body } = {}) => {
  const headers = { 'content-type': 'application/json' };
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await worker.fetch(new Request(`https://mesh.test${path}`, { method, headers, body: body ? JSON.stringify(body) : undefined }), env);
  return { status: res.status, body: await res.json() };
};
const wgKey = () => randomBytes(32).toString('base64');

let pass = 0, fail = 0;
const t = async (name, fn) => {
  try { await fn(); pass++; console.log(`  ok  ${name}`); }
  catch (e) { fail++; console.log(`FAIL  ${name}\n      ${e.message}`); }
};
const eq = (a, b, m) => { if (JSON.stringify(a) !== JSON.stringify(b)) throw new Error(`${m}: got ${JSON.stringify(a)}, want ${JSON.stringify(b)}`); };

const keys = { precision: wgKey(), compaq: wgKey(), pbm3: wgKey(), phone: wgKey() };
const tokens = {};

await t('health needs no auth', async () => {
  const r = await call('GET', '/health');
  eq(r.status, 200, 'status'); eq(r.body.admin_configured, true, 'admin configured');
});

await t('enroll requires the admin secret', async () => {
  const r = await call('POST', '/enroll', { token: 'nope', body: { name: 'x', pubkey: wgKey(), owner_email: 'a@b.co' } });
  eq(r.status, 401, 'status');
});

await t('enroll hands out sequential mesh IPs and a one-time token', async () => {
  for (const [name, hub, kind] of [['precision', true, 'agent'], ['compaq', false, 'agent'], ['pbm3', false, 'agent'], ['phone', false, 'static']]) {
    const r = await call('POST', '/enroll', { token: ADMIN, body: { name, pubkey: keys[name], owner_email: 'jw.leftwich1@gmail.com', hub, kind } });
    eq(r.status, 201, `${name} status`);
    tokens[name] = r.body.token;
    if (!/^[0-9a-f]{64}$/.test(r.body.token)) throw new Error('token shape');
  }
  eq((await call('GET', '/devices', { token: ADMIN })).body.devices.map(d => d.mesh_ip),
     ['10.47.0.1', '10.47.0.2', '10.47.0.3', '10.47.0.4'], 'ips');
});

await t('token is stored hashed, never in the clear', async () => {
  const row = sqlite.prepare('SELECT token_hash FROM mesh_devices WHERE name = ?').get('compaq');
  if (row.token_hash === tokens.compaq || row.token_hash.length !== 64) throw new Error('token not hashed');
});

await t('bad input is refused: name, pubkey, duplicate', async () => {
  eq((await call('POST', '/enroll', { token: ADMIN, body: { name: 'Bad Name', pubkey: wgKey(), owner_email: 'a@b.co' } })).status, 400, 'name');
  eq((await call('POST', '/enroll', { token: ADMIN, body: { name: 'ok-name', pubkey: 'not-a-key', owner_email: 'a@b.co' } })).status, 400, 'pubkey');
  eq((await call('POST', '/enroll', { token: ADMIN, body: { name: 'compaq', pubkey: wgKey(), owner_email: 'a@b.co' } })).status, 409, 'dup name');
  eq((await call('POST', '/enroll', { token: ADMIN, body: { name: 'other', pubkey: keys.pbm3, owner_email: 'a@b.co' } })).status, 409, 'dup key');
});

await t('heartbeat stores only clean endpoints and returns peers + names', async () => {
  const r = await call('POST', '/heartbeat', { token: tokens.compaq, body: { endpoints: [
    { addr: '192.168.1.141', port: 51820, scope: 'lan' },
    { addr: '2605:59ca:531b:9008::1', port: 51820, scope: 'public' },
    { addr: 'evil.example.com', port: 51820 },            // hostname: dropped
    { addr: '192.168.1.141; rm -rf /', port: 1 },         // junk: dropped
    { addr: '10.0.0.1', port: 70000 },                    // bad port: dropped
  ] } });
  eq(r.status, 200, 'status');
  eq(r.body.self.endpoints.map(e => e.addr), ['192.168.1.141', '2605:59ca:531b:9008::1'], 'endpoints');
  eq(r.body.peers.map(p => p.name), ['precision', 'pbm3', 'phone'], 'peers exclude self');
  eq(r.body.names['compaq.phx'], '10.47.0.2', 'names');
  eq(r.body.peers.find(p => p.name === 'precision').hub, true, 'hub flag');
});

await t('peers never expose tokens, hashes or emails', async () => {
  const r = await call('GET', '/peers', { token: tokens.pbm3 });
  const s = JSON.stringify(r.body);
  for (const bad of ['token_hash', tokens.compaq, 'owner_email', 'jw.leftwich1']) if (s.includes(bad)) throw new Error(`leaked ${bad}`);
});

await t('link health is recorded per link, ingress and egress', async () => {
  await call('POST', '/heartbeat', { token: tokens.precision, body: { links: [
    { to: 'compaq', path: 'direct', handshake_age: 12, rtt_ms: 1.8, rx_bytes: 5000, tx_bytes: 7000, endpoint: '192.168.1.141:51820' },
    { to: 'pbm3', path: 'fallback', handshake_age: null, rtt_ms: 40 },
    { to: 'Bad Name', path: 'direct' },                   // dropped
  ] } });
  const r = await call('GET', '/links', { token: ADMIN });
  eq(r.body.links.length, 2, 'two rows');
  const c = r.body.links.find(l => l.to_device === 'compaq');
  eq([c.path, c.rx_bytes, c.tx_bytes], ['direct', 5000, 7000], 'direct row');
});

await t('device token cannot use admin routes', async () => {
  eq((await call('GET', '/devices', { token: tokens.compaq })).status, 401, 'devices');
  eq((await call('POST', '/revoke', { token: tokens.compaq, body: { name: 'pbm3' } })).status, 401, 'revoke');
});

await t('revoke: the device is locked out and disappears from everyone', async () => {
  eq((await call('POST', '/revoke', { token: ADMIN, body: { name: 'pbm3' } })).status, 200, 'revoke');
  eq((await call('GET', '/peers', { token: tokens.pbm3 })).status, 401, 'revoked token refused');
  const r = await call('GET', '/peers', { token: tokens.compaq });
  eq(r.body.peers.map(p => p.name), ['precision', 'phone'], 'gone from peers');
  if ('pbm3.phx' in r.body.names) throw new Error('still in names');
  eq((await call('POST', '/enroll', { token: ADMIN, body: { name: 'pbm3', pubkey: wgKey(), owner_email: 'a@b.co' } })).status, 409, 'revoked name not reusable');
});

await t('unknown routes 404', async () => {
  eq((await call('GET', '/nope')).status, 404, 'status');
});

console.log(`\n${pass} passing, ${fail} failing`);
process.exit(fail ? 1 : 0);
