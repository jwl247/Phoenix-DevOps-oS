// pbm-radar-worker — Set-Aside Radar (PBM Consulting Service)
//
// Every morning: pull the federal opportunities posted the previous day from
// the SAM.gov Opportunities API v2, keep the set-asides, match them to each
// subscriber by NAICS + certification + state + notice type, and email a
// digest readable in ten seconds. Laurie's product; PBM is customer zero.
//
// Budget: a free non-federal SAM.gov key allows 10 requests/day. One request
// returns up to 1,000 notices, so a day's postings take ~2-5 requests. We cap
// ourselves at MAX_REQUESTS_PER_DAY (counted across every run that day) so a
// manual re-run can never burn the key's allowance.
//
// Own D1 (pbm_radar_db), own blast radius — same segmentation as every other
// public-facing worker here. Admin routes take Bearer PHOENIX_AUTH.
//
// Honesty rule: every run writes a `runs` row (requests used, notices seen,
// set-asides kept, matches per subscriber, error) and every digest footer says
// what was checked. Nothing is claimed that the run log doesn't show.

const SAM_URL = 'https://api.sam.gov/opportunities/v2/search';
const PAGE_LIMIT = 1000;
const MAX_REQUESTS_PER_DAY = 8;
const TZ = 'America/Chicago';
const EMAIL_ITEM_CAP = 30;
const KEEP_DAYS = 90;

// Certification -> the SAM.gov typeOfSetAside codes it makes you eligible for.
// EDWOSB firms also qualify for WOSB set-asides (FAR 19.15).
const CERT_SETASIDES = {
  small: ['SBA', 'SBP'],
  '8a': ['8A', '8AN'],
  hubzone: ['HZC', 'HZS'],
  wosb: ['WOSB', 'WOSBSS'],
  edwosb: ['EDWOSB', 'EDWOSBSS', 'WOSB', 'WOSBSS'],
  sdvosb: ['SDVOSBC', 'SDVOSBS'],
  vosb: ['VSA', 'VSS'],
  iee: ['IEE'],
  isbee: ['ISBEE'],
  buyindian: ['BICiv'],
};

// SAM returns the notice type as text; ptype letters are SAM's own codes.
const TYPE_TO_PTYPE = {
  'solicitation': 'o',
  'combined synopsis/solicitation': 'k',
  'presolicitation': 'p',
  'sources sought': 'r',
  'special notice': 's',
  'award notice': 'a',
  'justification': 'u',
  'sale of surplus property': 'g',
  'intent to bundle requirements (dod-funded)': 'i',
};
const ALL_PTYPES = ['o', 'k', 'p', 'r', 's', 'a', 'u', 'g', 'i'];
const DEFAULT_PTYPES = ['o', 'k', 'p', 'r'];
const PTYPE_LABEL = { o: 'Solicitation', k: 'Combined synopsis/solicitation', p: 'Presolicitation', r: 'Sources sought', s: 'Special notice', a: 'Award', u: 'Justification', g: 'Surplus sale', i: 'Intent to bundle' };

// ---------------------------------------------------------------- helpers

function json(body, status = 200) {
  return new Response(JSON.stringify(body, null, 2), { status, headers: { 'Content-Type': 'application/json' } });
}

function html(body, status = 200) {
  return new Response(body, { status, headers: { 'Content-Type': 'text/html; charset=utf-8' } });
}

function escapeHtml(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

async function sha256(text) {
  return new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(String(text))));
}

// Constant-time token check: compare digests, never the raw strings.
async function isAuthorized(req, env) {
  if (!env.PHOENIX_AUTH) return false;
  const h = req.headers.get('Authorization') || '';
  if (!h.startsWith('Bearer ')) return false;
  const [a, b] = await Promise.all([sha256(h.slice(7)), sha256(env.PHOENIX_AUTH)]);
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a[i] ^ b[i];
  return diff === 0;
}

function genToken() {
  const bytes = crypto.getRandomValues(new Uint8Array(32));
  return btoa(String.fromCharCode(...bytes)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

// Never let the API key reach a log line, an error message or a response.
function redact(s, env) {
  let out = String(s == null ? '' : s);
  if (env && env.SAM_API_KEY) out = out.split(env.SAM_API_KEY).join('[redacted]');
  return out.replace(/api_key=[^&\s"]+/g, 'api_key=[redacted]');
}

// Calendar date (YYYY-MM-DD) in Chicago for a given instant.
function chicagoDate(d = new Date()) {
  const p = new Intl.DateTimeFormat('en-CA', { timeZone: TZ, year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(d);
  const g = t => p.find(x => x.type === t).value;
  return `${g('year')}-${g('month')}-${g('day')}`;
}

function addDays(iso, n) {
  const d = new Date(iso + 'T12:00:00Z');
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

function toSamDate(iso) {
  const [y, m, d] = iso.split('-');
  return `${m}/${d}/${y}`;
}

function weekday(iso) {
  return new Date(iso + 'T12:00:00Z').getUTCDay(); // 0 Sun .. 1 Mon
}

const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

// Hand-formatted so it reads the same on every runtime ("Tue Sep 29").
function prettyDate(iso) {
  const d = new Date(iso + 'T12:00:00Z');
  return `${DAYS[d.getUTCDay()]} ${MONTHS[d.getUTCMonth()]} ${d.getUTCDate()}`;
}

function isIsoDate(s) {
  return typeof s === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(s);
}

function parseList(v) {
  if (Array.isArray(v)) return v;
  try { const a = JSON.parse(v || '[]'); return Array.isArray(a) ? a : []; } catch { return []; }
}

// ---------------------------------------------------------------- SAM.gov

function ptypeOf(typeText) {
  return TYPE_TO_PTYPE[String(typeText || '').trim().toLowerCase()] || '?';
}

function agencyOf(n) {
  const path = String(n.fullParentPathName || n.department || '').split('.').map(s => s.trim()).filter(Boolean);
  if (!path.length) return '';
  return path.length === 1 ? path[0] : `${path[0]} — ${path[path.length - 1]}`;
}

const STATE_NAMES = {
  alabama: 'AL', alaska: 'AK', arizona: 'AZ', arkansas: 'AR', california: 'CA', colorado: 'CO', connecticut: 'CT',
  delaware: 'DE', 'district of columbia': 'DC', florida: 'FL', georgia: 'GA', hawaii: 'HI', idaho: 'ID', illinois: 'IL',
  indiana: 'IN', iowa: 'IA', kansas: 'KS', kentucky: 'KY', louisiana: 'LA', maine: 'ME', maryland: 'MD',
  massachusetts: 'MA', michigan: 'MI', minnesota: 'MN', mississippi: 'MS', missouri: 'MO', montana: 'MT',
  nebraska: 'NE', nevada: 'NV', 'new hampshire': 'NH', 'new jersey': 'NJ', 'new mexico': 'NM', 'new york': 'NY',
  'north carolina': 'NC', 'north dakota': 'ND', ohio: 'OH', oklahoma: 'OK', oregon: 'OR', pennsylvania: 'PA',
  'rhode island': 'RI', 'south carolina': 'SC', 'south dakota': 'SD', tennessee: 'TN', texas: 'TX', utah: 'UT',
  vermont: 'VT', virginia: 'VA', washington: 'WA', 'west virginia': 'WV', wisconsin: 'WI', wyoming: 'WY',
  'puerto rico': 'PR', guam: 'GU',
};
const STATE_CODES = new Set(Object.values(STATE_NAMES));

// SAM sometimes leaves placeOfPerformance.state empty and puts the place in
// free text ("Yuma Proving Ground (YPG) in Yuma, Arizona"). Read the state out
// of that text: full names first (longest first, so "West Virginia" beats
// "Virginia"), then a ", XX" / "XX 12345" code.
function stateFromText(text) {
  const t = String(text || '');
  if (!t) return null;
  const lower = t.toLowerCase();
  const names = Object.keys(STATE_NAMES).sort((a, b) => b.length - a.length);
  for (const n of names) if (new RegExp(`\\b${n}\\b`).test(lower)) return STATE_NAMES[n];
  const m = t.match(/(?:,\s*|\s)([A-Z]{2})(?:\s+\d{5}|\s*$|[\s,.)])/);
  return m && STATE_CODES.has(m[1]) ? m[1] : null;
}

// SAM uses "0" as a placeholder city name.
function realCity(name) {
  const s = String(name || '').trim();
  return s && !/^\d+$/.test(s) ? s : null;
}

// Raw SAM notice -> the row we keep. Returns null for anything that is not an
// active set-aside (those are not what Radar is for).
function normalize(n) {
  const code = String(n.typeOfSetAside || '').trim();
  if (!code) return null;
  if (String(n.active || 'Yes').toLowerCase() === 'no') return null;
  const pop = n.placeOfPerformance || {};
  return {
    notice_id: String(n.noticeId),
    title: String(n.title || '').slice(0, 500),
    sol_number: n.solicitationNumber || null,
    agency: agencyOf(n).slice(0, 300),
    posted_date: String(n.postedDate || '').slice(0, 10),
    response_deadline: n.responseDeadLine || null,
    naics: String(n.naicsCode || '').trim(),
    set_aside: code,
    set_aside_desc: n.typeOfSetAsideDescription || code,
    ptype: ptypeOf(n.type || n.baseType),
    pop_state: (pop.state && pop.state.code) ? String(pop.state.code).toUpperCase() : stateFromText(pop.streetAddress),
    pop_city: realCity(pop.city && pop.city.name),
    ui_link: n.uiLink || `https://sam.gov/opp/${n.noticeId}/view`,
  };
}

async function requestsUsedOn(env, isoDate) {
  const r = await env.DB.prepare('SELECT COALESCE(SUM(requests_used),0) AS n FROM runs WHERE run_date = ?').bind(isoDate).first();
  return r ? Number(r.n) : 0;
}

// Pull every notice posted on `postedIso`, paging until totalRecords, never
// past the day's remaining request budget. Returns what it saw + what it kept.
async function fetchPosted(env, postedIso, budget) {
  const out = { requests: 0, totalRecords: 0, seen: 0, kept: [], capped: false, error: null };
  if (!env.SAM_API_KEY) { out.error = 'SAM_API_KEY unset'; return out; }
  let offset = 0;
  while (true) {
    if (out.requests >= budget) { out.capped = true; break; }
    const q = new URLSearchParams({
      api_key: env.SAM_API_KEY,
      postedFrom: toSamDate(postedIso),
      postedTo: toSamDate(postedIso),
      limit: String(PAGE_LIMIT),
      offset: String(offset),
    });
    let res;
    try {
      out.requests++;
      res = await fetch(`${SAM_URL}?${q}`, { headers: { Accept: 'application/json' }, signal: AbortSignal.timeout(30000) });
    } catch (e) {
      out.error = redact(`fetch failed: ${e.message}`, env).slice(0, 300);
      break;
    }
    if (!res.ok) {
      out.error = redact(`sam ${res.status}: ${(await res.text()).slice(0, 200)}`, env);
      break;
    }
    const body = await res.json();
    const items = Array.isArray(body.opportunitiesData) ? body.opportunitiesData : [];
    out.totalRecords = Number(body.totalRecords || 0);
    out.seen += items.length;
    for (const n of items) { const row = normalize(n); if (row) out.kept.push(row); }
    offset += items.length;
    if (!items.length || offset >= out.totalRecords) break;
  }
  return out;
}

async function storeOpportunities(env, rows) {
  if (!rows.length) return;
  const now = new Date().toISOString();
  const stmts = rows.map(r => env.DB.prepare(
    `INSERT OR REPLACE INTO opportunities
     (notice_id,title,sol_number,agency,posted_date,response_deadline,naics,set_aside,set_aside_desc,ptype,pop_state,pop_city,ui_link,fetched_at)
     VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)`
  ).bind(r.notice_id, r.title, r.sol_number, r.agency, r.posted_date, r.response_deadline, r.naics, r.set_aside,
    r.set_aside_desc, r.ptype, r.pop_state, r.pop_city, r.ui_link, now));
  for (let i = 0; i < stmts.length; i += 50) await env.DB.batch(stmts.slice(i, i + 50));
}

// ---------------------------------------------------------------- matching

function eligibleSetAsides(certs) {
  const s = new Set();
  for (const c of certs) for (const code of (CERT_SETASIDES[c] || [])) s.add(code);
  return s;
}

function normSub(row) {
  const ptypes = parseList(row.ptypes);
  return {
    ...row,
    naics: parseList(row.naics).map(String),
    certs: parseList(row.certs).map(String),
    states: parseList(row.states).map(s => String(s).toUpperCase()),
    ptypes: ptypes.length ? ptypes : DEFAULT_PTYPES,
  };
}

// All four must hold: NAICS (exact or prefix), set-aside eligible, state
// (listed / nationwide / no place given), notice type wanted. Unknown notice
// types ('?') are let through so a SAM wording change can't silently hide bids.
function matches(sub, opp) {
  if (!sub.naics.some(p => opp.naics && opp.naics.startsWith(p))) return false;
  if (!eligibleSetAsides(sub.certs).has(opp.set_aside)) return false;
  if (sub.states.length && opp.pop_state && !sub.states.includes(opp.pop_state)) return false;
  if (opp.ptype !== '?' && !sub.ptypes.includes(opp.ptype)) return false;
  return true;
}

// A bid whose response deadline has already passed is no use to anyone.
// No deadline listed = still shown (sources-sought notices often have none).
function isOpen(o, now = new Date()) {
  if (!o.response_deadline) return true;
  const t = Date.parse(o.response_deadline);
  return isNaN(t) || t >= now.getTime();
}

function byDeadline(a, b) {
  const x = a.response_deadline ? Date.parse(a.response_deadline) : Infinity;
  const y = b.response_deadline ? Date.parse(b.response_deadline) : Infinity;
  return x - y;
}

// ---------------------------------------------------------------- email

function daysLeft(deadline, now = new Date()) {
  if (!deadline) return null;
  const t = Date.parse(deadline);
  if (isNaN(t)) return null;
  return Math.ceil((t - now.getTime()) / 86400000);
}

function dueText(deadline, now) {
  const d = daysLeft(deadline, now);
  if (d == null) return 'No deadline listed';
  const [, m, dd] = chicagoDate(new Date(Date.parse(deadline))).split('-');
  const when = `${MONTHS[Number(m) - 1]} ${Number(dd)}`;
  if (d < 0) return `Closed ${when}`;
  if (d === 0) return `Due TODAY (${when})`;
  return `Due ${when} · ${d} day${d === 1 ? '' : 's'} left`;
}

function placeText(o) {
  if (o.pop_city && o.pop_state) return `${o.pop_city}, ${o.pop_state}`;
  return o.pop_state || 'Place not listed — check the bid';
}

function subjectFor(sub, count, runIso) {
  const who = sub.name || 'you';
  return `Radar · ${count} set-aside bid${count === 1 ? '' : 's'} for ${who} · ${prettyDate(runIso)}`;
}

function footerLine(stats) {
  if (stats.reused) return `Re-checked ${stats.kept.toLocaleString('en-US')} stored set-asides posted ${prettyDate(stats.posted)} · ${stats.matched} matched you.`;
  return `Checked ${stats.seen.toLocaleString('en-US')} notices posted ${prettyDate(stats.posted)} · ${stats.kept.toLocaleString('en-US')} were set-asides · ${stats.matched} matched you.`;
}

function digestText(sub, items, stats, unsubUrl, now) {
  const lines = [`SET-ASIDE RADAR — PBM Consulting Service`, ''];
  if (sub.mode === 'planning') lines.push('Planning mode: these match certifications you are PURSUING. Eligible once certified.', '');
  items.slice(0, EMAIL_ITEM_CAP).forEach((o, i) => {
    lines.push(`${i + 1}. [${o.set_aside}] ${o.title}`);
    lines.push(`   ${o.agency}`);
    lines.push(`   ${dueText(o.response_deadline, now)} · ${placeText(o)} · NAICS ${o.naics} · ${PTYPE_LABEL[o.ptype] || 'Notice'}`);
    lines.push(`   ${o.ui_link}`, '');
  });
  if (items.length > EMAIL_ITEM_CAP) lines.push(`+ ${items.length - EMAIL_ITEM_CAP} more — reply and we'll send the full list.`, '');
  lines.push(footerLine(stats), '', `Unsubscribe: ${unsubUrl}`);
  return lines.join('\n');
}

function digestHtml(sub, items, stats, unsubUrl, now) {
  const rows = items.slice(0, EMAIL_ITEM_CAP).map(o => {
    const d = daysLeft(o.response_deadline, now);
    const urgent = d != null && d >= 0 && d <= 7;
    return `<tr><td style="padding:14px 0;border-bottom:1px solid #CFC6A8;">
      <span style="display:inline-block;font:bold 11px Arial,sans-serif;letter-spacing:1px;color:#fff;background:#1F3D2B;padding:3px 7px;">${escapeHtml(o.set_aside)}</span>
      ${sub.mode === 'planning' ? '<span style="font:11px Arial,sans-serif;color:#8C2F1B;margin-left:6px;">eligible once certified</span>' : ''}
      <div style="font-size:16px;font-weight:bold;margin:6px 0 2px;"><a href="${escapeHtml(o.ui_link)}" style="color:#2B2620;text-decoration:none;">${escapeHtml(o.title)}</a></div>
      <div style="font-size:13px;color:#5a5346;">${escapeHtml(o.agency)}</div>
      <div style="font-size:13px;margin-top:4px;"><b style="color:${urgent ? '#8C2F1B' : '#2B2620'};">${escapeHtml(dueText(o.response_deadline, now))}</b>
        · ${escapeHtml(placeText(o))} · NAICS ${escapeHtml(o.naics)} · ${escapeHtml(PTYPE_LABEL[o.ptype] || 'Notice')}</div>
      <div style="margin-top:6px;"><a href="${escapeHtml(o.ui_link)}" style="font-size:13px;color:#8C2F1B;">View on SAM.gov →</a></div>
    </td></tr>`;
  }).join('');
  const more = items.length > EMAIL_ITEM_CAP
    ? `<p style="font-size:13px;">+ ${items.length - EMAIL_ITEM_CAP} more — reply and we'll send the full list.</p>` : '';
  const planning = sub.mode === 'planning'
    ? `<p style="font-size:13px;background:#E4DDC6;padding:8px 10px;margin:0 0 8px;">Planning mode: these match the certifications you are <b>pursuing</b>. Each one opens up once you're certified.</p>` : '';
  return `<!doctype html><html><body style="margin:0;background:#EFEAD9;font-family:Georgia,serif;color:#2B2620;">
  <div style="max-width:600px;margin:24px auto;padding:28px;background:#fff;border:1px solid #CFC6A8;">
    <div style="border-bottom:2px solid #1F3D2B;padding-bottom:12px;margin-bottom:14px;">
      <div style="font-size:12px;letter-spacing:2px;color:#8C2F1B;font-family:Arial,sans-serif;">SET-ASIDE RADAR</div>
      <div style="font-size:20px;font-weight:bold;color:#1F3D2B;">${items.length} new set-aside bid${items.length === 1 ? '' : 's'} for ${escapeHtml(sub.name || 'you')}</div>
    </div>
    ${planning}
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0">${rows}</table>
    ${more}
    <p style="font-size:12px;color:#5a5346;margin-top:20px;">${escapeHtml(footerLine(stats))}</p>
    <p style="font-size:12px;color:#5a5346;">PBM Consulting Service · 6814 Chris Madsen Rd, Guthrie, OK 73044 ·
      <a href="${escapeHtml(unsubUrl)}" style="color:#5a5346;">Unsubscribe</a></p>
  </div></body></html>`;
}

function quietText(sub, weekCount, unsubUrl) {
  return [`SET-ASIDE RADAR — weekly check-in`, '',
    weekCount
      ? `Nothing new matched ${sub.name || 'you'} yesterday. ${weekCount} bid${weekCount === 1 ? '' : 's'} matched in the past 7 days (sent as they came in).`
      : `Radar checked every day this past week. Nothing matched ${sub.name || 'you'} — no set-aside bids in your NAICS/states.`,
    '', 'Radar is running; you will hear from it the morning something matches.', '', `Unsubscribe: ${unsubUrl}`].join('\n');
}

// Never throws. 'ok' | 'skip' | 'err:<reason>'.
async function sendEmail(env, { to, subject, text, htmlBody, unsubUrl }) {
  if (!env.RESEND_API_KEY) return 'skip';
  try {
    const payload = {
      from: env.RESEND_FROM || 'Set-Aside Radar <onboarding@resend.dev>',
      to: [to], subject, text,
      headers: { 'List-Unsubscribe': `<${unsubUrl}>`, 'List-Unsubscribe-Post': 'List-Unsubscribe=One-Click' },
    };
    if (htmlBody) payload.html = htmlBody;
    const res = await fetch('https://api.resend.com/emails', {
      method: 'POST',
      headers: { Authorization: `Bearer ${env.RESEND_API_KEY}`, 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) return `err:resend ${res.status} ${(await res.text()).slice(0, 140)}`;
    return 'ok';
  } catch (e) {
    return `err:${String(e.message).slice(0, 160)}`;
  }
}

// ---------------------------------------------------------------- the run

function baseUrl(env) {
  return (env.WORKER_PUBLIC_URL || 'https://pbm-radar-worker.phoenix-jwl.workers.dev').replace(/\/+$/, '');
}

// opts: { dry, fetch (default true), date (the posted date, default yesterday Chicago), now }
async function runRadar(env, opts = {}) {
  const now = opts.now || new Date();
  const runIso = chicagoDate(now);
  const posted = opts.date || addDays(runIso, -1);
  const dry = !!opts.dry;
  const summary = { run_date: runIso, posted, dry, requests_used: 0, seen: 0, kept: 0, capped: false, error: null, subscribers: [] };

  if (opts.fetch !== false) {
    const budget = MAX_REQUESTS_PER_DAY - await requestsUsedOn(env, runIso);
    if (budget <= 0) {
      summary.error = `daily SAM.gov request budget (${MAX_REQUESTS_PER_DAY}) already used`;
    } else {
      const f = await fetchPosted(env, posted, budget);
      summary.requests_used = f.requests;
      summary.seen = f.seen;
      summary.kept = f.kept.length;
      summary.capped = f.capped;
      summary.error = f.error;
      if (f.capped) summary.error = (summary.error ? summary.error + '; ' : '') + `stopped at request budget: saw ${f.seen} of ${f.totalRecords}`;
      await storeOpportunities(env, f.kept);
    }
  }

  const opps = (await env.DB.prepare('SELECT * FROM opportunities WHERE posted_date = ?').bind(posted).all()).results || [];
  if (opts.fetch === false) { summary.kept = opps.length; }
  const subs = ((await env.DB.prepare('SELECT * FROM subscribers WHERE active = 1').all()).results || []).map(normSub);
  const monday = weekday(runIso) === 1;

  for (const sub of subs) {
    const matched = opps.filter(o => matches(sub, o) && isOpen(o, now)).sort(byDeadline);
    const already = new Set(((await env.DB.prepare('SELECT notice_id FROM sent_matches WHERE subscriber_id = ?').bind(sub.id).all()).results || []).map(r => r.notice_id));
    const fresh = matched.filter(o => !already.has(o.notice_id));
    const unsubUrl = `${baseUrl(env)}/unsub/${sub.unsub_token}`;
    const stats = { seen: summary.seen, kept: summary.kept, matched: fresh.length, posted, reused: opts.fetch === false };
    const entry = { id: sub.id, email: sub.email, matched: fresh.length, sent: 'none' };

    if (fresh.length) {
      const mail = {
        to: sub.email,
        subject: subjectFor(sub, fresh.length, runIso),
        text: digestText(sub, fresh, stats, unsubUrl, now),
        htmlBody: digestHtml(sub, fresh, stats, unsubUrl, now),
        unsubUrl,
      };
      if (dry) {
        entry.sent = 'dry';
        entry.preview = { subject: mail.subject, text: mail.text };
      } else {
        entry.sent = await sendEmail(env, mail);
        if (entry.sent === 'ok') {
          const ts = now.toISOString();
          await env.DB.batch(fresh.map(o => env.DB.prepare('INSERT OR IGNORE INTO sent_matches (subscriber_id, notice_id, sent_at) VALUES (?,?,?)').bind(sub.id, o.notice_id, ts)));
        }
      }
    } else if (monday && !dry) {
      const since = new Date(now.getTime() - 7 * 86400000).toISOString();
      const wk = await env.DB.prepare('SELECT COUNT(*) AS n FROM sent_matches WHERE subscriber_id = ? AND sent_at >= ?').bind(sub.id, since).first();
      const weekCount = wk ? Number(wk.n) : 0;
      entry.sent = 'quiet:' + await sendEmail(env, {
        to: sub.email,
        subject: `Radar · weekly check-in for ${sub.name || 'you'} · ${prettyDate(runIso)}`,
        text: quietText(sub, weekCount, unsubUrl),
        unsubUrl,
      });
    }
    summary.subscribers.push(entry);
  }

  if (!dry || summary.requests_used) {
    // Dry runs that spent SAM requests are still logged — the budget is real.
    await env.DB.prepare(
      `INSERT INTO runs (run_date, posted_date, dry, requests_used, notices_seen, set_asides_kept, capped, matches_json, error, created_at)
       VALUES (?,?,?,?,?,?,?,?,?,?)`
    ).bind(runIso, posted, dry ? 1 : 0, summary.requests_used, summary.seen, summary.kept, summary.capped ? 1 : 0,
      JSON.stringify(summary.subscribers.map(s => ({ id: s.id, matched: s.matched, sent: s.sent }))),
      summary.error, now.toISOString()).run();
  }
  if (!dry) {
    await env.DB.prepare('DELETE FROM opportunities WHERE posted_date < ?').bind(addDays(runIso, -KEEP_DAYS)).run();
  }
  return summary;
}

// ---------------------------------------------------------------- admin

function validateSubscriber(b) {
  const errs = [];
  if (!b || typeof b !== 'object') return ['body must be JSON'];
  if (typeof b.email !== 'string' || b.email.length > 254 || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(b.email)) errs.push('email invalid');
  if (b.name != null && (typeof b.name !== 'string' || b.name.length > 120)) errs.push('name invalid');
  const naics = b.naics || [];
  if (!Array.isArray(naics) || !naics.length || !naics.every(n => /^\d{2,6}$/.test(String(n)))) errs.push('naics: list of 2-6 digit codes/prefixes required');
  const certs = b.certs || [];
  if (!Array.isArray(certs) || !certs.length || !certs.every(c => CERT_SETASIDES[c])) errs.push(`certs: list from ${Object.keys(CERT_SETASIDES).join(', ')}`);
  if (b.states != null && (!Array.isArray(b.states) || !b.states.every(s => /^[A-Za-z]{2}$/.test(s)))) errs.push('states: list of 2-letter codes (empty = nationwide)');
  if (b.ptypes != null && (!Array.isArray(b.ptypes) || !b.ptypes.every(p => ALL_PTYPES.includes(p)))) errs.push(`ptypes: list from ${ALL_PTYPES.join(', ')}`);
  if (b.mode != null && !['certified', 'planning'].includes(b.mode)) errs.push('mode: certified | planning');
  return errs;
}

async function upsertSubscriber(req, env) {
  let b;
  try { b = await req.json(); } catch { return json({ ok: false, error: 'bad json' }, 400); }
  const errs = validateSubscriber(b);
  if (errs.length) return json({ ok: false, errors: errs }, 400);
  const email = b.email.trim().toLowerCase();
  const fields = [
    b.name || null,
    JSON.stringify(b.naics.map(String)),
    JSON.stringify(b.certs),
    JSON.stringify((b.states || []).map(s => s.toUpperCase())),
    JSON.stringify(b.ptypes && b.ptypes.length ? b.ptypes : DEFAULT_PTYPES),
    b.mode || 'certified',
    b.active === false ? 0 : 1,
  ];
  const existing = await env.DB.prepare('SELECT id FROM subscribers WHERE email = ?').bind(email).first();
  if (existing) {
    await env.DB.prepare('UPDATE subscribers SET name=?, naics=?, certs=?, states=?, ptypes=?, mode=?, active=? WHERE id=?').bind(...fields, existing.id).run();
    return json({ ok: true, id: existing.id, updated: true });
  }
  const r = await env.DB.prepare('INSERT INTO subscribers (email, name, naics, certs, states, ptypes, mode, active, unsub_token, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)')
    .bind(email, ...fields, genToken(), new Date().toISOString()).run();
  return json({ ok: true, id: r.meta && r.meta.last_row_id, created: true });
}

async function preview(url, env) {
  const id = Number(url.searchParams.get('subscriber'));
  const date = url.searchParams.get('date') || addDays(chicagoDate(), -1);
  if (!id || !isIsoDate(date)) return json({ ok: false, error: 'need ?subscriber=<id>&date=YYYY-MM-DD' }, 400);
  const row = await env.DB.prepare('SELECT * FROM subscribers WHERE id = ?').bind(id).first();
  if (!row) return json({ ok: false, error: 'no such subscriber' }, 404);
  const sub = normSub(row);
  const opps = (await env.DB.prepare('SELECT * FROM opportunities WHERE posted_date = ?').bind(date).all()).results || [];
  const m = opps.filter(o => matches(sub, o) && isOpen(o)).sort(byDeadline);
  return json({ ok: true, date, set_asides_stored: opps.length, matched: m.length, matches: m });
}

// ---------------------------------------------------------------- unsubscribe

function unsubPage(msg, token) {
  const form = token
    ? `<form method="POST" action="/unsub/${escapeHtml(token)}"><button style="font:16px Georgia,serif;padding:10px 18px;background:#8C2F1B;color:#fff;border:0;cursor:pointer;">Unsubscribe me</button></form>`
    : '';
  return `<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>Set-Aside Radar</title></head>
  <body style="margin:0;background:#EFEAD9;font-family:Georgia,serif;color:#2B2620;">
  <div style="max-width:480px;margin:40px auto;padding:28px;background:#fff;border:1px solid #CFC6A8;">
  <div style="font-size:12px;letter-spacing:2px;color:#8C2F1B;font-family:Arial,sans-serif;">SET-ASIDE RADAR</div>
  <p>${escapeHtml(msg)}</p>${form}</div></body></html>`;
}

async function handleUnsub(req, env, token) {
  const row = token ? await env.DB.prepare('SELECT id, active FROM subscribers WHERE unsub_token = ?').bind(token).first() : null;
  if (!row) return html(unsubPage('That unsubscribe link is not valid.'), 404);
  // A GET alone never acts — mail scanners follow links. RFC 8058 one-click posts.
  if (req.method === 'GET') {
    return html(row.active ? unsubPage('Stop the daily Set-Aside Radar emails?', token) : unsubPage('You are already unsubscribed.'));
  }
  await env.DB.prepare('UPDATE subscribers SET active = 0 WHERE id = ? AND active = 1').bind(row.id).run();
  return html(unsubPage('Done — you will not get Set-Aside Radar emails anymore.'));
}

// ---------------------------------------------------------------- entry

export {
  CERT_SETASIDES, normalize, matches, stateFromText, realCity, isOpen, normSub, eligibleSetAsides, ptypeOf, chicagoDate, addDays, toSamDate,
  redact, isAuthorized, fetchPosted, runRadar, subjectFor, footerLine, validateSubscriber, digestText,
};

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    const path = url.pathname.replace(/\/+$/, '') || '/';

    if (path === '/health') {
      const last = env.DB ? await env.DB.prepare('SELECT run_date, dry, requests_used, set_asides_kept, error FROM runs ORDER BY id DESC LIMIT 1').first().catch(() => null) : null;
      return json({
        status: 'ok', worker: 'pbm-radar-worker',
        db_bound: !!env.DB,
        sam_key: env.SAM_API_KEY ? 'set' : 'UNSET',
        transport: env.RESEND_API_KEY ? 'resend' : 'NONE',
        admin_auth: env.PHOENIX_AUTH ? 'set' : 'UNSET',
        last_run: last || null,
      });
    }

    if (path.startsWith('/unsub/') && (req.method === 'GET' || req.method === 'POST')) {
      let token = '';
      try { token = decodeURIComponent(path.slice('/unsub/'.length)); } catch { token = ''; }
      return handleUnsub(req, env, token);
    }

    const admin = ['/whoami', '/subscribers', '/preview', '/run', '/runs'];
    if (admin.includes(path)) {
      if (!(await isAuthorized(req, env))) return json({ ok: false, error: 'unauthorized' }, 401);
      // rotate-phoenix-auth.sh verifies each leg here.
      if (path === '/whoami') return json({ ok: true, worker: 'pbm-radar-worker' });
      if (path === '/subscribers' && req.method === 'POST') return upsertSubscriber(req, env);
      if (path === '/subscribers' && req.method === 'GET') {
        const r = await env.DB.prepare('SELECT id, email, name, naics, certs, states, ptypes, mode, active, created_at FROM subscribers ORDER BY id').all();
        return json({ ok: true, subscribers: r.results || [] });
      }
      if (path === '/preview' && req.method === 'GET') return preview(url, env);
      if (path === '/runs' && req.method === 'GET') {
        const r = await env.DB.prepare('SELECT * FROM runs ORDER BY id DESC LIMIT 30').all();
        return json({ ok: true, runs: r.results || [] });
      }
      if (path === '/run' && req.method === 'POST') {
        const date = url.searchParams.get('date');
        if (date && !isIsoDate(date)) return json({ ok: false, error: 'date must be YYYY-MM-DD' }, 400);
        const s = await runRadar(env, {
          dry: url.searchParams.get('dry') === '1',
          fetch: url.searchParams.get('fetch') !== '0',
          date: date || undefined,
        });
        return json({ ok: !s.error, ...s });
      }
      return json({ ok: false, error: 'method not allowed' }, 405);
    }
    return json({ ok: false, error: 'not found' }, 404);
  },

  async scheduled(event, env, ctx) {
    ctx.waitUntil(runRadar(env).catch(async e => {
      try {
        await env.DB.prepare('INSERT INTO runs (run_date, posted_date, dry, requests_used, notices_seen, set_asides_kept, capped, matches_json, error, created_at) VALUES (?,?,0,0,0,0,0,?,?,?)')
          .bind(chicagoDate(), addDays(chicagoDate(), -1), '[]', redact(`crash: ${e.message}`, env).slice(0, 300), new Date().toISOString()).run();
      } catch { /* nothing left to record into */ }
    }));
  },
};
