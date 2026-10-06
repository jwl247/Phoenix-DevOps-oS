// SHA3-512 against Python hashlib vectors (generated at test time) + FIPS empty-string vector.
import { sha3_512 } from '../worker/sha3.mjs';
import { execFileSync } from 'node:child_process';
import { randomBytes } from 'node:crypto';
let fail = 0;
const check = (label, got, want) => { if (got !== want) { fail++; console.log('FAIL', label, got.slice(0, 16), want.slice(0, 16)); } };
check('empty (FIPS 202)', sha3_512(''), 'a69f73cca23a9ac5c8b567dc185a756e97c982164fe25859e0d1dcc1475c80a615b2123af1f5f94c11e3e9402c3ac558f500199d95b6d3e301758586281dcd26');
check('abc (FIPS 202)', sha3_512('abc'), 'b751850b1a57168a5693cd924b6b096e08f621827444f70d884f5d0240d2712e10e116e9192af3c91a7ec57647e3934057340b4cf408d5a56592f8274eec53f0');
const sizes = [1, 71, 72, 73, 143, 144, 145, 1000, 65536, 300001];
for (const n of sizes) {
  const buf = randomBytes(n);
  const want = execFileSync('python3', ['-c', 'import hashlib,sys; print(hashlib.sha3_512(sys.stdin.buffer.read()).hexdigest())'], { input: buf }).toString().trim();
  check(`random ${n} B`, sha3_512(buf), want);
}
const t = Date.now(); sha3_512(randomBytes(4 * 1024 * 1024)); const ms = Date.now() - t;
console.log(fail ? `${fail} FAILED` : `all ${sizes.length + 2} vectors match`, `· 4 MB in ${ms} ms`);
process.exit(fail ? 1 : 0);
