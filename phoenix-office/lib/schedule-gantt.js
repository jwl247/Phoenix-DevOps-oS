'use strict';
// schedule-gantt.js — the Master schedule document, drawn as a schedule chart.
//
// Dates across the top, one trade per row down the left, a bar per trade
// coloured by status (green on schedule / yellow over schedule / red critical,
// Jerry 2026-09-26), and that trade's "what's scheduled" words under its bar.
//
// Source = the document's own phase_breakdown field, one line per trade:
//     Trade | start | finish | status | what's scheduled
//     Steel erection | 2026-10-05 | 2026-10-23 | on | set columns grid A-D, bolt-up
// status: on | over | critical (also green/yellow/red; blank = on). Dates are
// YYYY-MM-DD or M/D/YYYY. Lines that don't parse are reported, never guessed,
// and the chart is simply left out if no line parses (the field table stays).
//
// Pure string output (no DOM), so the same code draws the live preview in the
// app and the exported PDF (via document-html.js -> LibreOffice).

const COLORS = { green: '#2e7d32', yellow: '#e0a800', red: '#c62828' };
const WORDS = { green: 'on schedule', yellow: 'over schedule', red: 'critical' };
const STATUS = {
  '': 'green', on: 'green', 'on schedule': 'green', green: 'green', ok: 'green', scheduled: 'green',
  over: 'yellow', 'over schedule': 'yellow', late: 'yellow', yellow: 'yellow', behind: 'yellow',
  critical: 'red', red: 'red',
};
const DAY = 86400000;

function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function parseDate(s) {
  const t = String(s || '').trim();
  let m = /^(\d{4})-(\d{1,2})-(\d{1,2})$/.exec(t);
  if (m) return Date.UTC(+m[1], +m[2] - 1, +m[3]);
  m = /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/.exec(t);
  if (m) return Date.UTC(+m[3], +m[1] - 1, +m[2]);
  return null;
}

function parseBreakdown(text) {
  const rows = [], problems = [];
  String(text || '').split(/\r?\n/).forEach((line, i) => {
    if (!line.trim()) return;
    const parts = line.split('|').map(s => s.trim());
    if (parts.length < 3) { problems.push({ line: i + 1, text: line, why: 'needs at least: trade | start | finish' }); return; }
    const [trade, s, e, st = '', ...rest] = parts;
    const start = parseDate(s), end = parseDate(e);
    if (!trade) { problems.push({ line: i + 1, text: line, why: 'no trade name' }); return; }
    if (start == null || end == null) { problems.push({ line: i + 1, text: line, why: 'dates must be YYYY-MM-DD or M/D/YYYY' }); return; }
    if (end < start) { problems.push({ line: i + 1, text: line, why: 'finish is before start' }); return; }
    const status = STATUS[st.toLowerCase()];
    if (!status) { problems.push({ line: i + 1, text: line, why: `status "${st}" should be on, over or critical` }); return; }
    rows.push({ trade, start, end, status, notes: rest.join(' | ') });
  });
  return { rows, problems };
}

// fields: the document's fields. Returns '' when there's nothing to draw.
function scheduleSvg(fields, { width = 1000 } = {}) {
  const { rows } = parseBreakdown(fields && fields.phase_breakdown);
  if (!rows.length) return '';
  const target = parseDate(fields.overall_target_completion);
  const asOf = parseDate(fields.date);
  const lo = Math.min(...rows.map(r => r.start), parseDate(fields.overall_start_date) ?? Infinity) - DAY;
  const hi = Math.max(...rows.map(r => r.end), target ?? 0) + 2 * DAY;
  const W = width, X0 = 214, X1 = W - 16, TOP = 44, ROW = 50;
  const x = t => X0 + (t - lo) / (hi - lo) * (X1 - X0);
  const H = TOP + rows.length * ROW + 12;
  const fmt = t => new Date(t).toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' });
  const weeks = (hi - lo) / (7 * DAY);
  const step = weeks > 30 ? 28 : weeks > 16 ? 14 : 7;

  let ticks = '';
  for (let t = rows.reduce((m, r) => Math.min(m, r.start), Infinity); t <= hi; t += step * DAY) {
    ticks += `<line x1="${x(t)}" x2="${x(t)}" y1="${TOP - 8}" y2="${H - 10}" stroke="#e3e6ea"/>`
      + `<text x="${x(t) + 3}" y="${TOP - 14}" font-size="11" fill="#5b6470">${esc(fmt(t))}</text>`;
  }
  const vline = (t, label, color, dash) => (t == null || t < lo || t > hi) ? '' :
    `<line x1="${x(t)}" x2="${x(t)}" y1="${TOP - 30}" y2="${H - 10}" stroke="${color}" stroke-width="1.5"${dash ? ' stroke-dasharray="5 4"' : ''}/>`
    + (x(t) > X1 - 130
        ? `<text x="${x(t) - 4}" y="${TOP - 32}" font-size="11" font-weight="700" fill="${color}" text-anchor="end">${esc(label)}</text>`
        : `<text x="${x(t) + 4}" y="${TOP - 32}" font-size="11" font-weight="700" fill="${color}">${esc(label)}</text>`);

  const bars = rows.map((r, i) => {
    const y0 = TOP + i * ROW, c = COLORS[r.status];
    const noteX = Math.min(x(r.start), X1 - 380);
    const tip = `${r.trade}: ${new Date(r.start).toISOString().slice(0, 10)} to ${new Date(r.end).toISOString().slice(0, 10)} (${WORDS[r.status]})`;
    return `<g>`
      + `<rect x="0" y="${y0}" width="${W}" height="${ROW}" fill="${i % 2 ? '#f7f8fa' : '#ffffff'}"/>`
      + `<text x="12" y="${y0 + 21}" font-size="13" font-weight="700" fill="#1d232b">${esc(r.trade)}</text>`
      + `<text x="12" y="${y0 + 37}" font-size="11" font-weight="700" fill="${c}">${esc(WORDS[r.status])}</text>`
      + `<rect x="${x(r.start)}" y="${y0 + 10}" width="${Math.max(4, x(r.end + DAY) - x(r.start))}" height="18" rx="3" fill="${c}"><title>${esc(tip)}</title></rect>`
      + (r.notes ? `<text x="${noteX}" y="${y0 + 43}" font-size="11" fill="#39414b">${esc(r.notes)}</text>` : '')
      + `</g>`;
  }).join('');

  const legend = ['green', 'yellow', 'red'].map((k, i) =>
    `<rect x="${12 + i * 150}" y="${H - 2}" width="16" height="10" rx="2" fill="${COLORS[k]}"/>`
    + `<text x="${34 + i * 150}" y="${H + 7}" font-size="11" fill="#5b6470">${esc(WORDS[k])}</text>`).join('');

  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${H + 14}" width="100%" role="img" aria-label="Schedule by trade" font-family="Segoe UI, Arial, sans-serif">`
    + `<rect x="0" y="0" width="${W}" height="${H + 14}" fill="#ffffff"/>`
    + ticks + bars
    + vline(target, 'Target completion', '#6b3fa0', true)
    + vline(asOf, 'As of', '#1d232b', false)
    + legend + `</svg>`;
}

// Project Assist -> this format, one line per phase, status from scheduleTimeline().
function breakdownFromTimeline(timeline) {
  const word = { green: 'on', yellow: 'over', red: 'critical' };
  return (timeline.rows || []).map(r => {
    const end = r.actual_end || r.projected_end;
    const start = r.actual_start || r.planned_start;
    return [r.label, start, end, word[r.status] || 'on', r.notes || ''].join(' | ');
  }).join('\n');
}

module.exports = { parseBreakdown, scheduleSvg, breakdownFromTimeline, COLORS, WORDS };
