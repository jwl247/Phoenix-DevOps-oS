/**
 * QUAD COMMS — inter-node messaging for the Guardian ring
 * jwl247 / Jerry Leftwich / GPL v3
 *
 * Primary transport: Unix Domain Sockets (UDS)
 *   /run/phoenix/guardian/<nodeId>.sock
 *   Kernel-buffered, no network exposure, no port conflicts.
 *   PortGuard never flags these — they are not TCP/IP sockets.
 *   If a target node's socket is not there, connect() fails instantly —
 *   that failure IS the signal: the node is down, GK gets the alert.
 *
 * Fallback transport: JSONL drop file (if socket connect fails)
 *   ~/.unitedsys/comms/<nodeId>/inbox.jsonl
 *   Written when the target node can't be reached live.
 *   The target node drains this on startup.
 *
 * Audit log (always written regardless of transport):
 *   ~/.unitedsys/comms/<nodeId>/audit.jsonl   ← every message in/out, timestamped
 *   GK reads the audit log for the comms checkpoint. Not the primary comms path.
 *
 * Guardian drop-dir (always written):
 *   PHOENIX_GUARDIAN_DROPDIR → guardian_events.jsonl
 *   Quadengine.py polls this cross-process.
 *
 * Message types:
 *   alert     → node detected a threat, broadcasting to siblings
 *   status    → routine status ping
 *   directive → instruction from one node to another (e.g. alpha→delta: harden vault)
 *   ack       → acknowledgment of a received message
 *
 * Posture: comms are audit-only — no node auto-executes a directive without GK seeing it.
 */

'use strict';

const net    = require('net');
const fsp    = require('fs').promises;
const fs     = require('fs');
const path   = require('path');
const os     = require('os');
const crypto = require('crypto');

const NODES = ['alpha', 'beta', 'gamma', 'delta'];

// Socket root — /run/phoenix/guardian/<nodeId>.sock
// Falls back to ~/.unitedsys/sockets/ if /run/phoenix is not writable (non-root dev env)
function _socketPath(nodeId) {
  const runPath = `/run/phoenix/guardian/${nodeId}.sock`;
  try {
    fs.accessSync('/run/phoenix', fs.constants.W_OK);
    return runPath;
  } catch {
    return path.join(os.homedir(), '.unitedsys', 'sockets', `${nodeId}.sock`);
  }
}

function _commsRoot() {
  return process.env.PHOENIX_COMMS_DIR ||
    path.join(os.homedir(), '.unitedsys', 'comms');
}

function _guardianDropDir() {
  return process.env.PHOENIX_GUARDIAN_DROPDIR ||
    path.join(os.homedir(), '.unitedsys', 'logs', 'guardian_events.jsonl');
}


class QuadComms {
  /**
   * @param {string} nodeId   'alpha'|'beta'|'gamma'|'delta'
   * @param {object} [opts]
   * @param {number} [opts.ackTimeoutMs]    Unacked alert/directive timeout ms (default 2h)
   * @param {number} [opts.maxQueueDepth]   Alert threshold (default 100)
   * @param {number} [opts.connectTimeoutMs] Socket connect timeout ms (default 2000)
   */
  constructor(nodeId, opts = {}) {
    if (!NODES.includes(nodeId)) {
      throw new Error(`QuadComms: unknown nodeId "${nodeId}". Valid: ${NODES.join(', ')}`);
    }

    this.nodeId           = nodeId;
    this.ackTimeoutMs     = opts.ackTimeoutMs     ?? 2 * 60 * 60 * 1000;
    this.maxQueueDepth    = opts.maxQueueDepth    ?? 100;
    this.connectTimeoutMs = opts.connectTimeoutMs ?? 2000;

    this._socketPath  = _socketPath(nodeId);
    this._commsRoot   = _commsRoot();
    this._auditPath   = path.join(this._commsRoot, nodeId, 'audit.jsonl');
    this._fallbackDir = path.join(this._commsRoot, nodeId);

    // UDS server — receives messages from other nodes
    this._server      = null;
    this._inbox       = [];   // in-memory; drained from fallback on start
    this._onMessage   = null; // callback: fn(msg)

    fsp.mkdir(path.dirname(this._auditPath), { recursive: true }).catch(() => {});
    fsp.mkdir(path.dirname(this._socketPath), { recursive: true }).catch(() => {});
  }

  // ── Server (listener) ──────────────────────────────────────────────────────
  /**
   * Start listening for messages from other nodes.
   * Call this once per node at startup.
   */
  async listen() {
    // Remove stale socket file if it exists (previous crash)
    try { await fsp.unlink(this._socketPath); } catch {}

    return new Promise((resolve, reject) => {
      this._server = net.createServer(socket => {
        let buf = '';
        socket.on('data', chunk => { buf += chunk.toString('utf8'); });
        socket.on('end', async () => {
          const lines = buf.split('\n').filter(Boolean);
          for (const line of lines) {
            try {
              const msg = JSON.parse(line);
              this._inbox.push(msg);
              await this._audit('recv', msg);
              if (this._onMessage) this._onMessage(msg).catch(console.error);
            } catch (err) {
              console.error(`[QuadComms:${this.nodeId}] malformed message: ${err.message}`);
            }
          }
        });
        socket.on('error', err =>
          console.error(`[QuadComms:${this.nodeId}] socket error: ${err.message}`));
      });

      this._server.listen(this._socketPath, () => {
        // Set permissions so sibling nodes can write (group-readable)
        fsp.chmod(this._socketPath, 0o660).catch(() => {});
        console.log(`[QuadComms:${this.nodeId}] listening on ${this._socketPath}`);
        resolve(this);
      });

      this._server.on('error', err => {
        console.error(`[QuadComms:${this.nodeId}] server error: ${err.message}`);
        reject(err);
      });
    });
  }

  stopListening() {
    if (this._server) {
      this._server.close();
      this._server = null;
      fsp.unlink(this._socketPath).catch(() => {});
    }
  }

  /** Register a callback invoked on every received message. */
  onMessage(fn) { this._onMessage = fn; return this; }

  // ── Send ───────────────────────────────────────────────────────────────────
  /**
   * Send a message to one or more nodes.
   * Primary: UDS connect → write → end.
   * Fallback: JSONL drop to target node's fallback inbox.
   *
   * @param {string|string[]} to  Target nodeId(s) or 'all'
   * @param {'alert'|'status'|'directive'|'ack'} type
   * @param {object} payload
   * @returns {object[]} Results per target: { to, transport, msgId, ok }
   */
  async send(to, type, payload = {}) {
    const targets = to === 'all'
      ? NODES.filter(n => n !== this.nodeId)
      : (Array.isArray(to) ? to : [to]);

    const results = [];

    for (const target of targets) {
      if (!NODES.includes(target)) {
        console.error(`[QuadComms:${this.nodeId}] Unknown target "${target}" — skipped`);
        continue;
      }

      const msg = {
        msgId:     crypto.randomBytes(8).toString('hex'),
        from:      this.nodeId,
        to:        target,
        type,
        priority:  _priority(type, payload),
        payload,
        timestamp: new Date().toISOString(),
        acked:     false,
        ackedAt:   null,
      };

      const result = { to: target, msgId: msg.msgId, transport: null, ok: false };

      // ── Try UDS first ──────────────────────────────────────────────────────
      const sockPath = _socketPath(target);
      const sent = await this._sendSocket(sockPath, msg);

      if (sent) {
        result.transport = 'uds';
        result.ok        = true;
      } else {
        // ── Fallback: JSONL drop ───────────────────────────────────────────
        const fallback = path.join(this._commsRoot, target, 'inbox_fallback.jsonl');
        await fsp.mkdir(path.dirname(fallback), { recursive: true }).catch(() => {});
        await fsp.appendFile(fallback, JSON.stringify(msg) + '\n', 'utf8').catch(() => {});
        result.transport = 'jsonl_fallback';
        result.ok        = true;   // Written to disk; target drains on startup
        console.warn(
          `[QuadComms:${this.nodeId}→${target}] UDS unavailable — ` +
          `dropped to fallback (node may be down)`);
      }

      await this._audit('sent', msg);
      await this._dropEvent({
        type:       'node_message',
        from:       this.nodeId,
        to:         target,
        msgType:    type,
        msgId:      msg.msgId,
        priority:   msg.priority,
        transport:  result.transport,
        timestamp:  msg.timestamp,
      });

      results.push(result);
    }

    return results;
  }

  // ── Receive / Ack ──────────────────────────────────────────────────────────
  /** All unacked messages currently in the in-memory inbox. */
  receive() {
    return this._inbox.filter(m => !m.acked);
  }

  /** Acknowledge by msgId. */
  ack(msgId) {
    const msg = this._inbox.find(m => m.msgId === msgId);
    if (!msg) return false;
    msg.acked   = true;
    msg.ackedAt = new Date().toISOString();
    this._audit('acked', msg).catch(() => {});
    return true;
  }

  /**
   * Drain the JSONL fallback inbox into the in-memory inbox.
   * Call at node startup after listen().
   */
  async drainFallback() {
    const fallback = path.join(this._commsRoot, this.nodeId, 'inbox_fallback.jsonl');
    if (!fs.existsSync(fallback)) return 0;
    const raw   = await fsp.readFile(fallback, 'utf8').catch(() => '');
    const lines = raw.split('\n').filter(Boolean);
    let count   = 0;
    for (const line of lines) {
      try {
        const msg = JSON.parse(line);
        if (!this._inbox.find(m => m.msgId === msg.msgId)) {
          this._inbox.push(msg);
          count++;
        }
      } catch {}
    }
    // Truncate fallback after drain
    await fsp.writeFile(fallback, '', 'utf8').catch(() => {});
    if (count) console.log(`[QuadComms:${this.nodeId}] drained ${count} fallback messages`);
    return count;
  }

  // ── Health check (GK calls this per node per round) ───────────────────────
  async healthCheck() {
    const unacked = this._inbox.filter(m => !m.acked);
    const cutoff  = Date.now() - this.ackTimeoutMs;

    const stuckAlerts     = unacked.filter(
      m => m.type === 'alert' && new Date(m.timestamp).getTime() < cutoff);
    const stuckDirectives = unacked.filter(
      m => m.type === 'directive' && new Date(m.timestamp).getTime() < cutoff);

    const inboxDepth  = unacked.length;
    const socketLive  = fs.existsSync(this._socketPath);
    const issues      = [];

    if (!socketLive)                   issues.push('socket_not_listening');
    if (inboxDepth >= this.maxQueueDepth) issues.push(`inbox_overflow (${inboxDepth})`);
    if (stuckAlerts.length > 0)        issues.push(`${stuckAlerts.length} unacked alert(s) past timeout`);
    if (stuckDirectives.length > 0)    issues.push(`${stuckDirectives.length} unacked directive(s) past timeout`);

    return {
      nodeId: this.nodeId,
      ok:     issues.length === 0,
      issues,
      socketPath:       this._socketPath,
      socketLive,
      inboxDepth,
      stuckAlerts,
      stuckDirectives,
      checkedAt: new Date().toISOString(),
    };
  }

  // ── Status ─────────────────────────────────────────────────────────────────
  status() {
    const unacked = this._inbox.filter(m => !m.acked);
    return {
      nodeId:      this.nodeId,
      socketPath:  this._socketPath,
      socketLive:  fs.existsSync(this._socketPath),
      listening:   this._server !== null,
      inboxTotal:  this._inbox.length,
      inboxUnacked:unacked.length,
    };
  }

  // ── Internals ──────────────────────────────────────────────────────────────
  async _sendSocket(sockPath, msg) {
    return new Promise(resolve => {
      const socket  = net.createConnection(sockPath);
      const timeout = setTimeout(() => {
        socket.destroy();
        resolve(false);
      }, this.connectTimeoutMs);

      socket.on('connect', () => {
        socket.write(JSON.stringify(msg) + '\n');
        socket.end();
        clearTimeout(timeout);
        resolve(true);
      });

      socket.on('error', () => {
        clearTimeout(timeout);
        resolve(false);
      });
    });
  }

  async _audit(direction, msg) {
    try {
      await fsp.mkdir(path.dirname(this._auditPath), { recursive: true });
      const entry = { direction, nodeId: this.nodeId, ...msg, auditTs: new Date().toISOString() };
      await fsp.appendFile(this._auditPath, JSON.stringify(entry) + '\n', 'utf8');
    } catch {}
  }

  async _dropEvent(event) {
    try {
      const target = _guardianDropDir();
      await fsp.mkdir(path.dirname(target), { recursive: true });
      await fsp.appendFile(target, JSON.stringify(event) + '\n', 'utf8');
    } catch {}
  }
}


// ── Helpers ───────────────────────────────────────────────────────────────────
function _priority(type, payload) {
  if (type === 'alert')     return payload.severity === 'critical' ? 'critical' : 'high';
  if (type === 'directive') return 'high';
  return 'normal';
}


// ── Ring-level comms health (GK calls this for comms checkpoint) ─────────────
async function ringCommsHealth(ring) {
  const results = {};
  for (const nodeId of NODES) {
    const node = ring[nodeId];
    if (node?.quadComms) {
      results[nodeId] = await node.quadComms.healthCheck();
    }
  }
  const allOk    = Object.values(results).every(r => r.ok);
  const problems = Object.entries(results)
    .filter(([, r]) => !r.ok)
    .map(([id, r]) => ({ nodeId: id, issues: r.issues }));

  return { ok: allOk, nodes: results, problems, checkedAt: new Date().toISOString() };
}


module.exports = { QuadComms, ringCommsHealth, NODES };
