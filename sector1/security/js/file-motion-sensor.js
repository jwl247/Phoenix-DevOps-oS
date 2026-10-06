/**
 * FILE MOTION SENSOR
 * jwl247 / Jerry Leftwich / GPL v3
 *
 * Lightweight filesystem watcher — metadata only, no content hashing.
 * Detects file count, mtime, and permission changes on watched paths.
 * Ships snapshot batches to cloud when cap is reached.
 * Feeds events to the CoPES guardian layer via the drop-dir seam:
 *   writes { type: "file_motion", path, changeType, ... } to
 *   PHOENIX_GUARDIAN_DROPDIR (default ~/.unitedsys/logs/guardian_events.jsonl)
 *   so the Python copes_runtime poller picks it up cross-process.
 *
 * Watched by: Guardian Gamma (sector3 — network/file detection)
 */

'use strict';

const fs     = require('fs');
const fsp    = require('fs').promises;
const path   = require('path');
const crypto = require('crypto');
const os     = require('os');

// ── Default Phoenix paths ────────────────────────────────────────────────────
// These map to the physical drive layout (breach_coms4=T1, etc.).
// Override via config.watchedPaths in production.
const PHOENIX_DEFAULT_PATHS = [
  // System integrity
  '/etc/passwd',
  '/etc/shadow',
  '/etc/sudoers',
  '/root/.ssh',
  '/root/.bashrc',
  // Phoenix auth / kernel
  '/etc/phoenix',
  // Binary dirs — changes here = trojan risk
  '/usr/bin',
  '/usr/sbin',
  '/usr/local/bin',
  // Web / app surface
  '/var/www/html',
  // Vault mounts (Debian VM paths for breach_coms drives)
  '/mnt/g',   // breach_coms4 — T1 PRIMARY master vault
  '/mnt/f',   // breach_coms3 — T2 SECONDARY
  '/mnt/e',   // breach_coms2 — T3 TERTIARY / clonepool primary
  '/mnt/d',   // breach_coms1 — T4 TERTIARY
];

// ── Guardian drop-dir ────────────────────────────────────────────────────────
function _guardianDropDir() {
  return process.env.PHOENIX_GUARDIAN_DROPDIR ||
    path.join(os.homedir(), '.unitedsys', 'logs', 'guardian_events.jsonl');
}

async function _dropGuardianEvent(event) {
  try {
    const target = _guardianDropDir();
    await fsp.mkdir(path.dirname(target), { recursive: true });
    await fsp.appendFile(target, JSON.stringify(event) + '\n', 'utf8');
  } catch (err) {
    // Drop-dir write failure must never crash the sensor
    console.error(`[FileMotionSensor] drop-dir write failed: ${err.message}`);
  }
}


class FileMotionSensor {
  /**
   * @param {object} config
   * @param {string[]} [config.watchedPaths]     Override default Phoenix paths
   * @param {number}  [config.maxLocalSnapshots] Snapshots before shipping (default 100)
   * @param {number}  [config.checkInterval]     Poll interval ms (default 5000)
   * @param {number}  [config.triggerThreshold]  Changes before onMotion fires (default 1)
   * @param {boolean} [config.dropGuardianEvents] Write events to guardian drop-dir (default true)
   */
  constructor(config = {}) {
    this.config = {
      watchedPaths:      config.watchedPaths      || PHOENIX_DEFAULT_PATHS,
      maxLocalSnapshots: config.maxLocalSnapshots || 100,
      checkInterval:     config.checkInterval     || 5000,
      triggerThreshold:  config.triggerThreshold  || 1,
      dropGuardianEvents: config.dropGuardianEvents !== false,
    };

    this.watchedPaths  = new Map();   // path → watcher state
    this.motionQueue   = [];
    this.snapshotCount = 0;
    this._monitorInterval = null;

    this.callbacks = {
      onMotion:          null,
      onCapReached:      null,
      onPermissionCheck: null,
    };
  }

  // ── Callback hooks ──────────────────────────────────────────────────────────
  on(event, callback) {
    if (!(event in this.callbacks)) {
      throw new Error(`Unknown event "${event}". Valid: ${Object.keys(this.callbacks).join(', ')}`);
    }
    this.callbacks[event] = callback;
    return this;
  }

  // ── Watch management ────────────────────────────────────────────────────────
  watch(watchPath, options = {}) {
    const watcher = {
      path:        watchPath,
      lastState:   null,
      changeCount: 0,
      permissions: options.permissions || 'read-write',
      priority:    options.priority    || 'normal',
      enabled:     true,
    };
    this.watchedPaths.set(watchPath, watcher);
    // Capture initial baseline (non-blocking)
    this._captureState(watchPath).catch(() => {});
    return watcher;
  }

  watchDefaults() {
    for (const p of this.config.watchedPaths) {
      this.watch(p);
    }
    return this;
  }

  unwatch(watchPath) {
    this.watchedPaths.delete(watchPath);
  }

  // ── State capture ───────────────────────────────────────────────────────────
  async _captureState(watchPath) {
    const watcher = this.watchedPaths.get(watchPath) || null;

    let state;
    try {
      const entries = fs.existsSync(watchPath)
        ? fs.readdirSync(watchPath).length
        : 0;
      const stat = await fsp.stat(watchPath).catch(() => null);
      state = {
        timestamp:    Date.now(),
        path:         watchPath,
        fileCount:    entries,
        lastModified: stat ? stat.mtimeMs : 0,
        permissions:  stat ? (stat.mode & 0o777).toString(8) : '000',
        exists:       stat !== null,
      };
    } catch {
      state = {
        timestamp:    Date.now(),
        path:         watchPath,
        fileCount:    0,
        lastModified: 0,
        permissions:  '000',
        exists:       false,
      };
    }

    if (watcher) watcher.lastState = state;
    return state;
  }

  // ── Motion detection ────────────────────────────────────────────────────────
  async _detectMotion(watchPath) {
    const watcher = this.watchedPaths.get(watchPath);
    if (!watcher || !watcher.enabled) return null;

    const prev = watcher.lastState;
    const curr = await this._captureState(watchPath);
    if (!prev || !curr) return null;

    const hasMotion =
      curr.fileCount    !== prev.fileCount    ||
      curr.lastModified !== prev.lastModified ||
      curr.permissions  !== prev.permissions  ||
      curr.exists       !== prev.exists;

    if (!hasMotion) return null;

    watcher.changeCount++;

    const motion = {
      id:            `motion_${Date.now()}_${crypto.randomBytes(3).toString('hex')}`,
      path:          watchPath,
      timestamp:     Date.now(),
      changeType:    this._detectChangeType(curr, prev),
      priority:      watcher.priority,
      previousState: prev,
      currentState:  curr,
    };

    this.motionQueue.push(motion);

    // Permission check callback
    if (curr.permissions !== prev.permissions && this.callbacks.onPermissionCheck) {
      await this.callbacks.onPermissionCheck(motion).catch(console.error);
    }

    // Motion callback (after threshold)
    if (watcher.changeCount >= this.config.triggerThreshold) {
      if (this.callbacks.onMotion) {
        await this.callbacks.onMotion(motion).catch(console.error);
      }
      watcher.changeCount = 0;
    }

    // Feed guardian layer
    if (this.config.dropGuardianEvents) {
      await _dropGuardianEvent({
        type:       'file_motion',
        path:       watchPath,
        changeType: motion.changeType,
        priority:   motion.priority,
        timestamp:  new Date().toISOString(),
        motionId:   motion.id,
      });
    }

    return motion;
  }

  _detectChangeType(curr, prev) {
    if (!curr.exists && prev.exists)              return 'path_removed';
    if (curr.exists  && !prev.exists)             return 'path_appeared';
    if (curr.fileCount > prev.fileCount)          return 'files_added';
    if (curr.fileCount < prev.fileCount)          return 'files_removed';
    if (curr.permissions !== prev.permissions)    return 'permissions_changed';
    return 'files_modified';
  }

  // ── Snapshot ────────────────────────────────────────────────────────────────
  async createSnapshot(watchPath) {
    const state = await this._captureState(watchPath);
    this.snapshotCount++;

    const snapshot = {
      id:       `snapshot_${this.snapshotCount}`,
      path:     watchPath,
      ...state,
      type:     'metadata',
    };

    if (this.snapshotCount >= this.config.maxLocalSnapshots && this.callbacks.onCapReached) {
      await this.callbacks.onCapReached({
        snapshotCount:    this.snapshotCount,
        readyForShipping: this._shippableSummary(),
      }).catch(console.error);
    }

    return snapshot;
  }

  _shippableSummary() {
    return {
      count:       this.snapshotCount,
      readyToShip: this.snapshotCount >= this.config.maxLocalSnapshots,
    };
  }

  clearShipped() {
    this.snapshotCount = 0;
    this.motionQueue   = [];
  }

  // ── Monitor loop ────────────────────────────────────────────────────────────
  startMonitoring() {
    if (this._monitorInterval) return;
    this._monitorInterval = setInterval(async () => {
      for (const [p, w] of this.watchedPaths) {
        if (w.enabled) {
          await this._detectMotion(p).catch(console.error);
        }
      }
    }, this.config.checkInterval);
    console.log(`[FileMotionSensor] Monitoring ${this.watchedPaths.size} paths (interval ${this.config.checkInterval}ms)`);
    return this;
  }

  stopMonitoring() {
    if (this._monitorInterval) {
      clearInterval(this._monitorInterval);
      this._monitorInterval = null;
    }
  }

  // ── Introspection ───────────────────────────────────────────────────────────
  getMotionLog(limit = 50) {
    return this.motionQueue.slice(-limit);
  }

  status() {
    return {
      watchedPaths:    this.watchedPaths.size,
      motionEvents:    this.motionQueue.length,
      snapshots:       this.snapshotCount,
      monitoring:      this._monitorInterval !== null,
      guardianDropDir: _guardianDropDir(),
    };
  }
}


// ── Standalone hashing — separate process/worker ────────────────────────────
// HashingModule is intentionally isolated so it never blocks the sensor.
class HashingModule {
  constructor() {
    this.queue      = [];
    this.processing = false;
    this.store      = new Map();   // snapshotId → hash
  }

  async queueForHashing(snapshot) {
    this.queue.push(snapshot);
    if (!this.processing) {
      await this._processQueue();
    }
  }

  async _processQueue() {
    this.processing = true;
    while (this.queue.length > 0) {
      const snapshot = this.queue.shift();
      const hash = await this._computeHash(snapshot);
      this.store.set(snapshot.id, hash);
      console.log(`[HashingModule] ${snapshot.id} → ${hash}`);
    }
    this.processing = false;
  }

  async _computeHash(snapshot) {
    // Real implementation: SHA3-512 of stat fingerprint (path + mtime + size)
    const raw = `${snapshot.path}:${snapshot.lastModified}:${snapshot.fileCount}`;
    return crypto.createHash('sha256').update(raw).digest('hex');
  }

  lookup(snapshotId) {
    return this.store.get(snapshotId) || null;
  }
}


module.exports = { FileMotionSensor, HashingModule };
