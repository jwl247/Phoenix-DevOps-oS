/**
 * SIGNAL CAPTURE MODULE
 * jwl247 / Jerry Leftwich / GPL v3
 *
 * Captures malicious attack signals for intelligence and evidence.
 * Posture: capture + redirect to honeypot. NO retaliation, NO replay.
 * Captured signals are written to disk as forensic evidence only.
 *
 * Feeds into: buffer-system → lockdown-module (redirect path)
 * Was: SignalMirrorBouncer — JMeter bounce chain removed entirely.
 */

'use strict';

const fsp  = require('fs').promises;
const os   = require('os');
const path = require('path');


class SignalCapture {
  /**
   * @param {object} config
   * @param {string} [config.captureDir]      Where signals are written as evidence
   * @param {string[]} [config.whitelistIPs]  IPs never escalated (loopback etc.)
   */
  constructor(config = {}) {
    this.version = '2.0.0';

    this.config = {
      captureDir:   config.captureDir ||
        path.join(os.homedir(), '.unitedsys', 'logs', 'captured-signals'),
      whitelistIPs: config.whitelistIPs || ['127.0.0.1', '::1', 'localhost'],

      recognizePatterns: {
        bruteForce:       true,
        sqlInjection:     true,
        xss:              true,
        commandInjection: true,
        pathTraversal:    true,
        portScan:         true,
        sock5Tunnel:      true,
      },

      ...config,
    };

    this.state = {
      capturedSignals: [],
    };

    fsp.mkdir(this.config.captureDir, { recursive: true }).catch(() => {});
    this._log('info', 'Signal Capture online — evidence-only posture');
  }

  // ── Main capture entry point ─────────────────────────────────────────────
  /**
   * Capture a signal from an incoming incident. Saves evidence to disk.
   * Returns the signal record for the caller (buffer-system or lockdown-module).
   */
  async captureSignal(incident) {
    if (this._isWhitelisted(incident.sourceIP)) {
      this._log('info', `Skipping whitelisted IP: ${incident.sourceIP}`);
      return null;
    }

    const signal = {
      id:          `signal_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
      timestamp:   Date.now(),
      sourceIP:    incident.sourceIP    || 'unknown',
      sourcePort:  incident.sourcePort  || 0,
      targetPath:  incident.path        || '/',
      attackType:  await this._identifyAttackType(incident),
      payload:     this._extractPayload(incident),
      requestCount:this._countRequests(incident),
      pattern:     this._analyzePattern(incident),
      severity:    incident.severity    || 'medium',
      bufferLevel: incident.bufferLevel || null,
    };

    this.state.capturedSignals.push(signal);
    this._log('info', `Signal captured: ${signal.attackType} from ${signal.sourceIP} | ${signal.requestCount} reqs`);

    // Persist evidence — immutable record, never replayed
    await this._saveSignal(signal);

    return signal;
  }

  // ── Attack identification ─────────────────────────────────────────────────
  async _identifyAttackType(incident) {
    const payload = String(incident.payload || incident.rawPayload || '');
    const target  = String(incident.path || '');

    const indicators = {
      bruteForce:       [
        () => (incident.requestCount || 0) > 50,
        () => incident.failedAuth === true,
        () => incident.pattern?.type === 'repeated_login',
      ],
      sqlInjection:     [
        () => /('|"|;|--|\*|union\s|select\s|drop\s|insert\s)/i.test(payload),
        () => target.includes('?'),
      ],
      xss:              [
        () => /<script|javascript:|onerror=/i.test(payload),
      ],
      commandInjection: [
        () => /(\||;|&|`|\$\(|\$\{)/i.test(payload),
      ],
      pathTraversal:    [
        () => /\.\.\/|\.\.\\/.test(target),
      ],
      portScan:         [
        () => (incident.connectionAttempts || 0) > 10,
        () => incident.pattern?.type === 'sequential_ports',
      ],
      sock5Tunnel:      [
        () => incident.bufferLevel === 'SOCK5',
        () => incident.proxyDetected === true,
      ],
    };

    for (const [type, checks] of Object.entries(indicators)) {
      if (checks.some(fn => fn())) return type;
    }
    return 'unknown';
  }

  // ── Pattern analysis ──────────────────────────────────────────────────────
  _extractPayload(incident) {
    return {
      raw:     incident.rawPayload || '',
      headers: incident.headers    || {},
      params:  incident.params     || {},
      body:    incident.body       || '',
    };
  }

  _countRequests(incident) {
    return incident.requestCount || incident.connectionAttempts || 1;
  }

  _analyzePattern(incident) {
    return {
      type:      incident.pattern || 'single',
      frequency: incident.frequency || 1,
      interval:  incident.interval  || 0,
      target:    incident.path      || '/',
      method:    incident.method    || 'GET',
    };
  }

  // ── Evidence storage ──────────────────────────────────────────────────────
  async _saveSignal(signal) {
    const filePath = path.join(this.config.captureDir, `${signal.id}.json`);
    await fsp.writeFile(filePath, JSON.stringify(signal, null, 2), 'utf8').catch(err => {
      this._log('error', `Evidence write failed: ${err.message}`);
    });
    return filePath;
  }

  // ── Buffer escalation hook ─────────────────────────────────────────────────
  /**
   * Called by buffer-system on escalation.
   * SOCK5: capture + signal lockdown-module to redirect.
   * BACKTRACE: capture only.
   * No bounce at any level.
   */
  async handleBufferEscalation(bufferLevel, incident, lockdownModule) {
    if (bufferLevel === 'SOCK5') {
      this._log('critical', `SOCK5 — capturing + redirect`);
      const signal = await this.captureSignal({ ...incident, bufferLevel });
      if (signal && lockdownModule) {
        await lockdownModule.redirectToHoneypot(signal);
      }
      return { signal, action: 'captured_and_redirected' };
    }

    if (bufferLevel === 'BACKTRACE') {
      this._log('warning', `BACKTRACE — capture only`);
      const signal = await this.captureSignal({ ...incident, bufferLevel });
      return { signal, action: 'captured' };
    }

    return null;
  }

  // ── Utilities ─────────────────────────────────────────────────────────────
  _isWhitelisted(ip) {
    return this.config.whitelistIPs.includes(ip);
  }

  getStatus() {
    return {
      version:         this.version,
      capturedSignals: this.state.capturedSignals.length,
      captureDir:      this.config.captureDir,
    };
  }

  getCapturedSignals(limit = 10) {
    return this.state.capturedSignals.slice(-limit);
  }

  _log(level, message) {
    const ts  = new Date().toISOString();
    const sym = { info: '📘', warning: '⚠️', error: '❌', critical: '🚨' };
    console.log(`${ts} ${sym[level] || '📝'} [SignalCapture] ${message}`);
  }
}

module.exports = SignalCapture;
