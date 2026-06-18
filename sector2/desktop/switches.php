<?php
/**
 * switches.php — Phoenix Switches & Controls
 * Wired toggles, dropdowns, and action buttons.
 * Phoenix DevOps OS | jwl247 | GPL v3
 */
?><!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Phoenix Switches</title>
<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
:root {
  --bg:      #07090c;
  --panel:   #0d1117;
  --card:    #111820;
  --border:  #1e2a38;
  --accent:  #00ff88;
  --red:     #ff3b5c;
  --amber:   #ffaa00;
  --blue:    #00aaff;
  --purple:  #9b59ff;
  --muted:   #556677;
  --text:    #c8d8e8;
  --font:    'Courier New', Courier, monospace;
}
body { background: var(--bg); color: var(--text); font-family: var(--font);
       min-height: 100vh; display: flex; flex-direction: column; }

/* ── Header ──────────────────────────────────────────────────────────────── */
#hdr { background: var(--panel); border-bottom: 1px solid var(--border);
       padding: 10px 20px; display: flex; align-items: center; gap: 12px; flex-shrink: 0; }
#hdr .brand { font-size: 11px; letter-spacing: 3px; color: var(--accent); text-transform: uppercase; }
#save-status { margin-left: auto; font-size: 9px; color: var(--muted); letter-spacing: 1px; }

/* ── Layout ──────────────────────────────────────────────────────────────── */
#content { flex: 1; padding: 16px; display: grid;
           grid-template-columns: 1fr 1fr 1fr; gap: 14px; align-content: start; }
@media (max-width: 900px) { #content { grid-template-columns: 1fr 1fr; } }
@media (max-width: 580px) { #content { grid-template-columns: 1fr; } }

/* ── Card ────────────────────────────────────────────────────────────────── */
.card { background: var(--card); border: 1px solid var(--border); border-radius: 6px;
        padding: 14px 16px; display: flex; flex-direction: column; gap: 10px; }
.card-title { font-size: 9px; letter-spacing: 3px; text-transform: uppercase;
              color: var(--muted); border-bottom: 1px solid var(--border); padding-bottom: 8px; }
.card-title.ai       { color: var(--purple); }
.card-title.security { color: var(--red); }
.card-title.docs     { color: var(--amber); }
.card-title.core     { color: var(--accent); }
.card-title.actions  { color: var(--blue); }

/* ── Switch row ──────────────────────────────────────────────────────────── */
.sw-row { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.sw-label { font-size: 10px; color: var(--text); letter-spacing: 0.5px; }
.sw-label .sw-desc { display: block; font-size: 8px; color: var(--muted); margin-top: 2px; }

/* Toggle */
.toggle { position: relative; width: 44px; height: 22px; flex-shrink: 0; }
.toggle input { opacity: 0; width: 0; height: 0; }
.toggle-track {
  position: absolute; inset: 0;
  background: #1a2530; border: 1px solid var(--border); border-radius: 11px;
  cursor: pointer; transition: background 0.25s, border-color 0.25s;
}
.toggle-track::after {
  content: ''; position: absolute; left: 3px; top: 3px;
  width: 14px; height: 14px; border-radius: 50%;
  background: var(--muted); transition: left 0.25s, background 0.25s;
}
.toggle input:checked + .toggle-track { background: #003322; border-color: var(--accent); }
.toggle input:checked + .toggle-track::after { left: 25px; background: var(--accent);
  box-shadow: 0 0 6px var(--accent); }
.toggle.red input:checked + .toggle-track { background: #220010; border-color: var(--red); }
.toggle.red input:checked + .toggle-track::after { background: var(--red); box-shadow: 0 0 6px var(--red); }
.toggle.amber input:checked + .toggle-track { background: #1a1100; border-color: var(--amber); }
.toggle.amber input:checked + .toggle-track::after { background: var(--amber); box-shadow: 0 0 6px var(--amber); }

/* ── Dropdown ────────────────────────────────────────────────────────────── */
.dd-row { display: flex; flex-direction: column; gap: 5px; }
.dd-label { font-size: 9px; letter-spacing: 1px; color: var(--muted); text-transform: uppercase; }
select.phoenix-select {
  width: 100%; padding: 6px 10px; border-radius: 4px;
  background: #0a1018; border: 1px solid var(--border); color: var(--text);
  font-family: var(--font); font-size: 10px; letter-spacing: 1px;
  cursor: pointer; appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%23556677'/%3E%3C/svg%3E");
  background-repeat: no-repeat; background-position: right 10px center;
  transition: border-color 0.2s;
}
select.phoenix-select:focus { outline: none; border-color: var(--accent); }
select.phoenix-select option { background: #0d1117; }

/* ── Action buttons ──────────────────────────────────────────────────────── */
.action-btn {
  width: 100%; padding: 8px 12px; border-radius: 4px;
  border: 1px solid var(--border); background: #0a1018;
  color: var(--muted); font-family: var(--font); font-size: 9px;
  letter-spacing: 1.5px; text-transform: uppercase; cursor: pointer;
  text-align: left; transition: all 0.15s; display: flex; align-items: center; gap: 8px;
}
.action-btn:hover { border-color: var(--text); color: var(--text); }
.action-btn.blue:hover  { border-color: var(--blue);   color: var(--blue); }
.action-btn.red:hover   { border-color: var(--red);    color: var(--red); }
.action-btn.amber:hover { border-color: var(--amber);  color: var(--amber); }
.action-btn.green:hover { border-color: var(--accent); color: var(--accent); }
.action-btn .btn-icon { width: 16px; text-align: center; flex-shrink: 0; }
.action-btn.running { opacity: 0.6; cursor: wait; }
.action-btn.done { border-color: var(--accent); color: var(--accent); }
.action-btn.fail { border-color: var(--red); color: var(--red); }

/* ── Output area ─────────────────────────────────────────────────────────── */
#output-card { grid-column: 1 / -1; }
#output-box {
  background: #050810; border: 1px solid var(--border); border-radius: 4px;
  padding: 10px 12px; font-size: 9px; line-height: 1.6; color: var(--muted);
  min-height: 60px; max-height: 140px; overflow-y: auto; white-space: pre-wrap;
  font-family: var(--font); letter-spacing: 0.5px;
}
#output-box .ok   { color: var(--accent); }
#output-box .err  { color: var(--red); }
#output-box .warn { color: var(--amber); }

/* ── Footer ──────────────────────────────────────────────────────────────── */
#ftr { background: var(--panel); border-top: 1px solid var(--border);
       padding: 5px 20px; font-size: 9px; color: var(--muted); letter-spacing: 1px; flex-shrink: 0; }

/* ── Toast ───────────────────────────────────────────────────────────────── */
#toast { position: fixed; bottom: 36px; left: 50%; transform: translateX(-50%) translateY(20px);
         background: var(--panel); border: 1px solid var(--accent); border-radius: 4px;
         padding: 7px 16px; font-size: 10px; color: var(--accent); letter-spacing: 1px;
         opacity: 0; pointer-events: none; transition: opacity 0.2s, transform 0.2s; z-index: 99;
         white-space: nowrap; }
#toast.show { opacity: 1; transform: translateX(-50%) translateY(0); }
#toast.error { border-color: var(--red); color: var(--red); }
</style>
</head>
<body>

<div id="hdr">
  <div class="brand">Phoenix Switches</div>
  <span style="font-size:9px;color:var(--muted);letter-spacing:1px;">System Controls v1.0</span>
  <span id="save-status">Loading...</span>
</div>

<div id="content">

  <!-- AI Controls -->
  <div class="card">
    <div class="card-title ai">AI</div>
    <div class="sw-row" id="row-ai_suggestions">
      <label class="sw-label">AI Suggestions
        <span class="sw-desc">Ollama suggestions in Office pane</span>
      </label>
      <label class="toggle"><input type="checkbox" data-key="ai_suggestions"><span class="toggle-track"></span></label>
    </div>
    <div class="dd-row">
      <div class="dd-label">Active Model</div>
      <select class="phoenix-select" data-key="ollama_model" id="sel-ollama_model">
        <option value="llama3.1">llama3.1 — Life First / Laurie</option>
        <option value="llama3.2:3b">llama3.2:3b — Fast / Code</option>
        <option value="deepseek-r1:1.5b">deepseek-r1:1.5b — Reasoning</option>
        <option value="phi3.5">phi3.5 — Chat / Desktop</option>
      </select>
    </div>
    <button class="action-btn blue" data-action="pull_ollama_model">
      <span class="btn-icon">↓</span> Pull phi3.5 model
    </button>
  </div>

  <!-- Security Controls -->
  <div class="card">
    <div class="card-title security">Security</div>
    <div class="sw-row">
      <label class="sw-label">Life First Security
        <span class="sw-desc">Laurie's privacy protections active</span>
      </label>
      <label class="toggle"><input type="checkbox" data-key="lifefirst_security"><span class="toggle-track"></span></label>
    </div>
    <div class="sw-row">
      <label class="sw-label">Full Audit Log
        <span class="sw-desc">Verbose logging to /var/log/phoenix</span>
      </label>
      <label class="toggle amber"><input type="checkbox" data-key="full_audit_log"><span class="toggle-track"></span></label>
    </div>
    <div class="sw-row">
      <label class="sw-label">Bounce Armed
        <span class="sw-desc">1:1 return-to-sender at SOCK5</span>
      </label>
      <label class="toggle red"><input type="checkbox" data-key="bounce_armed"><span class="toggle-track"></span></label>
    </div>
    <div class="dd-row">
      <div class="dd-label">Lockdown Level</div>
      <select class="phoenix-select" data-key="lockdown_level" id="sel-lockdown_level">
        <option value="basic">Basic — chmod 700</option>
        <option value="high">High — chmod 500 (no write)</option>
        <option value="critical">Critical — chmod 000</option>
        <option value="immutable">Immutable — chattr +i</option>
      </select>
    </div>
    <div class="dd-row">
      <div class="dd-label">Threat Response</div>
      <select class="phoenix-select" data-key="threat_response" id="sel-threat_response">
        <option value="log-only">Log Only</option>
        <option value="auto-block">Auto Block (ufw)</option>
        <option value="full-lockdown">Full Lockdown</option>
      </select>
    </div>
    <div class="dd-row">
      <div class="dd-label">Buffer Sensitivity</div>
      <select class="phoenix-select" data-key="buffer_sensitivity" id="sel-buffer_sensitivity">
        <option value="standard">Standard (5 changes / 60s)</option>
        <option value="elevated">Elevated (3 changes / 60s)</option>
        <option value="paranoid">Paranoid (1 change)</option>
      </select>
    </div>
  </div>

  <!-- Document Controls -->
  <div class="card">
    <div class="card-title docs">Documents</div>
    <div class="sw-row">
      <label class="sw-label">Auto-Forge
        <span class="sw-desc">Seal documents automatically on save</span>
      </label>
      <label class="toggle amber"><input type="checkbox" data-key="auto_forge"><span class="toggle-track"></span></label>
    </div>
    <div class="sw-row">
      <label class="sw-label">Index New Docs
        <span class="sw-desc">Add to FTS5 search on forge</span>
      </label>
      <label class="toggle"><input type="checkbox" data-key="index_new_docs"><span class="toggle-track"></span></label>
    </div>
    <div class="sw-row">
      <label class="sw-label">Witness Required
        <span class="sw-desc">Two-signer for confidential docs</span>
      </label>
      <label class="toggle amber"><input type="checkbox" data-key="witness_required"><span class="toggle-track"></span></label>
    </div>
  </div>

  <!-- Core Controls -->
  <div class="card">
    <div class="card-title core">Core</div>
    <div class="sw-row">
      <label class="sw-label">Quadralingual Vault
        <span class="sw-desc">L1 obfuscation on breach_coms</span>
      </label>
      <label class="toggle"><input type="checkbox" data-key="quadralingual_vault"><span class="toggle-track"></span></label>
    </div>
  </div>

  <!-- Security Actions -->
  <div class="card">
    <div class="card-title security">Security Actions</div>
    <button class="action-btn blue"  data-action="guardian_scan">
      <span class="btn-icon">🔍</span> Run Config Scan
    </button>
    <button class="action-btn amber" data-action="guardian_conflicts">
      <span class="btn-icon">⚠</span> Check Conflicts
    </button>
    <button class="action-btn"       data-action="security_status">
      <span class="btn-icon">📡</span> Guardian Status
    </button>
    <button class="action-btn red"   data-action="clear_audit_log">
      <span class="btn-icon">✕</span> Clear Audit Log
    </button>
  </div>

  <!-- System Actions -->
  <div class="card">
    <div class="card-title actions">System Actions</div>
    <button class="action-btn green" data-action="frank_heartbeat">
      <span class="btn-icon">💓</span> Frank Heartbeat
    </button>
    <button class="action-btn blue"  data-action="reload_apache">
      <span class="btn-icon">↺</span> Reload Apache
    </button>
    <button class="action-btn blue"  data-action="reload_wireguard">
      <span class="btn-icon">↺</span> Reload WireGuard
    </button>
  </div>

  <!-- Output -->
  <div class="card" id="output-card">
    <div class="card-title">Output</div>
    <div id="output-box">Ready.</div>
  </div>

</div>

<div id="ftr">Phoenix DevOps OS — Switches &amp; Controls — jwl247</div>
<div id="toast"></div>

<script>
'use strict';

const API    = 'api/switches.php';
let settings = {};
let toastTimer;

// ── Load all states from API ──────────────────────────────────────────────────
async function loadAll() {
  try {
    const res  = await fetch(API);
    const data = await res.json();

    // Apply switches
    (data.switches || []).forEach(sw => {
      const input = document.querySelector(`input[data-key="${sw.key}"]`);
      if (input) input.checked = sw.value;
      settings[sw.key] = sw.value;
    });

    // Apply dropdowns
    (data.dropdowns || []).forEach(dd => {
      const sel = document.querySelector(`select[data-key="${dd.key}"]`);
      if (sel) sel.value = dd.value;
      settings[dd.key] = dd.value;
    });

    setSaveStatus('Loaded', 'ok');
  } catch (e) {
    setSaveStatus('API offline', 'err');
  }
}

// ── Toggle change ─────────────────────────────────────────────────────────────
document.querySelectorAll('input[type="checkbox"][data-key]').forEach(input => {
  input.addEventListener('change', async () => {
    const key   = input.dataset.key;
    const value = input.checked;
    setSaveStatus('Saving...', '');
    try {
      const res  = await fetch(API, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key, value }),
      });
      const data = await res.json();
      if (data.ok) {
        settings[key] = value;
        setSaveStatus(`${key} → ${value ? 'ON' : 'OFF'}`, 'ok');
        toast(`${key.replace(/_/g,' ').toUpperCase()}: ${value ? 'ON' : 'OFF'}`, false);
      } else {
        input.checked = !value;  // revert
        setSaveStatus('Save failed', 'err');
        toast('Save failed', true);
      }
    } catch (e) {
      input.checked = !value;
      setSaveStatus('API error', 'err');
    }
  });
});

// ── Dropdown change ───────────────────────────────────────────────────────────
document.querySelectorAll('select[data-key]').forEach(sel => {
  sel.addEventListener('change', async () => {
    const key   = sel.dataset.key;
    const value = sel.value;
    setSaveStatus('Saving...', '');
    try {
      const res  = await fetch(API, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key, value }),
      });
      const data = await res.json();
      if (data.ok) {
        settings[key] = value;
        setSaveStatus(`${key} → ${value}`, 'ok');
        toast(`${key.replace(/_/g,' ').toUpperCase()}: ${value}`, false);
        log(`Set ${key} = ${value}`, 'ok');
      } else {
        setSaveStatus('Save failed', 'err');
      }
    } catch (e) { setSaveStatus('API error', 'err'); }
  });
});

// ── Action buttons ────────────────────────────────────────────────────────────
document.querySelectorAll('button[data-action]').forEach(btn => {
  btn.addEventListener('click', async () => {
    const action = btn.dataset.action;
    btn.classList.add('running');
    const origText = btn.innerHTML;
    btn.innerHTML = `<span class="btn-icon">⋯</span> Running...`;

    try {
      const params = action === 'pull_ollama_model'
        ? `?action=${action}&model=${encodeURIComponent(settings['ollama_model'] || 'phi3.5')}`
        : `?action=${action}`;

      const res  = await fetch(API + params, { method: 'POST' });
      const data = await res.json();

      btn.classList.remove('running');
      if (data.ok) {
        btn.classList.add('done');
        const out = data.out || data.note || JSON.stringify(data, null, 2);
        log(out || `${action} complete`, 'ok');
        toast(`${action} — done`, false);
      } else {
        btn.classList.add('fail');
        log(data.error || `${action} failed`, 'err');
        toast(data.error || 'Failed', true);
      }
      setTimeout(() => { btn.classList.remove('done','fail'); btn.innerHTML = origText; }, 3000);
    } catch (e) {
      btn.classList.remove('running');
      btn.innerHTML = origText;
      log(`${action} error: ${e.message}`, 'err');
    }
  });
});

// ── Helpers ───────────────────────────────────────────────────────────────────
function setSaveStatus(msg, cls) {
  const el = document.getElementById('save-status');
  el.textContent = msg;
  el.style.color = cls === 'ok' ? 'var(--accent)' : cls === 'err' ? 'var(--red)' : 'var(--muted)';
}

function log(msg, cls = '') {
  const box  = document.getElementById('output-box');
  const line = document.createElement('div');
  line.className = cls;
  line.textContent = `${new Date().toLocaleTimeString()} — ${msg}`;
  box.appendChild(line);
  box.scrollTop = box.scrollHeight;
  if (box.children.length > 60) box.children[0].remove();
}

function toast(msg, isError = false) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = 'show' + (isError ? ' error' : '');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.className = ''; }, 2600);
}

// ── Init ──────────────────────────────────────────────────────────────────────
loadAll();
</script>
</body>
</html>
