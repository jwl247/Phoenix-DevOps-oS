// node slot-transfer.test.js — every rule in slot-transfer.js, on real temp folders.
const fs = require('fs');
const os = require('os');
const path = require('path');
const { transfer } = require('./slot-transfer');

let pass = 0, fail = 0;
const ok = (label, cond) => { if (cond) pass++; else { fail++; console.log('FAIL', label); } };

const T = fs.mkdtempSync(path.join(os.tmpdir(), 'slots-'));
const A = path.join(T, 'A'), B = path.join(T, 'B'), OUT = path.join(T, 'outside'), VAULT = path.join(T, 'breach_coms4');
for (const d of [A, B, OUT, VAULT, path.join(A, 'sub'), path.join(A, 'proj', 'deep')]) fs.mkdirSync(d, { recursive: true });
const w = (p, s) => fs.writeFileSync(p, s);
w(path.join(A, 'a.txt'), 'alpha'); w(path.join(A, 'c.txt'), 'gamma'); w(path.join(A, 'proj', 'deep', 'x.py'), 'print(1)');
w(path.join(B, 'a.txt'), 'other alpha'); w(path.join(OUT, 'from-explorer.txt'), 'dropped'); w(path.join(VAULT, 'key.txt'), 'vault');
const slots = [A, B, null, VAULT, null, null];

let r = transfer({ sources: [path.join(A, 'c.txt')], toDir: B, mode: 'move' }, slots);
ok('move a file A -> B', r.success && !fs.existsSync(path.join(A, 'c.txt')) && fs.readFileSync(path.join(B, 'c.txt'), 'utf8') === 'gamma');

r = transfer({ sources: [path.join(A, 'a.txt')], toDir: B, mode: 'move' }, slots);
ok('never overwrite: a.txt exists in B', !r.success && r.skipped[0].reason.includes('already exists') && fs.readFileSync(path.join(B, 'a.txt'), 'utf8') === 'other alpha' && fs.existsSync(path.join(A, 'a.txt')));

r = transfer({ sources: [path.join(A, 'a.txt')], toDir: path.join(B), mode: 'copy' }, [A, path.join(T, 'B2')]);
ok('destination must be a slot', !r.success && /not inside/.test(r.error) || /not a folder/.test(r.error));

r = transfer({ sources: [path.join(A, 'proj')], toDir: path.join(B), mode: 'copy' }, slots);
ok('copy a folder tree', r.success && fs.readFileSync(path.join(B, 'proj', 'deep', 'x.py'), 'utf8') === 'print(1)' && fs.existsSync(path.join(A, 'proj', 'deep', 'x.py')));

r = transfer({ sources: [path.join(A, 'proj')], toDir: path.join(A, 'proj', 'deep'), mode: 'move' }, slots);
ok("folder can't go inside itself", !r.success && /inside itself/.test(r.skipped[0].reason) && fs.existsSync(path.join(A, 'proj')));

r = transfer({ sources: [path.join(A, 'a.txt')], toDir: path.join(A, 'sub'), mode: 'move' }, slots);
ok('move into a subfolder of the same slot', r.success && fs.existsSync(path.join(A, 'sub', 'a.txt')));

r = transfer({ sources: [path.join(OUT, 'from-explorer.txt')], toDir: B, mode: 'move' }, slots);
ok('drag from outside the slots (not external) refused', !r.success && /not from a slot/.test(r.skipped[0].reason));

r = transfer({ sources: [path.join(OUT, 'from-explorer.txt')], toDir: B, mode: 'move', external: true }, slots);
ok('Explorer drop is forced to COPY', r.success && r.mode === 'copy' && fs.existsSync(path.join(OUT, 'from-explorer.txt')) && fs.existsSync(path.join(B, 'from-explorer.txt')));

r = transfer({ sources: [path.join(VAULT, 'key.txt')], toDir: B, mode: 'move' }, slots);
ok('never MOVE out of breach_coms4', !r.success && /master vault/.test(r.skipped[0].reason) && fs.existsSync(path.join(VAULT, 'key.txt')));
r = transfer({ sources: [path.join(VAULT, 'key.txt')], toDir: B, mode: 'copy' }, slots);
ok('…copy from it is fine', r.success && fs.existsSync(path.join(VAULT, 'key.txt')) && fs.existsSync(path.join(B, 'key.txt')));

r = transfer({ sources: [path.join(B, 'a.txt')], toDir: B, mode: 'move' }, slots);
ok('same folder = no-op, told why', !r.success && /already in that folder/.test(r.skipped[0].reason));

r = transfer({ sources: [path.join(A, '..', 'outside', 'from-explorer.txt')], toDir: path.join(B, '..', 'A'), mode: 'move' }, slots);
ok('../ tricks resolve before the checks', !r.success && /not from a slot/.test(r.skipped[0].reason));

// Cross-drive move: rename fails with EXDEV -> copy, verify, then remove.
const realRename = fs.renameSync;
fs.renameSync = () => { const e = new Error('cross-device'); e.code = 'EXDEV'; throw e; };
fs.mkdirSync(path.join(A, 'xdev', 'in'), { recursive: true }); w(path.join(A, 'xdev', 'in', 'f.bin'), Buffer.alloc(70000, 7));
r = transfer({ sources: [path.join(A, 'xdev')], toDir: B, mode: 'move' }, slots);
ok('cross-drive move: copied, verified, original removed', r.success && !fs.existsSync(path.join(A, 'xdev')) && fs.statSync(path.join(B, 'xdev', 'in', 'f.bin')).size === 70000);
// …and when the copy doesn't verify, the original stays
const realCp = fs.cpSync;
fs.cpSync = (s, d, o) => { realCp(s, d, o); fs.writeFileSync(path.join(d, 'in', 'f.bin'), 'corrupted'); };
fs.mkdirSync(path.join(A, 'xdev2', 'in'), { recursive: true }); w(path.join(A, 'xdev2', 'in', 'f.bin'), 'good');
r = transfer({ sources: [path.join(A, 'xdev2')], toDir: B, mode: 'move' }, slots);
ok('bad copy: original kept, bad copy removed', !r.success && /did not verify/.test(r.skipped[0].reason) && fs.readFileSync(path.join(A, 'xdev2', 'in', 'f.bin'), 'utf8') === 'good' && !fs.existsSync(path.join(B, 'xdev2')));
fs.renameSync = realRename; fs.cpSync = realCp;

w(path.join(A, 'sub', 'new.txt'), 'n');
r = transfer({ sources: [path.join(A, 'sub', 'new.txt'), path.join(A, 'proj')], toDir: B, mode: 'move' }, slots);
ok('several at once: one moves, the clash is reported', r.done.length === 1 && r.skipped.length === 1);

// Rename
const { rename } = require('./slot-transfer');
const R = fs.mkdtempSync(path.join(os.tmpdir(), 'ren-')); fs.writeFileSync(path.join(R, 'old.txt'), 'x'); fs.writeFileSync(path.join(R, 'taken.txt'), 'keep');
let rr = rename({ path: path.join(R, 'old.txt'), newName: 'new.txt' }, [R]);
ok('rename works', rr.success && fs.existsSync(path.join(R, 'new.txt')) && !fs.existsSync(path.join(R, 'old.txt')));
rr = rename({ path: path.join(R, 'new.txt'), newName: 'taken.txt' }, [R]);
ok('rename never overwrites', !rr.success && fs.readFileSync(path.join(R, 'taken.txt'), 'utf8') === 'keep');
rr = rename({ path: path.join(R, 'new.txt'), newName: '../escape.txt' }, [R]);
ok('rename refuses paths in the name', !rr.success && fs.existsSync(path.join(R, 'new.txt')));
rr = rename({ path: path.join(R, 'new.txt'), newName: 'x.txt' }, [path.join(T, 'nowhere')]);
ok('rename only inside places/slots', !rr.success);
fs.mkdirSync(path.join(R, 'breach_coms4')); fs.writeFileSync(path.join(R, 'breach_coms4', 'v.txt'), 'v');
rr = rename({ path: path.join(R, 'breach_coms4', 'v.txt'), newName: 'w.txt' }, [R]);
ok('nothing renamed in breach_coms4', !rr.success && fs.existsSync(path.join(R, 'breach_coms4', 'v.txt')));
fs.rmSync(R, { recursive: true, force: true });

// OS folders: never a destination, never moved (Linux rules here; Windows rules are the same shape)
const { isSystem } = require('./slot-transfer');
if (process.platform !== 'win32') {
    r = transfer({ sources: [path.join(A, 'proj')], toDir: '/etc', mode: 'copy' }, ['/']);
    ok('never put anything into an OS folder', !r.success && /operating-system/.test(r.error));
    ok('OS folder detection', isSystem('/usr/lib') && isSystem('/etc') && !isSystem('/home/x') && !isSystem('/etcetera'));
}

fs.rmSync(T, { recursive: true, force: true });
console.log(fail ? `${fail} FAILED, ${pass} passed` : `all ${pass} slot-transfer checks pass`);
process.exit(fail ? 1 : 0);
