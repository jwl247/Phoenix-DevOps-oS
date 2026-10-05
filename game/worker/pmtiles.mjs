// pmtiles.mjs — read tiles from a PMTiles v3 archive in R2 (range reads)
// Phoenix DevOps OS | jwl247 | GPL v3
//
// Sacrifice's maps are our own OpenStreetMap extract (game/map_extract.py),
// one PMTiles file in the sacrifice-maps bucket. Directories are cached per
// isolate and keyed by the object's etag, so a new map upload is picked up
// on the next request without a redeploy.
//
// Spec: https://github.com/protomaps/PMTiles/blob/main/spec/v3/spec.md

const HEADER_LEN = 127;

export function zxyToTileId(z, x, y) {
  if (z > 26 || x < 0 || y < 0 || x >= 2 ** z || y >= 2 ** z) throw new RangeError('tile out of range');
  let acc = (4 ** z - 1) / 3;                       // tiles in all lower zooms
  let d = 0;
  for (let s = 2 ** (z - 1); s >= 1; s /= 2) {
    const rx = (x & s) ? 1 : 0, ry = (y & s) ? 1 : 0;
    d += s * s * ((3 * rx) ^ ry);
    if (ry === 0) {
      if (rx === 1) { x = s - 1 - (x % s) + (x - (x % s)); y = s - 1 - (y % s) + (y - (y % s)); }
      [x, y] = [y, x];
    }
  }
  return acc + d;
}

function readVarint(buf, pos) {
  let result = 0, mult = 1, b;
  do {
    b = buf[pos.i++];
    result += (b & 0x7f) * mult;
    mult *= 128;
  } while (b & 0x80);
  return result;
}

async function decompress(bytes, kind) {
  if (kind === 1) return bytes;
  if (kind !== 2) throw new Error(`unsupported internal compression ${kind}`);
  const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'));
  return new Uint8Array(await new Response(stream).arrayBuffer());
}

export function parseHeader(b) {
  const v = new DataView(b.buffer, b.byteOffset, b.byteLength);
  const magic = new TextDecoder().decode(b.subarray(0, 7));
  if (magic !== 'PMTiles' || b[7] !== 3) throw new Error('not a PMTiles v3 archive');
  const u64 = (o) => Number(v.getBigUint64(o, true));
  return {
    rootOffset: u64(8), rootLength: u64(16),
    leafOffset: u64(40), dataOffset: u64(56),
    internalCompression: b[97], tileCompression: b[98], tileType: b[99],
    minZoom: b[100], maxZoom: b[101],
  };
}

export function parseDirectory(buf) {
  const pos = { i: 0 };
  const n = readVarint(buf, pos);
  const ids = new Array(n), runs = new Array(n), lens = new Array(n), offs = new Array(n);
  let last = 0;
  for (let k = 0; k < n; k++) { last += readVarint(buf, pos); ids[k] = last; }
  for (let k = 0; k < n; k++) runs[k] = readVarint(buf, pos);
  for (let k = 0; k < n; k++) lens[k] = readVarint(buf, pos);
  for (let k = 0; k < n; k++) {
    const v = readVarint(buf, pos);
    offs[k] = (v === 0 && k > 0) ? offs[k - 1] + lens[k - 1] : v - 1;
  }
  return { ids, runs, lens, offs };
}

function findEntry(dir, tileId) {
  let lo = 0, hi = dir.ids.length - 1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (dir.ids[mid] < tileId) lo = mid + 1;
    else if (dir.ids[mid] > tileId) hi = mid - 1;
    else return mid;
  }
  if (hi >= 0 && (dir.runs[hi] === 0 || tileId - dir.ids[hi] < dir.runs[hi])) return hi;
  return -1;
}

const cache = new Map();        // `${key}@${etag}` → { header, root, leaves: Map }

async function range(bucket, key, offset, length) {
  const obj = await bucket.get(key, { range: { offset, length } });
  if (!obj) return null;
  return { bytes: new Uint8Array(await obj.arrayBuffer()), etag: obj.etag };
}

async function archive(bucket, key) {
  const head = await bucket.head(key);
  if (!head) return null;
  const id = `${key}@${head.etag}`;
  let a = cache.get(id);
  if (a) return a;
  const first = await range(bucket, key, 0, 16384);
  const header = parseHeader(first.bytes);
  const rootBytes = header.rootOffset + header.rootLength <= first.bytes.length
    ? first.bytes.subarray(header.rootOffset, header.rootOffset + header.rootLength)
    : (await range(bucket, key, header.rootOffset, header.rootLength)).bytes;
  a = { header, root: parseDirectory(await decompress(rootBytes, header.internalCompression)), leaves: new Map() };
  for (const k of cache.keys()) if (k.startsWith(`${key}@`)) cache.delete(k);   // old upload
  cache.set(id, a);
  return a;
}

/** Tile bytes (still tile-compressed) or null. Also returns the header for content headers. */
export async function getTile(bucket, key, z, x, y) {
  const a = await archive(bucket, key);
  if (!a) return { header: null, bytes: null };
  if (z < a.header.minZoom || z > a.header.maxZoom) return { header: a.header, bytes: null };
  const tileId = zxyToTileId(z, x, y);
  let dir = a.root;
  for (let depth = 0; depth < 4; depth++) {
    const i = findEntry(dir, tileId);
    if (i < 0) return { header: a.header, bytes: null };
    if (dir.runs[i] > 0) {
      const r = await range(bucket, key, a.header.dataOffset + dir.offs[i], dir.lens[i]);
      return { header: a.header, bytes: r ? r.bytes : null };
    }
    const lk = `${dir.offs[i]}:${dir.lens[i]}`;
    let leaf = a.leaves.get(lk);
    if (!leaf) {
      const r = await range(bucket, key, a.header.leafOffset + dir.offs[i], dir.lens[i]);
      leaf = parseDirectory(await decompress(r.bytes, a.header.internalCompression));
      if (a.leaves.size > 256) a.leaves.clear();
      a.leaves.set(lk, leaf);
    }
    dir = leaf;
  }
  throw new Error('PMTiles directory nesting too deep');
}
