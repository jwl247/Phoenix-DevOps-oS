// node slot-transfer.test.js — every rule in slot-transfer.js, on real temp folders.
const fs = require('fs');
const os = require('os');
const path = require('path');
const st = require('./slot-transfer');
const { isSystem, moveRoots, defaultLabelsUnder } = st;

let pass = 0, fail = 0;
const ok = (label, cond) => { if (cond) pass++; else { fail++; console.log('FAIL', label); } };

// Volume labels are injected so the checks are the same on every machine.
// VAULT_DRV stands in for a drive whose LABEL is breach_coms4 (no "breach_coms4" in its path).
const T = fs.mkdtempSync(path.join(os.tmpdir(), 'slots-'));
const A = path.join(T, 'A'), B = path.join(T, 'B'), OUT = path.join(T, 'outside'), VAULT = path.join(T, 'breach_coms4');
const VAULT_DRV = path.join(T, 'G-drive');
const plain = { labelsUnder: async (p) => (p.startsWith(VAULT_DRV) ? ['breach_coms4'] : ['DATA']) };
const transfer = (req, roots, opts = plain) => st.transfer(req, roots, opts);
const rename = (req, roots, opts = plain) => st.rename(req, roots, opts);

(async () => {
    for (const d of [A, B, OUT, VAULT, VAULT_DRV, path.join(A, 'sub'), path.join(A, 'proj', 'deep')]) fs.mkdirSync(d, { recursive: true });
    const w = (p, s) => fs.writeFileSync(p, s);
    w(path.join(A, 'a.txt'), 'alpha'); w(path.join(A, 'c.txt'), 'gamma'); w(path.join(A, 'proj', 'deep', 'x.py'), 'print(1)');
    w(path.join(B, 'a.txt'), 'other alpha'); w(path.join(OUT, 'from-explorer.txt'), 'dropped'); w(path.join(VAULT, 'key.txt'), 'vault');
    w(path.join(VAULT_DRV, 'master.bin'), 'master');
    const slots = [A, B, null, VAULT, VAULT_DRV, null];

    let r = await transfer({ sources: [path.join(A, 'c.txt')], toDir: B, mode: 'move' }, slots);
    ok('move a file A -> B', r.success && r.mode === 'move' && !fs.existsSync(path.join(A, 'c.txt')) && fs.readFileSync(path.join(B, 'c.txt'), 'utf8') === 'gamma');

    r = await transfer({ sources: [path.join(A, 'a.txt')], toDir: B, mode: 'move' }, slots);
    ok('never overwrite: a.txt exists in B', !r.success && r.skipped[0].reason.includes('already exists') && fs.readFileSync(path.join(B, 'a.txt'), 'utf8') === 'other alpha' && fs.existsSync(path.join(A, 'a.txt')));

    r = await transfer({ sources: [path.join(A, 'a.txt')], toDir: path.join(B), mode: 'copy' }, [A, path.join(T, 'B2')]);
    ok('destination must be a slot', !r.success && (/not inside/.test(r.error) || /not a folder/.test(r.error)));

    r = await transfer({ sources: [path.join(A, 'proj')], toDir: path.join(B), mode: 'copy' }, slots);
    ok('copy a folder tree', r.success && fs.readFileSync(path.join(B, 'proj', 'deep', 'x.py'), 'utf8') === 'print(1)' && fs.existsSync(path.join(A, 'proj', 'deep', 'x.py')));

    r = await transfer({ sources: [path.join(A, 'proj')], toDir: path.join(A, 'proj', 'deep'), mode: 'move' }, slots);
    ok("folder can't go inside itself", !r.success && /inside itself/.test(r.skipped[0].reason) && fs.existsSync(path.join(A, 'proj')));

    r = await transfer({ sources: [path.join(A, 'a.txt')], toDir: path.join(A, 'sub'), mode: 'move' }, slots);
    ok('move into a subfolder of the same slot', r.success && fs.existsSync(path.join(A, 'sub', 'a.txt')));

    // DASH-S19: copy-only for anything outside the roots is decided in main, not by the page's flag.
    r = await transfer({ sources: [path.join(OUT, 'from-explorer.txt')], toDir: B, mode: 'move', external: false }, slots);
    ok('external:false from outside the roots is still COPY only', r.success && r.mode === 'copy' && r.done[0].mode === 'copy'
        && fs.existsSync(path.join(OUT, 'from-explorer.txt')) && fs.existsSync(path.join(B, 'from-explorer.txt')));
    fs.rmSync(path.join(B, 'from-explorer.txt'));
    r = await transfer({ sources: [path.join(OUT, 'from-explorer.txt')], toDir: B, mode: 'move' }, slots);
    ok('no flag at all from outside the roots: COPY only', r.success && r.mode === 'copy' && fs.existsSync(path.join(OUT, 'from-explorer.txt')));
    fs.rmSync(path.join(B, 'from-explorer.txt'));
    r = await transfer({ sources: [path.join(OUT, 'from-explorer.txt')], toDir: B, mode: 'move', external: true }, slots);
    ok('Explorer drop (external:true) is COPY', r.success && r.mode === 'copy' && fs.existsSync(path.join(OUT, 'from-explorer.txt')) && fs.existsSync(path.join(B, 'from-explorer.txt')));
    w(path.join(A, 'inside.txt'), 'i');
    r = await transfer({ sources: [path.join(A, 'inside.txt')], toDir: B, mode: 'move', external: true }, slots);
    ok('external:true can only narrow: in-root item is copied, not moved', r.success && r.mode === 'copy' && fs.existsSync(path.join(A, 'inside.txt')));

    // DASH-S19: roots are explicit places, never every drive.
    const mr = moveRoots(path.join(T, 'nope'), [A, null, B]);
    const driveRoot = (p) => path.parse(p).root === p;
    ok('move roots = HOME + slots (+ repo), no drive roots', mr.includes(os.homedir()) && mr.includes(A) && mr.includes(B) && !mr.some(driveRoot) && !mr.includes('/'));
    ok('move roots include the Phoenix repo when it exists', moveRoots(T, []).includes(T));

    r = await transfer({ sources: [path.join(VAULT, 'key.txt')], toDir: B, mode: 'move' }, slots);
    ok('never MOVE out of breach_coms4 (path text)', !r.success && /master vault/.test(r.skipped[0].reason) && fs.existsSync(path.join(VAULT, 'key.txt')));
    r = await transfer({ sources: [path.join(VAULT, 'key.txt')], toDir: B, mode: 'copy' }, slots);
    ok('…copy from it is fine', r.success && fs.existsSync(path.join(VAULT, 'key.txt')) && fs.existsSync(path.join(B, 'key.txt')));

    // DASH-F26: the drive is breach_coms4 by LABEL, path says nothing.
    r = await transfer({ sources: [path.join(VAULT_DRV, 'master.bin')], toDir: B, mode: 'move' }, slots);
    ok('never MOVE off a drive LABELLED breach_coms4', !r.success && /breach_coms4/.test(r.skipped[0].reason) && fs.existsSync(path.join(VAULT_DRV, 'master.bin')) && !fs.existsSync(path.join(B, 'master.bin')));
    r = await transfer({ sources: [path.join(VAULT_DRV, 'master.bin')], toDir: B, mode: 'copy' }, slots);
    ok('…copy off it is fine', r.success && fs.existsSync(path.join(VAULT_DRV, 'master.bin')) && fs.existsSync(path.join(B, 'master.bin')));
    let rr = await rename({ path: path.join(VAULT_DRV, 'master.bin'), newName: 'm2.bin' }, slots);
    ok('never RENAME on a drive LABELLED breach_coms4', !rr.success && /breach_coms4/.test(rr.error) && fs.existsSync(path.join(VAULT_DRV, 'master.bin')));
    fs.rmSync(path.join(B, 'master.bin'));
    r = await transfer({ sources: [path.join(VAULT_DRV, 'master.bin')], toDir: B, mode: 'move' },
        slots, { labelsUnder: async () => [' BREACH_COMS4 '] });
    ok('label match ignores case/spaces', !r.success && /breach_coms4/.test(r.skipped[0].reason));
    w(path.join(A, 'unk.txt'), 'u');
    r = await transfer({ sources: [path.join(A, 'unk.txt')], toDir: B, mode: 'move' }, slots, { labelsUnder: async () => null });
    ok('label unreadable: move refused (fails closed)', !r.success && /label/.test(r.skipped[0].reason) && fs.existsSync(path.join(A, 'unk.txt')));
    r = await transfer({ sources: [path.join(A, 'unk.txt')], toDir: B, mode: 'move' }, slots, { labelsUnder: async () => { throw new Error('ps died'); } });
    ok('label lookup throws: move refused', !r.success && /label/.test(r.skipped[0].reason) && fs.existsSync(path.join(A, 'unk.txt')));
    w(path.join(VAULT_DRV, 'in.txt'), 'x');
    r = await transfer({ sources: [path.join(A, 'unk.txt')], toDir: VAULT_DRV, mode: 'move' }, slots);
    ok('moving INTO breach_coms4 is allowed (nothing leaves the vault)', r.success && fs.existsSync(path.join(VAULT_DRV, 'unk.txt')));

    r = await transfer({ sources: [path.join(B, 'a.txt')], toDir: B, mode: 'move' }, slots);
    ok('same folder = no-op, told why', !r.success && /already in that folder/.test(r.skipped[0].reason));

    w(path.join(OUT, 'trick.txt'), 't');
    r = await transfer({ sources: [path.join(A, '..', 'outside', 'trick.txt')], toDir: path.join(B, '..', 'A'), mode: 'move' }, slots);
    ok('../ tricks resolve before the checks (outside = copy only)', r.success && r.mode === 'copy' && fs.existsSync(path.join(OUT, 'trick.txt')));

    // Cross-drive move: rename fails with EXDEV -> copy, verify, then remove.
    const fsp = fs.promises;
    const realRename = fsp.rename, realCp = fsp.cp, realRead = fs.readFileSync, realStream = fs.createReadStream;
    fsp.rename = async () => { const e = new Error('cross-device'); e.code = 'EXDEV'; throw e; };
    fs.mkdirSync(path.join(A, 'xdev', 'in'), { recursive: true }); w(path.join(A, 'xdev', 'in', 'f.bin'), Buffer.alloc(70000, 7));
    r = await transfer({ sources: [path.join(A, 'xdev')], toDir: B, mode: 'move' }, slots);
    ok('cross-drive move: copied, verified, original removed', r.success && !fs.existsSync(path.join(A, 'xdev')) && fs.statSync(path.join(B, 'xdev', 'in', 'f.bin')).size === 70000);

    // DASH-F27: > 2 GiB. The verify must stream: readFileSync throws the real Node error
    // for a file over 2 GiB, so any whole-file read fails the move. Sizes are faked (no disk filled).
    fs.mkdirSync(path.join(A, 'big'), { recursive: true }); w(path.join(A, 'big', 'huge.iso'), Buffer.alloc(3 << 20, 1));
    let streamed = 0;
    fs.readFileSync = (p, ...a) => {
        if (String(p).includes('huge.iso')) { const e = new RangeError('File size (3221225472) is greater than 2 GiB'); e.code = 'ERR_FS_FILE_TOO_LARGE'; throw e; }
        return realRead(p, ...a);
    };
    fs.createReadStream = (p, ...a) => { if (String(p).includes('huge.iso')) streamed++; return realStream(p, ...a); };
    let ticks = 0; const timer = setInterval(() => ticks++, 0);
    r = await transfer({ sources: [path.join(A, 'big')], toDir: B, mode: 'move' }, slots);
    clearInterval(timer);
    ok('> 2 GiB-style file: hashed by stream, move completes', r.success && streamed === 2 && !fs.existsSync(path.join(A, 'big')) && fs.statSync(path.join(B, 'big', 'huge.iso')).size === 3 << 20);
    ok('…and the event loop kept running during the verify', ticks > 0);
    fs.readFileSync = realRead; fs.createReadStream = realStream;
    const h = await st.sha256(path.join(B, 'big', 'huge.iso'));
    ok('streamed SHA-256 matches a one-shot hash', h === require('crypto').createHash('sha256').update(realRead(path.join(B, 'big', 'huge.iso'))).digest('hex'));

    // …and when the copy doesn't verify, the original stays and the copy goes
    fsp.cp = async (s, d, o) => { await realCp(s, d, o); fs.writeFileSync(path.join(d, 'in', 'f.bin'), 'corrupted'); };
    fs.mkdirSync(path.join(A, 'xdev2', 'in'), { recursive: true }); w(path.join(A, 'xdev2', 'in', 'f.bin'), 'good');
    r = await transfer({ sources: [path.join(A, 'xdev2')], toDir: B, mode: 'move' }, slots);
    ok('bad copy: original kept, bad copy removed', !r.success && /did not verify/.test(r.skipped[0].reason) && fs.readFileSync(path.join(A, 'xdev2', 'in', 'f.bin'), 'utf8') === 'good' && !fs.existsSync(path.join(B, 'xdev2')));

    // …verify THROWS (a read error mid-hash): copy removed, original kept
    fsp.cp = realCp;
    fs.createReadStream = (p, ...a) => {
        if (String(p).startsWith(B)) { const s = realStream(p, ...a); process.nextTick(() => s.destroy(Object.assign(new Error('EIO: read error'), { code: 'EIO' }))); return s; }
        return realStream(p, ...a);
    };
    r = await transfer({ sources: [path.join(A, 'xdev2')], toDir: B, mode: 'move' }, slots);
    fs.createReadStream = realStream;
    ok('verify throws: copy removed, original kept', !r.success && /original left in place/.test(r.skipped[0].reason) && fs.existsSync(path.join(A, 'xdev2', 'in', 'f.bin')) && !fs.existsSync(path.join(B, 'xdev2')));

    // …copy itself throws halfway: the partial copy goes, original kept
    fsp.cp = async (s, d) => { fs.mkdirSync(path.join(d, 'in'), { recursive: true }); fs.writeFileSync(path.join(d, 'in', 'f.bin'), 'go'); throw Object.assign(new Error('ENOSPC: no space left'), { code: 'ENOSPC' }); };
    r = await transfer({ sources: [path.join(A, 'xdev2')], toDir: B, mode: 'move' }, slots);
    ok('copy throws halfway: partial removed, original kept', !r.success && /ENOSPC/.test(r.skipped[0].reason) && fs.existsSync(path.join(A, 'xdev2', 'in', 'f.bin')) && !fs.existsSync(path.join(B, 'xdev2')));
    fsp.rename = realRename; fsp.cp = realCp;

    w(path.join(A, 'sub', 'new.txt'), 'n');
    r = await transfer({ sources: [path.join(A, 'sub', 'new.txt'), path.join(A, 'proj')], toDir: B, mode: 'move' }, slots);
    ok('several at once: one moves, the clash is reported', r.done.length === 1 && r.skipped.length === 1);

    // Rename
    const R = fs.mkdtempSync(path.join(os.tmpdir(), 'ren-')); fs.writeFileSync(path.join(R, 'old.txt'), 'x'); fs.writeFileSync(path.join(R, 'taken.txt'), 'keep');
    rr = await rename({ path: path.join(R, 'old.txt'), newName: 'new.txt' }, [R]);
    ok('rename works', rr.success && fs.existsSync(path.join(R, 'new.txt')) && !fs.existsSync(path.join(R, 'old.txt')));
    rr = await rename({ path: path.join(R, 'new.txt'), newName: 'taken.txt' }, [R]);
    ok('rename never overwrites', !rr.success && fs.readFileSync(path.join(R, 'taken.txt'), 'utf8') === 'keep');
    rr = await rename({ path: path.join(R, 'new.txt'), newName: '../escape.txt' }, [R]);
    ok('rename refuses paths in the name', !rr.success && fs.existsSync(path.join(R, 'new.txt')));
    rr = await rename({ path: path.join(R, 'new.txt'), newName: 'x.txt' }, [path.join(T, 'nowhere')]);
    ok('rename only inside places/slots', !rr.success);
    fs.mkdirSync(path.join(R, 'breach_coms4')); fs.writeFileSync(path.join(R, 'breach_coms4', 'v.txt'), 'v');
    rr = await rename({ path: path.join(R, 'breach_coms4', 'v.txt'), newName: 'w.txt' }, [R]);
    ok('nothing renamed in breach_coms4', !rr.success && fs.existsSync(path.join(R, 'breach_coms4', 'v.txt')));
    fs.rmSync(R, { recursive: true, force: true });

    // The real label lookup on this machine (read-only: it only lists volume labels).
    const live = await defaultLabelsUnder(T);
    ok('real label lookup answers for the temp drive', Array.isArray(live) && live.length >= 1);
    ok('real label lookup: a temp folder is not breach_coms4', !live.some((l) => String(l).toLowerCase() === 'breach_coms4'));
    if (process.platform === 'win32') ok('real label lookup: UNC path = unknown (refused)', (await defaultLabelsUnder('\\\\nohost\\share\\x')) === null);
    console.log(`  (live label for ${T.slice(0, 3)} -> ${JSON.stringify(live)})`);

    // OS folders: never a destination, never moved (Linux rules here; Windows rules are the same shape)
    if (process.platform !== 'win32') {
        r = await transfer({ sources: [path.join(A, 'proj')], toDir: '/etc', mode: 'copy' }, ['/']);
        ok('never put anything into an OS folder', !r.success && /operating-system/.test(r.error));
        ok('OS folder detection', isSystem('/usr/lib') && isSystem('/etc') && !isSystem('/home/x') && !isSystem('/etcetera'));
    } else {
        ok('OS folder detection', isSystem('C:\\Windows\\System32') && isSystem('c:\\program files (x86)\\x') && !isSystem('C:\\Users\\x'));
    }

    fs.rmSync(T, { recursive: true, force: true });
    console.log(fail ? `${fail} FAILED, ${pass} passed` : `all ${pass} slot-transfer checks pass`);
    process.exit(fail ? 1 : 0);
})().catch((e) => { console.log('CRASH', e); process.exit(1); });
