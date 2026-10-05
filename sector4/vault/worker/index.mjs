// index.mjs — phoenix-vault-worker: hands out the ENCRYPTED vault, nothing else
// Phoenix DevOps OS | jwl247 | GPL v3
//
//   GET /health                       liveness
//   GET /pull.py                      the standalone pull tool (public — it holds no secrets)
//   GET /vault/phoenix-vault.enc      the encrypted vault, only for Bearer <fetch token>
//
// The token is derived on the box from the vault passphrase (scrypt); this
// worker stores only sha256(token) as the secret FETCH_HASH. The file it serves
// is AES-256-GCM ciphertext sealed on the home PC — neither this worker, R2
// nor Cloudflare ever sees a readable secret.
//
// Binding: VAULT (R2 phoenix-vault — vault files only). Secret: FETCH_HASH.

export const VERSION = '1.0.0';
const OBJECT = 'phoenix-vault.enc';

const json = (body, status = 200) => new Response(JSON.stringify(body), {
  status, headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' },
});

async function sha256hex(text) {
  const d = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return [...new Uint8Array(d)].map(b => b.toString(16).padStart(2, '0')).join('');
}

function timingSafeEqual(a, b) {
  let diff = a.length ^ b.length;
  for (let i = 0; i < Math.max(a.length, b.length); i++) diff |= (a.charCodeAt(i) || 0) ^ (b.charCodeAt(i) || 0);
  return diff === 0;
}

export async function authorized(req, env) {
  const want = (env.FETCH_HASH || '').trim().toLowerCase();
  if (!/^[0-9a-f]{64}$/.test(want)) return false;           // not configured = nobody gets the vault
  const h = req.headers.get('Authorization') || '';
  if (!h.startsWith('Bearer ')) return false;
  const token = h.slice(7).trim();
  if (!/^[0-9a-f]{64}$/.test(token)) return false;
  return timingSafeEqual(await sha256hex(token), want);
}

export default {
  async fetch(req, env) {
    try {
      const path = new URL(req.url).pathname.replace(/\/+$/, '') || '/';
      if (req.method !== 'GET') return json({ error: 'method not allowed' }, 405);
      if (path === '/' || path === '/health') return json({ ok: true, worker: 'phoenix-vault-worker', version: VERSION });
      if (path === '/pull.py') {
        const obj = await env.VAULT.get('phoenix_vault.py');
        if (!obj) return json({ error: 'tool not uploaded yet' }, 404);
        return new Response(obj.body, { headers: { 'Content-Type': 'text/x-python; charset=utf-8', 'Cache-Control': 'no-store' } });
      }
      if (path === `/vault/${OBJECT}`) {
        if (!(await authorized(req, env))) return json({ error: 'unauthorized' }, 401);
        const obj = await env.VAULT.get(OBJECT);
        if (!obj) return json({ error: 'vault not pushed yet' }, 404);
        return new Response(obj.body, { headers: { 'Content-Type': 'application/octet-stream', 'Cache-Control': 'no-store' } });
      }
      return json({ error: 'not found' }, 404);
    } catch (e) {
      console.error('vault-worker:', e && e.stack || e);
      return json({ error: 'internal error' }, 500);
    }
  },
};
