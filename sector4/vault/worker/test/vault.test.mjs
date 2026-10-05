// vault.test.mjs — phoenix-vault-worker: only the right token gets the ciphertext
// Phoenix DevOps OS | jwl247 | GPL v3
//   node sector4/vault/worker/test/vault.test.mjs [token-hex hash-hex]

import worker from '../index.mjs';

let pass = 0, fail = 0;
const ok = (label, cond) => { if (cond) pass++; else { fail++; console.log('FAIL', label); } };
const sha = async (t) => [...new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(t)))]
  .map(b => b.toString(16).padStart(2, '0')).join('');

const TOKEN = process.argv[2] || 'ab'.repeat(32);
const HASH = process.argv[3] || await sha(TOKEN);
const store = new Map([
  ['phoenix-vault.enc', new Uint8Array([80, 72, 88, 86, 65, 85, 76, 84, 1, 2, 3])],
  ['phoenix_vault.py', new TextEncoder().encode('#!/usr/bin/env python3\n')],
]);
const bucket = { async get(k) { const v = store.get(k); return v ? { body: v } : null; } };
const env = { VAULT: bucket, FETCH_HASH: HASH };
const get = (path, token, e = env, method = 'GET') => worker.fetch(new Request(`https://v${path}`, {
  method, headers: token ? { Authorization: `Bearer ${token}` } : {} }), e);

ok('health', (await (await get('/health')).json()).ok === true);
ok('pull tool public', (await get('/pull.py')).status === 200);
ok('no token → 401', (await get('/vault/phoenix-vault.enc')).status === 401);
ok('wrong token → 401', (await get('/vault/phoenix-vault.enc', 'cd'.repeat(32))).status === 401);
ok('the hash itself is not a token', (await get('/vault/phoenix-vault.enc', HASH)).status === 401);
ok('junk token → 401', (await get('/vault/phoenix-vault.enc', 'not-hex')).status === 401);
const r = await get('/vault/phoenix-vault.enc', TOKEN);
const body = new Uint8Array(await r.arrayBuffer());
ok('right token → ciphertext', r.status === 200 && body[0] === 80 && r.headers.get('Cache-Control') === 'no-store');
ok('FETCH_HASH unset → nobody', (await get('/vault/phoenix-vault.enc', TOKEN, { VAULT: bucket })).status === 401);
ok('other objects not served', (await get('/vault/other.enc', TOKEN)).status === 404);
ok('POST refused', (await get('/vault/phoenix-vault.enc', TOKEN, env, 'POST')).status === 405);

console.log(`${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
