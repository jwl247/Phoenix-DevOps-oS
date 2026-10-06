/**
 * INTEGRATED GUARDIANS — TEST HARNESS
 * jwl247 / Jerry Leftwich / GPL v3
 *
 * Run: node test-suite.js
 *
 * SWITCH: set FULL=1 to run all tests including slow polls.
 *   node test-suite.js         — fast smoke tests
 *   FULL=1 node test-suite.js  — full suite (takes ~30s)
 *
 * Tests:
 *   1. Ring builds clean (all 4 nodes)
 *   2. FileMotionSensor watches defaults, detects baseline
 *   3. BufferSystem escalates through NORMAL→ELEVATED→BACKTRACE→SOCK5
 *   4. SignalCapture identifies attack types
 *   5. LockdownModule redirects (never bounces)
 *   6. ConfigManager snapshots and detects drift
 *   7. PortGuard toggle switch + manual event injection
 *   8. Drop-dir events are written (PHOENIX_GUARDIAN_DROPDIR)
 *   9. suiteStatus() returns all 4 nodes
 *  10. FULL only — FileMotionSensor monitor loop fires at least once
 */

'use strict';

const os   = require('os');
const fsp  = require('fs').promises;
const path = require('path');

// ── SWITCH ────────────────────────────────────────────────────────────────────
const FULL = process.env.FULL === '1';

// Use a temp drop-dir so we don't pollute production logs during tests
const TEST_DROP_DIR = path.join(os.tmpdir(), `phoenix-test-${Date.now()}`, 'guardian_events.jsonl');
process.env.PHOENIX_GUARDIAN_DROPDIR = TEST_DROP_DIR;

const {
  buildRing, suiteStatus,
  FileMotionSensor, SignalCapture, BufferSystem, TIER,
  LockdownModule, ConfigManager, PortGuard,
} = require('./index');

// ── Helpers ───────────────────────────────────────────────────────────────────
let passed = 0;
let failed = 0;

function ok(label, condition, extra = '') {
  if (condition) {
    console.log(`  ✅ ${label}`);
    passed++;
  } else {
    console.error(`  ❌ FAIL: ${label}${extra ? ' — ' + extra : ''}`);
    failed++;
  }
}

function header(title) {
  console.log(`\n── ${title} ${'─'.repeat(60 - title.length)}`);
}

async function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

// ── TEST RUNNER ───────────────────────────────────────────────────────────────
async function run() {
  await fsp.mkdir(path.dirname(TEST_DROP_DIR), { recursive: true });

  // ── 1. Build ring ──────────────────────────────────────────────────────────
  header('1. Ring build');
  const ring = buildRing({ startPolling: false });
  ok('alpha node exists',     !!ring.alpha);
  ok('beta node exists',      !!ring.beta);
  ok('gamma node exists',     !!ring.gamma);
  ok('delta node exists',     !!ring.delta);
  ok('teardown is a fn',      typeof ring.teardown === 'function');
  ok('alpha.configManager',   !!ring.alpha.configManager);
  ok('beta.bufferSystem',     !!ring.beta.bufferSystem);
  ok('gamma.vrmLayer',        !!ring.gamma.vrmLayer);
  ok('delta.lockdown',        !!ring.delta.lockdown);

  // ── 2. FileMotionSensor ────────────────────────────────────────────────────
  header('2. FileMotionSensor');
  const sensor = new FileMotionSensor({ checkInterval: 500 });
  sensor.watchDefaults();
  ok('watchedPaths > 0', sensor.watchedPaths.size > 0);
  const snap = await sensor.createSnapshot('/etc');
  ok('snapshot has path',      snap.path === '/etc');
  ok('snapshot has timestamp', typeof snap.timestamp === 'number');
  const st = sensor.status();
  ok('status.monitoring false before start', st.monitoring === false);
  ok('status.guardianDropDir set', !!st.guardianDropDir);

  // ── 3. BufferSystem escalation ────────────────────────────────────────────
  header('3. BufferSystem escalation');
  const buf = new BufferSystem({
    elevatedThreshold:  2,
    backtraceThreshold: 4,
    sock5Threshold:     6,
    windowMs:           60_000,
    dropDir: TEST_DROP_DIR,
  });

  let escalations = [];
  buf.onEscalate(async (ip, tier) => { escalations.push({ ip, tier }); });

  const r1 = await buf.record('10.0.0.1');
  ok('First record: NORMAL',      r1.tier === TIER.NORMAL);
  ok('First record: no escalate', !r1.escalated);

  await buf.record('10.0.0.1');
  const r3 = await buf.record('10.0.0.1');  // hits elevatedThreshold=2 (count=2 in window before this, now 3)
  ok('ELEVATED reached',  escalations.some(e => e.tier === TIER.ELEVATED), JSON.stringify(escalations));

  await buf.record('10.0.0.1');
  await buf.record('10.0.0.1');
  const r6 = await buf.record('10.0.0.1');
  ok('BACKTRACE reached', escalations.some(e => e.tier === TIER.BACKTRACE), JSON.stringify(escalations));

  await buf.record('10.0.0.1');
  const r8 = await buf.record('10.0.0.1');
  ok('SOCK5 reached',     escalations.some(e => e.tier === TIER.SOCK5), JSON.stringify(escalations));

  const bs = buf.status();
  ok('status.sessions present',    bs.sessions.length > 0);

  // ── 4. SignalCapture ───────────────────────────────────────────────────────
  header('4. SignalCapture');
  const sc = new SignalCapture({ captureDir: path.join(os.tmpdir(), 'sc-test') });

  const sqlSig = await sc.captureSignal({
    sourceIP: '10.0.0.2',
    rawPayload: "' OR 1=1 --",
    path: '/login',
    requestCount: 3,
  });
  ok('SQL injection identified', sqlSig?.attackType === 'sqlInjection',
    `got: ${sqlSig?.attackType}`);

  const whiteSig = await sc.captureSignal({ sourceIP: '127.0.0.1' });
  ok('Localhost whitelisted', whiteSig === null);

  const cmdSig = await sc.captureSignal({
    sourceIP: '10.0.0.3',
    rawPayload: 'ls | cat /etc/passwd',
  });
  ok('Command injection identified', cmdSig?.attackType === 'commandInjection',
    `got: ${cmdSig?.attackType}`);

  const scStatus = sc.getStatus();
  ok('capturedSignals >= 2', scStatus.capturedSignals >= 2);

  // ── 5. LockdownModule — redirect, not bounce ───────────────────────────────
  header('5. LockdownModule');
  const lm = new LockdownModule({ honeypotUrl: 'http://127.0.0.1:8888/honeypot' });
  const redirect = await lm.redirectToHoneypot(sqlSig);
  ok('Redirect record returned',   !!redirect);
  ok('Action is redirect',         redirect.action     === 'redirect');
  ok('Posture is redirect_only',   redirect.posture    === 'redirect_only');
  ok('Target is honeypot URL',     redirect.target.includes('honeypot'));
  ok('No bounce field',            redirect.bounce     === undefined);
  ok('No jmeter field',            redirect.jmeter     === undefined);
  ok('redirectCount incremented',  lm.status().totalRedirects === 1);

  // ── 6. ConfigManager ──────────────────────────────────────────────────────
  header('6. ConfigManager');
  const cm = new ConfigManager('gamma', {
    dropDir:  TEST_DROP_DIR,
    watchFiles: ['/etc/hostname', '/etc/os-release'],
    pollIntervalMs: 999_999,   // don't auto-poll during test
  });

  const baseline = await cm.captureBaseline();
  ok('Baseline captured',        Array.isArray(baseline));
  ok('Baseline nodeId gamma',    cm.nodeId === 'gamma');

  const drift = await cm.checkDrift();
  ok('No drift on clean check',  drift.length === 0, JSON.stringify(drift));

  const cmStatus = cm.status();
  ok('baselineSet true',         cmStatus.baselineSet === true);
  ok('polling false',            cmStatus.polling     === false);

  // ── 7. PortGuard toggle switch ─────────────────────────────────────────────
  header('7. PortGuard toggle');
  const pg = new PortGuard('beta', { dropDir: TEST_DROP_DIR, pollIntervalMs: 999_999 });

  ok('Enabled by default',       pg.config.enabled === true);
  pg.disable();
  ok('Disable works',            pg.config.enabled === false);
  pg.enable();
  ok('Enable works',             pg.config.enabled === true);
  const toggled = pg.toggle();
  ok('Toggle returns new state', toggled === false);
  pg.enable();

  // Inject a manual event
  const injected = await pg.injectEvent('10.0.0.9', 1080, { reason: 'test_socks5' });
  ok('Injected event has type',       injected.type    === 'network_connection');
  ok('Injected event has port 1080',  injected.port    === 1080);
  ok('Injected event has sourceIP',   injected.sourceIP === '10.0.0.9');

  const pgStatus = pg.status();
  ok('totalEvents >= 1', pgStatus.totalEvents >= 1);

  // ── 8. Drop-dir events written ─────────────────────────────────────────────
  header('8. Drop-dir');
  await sleep(200);  // Give async writes a moment
  let dropContents = '';
  try {
    dropContents = await fsp.readFile(TEST_DROP_DIR, 'utf8');
  } catch { /* file may not exist if no events written — that's the failure */ }

  const lines = dropContents.split('\n').filter(Boolean);
  ok('Drop-dir has events',          lines.length > 0, `got ${lines.length} lines`);
  const parsed = lines.map(l => { try { return JSON.parse(l); } catch { return null; }}).filter(Boolean);
  ok('All lines valid JSON',         parsed.length === lines.length);
  ok('Events have type field',       parsed.every(e => e.type));
  ok('Events have timestamp field',  parsed.every(e => e.timestamp));

  // ── 9. suiteStatus ─────────────────────────────────────────────────────────
  header('9. suiteStatus');
  const status = suiteStatus(ring);
  ok('alpha in status',  !!status.alpha);
  ok('beta in status',   !!status.beta);
  ok('gamma in status',  !!status.gamma);
  ok('delta in status',  !!status.delta);
  ok('alpha.portGuard',  !!status.alpha.portGuard);
  ok('beta.bufferSystem',!!status.beta.bufferSystem);
  ok('gamma.vrm',        !!status.gamma.vrm);
  ok('gamma.lockdown',   !!status.gamma.lockdown);

  // ── 10. FULL: monitor loop ──────────────────────────────────────────────────
  if (FULL) {
    header('10. FileMotionSensor live loop (FULL mode — ~5s)');
    const liveSensor = new FileMotionSensor({ checkInterval: 500 });
    liveSensor.watchDefaults();
    let monitorFired = false;
    liveSensor.startMonitoring();
    await sleep(1500);
    const liveSt = liveSensor.status();
    ok('Monitoring true after start', liveSt.monitoring === true);
    liveSensor.stopMonitoring();
    ok('Monitoring false after stop', liveSensor.status().monitoring === false);
  } else {
    console.log('\n── 10. FileMotionSensor live loop (skipped — set FULL=1 to run)');
  }

  // ── Teardown ────────────────────────────────────────────────────────────────
  ring.teardown();

  // ── Summary ─────────────────────────────────────────────────────────────────
  const total = passed + failed;
  console.log(`\n${'═'.repeat(64)}`);
  console.log(`RESULT: ${passed}/${total} passed  ${failed > 0 ? '❌ ' + failed + ' FAILED' : '✅ ALL PASS'}`);
  console.log(`Drop-dir: ${TEST_DROP_DIR}`);
  if (!FULL) console.log('Tip: FULL=1 node test-suite.js runs the live monitor loop');
  console.log('═'.repeat(64));

  process.exit(failed > 0 ? 1 : 0);
}

run().catch(err => {
  console.error('Unhandled test error:', err);
  process.exit(1);
});
