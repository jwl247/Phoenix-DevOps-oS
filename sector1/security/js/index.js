/**
 * INTEGRATED GUARDIANS — SECURITY SUITE RING INDEX
 * jwl247 / Jerry Leftwich / GPL v3
 *
 * Single import point. Each guardian node requires this file.
 * Ring layout:
 *   Alpha (sector1 — auth/boot)    → ConfigManager, FileMotionSensor, PortGuard
 *   Beta  (sector2 — process/intake)→ BufferSystem, PortGuard, ConfigManager
 *   Gamma (sector3 — network/file)  → HeIXVRM, SignalCapture, FileMotionSensor, PortGuard
 *   Delta (sector4 — custody/vault) → LockdownModule, ConfigManager, FileMotionSensor
 *
 * All four nodes:
 *   const suite = require('./index');
 *   const { alpha, beta, gamma, delta } = suite.rings;
 *
 * Or pick one ring:
 *   const { ConfigManager, PortGuard } = require('./index');
 *
 * Posture: detect + redirect. No retaliation at any tier.
 * Drop-dir: PHOENIX_GUARDIAN_DROPDIR env → ~/.unitedsys/logs/guardian_events.jsonl
 */

'use strict';

// ── Core exports ──────────────────────────────────────────────────────────────
const { FileMotionSensor, HashingModule } = require('./file-motion-sensor');
const HeIXVRM                             = require('./helix-vrm');
const SignalCapture                       = require('./signal-capture');
const { BufferSystem, TIER }              = require('./buffer-system');
const LockdownModule                      = require('./lockdown-module');
const ConfigManager                       = require('./config-manager');
const { PortGuard, DEFAULT_WATCH_PORTS }  = require('./port-guard');
const { QuadComms, ringCommsHealth, NODES } = require('./quad-comms');

// ── Ring factory ──────────────────────────────────────────────────────────────
/**
 * Build the full four-node security ring with shared drop-dir wiring.
 * Each node gets the modules it owns; event flow is pre-wired.
 *
 * @param {object} [options]
 * @param {string} [options.dropDir]      Override PHOENIX_GUARDIAN_DROPDIR
 * @param {string} [options.honeypotUrl]  Override PHOENIX_HONEYPOT_URL
 * @param {boolean}[options.startPolling] Auto-start all pollers (default false)
 *
 * @returns {{ alpha, beta, gamma, delta, teardown }}
 */
function buildRing(options = {}) {
  const base = {
    dropDir:    options.dropDir    || process.env.PHOENIX_GUARDIAN_DROPDIR,
    honeypotUrl:options.honeypotUrl|| process.env.PHOENIX_HONEYPOT_URL,
  };

  // ── Alpha — Sector 1 — auth / boot ─────────────────────────────────────────
  const alpha = {
    nodeId:        'alpha',
    quadComms:     new QuadComms('alpha'),
    configManager: new ConfigManager('alpha', { dropDir: base.dropDir }),
    portGuard:     new PortGuard('alpha', { dropDir: base.dropDir }),
    // Motion: system paths + every sector1 entry point
    motionSensor:  new FileMotionSensor({
      dropGuardianEvents: true,
      watchedPaths: [
        // System integrity (default Phoenix paths)
        '/etc/passwd', '/etc/shadow', '/etc/sudoers', '/root/.ssh', '/root/.bashrc',
        '/etc/phoenix',
        '/usr/bin', '/usr/sbin', '/usr/local/bin',
        '/var/www/html',
        // Sector 1 entry points
        'sector1/',
        'sector1/auth/phoenix_auth.py',
        'sector1/helix/',
        'sector1/kernels/',
        'sector1/concierge/concierge.c',
        'sector1/concierge/bridge.py',
        'sector1/concierge/linux_concierge.py',
        'sector1/kernel/genie/',         // Genie — Universal Kernel
      ],
    }),
  };

  // ── Beta — Sector 2 — process / intake ────────────────────────────────────
  const beta = {
    nodeId:        'beta',
    quadComms:     new QuadComms('beta'),
    bufferSystem:  new BufferSystem({ dropDir: base.dropDir }),
    portGuard:     new PortGuard('beta', { dropDir: base.dropDir }),
    configManager: new ConfigManager('beta', { dropDir: base.dropDir }),
    // Motion: every sector2 entry point — Frank, intake, package handler, propagator
    motionSensor:  new FileMotionSensor({
      dropGuardianEvents: true,
      watchedPaths: [
        'sector2/',
        'sector2/frank/frank_helix.py',
        'sector2/frank/frank_save.py',
        'sector2/frank/frank_http.py',
        'sector2/frank/frank_client.js',
        'sector2/ring0/frankenhelix.py',
        'sector2/propagator/propagator.py',
        'sector2/propagator/dispatch.json',
        'sector2/package-handler/worker/',
        'sector2/package-handler/intake.sh',
        'sector2/apps/lifefirst/',
        'sector2/apps/scriptforge/',
      ],
    }),
  };

  // ── Gamma — Sector 3 — network / file ─────────────────────────────────────
  const lockdown   = new LockdownModule({ honeypotUrl: base.honeypotUrl });
  const sigCapture = new SignalCapture();

  // Wire: at SOCK5 escalation → SignalCapture captures → LockdownModule redirects
  beta.bufferSystem.onEscalate(async (sourceIP, tier, session) => {
    if (tier === TIER.SOCK5) {
      const signal = await sigCapture.captureSignal({
        sourceIP,
        severity:    'critical',
        bufferLevel: tier,
        bufferSession: session,
      });
      if (signal) await lockdown.redirectToHoneypot(signal);
    }
  });

  const gamma = {
    nodeId:       'gamma',
    quadComms:    new QuadComms('gamma'),
    vrmLayer:     new HeIXVRM({ honeypotUrl: base.honeypotUrl }),
    signalCapture: sigCapture,
    portGuard:    new PortGuard('gamma', { dropDir: base.dropDir }),
    lockdown,
    // Motion: sector3 entry points — romeo/juliet/translator/quadengine
    motionSensor: new FileMotionSensor({
      dropGuardianEvents: true,
      watchedPaths: [
        'sector3/',
        'sector3/translator/translator.sh',
        'sector3/romeo_juliet/romeo.py',
        'sector3/romeo_juliet/juliet.py',
        'sector3/romeo_juliet/dbl_juliet.py',
        'sector3/quadengine/quadengine.py',
        'sector3/services/',
        // Network-side system paths
        '/etc/hosts',
        '/etc/resolv.conf',
        '/etc/iptables/',
        '/etc/firewalld/',
      ],
    }),
  };

  // ── Delta — Sector 4 — custody / vault ────────────────────────────────────
  const delta = {
    nodeId:        'delta',
    quadComms:     new QuadComms('delta'),
    lockdown,                     // shared with Gamma — one redirect authority
    configManager: new ConfigManager('delta', { dropDir: base.dropDir }),
    // Motion: vault mounts + sector4 entry points
    motionSensor:  new FileMotionSensor({
      dropGuardianEvents: true,
      watchedPaths: [
        // Physical vault mounts (breach_coms → Debian VM paths)
        '/mnt/g',   // breach_coms4 — T1 PRIMARY master vault
        '/mnt/f',   // breach_coms3 — T2
        '/mnt/e',   // breach_coms2 — T3 / clonepool
        '/mnt/d',   // breach_coms1 — T4
        // Sector 4 entry points
        'sector4/',
        'sector4/intake/intake.sh',
        'sector4/vault/phoenix-push.sh',
        'sector4/vault/download.sh',
        'sector4/paging.py',
        'sector4/paging_windows.py',
        'sector4/pcs.py',
      ],
    }),
  };

  // ── Optional auto-start ────────────────────────────────────────────────────
  if (options.startPolling) {
    // Alpha — sector1 / auth
    alpha.portGuard.startPolling();
    alpha.motionSensor.startMonitoring();   // paths already set in constructor
    alpha.configManager.startPolling();

    // Beta — sector2 / process
    beta.portGuard.startPolling();
    beta.motionSensor.startMonitoring();
    beta.configManager.startPolling();

    // Gamma — sector3 / network
    gamma.portGuard.startPolling();
    gamma.motionSensor.startMonitoring();

    // Delta — sector4 / vault
    delta.motionSensor.startMonitoring();
    delta.configManager.startPolling();
  }

  // ── Teardown helper ────────────────────────────────────────────────────────
  function teardown() {
    for (const node of [alpha, beta, gamma, delta]) {
      node.portGuard?.stopPolling();
      node.motionSensor?.stopMonitoring();
      node.configManager?.stopPolling();
    }
    beta.bufferSystem.status();  // flush / log final state
  }

  return { alpha, beta, gamma, delta, teardown };
}


// ── Suite status ──────────────────────────────────────────────────────────────
function suiteStatus(ring) {
  const { alpha, beta, gamma, delta } = ring;
  return {
    alpha: {
      portGuard:     alpha.portGuard.status(),
      configManager: alpha.configManager.status(),
    },
    beta: {
      bufferSystem:  beta.bufferSystem.status(),
      portGuard:     beta.portGuard.status(),
      configManager: beta.configManager.status(),
    },
    gamma: {
      vrm:           gamma.vrmLayer.getMemoryStatus(),
      signalCapture: gamma.signalCapture.getStatus(),
      portGuard:     gamma.portGuard.status(),
      lockdown:      gamma.lockdown.status(),
    },
    delta: {
      configManager: delta.configManager.status(),
      lockdown:      delta.lockdown.status(),
    },
  };
}


// ── Exports ───────────────────────────────────────────────────────────────────
module.exports = {
  // Raw class exports — for custom wiring
  FileMotionSensor,
  HashingModule,
  HeIXVRM,
  SignalCapture,
  BufferSystem,
  TIER,
  LockdownModule,
  ConfigManager,
  PortGuard,
  DEFAULT_WATCH_PORTS,
  QuadComms,
  ringCommsHealth,
  NODES,

  // Ring factory
  buildRing,
  suiteStatus,
};
