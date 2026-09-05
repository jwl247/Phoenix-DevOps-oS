// config-centralizer.js — Phoenix Dashboard, Settings tab
// Node/Electron port of the real config_centralizer.py recovered from an
// old claude.ai conversation (docs/config centralizer canner manager.txt —
// the CLI scanner/manager, complete and real, no mocks). Ported to Node
// rather than shelled out to Python, to stay consistent with the rest of
// the dashboard (pure Node/Electron already, no other Python dependency
// exists in main.js). Scan locations adapted for Windows, where this
// dashboard actually runs, rather than the original's Linux-only
// ~/.config, ~/.local/share, systemd paths.
//
// The GUI widget this logic was originally paired with (docs/config widget
// gui.txt) was wired to hardcoded mock data, not this real scanner — that
// mistake isn't repeated here.

const fs = require('fs');
const path = require('path');
const os = require('os');
const { execFile } = require('child_process');

const HOME = os.homedir();

const CONFIG_EXTENSIONS = new Set(['.conf', '.config', '.cfg', '.json', '.yaml', '.yml', '.toml', '.ini', '.env']);
const SERVICE_EXTENSIONS = new Set(['.service', '.timer', '.socket']);
const RC_NAME = /rc$/i;
const SENSITIVE_NAME = /api.?key|token|secret|credential|password/i;

const SKIP_PATTERNS = [
  /[\\/]cache[\\/]/i, /\.log$/i, /[\\/]logs?[\\/]/i, /[\\/]tmp[\\/]/i, /[\\/]temp[\\/]/i,
  /\.lock$/i, /\.pid$/i, /node_modules/i, /__pycache__/i, /\.pyc$/i, /[\\/]venv[\\/]/i,
  /[\\/]\.git[\\/]/i, /AppData[\\/]Local[\\/]Temp/i, /AppData[\\/]Local[\\/]Packages/i,
];

// Windows equivalents of the original's Linux scan locations. .ssh/.aws/.kube
// live under the user profile on Windows too; AppData/Roaming is the closest
// analogue to ~/.local/share; ~/.phoenix is Phoenix's own config, worth
// including since that's exactly the kind of scattered config this exists
// to find.
const SCAN_LOCATIONS = [
  path.join(HOME, '.ssh'),
  path.join(HOME, '.aws'),
  path.join(HOME, '.kube'),
  path.join(HOME, '.phoenix'),
  path.join(HOME, 'AppData', 'Roaming'),
];

const MAX_FILE_BYTES = 10 * 1024 * 1024; // >10MB is almost certainly not a config
const MAX_SCAN_DEPTH = 6; // AppData/Roaming is deep and noisy — cap recursion

function shouldSkipPath(fullPath) {
  return SKIP_PATTERNS.some(p => p.test(fullPath));
}

// Directories whose entire contents are credential/config files by
// convention, even though the files themselves are often bare-named with
// no extension (~/.ssh/config, ~/.aws/credentials, ~/.kube/config,
// ~/.ssh/id_ed25519). Extension/name pattern matching alone misses every
// one of these — which would defeat the entire reason these directories
// are scan locations in the first place. This was a real bug inherited
// from the original Python (its own config_patterns/api_key_patterns
// never matched a bare "config" or "credentials" filename either).
const ALWAYS_MATCH_DIRS = new Set(['.ssh', '.aws', '.kube']);

function matchesConfigPattern(fullPath) {
  const name = path.basename(fullPath).toLowerCase();
  const ext = path.extname(name);
  const parentDir = path.basename(path.dirname(fullPath)).toLowerCase();
  if (ALWAYS_MATCH_DIRS.has(parentDir)) return true;
  if (CONFIG_EXTENSIONS.has(ext)) return true;
  if (SERVICE_EXTENSIONS.has(ext)) return true;
  if (RC_NAME.test(name)) return true;
  if (SENSITIVE_NAME.test(name)) return true;
  return false;
}

function categorize(fullPath, stat) {
  const p = fullPath.toLowerCase();
  const name = path.basename(fullPath).toLowerCase();
  const ext = path.extname(name);

  let category = 'unknown';
  let importance = 1;
  let sensitive = false;

  const parentDirLower = path.basename(path.dirname(fullPath)).toLowerCase();

  if (SENSITIVE_NAME.test(p)) {
    category = 'secret'; importance = 5; sensitive = true;
  } else if (SERVICE_EXTENSIONS.has(ext)) {
    category = 'service'; importance = 4;
  } else if (parentDirLower === '.ssh') {
    category = 'ssh'; importance = 5; sensitive = true;
  } else if (parentDirLower === '.aws' || parentDirLower === '.kube') {
    // Bare-named files here (credentials, config) always hold cluster/cloud
    // credentials by convention — same treatment as .ssh.
    category = 'ssh'; importance = 5; sensitive = true;
  } else if (RC_NAME.test(name) || ['profile', 'bash_profile', 'zshrc', 'bashrc'].includes(name)) {
    category = 'shell'; importance = 4;
  } else if (name.includes('.env')) {
    category = 'environment'; importance = 4; sensitive = true;
  } else if (p.includes('config') || name.includes('config')) {
    category = 'application'; importance = 3;
  } else if (CONFIG_EXTENSIONS.has(ext)) {
    category = 'config'; importance = 3;
  }

  return {
    path: fullPath,
    category,
    importance,
    sensitive,
    size: stat.size,
    modified: stat.mtime.toISOString(),
    recommend_import: importance >= 3,
  };
}

function walk(dir, results, seen, depth) {
  if (depth > MAX_SCAN_DEPTH) return;
  let entries;
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true });
  } catch (_) {
    return; // permission denied / gone — skip, don't crash the scan
  }
  for (const entry of entries) {
    const full = path.join(dir, entry.name);
    if (shouldSkipPath(full)) continue;
    if (entry.isDirectory()) {
      walk(full, results, seen, depth + 1);
    } else if (entry.isFile()) {
      if (seen.has(full)) continue;
      seen.add(full);
      let stat;
      try {
        stat = fs.statSync(full);
      } catch (_) {
        continue;
      }
      if (stat.size > MAX_FILE_BYTES) continue;
      if (matchesConfigPattern(full)) {
        results.push(categorize(full, stat));
      }
    }
  }
}

function scan() {
  const results = [];
  const seen = new Set();
  for (const loc of SCAN_LOCATIONS) {
    if (fs.existsSync(loc)) walk(loc, results, seen, 0);
  }
  results.sort((a, b) => (b.importance - a.importance) || a.path.localeCompare(b.path));
  return results;
}

function summarize(results) {
  const categories = {};
  let totalSize = 0;
  let recommended = 0;
  let sensitive = 0;
  for (const r of results) {
    categories[r.category] = (categories[r.category] || 0) + 1;
    totalSize += r.size;
    if (r.recommend_import) recommended++;
    if (r.sensitive) sensitive++;
  }
  return {
    total: results.length,
    categories,
    total_size_mb: totalSize / (1024 * 1024),
    recommended,
    sensitive,
  };
}

// ── Centralized storage ─────────────────────────────────────────
const CENTRALIZER_ROOT = path.join(HOME, '.phoenix', 'config-centralizer');
const MASTER_DIR = path.join(CENTRALIZER_ROOT, 'master');
const MAPPING_FILE = path.join(CENTRALIZER_ROOT, 'config-mapping.json');
const SUBDIRS = ['apis', 'services', 'applications', 'system', 'secrets', 'shell'];

const CATEGORY_SUBDIR = {
  secret: 'secrets', service: 'services', application: 'applications',
  ssh: 'secrets', shell: 'shell', environment: 'applications',
  config: 'applications', unknown: 'applications',
};

function ensureMasterDirs() {
  fs.mkdirSync(MASTER_DIR, { recursive: true });
  for (const sub of SUBDIRS) fs.mkdirSync(path.join(MASTER_DIR, sub), { recursive: true });
}

function loadMapping() {
  if (fs.existsSync(MAPPING_FILE)) {
    try {
      return JSON.parse(fs.readFileSync(MAPPING_FILE, 'utf8'));
    } catch (_) {
      // corrupt mapping file — don't crash, just start fresh rather than
      // silently losing the ability to sync anything at all
    }
  }
  return { configs: {} };
}

function saveMapping(mapping) {
  fs.writeFileSync(MAPPING_FILE, JSON.stringify(mapping, null, 2), 'utf8');
}

function masterPathFor(originalPath, category) {
  const name = path.basename(originalPath);
  const subdir = CATEGORY_SUBDIR[category] || 'applications';
  let target = path.join(MASTER_DIR, subdir, name);
  if (fs.existsSync(target)) {
    // Name collision — differentiate by parent directory, same as the
    // original Python (get_master_path).
    const parentName = path.basename(path.dirname(originalPath));
    target = path.join(MASTER_DIR, subdir, `${parentName}_${name}`);
  }
  return target;
}

function importConfig(item, { backup = true } = {}) {
  ensureMasterDirs();
  try {
    const masterPath = masterPathFor(item.path, item.category);
    if (backup) {
      const backupPath = `${item.path}.backup`;
      if (!fs.existsSync(backupPath)) fs.copyFileSync(item.path, backupPath);
    }
    fs.copyFileSync(item.path, masterPath);

    const mapping = loadMapping();
    mapping.configs[masterPath] = {
      original: item.path,
      category: item.category,
      imported: new Date().toISOString(),
      sensitive: !!item.sensitive,
    };
    saveMapping(mapping);

    return { success: true, masterPath };
  } catch (e) {
    return { success: false, error: e.message };
  }
}

function importMany(items, opts) {
  const results = [];
  for (const item of items) {
    results.push({ path: item.path, ...importConfig(item, opts) });
  }
  return results;
}

function syncAll() {
  const mapping = loadMapping();
  const results = {};
  for (const masterPath of Object.keys(mapping.configs)) {
    if (!fs.existsSync(masterPath)) continue;
    const original = mapping.configs[masterPath].original;
    try {
      fs.copyFileSync(masterPath, original);
      results[masterPath] = { success: true, original };
    } catch (e) {
      results[masterPath] = { success: false, error: e.message, original };
    }
  }
  return results;
}

function listImported() {
  const mapping = loadMapping();
  return Object.entries(mapping.configs).map(([masterPath, info]) => ({ masterPath, ...info }));
}

// ── Git versioning of the master dir (small, scoped, part of the real
// config_centralizer feature — NOT the parked whole-filesystem restic
// system, which is a separate, bigger, unfinished thing) ──────────
function runGit(args) {
  return new Promise((resolve) => {
    execFile('git', args, { cwd: CENTRALIZER_ROOT }, (err, stdout, stderr) => {
      if (err) resolve({ success: false, error: (stderr || err.message).trim() });
      else resolve({ success: true, output: stdout.trim() });
    });
  });
}

async function initGit() {
  ensureMasterDirs();
  if (fs.existsSync(path.join(CENTRALIZER_ROOT, '.git'))) {
    return { success: true, message: 'Git repository already exists' };
  }
  const init = await runGit(['init']);
  if (!init.success) return init;
  await runGit(['add', '.']);
  const commit = await runGit(['commit', '-m', 'Initial config import']);
  return commit.success
    ? { success: true, message: 'Git repository initialized' }
    : { success: true, message: 'Git repository initialized (nothing to commit yet)' };
}

async function commitChanges(message) {
  const msg = message || `Config update ${new Date().toISOString()}`;
  await runGit(['add', '.']);
  const result = await runGit(['commit', '-m', msg]);
  return result.success ? { success: true, message: 'Changes committed' } : { success: true, message: 'No changes to commit' };
}

// ── IPC registration, same shape as the other *-launcher.js modules ──
function register({ ipcMain }) {
  ipcMain.handle('config-centralizer-scan', async () => {
    try {
      const results = scan();
      return { success: true, results, summary: summarize(results) };
    } catch (e) {
      return { success: false, error: e.message };
    }
  });

  ipcMain.handle('config-centralizer-import', async (event, { items, backup = true } = {}) => {
    if (!Array.isArray(items) || items.length === 0) {
      return { success: false, error: 'no items provided' };
    }
    try {
      const results = importMany(items, { backup });
      return { success: true, results };
    } catch (e) {
      return { success: false, error: e.message };
    }
  });

  ipcMain.handle('config-centralizer-sync-all', async () => {
    try {
      return { success: true, results: syncAll() };
    } catch (e) {
      return { success: false, error: e.message };
    }
  });

  ipcMain.handle('config-centralizer-list-imported', async () => {
    try {
      return { success: true, items: listImported() };
    } catch (e) {
      return { success: false, error: e.message };
    }
  });

  ipcMain.handle('config-centralizer-init-git', async () => initGit());
  ipcMain.handle('config-centralizer-commit', async (event, { message } = {}) => commitChanges(message));
}

module.exports = {
  scan, summarize, importConfig, importMany, syncAll, listImported,
  initGit, commitChanges, register, MASTER_DIR, CENTRALIZER_ROOT,
};
