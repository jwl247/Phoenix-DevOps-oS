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

function hexFor(nodePath) {
  return crypto.createHash('sha256').update(nodePath).digest('hex').slice(0, 16);
}

function areaFor(relPath) {
  const first = relPath.split(/[\\/]/)[0];
  return first === '.' || first === '' ? 'root' : first;
}

// State comes from the node's OWN description only. The root index's key-fact
// column talks about sub-parts ("assuming it's dead" about grub/, "stale, dead
// duplicate" about a sub-dir), and scanning it flagged 5 live dirs grey
// (audit CONN-F05: sector1, sector3, bin, docs, phoenix-core).
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
    // Record every doc that describes this node, not just the first one seen
    // (a dir named in the root index AND in its own CONNECTIONS.md), CONN-F06.
    const src = normalizePath(path.relative(REPO_ROOT, sourceFile));
    if (!existing.source_files.includes(src)) existing.source_files.push(src);
    // State stays the first-seen one: for a top-level dir that is the root
    // index's one-line "What it is" cell; the dir doc's intro paragraph talks
    // about its children and would re-introduce CONN-F05's false greys.
    return existing;
  }
  const node = {
    hex,
    name: name || path.basename(norm) || norm,
    path: norm,
    area: area || areaFor(norm),
    description: description || '',
    key_fact: keyFact || null,
    source_files: [normalizePath(path.relative(REPO_ROOT, sourceFile))],
    state: inferState(description),
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
function resolveOne(norm) {
  if (nodes.has(norm)) return norm;
  let best = null;
  for (const known of nodes.keys()) {
    // Suffix matches only at a path boundary: "b/c.js" may match "a/b/c.js",
    // but "oo.sh" must not match "foo.sh".
    if (known.endsWith(`/${norm}`) || norm.endsWith(`/${known}`)) {
      if (!best || known.length > best.length) best = known;
    }
  }
  return best;
}
// A file-level token (`sector2/package-handler/intake.sh`, `scripts/usys.ps1`)
// usually has no node of its own; walk up its directories until one resolves
// (a/b/c.js -> a/b -> a). Before this, such tokens were dropped, which left
// scripts/bin/phoenix-core/docs/bootstrap with 0 edges (audit CONN-F04).
function resolveToken(token) {
  let norm = normalizePath(token.trim());
  while (norm) {
    const hit = resolveOne(norm);
    if (hit) return hit;
    const up = path.posix.dirname(norm);
    if (up === norm || up === '.' || up === '/') break;
    norm = up;
  }
  return null;
}

// ── Pass 1: root index table ────────────────────────────────────────────────
function parseRootIndex(file) {
  const text = fs.readFileSync(file, 'utf8').replace(/\r\n/g, '\n');
  const lines = text.split('\n');
  for (const line of lines) {
    const m = line.match(/^\|\s*\[([^\]]+)\]\(([^)]+)\)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*$/);
    if (!m) continue;
    const [, label, , whatItIs, keyFact] = m;
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

  // Bullets under "What it is": "- `path` — description" (path optionally
  // backticked). Also "- `a`/`b` — …" and "- `a`, `b` — …": each extra full
  // path becomes its own node with the same description; suffix-only extras
  // like `.spec` are skipped (tools/ lost these bullets entirely, CONN-F04).
  const PATHTOK = '[^\\s`]+\\/[^\\s`]*|[^\\s`]+\\.[a-zA-Z0-9]+';
  const bulletRe = new RegExp(`^-\\s+\`?(${PATHTOK})\`?((?:\\s*[,/]\\s*\`[^\`]+\`)*)\\s*[—-]\\s*(.+)$`, 'gm');
  const toRel = (bulletPath) => (path.posix.normalize(path.posix.join(relDir, bulletPath)).startsWith(relDir)
    ? bulletPath.startsWith(relDir) ? bulletPath : `${relDir}/${bulletPath}`.replace(/\/{2,}/g, '/')
    : bulletPath);
  let b;
  while ((b = bulletRe.exec(whatItIsRaw))) {
    const [, bulletPath, extras, desc] = b;
    const extraPaths = [...(extras || '').matchAll(/`([^`]+)`/g)]
      .map((x) => x[1])
      .filter((x) => !x.startsWith('.') && new RegExp(`^(${PATHTOK})$`).test(x));
    for (const bp of [bulletPath, ...extraPaths]) {
      const child = addNode({
        relPath: toRel(bp),
        name: bp,
        description: desc.trim(),
        sourceFile: file,
        area,
      });
      link(dirNode.path, child.path);
    }
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
    source_file: n.source_files.join(', '),
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

    // Reconcile: drop D1 nodes that no longer exist in any CONNECTIONS.md
    // (upsert alone never deletes, CONN-F09). Only after a fully clean run,
    // so a partial upload can never delete live rows. A 404 means the worker
    // build predates POST /connections/reconcile — warn, don't fail.
    if (fail === 0 && rows.length) {
      try {
        const res = await fetch(`${workerUrl}/connections/reconcile`, {
          method: 'POST',
          headers,
          redirect: 'manual',
          body: JSON.stringify({ keep: rows.map((r) => r.hex) }),
        });
        const contentType = res.headers.get('content-type') || '';
        if (res.status === 404) {
          console.warn('Reconcile skipped: worker has no /connections/reconcile yet (deploy packages-worker >= 3.5.0).');
        } else if (res.ok && contentType.includes('application/json')) {
          const data = await res.json();
          console.log(`Reconciled: ${data.deleted.length} stale node(s) removed${data.deleted.length ? ': ' + data.deleted.join(', ') : ''}.`);
        } else {
          console.error(`Reconcile FAILED: ${res.status} (content-type="${contentType}")`);
          process.exitCode = 1;
        }
      } catch (e) {
        console.error(`Reconcile FAILED: ${e.message}`);
        process.exitCode = 1;
      }
    } else if (fail) {
      console.warn('Reconcile skipped: upload had failures.');
      process.exitCode = 1;
    }
  })();
}

main();
