<?php
/**
 * mixer.php — Phoenix System Mixer
 * Mixing board UI where each channel strip is a Phoenix service.
 * Buttons that would mute/solo audio tracks toggle SSH, WireGuard,
 * Cloudflared, venvs, Ollama, Frank, and more.
 *
 * Phoenix DevOps OS | jwl247 | GPL v3
 */
?><!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Phoenix Mixer</title>
<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

:root {
  --bg:        #07090c;
  --panel:     #0d1117;
  --strip:     #111820;
  --border:    #1e2a38;
  --accent:    #00ff88;
  --red:       #ff3b5c;
  --amber:     #ffaa00;
  --blue:      #00aaff;
  --purple:    #9b59ff;
  --dim:       #3a4a5a;
  --text:      #c8d8e8;
  --muted:     #556677;
  --font:      'Courier New', Courier, monospace;
}

body {
  background: var(--bg);
  color: var(--text);
  font-family: var(--font);
  height: 100vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  user-select: none;
}

/* ── Header ───────────────────────────────────────────────────────────────── */
#mixer-header {
  background: var(--panel);
  border-bottom: 1px solid var(--border);
  padding: 8px 16px;
  display: flex;
  align-items: center;
  gap: 16px;
  flex-shrink: 0;
}
#mixer-header .brand {
  font-size: 11px;
  letter-spacing: 3px;
  color: var(--accent);
  text-transform: uppercase;
}
#mixer-header .model-tag {
  font-size: 10px;
  color: var(--muted);
  letter-spacing: 1px;
}
#sys-status {
  margin-left: auto;
  display: flex;
  gap: 12px;
  align-items: center;
  font-size: 10px;
}
.sys-led {
  display: flex;
  align-items: center;
  gap: 5px;
  color: var(--muted);
}
.led-dot {
  width: 7px; height: 7px;
  border-radius: 50%;
  background: var(--dim);
  box-shadow: none;
  transition: background 0.3s, box-shadow 0.3s;
}
.led-dot.on   { background: var(--accent); box-shadow: 0 0 6px var(--accent); }
.led-dot.fail { background: var(--red);    box-shadow: 0 0 6px var(--red); }
.led-dot.warn { background: var(--amber);  box-shadow: 0 0 6px var(--amber); }

/* ── Group labels ─────────────────────────────────────────────────────────── */
#group-bar {
  background: var(--panel);
  border-bottom: 1px solid var(--border);
  display: flex;
  padding: 0 12px;
  flex-shrink: 0;
}
.group-label {
  font-size: 9px;
  letter-spacing: 2px;
  text-transform: uppercase;
  color: var(--muted);
  padding: 4px 8px;
  border-right: 1px solid var(--border);
}
.group-label.network { color: var(--blue); }
.group-label.core    { color: var(--accent); }
.group-label.ai      { color: var(--purple); }
.group-label.apps    { color: var(--amber); }
.group-label.monitor { color: #00cccc; }
.group-label.venv    { color: #ff6699; }

/* ── Channel board ────────────────────────────────────────────────────────── */
#board {
  display: flex;
  flex: 1;
  padding: 12px;
  gap: 8px;
  overflow-x: auto;
  overflow-y: hidden;
  align-items: stretch;
}

/* ── Channel strip ────────────────────────────────────────────────────────── */
.strip {
  background: var(--strip);
  border: 1px solid var(--border);
  border-radius: 6px;
  width: 90px;
  min-width: 90px;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 10px 6px 12px;
  gap: 8px;
  position: relative;
  transition: border-color 0.2s;
}
.strip:hover { border-color: var(--dim); }
.strip.active { border-color: var(--accent); }
.strip.failed { border-color: var(--red); }

/* group color accent line at top */
.strip::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 3px;
  border-radius: 6px 6px 0 0;
  background: var(--dim);
}
.strip[data-group="network"]::before { background: var(--blue); }
.strip[data-group="core"]::before    { background: var(--accent); }
.strip[data-group="ai"]::before      { background: var(--purple); }
.strip[data-group="apps"]::before    { background: var(--amber); }
.strip[data-group="monitor"]::before { background: #00cccc; }
.strip[data-group="venv"]::before    { background: #ff6699; }

/* ── VU meter (service health indicator) ─────────────────────────────────── */
.vu-meter {
  width: 18px;
  height: 80px;
  background: #0a0f14;
  border: 1px solid var(--border);
  border-radius: 3px;
  position: relative;
  overflow: hidden;
  display: flex;
  flex-direction: column-reverse;
  gap: 2px;
  padding: 2px;
}
.vu-seg {
  height: 8px;
  border-radius: 1px;
  background: var(--dim);
  transition: background 0.4s;
  flex-shrink: 0;
}
.vu-meter.active .vu-seg:nth-child(-n+3) { background: var(--red); }
.vu-meter.active .vu-seg:nth-child(n+4):nth-child(-n+6) { background: var(--amber); }
.vu-meter.active .vu-seg:nth-child(n+7) { background: var(--accent); }

/* ── Fader track ──────────────────────────────────────────────────────────── */
.fader-track {
  width: 8px;
  height: 80px;
  background: #0a0f14;
  border: 1px solid var(--border);
  border-radius: 4px;
  position: relative;
  cursor: ns-resize;
}
.fader-handle {
  position: absolute;
  left: -5px;
  width: 18px;
  height: 14px;
  background: linear-gradient(180deg, #2a3a4a 0%, #1a2530 100%);
  border: 1px solid #3a4a5a;
  border-radius: 3px;
  cursor: ns-resize;
  top: 30px;
  transition: border-color 0.2s;
}
.fader-handle::after {
  content: '';
  position: absolute;
  top: 50%; left: 50%;
  transform: translate(-50%, -50%);
  width: 10px; height: 1px;
  background: var(--muted);
}
.fader-handle:hover { border-color: var(--accent); }

.fader-row {
  display: flex;
  gap: 6px;
  align-items: center;
}

/* ── Channel buttons ──────────────────────────────────────────────────────── */
.btn-row {
  display: flex;
  gap: 4px;
}

.ch-btn {
  width: 36px;
  height: 24px;
  border: 1px solid var(--dim);
  border-radius: 3px;
  background: #0d1520;
  color: var(--muted);
  font-family: var(--font);
  font-size: 8px;
  letter-spacing: 1px;
  cursor: pointer;
  text-transform: uppercase;
  transition: all 0.15s;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
}
.ch-btn:hover { border-color: var(--text); color: var(--text); }
.ch-btn.lit {
  background: var(--accent);
  border-color: var(--accent);
  color: #000;
  box-shadow: 0 0 8px var(--accent);
}
.ch-btn.lit-red {
  background: var(--red);
  border-color: var(--red);
  color: #fff;
  box-shadow: 0 0 8px var(--red);
}
.ch-btn.lit-amber {
  background: var(--amber);
  border-color: var(--amber);
  color: #000;
  box-shadow: 0 0 8px var(--amber);
}
.ch-btn.spinning::after {
  content: '';
  position: absolute;
  inset: 2px;
  border: 1px solid transparent;
  border-top-color: currentColor;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* big ON button */
.on-btn {
  width: 74px;
  height: 32px;
  border: 1px solid var(--dim);
  border-radius: 4px;
  background: #0d1520;
  color: var(--muted);
  font-family: var(--font);
  font-size: 10px;
  letter-spacing: 2px;
  cursor: pointer;
  text-transform: uppercase;
  transition: all 0.2s;
  position: relative;
}
.on-btn:hover { border-color: var(--accent); color: var(--text); }
.on-btn.active {
  background: #003322;
  border-color: var(--accent);
  color: var(--accent);
  box-shadow: 0 0 10px rgba(0,255,136,0.25), inset 0 0 8px rgba(0,255,136,0.08);
}
.on-btn.busy { opacity: 0.6; cursor: wait; }

/* ── Channel label ────────────────────────────────────────────────────────── */
.ch-label {
  font-size: 9px;
  letter-spacing: 1.5px;
  text-transform: uppercase;
  color: var(--muted);
  text-align: center;
  line-height: 1.3;
  margin-top: 2px;
}
.strip.active .ch-label { color: var(--text); }

/* ── State badge ──────────────────────────────────────────────────────────── */
.state-badge {
  font-size: 8px;
  letter-spacing: 1px;
  text-transform: uppercase;
  padding: 2px 5px;
  border-radius: 2px;
  background: var(--dim);
  color: var(--bg);
}
.state-badge.active  { background: var(--accent); color: #000; }
.state-badge.failed  { background: var(--red);    color: #fff; }
.state-badge.unknown { background: var(--muted);  color: var(--bg); }

/* ── Master section ───────────────────────────────────────────────────────── */
#master {
  width: 110px;
  min-width: 110px;
  background: #0a0e15;
  border: 1px solid var(--border);
  border-radius: 6px;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 10px 8px 12px;
  gap: 8px;
  border-left: 3px solid var(--accent);
}
#master .master-label {
  font-size: 9px;
  letter-spacing: 3px;
  text-transform: uppercase;
  color: var(--accent);
}
.master-fader {
  width: 10px;
  height: 120px;
  background: #0a0f14;
  border: 1px solid var(--border);
  border-radius: 5px;
  position: relative;
}
.master-handle {
  position: absolute;
  left: -8px;
  width: 26px;
  height: 18px;
  background: linear-gradient(180deg, #1e3a2e 0%, #0f1e17 100%);
  border: 1px solid var(--accent);
  border-radius: 3px;
  cursor: ns-resize;
  top: 20px;
}
.master-handle::after {
  content: '';
  position: absolute;
  top: 50%; left: 50%;
  transform: translate(-50%, -50%);
  width: 14px; height: 1px;
  background: var(--accent);
}
#all-on-btn, #all-off-btn {
  width: 90px;
  height: 28px;
  border-radius: 4px;
  font-family: var(--font);
  font-size: 9px;
  letter-spacing: 2px;
  text-transform: uppercase;
  cursor: pointer;
  transition: all 0.2s;
  border: 1px solid;
}
#all-on-btn  { background: #003322; border-color: var(--accent); color: var(--accent); }
#all-on-btn:hover  { box-shadow: 0 0 8px rgba(0,255,136,0.4); }
#all-off-btn { background: #1a0a0a; border-color: var(--red);    color: var(--red); }
#all-off-btn:hover  { box-shadow: 0 0 8px rgba(255,59,92,0.4); }

#active-count {
  font-size: 22px;
  color: var(--accent);
  font-weight: bold;
  line-height: 1;
}
#active-label {
  font-size: 8px;
  letter-spacing: 1px;
  color: var(--muted);
  text-transform: uppercase;
}

/* ── Footer ───────────────────────────────────────────────────────────────── */
#mixer-footer {
  background: var(--panel);
  border-top: 1px solid var(--border);
  padding: 5px 16px;
  display: flex;
  align-items: center;
  gap: 16px;
  font-size: 9px;
  color: var(--muted);
  flex-shrink: 0;
  letter-spacing: 1px;
}
#log-line { flex: 1; color: var(--dim); }
#log-line.ok   { color: var(--accent); }
#log-line.err  { color: var(--red); }
#log-line.warn { color: var(--amber); }
#poll-timer { color: var(--dim); }

/* ── Telemetry panel ─────────────────────────────────────────────────────── */
#telemetry {
  width: 130px;
  min-width: 130px;
  background: #0a0e15;
  border: 1px solid var(--border);
  border-radius: 6px;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 10px 10px 12px;
  gap: 6px;
  border-left: 3px solid var(--blue);
}
.telem-label {
  font-size: 9px;
  letter-spacing: 3px;
  text-transform: uppercase;
  color: var(--blue);
  margin-bottom: 2px;
}
.telem-divider {
  width: 100%;
  height: 1px;
  background: var(--border);
  margin: 4px 0;
}
.telem-row {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 5px;
}
.telem-name {
  font-size: 8px;
  letter-spacing: 1px;
  color: var(--muted);
  text-transform: uppercase;
  width: 30px;
  flex-shrink: 0;
}
.telem-bar-wrap {
  flex: 1;
  height: 8px;
  background: #0a0f14;
  border: 1px solid var(--border);
  border-radius: 2px;
  overflow: hidden;
}
.telem-bar {
  height: 100%;
  width: 0%;
  background: var(--accent);
  transition: width 0.5s ease, background 0.5s ease;
  border-radius: 2px;
}
.telem-bar.warn { background: var(--amber); }
.telem-bar.crit { background: var(--red);   }
.telem-val {
  font-size: 9px;
  color: var(--text);
  width: 30px;
  text-align: right;
  flex-shrink: 0;
}

/* Threat level bars */
#threat-display {
  display: flex;
  gap: 3px;
  width: 100%;
  justify-content: center;
}
.threat-bar {
  width: 18px;
  height: 28px;
  border-radius: 3px;
  background: var(--dim);
  transition: background 0.4s, box-shadow 0.4s;
}
.threat-bar.lit-1 { background: var(--accent); }
.threat-bar.lit-2 { background: #88ff00; }
.threat-bar.lit-3 { background: var(--amber); }
.threat-bar.lit-4 { background: #ff6600; }
.threat-bar.lit-5 { background: var(--red); box-shadow: 0 0 10px var(--red); }

#threat-label {
  font-size: 11px;
  font-weight: bold;
  letter-spacing: 2px;
  color: var(--accent);
  text-transform: uppercase;
}
#threat-detail {
  font-size: 8px;
  color: var(--muted);
  text-align: center;
  line-height: 1.4;
  min-height: 12px;
}

/* Load avg */
.load-row {
  display: flex;
  gap: 6px;
  width: 100%;
  justify-content: space-around;
}
.load-cell {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}
.load-lbl { font-size: 7px; color: var(--muted); text-transform: uppercase; }
.load-cell span:last-child { font-size: 10px; color: var(--text); }

/* ── Toast ────────────────────────────────────────────────────────────────── */
#toast {
  position: fixed;
  bottom: 40px;
  left: 50%;
  transform: translateX(-50%) translateY(20px);
  background: var(--panel);
  border: 1px solid var(--accent);
  border-radius: 4px;
  padding: 8px 18px;
  font-size: 11px;
  color: var(--accent);
  letter-spacing: 1px;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.2s, transform 0.2s;
  z-index: 999;
  white-space: nowrap;
}
#toast.show {
  opacity: 1;
  transform: translateX(-50%) translateY(0);
}
#toast.error { border-color: var(--red); color: var(--red); }
</style>
</head>
<body>

<!-- Header -->
<div id="mixer-header">
  <div class="brand">Phoenix Mixer</div>
  <div class="model-tag">System Control Surface v1.0</div>
  <div id="sys-status">
    <div class="sys-led"><div class="led-dot" id="led-frank"></div>Frank</div>
    <div class="sys-led"><div class="led-dot" id="led-wg"></div>WireGuard</div>
    <div class="sys-led"><div class="led-dot" id="led-ollama"></div>Ollama</div>
    <div class="sys-led"><div class="led-dot" id="led-cf"></div>Tunnel</div>
    <span id="poll-timer" style="margin-left:8px;">─</span>
  </div>
</div>

<!-- Group bar -->
<div id="group-bar">
  <div class="group-label network">Network ×3</div>
  <div class="group-label core">Core ×2</div>
  <div class="group-label ai">AI ×1</div>
  <div class="group-label apps">Apps ×2</div>
  <div class="group-label monitor">Monitor ×1</div>
  <div class="group-label venv">venv ×3</div>
</div>

<!-- Board -->
<div id="board">
  <!-- Channel strips injected by JS -->
  <!-- Telemetry section -->
  <div id="telemetry">
    <div class="telem-label">Telemetry</div>

    <!-- CPU -->
    <div class="telem-row">
      <div class="telem-name">CPU</div>
      <div class="telem-bar-wrap">
        <div class="telem-bar" id="bar-cpu"></div>
      </div>
      <div class="telem-val" id="val-cpu">─</div>
    </div>

    <!-- RAM -->
    <div class="telem-row">
      <div class="telem-name">RAM</div>
      <div class="telem-bar-wrap">
        <div class="telem-bar" id="bar-ram"></div>
      </div>
      <div class="telem-val" id="val-ram">─</div>
    </div>

    <!-- SWAP -->
    <div class="telem-row">
      <div class="telem-name">SWAP</div>
      <div class="telem-bar-wrap">
        <div class="telem-bar" id="bar-swap"></div>
      </div>
      <div class="telem-val" id="val-swap">─</div>
    </div>

    <div class="telem-divider"></div>

    <!-- Threat level -->
    <div class="telem-name" style="margin-bottom:6px;">THREAT</div>
    <div id="threat-display">
      <div class="threat-bar" id="tbar-1"></div>
      <div class="threat-bar" id="tbar-2"></div>
      <div class="threat-bar" id="tbar-3"></div>
      <div class="threat-bar" id="tbar-4"></div>
      <div class="threat-bar" id="tbar-5"></div>
    </div>
    <div id="threat-label">─</div>
    <div id="threat-detail"></div>

    <div class="telem-divider"></div>

    <!-- Load avg -->
    <div class="telem-name">LOAD AVG</div>
    <div class="load-row">
      <span class="load-cell"><span class="load-lbl">1m</span><span id="load-1">─</span></span>
      <span class="load-cell"><span class="load-lbl">5m</span><span id="load-5">─</span></span>
      <span class="load-cell"><span class="load-lbl">15m</span><span id="load-15">─</span></span>
    </div>
  </div>

  <!-- Master section -->
  <div id="master">
    <div class="master-label">Master</div>
    <div id="active-count">─</div>
    <div id="active-label">active</div>
    <div class="master-fader"><div class="master-handle"></div></div>
    <button id="all-on-btn">▶ All On</button>
    <button id="all-off-btn">■ All Off</button>
  </div>
</div>

<!-- Footer log -->
<div id="mixer-footer">
  <span>Phoenix DevOps OS</span>
  <span id="log-line">Initializing...</span>
  <span id="poll-timer"></span>
</div>

<!-- Toast -->
<div id="toast"></div>

<script>
'use strict';

// ── Service definitions (mirrors PHP registry) ────────────────────────────
const SERVICES = [
  { id:'ssh',        label:'SSH',       group:'network', color:'var(--blue)'   },
  { id:'wireguard',  label:'WireGuard', group:'network', color:'var(--blue)'   },
  { id:'cloudflared',label:'Cloudflrd', group:'network', color:'var(--blue)'   },
  { id:'frank',      label:'Frank',     group:'core',    color:'var(--accent)' },
  { id:'conversion', label:'Conv Agent',group:'core',    color:'var(--accent)' },
  { id:'ollama',     label:'Ollama AI', group:'ai',      color:'var(--purple)' },
  { id:'lifefirst',  label:'Life First',group:'apps',    color:'var(--amber)'  },
  { id:'nextcloud',  label:'Nextcloud', group:'apps',    color:'var(--amber)'  },
  { id:'prometheus', label:'Prometheus',group:'monitor', color:'#00cccc'       },
  { id:'venv_frank', label:'venv/Frank',group:'venv',    color:'#ff6699'       },
  { id:'venv_lf',    label:'venv/LF',   group:'venv',    color:'#ff6699'       },
  { id:'venv_wt',    label:'venv/WT',   group:'venv',    color:'#ff6699'       },
];

// ── State ─────────────────────────────────────────────────────────────────
const state = {};   // id → 'active'|'inactive'|'failed'|'unknown'
let pollTimer = null;
let pollCountdown = 15;

// ── DOM refs ──────────────────────────────────────────────────────────────
const board    = document.getElementById('board');
const master   = document.getElementById('master');
const logLine  = document.getElementById('log-line');
const pollEl   = document.getElementById('poll-timer');
const toast    = document.getElementById('toast');

// ── Build channel strips ──────────────────────────────────────────────────
function buildStrips() {
  SERVICES.forEach(svc => {
    const strip = document.createElement('div');
    strip.className = 'strip';
    strip.dataset.id    = svc.id;
    strip.dataset.group = svc.group;
    strip.innerHTML = `
      <div class="vu-meter" id="vu-${svc.id}">
        ${Array(9).fill('<div class="vu-seg"></div>').join('')}
      </div>
      <div class="fader-row">
        <div class="fader-track"><div class="fader-handle"></div></div>
      </div>
      <div class="btn-row">
        <button class="ch-btn" id="btn-rst-${svc.id}" title="Restart" onclick="doAction('${svc.id}','restart')">RST</button>
        <button class="ch-btn" id="btn-log-${svc.id}" title="View status" onclick="doStatus('${svc.id}')">LOG</button>
      </div>
      <button class="on-btn" id="on-${svc.id}" onclick="toggleService('${svc.id}')">ON</button>
      <span class="state-badge" id="badge-${svc.id}">─</span>
      <div class="ch-label">${svc.label}</div>
    `;
    board.insertBefore(strip, master);
  });
}

// ── Update strip display from state ──────────────────────────────────────
function applyState(id, s) {
  state[id] = s;
  const strip = document.querySelector(`.strip[data-id="${id}"]`);
  const onBtn = document.getElementById(`on-${id}`);
  const badge = document.getElementById(`badge-${id}`);
  const vu    = document.getElementById(`vu-${id}`);
  const rst   = document.getElementById(`btn-rst-${id}`);

  if (!strip) return;

  strip.classList.toggle('active', s === 'active');
  strip.classList.toggle('failed', s === 'failed');

  onBtn.classList.toggle('active', s === 'active');
  onBtn.textContent = s === 'active' ? 'ON' : 'OFF';

  badge.className = `state-badge ${s}`;
  badge.textContent = s === 'unknown' ? '─' : s;

  vu.classList.toggle('active', s === 'active');

  rst.classList.toggle('lit-amber', s === 'active');
  rst.disabled = s === 'unknown';
}

function updateMaster() {
  const active = Object.values(state).filter(s => s === 'active').length;
  document.getElementById('active-count').textContent = active;

  // Header LEDs
  ['frank','wireguard','ollama','cloudflared'].forEach(id => {
    const ledMap = { frank:'led-frank', wireguard:'led-wg', ollama:'led-ollama', cloudflared:'led-cf' };
    const led = document.getElementById(ledMap[id]);
    if (!led) return;
    const s = state[id] || 'unknown';
    led.className = 'led-dot' + (s === 'active' ? ' on' : s === 'failed' ? ' fail' : '');
  });
}

// ── API calls ─────────────────────────────────────────────────────────────
async function callAPI(body) {
  const res = await fetch('api/service.php', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return res.json();
}

async function pollAll() {
  try {
    const res = await fetch('api/service.php');
    const data = await res.json();
    if (data.services) {
      data.services.forEach(svc => applyState(svc.service, svc.state));
      updateMaster();
      log(`Polled ${data.services.length} services`, 'ok');
    }
  } catch(e) {
    log('Poll failed — is Apache running?', 'err');
  }
}

async function toggleService(id) {
  const current = state[id] || 'unknown';
  const action = current === 'active' ? 'stop' : 'start';
  const onBtn = document.getElementById(`on-${id}`);

  onBtn.classList.add('busy');
  onBtn.textContent = '...';

  try {
    const r = await callAPI({ service: id, action });
    const newState = r.state || (action === 'start' ? 'active' : 'inactive');
    applyState(id, newState);
    updateMaster();
    log(`${id} → ${newState}`, r.ok ? 'ok' : 'err');
    showToast(`${id.toUpperCase()}: ${newState}`, !r.ok);
  } catch(e) {
    log(`${id} toggle error: ${e.message}`, 'err');
    showToast('API error', true);
  } finally {
    onBtn.classList.remove('busy');
  }
}

async function doAction(id, action) {
  const btn = document.getElementById(`btn-rst-${id}`);
  if (btn) { btn.classList.add('spinning'); btn.disabled = true; }

  try {
    const r = await callAPI({ service: id, action });
    const newState = r.state || state[id];
    applyState(id, newState);
    updateMaster();
    log(`${id} ${action} → ${newState}`, r.ok ? 'ok' : 'err');
    showToast(`${id.toUpperCase()}: ${action}`, !r.ok);
  } catch(e) {
    log(`${id} ${action} error: ${e.message}`, 'err');
  } finally {
    if (btn) { btn.classList.remove('spinning'); btn.disabled = false; }
  }
}

async function doStatus(id) {
  try {
    const r = await callAPI({ service: id, action: 'status' });
    const msg = `${id}: ${r.state || '?'}` + (r.note ? ` — ${r.note}` : '');
    log(msg, 'ok');
    showToast(msg, false);
  } catch(e) {
    log(`status error: ${e.message}`, 'err');
  }
}

// ── All on / All off ──────────────────────────────────────────────────────
document.getElementById('all-on-btn').onclick = async () => {
  log('Starting all services...', 'warn');
  for (const svc of SERVICES) {
    if (state[svc.id] !== 'active') await doAction(svc.id, 'start');
  }
};
document.getElementById('all-off-btn').onclick = async () => {
  if (!confirm('Stop ALL Phoenix services?')) return;
  log('Stopping all services...', 'warn');
  for (const svc of SERVICES) {
    if (state[svc.id] === 'active') await doAction(svc.id, 'stop');
  }
};

// ── Fader drag (visual only) ──────────────────────────────────────────────
board.addEventListener('mousedown', e => {
  const handle = e.target.closest('.fader-handle, .master-handle');
  if (!handle) return;
  const track = handle.parentElement;
  const trackH = track.clientHeight - handle.clientHeight;

  const onMove = mv => {
    const rect = track.getBoundingClientRect();
    let y = mv.clientY - rect.top - handle.clientHeight / 2;
    y = Math.max(0, Math.min(trackH, y));
    handle.style.top = y + 'px';
  };
  const onUp = () => { document.removeEventListener('mousemove', onMove); document.removeEventListener('mouseup', onUp); };
  document.addEventListener('mousemove', onMove);
  document.addEventListener('mouseup', onUp);
});

// ── Log / toast ───────────────────────────────────────────────────────────
function log(msg, cls = '') {
  logLine.textContent = msg;
  logLine.className = cls;
}

let toastTimer;
function showToast(msg, isError = false) {
  toast.textContent = msg;
  toast.className = 'show' + (isError ? ' error' : '');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { toast.className = ''; }, 2800);
}

// ── Poll loop ─────────────────────────────────────────────────────────────
function startPoll() {
  pollCountdown = 15;
  const tick = setInterval(() => {
    pollCountdown--;
    pollEl.textContent = `poll in ${pollCountdown}s`;
    if (pollCountdown <= 0) {
      clearInterval(tick);
      pollAll().then(startPoll);
    }
  }, 1000);
}

// ── Telemetry polling ─────────────────────────────────────────────────────
const THREAT_COLORS = ['','lit-1','lit-2','lit-3','lit-4','lit-5'];
const THREAT_TEXT_COLORS = {
  1: 'var(--accent)', 2: '#88ff00', 3: 'var(--amber)',
  4: '#ff6600',       5: 'var(--red)'
};

async function pollTelemetry() {
  try {
    const res  = await fetch('api/sysinfo.php');
    const data = await res.json();

    // CPU bar
    const cpu = data.cpu_pct ?? 0;
    const cpuBar = document.getElementById('bar-cpu');
    cpuBar.style.width = cpu + '%';
    cpuBar.className   = 'telem-bar' + (cpu > 90 ? ' crit' : cpu > 70 ? ' warn' : '');
    document.getElementById('val-cpu').textContent = cpu + '%';

    // RAM bar
    const ram    = data.memory?.ram_pct ?? 0;
    const ramBar = document.getElementById('bar-ram');
    ramBar.style.width = ram + '%';
    ramBar.className   = 'telem-bar' + (ram > 90 ? ' crit' : ram > 75 ? ' warn' : '');
    const ramUsed  = data.memory?.ram_used_mb ?? 0;
    const ramTotal = data.memory?.ram_total_mb ?? 0;
    document.getElementById('val-ram').textContent = ramUsed + 'M';

    // Swap bar
    const swap    = data.memory?.swap_pct ?? 0;
    const swapBar = document.getElementById('bar-swap');
    swapBar.style.width = swap + '%';
    swapBar.className   = 'telem-bar' + (swap > 50 ? ' crit' : swap > 20 ? ' warn' : '');
    document.getElementById('val-swap').textContent = (data.memory?.swap_used_mb ?? 0) + 'M';

    // Threat level
    const lvl = data.threat?.level ?? 1;
    for (let i = 1; i <= 5; i++) {
      const bar = document.getElementById(`tbar-${i}`);
      bar.className = 'threat-bar' + (i <= lvl ? ` ${THREAT_COLORS[i]}` : '');
    }
    const threatLabel = document.getElementById('threat-label');
    threatLabel.textContent = data.threat?.label ?? '─';
    threatLabel.style.color = THREAT_TEXT_COLORS[lvl] || 'var(--accent)';
    document.getElementById('threat-detail').textContent = (data.threat?.detail ?? []).join(' · ') || '';

    // Load avg
    document.getElementById('load-1').textContent  = data.threat?.load1  ?? '─';
    document.getElementById('load-5').textContent  = data.threat?.load5  ?? '─';
    document.getElementById('load-15').textContent = data.threat?.load15 ?? '─';

    // Header LED — threat level affects Frank LED if high
    if (lvl >= 4) {
      document.getElementById('led-frank').className = 'led-dot fail';
    }

  } catch(e) {
    // Telemetry offline — not fatal
  }
}

function startTelemPoll() {
  pollTelemetry();
  setInterval(pollTelemetry, 8000);  // every 8s (CPU read takes 200ms)
}

// ── Init ──────────────────────────────────────────────────────────────────
buildStrips();
pollAll().then(startPoll);
startTelemPoll();
</script>
</body>
</html>
