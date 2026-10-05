// index.mjs — sacrifice-worker: the Sacrifice game state API
// Phoenix DevOps OS | jwl247 | GPL v3
//
// The Godot client and the public read here; Frank writes here. Nothing else.
//
//   GET  /health                       liveness + history length
//   GET  /history?since=&type=&theater=&limit=   the permanent record (public, GDD §11.2)
//   GET  /named-ground?theater=        active named ground (public)
//   GET  /territory?theater=           AO boundaries + control (public)
//   GET  /tiles/{z}/{x}/{y}.png        map tiles, proxied — the MapTiler key
//                                      never reaches a client, and the tile
//                                      vendor can change without a client update
//   POST /history                      Frank only (Bearer FRANK_TOKEN): append
//                                      chained rows; every hash and link is
//                                      re-checked here, then again by D1 triggers
//
// Bindings: DB (D1 sacrifice_world). Secrets: FRANK_TOKEN, MAPTILER_API_KEY.
// Vars: MAPTILER_MAP (default outdoor-v2).

import { sha3_512 } from './sha3.mjs';

export const VERSION = '1.0.1';
const GENESIS = '0'.repeat(128);
const MAX_BODY = 1 << 20;          // 1 MiB per POST
const MAX_ROWS = 500;
const HEX128 = /^[0-9a-f]{128}$/;

const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Authorization, Content-Type',
};

const json = (body, status = 200, extra = {}) => new Response(JSON.stringify(body), {
  status, headers: { 'Content-Type': 'application/json', ...CORS, ...extra },
});
const err = (msg, status) => json({ error: msg }, status);

export default {
  async fetch(req, env, ctx) {
    try {
      return await route(req, env, ctx);
    } catch (e) {
      console.error('sacrifice-worker:', e && e.stack || e);
      return err('internal error', 500);
    }
  },
};

export async function route(req, env, ctx) {
  const url = new URL(req.url);
  const path = url.pathname.replace(/\/+$/, '') || '/';
  if (req.method === 'OPTIONS') return new Response(null, { status: 204, headers: CORS });

  if ((path === '/' || path === '/health') && req.method === 'GET') {
    const r = await env.DB.prepare('SELECT COALESCE(MAX(seq), 0) AS n FROM world_history').first();
    return json({ ok: true, worker: 'sacrifice-worker', version: VERSION, history: r.n });
  }
  if (path === '/history') {
    if (req.method === 'POST') return postHistory(req, env);
    if (req.method === 'GET') return getHistory(url, env);
  }
  if (path === '/named-ground' && req.method === 'GET') return getNamedGround(url, env);
  if (path === '/territory' && req.method === 'GET') return getTerritory(url, env);
  const t = path.match(/^\/tiles\/(\d{1,2})\/(\d{1,7})\/(\d{1,7})\.png$/);
  if (t && req.method === 'GET') return tile(+t[1], +t[2], +t[3], env, ctx, url);
  return err('not found', 404);
}

// ── auth ────────────────────────────────────────────────────────────────────

function timingSafeEqual(a, b) {
  const ea = new TextEncoder().encode(a), eb = new TextEncoder().encode(b);
  let diff = ea.length ^ eb.length;
  for (let i = 0; i < Math.max(ea.length, eb.length); i++) diff |= (ea[i] || 0) ^ (eb[i] || 0);
  return diff === 0;
}

export function isFrank(req, env) {
  const token = env.FRANK_TOKEN || '';
  if (token.length < 32) return false;                       // unset or weak = nobody writes
  const h = req.headers.get('Authorization') || '';
  return h.startsWith('Bearer ') && timingSafeEqual(h.slice(7), token);
}

// ── POST /history ───────────────────────────────────────────────────────────

export async function postHistory(req, env) {
  if (!isFrank(req, env)) return err('unauthorized', 401);
  const len = Number(req.headers.get('Content-Length') || 0);
  if (len > MAX_BODY) return err('body too large', 413);
  const text = await req.text();
  if (text.length > MAX_BODY) return err('body too large', 413);
  let entries;
  try { ({ entries } = JSON.parse(text)); } catch { return err('body is not JSON', 400); }
  if (!Array.isArray(entries) || entries.length === 0) return err('entries[] required', 400);
  if (entries.length > MAX_ROWS) return err(`at most ${MAX_ROWS} entries per request`, 400);

  const head = await env.DB.prepare(
    'SELECT seq, entry_hash FROM world_history ORDER BY seq DESC LIMIT 1').first();
  let seq = head ? head.seq : 0;
  let prev = head ? head.entry_hash : GENESIS;
  const stmts = [];

  for (const e of entries) {
    if (!e || !Number.isInteger(e.seq) || typeof e.canonical !== 'string' || !HEX128.test(e.entry_hash || ''))
      return err('each entry needs seq, canonical, entry_hash', 400);
    if (e.seq <= seq) {                                       // already have it: same bytes = ack
      const have = e.seq <= (head ? head.seq : 0)
        ? await env.DB.prepare('SELECT entry_hash FROM world_history WHERE seq = ?').bind(e.seq).first()
        : null;
      if (have && have.entry_hash === e.entry_hash) continue;
      return err(`entry ${e.seq} conflicts with the record`, 409);
    }
    if (e.seq !== seq + 1) return err(`entry ${e.seq} does not follow ${seq}`, 409);
    if (sha3_512(e.canonical) !== e.entry_hash) return err(`entry ${e.seq}: hash does not match its bytes`, 422);
    let body;
    try { body = JSON.parse(e.canonical); } catch { return err(`entry ${e.seq}: canonical is not JSON`, 422); }
    if (body.seq !== e.seq) return err(`entry ${e.seq}: seq inside the bytes differs`, 422);
    if (body.prev_hash !== prev) return err(`entry ${e.seq}: does not chain to ${seq}`, 409);
    if (typeof body.type !== 'string' || !body.type) return err(`entry ${e.seq}: no type`, 422);

    stmts.push(env.DB.prepare(
      'INSERT INTO world_history (seq, entry_hash, prev_hash, type, theater, canonical) VALUES (?, ?, ?, ?, ?, ?)')
      .bind(e.seq, e.entry_hash, prev, body.type, body.theater ?? null, e.canonical));
    stmts.push(...project(env, body, e.seq));
    seq = e.seq;
    prev = e.entry_hash;
  }
  if (stmts.length) {
    try {
      await env.DB.batch(stmts);                             // one transaction — all or nothing
    } catch (e) {
      const m = String(e && e.message || e);
      const rule = m.match(/(append-only|chain broken|never renamed|is permanent|not undrawn)[^"]*/);
      if (rule) return err(`refused by the record: ${rule[0]}`, 409);
      throw e;
    }
  }
  return json({ accepted_through: seq });
}

// History rows → current-state tables (same transaction).
export function project(env, b, seq) {
  const out = [];
  if (b.type === 'named_ground') {
    out.push(env.DB.prepare(
      `INSERT INTO named_ground (ground_id, ao_id, theater, name, lon, lat, kind, player_id, callsign,
         battle_id, casualties, ts, seq) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`)
      .bind(b.ground_id, b.ao_id, b.theater, b.name, b.lon, b.lat, b.kind, b.player_id, b.callsign,
            b.battle_id, b.casualties, b.ts, seq));
    for (const old of b.replaced || []) {
      out.push(env.DB.prepare(
        'UPDATE named_ground SET superseded_by = ? WHERE ground_id = ? AND superseded_by IS NULL')
        .bind(b.ground_id, old));
    }
  } else if (b.type === 'territory' && b.ao_id) {
    out.push(env.DB.prepare(
      `INSERT INTO territory (ao_id, theater, name, polygon, control, controller_id, controller_callsign,
         held_since, contested_by, seq) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
       ON CONFLICT (ao_id) DO UPDATE SET control = excluded.control,
         controller_id = excluded.controller_id, controller_callsign = excluded.controller_callsign,
         held_since = excluded.held_since, contested_by = excluded.contested_by, seq = excluded.seq`)
      .bind(b.ao_id, b.theater, b.name, JSON.stringify(b.polygon || []), b.control,
            b.controller_id ?? null, b.controller_callsign ?? null, b.held_since ?? null,
            b.contested_by ?? null, seq));
  }
  return out;
}

// ── public reads ────────────────────────────────────────────────────────────

function intParam(url, name, dflt, max) {
  const v = Number.parseInt(url.searchParams.get(name) ?? '', 10);
  return Number.isFinite(v) && v >= 0 ? Math.min(v, max) : dflt;
}

export async function getHistory(url, env) {
  const since = intParam(url, 'since', 0, Number.MAX_SAFE_INTEGER);
  const limit = intParam(url, 'limit', 100, 500) || 100;
  const where = ['seq > ?'], args = [since];
  for (const k of ['type', 'theater']) {
    const v = url.searchParams.get(k);
    if (v) { where.push(`${k} = ?`); args.push(v); }
  }
  const { results } = await env.DB.prepare(
    `SELECT seq, entry_hash, canonical FROM world_history WHERE ${where.join(' AND ')} ORDER BY seq LIMIT ?`)
    .bind(...args, limit).all();
  const entries = results.map(r => ({ ...JSON.parse(r.canonical), entry_hash: r.entry_hash }));
  return json({ entries, next: entries.length ? entries[entries.length - 1].seq : since },
              200, { 'Cache-Control': 'public, max-age=5' });
}

export async function getNamedGround(url, env) {
  const theater = url.searchParams.get('theater');
  const q = theater
    ? env.DB.prepare('SELECT * FROM named_ground WHERE superseded_by IS NULL AND theater = ? ORDER BY ts').bind(theater)
    : env.DB.prepare('SELECT * FROM named_ground WHERE superseded_by IS NULL ORDER BY ts');
  const { results } = await q.all();
  return json({
    type: 'FeatureCollection',
    features: results.map(g => ({
      type: 'Feature', id: g.ground_id,
      geometry: { type: 'Point', coordinates: [g.lon, g.lat] },
      properties: { ...g, lon: undefined, lat: undefined, kind: 'named_ground', ground_kind: g.kind,
                    active: true },
    })),
  }, 200, { 'Cache-Control': 'public, max-age=30' });
}

export async function getTerritory(url, env) {
  const theater = url.searchParams.get('theater');
  const q = theater
    ? env.DB.prepare('SELECT * FROM territory WHERE theater = ? ORDER BY ao_id').bind(theater)
    : env.DB.prepare('SELECT * FROM territory ORDER BY ao_id');
  const { results } = await q.all();
  return json({
    type: 'FeatureCollection',
    features: results.map(a => ({
      type: 'Feature', id: a.ao_id,
      geometry: { type: 'Polygon', coordinates: [JSON.parse(a.polygon)] },
      properties: { ...a, polygon: undefined },
    })),
  }, 200, { 'Cache-Control': 'public, max-age=10' });
}

// ── tiles ───────────────────────────────────────────────────────────────────

export async function tile(z, x, y, env, ctx, url) {
  if (z > 20 || x >= 2 ** z || y >= 2 ** z) return err('no such tile', 404);
  const key = (env.MAPTILER_API_KEY || '').trim();
  if (!key) return err('map tiles are not configured', 503);
  const cache = globalThis.caches && caches.default;
  const cacheKey = new Request(`${url.origin}/tiles/${z}/${x}/${y}.png`);
  if (cache) {
    const hit = await cache.match(cacheKey);
    if (hit) return hit;
  }
  const map = env.MAPTILER_MAP || 'outdoor-v2';
  const upstream = await fetch(
    `https://api.maptiler.com/maps/${encodeURIComponent(map)}/256/${z}/${x}/${y}.png?key=${encodeURIComponent(key)}`,
    { headers: { 'User-Agent': 'phoenix-sacrifice-worker/1.0' } });
  if (!upstream.ok) {                       // status code only — never the upstream URL or body (key in URL)
    console.error(`tile upstream ${upstream.status} for ${z}/${x}/${y}`);
    return json({ error: 'tile source unavailable', upstream_status: upstream.status }, 502);
  }
  const res = new Response(upstream.body, {
    headers: { 'Content-Type': 'image/png', 'Cache-Control': 'public, max-age=604800', ...CORS },
  });
  if (cache && ctx) ctx.waitUntil(cache.put(cacheKey, res.clone()));
  return res;
}
