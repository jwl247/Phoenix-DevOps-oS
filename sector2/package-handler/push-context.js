#!/usr/bin/env node
// push-context.js — Phoenix Context Push (pbmii edition)
// Reads secrets from phoenix-secrets.env, pushes /meta/framework + /meta/status
// Run: node push-context.js  (or via push-context.bat)
// JWL 2026-10-02

'use strict';
const fs   = require('fs');
const path = require('path');

// ── Load secrets env file ─────────────────────────────────────────────────────
const SECRETS_PATH = process.env.PHOENIX_SECRETS ||
    'F:\\Phoenix\\vault\\secrets\\phoenix-secrets.env';

if (fs.existsSync(SECRETS_PATH)) {
  for (const line of fs.readFileSync(SECRETS_PATH, 'utf8').split('\n')) {
    const m = line.match(/^([A-Z0-9_]+)=(.+)$/);
    if (m && !process.env[m[1]]) process.env[m[1]] = m[2].trim().replace(/^['"]|['"]$/g,'');
  }
  console.log('[ok] secrets loaded from', SECRETS_PATH);
} else {
  console.log('[warn] secrets file not found at', SECRETS_PATH, '— using env vars');
}

const WORKER_URL = process.env.PHOENIX_WORKER_URL || 'https://packages-worker.phoenix-jwl.workers.dev';
const AUTH       = process.env.PHOENIX_AUTH;
const CF_ID      = process.env.CF_ACCESS_CLIENT_ID;
const CF_SECRET  = process.env.CF_ACCESS_CLIENT_SECRET;
const ROOT       = process.env.PHOENIX_ROOT || 'F:\\Phoenix\\Phoenix-DevOps-oS';

if (!AUTH) { console.error('ERROR: PHOENIX_AUTH not set'); process.exit(1); }

const HEADERS = {
  'Content-Type':  'application/json',
  'Authorization': `Bearer ${AUTH}`,
  ...(CF_ID     ? { 'CF-Access-Client-Id':     CF_ID }     : {}),
  ...(CF_SECRET ? { 'CF-Access-Client-Secret': CF_SECRET } : {}),
};

function log(msg) { console.log(`[${new Date().toISOString().slice(11,19)}] ${msg}`); }

function chk(rel) { try { return fs.existsSync(path.join(ROOT, rel)); } catch { return false; } }
function mt(rel)  {
  try { return fs.statSync(path.join(ROOT, rel)).mtime.toISOString(); }
  catch { return null; }
}

async function metaPut(key, data) {
  const blob = JSON.stringify(data, null, 2);
  log(`  /meta/${key} — ${blob.length} bytes`);
  try {
    const res = await fetch(`${WORKER_URL}/meta/${key}`, {
      method: 'PUT', headers: HEADERS, body: blob,
    });
    const text = await res.text().catch(() => '');
    if (res.ok) {
      const d = JSON.parse(text);
      log(`  stored: ${d.bytes ?? '?'} bytes`);
    } else if (text.includes('Cloudflare Access') || text.includes('Sign in')) {
      log(`  BLOCKED by Cloudflare Access — set CF_ACCESS_CLIENT_ID + CF_ACCESS_CLIENT_SECRET (the usys-cli service token). Never remove the Access policy (XCUT-S16).`);
    } else {
      log(`  ERROR ${res.status}: ${text.slice(0,100)}`);
    }
  } catch(e) { log(`  ERROR: ${e.message}`); }
}

const NOW = new Date().toISOString();

const framework = {
  generated: NOW, source: 'pbmii-push-context',
  description: 'Phoenix DevOps OS architecture map. Read before touching anything.',
  sectors: {
    sector1: {
      name: 'Data / Sync Engine', status: 'intact', last_audited: '2026-10-02',
      canonical_files: {
        helix_complete_stack: 'sector1/helix/helix_complete_stack.py',
        helixi:               'sector1/helix-lightning/helixi.py',
        helixe:               'sector1/helix-lightning/helixe.py',
        franken5:             'sector1/helix-lightning/franken5.py',
      },
      helix_suits: ['frank3_slot_a','frank3_slot_b','concierge','clone_pool',
                    'packages_worker','helix','freewheeling','propcoms','conductor'],
      notes: [
        'helix_complete_stack.py audited 2026-10-02 — all 9 suits intact',
        'Dandelion: 64-lane EMA thermal (HX_LANES=64, HX_TICK_MS=1000)',
        'HelixHostProfile: auto-detects OS/RAM, scales L1-L5',
      ],
      compaq_config: {
        helixi: 'HELIX_I_BIND=0.0.0.0 in /etc/default/helix-ingress',
        helixe: 'HELIX_E_BIND=0.0.0.0 in /etc/default/helix-egress',
      },
    },
    sector2: {
      name: 'Package Handler / Atlas / Clonepool', status: 'live',
      canonical_files: {
        worker:            'sector2/package-handler/worker/index.js',
        parse_connections: 'sector2/package-handler/parse-connections.js',
        run_atlas:         'sector2/package-handler/run-atlas.bat',
        connections_md:    'sector2/CONNECTIONS.md',
      },
      worker: {
        url: WORKER_URL, version: 'e295b1d0-bcdc-48a2-ade7-dec04b7228e5', deployed: '2026-10-02',
      },
      bindings: {
        D1: { binding: 'PHOENIX_DB', database: 'phoenix_dev_db', id: '27958687-4349-47ed-8b6a-dbc4ab29730f' },
        R2: { binding: 'CLONEPOOL_BUCKET', bucket: 'phoenix-clonepool' },
      },
      r2_accounts: {
        jw_account:    { account_id: 'ed936f2c71a0d788e39b8f44200df76d', bucket: 'phoenix-clonepool', role: 'source-of-truth' },
        jerry_account: { account_id: '4190f723a3b308062bed1b797e70e527', bucket: 'phoenix-roadtest',  role: 'R&D sync target' },
      },
    },
    sector3: {
      name: 'Decoy Zone', status: 'decoy-zone',
      decoys: [{ path: 'sector3/workers/packages-worker/', trip_wire: 'wrangler.jsonc → STALE-COPY file' }],
    },
    sector4: { name: 'AI / ML', status: 'pending' },
  },
  mesh_nodes: {
    pbmii:      { tailscale_ip: '100.72.7.92',  os: 'windows', role: 'primary dev', status: 'active' },
    'pbm-compaq': { tailscale_ip: '100.94.101.53', os: 'linux', role: 'first R&D node', status: 'commissioning',
                    setup_needed: ['npm + wrangler install', 'wrangler login', 'helix systemd units'] },
  },
  auth_rules: [
    'PHOENIX_AUTH = Worker secret + env var in phoenix-secrets.env',
    'NEVER run wrangler secret put PHOENIX_AUTH by hand — use rotate-phoenix-auth.sh',
    'All packages-worker routes: Authorization: Bearer <PHOENIX_AUTH>',
    'CF_ACCESS_CLIENT_ID + CF_ACCESS_CLIENT_SECRET bypass Cloudflare Access wall',
    'R2 nodes never hold direct credentials — all via packages-worker',
  ],
  trip_wires: [
    'NEVER deploy from sector3/workers/packages-worker/',
    'NEVER run wrangler secret put PHOENIX_AUTH directly',
    'sector2/package-handler/r2-worker/ retired 2026-09-25',
    'translator.sh OUTPUT ONLY — never intake or clone',
    'Tailscale sole mesh VPN — WireGuard retired 2026-10-01',
  ],
  pending_work: [
    'Compaq: npm + wrangler install, wrangler login, helix systemd units',
    'R2 sync: phoenix-roadtest (jerry acct) ← phoenix-clonepool (jw acct)',
    'parse-connections.js: fix stale worker_version 324b61b9 → e295b1d0',
    'HUD wire-in (PHOENIX_LIFEFIRST_MCP_TOKEN)',
    'Intake pipeline: canonical intake.sh vs intake.py',
    'Monster Phoenix GDD: bracket/prize-pool economy section',
  ],
};

const status = {
  generated: NOW, overall: 'green',
  workers: {
    'packages-worker': {
      live: true, url: WORKER_URL,
      version: 'e295b1d0-bcdc-48a2-ade7-dec04b7228e5', deployed: '2026-10-02',
    },
  },
  helix:   { intact: true, suits: 9, last_audited: '2026-10-02' },
  d1:      { phoenix_dev_db: { id: '27958687-4349-47ed-8b6a-dbc4ab29730f', node_count: 247 } },
  r2: {
    'phoenix-clonepool': { account: 'jw.leftwich1',    status: 'live', role: 'source-of-truth' },
    'phoenix-roadtest':  { account: 'jerry.leftwich1', status: 'live', role: 'needs sync from clonepool' },
  },
  compaq: { status: 'commissioning', next: 'npm install -g wrangler && wrangler login' },
  file_checks: {
    'worker/index.js':         chk('sector2/package-handler/worker/index.js'),
    'parse-connections.js':    chk('sector2/package-handler/parse-connections.js'),
    'helix_complete_stack.py': chk('sector1/helix/helix_complete_stack.py'),
    'helixe.py':               chk('sector1/helix-lightning/helixe.py'),
    'helixi.py':               chk('sector1/helix-lightning/helixi.py'),
  },
  mtimes: {
    'helix_complete_stack.py': mt('sector1/helix/helix_complete_stack.py'),
    'helixe.py':               mt('sector1/helix-lightning/helixe.py'),
    'helixi.py':               mt('sector1/helix-lightning/helixi.py'),
    'worker/index.js':         mt('sector2/package-handler/worker/index.js'),
  },
};

(async () => {
  log('=== Phoenix Context Push ===');
  log(`worker: ${WORKER_URL}`);
  log(`root:   ${ROOT}`);
  log(`CF Access headers: ${CF_ID ? 'YES' : 'no'}`);
  await metaPut('framework', framework);
  await metaPut('status',    status);
  log('=== Done ===');
})();
