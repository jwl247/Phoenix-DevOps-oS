/**
 * CONFIG MANAGER
 * jwl247 / Jerry Leftwich / GPL v3
 *
 * Tracks known-good config baseline for a guardian node.
 * Detects config drift and feeds guardian events via drop-dir.
 * One instance per node (Alpha/Beta/Gamma/Delta).
 *
 * Ring role: baseline authority — all guardian nodes import this.
 * If config drifts, guardian rotator gets the event; node goes
 * to forced rotation; lockdown-module redirects if SOCK5 severity.
 */

'use strict';

const fsp    = require('fs').promises;
const crypto = require('crypto');
const os     = require('os');
const path   = require('path');


class ConfigManager {
  /**
   * @param {string}  nodeId       Guardian node ID: 'alpha'|'beta'|'gamma'|'delta'
   * @param {object}  [config]
   * @param {string}  [config.baselineDir]    Where baselines are stored
   * @param {string}  [config.dropDir]        Guardian drop-dir (env fallback)
   * @param {number}  [config.pollIntervalMs] How often to re-check (default 30 000)
   * @param {string[]}[config.watchFiles]     Config files to baseline (node-specific defaults)
   */
  constructor(nodeId, config = {}) {
    if (!['alpha', 'beta', 'gamma', 'delta'].includes(nodeId)) {
      throw new Error(`Invalid nodeId "${nodeId}" — must be alpha|beta|gamma|delta`);
    }

    this.nodeId  = nodeId;
    this.version = '1.0.0';

    this.config = {
      baselineDir:    config.baselineDir ||
        path.join(os.homedir(), '.unitedsys', 'baselines', nodeId),
      dropDir: config.dropDir ||
        process.env.PHOENIX_GUARDIAN_DROPDIR ||
        path.join(os.homedir(), '.unitedsys', 'logs', 'guardian_events.jsonl'),
      pollIntervalMs: config.pollIntervalMs ?? 30_000,
      watchFiles:     config.watchFiles    || _defaultWatchFiles(nodeId),
    };

    // baselinePath: { hash, mtime, capturedAt }
    this._baseline   = new Map();
    this._driftLog   = [];
    this._pollTimer  = null;
    this._baselineSet = false;

    fsp.mkdir(this.config.baselineDir, { recursive: true }).catch(() => {});
    this._log('info', `ConfigManager [${nodeId}] online — watching ${this.config.watchFiles.length} files`);
  }

  // ── Baseline capture ───────────────────────────────────────────────────────
  /**
   * Capture current state as known-good baseline.
   * Call this after a verified-clean boot or deploy.
   */
  async captureBaseline() {
    const results = [];
    for (const filePath of this.config.watchFiles) {
      const snap = await this._snapshot(filePath);
      if (snap) {
        this._baseline.set(filePath, snap);
        results.push({ path: filePath, hash: snap.hash });
      }
    }

    // Persist baseline to disk
    const baselineFile = path.join(this.config.baselineDir, 'baseline.json');
    const record = {
      nodeId:    this.nodeId,
      capturedAt:new Date().toISOString(),
      files:     Object.fromEntries(this._baseline),
    };
    await fsp.writeFile(baselineFile, JSON.stringify(record, null, 2), 'utf8').catch(err =>
      this._log('error', `Baseline write failed: ${err.message}`));

    this._baselineSet = true;
    this._log('info', `Baseline captured — ${results.length} files`);
    return results;
  }

  /**
   * Load a previously saved baseline from disk.
   */
  async loadBaseline() {
    const baselineFile = path.join(this.config.baselineDir, 'baseline.json');
    try {
      const raw  = await fsp.readFile(baselineFile, 'utf8');
      const data = JSON.parse(raw);
      for (const [filePath, snap] of Object.entries(data.files || {})) {
        this._baseline.set(filePath, snap);
      }
      this._baselineSet = true;
      this._log('info', `Baseline loaded — ${this._baseline.size} files`);
    } catch (err) {
      this._log('warning', `No baseline on disk: ${err.message} — run captureBaseline() first`);
    }
  }

  // ── Drift detection ────────────────────────────────────────────────────────
  /**
   * Check all watched files against baseline.
   * Returns array of drift events (empty = clean).
   */
  async checkDrift() {
    if (!this._baselineSet) {
      this._log('warning', 'No baseline set — skipping drift check');
      return [];
    }

    const drifted = [];

    for (const filePath of this.config.watchFiles) {
      const current = await this._snapshot(filePath);
      const base    = this._baseline.get(filePath);

      if (!base) continue;  // File wasn't in baseline (new file added post-baseline)

      let driftType = null;

      if (!current && base.exists) {
        driftType = 'file_removed';
      } else if (current && !base.exists) {
        driftType = 'file_appeared';
      } else if (current && base.hash !== current.hash) {
        driftType = 'content_changed';
      } else if (current && base.permissions !== current.permissions) {
        driftType = 'permissions_changed';
      }

      if (driftType) {
        const event = {
          type:      'config_drift',
          nodeId:    this.nodeId,
          path:      filePath,
          driftType,
          baseline:  base,
          current:   current || { exists: false },
          timestamp: new Date().toISOString(),
        };
        drifted.push(event);
        this._driftLog.push(event);
        this._log('critical', `DRIFT [${this.nodeId}] ${filePath} — ${driftType}`);

        // Feed guardian drop-dir
        await this._dropEvent(event);
      }
    }

    return drifted;
  }

  // ── Polling ────────────────────────────────────────────────────────────────
  startPolling() {
    if (this._pollTimer) return;
    this._pollTimer = setInterval(() => {
      this.checkDrift().catch(err =>
        this._log('error', `Drift check threw: ${err.message}`));
    }, this.config.pollIntervalMs);
    this._log('info', `Polling started (${this.config.pollIntervalMs / 1000}s interval)`);
    return this;
  }

  stopPolling() {
    if (this._pollTimer) {
      clearInterval(this._pollTimer);
      this._pollTimer = null;
    }
  }

  // ── Drop-dir ───────────────────────────────────────────────────────────────
  async _dropEvent(event) {
    try {
      await fsp.appendFile(
        this.config.dropDir,
        JSON.stringify(event) + '\n',
        'utf8'
      );
    } catch (err) {
      this._log('error', `drop-dir write failed: ${err.message}`);
    }
  }

  // ── Snapshot ───────────────────────────────────────────────────────────────
  async _snapshot(filePath) {
    try {
      const stat    = await fsp.stat(filePath);
      const content = await fsp.readFile(filePath, 'utf8').catch(() => '');
      return {
        path:        filePath,
        exists:      true,
        hash:        crypto.createHash('sha256').update(content).digest('hex'),
        permissions: (stat.mode & 0o777).toString(8),
        mtime:       stat.mtimeMs,
        size:        stat.size,
        capturedAt:  new Date().toISOString(),
      };
    } catch {
      return { path: filePath, exists: false, hash: null, capturedAt: new Date().toISOString() };
    }
  }

  // ── Status ─────────────────────────────────────────────────────────────────
  status() {
    return {
      nodeId:       this.nodeId,
      version:      this.version,
      baselineSet:  this._baselineSet,
      watchedFiles: this.config.watchFiles.length,
      driftEvents:  this._driftLog.length,
      polling:      this._pollTimer !== null,
    };
  }

  getDriftLog(limit = 20) {
    return this._driftLog.slice(-limit);
  }

  _log(level, message) {
    const ts  = new Date().toISOString();
    const sym = { info: '📘', warning: '⚠️', error: '❌', critical: '🚨' };
    console.log(`${ts} ${sym[level] || '📝'} [ConfigManager:${this.nodeId}] ${message}`);
  }
}


// ── Node-specific default watch lists ─────────────────────────────────────────
function _defaultWatchFiles(nodeId) {
  const shared = [
    '/etc/phoenix/config.json',
    '/etc/phoenix/auth.json',
  ];

  const byNode = {
    alpha: [
      ...shared,
      '/etc/pam.d/common-auth',
      '/etc/ssh/sshd_config',
      '/etc/sudoers',
      // sector1 kernel / auth
      'sector1/auth/phoenix_auth.py',
      'sector1/helix/helix.conf',
    ],
    beta: [
      ...shared,
      'sector2/package-handler/worker/wrangler.jsonc',
      'sector2/frank/frank_helix.py',
      'sector2/propagator/dispatch.json',
    ],
    gamma: [
      ...shared,
      'sector3/translator/translator.sh',
      'sector3/romeo_juliet/romeo.py',
      'sector3/romeo_juliet/juliet.py',
      'sector3/services/',
    ],
    delta: [
      ...shared,
      // Vault / custody  — breach_coms mounts (Debian VM paths)
      '/mnt/g/phoenix/config/',   // T1 PRIMARY
      '/mnt/f/phoenix/config/',   // T2 SECONDARY
      'sector4/vault/phoenix-push.sh',
      'sector4/paging.py',
    ],
  };

  return byNode[nodeId] || shared;
}


module.exports = ConfigManager;
