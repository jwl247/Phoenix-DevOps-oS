/**
 * LOCKDOWN MODULE
 * jwl247 / Jerry Leftwich / GPL v3
 *
 * Redirect-only response to confirmed threats.
 * On detection: attacker is silently redirected to honeypot.
 * No retaliation, no bounce, no JMeter.
 * Redirect is logged as evidence — immutable record.
 *
 * Ring role: terminal action layer — receives escalation from
 * buffer-system / signal-capture and executes the redirect.
 */

'use strict';

const fsp  = require('fs').promises;
const os   = require('os');
const path = require('path');

const HONEYPOT_URL = process.env.PHOENIX_HONEYPOT_URL || 'http://127.0.0.1:8888/honeypot';


class LockdownModule {
  /**
   * @param {object} config
   * @param {string}  [config.honeypotUrl]   Redirect target (never attacker origin)
   * @param {string}  [config.evidenceLog]   Redirect evidence log path
   * @param {boolean} [config.deepProfile]   Keep extended session on SOCK5 (default true)
   */
  constructor(config = {}) {
    this.version = '1.0.0';

    this.config = {
      honeypotUrl:   config.honeypotUrl || HONEYPOT_URL,
      deepHoneypot:  config.deepHoneypot || (HONEYPOT_URL + '/deep'),
      evidenceLog:   config.evidenceLog ||
        path.join(os.homedir(), '.unitedsys', 'logs', 'lockdown_redirects.jsonl'),
      deepProfile:   config.deepProfile !== false,
    };

    this._redirectCount  = 0;
    this._redirectRecord = [];

    fsp.mkdir(path.dirname(this.config.evidenceLog), { recursive: true }).catch(() => {});
    this._log('info', `LockdownModule armed | honeypot=${this.config.honeypotUrl}`);
  }

  // ── Primary redirect ───────────────────────────────────────────────────────
  /**
   * Redirect attacker to honeypot. Called by signal-capture at SOCK5
   * or by the guardian rotator on honeypot probe.
   *
   * @param {object} signal   — signal record from SignalCapture
   * @returns {object}        — redirect record
   */
  async redirectToHoneypot(signal) {
    this._redirectCount++;

    const target = signal.attackType === 'sock5Tunnel' && this.config.deepProfile
      ? this.config.deepHoneypot
      : this.config.honeypotUrl;

    const record = {
      id:          `redirect_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
      redirectNum: this._redirectCount,
      timestamp:   new Date().toISOString(),
      sourceIP:    signal.sourceIP     || 'unknown',
      attackType:  signal.attackType   || 'unknown',
      signalId:    signal.id           || null,
      severity:    signal.severity     || 'medium',
      bufferLevel: signal.bufferLevel  || null,
      target,
      action:      'redirect',
      posture:     'redirect_only',    // reminder: never retaliation
    };

    this._redirectRecord.push(record);
    this._log('critical',
      `REDIRECT #${this._redirectCount} | ${record.sourceIP} → ${target} | ${record.attackType}`);

    // Persist as evidence (immutable — never replayed)
    await this._writeEvidence(record);

    return record;
  }

  // ── Bulk redirect (Guardian rotator honeypot probe) ───────────────────────
  async redirectProbe(incidentData) {
    const signal = {
      id:         null,
      sourceIP:   incidentData.sourceIP   || incidentData.data?.sourceIP || 'unknown',
      attackType: incidentData.type       || 'honeypot_probe',
      severity:   'high',
      bufferLevel: incidentData.bufferLevel || null,
    };
    return this.redirectToHoneypot(signal);
  }

  // ── Evidence write ─────────────────────────────────────────────────────────
  async _writeEvidence(record) {
    try {
      await fsp.appendFile(
        this.config.evidenceLog,
        JSON.stringify(record) + '\n',
        'utf8'
      );
    } catch (err) {
      this._log('error', `Evidence write failed: ${err.message}`);
    }
  }

  // ── Status ─────────────────────────────────────────────────────────────────
  getRedirects(limit = 20) {
    return this._redirectRecord.slice(-limit);
  }

  status() {
    return {
      version:       this.version,
      totalRedirects:this._redirectCount,
      honeypotUrl:   this.config.honeypotUrl,
      evidenceLog:   this.config.evidenceLog,
    };
  }

  _log(level, message) {
    const ts  = new Date().toISOString();
    const sym = { info: '📘', warning: '⚠️', error: '❌', critical: '🚨' };
    console.log(`${ts} ${sym[level] || '📝'} [LockdownModule] ${message}`);
  }
}

module.exports = LockdownModule;
