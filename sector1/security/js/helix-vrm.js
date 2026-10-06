/**
 * HeIXVRM — MEMORY ABSORPTION & INTELLIGENCE LAYER
 * jwl247 / Jerry Leftwich / GPL v3
 *
 * "Let them think they're winning while we learn everything."
 *
 * Strategy: Absorb → Analyze → Redirect
 *
 * On detection: REDIRECT to honeypot — never bounce, never retaliate.
 * Captured attacker data is evidence; it is stored, never replayed.
 *
 * Integrates with:
 *   - Ollama (local LLM for attack analysis — three-tier AI fallback)
 *   - lockdown-module (redirect path)
 *   - buffer-system (escalation feeding)
 *   - CoPES guardian layer (drops file_motion / network_connection events)
 */

'use strict';

const os   = require('os');
const path = require('path');
const fsp  = require('fs').promises;

const HONEYPOT_REDIRECT_URL = process.env.PHOENIX_HONEYPOT_URL || 'http://127.0.0.1:8888/honeypot';


class HeIXVRM {
  constructor(config = {}) {
    this.version = '2.0.0';
    this.name    = 'HeIXVRM';

    this.config = {
      // Absorption
      absorptionTime:    config.absorptionTime    || 30000,   // 30s honeypot window
      maxAbsorptionTime: config.maxAbsorptionTime || 120000,  // 2 min hard cap
      minDataPoints:     config.minDataPoints     || 10,

      // Ollama (local LLM — always first, vendor-independent)
      ollamaEndpoint: config.ollamaEndpoint || 'http://localhost:11434/api/generate',
      ollamaModel:    config.ollamaModel    || 'llama3.2',

      // Deception
      fakeVulnerabilities: config.fakeVulnerabilities !== false,
      fakeLogs:            config.fakeLogs            !== false,
      fakeDelays:          config.fakeDelays          !== false,

      // Snap thresholds
      snapThreshold: config.snapThreshold || {
        sqlInjectionAttempts:     10,
        commandInjectionAttempts: 5,
        suspicionTotal:           50,
        minUniquePatterns:        3,
      },

      // Redirect target (honeypot — never attacker origin)
      honeypotUrl: config.honeypotUrl || HONEYPOT_REDIRECT_URL,

      // Evidence log
      evidenceLog: config.evidenceLog ||
        path.join(os.homedir(), '.unitedsys', 'logs', 'helix_vrm_evidence.jsonl'),

      ...config,
    };

    this.memory = {
      attackSessions:  new Map(),
      learnedPatterns: [],
      attackerProfiles: new Map(),
      absorptionActive: false,
      snapTriggered:    false,
    };

    this.intelligence = {
      techniques:    [],
      tools:         [],
      ips:           new Set(),
      userAgents:    new Set(),
      payloads:      [],
      timingPatterns:[],
    };

    this._initLog();
  }

  async _initLog() {
    await fsp.mkdir(path.dirname(this.config.evidenceLog), { recursive: true }).catch(() => {});
    this._log('info', 'HeIXVRM Memory Layer Online — posture: absorb + redirect');
  }

  // ── Evidence persistence ────────────────────────────────────────────────────
  async _appendEvidence(record) {
    try {
      await fsp.appendFile(
        this.config.evidenceLog,
        JSON.stringify({ ...record, savedAt: new Date().toISOString() }) + '\n',
        'utf8'
      );
    } catch (err) {
      this._log('error', `Evidence write failed: ${err.message}`);
    }
  }

  // ── Absorption phase ────────────────────────────────────────────────────────
  async startAbsorption(attackerId, initialMotion) {
    if (this.memory.absorptionActive) {
      return { absorbed: false, reason: 'busy' };
    }

    this.memory.absorptionActive = true;

    const session = {
      id:              `session_${Date.now()}`,
      attackerId,
      startTime:       Date.now(),
      endTime:         null,
      dataPoints:      [],
      techniques:      [],
      suspicionLevel:  0,
      snapDecision:    null,
      absorptionTimeout: null,
    };

    this.memory.attackSessions.set(attackerId, session);

    this._log('critical',
      `ABSORPTION MODE: ${attackerId} — window ${this.config.absorptionTime / 1000}s ` +
      `(hard cap ${this.config.maxAbsorptionTime / 1000}s)`
    );

    await this._deployDeception(attackerId);

    session.absorptionTimeout = setTimeout(() => {
      if (!this.memory.snapTriggered) {
        this._log('warning', 'Max absorption time — forcing snap');
        this.snap(attackerId, 'timeout');
      }
    }, this.config.maxAbsorptionTime);

    return { absorbed: true, session, message: 'Attacker believes they are winning.' };
  }

  async observeAction(attackerId, action) {
    const session = this.memory.attackSessions.get(attackerId);
    if (!session) return null;

    const dataPoint = {
      timestamp: Date.now(),
      action:    action.type,
      target:    action.target,
      payload:   action.payload,
      success:   action.success || false,
      metadata:  action.metadata || {},
    };

    session.dataPoints.push(dataPoint);
    this.intelligence.payloads.push(action.payload);

    if (this.config.fakeLogs) {
      this._sendFakeSuccess(attackerId, action);
    }

    const analysis = await this._analyzeWithOllama(dataPoint);
    session.techniques.push(analysis.technique);
    session.suspicionLevel += analysis.suspicionScore;

    const shouldSnap = this._evaluateSnapCondition(session);
    if (shouldSnap.snap) {
      await this.snap(attackerId, shouldSnap.reason);
    }

    return {
      observed:       true,
      dataPoints:     session.dataPoints.length,
      suspicionLevel: session.suspicionLevel,
      techniques:     session.techniques,
    };
  }

  // ── Deception ───────────────────────────────────────────────────────────────
  async _deployDeception(attackerId) {
    if (this.config.fakeVulnerabilities) {
      this._log('info', `[DECEPTION:${attackerId}] Fake vuln endpoints active`);
    }
    if (this.config.fakeLogs) {
      this._log('info', `[DECEPTION:${attackerId}] Fake success responses armed`);
    }
    return { deployed: true };
  }

  _sendFakeSuccess(attackerId, action) {
    const responses = {
      login:               '{"success":true,"token":"<fake-jwt>"}',
      sql_injection:       '{"users":[{"id":1,"username":"admin","password":"<fake-hash>"}]}',
      file_upload:         '{"success":true,"filename":"uploaded.php","path":"/uploads/"}',
      command_injection:   '{"output":"uid=33(www-data) gid=33(www-data)"}',
      directory_traversal: '{"file":"root:x:0:0:root:/root:/bin/bash"}',
    };
    const resp = responses[action.type] || '{"success":true}';
    this._log('info', `[FAKE:${attackerId}] ${action.type} → ${resp.slice(0, 60)}`);
    // Real impl: pipe resp to attacker connection
  }

  // ── Ollama analysis ─────────────────────────────────────────────────────────
  async _analyzeWithOllama(dataPoint) {
    const prompt = `Security event — identify technique (under 80 words):
Action: ${dataPoint.action}
Target: ${dataPoint.target}
Payload: ${JSON.stringify(dataPoint.payload).slice(0, 200)}
Reply: technique name, suspicion 0-10, next-action (redirect or observe).`;

    try {
      const res = await fetch(this.config.ollamaEndpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model: this.config.ollamaModel, prompt, stream: false }),
        signal: AbortSignal.timeout(5000),
      });
      const data = await res.json();
      return this._parseOllamaResponse(data.response, dataPoint);
    } catch {
      // Ollama unavailable — fall back to heuristic
      return {
        technique:     this._inferTechnique(dataPoint),
        suspicionScore: 5,
        recommendation: 'observe',
      };
    }
  }

  _parseOllamaResponse(raw, dataPoint) {
    // Best-effort parse; heuristic fallback
    const scoreMatch = raw && raw.match(/(\d+(\.\d+)?)\s*\/?\s*10/);
    return {
      technique:      this._inferTechnique(dataPoint),
      suspicionScore: scoreMatch ? parseFloat(scoreMatch[1]) : 5,
      recommendation: 'observe',
      raw,
    };
  }

  _inferTechnique(dataPoint) {
    const payload = String(dataPoint.payload || '');
    const checks = {
      sql_injection:       /('|"|;|--|union\s|select\s|drop\s)/i,
      command_injection:   /(\||;|&|`|\$\(|\$\{)/,
      xss:                 /<script|javascript:|onerror=/i,
      path_traversal:      /\.\.\//,
      credential_stuffing: /login|auth|password/i,
    };
    for (const [tech, re] of Object.entries(checks)) {
      if (re.test(payload)) return tech;
    }
    return 'reconnaissance';
  }

  // ── Snap decision ───────────────────────────────────────────────────────────
  _evaluateSnapCondition(session) {
    const t = this.config.snapThreshold;
    const counts = {};
    for (const tech of session.techniques) {
      counts[tech] = (counts[tech] || 0) + 1;
    }

    if ((counts.sql_injection     || 0) >= t.sqlInjectionAttempts)     return { snap: true, reason: 'sql_injection_threshold' };
    if ((counts.command_injection || 0) >= t.commandInjectionAttempts) return { snap: true, reason: 'command_injection_threshold' };
    if (session.suspicionLevel >= t.suspicionTotal)                    return { snap: true, reason: 'suspicion_critical' };

    const elapsed = Date.now() - session.startTime;
    const unique  = new Set(session.techniques).size;
    if (session.dataPoints.length >= this.config.minDataPoints && unique >= t.minUniquePatterns) {
      return { snap: true, reason: 'intelligence_sufficient' };
    }
    if (elapsed >= this.config.absorptionTime && session.dataPoints.length >= this.config.minDataPoints) {
      return { snap: true, reason: 'absorption_complete' };
    }

    return { snap: false };
  }

  async snap(attackerId, reason) {
    const session = this.memory.attackSessions.get(attackerId);
    if (!session) return null;

    this.memory.snapTriggered    = true;
    this.memory.absorptionActive = false;
    session.endTime              = Date.now();
    session.snapDecision         = reason;

    if (session.absorptionTimeout) clearTimeout(session.absorptionTimeout);

    const duration = ((session.endTime - session.startTime) / 1000).toFixed(1);
    this._log('critical',
      `SNAP [${reason}] | ${attackerId} | ${duration}s | ` +
      `${session.dataPoints.length} data points | suspicion ${session.suspicionLevel.toFixed(0)}`
    );

    const intel = await this._generateIntelligenceReport(session);

    return {
      snapped:     true,
      reason,
      session,
      intelligence: intel,
      nextAction:  'redirect_to_honeypot',   // POSTURE: redirect, never bounce
    };
  }

  // ── Intelligence report ──────────────────────────────────────────────────────
  async _generateIntelligenceReport(session) {
    const report = {
      sessionId:          session.id,
      attackerId:         session.attackerId,
      duration:           session.endTime - session.startTime,
      techniques:         [...new Set(session.techniques)],
      totalActions:       session.dataPoints.length,
      suspicionLevel:     session.suspicionLevel,
      averageInterval:    this._avgInterval(session.dataPoints),
      burstDetected:      this._detectBurst(session.dataPoints),
      uniquePayloads:     new Set(session.dataPoints.map(d => d.payload)).size,
      mostCommonTechnique:this._mostCommon(session.techniques),
      sophistication:     this._sophistication(session),
      likelyTools:        this._inferTools(session),
      recommendedResponse:this._recommendResponse(session),
    };

    // Persist as evidence — never replayed, read-only record
    await this._appendEvidence({ type: 'intelligence_report', ...report });

    this.memory.learnedPatterns.push({
      timestamp:     Date.now(),
      techniques:    report.techniques,
      sophistication:report.sophistication,
      tools:         report.likelyTools,
    });

    this._log('info',
      `Intel: sophistication=${report.sophistication} | ` +
      `technique=${report.mostCommonTechnique} | response=${report.recommendedResponse}`
    );

    return report;
  }

  _recommendResponse(session) {
    // Posture: REDIRECT ONLY. No bounce, no retaliation, no JMeter.
    // Attacker data is evidence; redirect to honeypot to keep absorbing.
    const s = this._sophistication(session);
    if (s === 'advanced')     return 'redirect_to_honeypot_deep';    // extend honeypot, full profile
    if (s === 'intermediate') return 'redirect_to_honeypot';         // standard honeypot redirect
    return 'redirect_and_log';                                        // basic — log + redirect
  }

  _avgInterval(dataPoints) {
    if (dataPoints.length < 2) return 0;
    let total = 0;
    for (let i = 1; i < dataPoints.length; i++) {
      total += dataPoints[i].timestamp - dataPoints[i - 1].timestamp;
    }
    return total / (dataPoints.length - 1);
  }

  _detectBurst(dataPoints) {
    let max = 0, cur = 1;
    for (let i = 1; i < dataPoints.length; i++) {
      if (dataPoints[i].timestamp - dataPoints[i - 1].timestamp < 1000) {
        max = Math.max(max, ++cur);
      } else {
        cur = 1;
      }
    }
    return max >= 5 ? { detected: true, size: max } : { detected: false };
  }

  _mostCommon(arr) {
    if (!arr.length) return 'unknown';
    const counts = {};
    for (const x of arr) counts[x] = (counts[x] || 0) + 1;
    return Object.keys(counts).reduce((a, b) => counts[a] > counts[b] ? a : b);
  }

  _sophistication(session) {
    const unique = new Set(session.techniques).size;
    const score  = session.suspicionLevel / 10;
    if (unique >= 5 || score >= 8) return 'advanced';
    if (unique >= 3 || score >= 5) return 'intermediate';
    return 'script_kiddie';
  }

  _inferTools(session) {
    const tools = new Set();
    for (const dp of session.dataPoints) {
      const ua = dp.metadata?.userAgent || '';
      if (ua.includes('sqlmap'))  tools.add('sqlmap');
      if (ua.includes('nikto'))   tools.add('nikto');
      if (ua.includes('nmap'))    tools.add('nmap');
      if (ua.includes('curl'))    tools.add('curl');
      if (ua.includes('python'))  tools.add('custom_script');
    }
    if (!tools.size) tools.add('manual_browser');
    return [...tools];
  }

  // ── Vosk (audio exploit detection — optional) ─────────────────────────────
  async analyzeAudioStream(audioData) {
    if (!this.config.voskEnabled) return null;
    // Real impl: vosk.Recognizer over audioData
    // Suspicious keywords fire a file_motion/network_connection guardian event
    return null;
  }

  // ── Status ──────────────────────────────────────────────────────────────────
  getMemoryStatus() {
    return {
      absorptionActive: this.memory.absorptionActive,
      activeSessions:   this.memory.attackSessions.size,
      learnedPatterns:  this.memory.learnedPatterns.length,
      intelligence: {
        uniqueIPs:      this.intelligence.ips.size,
        uniquePayloads: this.intelligence.payloads.length,
        techniques:     this.intelligence.techniques.length,
      },
      evidenceLog: this.config.evidenceLog,
    };
  }

  _log(level, message) {
    const ts = new Date().toISOString();
    const sym = { info: '📘', success: '✅', warning: '⚠️', error: '❌', critical: '🚨' };
    console.log(`${ts} ${sym[level] || '📝'} [HeIXVRM] ${message}`);
  }
}

module.exports = HeIXVRM;
