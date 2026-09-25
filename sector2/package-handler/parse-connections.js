#!/usr/bin/env node
// parse-connections.js — Atlas backfill.
//
// Walks every CONNECTIONS.md in the repo (root index + the 5-section skeleton
// each sector/dir doc follows: What it is / Dependencies / Commands / Connects
// to-from / Known issues), turns it into `connections` table rows, and (if
// PHOENIX_WORKER_URL + PHOENIX_AUTH are set) POSTs them to packages-worker.
// Always also writes connections-seed.json next to this file so the parse can
// be reviewed or replayed without hitting the network.
//
// Usage: node parse-connections.js [--dry-run]

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const REPO_ROOT = path.resolve(__dirname, '..', '..');
const SKIP_DIRS = new Set(['archive', 'node_modules', '.git', '.wrangler', '.claude', 'clonepool', '.metadata']);
const DRY_RUN = process.argv.includes('--dry-run');

function findConnectionsFiles(dir, out = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.name.startsWith('.') && entry.name !== '.') {
      if (!SKIP_DIRS.has(entry.name)) {
        // allow dotfile dirs we didn't think to skip, but never descend into them here
      }
      continue;
    }
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

function hexFor(nodePath) {
  return crypto.createHash('sha256').update(nodePath).digest('hex').slice(0, 16);
}

function areaFor(relPath) {
  const first = relPath.split(/[\\/]/)[0];
  return first === '.' || first === '' ? 'root' : first;
}

function inferState(text) {
  const t = (text || '').toLowerCase();
  if (/\b(stale|dead|deprecated|retired|fossil|superseded|orphaned|dormant)\b/.test(t)) return 'grey';
  return 'white';
}

// Registry: path (normalized, relative to repo root) -> node
const nodes = new Map();

function normalizePath(p) {
  return p.replace(/\\/g, '/').replace(/^\.\//, '').replace(/\/$/, '');
}

function addNode({ relPath, name, description, keyFact, sourceFile, area }) {
  const norm = normalizePath(relPath);
  const hex = hexFor(norm);
  const existing = nodes.get(norm);
  if (existing) {
    // Merge — prefer the longer/richer description, keep first-seen key fact if new one absent.
    if (description && description.length > (existing.description || '').length) existing.description = description;
    if (keyFact && !existing.key_fact) existing.key_fact = keyFact;
    return existing;
  }
  const node = {
    hex,
    name: name || path.basename(norm) || norm,
    path: norm,
    area: area || areaFor(norm),
    description: description || '',
    key_fact: keyFact || null,
    source_file: normalizePath(path.relative(REPO_ROOT, sourceFile)),
    state: inferState(`${description} ${keyFact}`),
    links: new Set(),
  };
  nodes.set(norm, node);
  return node;
}

function link(aPath, bPath) {
  const a = nodes.get(normalizePath(aPath));
  const b = nodes.get(normalizePath(bPath));
  if (!a || !b || a === b) return;
  a.links.add(b.hex);
  b.links.add(a.hex);
}

// Resolve a loosely-written path token (from prose) against known nodes by
// exact match first, then longest-suffix match — CONNECTIONS.md prose is
// hand-written, not guaranteed to match a node's path byte-for-byte.
function resolveToken(token) {
  const norm = normalizePath(token);
  if (nodes.has(norm)) return norm;
  let best = null;
  for (const known of nodes.keys()) {
    if (known.endsWith(norm) || norm.endsWith(known)) {
      if (!best || known.length > best.length) best = known;
    }
  }
  return best;
}

// ── Pass 1: root index table ────────────────────────────────────────────────
function parseRootIndex(file) {
  const text = fs.readFileSync(file, 'utf8').replace(/\r\n/g, '\n');
  const lines = text.split('\n');
  for (const line of lines) {
    const m = line.match(/^\|\s*\[([^\]]+)\]\(([^)]+)\)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*$/);
    if (!m) continue;
    const [, label, linkTarget, whatItIs, keyFact] = m;
    const relPath = path.dirname(linkTarget) === '.' ? label : path.dirname(linkTarget);
    addNode({
      relPath: label,
      name: label,
      description: whatItIs,
      keyFact,
      sourceFile: file,
      area: label,
    });
  }
}

// ── Pass 2: per-dir CONNECTIONS.md (What it is / Connects to-from) ─────────
function parseDirDoc(file) {
  const text = fs.readFileSync(file, 'utf8').replace(/\r\n/g, '\n');
  const relDir = normalizePath(path.relative(REPO_ROOT, path.dirname(file)));
  const area = areaFor(relDir || path.basename(path.dirname(file)));

  const titleMatch = text.match(/^#\s+(.+)$/m);
  const title = titleMatch ? titleMatch[1] : area;

  const sections = {};
  const sectionRe = /^##\s+(.+)$/gm;
  let match;
  const marks = [];
  while ((match = sectionRe.exec(text))) marks.push({ heading: match[1].trim(), index: match.index, bodyStart: match.index + match[0].length });
  for (let i = 0; i < marks.length; i++) {
    const end = i + 1 < marks.length ? marks[i + 1].index : text.length;
    sections[marks[i].heading] = text.slice(marks[i].bodyStart, end).trim();
  }

  // The directory itself is a node. Its description is whatever prose comes
  // before the first bullet in "What it is" — if bullets start immediately
  // (no intro paragraph), fall back to the doc title instead of grabbing the
  // first bullet's text by accident.
  const whatItIsRaw = sections['What it is'] || '';
  const bulletStart = whatItIsRaw.search(/(^|\n)-\s/);
  const introText = (bulletStart >= 0 ? whatItIsRaw.slice(0, bulletStart) : whatItIsRaw).replace(/\n/g, ' ').trim();
  const dirNode = addNode({
    relPath: relDir || area,
    name: title.split('—')[0].trim() || area,
    description: introText || title,
    sourceFile: file,
    area,
  });

  // Bullets under "What it is": "- `path` — description" (path optionally backticked).
  const bulletRe = /^-\s+`?([^\s`]+\/[^\s`]*|[^\s`]+\.[a-zA-Z0-9]+)`?\s*[—-]\s*(.+)$/gm;
  let b;
  while ((b = bulletRe.exec(whatItIsRaw))) {
    const [, bulletPath, desc] = b;
    const resolvedPath = path.posix.normalize(path.posix.join(relDir, bulletPath)).startsWith(relDir)
      ? bulletPath.startsWith(relDir) ? bulletPath : `${relDir}/${bulletPath}`.replace(/\/{2,}/g, '/')
      : bulletPath;
    const child = addNode({
      relPath: resolvedPath,
      name: bulletPath,
      description: desc.trim(),
      sourceFile: file,
      area,
    });
    link(dirNode.path, child.path);
  }

  // "Connects to / connected from": link every path-looking token mentioned
  // on the same line, in order (A → B → C, or a plain sentence naming two).
  const connects = sections['Connects to / connected from'] || '';
  const lineTokenRe = /`([^`]+)`/g;
  for (const rawLine of connects.split('\n')) {
    const tokens = [];
    let t;
    while ((t = lineTokenRe.exec(rawLine))) tokens.push(t[1]);
    lineTokenRe.lastIndex = 0;
    const resolved = tokens.map(resolveToken).filter(Boolean);
    for (let i = 0; i < resolved.length - 1; i++) link(resolved[i], resolved[i + 1]);
    // Also tie every mentioned node back to this doc's own directory node.
    for (const r of resolved) link(dirNode.path, r);
  }
}

function main() {
  const files = findConnectionsFiles(REPO_ROOT);
  const rootIndex = files.find(f => path.dirname(f) === REPO_ROOT);
  const dirDocs = files.filter(f => f !== rootIndex);

  if (rootIndex) parseRootIndex(rootIndex);
  for (const f of dirDocs) parseDirDoc(f);

  const rows = [...nodes.values()].map(n => ({
    hex: n.hex,
    name: n.name,
    path: n.path,
    area: n.area,
    description: n.description,
    key_fact: n.key_fact,
    source_file: n.source_file,
    state: n.state,
    links: JSON.stringify([...n.links]),
  }));

  const seedPath = path.join(__dirname, 'connections-seed.json');
  fs.writeFileSync(seedPath, JSON.stringify(rows, null, 2));
  console.log(`Parsed ${files.length} CONNECTIONS.md files -> ${rows.length} nodes.`);
  console.log(`Seed written: ${seedPath}`);

  if (DRY_RUN) {
    console.log('--dry-run: not posting to worker.');
    return;
  }

  const workerUrl = process.env.PHOENIX_WORKER_URL;
  const auth = process.env.PHOENIX_AUTH;
  if (!workerUrl || !auth) {
    console.log('PHOENIX_WORKER_URL / PHOENIX_AUTH not set — skipping live upload. Seed file is ready to POST later.');
    return;
  }
  const cfId = process.env.CF_ACCESS_CLIENT_ID;
  const cfSecret = process.env.CF_ACCESS_CLIENT_SECRET;
  const headers = { 'Content-Type': 'application/json', Authorization: `Bearer ${auth}` };
  if (cfId) headers['CF-Access-Client-Id'] = cfId;
  if (cfSecret) headers['CF-Access-Client-Secret'] = cfSecret;

  (async () => {
    let ok = 0, fail = 0;
    for (const row of rows) {
      try {
        const res = await fetch(`${workerUrl}/connections`, {
          method: 'POST',
          headers,
          body: JSON.stringify(row),
        });
        // A real D1 POST never redirects — if Cloudflare Access intercepted this
        // (missing/wrong service-token headers), fetch silently follows the
        // redirect to its login page and hands back a 200 that means nothing.
        // Same false-success bug class fixed in intake.py on 2026-09-21 — don't
        // repeat it here. Treat a redirect or a non-JSON body as a real failure.
        const contentType = res.headers.get('content-type') || '';
        if (res.redirected || !contentType.includes('application/json')) {
          fail++;
          console.error(`FAIL ${row.path}: blocked upstream of the worker (redirected=${res.redirected}, content-type="${contentType}") — check CF_ACCESS_CLIENT_ID/SECRET`);
        } else if (res.ok) {
          ok++;
        } else {
          fail++;
          console.error(`FAIL ${row.path}: ${res.status}`);
        }
      } catch (e) {
        fail++;
        console.error(`FAIL ${row.path}: ${e.message}`);
      }
    }
    console.log(`Uploaded: ${ok} ok, ${fail} failed.`);
  })();
}

main();
