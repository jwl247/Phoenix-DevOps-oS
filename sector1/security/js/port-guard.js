/**
 * PORT GUARD
 * jwl247 / Jerry Leftwich / GPL v3
 *
 * Monitors network ports for SOCKS5/proxy/scanner activity.
 * One instance per guardian node (Alpha/Beta/Gamma/Delta).
 * Feeds network_connection events to the guardian drop-dir.
 * Posture: detect + redirect (never retaliate).
 *
 * Ring role: network sentinel — all nodes import this.
 * Detected port activity escalates through buffer-system → signal-capture
 * → lockdown-module (redirect to honeypot).
 */

'use strict';

const { execFile } = require('child_process');
const fsp    = require('fs').promises;
const os     = require('os');
const path   = require('path');
const { promisify } = require('util');

const execFileAsync = promisify(execFile);

// SOCKS5 and known proxy / C2 ports
const DEFAULT_WATCH_PORTS = [
  1080,   // SOCKS5
  9050,   // Tor SOCKS
  4444,   // Metasploit default
  31337,  // Back Orifice / C2
  8888,   // Common proxy
  3128,   // Squid
  8080,   // Alt-HTTP / proxy
  6667,   // IRC (C2 channel)
  6666,
  65535,  // High port sweeps
];


class PortGuard {
  /**
   * @param {string}   nodeId          Guardian node: 'alpha'|'beta'|'gamma'|'delta'
   * @param {object}  [config]
   * @param {number[]}[config.watchPorts]        Ports to flag (overrides defaults)
   * @param {number}  [config.pollIntervalMs]    Scan interval ms (default 15 000)
   * @param {string}  [config.dropDir]           Guardian drop-dir path
   * @param {boolean} [config.enabled]           Master switch — can be toggled (default true)
   */
  constructor(nodeId, config = {}) {
    this.nodeId  = nodeId;
    this.version = '1.0.0';

    this.config = {
      watchPorts:     config.watchPorts     || DEFAULT_WATCH_PORTS,
      pollIntervalMs: config.pollIntervalMs ?? 15_000,
      dropDir: config.dropDir ||
        process.env.PHOENIX_GUARDIAN_DROPDIR ||
        path.join(os.homedir(), '.unitedsys', 'logs', 'guardian_events.jsonl'),
      enabled: config.enabled !== false,
    };

    this._seenConnections = new Map();  // `ip:port` → first_seen_ts
    this._eventLog        = [];
    this._pollTimer       = null;

    fsp.mkdir(path.dirname(this.config.dropDir), { recursive: true }).catch(() => {});
    this._log('info',
      `PortGuard [${nodeId}] online | switch=${this.config.enabled} | ` +
      `watching ${this.config.watchPorts.length} ports`);
  }

  // ── Master switch ──────────────────────────────────────────────────────────
  enable()  { this.config.enabled = true;  this._log('info',  `[${this.nodeId}] enabled`);  }
  disable() { this.config.enabled = false; this._log('info',  `[${this.nodeId}] disabled`); }
  toggle()  {
    this.config.enabled = !this.config.enabled;
    this._log('info', `[${this.nodeId}] toggled → ${this.config.enabled}`);
    return this.config.enabled;
  }

  // ── Polling ────────────────────────────────────────────────────────────────
  startPolling() {
    if (this._pollTimer) return this;
    this._pollTimer = setInterval(() => {
      if (this.config.enabled) {
        this.scan().catch(err =>
          this._log('error', `Scan threw: ${err.message}`));
      }
    }, this.config.pollIntervalMs);
    this._log('info', `Polling started (${this.config.pollIntervalMs / 1000}s)`);
    return this;
  }

  stopPolling() {
    if (this._pollTimer) {
      clearInterval(this._pollTimer);
      this._pollTimer = null;
    }
  }

  // ── Scan ───────────────────────────────────────────────────────────────────
  /**
   * Query active network connections via `ss` (or `netstat` fallback).
   * Flags any connection on a watched port.
   */
  async scan() {
    if (!this.config.enabled) return [];

    let connections;
    try {
      connections = await this._queryConnections();
    } catch (err) {
      this._log('error', `Connection query failed: ${err.message}`);
      return [];
    }

    const flagged = [];

    for (const conn of connections) {
      if (!this.config.watchPorts.includes(conn.port)) continue;

      const key = `${conn.ip}:${conn.port}`;
      const isNew = !this._seenConnections.has(key);

      if (isNew) {
        this._seenConnections.set(key, Date.now());
        const event = {
          type:       'network_connection',
          nodeId:     this.nodeId,
          sourceIP:   conn.ip,
          port:       conn.port,
          protocol:   conn.protocol,
          state:      conn.state,
          pid:        conn.pid     || null,
          process:    conn.process || null,
          timestamp:  new Date().toISOString(),
          flagReason: `port_${conn.port}_on_watchlist`,
        };

        this._eventLog.push(event);
        flagged.push(event);
        this._log('warning',
          `FLAGGED ${conn.ip}:${conn.port} (${conn.protocol}) — ` +
          (conn.port === 1080 || conn.port === 9050 ? 'SOCKS5' : 'watchport'));

        await this._dropEvent(event);
      }
    }

    // Prune stale connections (not seen for 10 min)
    const cutoff = Date.now() - 600_000;
    for (const [key, ts] of this._seenConnections) {
      if (ts < cutoff) this._seenConnections.delete(key);
    }

    return flagged;
  }

  // ── Manual event injection (for testing / integration) ────────────────────
  async injectEvent(sourceIP, port, meta = {}) {
    const event = {
      type:       'network_connection',
      nodeId:     this.nodeId,
      sourceIP,
      port,
      protocol:   meta.protocol  || 'tcp',
      state:      meta.state     || 'ESTABLISHED',
      timestamp:  new Date().toISOString(),
      flagReason: meta.reason    || `manual_inject_port_${port}`,
      ...meta,
    };
    this._eventLog.push(event);
    await this._dropEvent(event);
    return event;
  }

  // ── Connection query ───────────────────────────────────────────────────────
  async _queryConnections() {
    // Try `ss` first (modern Linux)
    try {
      const { stdout } = await execFileAsync('ss', ['-tnpH'], { timeout: 5000 });
      return this._parseSS(stdout);
    } catch {
      // Fall back to `netstat`
      try {
        const { stdout } = await execFileAsync('netstat', ['-tnp'], { timeout: 5000 });
        return this._parseNetstat(stdout);
      } catch {
        return [];  // Neither available — scan returns empty (non-fatal)
      }
    }
  }

  _parseSS(output) {
    const conns = [];
    for (const line of output.split('\n')) {
      const parts = line.trim().split(/\s+/);
      if (parts.length < 4) continue;
      const [state, , , peer] = parts;
      if (!peer) continue;
      const lastColon = peer.lastIndexOf(':');
      if (lastColon < 0) continue;
      const ip   = peer.slice(0, lastColon);
      const port = parseInt(peer.slice(lastColon + 1), 10);
      if (!isNaN(port)) conns.push({ ip, port, state, protocol: 'tcp' });
    }
    return conns;
  }

  _parseNetstat(output) {
    const conns = [];
    for (const line of output.split('\n')) {
      if (!line.includes('ESTABLISHED') && !line.includes('LISTEN')) continue;
      const parts = line.trim().split(/\s+/);
      if (parts.length < 5) continue;
      const peer = parts[4] || '';
      const lastColon = peer.lastIndexOf(':');
      if (lastColon < 0) continue;
      const ip   = peer.slice(0, lastColon);
      const port = parseInt(peer.slice(lastColon + 1), 10);
      if (!isNaN(port)) conns.push({ ip, port, state: parts[5] || '', protocol: 'tcp' });
    }
    return conns;
  }

  // ── Drop-dir ───────────────────────────────────────────────────────────────
  async _dropEvent(event) {
    try {
      await fsp.appendFile(this.config.dropDir, JSON.stringify(event) + '\n', 'utf8');
    } catch (err) {
      this._log('error', `drop-dir write failed: ${err.message}`);
    }
  }

  // ── Status ─────────────────────────────────────────────────────────────────
  status() {
    return {
      nodeId:       this.nodeId,
      version:      this.version,
      enabled:      this.config.enabled,
      watchPorts:   this.config.watchPorts,
      flagged:      this._seenConnections.size,
      totalEvents:  this._eventLog.length,
      polling:      this._pollTimer !== null,
    };
  }

  getEventLog(limit = 20) {
    return this._eventLog.slice(-limit);
  }

  _log(level, message) {
    const ts  = new Date().toISOString();
    const sym = { info: '📘', warning: '⚠️', error: '❌', critical: '🚨' };
    console.log(`${ts} ${sym[level] || '📝'} [PortGuard:${this.nodeId}] ${message}`);
  }
}


module.exports = { PortGuard, DEFAULT_WATCH_PORTS };
