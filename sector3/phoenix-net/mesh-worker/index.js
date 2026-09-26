// phoenix-mesh-worker — the Phoenix Mesh switchboard.
// UnitedSys — United Systems | jwl247 | GPL-3.0
//
// Phoenix Mesh = our own ZeroTier-style network: WireGuard links run DIRECT
// between Phoenix machines; this worker only coordinates (Workers can't carry
// UDP, so it never relays). It keeps the family registry — name, owner,
// WireGuard PUBLIC key, mesh address, current endpoints — and the per-link
// health log. When two devices can't link directly, they fall back to the
// phoenix-net Cloudflare tunnel (see ../README.md).
//
// Auth:
//   admin  — Bearer MESH_ADMIN (its own secret, not PHOENIX_AUTH): enroll,
//            revoke, list, health log.
//   device — Bearer <device token> handed out ONCE at enroll; stored only as
//            SHA-256. Heartbeat, peers, names.
//
// Routes:
//   GET  /health                     no auth
//   POST /enroll    admin   {name, pubkey, owner_email, kind?, hub?, listen_port?} -> {device_id, mesh_ip, token}
//   POST /revoke    admin   {name}
//   GET  /devices   admin   all devices incl. revoked (no token hashes)
//   GET  /links     admin   ?since=ISO  recent link health
//   POST /heartbeat device  {endpoints?, links?} -> {self, peers, names}
//   GET  /peers     device  -> {self, peers, names}

const MESH_PREFIX = '10.47.0.';
const NAME_RE = /^[a-z][a-z0-9-]{1,30}$/;
const PUBKEY_RE = /^[A-Za-z0-9+/]{42}[AEIMQUYcgkosw048]=$/;   // 32-byte WireGuard key, base64
const MAX_ENDPOINTS = 8;
const MAX_LINKS = 32;

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), { status, headers: { 'content-type': 'application/json' } });
}
const err = (msg, status = 400) => json({ ok: false, error: msg }, status);

function timingSafeEqualStr(a, b) {
  const ea = new TextEncoder().encode(a), eb = new TextEncoder().encode(b);
  if (ea.length !== eb.length) return false;
  let d = 0;
  for (let i = 0; i < ea.length; i++) d |= ea[i] ^ eb[i];
  return d === 0;
}
function bearer(req) {
  return (req.headers.get('Authorization') || '').replace(/^Bearer\s+/i, '').trim();
}
function isAdmin(req, env) {
  const t = bearer(req), e = (env.MESH_ADMIN || '').trim();
  return !!t && !!e && timingSafeEqualStr(t, e);
}
async function sha256Hex(s) {
  const d = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s));
  return [...new Uint8Array(d)].map(b => b.toString(16).padStart(2, '0')).join('');
}
function newToken() {
  const b = new Uint8Array(32);
  crypto.getRandomValues(b);
  return [...b].map(x => x.toString(16).padStart(2, '0')).join('');
}
async function deviceFromToken(req, env) {
  const t = bearer(req);
  if (!t || t.length !== 64) return null;
  const h = await sha256Hex(t);
  return env.MESH_DB.prepare('SELECT * FROM mesh_devices WHERE token_hash = ? AND revoked_at IS NULL').bind(h).first();
}

// Endpoints a device says it can be reached on. Only plain IPs + ports;
// anything else is dropped (this list goes straight into peers' WireGuard configs).
function cleanEndpoints(list) {
  if (!Array.isArray(list)) return [];
  const out = [];
  for (const e of list.slice(0, MAX_ENDPOINTS)) {
    if (!e || typeof e !== 'object') continue;
    const addr = String(e.addr || '').trim();
    const port = Number(e.port);
    const v4 = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/.exec(addr);
    const isV4 = !!v4 && v4.slice(1).every(o => Number(o) <= 255);
    const isV6 = !isV4 && /^[0-9a-fA-F:]+$/.test(addr) && addr.includes(':') && addr.length <= 45;
    if (!(isV4 || isV6) || !Number.isInteger(port) || port < 1 || port > 65535) continue;
    const scope = ['lan', 'public', 'stun'].includes(e.scope) ? e.scope : 'lan';
    out.push({ addr, port, family: isV6 ? 6 : 4, scope });
  }
  return out;
}

function publicView(d) {
  let endpoints = [];
  try { endpoints = JSON.parse(d.endpoints || '[]'); } catch { endpoints = []; }
  return { name: d.name, pubkey: d.pubkey, mesh_ip: d.mesh_ip, kind: d.kind, hub: !!d.hub,
           listen_port: d.listen_port, endpoints, last_seen: d.last_seen };
}

async function namesAndPeers(self, env) {
  const rows = (await env.MESH_DB.prepare(
    'SELECT * FROM mesh_devices WHERE revoked_at IS NULL ORDER BY mesh_ip').all()).results || [];
  const peers = rows.filter(r => r.device_id !== self.device_id).map(publicView);
  const names = Object.fromEntries(rows.map(r => [`${r.name}.phx`, r.mesh_ip]));
  return { self: publicView(self), peers, names };
}

async function nextMeshIp(env) {
  const used = new Set(((await env.MESH_DB.prepare('SELECT mesh_ip FROM mesh_devices').all()).results || []).map(r => r.mesh_ip));
  for (let i = 1; i <= 254; i++) if (!used.has(MESH_PREFIX + i)) return MESH_PREFIX + i;
  return null;
}

async function handleEnroll(req, env) {
  if (!isAdmin(req, env)) return err('unauthorized', 401);
  let b; try { b = await req.json(); } catch { return err('body must be JSON'); }
  const name = String(b.name || '').toLowerCase();
  if (!NAME_RE.test(name)) return err('name: 2-31 chars, a-z 0-9 -, starts with a letter');
  if (!PUBKEY_RE.test(String(b.pubkey || ''))) return err('pubkey: not a WireGuard public key');
  const email = String(b.owner_email || '').trim().toLowerCase();
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) return err('owner_email required');
  const kind = b.kind === 'static' ? 'static' : 'agent';
  const port = Number.isInteger(b.listen_port) && b.listen_port > 0 && b.listen_port < 65536 ? b.listen_port : 51820;

  const clash = await env.MESH_DB.prepare('SELECT name, revoked_at FROM mesh_devices WHERE name = ? OR pubkey = ?')
    .bind(name, b.pubkey).first();
  if (clash) return err(clash.revoked_at ? `'${clash.name}' was revoked; enroll under a new name` : `'${clash.name}' already enrolled`, 409);

  const mesh_ip = await nextMeshIp(env);
  if (!mesh_ip) return err('mesh is full', 507);
  const token = newToken();
  const device_id = crypto.randomUUID();
  await env.MESH_DB.prepare(
    `INSERT INTO mesh_devices (device_id, name, owner_email, pubkey, mesh_ip, kind, hub, token_hash, listen_port)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`
  ).bind(device_id, name, email, b.pubkey, mesh_ip, kind, b.hub ? 1 : 0, await sha256Hex(token), port).run();
  return json({ ok: true, device_id, name, mesh_ip, token, note: 'token is shown once; store it on the device only' }, 201);
}

async function handleRevoke(req, env) {
  if (!isAdmin(req, env)) return err('unauthorized', 401);
  let b; try { b = await req.json(); } catch { return err('body must be JSON'); }
  const r = await env.MESH_DB.prepare(
    "UPDATE mesh_devices SET revoked_at = datetime('now') WHERE name = ? AND revoked_at IS NULL").bind(String(b.name || '')).run();
  const changed = r?.meta?.changes ?? 0;
  return changed ? json({ ok: true, revoked: b.name }) : err('no such active device', 404);
}

async function handleDevices(req, env) {
  if (!isAdmin(req, env)) return err('unauthorized', 401);
  const rows = (await env.MESH_DB.prepare('SELECT * FROM mesh_devices ORDER BY mesh_ip').all()).results || [];
  return json({ ok: true, devices: rows.map(r => ({ ...publicView(r), owner_email: r.owner_email, created_at: r.created_at, revoked_at: r.revoked_at })) });
}

async function handleLinks(req, env) {
  if (!isAdmin(req, env)) return err('unauthorized', 401);
  const since = new URL(req.url).searchParams.get('since') || '1970-01-01';
  const rows = (await env.MESH_DB.prepare(
    'SELECT * FROM mesh_link_health WHERE at >= ? ORDER BY at DESC LIMIT 1000').bind(since).all()).results || [];
  return json({ ok: true, links: rows });
}

async function handleHeartbeat(req, env) {
  const self = await deviceFromToken(req, env);
  if (!self) return err('unauthorized', 401);
  let b; try { b = await req.json(); } catch { b = {}; }
  const endpoints = cleanEndpoints(b.endpoints);
  await env.MESH_DB.prepare("UPDATE mesh_devices SET endpoints = ?, last_seen = datetime('now') WHERE device_id = ?")
    .bind(JSON.stringify(endpoints), self.device_id).run();
  if (Array.isArray(b.links)) {
    for (const l of b.links.slice(0, MAX_LINKS)) {
      if (!l || !NAME_RE.test(String(l.to || ''))) continue;
      const path = ['direct', 'fallback', 'down'].includes(l.path) ? l.path : 'down';
      // null/undefined stay null: Number(null) is 0, and "no handshake" must
      // not read as "handshake 0 seconds ago" (found live 2026-09-26)
      const num = v => (v === null || v === undefined || v === '' || !Number.isFinite(Number(v)) ? null : Number(v));
      await env.MESH_DB.prepare(
        `INSERT INTO mesh_link_health (from_device, to_device, path, handshake_age, rtt_ms, rx_bytes, tx_bytes, endpoint)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?)`
      ).bind(self.name, l.to, path, num(l.handshake_age), num(l.rtt_ms), num(l.rx_bytes), num(l.tx_bytes),
             l.endpoint ? String(l.endpoint).slice(0, 64) : null).run();
    }
  }
  const fresh = await env.MESH_DB.prepare('SELECT * FROM mesh_devices WHERE device_id = ?').bind(self.device_id).first();
  return json({ ok: true, ...(await namesAndPeers(fresh, env)) });
}

async function handlePeers(req, env) {
  const self = await deviceFromToken(req, env);
  if (!self) return err('unauthorized', 401);
  return json({ ok: true, ...(await namesAndPeers(self, env)) });
}

export default {
  async fetch(req, env) {
    const { pathname } = new URL(req.url);
    const m = req.method;
    try {
      if (pathname === '/health' && m === 'GET') return json({ ok: true, service: 'phoenix-mesh-worker', admin_configured: !!env.MESH_ADMIN });
      if (pathname === '/enroll' && m === 'POST') return await handleEnroll(req, env);
      if (pathname === '/revoke' && m === 'POST') return await handleRevoke(req, env);
      if (pathname === '/devices' && m === 'GET') return await handleDevices(req, env);
      if (pathname === '/links' && m === 'GET') return await handleLinks(req, env);
      if (pathname === '/heartbeat' && m === 'POST') return await handleHeartbeat(req, env);
      if (pathname === '/peers' && m === 'GET') return await handlePeers(req, env);
      return err('not found', 404);
    } catch (e) {
      return err('internal error', 500);
    }
  },
};
