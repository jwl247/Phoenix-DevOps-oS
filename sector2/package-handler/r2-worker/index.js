// phoenix-clonepool-r2 — Phoenix DevOps OS
// A brand-new worker, never deployed before, deliberately separate from
// packages-worker (which is live and load-bearing — nothing here touches it).
//
// Purpose: the pull-down half of the clone pool. packages-worker's D1 rows
// record a pool_path and a hex, but nothing in the currently-deployed
// packages-worker actually reads/writes R2 bytes (checked: no R2 binding in
// its wrangler.jsonc, no PUT handler for the route intake.sh's
// upload_to_r2() has been calling all along). This worker is the other half
// — raw object storage against the R2 bucket that already exists
// (phoenix-clonepool, created 2026-06-22) — so a file can actually be
// fetched back down, not just looked up in the catalog.
//
// Routes:
//   GET  /object/:hex   -> raw bytes back from R2 (auth required)
//   PUT  /object/:hex   -> store raw bytes in R2 (auth required)
//   HEAD /object/:hex   -> exists + size, no body (auth required)
//   GET  /health        -> worker + bucket binding status

function isAuthorized(req, env) {
  const token = req.headers.get('Authorization')?.replace('Bearer ', '').trim();
  return token && token === (env.PHOENIX_AUTH || '').trim();
}

const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, PUT, HEAD, OPTIONS',
  'Access-Control-Allow-Headers': 'Authorization, Content-Type',
};

function err(message, status = 400) {
  return new Response(JSON.stringify({ status: 'error', message }), {
    status,
    headers: { 'Content-Type': 'application/json', ...CORS },
  });
}

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    const path = url.pathname.replace(/\/$/, '') || '/';

    if (req.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: CORS });
    }

    if (path === '/health') {
      return new Response(JSON.stringify({
        status: 'ok',
        worker: 'phoenix-clonepool-r2',
        bucket_bound: !!env.CLONEPOOL_BUCKET,
      }), { headers: { 'Content-Type': 'application/json', ...CORS } });
    }

    if (path.startsWith('/object/')) {
      const hex = decodeURIComponent(path.slice('/object/'.length));
      if (!hex) return err('hex required', 400);
      if (!isAuthorized(req, env)) return err('unauthorized', 401);

      if (req.method === 'GET' || req.method === 'HEAD') {
        const obj = await env.CLONEPOOL_BUCKET.get(hex);
        if (!obj) return err('not found in R2 — this file may predate R2 upload being wired (2026-08-22), or was never uploaded', 404);
        const headers = new Headers(CORS);
        headers.set('Content-Length', String(obj.size));
        headers.set('Content-Type', 'application/octet-stream');
        if (obj.httpEtag) headers.set('ETag', obj.httpEtag);
        if (req.method === 'HEAD') return new Response(null, { headers });
        return new Response(obj.body, { headers });
      }

      if (req.method === 'PUT') {
        const body = await req.arrayBuffer();
        if (body.byteLength === 0) return err('empty body', 400);
        await env.CLONEPOOL_BUCKET.put(hex, body);
        return new Response(JSON.stringify({ status: 'ok', hex, size: body.byteLength }), {
          headers: { 'Content-Type': 'application/json', ...CORS },
        });
      }

      return err('method not allowed', 405);
    }

    return err('not found', 404);
  },
};
