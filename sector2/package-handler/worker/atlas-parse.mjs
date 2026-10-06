// atlas-parse.mjs — the ONE Atlas parser, shared by packages-worker (which
// rebuilds the graph by itself from the intaked bundle in R2) and
// parse-connections.js (local dry runs + building that bundle).
//
// Input: the bundle's `files` — [{ path, text }] for every CONNECTIONS.md in
// the repo, repo-relative POSIX paths, in walk order (order matters: the
// first doc to describe a node sets its state). No fs, no node:path — this
// runs in a Worker as-is.
//
// Output: `connections` rows (hex, name, path, area, description, key_fact,
// source_file, state, links) and the /meta/atlas session-bootstrap blob,
// both derived from the docs only — nothing hand-typed in code.

export const BUNDLE_FORMAT = 'phoenix-atlas-sources/1';
export const BUNDLE_NAME = 'atlas-sources.json';
// intake.sh keys a file by to_hex(basename) — the R2 key the bundle lands on.
export const BUNDLE_KEY = Array.from(new TextEncoder().encode(BUNDLE_NAME), (b) => b.toString(16).padStart(2, '0')).join('');

// ── POSIX path helpers (stand-ins for node:path's posix functions) ─────────
function normalizePath(p) {
  return p.replace(/\\/g, '/').replace(/^\.\//, '').replace(/\/$/, '');
}
function posixNormalize(p) {
  const abs = p.startsWith('/');
  const out = [];
  for (const seg of p.split('/')) {
    if (!seg || seg === '.') continue;
    if (seg === '..') { if (out.length && out[out.length - 1] !== '..') out.pop(); else if (!abs) out.push('..'); }
    else out.push(seg);
  }
  const s = (abs ? '/' : '') + out.join('/');
  return s || (abs ? '/' : '.');
}
function posixJoin(a, b) { return posixNormalize([a, b].filter(Boolean).join('/')); }
function posixDirname(p) {
  const i = p.lastIndexOf('/');
  if (i < 0) return '.';
  return i === 0 ? '/' : p.slice(0, i);
}
function basename(p) { return p.split('/').pop(); }

async function sha256Hex16(s) {
  const d = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s));
  return Array.from(new Uint8Array(d), (b) => b.toString(16).padStart(2, '0')).join('').slice(0, 16);
}

function areaFor(relPath) {
  const first = relPath.split(/[\\/]/)[0];
  return first === '.' || first === '' ? 'root' : first;
}

// A node is grey only when its OWN description says IT is out of service —
// the status word leads the description ("dormant (nothing runs it)",
// "Retired 2026-09-25 …") or is stated about it ("is retired", "— legacy").
// Before 2026-10-02 any of these words anywhere greyed the node, so
// packages-worker went grey for mentioning a "stale copy" of itself elsewhere.
const STATE_WORDS = '(?:stale|dead|deprecated|retired|fossil|superseded|orphaned|dormant|legacy)';
// "dormant …", "**retired** …", "a stale duplicate …" — up to two words may lead.
const GREY_LEAD = new RegExp(`^\\W*(?:\\*\\*)?(?:(?:a|an|the)\\s+)?(?:[\\w-]+\\s+){0,2}?${STATE_WORDS}\\b`, 'i');
// "… snapshot, superseded", "… is retired", "— legacy"
const GREY_SELF = new RegExp(`(?:\\b(?:is|are|now|was)|[—,-])\\s+(?:\\*\\*)?(?:a\\s+|an\\s+)?${STATE_WORDS}\\b`, 'i');
function inferState(text) {
  const t = String(text || '').trim();
  if (GREY_LEAD.test(t)) return 'grey';
  // Only the first sentence speaks about the node itself; later sentences
  // usually talk about neighbours ("… the sector3 copy is stale").
  const first = t.split(/(?<=[.!?])\s/)[0];
  return GREY_SELF.test(first) ? 'grey' : 'white';
}

function splitSections(text) {
  const sections = {};
  const sectionRe = /^##\s+(.+)$/gm;
  const marks = [];
  let m;
  while ((m = sectionRe.exec(text))) marks.push({ heading: m[1].trim(), index: m.index, bodyStart: m.index + m[0].length });
  for (let i = 0; i < marks.length; i++) {
    const end = i + 1 < marks.length ? marks[i + 1].index : text.length;
    sections[marks[i].heading] = text.slice(marks[i].bodyStart, end).trim();
  }
  return sections;
}

// ── Graph ──────────────────────────────────────────────────────────────────
export async function parseAtlas(files) {
  const nodes = new Map();           // normalized path -> node (links hold paths until the end)

  function addNode({ relPath, name, description, keyFact, sourceFile, area }) {
    const norm = normalizePath(relPath);
    const src = normalizePath(sourceFile);
    const existing = nodes.get(norm);
    if (existing) {
      // Prefer the longer/richer description; keep the first key fact; record
      // every doc that describes this node (CONN-F06). State stays the
      // first-seen one (root index's one-liner beats a dir doc's intro, CONN-F05).
      if (description && description.length > (existing.description || '').length) existing.description = description;
      if (keyFact && !existing.key_fact) existing.key_fact = keyFact;
      if (!existing.source_files.includes(src)) existing.source_files.push(src);
      return existing;
    }
    const node = {
      name: name || basename(norm) || norm,
      path: norm,
      area: area || areaFor(norm),
      description: description || '',
      key_fact: keyFact || null,
      source_files: [src],
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
    a.links.add(b.path);
    b.links.add(a.path);
  }

  // Loosely written prose path → known node: exact, then longest suffix match
  // at a path boundary ("b/c.js" may match "a/b/c.js", "oo.sh" not "foo.sh").
  function resolveOne(norm) {
    if (nodes.has(norm)) return norm;
    let best = null;
    for (const known of nodes.keys()) {
      if (known.endsWith(`/${norm}`) || norm.endsWith(`/${known}`)) {
        if (!best || known.length > best.length) best = known;
      }
    }
    return best;
  }
  // A file-level token walks up its directories until one resolves (CONN-F04).
  function resolveToken(token) {
    let norm = normalizePath(token.trim());
    while (norm) {
      const hit = resolveOne(norm);
      if (hit) return hit;
      const up = posixDirname(norm);
      if (up === norm || up === '.' || up === '/') break;
      norm = up;
    }
    return null;
  }

  // Pass 1: root index table — | [label](link) | what it is | key fact |
  function parseRootIndex(file) {
    for (const line of file.text.split('\n')) {
      const m = line.match(/^\|\s*\[([^\]]+)\]\(([^)]+)\)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*$/);
      if (!m) continue;
      const [, label, , whatItIs, keyFact] = m;
      addNode({ relPath: label, name: label, description: whatItIs, keyFact, sourceFile: file.path, area: label });
    }
  }

  // Pass 2: per-dir doc — "What it is" bullets + "Connects to / connected from".
  function parseDirDoc(file) {
    const text = file.text;
    const dir = posixDirname(file.path);
    const relDir = normalizePath(dir === '.' ? '' : dir);
    const area = areaFor(relDir || basename(dir));

    const titleMatch = text.match(/^#\s+(.+)$/m);
    const title = titleMatch ? titleMatch[1] : area;
    const sections = splitSections(text);

    // The directory node: prose before the first bullet in "What it is",
    // else the doc title (never the first bullet's text by accident).
    const whatItIsRaw = sections['What it is'] || '';
    const bulletStart = whatItIsRaw.search(/(^|\n)-\s/);
    const introText = (bulletStart >= 0 ? whatItIsRaw.slice(0, bulletStart) : whatItIsRaw).replace(/\n/g, ' ').trim();
    const dirNode = addNode({
      relPath: relDir || area,
      name: title.split('—')[0].trim() || area,
      description: introText || title,
      sourceFile: file.path,
      area,
    });

    // "- `path` — description"; also "- `a`/`b` — …" and "- `a`, `b` — …"
    // (each extra full path its own node; suffix-only extras skipped, CONN-F04).
    const PATHTOK = '[^\\s`]+\\/[^\\s`]*|[^\\s`]+\\.[a-zA-Z0-9]+';
    const bulletRe = new RegExp(`^-\\s+\`?(${PATHTOK})\`?((?:\\s*[,/]\\s*\`[^\`]+\`)*)\\s*[—-]\\s*(.+)$`, 'gm');
    const toRel = (bp) => (posixJoin(relDir, bp).startsWith(relDir)
      ? bp.startsWith(relDir) ? bp : `${relDir}/${bp}`.replace(/\/{2,}/g, '/')
      : bp);
    let b;
    while ((b = bulletRe.exec(whatItIsRaw))) {
      const [, bulletPath, extras, desc] = b;
      const extraPaths = [...(extras || '').matchAll(/`([^`]+)`/g)]
        .map((x) => x[1])
        .filter((x) => !x.startsWith('.') && new RegExp(`^(${PATHTOK})$`).test(x));
      for (const bp of [bulletPath, ...extraPaths]) {
        const child = addNode({ relPath: toRel(bp), name: bp, description: desc.trim(), sourceFile: file.path, area });
        link(dirNode.path, child.path);
      }
    }

    // Every path token on one line links in order (A → B → C), and each
    // back to this doc's own directory node.
    const connects = sections['Connects to / connected from'] || '';
    for (const rawLine of connects.split('\n')) {
      const tokens = [...rawLine.matchAll(/`([^`]+)`/g)].map((t) => t[1]);
      const resolved = tokens.map(resolveToken).filter(Boolean);
      for (let i = 0; i < resolved.length - 1; i++) link(resolved[i], resolved[i + 1]);
      for (const r of resolved) link(dirNode.path, r);
    }
  }

  const clean = files.map((f) => ({ path: normalizePath(f.path), text: String(f.text).replace(/\r\n/g, '\n') }));
  const rootIndex = clean.find((f) => f.path === 'CONNECTIONS.md');
  if (rootIndex) parseRootIndex(rootIndex);
  for (const f of clean) if (f !== rootIndex) parseDirDoc(f);

  const hexOf = new Map();
  for (const p of nodes.keys()) hexOf.set(p, await sha256Hex16(p));
  return [...nodes.values()].map((n) => ({
    hex: hexOf.get(n.path),
    name: n.name,
    path: n.path,
    area: n.area,
    description: n.description,
    key_fact: n.key_fact,
    source_file: n.source_files.join(', '),
    state: n.state,
    links: JSON.stringify([...n.links].map((p) => hexOf.get(p))),
  }));
}

// ── /meta/atlas blob ───────────────────────────────────────────────────────
// Markdown table rows under a heading → arrays of cells (header + separator dropped).
function tableRows(body) {
  const rows = [];
  let header = true;
  for (const line of (body || '').split('\n')) {
    if (!/^\|/.test(line.trim())) continue;
    if (/^\|[\s|:-]+\|?\s*$/.test(line.trim())) { header = false; continue; }
    if (header) continue;                          // the row above the --- separator
    rows.push(line.trim().replace(/^\||\|$/g, '').split('|').map((s) => s.trim()));
  }
  return rows;
}
function findSection(files, re) {
  for (const f of files) {
    const s = splitSections(String(f.text).replace(/\r\n/g, '\n'));
    for (const [h, body] of Object.entries(s)) if (re.test(h)) return body;
  }
  return '';
}
const dash = (v) => (v && v !== '—' && v !== '-' ? v : '');

export function buildAtlasBlob(files, rows, builtFrom = {}) {
  const trip_wires = findSection(files, /^Trip-wires\b/i)
    .split('\n').filter((l) => /^-\s+/.test(l)).map((l) => l.replace(/^-\s+/, '').trim());

  const nodes = {};
  for (const [name, ip, os, role] of tableRows(findSection(files, /^Phoenix mesh\b/i))) {
    if (name) nodes[name.replace(/`/g, '')] = { ip: dash(ip).replace(/`/g, ''), os: dash(os), role: dash(role) };
  }

  const frames = {};
  for (const [frame, status, next, blocked] of tableRows(findSection(files, /^(Session State|Frames)\b/i))) {
    if (frame) frames[frame] = { status: dash(status), next: dash(next), blocked_by: dash(blocked) };
  }

  const upgrade_log = tableRows(findSection(files, /^Atlas Upgrade Log\b/i))
    .map(([date, component, change, by]) => ({ date, component, change, by: by || '' }));

  const edges = rows.reduce((n, r) => n + JSON.parse(r.links || '[]').length, 0) / 2;
  return {
    generated: new Date().toISOString(),
    built_from: builtFrom,                       // { key, etag, uploaded, files } of the bundle
    canonical_source: 'sector2/package-handler/worker/index.js',
    trip_wires,
    nodes,
    frames,
    upgrade_log: upgrade_log.slice(-10),
    atlas_node_count: rows.length,
    atlas_edge_count: edges,
  };
}
