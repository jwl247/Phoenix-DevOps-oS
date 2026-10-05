#!/usr/bin/env python3
"""
pmtiles.py — PMTiles v3 read / write / extract, no dependencies
Sacrifice | Phoenix DevOps OS | jwl247 | GPL v3

Sacrifice's maps are self-hosted OpenStreetMap data (JW, 2026-10-05: no map
vendor). OSM vector tiles come packed as one PMTiles file. This module:

  - reads PMTiles from a local file or over HTTP range requests
  - extracts theater regions (bounding boxes, zoom range) from any PMTiles
    source — e.g. the Protomaps daily planet build — without downloading the
    whole planet: only the directories and tiles inside the boxes are fetched
  - writes a clustered PMTiles v3 file (deduplicated, run-length encoded,
    leaf directories when the root would not fit)

The result goes into the clone pool through Frank's import method and the
sacrifice-worker serves tiles from it out of our own R2.

Spec: https://github.com/protomaps/PMTiles/blob/main/spec/v3/spec.md
Data: © OpenStreetMap contributors, ODbL.
"""

from __future__ import annotations

import gzip
import hashlib
import http.client
import io
import json
import math
import struct
import threading
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional

HEADER_LEN = 127
ROOT_MAX = 16384 - HEADER_LEN          # header + root must fit the first 16 KiB
USER_AGENT = "phoenix-sacrifice/1.0"

COMPRESSION = {1: "none", 2: "gzip", 3: "brotli", 4: "zstd"}
TILE_TYPE = {1: "mvt", 2: "png", 3: "jpeg", 4: "webp", 5: "avif"}


# ---------------------------------------------------------------------------
# Tile ids (Hilbert curve, per spec)
# ---------------------------------------------------------------------------

def zxy_to_tileid(z: int, x: int, y: int) -> int:
    if z > 31 or x >= (1 << z) or y >= (1 << z) or x < 0 or y < 0:
        raise ValueError(f"Tile out of range: {z}/{x}/{y}")
    acc = ((1 << (2 * z)) - 1) // 3
    d = 0
    s = 1 << (z - 1) if z else 0
    while s > 0:
        rx = 1 if x & s else 0
        ry = 1 if y & s else 0
        d += s * s * ((3 * rx) ^ ry)
        if ry == 0:
            if rx == 1:
                x = s - 1 - (x & (s - 1)) | (x & ~(s - 1))
                y = s - 1 - (y & (s - 1)) | (y & ~(s - 1))
            x, y = y, x
        s >>= 1
    return acc + d


def tileid_to_zxy(tile_id: int) -> tuple[int, int, int]:
    acc, z = 0, 0
    while True:
        n = 1 << (2 * z)
        if tile_id < acc + n:
            break
        acc += n
        z += 1
    d = tile_id - acc
    x = y = 0
    s = 1
    while s < (1 << z):
        rx = 1 & (d // 2)
        ry = 1 & (d ^ rx)
        if ry == 0:
            if rx == 1:
                x, y = s - 1 - x, s - 1 - y
            x, y = y, x
        x += s * rx
        y += s * ry
        d //= 4
        s *= 2
    return z, x, y


def lonlat_to_tile(lon: float, lat: float, z: int) -> tuple[int, int]:
    lat = max(-85.05112878, min(85.05112878, lat))
    n = 1 << z
    x = int((lon + 180.0) / 360.0 * n)
    s = math.sin(math.radians(lat))
    y = int((0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)) * n)
    return min(max(x, 0), n - 1), min(max(y, 0), n - 1)


def tiles_in_bbox(bbox: tuple[float, float, float, float], z: int) -> Iterable[tuple[int, int]]:
    minlon, minlat, maxlon, maxlat = bbox
    x0, y0 = lonlat_to_tile(minlon, maxlat, z)
    x1, y1 = lonlat_to_tile(maxlon, minlat, z)
    for x in range(x0, x1 + 1):
        for y in range(y0, y1 + 1):
            yield x, y


# ---------------------------------------------------------------------------
# Varints, header, directories
# ---------------------------------------------------------------------------

def _read_varint(buf: bytes, pos: int) -> tuple[int, int]:
    result = shift = 0
    while True:
        b = buf[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if not b & 0x80:
            return result, pos
        shift += 7


def _write_varint(out: bytearray, v: int) -> None:
    while True:
        b = v & 0x7F
        v >>= 7
        if v:
            out.append(b | 0x80)
        else:
            out.append(b)
            return


@dataclass
class Entry:
    tile_id:    int
    offset:     int
    length:     int
    run_length: int      # 0 = pointer to a leaf directory


HEADER_FMT = "<7sB QQQQQQQQ QQQ BBBB BB iiii B ii"


@dataclass
class Header:
    root_offset: int
    root_length: int
    metadata_offset: int
    metadata_length: int
    leaf_offset: int
    leaf_length: int
    data_offset: int
    data_length: int
    addressed_tiles: int
    tile_entries: int
    tile_contents: int
    clustered: bool
    internal_compression: int
    tile_compression: int
    tile_type: int
    min_zoom: int
    max_zoom: int
    min_lon: float
    min_lat: float
    max_lon: float
    max_lat: float
    center_zoom: int
    center_lon: float
    center_lat: float

    @classmethod
    def parse(cls, b: bytes) -> "Header":
        f = struct.unpack(HEADER_FMT, b[:HEADER_LEN])
        if f[0] != b"PMTiles" or f[1] != 3:
            raise ValueError("Not a PMTiles v3 archive")
        return cls(*f[2:13], bool(f[13]), *f[14:19],
                   f[19] / 1e7, f[20] / 1e7, f[21] / 1e7, f[22] / 1e7, f[23], f[24] / 1e7, f[25] / 1e7)

    def pack(self) -> bytes:
        e7 = lambda v: int(round(v * 1e7))
        return struct.pack(HEADER_FMT, b"PMTiles", 3,
                           self.root_offset, self.root_length, self.metadata_offset, self.metadata_length,
                           self.leaf_offset, self.leaf_length, self.data_offset, self.data_length,
                           self.addressed_tiles, self.tile_entries, self.tile_contents,
                           int(self.clustered), self.internal_compression, self.tile_compression,
                           self.tile_type, self.min_zoom, self.max_zoom,
                           e7(self.min_lon), e7(self.min_lat), e7(self.max_lon), e7(self.max_lat),
                           self.center_zoom, e7(self.center_lon), e7(self.center_lat))


def _decompress(data: bytes, kind: int) -> bytes:
    if kind == 1:
        return data
    if kind == 2:
        return gzip.decompress(data)
    raise ValueError(f"Unsupported internal compression: {COMPRESSION.get(kind, kind)}")


def _compress(data: bytes, kind: int) -> bytes:
    if kind == 1:
        return data
    if kind == 2:
        return gzip.compress(data, compresslevel=9, mtime=0)
    raise ValueError(f"Unsupported compression: {kind}")


def deserialize_directory(buf: bytes) -> list[Entry]:
    n, pos = _read_varint(buf, 0)
    ids, runs, lens, offs = [], [], [], []
    last = 0
    for _ in range(n):
        v, pos = _read_varint(buf, pos)
        last += v
        ids.append(last)
    for _ in range(n):
        v, pos = _read_varint(buf, pos)
        runs.append(v)
    for _ in range(n):
        v, pos = _read_varint(buf, pos)
        lens.append(v)
    for i in range(n):
        v, pos = _read_varint(buf, pos)
        offs.append(offs[i - 1] + lens[i - 1] if (v == 0 and i > 0) else v - 1)
    return [Entry(ids[i], offs[i], lens[i], runs[i]) for i in range(n)]


def serialize_directory(entries: list[Entry]) -> bytes:
    out = bytearray()
    _write_varint(out, len(entries))
    last = 0
    for e in entries:
        _write_varint(out, e.tile_id - last)
        last = e.tile_id
    for e in entries:
        _write_varint(out, e.run_length)
    for e in entries:
        _write_varint(out, e.length)
    for i, e in enumerate(entries):
        if i > 0 and e.offset == entries[i - 1].offset + entries[i - 1].length:
            _write_varint(out, 0)
        else:
            _write_varint(out, e.offset + 1)
    return bytes(out)


def find_entry(entries: list[Entry], tile_id: int) -> Optional[Entry]:
    lo, hi = 0, len(entries) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        c = entries[mid].tile_id
        if c < tile_id:
            lo = mid + 1
        elif c > tile_id:
            hi = mid - 1
        else:
            return entries[mid]
    if hi >= 0:
        e = entries[hi]
        if e.run_length == 0 or tile_id - e.tile_id < e.run_length:
            return e
    return None


# ---------------------------------------------------------------------------
# Sources: local file or HTTP range requests
# ---------------------------------------------------------------------------

class FileSource:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.Lock()
        self._f = open(self.path, "rb")

    def read(self, offset: int, length: int) -> bytes:
        with self._lock:
            self._f.seek(offset)
            return self._f.read(length)

    def close(self) -> None:
        self._f.close()


class HttpSource:
    """Range reads with one kept-alive connection per thread."""

    def __init__(self, url: str, timeout: int = 60):
        u = urllib.parse.urlsplit(url)
        if u.scheme != "https":
            raise ValueError("PMTiles over HTTP must use https")
        self.host, self.path, self.timeout = u.netloc, u.path + (f"?{u.query}" if u.query else ""), timeout
        self._local = threading.local()
        self.requests = 0
        self.bytes = 0

    def _conn(self) -> http.client.HTTPSConnection:
        c = getattr(self._local, "conn", None)
        if c is None:
            c = self._local.conn = http.client.HTTPSConnection(self.host, timeout=self.timeout)
        return c

    def read(self, offset: int, length: int) -> bytes:
        for attempt in range(3):
            try:
                c = self._conn()
                c.request("GET", self.path, headers={"Range": f"bytes={offset}-{offset + length - 1}",
                                                     "User-Agent": USER_AGENT})
                r = c.getresponse()
                data = r.read()
                if r.status != 206 or len(data) != length:
                    raise IOError(f"range read {offset}+{length}: HTTP {r.status}, {len(data)} bytes")
                self.requests += 1
                self.bytes += length
                return data
            except (http.client.HTTPException, OSError):
                self._local.conn = None
                if attempt == 2:
                    raise
        raise IOError("unreachable")

    def close(self) -> None:
        pass


class Reader:
    def __init__(self, source):
        self.source = source
        first = source.read(0, 16384)
        self.header = Header.parse(first)
        h = self.header
        root = first[h.root_offset:h.root_offset + h.root_length] \
            if h.root_offset + h.root_length <= len(first) else source.read(h.root_offset, h.root_length)
        self.root = deserialize_directory(_decompress(root, h.internal_compression))
        self._leaves: dict[tuple[int, int], list[Entry]] = {}
        self._lock = threading.Lock()

    def metadata(self) -> dict:
        h = self.header
        raw = self.source.read(h.metadata_offset, h.metadata_length) if h.metadata_length else b"{}"
        return json.loads(_decompress(raw, h.internal_compression))

    def _leaf(self, offset: int, length: int) -> list[Entry]:
        key = (offset, length)
        with self._lock:
            if key in self._leaves:
                return self._leaves[key]
        h = self.header
        entries = deserialize_directory(_decompress(
            self.source.read(h.leaf_offset + offset, length), h.internal_compression))
        with self._lock:
            self._leaves[key] = entries
        return entries

    def locate(self, tile_id: int) -> Optional[tuple[int, int]]:
        """(absolute offset, length) of a tile's bytes, or None if the archive has no such tile."""
        entries = self.root
        for _ in range(4):                         # spec: at most 3 levels deep
            e = find_entry(entries, tile_id)
            if e is None:
                return None
            if e.run_length > 0:
                return self.header.data_offset + e.offset, e.length
            entries = self._leaf(e.offset, e.length)
        raise ValueError("Directory nesting too deep")

    def tile(self, z: int, x: int, y: int) -> Optional[bytes]:
        loc = self.locate(zxy_to_tileid(z, x, y))
        return self.source.read(*loc) if loc else None


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------

def _build_directories(entries: list[Entry], kind: int, root_max: int = ROOT_MAX) -> tuple[bytes, bytes]:
    """Root (compressed) and leaf section. Leaves only when the root won't fit."""
    root = _compress(serialize_directory(entries), kind)
    if len(root) <= root_max:
        return root, b""
    leaf_size = max(1, min(4096, len(entries) // 8))
    while True:
        leaves, pointers, off = bytearray(), [], 0
        for i in range(0, len(entries), leaf_size):
            chunk = entries[i:i + leaf_size]
            blob = _compress(serialize_directory(chunk), kind)
            pointers.append(Entry(chunk[0].tile_id, off, len(blob), 0))
            leaves += blob
            off += len(blob)
        root = _compress(serialize_directory(pointers), kind)
        if len(root) <= root_max:
            return root, bytes(leaves)
        if leaf_size >= len(entries):
            raise ValueError(f"directory cannot fit a {root_max}-byte root")
        leaf_size *= 2


def write_pmtiles(
    out:       Path,
    tiles:     dict[int, bytes],           # tile_id → tile bytes (already tile-compressed)
    template:  Header,                     # compression / type copied from the source
    metadata:  dict,
    bounds:    tuple[float, float, float, float],
    min_zoom:  int,
    max_zoom:  int,
    root_max:  int = ROOT_MAX,               # tests force leaf directories with a small value
) -> Path:
    kind = template.internal_compression
    entries: list[Entry] = []
    data = bytearray()
    seen: dict[bytes, tuple[int, int]] = {}
    for tid in sorted(tiles):
        blob = tiles[tid]
        digest = hashlib.sha256(blob).digest()
        if digest in seen:
            off, ln = seen[digest]
        else:
            off, ln = len(data), len(blob)
            data += blob
            seen[digest] = (off, ln)
        last = entries[-1] if entries else None
        if last and last.offset == off and last.tile_id + last.run_length == tid:
            last.run_length += 1                    # identical neighbours (open sea, forest)
        else:
            entries.append(Entry(tid, off, ln, 1))

    root, leaves = _build_directories(entries, kind, root_max)
    meta = _compress(json.dumps(metadata, separators=(",", ":")).encode(), kind)
    root_off = HEADER_LEN
    meta_off = root_off + len(root)
    leaf_off = meta_off + len(meta)
    data_off = leaf_off + len(leaves)
    minlon, minlat, maxlon, maxlat = bounds
    h = Header(root_off, len(root), meta_off, len(meta), leaf_off, len(leaves), data_off, len(data),
               len(tiles), len(entries), len(seen), True, kind, template.tile_compression,
               template.tile_type, min_zoom, max_zoom, minlon, minlat, maxlon, maxlat,
               min_zoom + (max_zoom - min_zoom) // 2, (minlon + maxlon) / 2, (minlat + maxlat) / 2)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    with open(tmp, "wb") as f:
        f.write(h.pack())
        f.write(root)
        f.write(meta)
        f.write(leaves)
        f.write(data)
    tmp.replace(out)
    return out


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------

def extract(
    reader:    Reader,
    regions:   list[tuple[float, float, float, float]],   # (minlon, minlat, maxlon, maxlat)
    out:       Path,
    min_zoom:  int = 0,
    max_zoom:  int = 14,
    workers:   int = 16,
    progress:  Optional[Callable[[int, int], None]] = None,
) -> dict:
    """Cut the regions out of a PMTiles source into a new archive. Returns stats."""
    max_zoom = min(max_zoom, reader.header.max_zoom)
    ids: set[int] = set()
    for bbox in regions:
        for z in range(min_zoom, max_zoom + 1):
            for x, y in tiles_in_bbox(bbox, z):
                ids.add(zxy_to_tileid(z, x, y))
    ordered = sorted(ids)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        locs = list(pool.map(reader.locate, ordered))
    wanted = [(tid, loc) for tid, loc in zip(ordered, locs) if loc]

    # Coalesce nearby byte ranges into one request each — far fewer round trips.
    spans: list[list] = []
    for tid, (off, ln) in sorted(wanted, key=lambda t: t[1][0]):
        if spans and off - (spans[-1][0] + spans[-1][1]) <= 32_768 and spans[-1][1] < 4_194_304:
            spans[-1][1] = max(spans[-1][1], off + ln - spans[-1][0])
            spans[-1][2].append((tid, off, ln))
        else:
            spans.append([off, ln, [(tid, off, ln)]])

    tiles: dict[int, bytes] = {}
    done = [0]
    lock = threading.Lock()

    def fetch(span):
        start, length, members = span
        blob = reader.source.read(start, length)
        got = {tid: blob[off - start:off - start + ln] for tid, off, ln in members}
        with lock:
            tiles.update(got)
            done[0] += 1
            if progress:
                progress(done[0], len(spans))

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(fetch, spans))

    lons = [b[0] for b in regions] + [b[2] for b in regions]
    lats = [b[1] for b in regions] + [b[3] for b in regions]
    meta = reader.metadata()
    meta = {**meta, "sacrifice": {"regions": [list(r) for r in regions], "source_version": meta.get("version")}}
    write_pmtiles(out, tiles, reader.header, meta, (min(lons), min(lats), max(lons), max(lats)),
                  min_zoom, max_zoom)
    return {"tiles": len(tiles), "requests": len(spans), "bytes": Path(out).stat().st_size}
