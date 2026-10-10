#!/usr/bin/env node
// atlas-tree.js — the Atlas as a tree: 8 sectors at the top, name + location only, expand to go down.
// Phoenix DevOps OS | jwl247 | GPL v3
//
// Built from the CODE on disk (git's tracked + untracked files, .gitignore honoured), sorted into
// sectors by atlas/sectors.json (the ONE source; most specific key wins). A file no rule covers is
// listed under UNMAPPED, so a new folder can never be invisible (audit A-03).
// One source, two views (Jerry 10/9): the Console shows this tree; the graph adds edges from code.
//
//   node atlas/atlas-tree.js build            # write atlas/atlas-tree.json, print counts
//   node atlas/atlas-tree.js show [S3[/path]] # one level only: the sectors, or one branch
//   node atlas/atlas-tree.js find <text>      # where is it: sector + path (max 25)
//   node atlas/atlas-tree.js near <path|name> # what it touches + what touches it, by sector (max 15 each)
//
// Edges come from the CODE only (Directive #1): Python imports, JS require/import, and any path or
// file name in a file that is another real file of the repo. .md never draws a line; ARCHIVE is
// left out (fossils are noise). A bare name only links when exactly one live file has that name.

const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const HERE = __dirname;
const REPO = path.resolve(HERE, '..', '..', '..');
const SECTORS = JSON.parse(fs.readFileSync(path.join(HERE, 'sectors.json'), 'utf8'));
const OUT = path.join(HERE, 'atlas-tree.json');
const UNMAPPED = 'UNMAPPED';

const esc = (s) => s.replace(/[.+?^${}()|[\]\\]/g, '\\$&');
const RULES = Object.entries(SECTORS.rules)
  .map(([key, sector]) => ({
    key, sector,
    re: new RegExp('^' + key.split('*').map(esc).join('.*') + (key.endsWith('/') || key.includes('*') ? '' : '$')),
  }))
  .sort((a, b) => b.key.length - a.key.length);          // most specific first

function sectorOf(p) {
  const hit = RULES.find((r) => r.re.test(p));
  return hit ? hit.sector : UNMAPPED;
}

function repoFiles() {
  const git = (args) => execFileSync('git', ['-C', REPO, ...args], { maxBuffer: 64 << 20 }).toString('utf8').split('\0').filter(Boolean);
  const tracked = git(['ls-files', '-z']);
  const untracked = git(['ls-files', '-z', '-o', '--exclude-standard']);
  return [...new Set([...tracked, ...untracked])].filter((p) => fs.existsSync(path.join(REPO, p))).sort();
}

// ── edges, read from the code ────────────────────────────────────────────────
const CODE_EXT = /\.(py|sh|ps1|psm1|js|mjs|cjs|ts|cs|c|h|json|toml|service|timer|conf|bat|cmd|xaml|html|yaml|yml)$/i;
const TOKEN = /[A-Za-z0-9_.\-\/\\]+\.(?:py|sh|ps1|psm1|js|mjs|cjs|ts|cs|c|h|json|toml|service|timer|conf|bat|cmd|xaml|html|css|yaml|yml)\b/g;
const PY_IMPORT = /^\s*(?:from\s+([A-Za-z_][\w.]*)\s+import|import\s+([A-Za-z_][\w.]*(?:\s*,\s*[A-Za-z_][\w.]*)*))/gm;
const NOT_A_SOURCE = new Set(['sector2/package-handler/atlas/sectors.json', 'sector2/package-handler/atlas/atlas-tree.json',
                              'sector2/package-handler/connections-seed.json']);

function edgesFor(files) {
  const live = files.filter((p) => !['ARCHIVE', UNMAPPED].includes(sectorOf(p)));
  const liveSet = new Set(live);
  const byName = new Map();
  for (const p of live) {
    const b = p.split('/').pop();
    byName.set(b, [...(byName.get(b) || []), p]);
  }
  const resolve = (tok, from) => {
    let t = tok.replace(/\\/g, '/').replace(/^(\.\.?\/)+/, '');
    if (liveSet.has(t)) return t;
    const rel = from.split('/').slice(0, -1).concat(t).join('/');          // relative to the file
    if (liveSet.has(rel)) return rel;
    for (const p of live) if (t.includes('/') && p.endsWith('/' + t)) return p;
    const hits = byName.get(t.split('/').pop()) || [];
    return hits.length === 1 && t.length >= 6 ? hits[0] : null;
  };
  const edges = new Set();
  for (const from of live) {
    if (!CODE_EXT.test(from) || NOT_A_SOURCE.has(from)) continue;
    let text;
    try { text = fs.readFileSync(path.join(REPO, from), 'utf8'); } catch { continue; }
    if (text.length > 2_000_000) continue;
    const add = (to, kind) => { if (to && to !== from) edges.add(`${from}\t${to}\t${kind}`); };
    for (const m of text.matchAll(TOKEN)) add(resolve(m[0], from), 'names');
    if (from.endsWith('.py')) {
      for (const m of text.matchAll(PY_IMPORT)) {
        for (const mod of (m[1] || m[2]).split(',')) {
          const parts = mod.trim().split('.');
          add(resolve(parts.join('/') + '.py', from) || resolve(parts[parts.length - 1] + '.py', from), 'imports');
        }
      }
    }
  }
  return [...edges].map((e) => e.split('\t'));
}

function build() {
  const order = [...Object.keys(SECTORS.sectors), UNMAPPED];
  const roots = new Map(order.map((id) => [id, { n: id === UNMAPPED ? 'UNMAPPED' : `${id} ${SECTORS.sectors[id]}`, id, k: new Map() }]));
  const all = repoFiles();
  for (const p of all) {
    let node = roots.get(sectorOf(p));
    const parts = p.split('/');
    parts.forEach((part, i) => {
      const loc = parts.slice(0, i + 1).join('/');
      if (!node.k.has(part)) node.k.set(part, i === parts.length - 1 ? { n: part, p: loc } : { n: part, p: loc + '/', k: new Map() });
      node = node.k.get(part);
    });
  }
  const plain = (node) => {
    const out = { n: node.n };
    if (node.id) out.id = node.id;
    if (node.p) out.p = node.p;
    if (node.k) out.k = [...node.k.values()].sort((a, b) => (!!b.k - !!a.k) || a.n.localeCompare(b.n)).map(plain);
    return out;
  };
  const files = (node) => (node.k ? node.k.reduce((s, c) => s + files(c), 0) : 1);
  const sectors = order.map((id) => plain(roots.get(id))).filter((s) => s.k.length || s.id !== UNMAPPED);
  const edges = edgesFor(all);
  const tree = { format: 'phoenix-atlas-tree/1', generated: new Date().toISOString(), source: 'sector2/package-handler/atlas/sectors.json', sectors, edges };
  fs.writeFileSync(OUT, JSON.stringify(tree));
  for (const s of sectors) console.log(`${s.n.padEnd(22)} ${String(files(s)).padStart(5)} files`);
  console.log(`${edges.length} edges from code -> ${path.relative(REPO, OUT)}`);
}

function near(q) {
  const tree = load();
  const t = q.replace(/\\/g, '/');
  const nodes = new Set(tree.edges.flatMap(([a, b]) => [a, b]));
  let exact = [...nodes].filter((p) => p === t || p.endsWith('/' + t));
  if (!exact.length) {                       // plain words: take the best-scoring file that has code links
    const best = findHits(q).filter(([, id, p]) => id !== 'ARCHIVE' && nodes.has(p));
    if (best.length) exact = [best[0][2]];
  }
  const target = exact.length === 1 ? exact[0] : null;
  if (!target) {
    console.log(exact.length ? `which one?\n  ${exact.join('\n  ')}` : `no code links found for "${q}" (try: find ${q})`);
    return;
  }
  const show = (label, list) => {
    console.log(`${label} (${list.length})`);
    const bySector = new Map();
    for (const [p, kind] of list) { const s = sectorOf(p); bySector.set(s, [...(bySector.get(s) || []), `${p}${kind === 'imports' ? '  [import]' : ''}`]); }
    let n = 0;
    for (const [s, ps] of [...bySector].sort()) for (const p of ps) { if (n++ < 15) console.log(`  ${s.padEnd(7)} ${p}`); }
    if (n > 15) console.log(`  ... ${n - 15} more`);
  };
  console.log(`${sectorOf(target)} ${target}`);
  show('touches', tree.edges.filter(([a]) => a === target).map(([, b, k]) => [b, k]));
  show('touched by', tree.edges.filter(([, b]) => b === target).map(([a, , k]) => [a, k]));
}

function load() {
  if (!fs.existsSync(OUT)) build();
  return JSON.parse(fs.readFileSync(OUT, 'utf8'));
}

function show(where) {
  const tree = load();
  if (!where) { for (const s of tree.sectors) console.log(`+ ${s.n}`); return; }
  const [id, ...rest] = where.replace(/\\/g, '/').split('/');
  let node = tree.sectors.find((s) => s.id.toLowerCase() === id.toLowerCase());
  for (const part of rest.filter(Boolean)) node = node && node.k && node.k.find((c) => c.n === part);
  if (!node) { console.error(`not found: ${where}`); process.exitCode = 1; return; }
  console.log(node.p || node.n);
  for (const c of node.k || []) console.log(`  ${c.k ? '+' : ' '} ${c.n}`);
}

// Plain words work ("buddy healer" finds phoenix_buddy.py): a path scores one point per word it contains,
// best first. A whole-phrase match still ranks above any word match.
function findHits(text) {
  const t = text.toLowerCase().trim();
  const words = t.split(/[\s_\-/.]+/).filter((w) => w.length >= 3);
  const hits = [];
  const walk = (node, id) => {
    if (node.p && !node.k) {
      const p = node.p.toLowerCase();
      const score = (p.includes(t) ? 100 : 0) + words.filter((w) => p.includes(w)).length;
      if (score) hits.push([score, id, node.p]);
    }
    for (const c of node.k || []) walk(c, id);
  };
  for (const s of load().sectors) walk(s, s.id);
  return hits.sort((a, b) => b[0] - a[0] || a[2].localeCompare(b[2]));
}

function find(text) {
  const hits = findHits(text).filter(([, id]) => id !== 'ARCHIVE').slice(0, 25);
  for (const [, id, p] of hits) console.log(`${id.padEnd(8)} ${p}`);
  if (!hits.length) console.log(`nothing matches "${text}"`);
}

const [verb, arg] = process.argv.slice(2);
if (verb === 'build') build();
else if (verb === 'show') show(arg);
else if (verb === 'find' && arg) find(arg);
else if (verb === 'near' && arg) near(arg);
else { console.error('usage: atlas-tree.js build | show [S3[/path]] | find <text> | near <path|name>'); process.exitCode = 1; }
