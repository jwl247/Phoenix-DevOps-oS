// Quick real-filesystem test for config-centralizer.js — not part of any
// suite runner, just a standalone script: node config-centralizer.test.js
const fs = require('fs');
const os = require('os');
const path = require('path');
const assert = require('assert');

// Deliberately NOT under os.tmpdir() — that resolves to AppData/Local/Temp
// on Windows, which config-centralizer.js intentionally skips as real-temp
// junk. A synthetic home there would silently exclude itself.
const tmpRoot = fs.mkdtempSync(path.join(__dirname, 'cc-test-'));

// Build a fake "home" with a mix of real config-shaped files and noise,
// then point the module's scan at it by monkey-patching os.homedir()
// before requiring the module (it reads HOME at require-time).
const realHomedir = os.homedir;
os.homedir = () => tmpRoot;

fs.mkdirSync(path.join(tmpRoot, '.ssh'), { recursive: true });
fs.writeFileSync(path.join(tmpRoot, '.ssh', 'config'), 'Host example\n  User me\n');
fs.mkdirSync(path.join(tmpRoot, '.phoenix'), { recursive: true });
fs.writeFileSync(path.join(tmpRoot, '.phoenix', 'phoenix.env'), 'PHOENIX_ROOT=D:/x\n');
fs.writeFileSync(path.join(tmpRoot, '.phoenix', 'api_secret_key.json'), '{"key":"fake"}');
fs.mkdirSync(path.join(tmpRoot, '.phoenix', '__pycache__'), { recursive: true });
fs.writeFileSync(path.join(tmpRoot, '.phoenix', '__pycache__', 'noise.pyc'), 'binary junk');
fs.mkdirSync(path.join(tmpRoot, 'AppData', 'Roaming', 'SomeApp'), { recursive: true });
fs.writeFileSync(path.join(tmpRoot, 'AppData', 'Roaming', 'SomeApp', 'settings.json'), '{}');
fs.writeFileSync(path.join(tmpRoot, 'AppData', 'Roaming', 'SomeApp', 'app.log'), 'noise');

const cc = require('./config-centralizer');

const results = cc.scan();
const summary = cc.summarize(results);

console.log('Scan found', results.length, 'items');
results.forEach(r => console.log(' -', r.category, r.sensitive ? '[sensitive]' : '', r.path));

// __pycache__ and .log noise must be excluded
assert.ok(!results.some(r => r.path.includes('__pycache__')), '__pycache__ file should be skipped');
assert.ok(!results.some(r => r.path.endsWith('.log')), '.log file should be skipped');

// The 3 real config-shaped files should be found
const sshConfig = results.find(r => r.path.endsWith(path.join('.ssh', 'config')));
assert.ok(sshConfig, 'ssh config should be found');
assert.strictEqual(sshConfig.category, 'ssh');
assert.strictEqual(sshConfig.sensitive, true);

const secretKey = results.find(r => r.path.endsWith('api_secret_key.json'));
assert.ok(secretKey, 'api secret key file should be found');
assert.strictEqual(secretKey.category, 'secret');
assert.strictEqual(secretKey.sensitive, true);

const appSettings = results.find(r => r.path.endsWith(path.join('SomeApp', 'settings.json')));
assert.ok(appSettings, 'app settings.json should be found');
assert.strictEqual(appSettings.category, 'config');

assert.strictEqual(summary.total, results.length);
assert.strictEqual(summary.sensitive, 3); // ssh/config, api_secret_key.json, phoenix.env (environment category is always sensitive)
console.log('Summary:', summary);

// ── Import + sync round trip ──────────────────────────────────────
const importResult = cc.importConfig(sshConfig);
assert.strictEqual(importResult.success, true, 'import should succeed');
assert.ok(fs.existsSync(importResult.masterPath), 'master copy should exist on disk');
assert.ok(fs.existsSync(`${sshConfig.path}.backup`), 'a .backup of the original should be created');

// Mutate the master copy, then sync back, and confirm the original changed
fs.writeFileSync(importResult.masterPath, 'Host example\n  User CHANGED\n');
const syncResults = cc.syncAll();
assert.ok(syncResults[importResult.masterPath].success, 'sync should succeed');
const originalNow = fs.readFileSync(sshConfig.path, 'utf8');
assert.ok(originalNow.includes('CHANGED'), 'original file should reflect the synced master content');

const imported = cc.listImported();
assert.strictEqual(imported.length, 1);
assert.strictEqual(imported[0].original, sshConfig.path);

console.log('\nALL CONFIG-CENTRALIZER TESTS PASSED');

os.homedir = realHomedir;
fs.rmSync(tmpRoot, { recursive: true, force: true });
fs.rmSync(cc.CENTRALIZER_ROOT, { recursive: true, force: true });
