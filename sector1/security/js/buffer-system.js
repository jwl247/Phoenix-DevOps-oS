/**
 * BUFFER SYSTEM
 * jwl247 / Jerry Leftwich / GPL v3
 *
 * Tiered escalation buffer: NORMAL → ELEVATED → BACKTRACE → SOCK5
 * Feeds guardian events to copes_runtime via the drop-dir seam.
 * Posture: escalate + redirect. NO bounce at any level.
 *
 * Ring role: sits between raw network/process events and
 * signal-capture + lockdown-module. When a session climbs tiers,
 * buffer-system tells signal-capture to capture and lockdown-module
 * to redirect.
 */

'use strict';

const fsp  = require('fs').promises;
const os   = require('os');
const path = require('path');

// Tier constants — exported so callers can reference them by name
const TIER = Object.freeze({
  NORMAL:    'NORMAL',
  ELEVATED:  'ELEVATED',
  BACKTRACE: 'BACKTRACE',
  SOCK5:     'SOCK5',
});

// Tier order for comparison
const TIER_ORDER = [TIER.NORMAL, TIER.ELEVATED, TIER.BACKTRACE, TIER.SOCK5];


class BufferSystem {
  /**
   * @param {object} config
   * @param {number} [config.elevatedThreshold]    Events before NORMAL→ELEVATED (default 5)
   * @param {number} [config.backtraceThreshold]   Events before ELEVATED→BACKTRACE (default 15)
   * @param {number} [config.sock5Threshold]       Events before BACKTRACE→SOCK5 (default 30)
   * @param {number} [config.windowMs]             Count window in ms (default 60 000 = 1 min)
   * @param {number} [config.decayMs]              Auto-decay tier after idle (default 300 000 = 5 min)
   * @param {string} [config.dropDir]              Guardian drop-dir path (defaults to env/default)
   */
  constructor(config = {}) {
    this.version = '1.0.0';

    this.config = {
      elevatedThreshold:  config.elevatedThreshold  ?? 5,
      backtraceThreshold: config.backtraceThreshold ?? 15,
      sock5Threshold:     config.sock5Threshold     ?? 30,
      windowMs:           config.windowMs           ?? 60_000,
      decayMs:            config.decayMs            ?? 300_000,
      dropDir: config.dropDir ||
        process.env.PHOENIX_GUARDIAN_DROPDIR ||
        path.join(os.homedir(), '.unitedsys', 'logs', 'guardian_events.jsonl'),
    };

    // Per-source session state
    // key = sourceIP, value = { tier, events: [{ts}], lastSeen, decayTimer }
    this._sessions = new Map();

    // Wired callbacks — set by caller
    this._onEscalate = null;   // (sourceIP, newTier, session) → void
    this._onDecay    = null;   // (sourceIP, newTier, session) → void

    fsp.mkdir(path.dirname(this.config.dropDir), { recursive: true }).catch(() => {});
    this._log('info', `BufferSystem online | SOCK5 threshold=${this.config.sock5Threshold}`);
  }

  // ── Callbacks ──────────────────────────────────────────────────────────────
  onEscalate(fn) { this._onEscalate = fn; return this; }
  onDecay(fn)    { this._onDecay    = fn; return this; }

  // ── Main ingestion ─────────────────────────────────────────────────────────
  /**
   * Record a network/process event from sourceIP.
   * Returns the current tier and whether an escalation occurred.
   */
  async record(sourceIP, eventMeta = {}) {
    const now = Date.now();
    let session = this._sessions.get(sourceIP);

    if (!session) {
      session = {
        sourceIP,
        tier:      TIER.NORMAL,
        events:    [],
        firstSeen: now,
        lastSeen:  now,
        decayTimer: null,
      };
      this._sessions.set(sourceIP, session);
    }

    session.lastSeen = now;

    // Prune events outside the count window
    const cutoff = now - this.config.windowMs;
    session.events = session.events.filter(e => e.ts >= cutoff);
    session.events.push({ ts: now, ...eventMeta });

    const count = session.events.length;
    const prevTier = session.tier;
    const nextTier = this._computeTier(count);

    // Escalate
    if (TIER_ORDER.indexOf(nextTier) > TIER_ORDER.indexOf(prevTier)) {
      session.tier = nextTier;
      this._log(nextTier === TIER.SOCK5 ? 'critical' : 'warning',
        `ESCALATE ${sourceIP}: ${prevTier} → ${nextTier} | ${count} events in window`);

      // Drop guardian event
      await this._dropEvent(sourceIP, session, nextTier, eventMeta);

      if (this._onEscalate) {
        await this._onEscalate(sourceIP, nextTier, session).catch(err =>
          this._log('error', `onEscalate threw: ${err.message}`));
      }
    }

    // Reset/restart decay timer
    this._resetDecay(session);

    return {
      sourceIP,
      tier:       session.tier,
      escalated:  session.tier !== prevTier,
      eventCount: count,
    };
  }

  // ── Tier computation ───────────────────────────────────────────────────────
  _computeTier(count) {
    if (count >= this.config.sock5Threshold)     return TIER.SOCK5;
    if (count >= this.config.backtraceThreshold) return TIER.BACKTRACE;
    if (count >= this.config.elevatedThreshold)  return TIER.ELEVATED;
    return TIER.NORMAL;
  }

  // ── Decay ──────────────────────────────────────────────────────────────────
  _resetDecay(session) {
    if (session.decayTimer) clearTimeout(session.decayTimer);
    session.decayTimer = setTimeout(() => {
      if (session.tier === TIER.NORMAL) return;
      const prev = session.tier;
      // Step down one tier
      const idx  = TIER_ORDER.indexOf(session.tier);
      session.tier = TIER_ORDER[Math.max(0, idx - 1)];
      session.events = [];
      this._log('info', `DECAY ${session.sourceIP}: ${prev} → ${session.tier}`);
      if (this._onDecay) {
        this._onDecay(session.sourceIP, session.tier, session).catch(() => {});
      }
    }, this.config.decayMs);
  }

  // ── Guardian drop-dir ──────────────────────────────────────────────────────
  async _dropEvent(sourceIP, session, tier, meta) {
    const event = {
      type:       'network_connection',
      sourceIP,
      bufferTier: tier,
      eventCount: session.events.length,
      timestamp:  new Date().toISOString(),
      ...meta,
    };
    try {
      await fsp.appendFile(this.config.dropDir, JSON.stringify(event) + '\n', 'utf8');
    } catch (err) {
      this._log('error', `drop-dir write failed: ${err.message}`);
    }
  }

  // ── Session management ─────────────────────────────────────────────────────
  getSession(sourceIP) {
    return this._sessions.get(sourceIP) || null;
  }

  clearSession(sourceIP) {
    const s = this._sessions.get(sourceIP);
    if (s?.decayTimer) clearTimeout(s.decayTimer);
    this._sessions.delete(sourceIP);
  }

  status() {
    const sessions = [];
    for (const [ip, s] of this._sessions) {
      sessions.push({ ip, tier: s.tier, events: s.events.length, lastSeen: s.lastSeen });
    }
    return {
      version:   this.version,
      sessions:  sessions.filter(s => s.tier !== TIER.NORMAL),
      total:     this._sessions.size,
      thresholds: {
        elevated:  this.config.elevatedThreshold,
        backtrace: this.config.backtraceThreshold,
        sock5:     this.config.sock5Threshold,
      },
    };
  }

  _log(level, message) {
    const ts  = new Date().toISOString();
    const sym = { info: '📘', warning: '⚠️', error: '❌', critical: '🚨' };
    console.log(`${ts} ${sym[level] || '📝'} [BufferSystem] ${message}`);
  }
}

module.exports = { BufferSystem, TIER };
