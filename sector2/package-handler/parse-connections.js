#!/usr/bin/env node
// parse-connections.js — feed the Atlas.
//
// Collects every CONNECTIONS.md in the repo (root index + one per sector/dir)
// into ONE bundle file, atlas-sources.json, and sends it through the import
// method (intake.sh): bytes in R2, version + custody in D1. packages-worker
// rebuilds the `connections` graph and /meta/atlas from that bundle by itself
// the moment it lands (and re-checks daily), so the Atlas the dashboard, the
// HUD and the atlas skill read is always built from what was last intaked.
//
// One bundle, not 13 intakes: intake keys a file by its basename, so 13 files
// all named CONNECTIONS.md would overwrite each other in R2.
//
// The parser itself lives in worker/atlas-parse.mjs — the same code the worker
// runs, so a local dry run shows exactly what the worker will build.
//
// Usage:
//   node parse-connections.js            bundle → intake → wait for the worker's rebuild
//   node parse-connections.js --dry-run  parse only: connections-seed.json + counts, no network
//   node parse-connections.js --rebuild  ask the worker to rebuild from what is already in R2
// Needs PHOENIX_WORKER_URL, PHOENIX_AUTH, CF_ACCESS_CLIENT_ID, CF_ACCESS_CLIENT_SECRET
// (and Git Bash on Windows — PHOENIX_BASH if it is not in the usual place).

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { spawnSync } = require('child_process');
const { pathToFileURL } = require('url');

const REPO_ROOT = path.resolve(__dirname, '..', '..');
const SKIP_DIRS = new Set(['archive', 'node_modules', '.git', '.wrangler', '.claude', 'clonepool', '.metadata']);
const DRY_RUN = process.argv.includes('--dry-run');
const REBUILD_ONLY = process.argv.includes('--rebuild');

function findConnectionsFiles(dir, out = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.name.startsWith('.')) continue;   // never descend into dot dirs/files
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (SKIP_DIRS.has(entry.name)) continue;
      findConnectionsFiles(full, out);
    } else if (entry.name === 'CONNECTIONS.md') {
      out.push(full);
    }
  }
  return out;
}

// Deterministic bytes: same docs → same bundle → intake sees a duplicate and
// nothing is re-uploaded. Line endings normalized so a CRLF checkout and an LF
// checkout produce the identical bundle. Walk order is kept (it matters to the
// parser: the first doc to describe a node sets its state).
function buildBundle(format) {
  const files = findConnectionsFiles(REPO_ROOT).map((f) => ({
    path: path.relative(REPO_ROOT, f).replace(/\\/g, '/'),
    text: fs.readFileSync(f, 'utf8').replace(/\r\n/g, '\n'),
  }));
  return { format, files };
}

function findBash() {
  const candidates = [
    process.env.PHOENIX_BASH,
    'C:\\Program Files\\Git\\bin\\bash.exe',
    'C:\\Program Files (x86)\\Git\\bin\\bash.exe',
    process.env.LOCALAPPDATA && path.join(process.env.LOCALAPPDATA, 'Programs', 'Git', 'bin', 'bash.exe'),
  ].filter(Boolean);
  if (process.platform !== 'win32') return 'bash';
  // Never System32\bash.exe — that is WSL, which Phoenix does not use.
  return candidates.find((c) => fs.existsSync(c)) || null;
}
const toBashPath = (p) => p.replace(/\\/g, '/').replace(/^([A-Za-z]):/, (_, d) => `/${d.toLowerCase()}`);

function workerHeaders() {
  const h = { Authorization: `Bearer ${process.env.PHOENIX_AUTH}` };
  if (process.env.CF_ACCESS_CLIENT_ID) h['CF-Access-Client-Id'] = process.env.CF_ACCESS_CLIENT_ID;
  if (process.env.CF_ACCESS_CLIENT_SECRET) h['CF-Access-Client-Secret'] = process.env.CF_ACCESS_CLIENT_SECRET;
  return h;
}

// A real worker answer is JSON and never a redirect — Cloudflare Access bounces
// a missing/wrong service token to its login page with a 200 that means nothing.
async function workerJson(route, init = {}) {
  const res = await fetch(`${process.env.PHOENIX_WORKER_URL}${route}`, {
    ...init, redirect: 'manual', headers: { ...workerHeaders(), ...(init.headers || {}) },
  });
  const ct = res.headers.get('content-type') || '';
  if (!ct.includes('application/json')) throw new Error(`${route}: ${res.status}, not JSON (content-type "${ct}") — check CF_ACCESS_CLIENT_ID/SECRET`);
  return { status: res.status, body: await res.json() };
}

async function rebuild() {
  const { status, body } = await workerJson('/connections/rebuild', { method: 'POST' });
  if (status !== 200 || !body.ok) throw new Error(`rebuild refused (${status}): ${body.error || body.reason || JSON.stringify(body)}`);
  return body;
}

async function main() {
  const atlas = await import(pathToFileURL(path.join(__dirname, 'worker', 'atlas-parse.mjs')).href);
  const bundle = buildBundle(atlas.BUNDLE_FORMAT);
  const rows = await atlas.parseAtlas(bundle.files);
  const edges = rows.reduce((n, r) => n + JSON.parse(r.links).length, 0) / 2;
  const grey = rows.filter((r) => r.state !== 'white').length;

  const seedPath = path.join(__dirname, 'connections-seed.json');
  fs.writeFileSync(seedPath, JSON.stringify(rows, null, 2));
  console.log(`Parsed ${bundle.files.length} CONNECTIONS.md files -> ${rows.length} nodes, ${edges} edges (${grey} grey).`);
  console.log(`Seed written: ${seedPath}`);
  if (DRY_RUN) { console.log('--dry-run: nothing sent.'); return; }

  for (const v of ['PHOENIX_WORKER_URL', 'PHOENIX_AUTH']) {
    if (!process.env[v]) { console.error(`${v} not set — cannot reach the worker.`); process.exitCode = 1; return; }
  }

  if (REBUILD_ONLY) {
    const r = await rebuild();
    console.log(`Worker rebuilt the Atlas from R2: ${r.nodes} nodes, ${r.edges} edges, ${r.deleted.length} removed.`);
    return;
  }

  const bytes = JSON.stringify(bundle, null, 1) + '\n';
  const bundlePath = path.join(__dirname, atlas.BUNDLE_NAME);
  fs.writeFileSync(bundlePath, bytes);
  const md5 = crypto.createHash('md5').update(bytes).digest('hex');   // = R2's etag for a single-PUT object
  console.log(`Bundle written: ${bundlePath} (${bytes.length} bytes, etag ${md5})`);

  const bash = findBash();
  if (!bash) { console.error('Git Bash not found — set PHOENIX_BASH.'); process.exitCode = 1; return; }
  const env = { ...process.env, INTAKE_YES: '1' };   // unattended: an unchanged bundle is kept, not re-versioned
  if (env.CLONEPOOL_DIR) env.CLONEPOOL_DIR = toBashPath(env.CLONEPOOL_DIR);
  const r = spawnSync(bash, [toBashPath(path.join(__dirname, 'intake.sh')), toBashPath(bundlePath), 'atlas', 'CONNECTIONS.md bundle'],
    { stdio: 'inherit', env, cwd: __dirname });
  if (r.status !== 0) { console.error(`intake.sh exited ${r.status}`); process.exitCode = 1; return; }

  // The worker rebuilds as soon as the bundle's bytes land in R2. Wait for its
  // /meta/atlas to name this exact bundle; if intake kept an identical earlier
  // copy (no upload, no trigger) and the graph is still behind, ask directly.
  const built = async () => {
    const { status, body } = await workerJson('/meta/atlas');
    return status === 200 && body.built_from && body.built_from.etag === md5 ? body : null;
  };
  for (let i = 0; i < 20; i++) {
    const b = await built();
    if (b) { console.log(`Atlas current: ${b.atlas_node_count} nodes, ${b.atlas_edge_count} edges, built ${b.generated}.`); return; }
    await new Promise((s) => setTimeout(s, 1500));
  }
  console.log('Worker has not rebuilt from this bundle yet — asking it to rebuild now.');
  const rb = await rebuild();
  if (rb.built_from.etag !== md5) {
    console.error(`Worker's R2 bundle (etag ${rb.built_from.etag}) is not this one (${md5}) — the intake upload did not reach R2.`);
    process.exitCode = 1;
    return;
  }
  console.log(`Atlas current: ${rb.nodes} nodes, ${rb.edges} edges.`);
}

main().catch((e) => { console.error(`FAILED: ${e.message}`); process.exitCode = 1; });
