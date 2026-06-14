// packages-worker — Phoenix DevOps OS
// UnitedSys — United Systems | jwl247
// Role: Catalog index — clonepool, glossary, TOC, packages, peer review
// DB: phoenix_dev_db (D1) — the backbone
// Auth: PHOENIX_AUTH (Cloudflare secret)
// Version: 3.4.0

const HEADERS = {
  'Content-Type': 'application/json',
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type, Authorization',
};

const ok = (data, status = 200) => new Response(JSON.stringify(data, null, 2), { status, headers: HEADERS });
const err = (msg, status = 400) => ok({ error: msg }, status);

// ── Auth ─────────────────────────────────────────────────────────────────────
function isAuthorized(req, env) {
  const token = req.headers.get('Authorization')?.replace('Bearer ', '').trim();
  return token && token === env.PHOENIX_AUTH;
}

// ── Platform HTML ───────────────────────────────────────────────────────────
const HTML_PLATFORM = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Phoenix Package Handler — Platform</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  :root{--bg:#0d1117;--surface:#161b22;--border:#30363d;--accent:#f78166;--accent2:#79c0ff;--text:#e6edf3;--muted:#8b949e;--green:#56d364;--red:#f85149;--yellow:#e3b341;--purple:#bc8cff}
  body{font-family:'Segoe UI',system-ui,sans-serif;background:var(--bg);color:var(--text);min-height:100vh}
  header{background:var(--surface);border-bottom:1px solid var(--border);padding:12px 24px;display:flex;align-items:center;gap:16px}
  header h1{font-size:1.1rem;font-weight:600;color:var(--accent)}
  header span{color:var(--muted);font-size:.85rem}
  .tabs{display:flex;gap:0;border-bottom:1px solid var(--border);background:var(--surface);padding:0 24px}
  .tab{padding:10px 18px;cursor:pointer;border:none;background:none;color:var(--muted);font-size:.9rem;border-bottom:2px solid transparent;transition:all .15s}
  .tab:hover{color:var(--text)}
  .tab.active{color:var(--accent2);border-bottom-color:var(--accent2)}
  .panel{display:none;padding:24px;max-width:1100px;margin:0 auto}
  .panel.active{display:block}
  .card{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:16px;margin-bottom:12px}
  .card h3{font-size:.95rem;font-weight:600;margin-bottom:8px}
  .badge{display:inline-block;padding:2px 8px;border-radius:12px;font-size:.75rem;font-weight:600}
  .badge.white{background:#1f3a2a;color:var(--green)}
  .badge.grey{background:#2d2a1f;color:var(--yellow)}
  .badge.black{background:#2d1f1f;color:var(--red)}
  .badge.pending{background:#1f2a3a;color:var(--accent2)}
  .badge.approved{background:#1f3a2a;color:var(--green)}
  .badge.rejected{background:#2d1f1f;color:var(--red)}
  .badge.revoked{background:#2d1f2d;color:var(--purple)}
  .row{display:flex;gap:12px;align-items:center;flex-wrap:wrap}
  .row.sb{justify-content:space-between}
  input,select,textarea{background:#0d1117;border:1px solid var(--border);color:var(--text);border-radius:6px;padding:8px 12px;font-size:.9rem;font-family:inherit;width:100%}
  input:focus,select:focus,textarea:focus{outline:none;border-color:var(--accent2)}
  textarea{resize:vertical;min-height:80px}
  .btn{padding:8px 16px;border:none;border-radius:6px;cursor:pointer;font-size:.85rem;font-weight:600;transition:opacity .15s}
  .btn:hover{opacity:.85}
  .btn:disabled{opacity:.4;cursor:not-allowed}
  .btn.primary{background:var(--accent2);color:#0d1117}
  .btn.success{background:var(--green);color:#0d1117}
  .btn.danger{background:var(--red);color:#fff}
  .btn.warn{background:var(--yellow);color:#0d1117}
  .btn.ghost{background:transparent;border:1px solid var(--border);color:var(--text)}
  .form-row{display:grid;gap:10px;margin-bottom:14px}
  .form-row label{font-size:.8rem;color:var(--muted);margin-bottom:2px;display:block}
  .grid2{display:grid;grid-template-columns:1fr 1fr;gap:12px}
  .grid3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px}
  .meta{font-size:.78rem;color:var(--muted)}
  .votes{display:flex;gap:6px;align-items:center}
  .votes span{font-size:.8rem}
  #toast{position:fixed;bottom:24px;right:24px;padding:12px 20px;border-radius:8px;font-size:.9rem;font-weight:500;opacity:0;transition:opacity .3s;pointer-events:none;z-index:999}
  #toast.show{opacity:1}
  #toast.ok{background:#1f3a2a;color:var(--green);border:1px solid var(--green)}
  #toast.err{background:#2d1f1f;color:var(--red);border:1px solid var(--red)}
  .empty{text-align:center;color:var(--muted);padding:40px 0;font-size:.9rem}
  .filter-bar{display:flex;gap:10px;margin-bottom:16px;flex-wrap:wrap}
  .filter-bar input{max-width:280px}
  .filter-bar select{max-width:160px;width:auto}
  details summary{cursor:pointer;color:var(--accent2);font-size:.85rem;margin-top:8px}
  .vote-row{display:flex;gap:8px;margin-top:10px}
  .hex{font-family:monospace;font-size:.8rem;color:var(--muted)}
  hr{border:none;border-top:1px solid var(--border);margin:16px 0}
  .loading{text-align:center;padding:32px;color:var(--muted)}
  .auth-note{background:#1a1a2a;border:1px solid #3a3a5a;border-radius:6px;padding:10px 14px;font-size:.82rem;color:var(--muted);margin-bottom:14px}
  .auth-note b{color:var(--accent2)}
</style>
</head>
<body>
<header>
  <div>
    <h1>&#9654; Phoenix Package Handler</h1>
    <span>UnitedSys &mdash; United Systems &bull; packages-worker</span>
  </div>
  <div style="margin-left:auto;display:flex;gap:10px;align-items:center">
    <label style="font-size:.8rem;color:var(--muted)">Auth Token</label>
    <input id="authToken" type="password" placeholder="PHOENIX_AUTH" style="width:200px;padding:6px 10px;font-size:.82rem">
  </div>
</header>

<div class="tabs">
  <button class="tab active" onclick="showTab('glossary')">Glossary</button>
  <button class="tab" onclick="showTab('review')">Review Queue</button>
  <button class="tab" onclick="showTab('submit')">Submit</button>
  <button class="tab" onclick="showTab('feed')">Opt-In Feed</button>
  <button class="tab" onclick="showTab('verify')">Verify</button>
</div>

<!-- GLOSSARY TAB -->
<div id="tab-glossary" class="panel active">
  <div class="row sb" style="margin-bottom:16px">
    <h2 style="font-size:1rem">Package Glossary</h2>
    <button class="btn primary" onclick="openGlossaryAdd()">+ Add Entry</button>
  </div>
  <div class="filter-bar">
    <input id="g-search" placeholder="Search by name..." oninput="loadGlossary()">
    <select id="g-cat" onchange="loadGlossary()"><option value="">All Categories</option></select>
    <select id="g-state" onchange="loadGlossary()">
      <option value="">All States</option>
      <option value="white">White (active)</option>
      <option value="grey">Grey (deprecated)</option>
      <option value="black">Black (retired)</option>
    </select>
    <button class="btn ghost" onclick="loadGlossary()">Refresh</button>
  </div>
  <div id="glossary-list"><div class="loading">Loading glossary...</div></div>
  
  <!-- Add/Edit Modal -->
  <div id="glossary-modal" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:100;display:flex;align-items:center;justify-content:center">
    <div style="background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:24px;width:560px;max-width:95vw;max-height:90vh;overflow-y:auto">
      <h3 id="gmodal-title" style="margin-bottom:16px">Add Glossary Entry</h3>
      <div class="grid2">
        <div class="form-row"><label>Name *</label><input id="gf-name" placeholder="e.g. nginx.conf"></div>
        <div class="form-row"><label>Hex (SHA-derived)</label><input id="gf-hex" placeholder="auto-generated if blank"></div>
      </div>
      <div class="form-row"><label>Description</label><textarea id="gf-desc" rows="2" placeholder="What does this package do?"></textarea></div>
      <div class="grid3">
        <div class="form-row"><label>Category</label><input id="gf-cat" placeholder="scripts, configs..."></div>
        <div class="form-row"><label>Platform</label>
          <select id="gf-platform"><option value="">any</option><option>linux</option><option>macos</option><option>windows</option><option>all</option></select>
        </div>
        <div class="form-row"><label>State</label>
          <select id="gf-state"><option value="white">white</option><option value="grey">grey</option><option value="black">black</option></select>
        </div>
      </div>
      <div class="grid2">
        <div class="form-row"><label>Version</label><input id="gf-version" placeholder="1.0.0"></div>
        <div class="form-row"><label>Backend</label><input id="gf-backend" placeholder="apt, brew, pip..."></div>
      </div>
      <div class="form-row"><label>Notes</label><input id="gf-notes" placeholder="optional notes"></div>
      <input type="hidden" id="gf-editing-hex">
      <div class="row" style="margin-top:16px;gap:8px;justify-content:flex-end">
        <button class="btn ghost" onclick="closeGlossaryModal()">Cancel</button>
        <button class="btn primary" onclick="saveGlossaryEntry()">Save Entry</button>
      </div>
    </div>
  </div>
</div>

<!-- REVIEW QUEUE TAB -->
<div id="tab-review" class="panel">
  <div class="row sb" style="margin-bottom:16px">
    <h2 style="font-size:1rem">Review Queue</h2>
    <div class="row" style="gap:8px">
      <select id="r-status" onchange="loadReviews()">
        <option value="">All</option>
        <option value="pending">Pending</option>
        <option value="approved">Approved</option>
        <option value="rejected">Rejected</option>
        <option value="revoked">Revoked</option>
      </select>
      <button class="btn ghost" onclick="loadReviews()">Refresh</button>
    </div>
  </div>
  <div id="review-list"><div class="loading">Loading submissions...</div></div>
</div>

<!-- SUBMIT TAB -->
<div id="tab-submit" class="panel">
  <div style="max-width:600px">
    <h2 style="font-size:1rem;margin-bottom:6px">Submit Artifact for Review</h2>
    <p style="color:var(--muted);font-size:.85rem;margin-bottom:16px">Submit a file, package, config, or dependency for community peer review. The hex hash is the canonical identity.</p>
    <div class="auth-note"><b>Auth required.</b> Set your PHOENIX_AUTH token in the header above before submitting.</div>
    <div class="form-row"><label>Artifact Name *</label><input id="sf-name" placeholder="e.g. nginx.conf"></div>
    <div class="form-row"><label>SHA-256 Hex *</label><input id="sf-hex" placeholder="64-char SHA-256 hash of the artifact"></div>
    <div class="form-row"><label>Description</label><textarea id="sf-desc" placeholder="What does this artifact do?"></textarea></div>
    <div class="grid2">
      <div class="form-row"><label>Category</label><input id="sf-cat" placeholder="scripts, configs, packages..."></div>
      <div class="form-row"><label>Platform</label>
        <select id="sf-platform"><option value="">any</option><option>linux</option><option>macos</option><option>windows</option><option>all</option></select>
      </div>
    </div>
    <div class="form-row"><label>Submitter Handle</label><input id="sf-submitter" placeholder="your handle or ID (optional)"></div>
    <div class="form-row"><label>Artifact URL (optional pull pointer — not the content)</label><input id="sf-url" placeholder="https://..."></div>
    <button class="btn primary" onclick="submitArtifact()" style="margin-top:8px">Submit for Review</button>
  </div>
</div>

<!-- FEED TAB -->
<div id="tab-feed" class="panel">
  <div class="row sb" style="margin-bottom:16px">
    <div>
      <h2 style="font-size:1rem">Opt-In Availability Feed</h2>
      <p style="color:var(--muted);font-size:.82rem;margin-top:4px">Approved artifacts available to pull. Nothing is pushed — availability is announced only.</p>
    </div>
    <div class="row" style="gap:8px">
      <select id="feed-cat" onchange="loadFeed()"><option value="">All Categories</option></select>
      <select id="feed-platform" onchange="loadFeed()">
        <option value="">All Platforms</option>
        <option>linux</option><option>macos</option><option>windows</option><option>all</option>
      </select>
      <button class="btn ghost" onclick="loadFeed()">Refresh</button>
    </div>
  </div>
  <div id="feed-list"><div class="loading">Loading feed...</div></div>
</div>

<!-- VERIFY TAB -->
<div id="tab-verify" class="panel">
  <div style="max-width:560px">
    <h2 style="font-size:1rem;margin-bottom:6px">Verify Artifact</h2>
    <p style="color:var(--muted);font-size:.85rem;margin-bottom:16px">Enter a SHA-256 hex to check an artifact's verification status. Scan a QR code or paste the hash directly.</p>
    <div class="row" style="gap:10px;margin-bottom:16px">
      <input id="v-hex" placeholder="SHA-256 hex hash..." style="flex:1">
      <button class="btn primary" onclick="verifyArtifact()">Verify</button>
    </div>
    <div id="verify-result"></div>
  </div>
</div>

<div id="toast"></div>

<script>
const BASE = '';  // same-origin — worker serves this HTML and the API

function getAuth() { return document.getElementById('authToken').value.trim(); }

function toast(msg, type='ok') {
  const t = document.getElementById('toast');
  t.textContent = msg; t.className = 'show ' + type;
  setTimeout(() => t.className = '', 3000);
}

function showTab(name) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  event.target.classList.add('active');
  document.getElementById('tab-' + name).classList.add('active');
  if(name === 'glossary') loadGlossary();
  if(name === 'review') loadReviews();
  if(name === 'feed') loadFeed();
}

async function apiFetch(path, opts={}) {
  const auth = getAuth();
  const headers = { 'Content-Type': 'application/json' };
  if(auth) headers['Authorization'] = 'Bearer ' + auth;
  try {
    const r = await fetch(BASE + path, { ...opts, headers });
    const json = await r.json();
    return { ok: r.ok, status: r.status, data: json };
  } catch(e) {
    return { ok: false, error: e.message };
  }
}

// ── GLOSSARY ────────────────────────────────────────────────────────────────

async function loadGlossary() {
  const search = document.getElementById('g-search').value;
  const cat = document.getElementById('g-cat').value;
  const state = document.getElementById('g-state').value;
  let qs = [];
  if(search) qs.push('q=' + encodeURIComponent(search));
  if(cat) qs.push('category=' + encodeURIComponent(cat));
  const url = '/glossary' + (qs.length ? '?' + qs.join('&') : '');
  const res = await apiFetch(url);
  const list = document.getElementById('glossary-list');
  if(!res.ok) { list.innerHTML = '<div class="empty">Failed to load glossary</div>'; return; }
  const items = (res.data.glossary || res.data || []).filter(g => !state || g.state === state);
  if(!items.length) { list.innerHTML = '<div class="empty">No entries found</div>'; return; }
  list.innerHTML = items.map(g => renderGlossaryEntry(g)).join('');
  // Populate category filter
  const cats = [...new Set(items.map(g => g.category).filter(Boolean))];
  const catSel = document.getElementById('g-cat');
  const curVal = catSel.value;
  catSel.innerHTML = '<option value="">All Categories</option>' + cats.map(c => '<option value="' + c + '">' + c + '</option>').join('');
  catSel.value = curVal;
}

function renderGlossaryEntry(g) {
  return '<div class="card" id="gentry-' + g.hex + '">' +
    '<div class="row sb">' +
      '<div class="row" style="gap:8px"><b>' + esc(g.name) + '</b>' +
      (g.state ? '<span class="badge ' + g.state + '">' + g.state + '</span>' : '') +
      (g.category ? '<span class="badge grey">' + esc(g.category) + '</span>' : '') +
      (g.platform ? '<span class="meta">' + esc(g.platform) + '</span>' : '') +
      '</div>' +
      '<div class="row" style="gap:6px">' +
        '<button class="btn ghost" style="padding:4px 10px;font-size:.78rem" onclick="editGlossaryEntry(' + JSON.stringify(g).replace(/"/g, '&quot;') + ')">Edit</button>' +
        '<button class="btn danger" style="padding:4px 10px;font-size:.78rem" onclick="deleteGlossaryEntry('' + esc(g.hex || g.name) + '')">Delete</button>' +
      '</div>' +
    '</div>' +
    (g.description ? '<p style="margin-top:6px;font-size:.85rem;color:var(--muted)">' + esc(g.description) + '</p>' : '') +
    '<div class="row" style="margin-top:6px;gap:12px">' +
      (g.version ? '<span class="meta">v' + esc(g.version) + '</span>' : '') +
      (g.backend ? '<span class="meta">via ' + esc(g.backend) + '</span>' : '') +
      '<span class="hex">' + esc((g.hex||'').substring(0,16)) + '...</span>' +
    '</div>' +
  '</div>';
}

function openGlossaryAdd() {
  document.getElementById('gmodal-title').textContent = 'Add Glossary Entry';
  ['gf-name','gf-hex','gf-desc','gf-version','gf-backend','gf-notes','gf-cat'].forEach(id => document.getElementById(id).value = '');
  document.getElementById('gf-state').value = 'white';
  document.getElementById('gf-platform').value = '';
  document.getElementById('gf-editing-hex').value = '';
  document.getElementById('glossary-modal').style.display = 'flex';
}

function editGlossaryEntry(g) {
  document.getElementById('gmodal-title').textContent = 'Edit Glossary Entry';
  document.getElementById('gf-name').value = g.name || '';
  document.getElementById('gf-hex').value = g.hex || '';
  document.getElementById('gf-desc').value = g.description || '';
  document.getElementById('gf-state').value = g.state || 'white';
  document.getElementById('gf-platform').value = g.platform || '';
  document.getElementById('gf-version').value = g.version || '';
  document.getElementById('gf-backend').value = g.backend || '';
  document.getElementById('gf-notes').value = g.notes || '';
  document.getElementById('gf-cat').value = g.category || '';
  document.getElementById('gf-editing-hex').value = g.hex || g.name;
  document.getElementById('glossary-modal').style.display = 'flex';
}

function closeGlossaryModal() {
  document.getElementById('glossary-modal').style.display = 'none';
}

async function saveGlossaryEntry() {
  const editingHex = document.getElementById('gf-editing-hex').value;
  const body = {
    name: document.getElementById('gf-name').value.trim(),
    hex: document.getElementById('gf-hex').value.trim(),
    description: document.getElementById('gf-desc').value.trim(),
    state: document.getElementById('gf-state').value,
    platform: document.getElementById('gf-platform').value,
    version: document.getElementById('gf-version').value.trim(),
    backend: document.getElementById('gf-backend').value.trim(),
    notes: document.getElementById('gf-notes').value.trim(),
    category: document.getElementById('gf-cat').value.trim(),
  };
  if(!body.name) { toast('Name is required', 'err'); return; }
  let res;
  if(editingHex) {
    res = await apiFetch('/glossary/' + editingHex, { method: 'PUT', body: JSON.stringify(body) });
  } else {
    res = await apiFetch('/glossary', { method: 'POST', body: JSON.stringify(body) });
  }
  if(res.ok) { toast(editingHex ? 'Entry updated' : 'Entry added'); closeGlossaryModal(); loadGlossary(); }
  else toast('Error: ' + (res.data?.error || 'unknown'), 'err');
}

async function deleteGlossaryEntry(hexOrName) {
  if(!confirm('Delete entry ' + hexOrName + '?')) return;
  if(!getAuth()) { toast('Auth token required to delete', 'err'); return; }
  const res = await apiFetch('/glossary/' + hexOrName, { method: 'DELETE' });
  if(res.ok) { toast('Entry deleted'); loadGlossary(); }
  else toast('Error: ' + (res.data?.error || 'unauthorized'), 'err');
}

// ── REVIEW QUEUE ─────────────────────────────────────────────────────────────

async function loadReviews() {
  const status = document.getElementById('r-status').value;
  const url = '/review' + (status ? '?status=' + status : '');
  const res = await apiFetch(url);
  const list = document.getElementById('review-list');
  if(!res.ok) { list.innerHTML = '<div class="empty">Failed to load submissions</div>'; return; }
  const items = res.data.submissions || res.data || [];
  if(!items.length) { list.innerHTML = '<div class="empty">No submissions found</div>'; return; }
  list.innerHTML = items.map(s => renderSubmission(s)).join('');
}

function renderSubmission(s) {
  return '<div class="card" id="sub-' + s.hex + '">' +
    '<div class="row sb">' +
      '<div><b>' + esc(s.name) + '</b> <span class="badge ' + s.status + '">' + s.status + '</span></div>' +
      '<span class="meta">' + (s.submitted_at||'').substring(0,10) + '</span>' +
    '</div>' +
    (s.description ? '<p class="meta" style="margin-top:4px">' + esc(s.description) + '</p>' : '') +
    '<div class="row" style="margin-top:6px;gap:10px">' +
      (s.category ? '<span class="meta">&#128193; ' + esc(s.category) + '</span>' : '') +
      (s.platform ? '<span class="meta">&#x1F4BB; ' + esc(s.platform) + '</span>' : '') +
      '<span class="hex">' + esc((s.hex||'').substring(0,20)) + '...</span>' +
    '</div>' +
    '<div class="vote-row">' +
      '<button class="btn success" style="padding:5px 12px;font-size:.8rem" onclick="castVote('' + esc(s.hex) + '','approve')">&#10003; Approve</button>' +
      '<button class="btn danger" style="padding:5px 12px;font-size:.8rem" onclick="castVote('' + esc(s.hex) + '','reject')">&#10007; Reject</button>' +
      '<button class="btn ghost" style="padding:5px 12px;font-size:.8rem" onclick="castVote('' + esc(s.hex) + '','abstain')">&#x25CB; Abstain</button>' +
      '<button class="btn ghost" style="padding:5px 12px;font-size:.8rem" onclick="loadVotes('' + esc(s.hex) + '')">View Votes</button>' +
      (s.status === 'approved' ? '<button class="btn warn" style="padding:5px 12px;font-size:.8rem" onclick="revokeArtifact('' + esc(s.hex) + '')">Revoke</button>' : '') +
    '</div>' +
    '<div id="votes-' + s.hex + '" style="margin-top:8px"></div>' +
  '</div>';
}

async function castVote(hex, vote) {
  if(!getAuth()) { toast('Auth token required to vote', 'err'); return; }
  const reviewer = prompt('Your reviewer handle:', 'anonymous');
  if(reviewer === null) return;
  const notes = prompt('Notes (optional):', '');
  const res = await apiFetch('/review/' + hex + '/vote', {
    method: 'POST',
    body: JSON.stringify({ vote, reviewer: reviewer||'anonymous', notes: notes||'' })
  });
  if(res.ok) { toast('Vote cast: ' + vote + ' — ' + (res.data.status||'')); loadReviews(); }
  else toast('Error: ' + (res.data?.error || 'unknown'), 'err');
}

async function loadVotes(hex) {
  const el = document.getElementById('votes-' + hex);
  const res = await apiFetch('/review/' + hex + '/votes');
  if(!res.ok) { el.innerHTML = '<span class="meta">Failed to load votes</span>'; return; }
  const votes = res.data.votes || [];
  if(!votes.length) { el.innerHTML = '<span class="meta">No votes yet</span>'; return; }
  el.innerHTML = '<hr><div class="meta" style="margin-bottom:4px">Votes:</div>' +
    votes.map(v => '<span class="badge ' + (v.vote==='approve'?'approved':v.vote==='reject'?'rejected':'pending') + '" style="margin-right:4px">' + esc(v.vote) + ' — ' + esc(v.reviewer) + (v.notes?' ('+esc(v.notes)+')':'') + '</span>').join(' ');
}

async function revokeArtifact(hex) {
  if(!getAuth()) { toast('Auth token required', 'err'); return; }
  const reason = prompt('Revocation reason:');
  if(!reason) return;
  const res = await apiFetch('/review/' + hex + '/revoke', {
    method: 'POST', body: JSON.stringify({ reason, revoked_by: 'admin' })
  });
  if(res.ok) { toast('Artifact revoked'); loadReviews(); }
  else toast('Error: ' + (res.data?.error || 'unknown'), 'err');
}

// ── SUBMIT ───────────────────────────────────────────────────────────────────

async function submitArtifact() {
  if(!getAuth()) { toast('Auth token required to submit', 'err'); return; }
  const body = {
    name: document.getElementById('sf-name').value.trim(),
    hex: document.getElementById('sf-hex').value.trim(),
    description: document.getElementById('sf-desc').value.trim(),
    category: document.getElementById('sf-cat').value.trim(),
    platform: document.getElementById('sf-platform').value,
    submitter: document.getElementById('sf-submitter').value.trim()||'anonymous',
    artifact_url: document.getElementById('sf-url').value.trim()||null,
  };
  if(!body.name||!body.hex) { toast('Name and hex are required', 'err'); return; }
  const res = await apiFetch('/review', { method: 'POST', body: JSON.stringify(body) });
  if(res.ok) {
    toast('Submitted for review!');
    ['sf-name','sf-hex','sf-desc','sf-cat','sf-submitter','sf-url'].forEach(id => document.getElementById(id).value='');
  } else toast('Error: ' + (res.data?.error || 'unknown'), 'err');
}

// ── FEED ─────────────────────────────────────────────────────────────────────

async function loadFeed() {
  const cat = document.getElementById('feed-cat').value;
  const platform = document.getElementById('feed-platform').value;
  let qs = [];
  if(cat) qs.push('category=' + encodeURIComponent(cat));
  if(platform) qs.push('platform=' + encodeURIComponent(platform));
  const url = '/feed' + (qs.length ? '?' + qs.join('&') : '');
  const res = await apiFetch(url);
  const list = document.getElementById('feed-list');
  if(!res.ok) { list.innerHTML = '<div class="empty">Failed to load feed</div>'; return; }
  const items = res.data.feed || res.data || [];
  if(!items.length) { list.innerHTML = '<div class="empty">No approved artifacts in the feed yet</div>'; return; }
  list.innerHTML = items.map(f => '<div class="card">' +
    '<div class="row sb">' +
      '<div><b>' + esc(f.name) + '</b>' +
      (f.revoked ? '<span class="badge black" style="margin-left:6px">revoked</span>' : '<span class="badge white" style="margin-left:6px">available</span>') +
      (f.category ? '<span class="badge grey" style="margin-left:6px">' + esc(f.category) + '</span>' : '') +
      '</div>' +
      '<span class="meta">' + (f.advertised_at||'').substring(0,10) + '</span>' +
    '</div>' +
    (f.description ? '<p class="meta" style="margin-top:4px">' + esc(f.description) + '</p>' : '') +
    '<div class="row" style="margin-top:6px;gap:10px">' +
      '<span class="meta">&#10003; ' + (f.approvals||0) + ' approvals</span>' +
      (f.platform ? '<span class="meta">&#x1F4BB; ' + esc(f.platform) + '</span>' : '') +
      '<span class="hex">' + esc((f.hex||'').substring(0,20)) + '...</span>' +
    '</div>' +
    (f.artifact_url ? '<div style="margin-top:8px"><a href="' + esc(f.artifact_url) + '" target="_blank" rel="noopener" style="color:var(--accent2);font-size:.82rem">Opt-in pull link &rarr;</a></div>' : '') +
  '</div>').join('');
  // Populate category filter from feed items
  const cats = [...new Set(items.map(i => i.category).filter(Boolean))];
  const catSel = document.getElementById('feed-cat');
  catSel.innerHTML = '<option value="">All Categories</option>' + cats.map(c => '<option>' + esc(c) + '</option>').join('');
}

// ── VERIFY ───────────────────────────────────────────────────────────────────

async function verifyArtifact() {
  const hex = document.getElementById('v-hex').value.trim();
  if(!hex) { toast('Enter a hex hash', 'err'); return; }
  const res = await apiFetch('/verify/' + hex);
  const el = document.getElementById('verify-result');
  if(!res.ok && res.status !== 200) { el.innerHTML = '<div class="card"><span class="badge rejected">Error loading</span></div>'; return; }
  const d = res.data;
  const statusColor = d.verified ? 'approved' : (d.status === 'revoked' ? 'black' : d.status === 'pending' ? 'pending' : 'rejected');
  el.innerHTML = '<div class="card">' +
    '<div class="row" style="gap:10px;margin-bottom:8px">' +
      '<span class="badge ' + statusColor + '" style="font-size:.9rem;padding:4px 12px">' + (d.status||'unknown') + '</span>' +
      (d.verified ? '<span style="color:var(--green)">&#10003; Verified</span>' : '<span style="color:var(--red)">&#10007; Not Verified</span>') +
    '</div>' +
    (d.name ? '<div><b>' + esc(d.name) + '</b></div>' : '') +
    (d.description ? '<p class="meta" style="margin-top:4px">' + esc(d.description) + '</p>' : '') +
    '<div class="row" style="margin-top:8px;gap:12px">' +
      (d.reviewed_at ? '<span class="meta">Reviewed: ' + esc(d.reviewed_at.substring(0,10)) + '</span>' : '') +
      (d.revoked_by ? '<span class="meta">Revoked by: ' + esc(d.revoked_by) + '</span>' : '') +
      (d.reason ? '<span class="meta">Reason: ' + esc(d.reason) + '</span>' : '') +
    '</div>' +
    '<div class="hex" style="margin-top:8px">' + esc(hex) + '</div>' +
  '</div>';
}

// ── HELPERS ──────────────────────────────────────────────────────────────────
function esc(s) {
  if(s == null) return '';
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// Auto-load on start
loadGlossary();
</script>
</body>
</html>`;


// ── Router ───────────────────────────────────────────────────────────────────
export default {
  async fetch(req, env) {

    if (req.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: HEADERS });
    }

    const url = new URL(req.url);
    const path = url.pathname.replace(/\/$/, '') || '/';
    const db = env.PHOENIX_DB;

    try {

      // ── Health ──────────────────────────────────────────────────────────────
      // ── Platform UI (GET /platform or browser request to /)
      if (path === '/platform' || (path === '/' && (req.headers.get('Accept')||'').includes('text/html'))) {
        return new Response(HTML_PLATFORM, { status: 200, headers: { 'Content-Type': 'text/html;charset=UTF-8', 'Access-Control-Allow-Origin': '*' } });
      }

      // ── Health (GET / or GET /health — API clients) ──────────────────────────
      if (path === '/' || path === '/health') {
        const tables = await db
          .prepare("SELECT count(*) as n FROM sqlite_master WHERE type='table'")
          .first();
        return ok({
          status: 'ok',
          worker: 'packages-worker',
          version: '3.4.0',
          brand: 'USys — United Systems',
          db: 'phoenix_dev_db',
          tables: tables.n,
          platform_ui: '/platform',
        });
      }

      // ══════════════════════════════════════════════════════════════════════
      // INTAKE ENDPOINTS — called by intake.sh after every operation
      // All writes require auth
      // ══════════════════════════════════════════════════════════════════════

      // POST /clonepool — intake.sh reports a new file into the pool
      if (path === '/clonepool' && req.method === 'POST') {
        if (!isAuthorized(req, env)) return err('unauthorized', 401);
        const body = await req.json();
        if (!body.hex_id || !body.name) return err('hex_id and name required');

        await db.prepare(`
          INSERT INTO clonepool (hex_id, b58, name, original_name, pool_path, sidecar_path,
            state, tier, size, version)
          VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
          ON CONFLICT(hex_id) DO UPDATE SET
            state = excluded.state,
            version = excluded.version,
            updated_at = CURRENT_TIMESTAMP
        `).bind(
          body.hex_id,
          body.b58 || body.hex_id,
          body.name,
          body.original_name|| body.name,
          body.pool_path || null,
          body.sidecar_path || null,
          body.state || 'white',
          body.tier || 1,
          body.size || 0,
          body.version || 'v1',
        ).run();

        return ok({ ok: true, hex_id: body.hex_id, name: body.name });
      }

      // GET /custody — ledger view
      if (path === '/custody' && req.method === 'GET') {
        const hex = url.searchParams.get('hex');
        const limit = parseInt(url.searchParams.get('limit') || '50', 10);
        const params = [];
        let query = 'SELECT * FROM custody';

        if (hex) { query += ' WHERE hex_id = ?'; params.push(hex); }
        query += ' ORDER BY intaked_at DESC LIMIT ?';
        params.push(limit);

        const result = await db.prepare(query).bind(...params).all();
        return ok({ custody: result.results, count: result.results.length });
      }

      // POST /custody — intake.sh reports a custody receipt (append only)
      if (path === '/custody' && req.method === 'POST') {
        if (!isAuthorized(req, env)) return err('unauthorized', 401);
        const body = await req.json();
        if (!body.hex_id || !body.name) return err('hex_id and name required');

        await db.prepare(`
          INSERT INTO custody (hex_id, name, qr_top, qr_bottom, state, action, actor, validated)
          VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        `).bind(
          body.hex_id,
          body.name,
          body.qr_top || null,
          body.qr_bottom|| null,
          body.state || 'white',
          body.action || 'intake',
          body.actor || 'usys',
          body.validated|| 0,
        ).run();

        return ok({ ok: true, hex_id: body.hex_id, action: body.action });
      }

      // ══════════════════════════════════════════════════════════════════════
      // CLONEPOOL
      // columns: id, hex_id, b58, name, original_name, pool_path, sidecar_path,
      //          header_qr, footer_qr, hash_sha3, hash_blake2, sha3_fp, blake2_fp,
      //          state, tier, size, version, source_path, intaked_at, updated_at,
      //          qr_valid, notes
      // ══════════════════════════════════════════════════════════════════════

      if (path === '/clonepool' && req.method === 'GET') {
        const state = url.searchParams.get('state');
        const limit = parseInt(url.searchParams.get('limit') || '100', 10);
        const params = [];
        let query = 'SELECT * FROM clonepool';

        if (state) { query += ' WHERE state = ?'; params.push(state); }
        query += ' ORDER BY intaked_at DESC LIMIT ?';
        params.push(limit);

        const result = await db.prepare(query).bind(...params).all();
        return ok({ clonepool: result.results, count: result.results.length, filter: state || 'all' });
      }

      if (path.startsWith('/clonepool/') && req.method === 'GET') {
        const id = decodeURIComponent(path.slice(11));
        const row = await db
          .prepare('SELECT * FROM clonepool WHERE hex_id = ? OR name = ?')
          .bind(id, id).first();
        return row ? ok(row) : err('not found', 404);
      }
      // DELETE /clonepool/:id — remove entry by hex_id or name (auth required)
      if (path.startsWith('/clonepool/') && req.method === 'DELETE') {
        if (!isAuthorized(req, env)) return err('unauthorized', 401);
        const id = decodeURIComponent(path.slice(11));
        if (!id) return err('id required', 400);
        const existing = await db.prepare('SELECT id FROM clonepool WHERE hex_id = ? OR name = ?').bind(id, id).first();
        if (!existing) return err('not found', 404);
        await db.prepare('DELETE FROM clonepool WHERE hex_id = ? OR name = ?').bind(id, id).run();
        return ok({ ok: true, deleted: id });
      }


      // ══════════════════════════════════════════════════════════════════════
      // PACKAGES
      // ══════════════════════════════════════════════════════════════════════

      if (path === '/packages' && req.method === 'GET') {
        const limit = parseInt(url.searchParams.get('limit') || '100', 10);
        const result = await db
          .prepare('SELECT * FROM packages ORDER BY name LIMIT ?')
          .bind(limit).all();
        return ok({ packages: result.results, count: result.results.length });
      }

      if (path.startsWith('/packages/') && req.method === 'GET') {
        const id = decodeURIComponent(path.slice(10));
        const row = await db
          .prepare('SELECT * FROM packages WHERE name = ? OR id = ?')
          .bind(id, id).first();
        return row ? ok(row) : err('not found', 404);
      }

      // ══════════════════════════════════════════════════════════════════════
      // GLOSSARY
      // columns: id, hex, b58, name, category_hex, description, state,
      //          version, platform, backend, size, pool_path, sidecar,
      //          amended, intaked_at, grace_until, evicted_at, notes
      // JOIN: categories on categories.hex = glossary.category_hex
      // ══════════════════════════════════════════════════════════════════════

      if (path === '/glossary' && req.method === 'GET') {
        const search = url.searchParams.get('q');
        const cat = url.searchParams.get('category');
        const params = [];
        const conditions = [];
        let query = 'SELECT * FROM glossary g';

        if (search) { conditions.push('g.name LIKE ?'); params.push(`%${search}%`); }
        if (cat) { conditions.push('c.name = ?'); params.push(cat); }
        if (conditions.length) query += ' WHERE ' + conditions.join(' AND ');
        query += ' ORDER BY g.name';

        const result = await db.prepare(query).bind(...params).all();
        return ok({ glossary: result.results, count: result.results.length });
      }

      if (path === '/glossary' && req.method === 'POST') {
        if (!isAuthorized(req, env)) return err('unauthorized', 401);
        const body = await req.json();
        if (!body.hex || !body.name) return err('hex and name required');

        await db.prepare(`
          INSERT INTO glossary (hex, b58, name, category_hex, description, state, version, platform, backend, size, pool_path, sidecar, notes)
          VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
          ON CONFLICT(hex) DO UPDATE SET
            name = excluded.name,
            description = excluded.description,
            category_hex = excluded.category_hex,
            state = excluded.state,
            amended = 1
        `).bind(
          body.hex,
          body.b58 || null,
          body.name,
          body.category_hex|| null,
          body.description || '',
          body.state || 'white',
          body.version || null,
          body.platform || null,
          body.backend || null,
          body.size || null,
          body.pool_path || null,
          body.sidecar || null,
          body.notes || null,
        ).run();

        return ok({ ok: true, hex: body.hex, name: body.name });
      }

      if (path.startsWith('/glossary/') && req.method === 'GET') {
        const id = decodeURIComponent(path.slice(10));
        const row = await db
          .prepare('SELECT * FROM glossary g WHERE g.hex = ? OR g.name = ?')
          .bind(id, id).first();
        return row ? ok(row) : err('not found', 404);
      }

      if (path.startsWith('/glossary/') && req.method === 'PUT') {
        if (!isAuthorized(req, env)) return err('unauthorized', 401);
        const id = decodeURIComponent(path.slice(10));
        const body = await req.json();

        await db.prepare(`
          UPDATE glossary SET
            description = COALESCE(?, description),
            category_hex = COALESCE(?, category_hex),
            state = COALESCE(?, state),
            notes = COALESCE(?, notes),
            amended = 1
          WHERE hex = ? OR name = ?
        `).bind(
          body.description ?? null,
          body.category_hex ?? null,
          body.state ?? null,
          body.notes ?? null,
          id, id,
        ).run();

        return ok({ ok: true, updated: id });
      }

      if (path.startsWith('/glossary/') && req.method === 'DELETE') {
        if (!isAuthorized(req, env)) return err('unauthorized', 401);
        const id = decodeURIComponent(path.slice(10));
        await db.prepare('DELETE FROM glossary WHERE hex = ? OR name = ?').bind(id, id).run();
        return ok({ ok: true, deleted: id });
      }

      // ══════════════════════════════════════════════════════════════════════
      // CATEGORIES
      // columns: hex, name, description
      // ══════════════════════════════════════════════════════════════════════

      if (path === '/categories' && req.method === 'GET') {
        const result = await db.prepare('SELECT * FROM categories ORDER BY name').all();
        return ok({ categories: result.results, count: result.results.length });
      }

      // ══════════════════════════════════════════════════════════════════════
      // TOC — live table of contents
      // toc columns: id, title, parent_id, position, description, layer
      // toc_entries columns: id, toc_id, package_id, position
      // ══════════════════════════════════════════════════════════════════════

      if (path === '/toc' && req.method === 'GET') {
        const [toc, entries, poolSummary] = await Promise.all([
          db.prepare('SELECT * FROM toc ORDER BY position, title').all(),
          db.prepare('SELECT * FROM toc_entries ORDER BY toc_id, position').all(),
          db.prepare('SELECT state, COUNT(*) as n FROM clonepool GROUP BY state').all(),
        ]);

        const entryMap = {};
        for (const e of entries.results) {
          if (!entryMap[e.toc_id]) entryMap[e.toc_id] = [];
          entryMap[e.toc_id].push(e);
        }

        const tocFull = toc.results.map(t => ({
          ...t,
          entries: entryMap[t.id] || [],
        }));

        return ok({
          toc: tocFull,
          total: tocFull.length,
          pool_summary: poolSummary.results,
          generated_at: new Date().toISOString(),
        });
      }

      // ══════════════════════════════════════════════════════════════════════
      // VERSIONS
      // ══════════════════════════════════════════════════════════════════════

      if (path === '/versions' && req.method === 'GET') {
        const pkg = url.searchParams.get('package');
        const limit = parseInt(url.searchParams.get('limit') || '50', 10);
        const params = [];
        let query = 'SELECT * FROM versions';

        if (pkg) { query += ' WHERE package_name = ?'; params.push(pkg); }
        query += ' ORDER BY created_at DESC LIMIT ?';
        params.push(limit);

        const result = await db.prepare(query).bind(...params).all();
        return ok({ versions: result.results, count: result.results.length });
      }

      // ══════════════════════════════════════════════════════════════════════
      // SEARCH — clonepool + glossary + packages
      // ══════════════════════════════════════════════════════════════════════

      if (path === '/search' && req.method === 'GET') {
        const q = url.searchParams.get('q');
        if (!q) return err('q required');
        const term = `%${q}%`;

        const [pool, gloss, pkgs] = await Promise.all([
          db.prepare('SELECT hex_id, name, state, tier FROM clonepool WHERE name LIKE ? OR hex_id LIKE ? LIMIT 20').bind(term, term).all(),
          db.prepare('SELECT hex, name, description, category_hex FROM glossary WHERE name LIKE ? OR description LIKE ? LIMIT 20').bind(term, term).all(),
          db.prepare('SELECT name, version, description FROM packages WHERE name LIKE ? OR description LIKE ? LIMIT 20').bind(term, term).all(),
        ]);

        return ok({
          query: q,
          clonepool: pool.results,
          glossary: gloss.results,
          packages: pkgs.results,
          total: pool.results.length + gloss.results.length + pkgs.results.length,
        });
      }

      // ══════════════════════════════════════════════════════════════════════
      // PEER REVIEW — opt-in distribution + review + hex + QR verification
      // Tables: submissions, reviews, revocations, advertisement_feed
      // Principle: the hex is the identity. Review attaches judgment, not content.
      // Nothing is pushed. Availability is advertised. Users pull only what they choose.
      // ══════════════════════════════════════════════════════════════════════

      // GET /review — list all submissions (filter by ?status=pending|approved|rejected)
      if (path === '/review' && req.method === 'GET') {
        const status = url.searchParams.get('status');
        const limit = parseInt(url.searchParams.get('limit') || '50', 10);
        const params = [];
        let query = 'SELECT * FROM submissions';

        if (status) { query += ' WHERE status = ?'; params.push(status); }
        query += ' ORDER BY submitted_at DESC LIMIT ?';
        params.push(limit);

        const result = await db.prepare(query).bind(...params).all();
        return ok({ submissions: result.results, count: result.results.length, filter: status || 'all' });
      }

      // GET /review/:hex — fetch review record for a specific artifact
      if (path.startsWith('/review/') && !path.includes('/vote') && !path.includes('/revoke') && req.method === 'GET') {
        const hex = decodeURIComponent(path.slice(8));
        const [submission, reviewVotes] = await Promise.all([
          db.prepare('SELECT * FROM submissions WHERE hex = ?').bind(hex).first(),
          db.prepare('SELECT * FROM reviews WHERE submission_hex = ? ORDER BY voted_at DESC').bind(hex).all(),
        ]);
        if (!submission) return err('not found', 404);
        return ok({ submission, reviews: reviewVotes.results, vote_count: reviewVotes.results.length });
      }

      // POST /review — submit an artifact for community review (auth required)
      if (path === '/review' && req.method === 'POST') {
        if (!isAuthorized(req, env)) return err('unauthorized', 401);
        const body = await req.json();
        if (!body.hex || !body.name) return err('hex and name required');

        await db.prepare(`
          INSERT INTO submissions (hex, name, description, category, platform, submitter, artifact_url, status)
          VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')
          ON CONFLICT(hex) DO UPDATE SET
            name = excluded.name,
            description = excluded.description,
            status = 'pending',
            submitted_at = CURRENT_TIMESTAMP
        `).bind(
          body.hex,
          body.name,
          body.description || '',
          body.category || null,
          body.platform || null,
          body.submitter || 'anonymous',
          body.artifact_url || null,
        ).run();

        return ok({ ok: true, hex: body.hex, name: body.name, status: 'pending' });
      }

      // POST /review/:hex/vote — cast a vote (approve / reject / abstain) (auth required)
      if (path.match(/^\/review\/[^\/]+\/vote$/) && req.method === 'POST') {
        if (!isAuthorized(req, env)) return err('unauthorized', 401);
        const hex = decodeURIComponent(path.slice(8, path.lastIndexOf('/vote')));
        const body = await req.json();
        if (!body.vote || !['approve', 'reject', 'abstain'].includes(body.vote)) {
          return err('vote must be approve, reject, or abstain');
        }

        await db.prepare(`
          INSERT INTO reviews (submission_hex, reviewer, vote, notes)
          VALUES (?, ?, ?, ?)
        `).bind(
          hex,
          body.reviewer || 'anonymous',
          body.vote,
          body.notes || null,
        ).run();

        // Tally votes — auto-approve if approvals >= threshold (default 2)
        const threshold = 2;
        const tally = await db.prepare(
          "SELECT vote, COUNT(*) as n FROM reviews WHERE submission_hex = ? GROUP BY vote"
        ).bind(hex).all();

        const counts = {};
        for (const row of tally.results) counts[row.vote] = row.n;
        const approvals = counts['approve'] || 0;
        const rejections = counts['reject'] || 0;

        let newStatus = null;
        if (approvals >= threshold) newStatus = 'approved';
        else if (rejections >= threshold) newStatus = 'rejected';

        if (newStatus) {
          await db.prepare("UPDATE submissions SET status = ? WHERE hex = ?").bind(newStatus, hex).run();

          // If approved, register in the advertisement feed
          if (newStatus === 'approved') {
            const sub = await db.prepare('SELECT * FROM submissions WHERE hex = ?').bind(hex).first();
            if (sub) {
              await db.prepare(`
                INSERT INTO advertisement_feed (hex, name, description, category, platform, approvals, artifact_url)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(hex) DO UPDATE SET
                  approvals = excluded.approvals,
                  advertised_at = CURRENT_TIMESTAMP
              `).bind(
                hex,
                sub.name,
                sub.description || '',
                sub.category || null,
                sub.platform || null,
                approvals,
                sub.artifact_url || null,
              ).run();
            }
          }
        }

        return ok({ ok: true, hex, vote: body.vote, approvals, rejections, status: newStatus || 'pending' });
      }

      // GET /review/:hex/votes — view all votes on a submission
      if (path.match(/^\/review\/[^\/]+\/votes$/) && req.method === 'GET') {
        const hex = decodeURIComponent(path.slice(8, path.lastIndexOf('/votes')));
        const result = await db.prepare(
          'SELECT * FROM reviews WHERE submission_hex = ? ORDER BY voted_at DESC'
        ).bind(hex).all();
        const tally = await db.prepare(
          "SELECT vote, COUNT(*) as n FROM reviews WHERE submission_hex = ? GROUP BY vote"
        ).bind(hex).all();
        const counts = {};
        for (const row of tally.results) counts[row.vote] = row.n;
        return ok({ hex, votes: result.results, tally: counts, total: result.results.length });
      }

      // POST /review/:hex/revoke — revoke an approved artifact (auth required)
      if (path.match(/^\/review\/[^\/]+\/revoke$/) && req.method === 'POST') {
        if (!isAuthorized(req, env)) return err('unauthorized', 401);
        const hex = decodeURIComponent(path.slice(8, path.lastIndexOf('/revoke')));
        const body = await req.json();

        // Identity == hash. Old artifact remains addressable. Only status changes.
        await db.prepare("UPDATE submissions SET status = 'revoked' WHERE hex = ?").bind(hex).run();

        await db.prepare(`
          INSERT INTO revocations (hex, reason, revoked_by, superseded_by)
          VALUES (?, ?, ?, ?)
        `).bind(
          hex,
          body.reason || 'no reason provided',
          body.revoked_by || 'admin',
          body.superseded_by || null,
        ).run();

        // Mark as revoked in the feed (don't delete — revocation is public record)
        await db.prepare(
          "UPDATE advertisement_feed SET revoked = 1, revoked_at = CURRENT_TIMESTAMP WHERE hex = ?"
        ).bind(hex).run();

        return ok({ ok: true, hex, status: 'revoked', reason: body.reason || 'no reason provided' });
      }

      // GET /verify/:hex — verify an artifact — returns status + review provenance
      if (path.startsWith('/verify/') && req.method === 'GET') {
        const hex = decodeURIComponent(path.slice(8));
        const [submission, revocation, feedEntry] = await Promise.all([
          db.prepare('SELECT hex, name, status, submitted_at FROM submissions WHERE hex = ?').bind(hex).first(),
          db.prepare('SELECT * FROM revocations WHERE hex = ?').bind(hex).first(),
          db.prepare('SELECT * FROM advertisement_feed WHERE hex = ?').bind(hex).first(),
        ]);

        if (!submission) {
          return ok({ hex, status: 'unknown', verified: false });
        }

        if (revocation) {
          return ok({
            hex,
            status: 'revoked',
            verified: false,
            name: submission.name,
            revocation: {
              reason: revocation.reason,
              revoked_by: revocation.revoked_by,
              revoked_at: revocation.revoked_at,
              superseded_by: revocation.superseded_by || null,
            },
          });
        }

        if (submission.status === 'approved') {
          return ok({
            hex,
            status: 'verified',
            verified: true,
            name: submission.name,
            submitted_at: submission.submitted_at,
            in_feed: feedEntry ? true : false,
          });
        }

        return ok({ hex, status: submission.status, verified: false, name: submission.name });
      }

      // GET /feed — opt-in availability feed of approved artifacts
      if (path === '/feed' && req.method === 'GET') {
        const category = url.searchParams.get('category');
        const platform = url.searchParams.get('platform');
        const limit = parseInt(url.searchParams.get('limit') || '50', 10);
        const params = [];
        const conditions = ['revoked = 0'];
        let query = 'SELECT * FROM advertisement_feed';

        if (category) { conditions.push('category = ?'); params.push(category); }
        if (platform) { conditions.push('platform = ?'); params.push(platform); }
        query += ' WHERE ' + conditions.join(' AND ');
        query += ' ORDER BY advertised_at DESC LIMIT ?';
        params.push(limit);

        const result = await db.prepare(query).bind(...params).all();
        return ok({
          feed: result.results,
          count: result.results.length,
          note: 'Availability advertised. Nothing is pushed. Pull only what you choose.',
        });
      }

      // ── 404 ───────────────────────────────────────────────────────────────
      return err('not found', 404);

    } catch (e) {
      return ok({ error: e.message, worker: 'packages-worker', db: 'phoenix_dev_db' }, 500);
    }
  },
};
