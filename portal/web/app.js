// Phoenix Portal v0 — draws /api/state. No innerHTML with data: every name
// and number goes in through textContent / setAttribute.
'use strict';

const REFRESH_MS = 15000;
const NS = 'http://www.w3.org/2000/svg';
const W = 1000, H = 480, PW = 210, PH = 84;
let lastFetch = null;

const $ = id => document.getElementById(id);
function el(tag, attrs = {}, text) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (text !== undefined) e.textContent = text;
  return e;
}
function sv(tag, attrs = {}, text) {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (text !== undefined) e.textContent = text;
  return e;
}
const ms = v => (v === null || v === undefined ? '–' : `${v < 10 ? v.toFixed(1) : Math.round(v)} ms`);
function ago(s) {
  if (s === null || s === undefined) return 'never';
  if (s < 60) return `${s} s ago`;
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  return `${Math.round(s / 3600)} h ago`;
}
const PATH_WORD = { direct: 'Direct', fallback: 'Relayed', down: 'Down' };
const RANK = { direct: 0, fallback: 1, down: 2 };

// Hub on top, everyone else along the bottom: a relayed link then bows up
// through the hub instead of lying on top of the hub's own members.
function layout(machines) {
  const pos = {};
  const hub = machines.find(m => m.hub);
  const rest = machines.filter(m => m !== hub);
  if (hub) pos[hub.name] = { x: W / 2, y: 90 };
  rest.forEach((m, i) => {
    const x = rest.length === 1 ? W / 2 : 150 + i * ((W - 300) / (rest.length - 1));
    pos[m.name] = { x, y: hub ? 300 : H / 2 };
  });
  return { pos, hub };
}

// Two directions of one link -> one member, drawn at its worse side.
function members(links) {
  const by = {};
  for (const l of links) {
    const key = [l.from, l.to].sort().join('|');
    (by[key] = by[key] || []).push(l);
  }
  return Object.entries(by).map(([key, ls]) => {
    const [a, b] = key.split('|');
    const worst = ls.reduce((w, l) => (RANK[l.path] > RANK[w.path] ? l : w), ls[0]);
    const rtts = ls.map(l => l.rtt_ms).filter(v => v !== null);
    return { a, b, path: worst.path, relay: ls.some(l => l.relay),
             rtt: rtts.length ? rtts.reduce((s, v) => s + v, 0) / rtts.length : null };
  });
}

function drawPlan(state) {
  const svg = $('plan');
  svg.replaceChildren();
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  const { pos, hub } = layout(state.machines);
  const hubPos = hub && pos[hub.name];

  for (const m of members(state.links)) {
    const p = pos[m.a], q = pos[m.b];
    if (!p || !q) continue;
    const cls = m.path === 'down' ? 'm-down' : (m.relay || m.path === 'fallback') ? 'm-relay' : 'm-direct';
    let mid;
    if (cls === 'm-relay' && hubPos && m.a !== hub.name && m.b !== hub.name) {
      svg.append(sv('path', { d: `M${p.x},${p.y} Q${hubPos.x},${hubPos.y} ${q.x},${q.y}`, class: cls }));
      mid = { x: 0.25 * p.x + 0.5 * hubPos.x + 0.25 * q.x, y: 0.25 * p.y + 0.5 * hubPos.y + 0.25 * q.y };
    } else {
      svg.append(sv('line', { x1: p.x, y1: p.y, x2: q.x, y2: q.y, class: cls }));
      mid = { x: (p.x + q.x) / 2, y: (p.y + q.y) / 2 };
    }
    if (m.path === 'down') {                     // a break mark across the member
      svg.append(sv('path', { d: `M${mid.x - 14},${mid.y + 10} l10,-20 M${mid.x - 2},${mid.y + 10} l10,-20`, class: 'break' }));
    }
    const label = m.path === 'down' ? 'down' : `${ms(m.rtt)}${cls === 'm-relay' ? ' via hub' : ''}`;
    const w = label.length * 7.4 + 12;
    svg.append(sv('rect', { x: mid.x - w / 2, y: mid.y - 11, width: w, height: 20, class: 'dim-bg' }));
    svg.append(sv('text', { x: mid.x, y: mid.y + 4, 'text-anchor': 'middle', class: 'dim' }, label));
  }

  for (const m of state.machines) {
    const p = pos[m.name];
    const g = sv('g', { transform: `translate(${p.x - PW / 2},${p.y - PH / 2})` });
    g.append(sv('rect', { width: PW, height: PH, class: `plate${m.hub ? ' hub' : ''}${m.online ? '' : ' offline'}` }));
    g.append(sv('text', { x: 14, y: 28, class: 'plate-name' }, m.host));
    const sub = sv('text', { x: 14, y: 49, class: 'plate-sub' }, m.mesh_ip);
    if (m.lan.length) sub.append(sv('tspan', { dx: 14 }, `LAN ${m.lan[0]}`));   // SVG collapses spaces
    g.append(sub);
    const st = m.online ? `Online${m.hub ? ', the hub' : ''}` : `Offline, last seen ${ago(m.seen_s)}`;
    g.append(sv('text', { x: 14, y: 70, class: `plate-state${m.online ? '' : ' off'}` }, st));
    svg.append(g);
  }
}

function spark(series) {
  const s = sv('svg', { width: 90, height: 22, 'aria-hidden': 'true' });
  const pts = series.filter(v => v !== null);
  if (pts.length < 2) return s;
  const max = Math.max(...pts), min = Math.min(...pts), span = max - min || 1;
  const d = pts.map((v, i) => `${i ? 'L' : 'M'}${(i / (pts.length - 1)) * 88 + 1},${21 - ((v - min) / span) * 20}`).join(' ');
  s.append(sv('path', { d, class: 'spark' }));
  return s;
}

function drawLinks(links) {
  const body = $('links').tBodies[0];
  body.replaceChildren();
  for (const l of links) {
    const tr = el('tr');
    tr.append(el('td', {}, `${l.from} to ${l.to}`));
    tr.append(el('td', { class: `now-${l.path}` }, l.stale ? 'No recent report' : PATH_WORD[l.path]));
    const td = el('td');
    const bar = el('span', { class: 'bar', role: 'img',
      'aria-label': `${l.share.direct}% direct, ${l.share.fallback}% relayed, ${l.share.down}% down` });
    for (const p of ['direct', 'fallback', 'down']) if (l.share[p]) bar.append(el('span', { class: `b-${p}`, style: `width:${l.share[p]}%` }));
    td.append(bar);
    const words = [];
    if (l.share.direct) words.push(`${l.share.direct}% direct`);
    if (l.share.fallback) words.push(`${l.share.fallback}% relayed`);
    if (l.share.down) words.push(`${l.share.down}% down`);
    td.append(el('span', { class: `bar-label${l.share.down ? ' warn' : ''}` }, words.join(', ')));
    tr.append(td);
    tr.append(el('td', { class: `num${l.flips > 2 ? ' warn' : ''}` }, String(l.flips)));
    tr.append(el('td', { class: 'num' }, ms(l.rtt_avg)));
    tr.append(el('td', { class: 'num' }, ms(l.rtt_max)));
    const tdS = el('td'); tdS.append(spark(l.series)); tr.append(tdS);
    body.append(tr);
  }
  if (!links.length) {
    const tr = el('tr'); tr.append(el('td', { colspan: 7 }, 'No link reports in the last hour. Are the mesh agents running?'));
    body.append(tr);
  }
}

function drawServices(svcs) {
  const ul = $('services');
  ul.replaceChildren();
  for (const s of svcs) {
    const li = el('li', { class: s.up ? '' : 'is-down' });
    li.append(el('span', { class: `bolt${s.up ? '' : ' down'}`, 'aria-hidden': 'true' }));
    li.append(el('span', { class: 'svc-name' }, s.name));
    li.append(el('span', { class: 'svc-ms' }, s.ms ? `${s.ms} ms` : ''));
    li.append(el('span', { class: 'svc-note' }, `${s.up ? 'Up' : 'Down'}, ${s.note}. ${s.detail}`));
    ul.append(li);
  }
}

function verdict(state) {
  const b = $('banner');
  const problems = [];
  if (state.switchboard !== 'ok') problems.push(`The switchboard is ${state.switchboard}, so machines and links can't be shown.`);
  for (const m of state.machines) if (!m.online) problems.push(`${m.host} is offline (last seen ${ago(m.seen_s)}).`);
  const down = members(state.links).filter(m => m.path === 'down');
  for (const m of down) problems.push(`The link between ${m.a} and ${m.b} is down.`);
  for (const s of state.services) if (!s.up) problems.push(`${s.name} is down (${s.note}).`);
  b.hidden = !problems.length;
  b.textContent = problems.join(' ');
}

function tick() {
  if (!lastFetch) return;
  const s = Math.round((Date.now() - lastFetch) / 1000);
  $('checked').textContent = `Checked ${s < 2 ? 'just now' : `${s} s ago`}. Refreshes every 15 s.`;
}

async function load() {
  try {
    const r = await fetch('/api/state', { cache: 'no-store' });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const state = await r.json();
    lastFetch = Date.now();
    drawPlan(state);
    drawLinks(state.links);
    drawServices(state.services);
    verdict(state);
    const on = state.machines.filter(m => m.online).length;
    $('tb-machines').textContent = `${on} of ${state.machines.length} online`;
    $('tb-drawn').textContent = new Date(state.generated_at).toLocaleString();
    tick();
  } catch (e) {
    $('checked').textContent = `Can't reach the portal server (${e.message}). Trying again in 15 s.`;
  }
}

load();
setInterval(load, REFRESH_MS);
setInterval(tick, 1000);
