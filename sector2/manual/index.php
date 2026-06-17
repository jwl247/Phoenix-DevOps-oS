<?php
/**
 * Phoenix DevOps OS — Operator Manual
 * /manual/ — Jerry Leftwich / jwl247
 * Dark cockpit UI, organized by sector. Run at http://192.168.1.133/manual/
 */
?><!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Phoenix OS — Operator Manual</title>
<style>
:root {
  --bg:      #07090c;
  --panel:   #0d1117;
  --border:  #1e2a38;
  --accent:  #00ff88;
  --amber:   #ffb300;
  --red:     #ff4040;
  --blue:    #4fc3f7;
  --muted:   #4a5568;
  --text:    #c9d1d9;
  --bright:  #e6edf3;
  --font:    'Courier New', 'Lucida Console', monospace;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: var(--bg); color: var(--text); font-family: var(--font); font-size: 14px; min-height: 100vh; }

/* ── Layout ── */
.shell { display: flex; min-height: 100vh; }
.sidebar { width: 240px; min-width: 240px; background: var(--panel); border-right: 1px solid var(--border); position: sticky; top: 0; height: 100vh; overflow-y: auto; display: flex; flex-direction: column; }
.main { flex: 1; overflow-y: auto; padding: 32px; max-width: 900px; }

/* ── Sidebar ── */
.logo { padding: 20px 16px 12px; border-bottom: 1px solid var(--border); }
.logo-title { color: var(--accent); font-size: 13px; font-weight: bold; letter-spacing: 2px; }
.logo-sub { color: var(--muted); font-size: 10px; margin-top: 4px; }
.nav-section { padding: 12px 0 4px 16px; font-size: 9px; color: var(--muted); letter-spacing: 2px; text-transform: uppercase; }
.nav-item { display: block; padding: 7px 16px; color: var(--text); text-decoration: none; font-size: 12px; cursor: pointer; border-left: 2px solid transparent; transition: all 0.15s; }
.nav-item:hover { color: var(--accent); background: rgba(0,255,136,0.05); border-left-color: var(--accent); }
.nav-item.active { color: var(--accent); border-left-color: var(--accent); background: rgba(0,255,136,0.08); }
.nav-item .badge { float: right; background: var(--border); color: var(--muted); font-size: 9px; padding: 1px 6px; border-radius: 2px; }
.nav-item.warn .badge { background: rgba(255,179,0,0.15); color: var(--amber); }
.nav-item.ok .badge { background: rgba(0,255,136,0.12); color: var(--accent); }
.sidebar-footer { margin-top: auto; padding: 12px 16px; border-top: 1px solid var(--border); font-size: 10px; color: var(--muted); }

/* ── Content sections ── */
.section { display: none; }
.section.active { display: block; }
h1 { color: var(--bright); font-size: 22px; margin-bottom: 6px; }
h2 { color: var(--accent); font-size: 14px; margin: 28px 0 10px; letter-spacing: 1px; text-transform: uppercase; }
h3 { color: var(--blue); font-size: 13px; margin: 20px 0 8px; }
p { color: var(--text); line-height: 1.7; margin-bottom: 12px; }
.subtitle { color: var(--muted); font-size: 12px; margin-bottom: 28px; }

/* ── Code blocks ── */
pre, code { font-family: var(--font); }
.code-block { background: #0a0e14; border: 1px solid var(--border); border-left: 3px solid var(--accent); padding: 14px 16px; margin: 10px 0 16px; overflow-x: auto; position: relative; border-radius: 2px; }
.code-block code { color: var(--accent); font-size: 13px; line-height: 1.6; }
.code-block .copy-btn { position: absolute; top: 8px; right: 8px; background: var(--border); border: none; color: var(--muted); padding: 3px 8px; font-size: 10px; cursor: pointer; font-family: var(--font); border-radius: 2px; }
.code-block .copy-btn:hover { color: var(--accent); }
.inline-code { background: #0a0e14; border: 1px solid var(--border); color: var(--accent); padding: 1px 5px; font-size: 12px; border-radius: 2px; }

/* ── Tables ── */
table { width: 100%; border-collapse: collapse; margin: 12px 0 20px; }
th { text-align: left; color: var(--muted); font-size: 10px; letter-spacing: 1px; text-transform: uppercase; padding: 6px 10px; border-bottom: 1px solid var(--border); }
td { padding: 8px 10px; border-bottom: 1px solid #111820; font-size: 12px; vertical-align: top; }
td:first-child { color: var(--accent); white-space: nowrap; }
tr:hover td { background: rgba(255,255,255,0.02); }

/* ── Status pills ── */
.pill { display: inline-block; font-size: 9px; padding: 2px 7px; border-radius: 2px; letter-spacing: 1px; text-transform: uppercase; font-weight: bold; }
.pill.ok    { background: rgba(0,255,136,0.12); color: var(--accent); }
.pill.warn  { background: rgba(255,179,0,0.12); color: var(--amber); }
.pill.off   { background: rgba(255,64,64,0.12);  color: var(--red); }
.pill.info  { background: rgba(79,195,247,0.12); color: var(--blue); }

/* ── Callouts ── */
.callout { border-left: 3px solid; padding: 12px 16px; margin: 14px 0; border-radius: 2px; }
.callout.tip    { border-color: var(--accent); background: rgba(0,255,136,0.05); }
.callout.warn   { border-color: var(--amber);  background: rgba(255,179,0,0.05); }
.callout.danger { border-color: var(--red);    background: rgba(255,64,64,0.05); }
.callout-title  { font-size: 10px; letter-spacing: 1px; text-transform: uppercase; font-weight: bold; margin-bottom: 6px; }
.callout.tip  .callout-title { color: var(--accent); }
.callout.warn .callout-title { color: var(--amber); }
.callout.danger .callout-title { color: var(--red); }

/* ── Key grid ── */
.key-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 10px; margin: 12px 0 20px; }
.key-card { background: var(--panel); border: 1px solid var(--border); padding: 12px; border-radius: 2px; }
.key-card .kc-label { color: var(--muted); font-size: 9px; letter-spacing: 1px; text-transform: uppercase; margin-bottom: 4px; }
.key-card .kc-val { color: var(--bright); font-size: 13px; }
.key-card .kc-sub { color: var(--muted); font-size: 10px; margin-top: 3px; }

/* ── Search ── */
.search-bar { position: relative; margin-bottom: 24px; }
.search-bar input { width: 100%; background: var(--panel); border: 1px solid var(--border); color: var(--text); padding: 10px 14px; font-family: var(--font); font-size: 13px; outline: none; border-radius: 2px; }
.search-bar input:focus { border-color: var(--accent); }
.search-bar input::placeholder { color: var(--muted); }

/* ── Toast ── */
#toast { position: fixed; bottom: 24px; right: 24px; background: var(--accent); color: #000; padding: 8px 16px; font-size: 12px; font-family: var(--font); font-weight: bold; border-radius: 2px; opacity: 0; transition: opacity 0.2s; pointer-events: none; z-index: 9999; }
#toast.show { opacity: 1; }

/* ── Divider ── */
hr { border: none; border-top: 1px solid var(--border); margin: 24px 0; }
</style>
</head>
<body>
<div class="shell">

<!-- ── SIDEBAR ── -->
<nav class="sidebar">
  <div class="logo">
    <div class="logo-title">PHOENIX OS</div>
    <div class="logo-sub">OPERATOR MANUAL · jwl247</div>
  </div>

  <div class="nav-section">Overview</div>
  <a class="nav-item active" onclick="show('overview')">What is Phoenix</a>
  <a class="nav-item" onclick="show('status')">System Status <span class="badge ok">LIVE</span></a>

  <div class="nav-section">Sectors</div>
  <a class="nav-item" onclick="show('sector1')">Sector 1 — Boot / Kernel</a>
  <a class="nav-item" onclick="show('sector2')">Sector 2 — Packages / Apps</a>
  <a class="nav-item" onclick="show('sector3')">Sector 3 — Comms / Network</a>
  <a class="nav-item" onclick="show('sector4')">Sector 4 — Helix / Frank</a>

  <div class="nav-section">Daily Use</div>
  <a class="nav-item" onclick="show('intake')">Intake — lol / intake.sh</a>
  <a class="nav-item" onclick="show('ssh')">SSH &amp; WireGuard</a>
  <a class="nav-item" onclick="show('apps')">Apps — Glossary / Review</a>
  <a class="nav-item" onclick="show('lifefirst')">Life First (Laurie)</a>

  <div class="nav-section">AI</div>
  <a class="nav-item" onclick="show('ollama')">Ollama — Self-Hosted AI</a>
  <a class="nav-item" onclick="show('frank-ai')">Frank × Ollama Bridge</a>

  <div class="nav-section">Ops</div>
  <a class="nav-item" onclick="show('services')">Services &amp; Ports</a>
  <a class="nav-item" onclick="show('vault')">breach_coms Vault</a>
  <a class="nav-item" onclick="show('deploy')">Deploy Scripts</a>
  <a class="nav-item" onclick="show('rules')">Critical Rules</a>

  <div class="sidebar-footer">
    phoenix-ext · 192.168.1.133<br>
    GPL v3 · Phoenix DevOps LLC
  </div>
</nav>

<!-- ── MAIN ── -->
<main class="main">

<!-- OVERVIEW -->
<section class="section active" id="sec-overview">
  <h1>Phoenix DevOps OS</h1>
  <p class="subtitle">Deterministic · Agnostic · Prefetched · Self-healing · Versioned</p>

  <p>Phoenix is an operating system layer built on top of a Debian/Ubuntu base. It adds deterministic package management, a dual-strand memory engine (Helix), a process orchestration kernel (Frank), a 4-tier versioned vault (breach_coms), and a full self-hosted AI stack. It is the OS — not a tool that runs on one.</p>

  <h2>The Big Picture</h2>
  <div class="key-grid">
    <div class="key-card"><div class="kc-label">Build Target</div><div class="kc-val">phoenix-ext</div><div class="kc-sub">Dell Inspiron · 192.168.1.133</div></div>
    <div class="key-card"><div class="kc-label">Base OS</div><div class="kc-val">Ubuntu 24.04 LTS</div><div class="kc-sub">HWE kernel 6.8.0</div></div>
    <div class="key-card"><div class="kc-label">Phoenix Kernel</div><div class="kc-val">Frank5 v5.1.0-alpha</div><div class="kc-sub">20 suits · 8 Helix channels</div></div>
    <div class="key-card"><div class="kc-label">Vault</div><div class="kc-val">4-tier breach_coms</div><div class="kc-sub">T1 master → T4 archive</div></div>
    <div class="key-card"><div class="kc-label">Clonepool</div><div class="kc-val">/breach_coms4/clonepool</div><div class="kc-sub">All packages · D1 synced</div></div>
    <div class="key-card"><div class="kc-label">Install</div><div class="kc-val">get.authenticcoder.com</div><div class="kc-sub">curl -fsSL | bash</div></div>
  </div>

  <h2>Four Sectors</h2>
  <table>
    <tr><th>Sector</th><th>Purpose</th><th>Key Components</th></tr>
    <tr><td>Sector 1</td><td>Boot, GRUB, kernel modules</td><td>frank3, helix stack, phoenix_auth, concierge</td></tr>
    <tr><td>Sector 2</td><td>Intake authority, packages, apps</td><td>intake.sh, package-handler, clone pool, glossary, review</td></tr>
    <tr><td>Sector 3</td><td>Comms, networking, translation</td><td>romeo/juliet, quadengine, translator.sh, WireGuard</td></tr>
    <tr><td>Sector 4</td><td>Helix engine, Frank core, AI</td><td>frank.py, helix.py, breach_coms vault, Ollama bridge</td></tr>
  </table>

  <h2>Philosophy</h2>
  <p>Everything in Phoenix follows three principles: <strong>everything is deterministic</strong> (same input, same output, always), <strong>everything has custody</strong> (chain of evidence in D1 for every file), and <strong>everything is agnostic</strong> (Phoenix doesn't care what distro, architecture, or language — it absorbs and tracks it all).</p>

  <div class="callout tip">
    <div class="callout-title">CLI, GUI, or Never Type Again</div>
    Phoenix meets you where you are. The operator (Jerry) works in the terminal. Laurie works through Life First. The HUD desktop is the graphical face. All three paths go through the same kernel.
  </div>
</section>

<!-- STATUS -->
<section class="section" id="sec-status">
  <h1>System Status</h1>
  <p class="subtitle">Live checks against phoenix-ext</p>
  <div id="status-grid" class="key-grid"><div class="key-card"><div class="kc-label">Loading...</div></div></div>
  <div class="callout tip" style="margin-top:20px;">
    <div class="callout-title">Run Manually</div>
    <code>ssh phoenix-ext "sudo systemctl status phoenix-kernel ollama prometheus"</code>
  </div>
  <h2>Service Port Map</h2>
  <table>
    <tr><th>Service</th><th>Port</th><th>Description</th></tr>
    <tr><td>Helix-I ch1-4</td><td>7701–7704</td><td>Intake channels (strand A + B)</td></tr>
    <tr><td>Helix-E ch5-8</td><td>7805–7808</td><td>Output channels (strand A + B)</td></tr>
    <tr><td>Frank HTTP</td><td>7347</td><td>Frank proxy wall + /lifefirst routes</td></tr>
    <tr><td>Telemetry</td><td>7899</td><td>WebSocket — HUD desktop feed</td></tr>
    <tr><td>Ollama</td><td>11434</td><td>Local LLM API</td></tr>
    <tr><td>Prometheus</td><td>9090</td><td>Metrics scraper</td></tr>
    <tr><td>Apache</td><td>80</td><td>Glossary / Review / Life First / Manual</td></tr>
  </table>
</section>

<!-- SECTOR 1 -->
<section class="section" id="sec-sector1">
  <h1>Sector 1 — Boot / Kernel</h1>
  <p class="subtitle">frank3 · helix stack · phoenix_auth · concierge</p>

  <p>Sector 1 owns the boot path. Everything here runs before the OS hands off to the Phoenix kernel layer. It does not move data — it establishes identity and starts the chain of trust.</p>

  <h2>Directory Map</h2>
  <table>
    <tr><th>Path</th><th>Contents</th></tr>
    <tr><td>sector1/kernels/</td><td>frank3_slot_a.c, frank3_slot_b.c, Makefile — C kernel modules</td></tr>
    <tr><td>sector1/helix/</td><td>Full helix stack: kernel, run, conf, vram, translator, slim</td></tr>
    <tr><td>sector1/auth/</td><td>phoenix_auth.py — authentication, PHOENIX_AUTH token</td></tr>
    <tr><td>sector1/concierge/</td><td>concierge.c, linux_concierge.py, windows_concierge.py, bridge.py</td></tr>
  </table>

  <h2>phoenix_auth</h2>
  <p>The <span class="inline-code">PHOENIX_AUTH</span> token is the system-wide authentication secret. It lives in <span class="inline-code">~/.phoenix_env</span> on phoenix-ext and is injected into every service via systemd <span class="inline-code">EnvironmentFile</span>.</p>
  <div class="code-block"><button class="copy-btn" onclick="cp(this)">copy</button><code># Check token is loaded in the kernel process
cat /proc/$(systemctl show -p MainPID --value phoenix-kernel)/environ | tr '\0' '\n' | grep PHOENIX_AUTH</code></div>

  <div class="callout warn">
    <div class="callout-title">Custom GRUB — Phase 7</div>
    The custom Phoenix GRUB theme and boot entries are Phase 7. Do not touch GRUB until Phoenix is fully standing.
  </div>

  <h2>Concierge</h2>
  <p>The concierge layer sits between the outside world and the kernel. <span class="inline-code">linux_concierge.py</span> runs on phoenix-ext, <span class="inline-code">windows_concierge.py</span> runs on the Windows host. <span class="inline-code">bridge.py</span> connects them. Intake travels through the concierge — never directly to Frank.</p>
</section>

<!-- SECTOR 2 -->
<section class="section" id="sec-sector2">
  <h1>Sector 2 — Packages / Apps</h1>
  <p class="subtitle">intake authority · package handler · clone pool · glossary · review</p>

  <p>Sector 2 is the intake authority. Every file, package, config, and dependency that enters Phoenix goes through Sector 2. Nothing gets placed without a hex identity and a D1 custody receipt.</p>

  <h2>Package Handler</h2>
  <table>
    <tr><th>Component</th><th>Purpose</th></tr>
    <tr><td>intake.sh</td><td>Main intake entry — generates hex identity + sidecar, syncs to D1</td></tr>
    <tr><td>worker/index.js</td><td>Cloudflare Worker — packages-worker, D1 gateway, /clonepool /custody /glossary</td></tr>
    <tr><td>wrangler.jsonc</td><td>Worker config — binds to phoenix_dev_db (D1, 41 tables)</td></tr>
  </table>

  <h2>Clone Pool</h2>
  <p>The clone pool is the callable face of the vault. Every file that passes intake lives in the clone pool as a named directory with its sidecar.json. The pool is at <span class="inline-code">/breach_coms4/clonepool</span> (symlinked to <span class="inline-code">~/Phoenix/clonepool</span>).</p>
  <div class="code-block"><button class="copy-btn" onclick="cp(this)">copy</button><code># Count pool entries
ls /breach_coms4/clonepool | wc -l

# View a sidecar
cat /breach_coms4/clonepool/&lt;name&gt;/sidecar.json</code></div>

  <h2>TAV Address System</h2>
  <p>Every file gets a permanent base58 address: <span class="inline-code">SHA3-512 → first 8 bytes → base58</span>. This is the shortest unique address for any file in the system — deterministic and permanent.</p>
  <div class="code-block"><button class="copy-btn" onclick="cp(this)">copy</button><code>Header QR:  USYS:&lt;b58&gt;:HEADER         (state: white/grey/black)
Footer QR:  USYS:&lt;b58&gt;:FOOTER:&lt;sha3&gt;  (tier: T1/T2/T3/T4)</code></div>

  <div class="callout danger">
    <div class="callout-title">Rule: Header Before Hash / Footer After Hash</div>
    The header QR is generated BEFORE the file is hashed. The footer QR is generated AFTER. Never swap these. This is how custody and state are tracked separately.
  </div>

  <h2>Apps in Sector 2</h2>
  <table>
    <tr><th>App</th><th>URL</th><th>Status</th></tr>
    <tr><td>Glossary</td><td>/glossary/</td><td><span class="pill ok">LIVE</span></td></tr>
    <tr><td>Review Platform</td><td>/review/</td><td><span class="pill ok">LIVE</span></td></tr>
    <tr><td>Manual (this)</td><td>/manual/</td><td><span class="pill ok">LIVE</span></td></tr>
    <tr><td>Office</td><td>/office/</td><td><span class="pill warn">PLANNED</span></td></tr>
    <tr><td>Sketchpad</td><td>/sketchpad/</td><td><span class="pill warn">PLANNED</span></td></tr>
    <tr><td>Music Notation</td><td>/notation/</td><td><span class="pill warn">PLANNED</span></td></tr>
    <tr><td>Desktop HUD</td><td>/desktop/</td><td><span class="pill warn">PLANNED</span></td></tr>
  </table>
</section>

<!-- SECTOR 3 -->
<section class="section" id="sec-sector3">
  <h1>Sector 3 — Comms / Network</h1>
  <p class="subtitle">romeo/juliet · quadengine · translator · WireGuard</p>

  <div class="callout danger">
    <div class="callout-title">Critical Rule — translator.sh fires on OUTPUT ONLY</div>
    <span class="inline-code">translator.sh</span> is the OUTPUT boundary. It fires when data leaves Sector 3 — never on intake, never on clones. Data inside Phoenix stays quadralingual until it crosses this line.
  </div>

  <h2>Romeo / Juliet</h2>
  <table>
    <tr><th>Component</th><th>Role</th></tr>
    <tr><td>romeo.py</td><td>Ingress handler — accepts data into Sector 3</td></tr>
    <tr><td>juliet.py</td><td>Egress handler — routes data out of Sector 3</td></tr>
    <tr><td>dbl_juliet.py</td><td>Double-egress — mirrors output to two destinations</td></tr>
    <tr><td>quadengine.py</td><td>Quadralingual engine — manages 4-language simultaneous processing</td></tr>
  </table>

  <h2>WireGuard Mesh</h2>
  <p>Phoenix runs a 3-node WireGuard mesh. Windows is the hub. All traffic between nodes goes through the mesh — not the LAN.</p>
  <div class="key-grid">
    <div class="key-card"><div class="kc-label">Windows (Hub)</div><div class="kc-val">10.77.0.1</div><div class="kc-sub">wg0-windows · ListenPort 51820</div></div>
    <div class="key-card"><div class="kc-label">WSL</div><div class="kc-val">10.77.0.2</div><div class="kc-sub">wg0-wsl · auto-starts on shell</div></div>
    <div class="key-card"><div class="kc-label">phoenix-ext</div><div class="kc-val">10.77.0.3</div><div class="kc-sub">wg0 · enabled via systemd</div></div>
  </div>
  <div class="code-block"><button class="copy-btn" onclick="cp(this)">copy</button><code># Check mesh status from any node
sudo wg show

# Restart WireGuard on WSL (auto-starts in .bashrc)
sudo wg-quick down wg0 && sudo wg-quick up wg0</code></div>

  <h2>Systemd Units (Sector 3)</h2>
  <div class="code-block"><button class="copy-btn" onclick="cp(this)">copy</button><code># Install all 18 Phoenix units on a new machine
sudo bash ~/phoenix-devops/sector3/services/install-units.sh

# Key services
sudo systemctl status phoenix-kernel       # Frank5 + Helix
sudo systemctl status phoenix-telemetry    # WebSocket port 7899
sudo systemctl status ollama               # Local LLM API</code></div>
</section>

<!-- SECTOR 4 -->
<section class="section" id="sec-sector4">
  <h1>Sector 4 — Helix / Frank</h1>
  <p class="subtitle">dual-strand memory · process orchestration · breach_coms vault</p>

  <h2>Frank</h2>
  <p>Frank is the environment orchestrator and import method authority. Frank is immovable — Frank is where Frank is. Every action in Phoenix is logged through Frank's audit trail.</p>
  <div class="key-grid">
    <div class="key-card"><div class="kc-label">Version</div><div class="kc-val">Frank5 v5.1.0-alpha</div></div>
    <div class="key-card"><div class="kc-label">Suits</div><div class="kc-val">20 in closet</div></div>
    <div class="key-card"><div class="kc-label">Workers</div><div class="kc-val">32 FrankSpawn</div></div>
    <div class="key-card"><div class="kc-label">Audit log</div><div class="kc-val">/var/log/phoenix/audit.log</div></div>
  </div>
  <div class="code-block"><button class="copy-btn" onclick="cp(this)">copy</button><code># Frank kernel status
systemctl status phoenix-kernel
journalctl -u phoenix-kernel -n 30 --no-pager

# Frank HTTP proxy wall (port 7347)
curl http://localhost:7347/status</code></div>

  <h2>Helix — Double Strand Memory Engine</h2>
  <p>Helix is the memory layer. Twin single-pass, peer-optimized. 300k+ ops/sec benchmarked at 700k. Uses zlib level 5 compression. 4GB of 8GB RAM allocated (thermal limited).</p>
  <table>
    <tr><th>Strand</th><th>Ports</th><th>Role</th></tr>
    <tr><td>Helix-I (Intake)</td><td>7701–7704</td><td>ch1+2 strand A · ch3+4 strand B</td></tr>
    <tr><td>Helix-E (Export)</td><td>7805–7808</td><td>ch5+6 strand A · ch7+8 strand B</td></tr>
  </table>

  <h2>breach_coms Vault</h2>
  <table>
    <tr><th>Tier</th><th>Mount</th><th>Drive</th><th>Role</th></tr>
    <tr><td>T1 PRIMARY</td><td>/breach_coms4</td><td>sdc1</td><td>Master vault — intake writes here. Never delete.</td></tr>
    <tr><td>T2 SECONDARY</td><td>/breach_coms3</td><td>sdb1</td><td>Day-1 mirror</td></tr>
    <tr><td>T3 TERTIARY</td><td>/breach_coms2</td><td>sdc2</td><td>Day-2 mirror</td></tr>
    <tr><td>T4 TERTIARY</td><td>/breach_coms1</td><td>sda2</td><td>Day-3 mirror — 4-day window</td></tr>
  </table>
  <div class="callout danger">
    <div class="callout-title">Rule: Never Delete from breach_coms4</div>
    T1 is the master vault. Intake always writes to T1. Never delete from /breach_coms4. Propagation moves data down the tiers — it never removes from T1.
  </div>

  <h2>D1 — Custody Database</h2>
  <p>D1 is the chain of evidence. Every file that passes intake gets a custody receipt in D1. 41 tables. Worker: <span class="inline-code">packages-worker.phoenix-jwl.workers.dev</span>.</p>
  <div class="code-block"><button class="copy-btn" onclick="cp(this)">copy</button><code># Test D1 endpoints from phoenix-ext
curl -s https://packages-worker.phoenix-jwl.workers.dev/clonepool | head -20
curl -s https://packages-worker.phoenix-jwl.workers.dev/custody | head -20
curl -s https://packages-worker.phoenix-jwl.workers.dev/glossary | head -20</code></div>
</section>

<!-- INTAKE -->
<section class="section" id="sec-intake">
  <h1>Intake — lol / intake.sh</h1>
  <p class="subtitle">The Phoenix import method. Everything goes through Frank.</p>

  <p><span class="inline-code">lol</span> is the intake command. It wraps <span class="inline-code">intake.sh</span> and is the canonical way to register a file into Phoenix. Every file gets a hex identity, a sidecar.json, a clonepool slot, and a D1 custody receipt.</p>

  <h2>Using lol</h2>
  <div class="code-block"><button class="copy-btn" onclick="cp(this)">copy</button><code># Register a single file
lol myfile.py

# Register with a description
lol myfile.py "Frank HTTP proxy handler"

# Register everything in a directory
for f in ~/myproject/*; do lol "$f"; done</code></div>

  <h2>What Happens on Intake</h2>
  <table>
    <tr><th>Step</th><th>What</th><th>Where</th></tr>
    <tr><td>1</td><td>Frank registers the file</td><td>Frank audit log</td></tr>
    <tr><td>2</td><td>SHA3-512 hash + base58 TAV address generated</td><td>In memory</td></tr>
    <tr><td>3</td><td>sidecar.json written (name, hex, sha3, description, ts)</td><td>clonepool/&lt;name&gt;/</td></tr>
    <tr><td>4</td><td>File copied to clonepool slot</td><td>/breach_coms4/clonepool/</td></tr>
    <tr><td>5</td><td>D1 custody receipt posted to packages-worker</td><td>Cloudflare D1</td></tr>
    <tr><td>6</td><td>Glossary entry updated</td><td>D1 glossary table</td></tr>
  </table>

  <h2>Direct intake.sh</h2>
  <div class="code-block"><button class="copy-btn" onclick="cp(this)">copy</button><code>bash ~/phoenix-devops/sector2/package-handler/intake.sh &lt;file&gt; [description]</code></div>

  <h2>Checking What's in the Pool</h2>
  <div class="code-block"><button class="copy-btn" onclick="cp(this)">copy</button><code># Count
ls /breach_coms4/clonepool | wc -l

# Find a specific file
ls /breach_coms4/clonepool | grep myfile

# View custody receipt
cat /breach_coms4/clonepool/myfile.py/sidecar.json</code></div>

  <div class="callout tip">
    <div class="callout-title">Glossary = TOC for the Clonepool</div>
    After intake, every file appears in the Glossary at <a href="/glossary/" style="color:var(--accent)">/glossary/</a>. The Glossary is the human-readable index of everything in Phoenix.
  </div>
</section>

<!-- SSH -->
<section class="section" id="sec-ssh">
  <h1>SSH &amp; WireGuard</h1>
  <p class="subtitle">Getting to phoenix-ext from Windows or WSL</p>

  <h2>SSH Aliases</h2>
  <table>
    <tr><th>Alias</th><th>Resolves To</th><th>Use When</th></tr>
    <tr><td>phoenix-ext</td><td>10.77.0.3 (WireGuard)</td><td>Normal operations — mesh must be up</td></tr>
    <tr><td>phoenix-lan</td><td>192.168.1.133 (LAN)</td><td>Long-running commands, WireGuard down</td></tr>
    <tr><td>phx</td><td>10.77.0.3 (WireGuard)</td><td>Short alias for phoenix-ext</td></tr>
    <tr><td>windows-host</td><td>10.77.0.1</td><td>SSH back to Windows from WSL</td></tr>
  </table>
  <div class="code-block"><button class="copy-btn" onclick="cp(this)">copy</button><code># Normal login
ssh phoenix-ext

# Long-running command (use LAN to avoid WireGuard timeout)
ssh phoenix-lan "python3 ~/phoenix-devops/sector4/frank/frank_ollama_bridge.py --test"

# Run something with sudo interactively
ssh -t phoenix-lan "sudo systemctl restart phoenix-kernel"</code></div>

  <h2>WireGuard Quick Commands</h2>
  <div class="code-block"><button class="copy-btn" onclick="cp(this)">copy</button><code># WSL — check status
sudo wg show

# WSL — restart mesh
sudo wg-quick down wg0 && sudo wg-quick up wg0

# phoenix-ext — check (already auto-starts on boot)
ssh phoenix-lan "sudo wg show"</code></div>

  <div class="callout tip">
    <div class="callout-title">WireGuard Auto-Starts on WSL</div>
    WSL runs <span class="inline-code">sudo wg-quick up wg0</span> automatically in <span class="inline-code">~/.bashrc</span> (passwordless sudo is configured in <span class="inline-code">/etc/sudoers.d/phoenix-wg</span>).
  </div>
</section>

<!-- APPS -->
<section class="section" id="sec-apps">
  <h1>Apps — Glossary / Review Platform</h1>

  <h2>Glossary <span class="pill ok">LIVE</span></h2>
  <p>The Glossary is the table of contents for the Phoenix clonepool and D1 database. Dark cockpit UI. 135+ entries. Every file that passes intake appears here.</p>
  <div class="key-grid">
    <div class="key-card"><div class="kc-label">URL</div><div class="kc-val">/glossary/</div><div class="kc-sub"><a href="/glossary/" style="color:var(--accent)">Open Glossary</a></div></div>
    <div class="key-card"><div class="kc-label">Search</div><div class="kc-val">/glossary/?q=term</div><div class="kc-sub">URL param or search box</div></div>
    <div class="key-card"><div class="kc-label">Source</div><div class="kc-val">sector2/glossary/</div><div class="kc-sub">glossary.php</div></div>
    <div class="key-card"><div class="kc-label">Backend</div><div class="kc-val">D1 via packages-worker</div><div class="kc-sub">/glossary endpoint</div></div>
  </div>

  <h2>Review Platform <span class="pill ok">LIVE</span></h2>
  <p>General peer review — submit anything: Phoenix additions, projects, questions, ideas, problems. Immutable records. Reviewers earn their way in. Auto-approves at 2 votes.</p>
  <div class="key-grid">
    <div class="key-card"><div class="kc-label">URL</div><div class="kc-val">/review/</div><div class="kc-sub"><a href="/review/" style="color:var(--accent)">Open Review Platform</a></div></div>
    <div class="key-card"><div class="kc-label">Types</div><div class="kc-val">6 submission types</div><div class="kc-sub">addition · project · question · idea · problem · general</div></div>
    <div class="key-card"><div class="kc-label">Votes</div><div class="kc-val">APPROVE / REJECT / ABSTAIN</div><div class="kc-sub">2 approvals = promoted</div></div>
    <div class="key-card"><div class="kc-label">Immutable</div><div class="kc-val">No edit. No delete.</div><div class="kc-sub">Chain of evidence</div></div>
  </div>
</section>

<!-- LIFE FIRST -->
<section class="section" id="sec-lifefirst">
  <h1>Life First (Laurie)</h1>
  <p class="subtitle">Laurie's personal AI assistant — running on phoenix-ext</p>

  <p>Life First is Laurie's AI assistant system. It runs locally on phoenix-ext via Apache + PHP. Laurie's conversations stay on the machine — no data leaves Phoenix.</p>

  <h2>Modules</h2>
  <table>
    <tr><th>Module</th><th>Role</th><th>Status</th></tr>
    <tr><td>Module 2 — API Router</td><td>Main entry point, intent detection, routes to specialists</td><td><span class="pill ok">LIVE</span></td></tr>
    <tr><td>Module 3 — Schedule AI</td><td>Calendar, appointments, time queries</td><td><span class="pill ok">LIVE</span></td></tr>
    <tr><td>Module 4 — Messenger AI</td><td>Cross-phone messaging (Jerry ↔ Laurie)</td><td><span class="pill ok">LIVE</span></td></tr>
    <tr><td>Module 5 — Memory AI</td><td>Preference and memory keeper</td><td><span class="pill ok">LIVE</span></td></tr>
    <tr><td>Module 6 — Notification AI</td><td>Reminders and alerts</td><td><span class="pill ok">LIVE</span></td></tr>
    <tr><td>Module 7 — Voice Commander</td><td>General conversation — Ollama primary, Claude fallback</td><td><span class="pill ok">LIVE</span></td></tr>
  </table>

  <h2>AI Model — llama3.1</h2>
  <p>Laurie's assistant runs on <span class="inline-code">llama3.1</span> (8B) via Ollama. It is dedicated — never shared with the desktop AI pool. The system prompt is tuned for Laurie: clear, literal, no vagueness, no guessing. If Ollama is down, it falls back to the Claude API automatically.</p>

  <div class="callout tip">
    <div class="callout-title">Response time</div>
    First message of the day: ~60s (cold model load into RAM). Subsequent messages: ~15-20s for a typical reply. When Frank pre-warms llama3.1 on boot this will be consistent from the first message.
  </div>

  <h2>Testing Life First</h2>
  <div class="code-block"><button class="copy-btn" onclick="cp(this)">copy</button><code># Health check (from phoenix-ext)
curl -s http://localhost/lifefirst/api.php?action=health

# Test Laurie's voice AI
LF_SECRET=$(grep LF_API_SECRET /etc/lifefirst/lifefirst.env | cut -d= -f2)
curl -s -X POST http://localhost/lifefirst/api.php \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $LF_SECRET" \
  -d '{"username":"laurie","message":"What time is it?"}'</code></div>

  <h2>Frank Bridge</h2>
  <p>Frank can dispatch packets directly to Life First via <span class="inline-code">frank_lifefirst.py</span>. This wires the Phoenix kernel into Laurie's assistant — Frank logs every interaction to the D1 audit chain.</p>
  <div class="code-block"><button class="copy-btn" onclick="cp(this)">copy</button><code># Direct Frank → Life First dispatch
python3 ~/phoenix-devops/sector4/frank/frank_lifefirst.py \
  --user laurie --message "Good morning, what do I have today?"</code></div>
</section>

<!-- OLLAMA -->
<section class="section" id="sec-ollama">
  <h1>Ollama — Self-Hosted AI</h1>
  <p class="subtitle">Local LLM inference on phoenix-ext · No API cost · No data egress</p>

  <h2>Installed Models</h2>
  <table>
    <tr><th>Model</th><th>Size</th><th>Purpose</th><th>Status</th></tr>
    <tr><td>llama3.1</td><td>4.9 GB</td><td>Life First / Laurie — dedicated, never shared</td><td><span class="pill ok">LIVE</span></td></tr>
    <tr><td>llama3.2:3b</td><td>2.0 GB</td><td>Kernel / code fast path</td><td><span class="pill ok">LIVE</span></td></tr>
    <tr><td>deepseek-r1:1.5b</td><td>1.1 GB</td><td>Reasoning — shows chain of thought</td><td><span class="pill ok">LIVE</span></td></tr>
    <tr><td>phi3.5</td><td>2.2 GB</td><td>Chat / conversational desktop AI</td><td><span class="pill warn">PENDING PULL</span></td></tr>
  </table>

  <h2>Benchmark Results (Jun 16, 2026)</h2>
  <div class="key-grid">
    <div class="key-card"><div class="kc-label">llama3.2:3b — Warm</div><div class="kc-val">6.1 tok/s</div><div class="kc-sub">Cold start: 0.7 tok/s (load penalty)</div></div>
    <div class="key-card"><div class="kc-label">llama3.2:3b — Code</div><div class="kc-val">6.1 tok/s</div><div class="kc-sub">422 tokens · 69s</div></div>
    <div class="key-card"><div class="kc-label">Average</div><div class="kc-val">4.1 tok/s</div><div class="kc-sub">MARGINAL — improves with pre-warm</div></div>
    <div class="key-card"><div class="kc-label">Mode</div><div class="kc-val">CPU-only</div><div class="kc-sub">GPU drivers blacklisted by design</div></div>
  </div>

  <div class="callout tip">
    <div class="callout-title">Phoenix Performance Advantage</div>
    When Frank pre-warms models on boot via ProcessLibrary, cold-start penalty disappears. Helix's 300k+ ops/sec memory layer means context lookups never block inference. The system will perform above its hardware class once fully operational.
  </div>

  <h2>Ollama Commands</h2>
  <div class="code-block"><button class="copy-btn" onclick="cp(this)">copy</button><code># List installed models
ollama list

# Pull a model
ollama pull phi3.5

# Remove a model
ollama rm &lt;model&gt;

# Quick test
ollama run llama3.2:3b "What is Frank5?"

# API test
curl http://localhost:11434/api/tags</code></div>
</section>

<!-- FRANK AI -->
<section class="section" id="sec-frank-ai">
  <h1>Frank × Ollama Bridge</h1>
  <p class="subtitle">sector4/frank/frank_ollama_bridge.py</p>

  <p>The bridge routes AI dispatch packets through the Frank proxy wall to local Ollama. All inference stays on phoenix-ext — zero API cost, no data leaves the machine.</p>

  <h2>Routing Logic</h2>
  <table>
    <tr><th>Channel</th><th>Model</th><th>Trigger</th></tr>
    <tr><td>Life First</td><td>llama3.1 (dedicated)</td><td>dispatch_lifefirst() — always this model</td></tr>
    <tr><td>Fast / Kernel</td><td>llama3.2:3b</td><td>Keywords: kernel, frank, helix, code, script, debug…</td></tr>
    <tr><td>Chat</td><td>phi3.5</td><td>Everything else</td></tr>
    <tr><td>Reasoning</td><td>deepseek-r1:1.5b</td><td>Explicit reasoning requests</td></tr>
  </table>

  <h2>CLI Usage</h2>
  <div class="code-block"><button class="copy-btn" onclick="cp(this)">copy</button><code>cd ~/phoenix-devops

# Run benchmark (use phoenix-lan for long sessions)
python3 sector4/frank/frank_ollama_bridge.py --test

# Single prompt
python3 sector4/frank/frank_ollama_bridge.py --prompt "What is Helix?"

# Override model
python3 sector4/frank/frank_ollama_bridge.py --prompt "Explain intake.sh" --model llama3.2:3b

# List available models
python3 sector4/frank/frank_ollama_bridge.py --list</code></div>

  <h2>Python API (from other scripts)</h2>
  <div class="code-block"><button class="copy-btn" onclick="cp(this)">copy</button><code">from sector4.frank.frank_ollama_bridge import dispatch, dispatch_lifefirst

# General dispatch — auto-routes by keyword
result = dispatch({"payload": "Explain the clonepool", "id": "my-packet"})
print(result["response"])  # AI response
print(result["tok_sec"])   # Performance metric

# Life First — always llama3.1, always Laurie's system prompt
result = dispatch_lifefirst("Good morning, what time is it?")
print(result["response"])</code></div>
</section>

<!-- SERVICES -->
<section class="section" id="sec-services">
  <h1>Services &amp; Ports</h1>

  <h2>Systemd Services</h2>
  <div class="code-block"><button class="copy-btn" onclick="cp(this)">copy</button><code"># Status of all Phoenix services
sudo systemctl status phoenix-kernel phoenix-telemetry ollama prometheus

# Restart kernel
sudo systemctl restart phoenix-kernel

# View kernel logs (live)
journalctl -u phoenix-kernel -f

# View telemetry logs
journalctl -u phoenix-telemetry -n 50 --no-pager</code></div>

  <h2>Port Reference</h2>
  <table>
    <tr><th>Port</th><th>Service</th><th>Protocol</th><th>Notes</th></tr>
    <tr><td>7701–7704</td><td>Helix-I</td><td>TCP</td><td>Intake channels — strand A (1,2) + B (3,4)</td></tr>
    <tr><td>7805–7808</td><td>Helix-E</td><td>TCP</td><td>Output channels — strand A (5,6) + B (7,8)</td></tr>
    <tr><td>7347</td><td>Frank HTTP</td><td>HTTP</td><td>Frank proxy wall · /status · /lifefirst/*</td></tr>
    <tr><td>7899</td><td>Telemetry</td><td>WebSocket</td><td>HUD desktop data feed — 2s broadcast</td></tr>
    <tr><td>11434</td><td>Ollama</td><td>HTTP</td><td>Local LLM API — /api/generate /api/tags</td></tr>
    <tr><td>9090</td><td>Prometheus</td><td>HTTP</td><td>Metrics scraper</td></tr>
    <tr><td>80</td><td>Apache</td><td>HTTP</td><td>/glossary /review /lifefirst /manual</td></tr>
    <tr><td>51820</td><td>WireGuard</td><td>UDP</td><td>Mesh VPN hub on Windows</td></tr>
  </table>
</section>

<!-- VAULT -->
<section class="section" id="sec-vault">
  <h1>breach_coms Vault</h1>
  <p class="subtitle">4-tier versioned storage · 4-day custody window</p>

  <p>breach_coms is the Phoenix vault system. Four tiers, four drives. Every file that enters intake lands in T1 and propagates down the tiers over 4 days. This gives a complete 4-day recovery window for any file.</p>

  <h2>Tier Map</h2>
  <table>
    <tr><th>Tier</th><th>Mount</th><th>Drive</th><th>Size</th><th>Role</th></tr>
    <tr><td>T1 PRIMARY</td><td>/breach_coms4</td><td>sdc1</td><td>492 GB</td><td>Master vault — intake writes here</td></tr>
    <tr><td>T2 SECONDARY</td><td>/breach_coms3</td><td>sdb1</td><td>1.8 TB</td><td>Day-1 mirror</td></tr>
    <tr><td>T3 TERTIARY</td><td>/breach_coms2</td><td>sdc2</td><td>1.4 TB</td><td>Day-2 mirror</td></tr>
    <tr><td>T4 TERTIARY</td><td>/breach_coms1</td><td>sda2</td><td>internal</td><td>Day-3 mirror</td></tr>
    <tr><td>Clonepool</td><td>/breach_coms4/clonepool</td><td>—</td><td>—</td><td>Callable face — symlinked to ~/Phoenix/clonepool</td></tr>
  </table>

  <h2>Vault Commands</h2>
  <div class="code-block"><button class="copy-btn" onclick="cp(this)">copy</button><code"># Check vault space
df -h /breach_coms4 /breach_coms3 /breach_coms2 /breach_coms1

# Count clonepool entries
ls /breach_coms4/clonepool | wc -l

# Check a specific entry
ls /breach_coms4/clonepool/&lt;filename&gt;/

# Run propagator (mirrors T1 → T2 → T3 → T4)
python3 ~/phoenix-devops/sector2/propagator/propagator.py</code></div>

  <h2>Propagation Schedule</h2>
  <p>The propagator copies from T1 → T2 → T3 → T4 on a rolling 24-hour basis. After 4 days, the oldest copy in T4 is the archive boundary. This gives the complete "what was it + custody" history for every file.</p>
</section>

<!-- DEPLOY -->
<section class="section" id="sec-deploy">
  <h1>Deploy Scripts</h1>
  <p class="subtitle">All scripts are idempotent — safe to re-run</p>

  <table>
    <tr><th>Script</th><th>What It Does</th><th>Run As</th></tr>
    <tr><td>deploy/setup_phoenix_ext.sh</td><td>Phase 1 — Prometheus, Nextcloud, phoenix-kernel.service</td><td>sudo bash</td></tr>
    <tr><td>deploy/setup_breach_coms.sh</td><td>Format drives, mount tiers, wire fstab, init vault dirs</td><td>sudo bash</td></tr>
    <tr><td>deploy/setup_glossary.sh</td><td>Deploy glossary.php to Apache, wire Phoenix env</td><td>sudo bash</td></tr>
    <tr><td>deploy/setup_review_platform.sh</td><td>Deploy review platform to Apache</td><td>sudo bash</td></tr>
    <tr><td>deploy/setup_ollama.sh</td><td>Install Ollama, pull all 4 models</td><td>sudo bash</td></tr>
    <tr><td>deploy/setup_telemetry.sh</td><td>Install phoenix-telemetry.service, WebSocket port 7899</td><td>sudo bash</td></tr>
    <tr><td>lifefirst_modules/deploy_lifefirst.sh</td><td>Full Life First deploy — MySQL + Apache + all modules</td><td>bash (self-elevates)</td></tr>
  </table>

  <div class="code-block"><button class="copy-btn" onclick="cp(this)">copy</button><code"># Pull latest then run any deploy script
cd ~/phoenix-devops && git pull && sudo bash deploy/&lt;script&gt;.sh

# Full system bootstrap on a new machine
curl -fsSL https://get.authenticcoder.com | bash</code></div>

  <div class="callout tip">
    <div class="callout-title">New Machine Checklist</div>
    1. curl bootstrap → 2. setup_breach_coms.sh → 3. setup_phoenix_ext.sh → 4. setup_ollama.sh → 5. setup_telemetry.sh → 6. deploy_lifefirst.sh
  </div>
</section>

<!-- RULES -->
<section class="section" id="sec-rules">
  <h1>Critical Rules</h1>
  <p class="subtitle">These are never broken. Ever.</p>

  <div class="callout danger"><div class="callout-title">1. Quadralingual until Sector 3 boundary</div>Everything stays quadralingual until translator.sh fires at the Sector 3 output boundary.</div>
  <div class="callout danger"><div class="callout-title">2. translator.sh — OUTPUT ONLY</div>translator.sh fires on output only. Never on intake. Never on clones.</div>
  <div class="callout danger"><div class="callout-title">3. Romeo IN / Juliet OUT</div>Romeo handles ingress at Sector 3. Juliet handles egress. Never swap them.</div>
  <div class="callout danger"><div class="callout-title">4. breach_coms stays quadralingual</div>The breach_coms drives hold the quadralingual vault. Never translate inside them.</div>
  <div class="callout danger"><div class="callout-title">5. Script shebangs</div>All scripts: <span class="inline-code">#!/usr/bin/env bash</span> (external Ubuntu) or <span class="inline-code">zsh</span> (WSL dev). No exceptions.</div>
  <div class="callout danger"><div class="callout-title">6. No GPU drivers</div>GPU drivers are blacklisted. Never suggest GPU-dependent solutions. Phoenix runs CPU-only by design.</div>
  <div class="callout danger"><div class="callout-title">7. Header QR before hash / Footer QR after hash</div>The header QR is generated before the file is hashed. The footer QR is generated after. Never swap.</div>
  <div class="callout danger"><div class="callout-title">8. Never delete from breach_coms4</div>T1 is the master vault. Nothing is ever deleted from /breach_coms4. Propagation goes down — never removes from top.</div>
  <div class="callout danger"><div class="callout-title">9. Real code only</div>Nothing enters the repo unless tested, polished, pro+ status. No demos. No half-finished implementations.</div>
  <div class="callout danger"><div class="callout-title">10. Immutable: reviews, switches, custody chain</div>Once written to D1, review submissions and custody records cannot be edited or deleted.</div>
  <div class="callout danger"><div class="callout-title">11. One repo</div>One repo. One OS. Everything in its sector. No sprawl.</div>
</section>

</main>
</div>

<div id="toast">Copied</div>

<script>
function show(id) {
  document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  const sec = document.getElementById('sec-' + id);
  if (sec) sec.classList.add('active');
  event.currentTarget.classList.add('active');
  window.scrollTo(0, 0);
}

function cp(btn) {
  const code = btn.parentElement.querySelector('code').innerText;
  navigator.clipboard.writeText(code).then(() => {
    const t = document.getElementById('toast');
    t.classList.add('show');
    setTimeout(() => t.classList.remove('show'), 1500);
  });
}
</script>
</body>
</html>
