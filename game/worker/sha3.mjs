// sha3.mjs — SHA3-512 (FIPS 202) for Workers.
// Phoenix DevOps OS | jwl247 | GPL v3
//
// Phoenix custody is SHA3-512 (intake.sh, D1 clonepool.hash_sha3), but the
// Workers runtime's Web Crypto has no SHA3 (packages-worker's own comments say
// so). Callers must check submitted bytes against custody themselves, so this
// is a plain Keccak-f[1600] with the SHA3 domain byte (0x06). BigInt-free:
// 64-bit lanes are held as [lo, hi] 32-bit halves. Tested against Python's
// hashlib.sha3_512 (test/sha3.test.mjs).

const RC = [
  [0x00000001, 0x00000000], [0x00008082, 0x00000000], [0x0000808a, 0x80000000], [0x80008000, 0x80000000],
  [0x0000808b, 0x00000000], [0x80000001, 0x00000000], [0x80008081, 0x80000000], [0x00008009, 0x80000000],
  [0x0000008a, 0x00000000], [0x00000088, 0x00000000], [0x80008009, 0x00000000], [0x8000000a, 0x00000000],
  [0x8000808b, 0x00000000], [0x0000008b, 0x80000000], [0x00008089, 0x80000000], [0x00008003, 0x80000000],
  [0x00008002, 0x80000000], [0x00000080, 0x80000000], [0x0000800a, 0x00000000], [0x8000000a, 0x80000000],
  [0x80008081, 0x80000000], [0x00008080, 0x80000000], [0x80000001, 0x00000000], [0x80008008, 0x80000000],
];
// rotation offsets r[x + 5y]
const ROT = [0, 1, 62, 28, 27, 36, 44, 6, 55, 20, 3, 10, 43, 25, 39, 41, 45, 15, 21, 8, 18, 2, 61, 56, 14];

function keccakF(lo, hi) {
  const Clo = new Uint32Array(5), Chi = new Uint32Array(5);
  const Blo = new Uint32Array(25), Bhi = new Uint32Array(25);
  for (let round = 0; round < 24; round++) {
    // θ
    for (let x = 0; x < 5; x++) {
      Clo[x] = lo[x] ^ lo[x + 5] ^ lo[x + 10] ^ lo[x + 15] ^ lo[x + 20];
      Chi[x] = hi[x] ^ hi[x + 5] ^ hi[x + 10] ^ hi[x + 15] ^ hi[x + 20];
    }
    for (let x = 0; x < 5; x++) {
      const x1 = (x + 1) % 5, x4 = (x + 4) % 5;
      // D = C[x-1] ^ rot(C[x+1], 1)
      const dlo = Clo[x4] ^ ((Clo[x1] << 1) | (Chi[x1] >>> 31));
      const dhi = Chi[x4] ^ ((Chi[x1] << 1) | (Clo[x1] >>> 31));
      for (let y = 0; y < 25; y += 5) { lo[y + x] ^= dlo; hi[y + x] ^= dhi; }
    }
    // ρ and π
    for (let x = 0; x < 5; x++) {
      for (let y = 0; y < 5; y++) {
        const i = x + 5 * y, r = ROT[i];
        let l = lo[i], h = hi[i], nl, nh;
        if (r === 0) { nl = l; nh = h; }
        else if (r < 32) { nl = (l << r) | (h >>> (32 - r)); nh = (h << r) | (l >>> (32 - r)); }
        else if (r === 32) { nl = h; nh = l; }
        else { const s = r - 32; nl = (h << s) | (l >>> (32 - s)); nh = (l << s) | (h >>> (32 - s)); }
        const j = y + 5 * ((2 * x + 3 * y) % 5);
        Blo[j] = nl; Bhi[j] = nh;
      }
    }
    // χ
    for (let y = 0; y < 25; y += 5) {
      for (let x = 0; x < 5; x++) {
        lo[y + x] = Blo[y + x] ^ (~Blo[y + ((x + 1) % 5)] & Blo[y + ((x + 2) % 5)]);
        hi[y + x] = Bhi[y + x] ^ (~Bhi[y + ((x + 1) % 5)] & Bhi[y + ((x + 2) % 5)]);
      }
    }
    // ι
    lo[0] ^= RC[round][0]; hi[0] ^= RC[round][1];
  }
}

/** SHA3-512 of a Uint8Array / ArrayBuffer / string (UTF-8). Returns lowercase hex. */
export function sha3_512(input) {
  const data = typeof input === 'string' ? new TextEncoder().encode(input)
    : input instanceof Uint8Array ? input : new Uint8Array(input);
  const rate = 72;                                   // 1600 - 2*512 bits = 576 bits
  const lo = new Uint32Array(25), hi = new Uint32Array(25);
  const absorb = (block, off) => {
    for (let i = 0; i < rate / 8; i++) {
      const p = off + i * 8;
      lo[i] ^= block[p] | (block[p + 1] << 8) | (block[p + 2] << 16) | (block[p + 3] << 24);
      hi[i] ^= block[p + 4] | (block[p + 5] << 8) | (block[p + 6] << 16) | (block[p + 7] << 24);
    }
    keccakF(lo, hi);
  };
  let off = 0;
  for (; off + rate <= data.length; off += rate) absorb(data, off);
  const last = new Uint8Array(rate);
  last.set(data.subarray(off));
  last[data.length - off] ^= 0x06;                   // SHA3 domain separation
  last[rate - 1] ^= 0x80;
  absorb(last, 0);
  let out = '';
  for (let i = 0; i < 8; i++) {                      // 64 bytes = 8 lanes
    for (const w of [lo[i], hi[i]]) {
      for (let b = 0; b < 4; b++) out += ((w >>> (8 * b)) & 0xff).toString(16).padStart(2, '0');
    }
  }
  return out;
}
