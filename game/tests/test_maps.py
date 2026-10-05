#!/usr/bin/env python3
"""
test_maps.py — Sacrifice's own maps: PMTiles, MVT, Frank's renderer
Phoenix DevOps OS | jwl247 | GPL v3

No network: tiles are built here with a tiny MVT encoder, packed with our
PMTiles writer, read back, rendered. The live planet path was exercised by
hand on 2026-10-05 (Ardennes: 32 MB read of 138 GB, tiles byte-identical).

    python game/tests/test_maps.py
"""

from __future__ import annotations

import gzip
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from game import pmtiles as pm, mvt, theater_map as tm
from game.territory import AO


# ---------------------------------------------------------------------------
# A minimal MVT encoder (test-only) — enough to build real tiles
# ---------------------------------------------------------------------------

def _v(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        out.append(b | 0x80 if n else b)
        if not n:
            return bytes(out)


def _f(num: int, wt: int, payload) -> bytes:
    key = _v((num << 3) | wt)
    if wt == 0:
        return key + _v(payload)
    return key + _v(len(payload)) + payload


def _zz(n: int) -> int:
    return (n << 1) ^ (n >> 31)


def _geom(gtype: int, rings) -> list[int]:
    cmds, cx, cy = [], 0, 0
    for ring in rings:
        pts = ring[:-1] if gtype == mvt.POLYGON and ring[0] == ring[-1] else ring
        x, y = pts[0]
        cmds += [(1 & 7) | (1 << 3), _zz(x - cx), _zz(y - cy)]
        cx, cy = x, y
        if len(pts) > 1:
            cmds.append((2 & 7) | ((len(pts) - 1) << 3))
            for x, y in pts[1:]:
                cmds += [_zz(x - cx), _zz(y - cy)]
                cx, cy = x, y
        if gtype == mvt.POLYGON:
            cmds.append((7 & 7) | (1 << 3))
    return cmds


def encode_tile(layers: dict) -> bytes:
    """layers: {name: [(gtype, props, rings), ...]} → gzip MVT bytes."""
    out = b""
    for name, feats in layers.items():
        keys, vals, body = [], [], b""
        for gtype, props, rings in feats:
            tags = []
            for k, val in props.items():
                if k not in keys:
                    keys.append(k)
                if val not in vals:
                    vals.append(val)
                tags += [keys.index(k), vals.index(val)]
            packed = b"".join(_v(t) for t in tags)
            geom = b"".join(_v(c) for c in _geom(gtype, rings))
            body += _f(2, 2, _f(2, 2, packed) + _f(3, 0, gtype) + _f(4, 2, geom))
        lb = _f(15, 0, 2) + _f(1, 2, name.encode()) + body
        lb += b"".join(_f(3, 2, k.encode()) for k in keys)
        for val in vals:
            vb = _f(1, 2, val.encode()) if isinstance(val, str) else _f(4, 0, val)
            lb += _f(4, 2, vb)
        lb += _f(5, 0, 4096)
        out += _f(3, 2, lb)
    return gzip.compress(out, mtime=0)


LAND = [(0, 0), (4096, 0), (4096, 4096), (0, 4096), (0, 0)]
LAKE = [(1000, 1000), (3000, 1000), (3000, 3000), (1000, 3000), (1000, 1000)]


def sample_tile(name="Clervaux") -> bytes:
    return encode_tile({
        "landuse": [(mvt.POLYGON, {"kind": "forest"}, [LAND])],
        "water":   [(mvt.POLYGON, {"kind": "lake"}, [LAKE]),
                    (mvt.LINESTRING, {"kind": "river"}, [[(0, 2048), (4096, 2100)]])],
        "roads":   [(mvt.LINESTRING, {"kind": "major_road"}, [[(0, 500), (4096, 600)]])],
        "places":  [(mvt.POINT, {"kind": "locality", "name": name, "min_zoom": 6, "population_rank": 5},
                     [[(2048, 2048)]])],
    })


def build_archive(path: Path, bbox, zooms=range(0, 11), root_max: int = pm.ROOT_MAX, unique: bool = False) -> dict:
    tiles = {}
    for z in zooms:
        for x, y in pm.tiles_in_bbox(bbox, z):
            tiles[pm.zxy_to_tileid(z, x, y)] = sample_tile(f"T{z}-{x}-{y}" if unique else f"T{z}")
    tmpl = pm.Header(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, True, 2, 2, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    pm.write_pmtiles(path, tiles, tmpl, {"attribution": "© OpenStreetMap contributors", "vector_layers": []},
                     bbox, min(zooms), max(zooms), root_max=root_max)
    return tiles


# ---------------------------------------------------------------------------

class TestTileIds(unittest.TestCase):
    def test_spec_order_and_round_trip(self):
        self.assertEqual([pm.zxy_to_tileid(*k) for k in [(0, 0, 0), (1, 0, 0), (1, 0, 1), (1, 1, 1), (1, 1, 0)]],
                         [0, 1, 2, 3, 4])
        self.assertEqual(pm.zxy_to_tileid(2, 0, 0), 5)
        for k in [(3, 7, 0), (10, 523, 344), (15, 17000, 11000), (14, 8546, 5605)]:
            self.assertEqual(pm.tileid_to_zxy(pm.zxy_to_tileid(*k)), k)
        with self.assertRaises(ValueError):
            pm.zxy_to_tileid(2, 4, 0)

    def test_directory_round_trip_with_run_lengths(self):
        es = [pm.Entry(0, 0, 10, 1), pm.Entry(5, 10, 20, 3), pm.Entry(9, 0, 10, 1), pm.Entry(40, 30, 5, 0)]
        back = pm.deserialize_directory(pm.serialize_directory(es))
        self.assertEqual([(e.tile_id, e.offset, e.length, e.run_length) for e in back],
                         [(e.tile_id, e.offset, e.length, e.run_length) for e in es])
        self.assertEqual(pm.find_entry(back, 7).tile_id, 5)        # inside a run
        self.assertIsNone(pm.find_entry(back, 8))                  # past the run
        self.assertEqual(pm.find_entry(back, 99).tile_id, 40)      # leaf pointer covers the rest


class TestArchive(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="phoenix_maps_"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_write_read_dedupe(self):
        bbox = (5.9, 49.8, 6.3, 50.05)
        tiles = build_archive(self.tmp / "a.pmtiles", bbox)
        r = pm.Reader(pm.FileSource(self.tmp / "a.pmtiles"))
        h = r.header
        self.assertEqual((h.min_zoom, h.max_zoom, h.addressed_tiles), (0, 10, len(tiles)))
        self.assertEqual(h.tile_contents, 11)                     # one unique tile per zoom — deduped
        x, y = pm.lonlat_to_tile(6.0, 49.9, 10)
        self.assertEqual(r.tile(10, x, y), tiles[pm.zxy_to_tileid(10, x, y)])
        self.assertIsNone(r.tile(10, 0, 0))
        self.assertIn("OpenStreetMap", r.metadata()["attribution"])

    def test_leaf_directories_when_root_is_too_big(self):
        def blob(x, y):                     # distinct, irregular sizes — defeats compression
            return bytes([x % 251, y % 251]) * (1 + (x * 7919 + y * 104729) % 97)
        keep = [(x, y) for x in range(4000, 4300) for y in range(2600, 2900) if (x * 31 + y * 17) % 3]
        tiles = {pm.zxy_to_tileid(13, x, y): blob(x, y) for x, y in keep}   # ~60,000 entries
        tmpl = pm.Header(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, True, 2, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        pm.write_pmtiles(self.tmp / "big.pmtiles", tiles, tmpl, {}, (0, 0, 1, 1), 13, 13, root_max=512)
        r = pm.Reader(pm.FileSource(self.tmp / "big.pmtiles"))
        self.assertGreater(r.header.leaf_length, 0)
        self.assertLessEqual(r.header.root_length, 512)
        for x, y in [keep[0], keep[len(keep) // 2], keep[-1]]:
            self.assertEqual(r.tile(13, x, y), blob(x, y))

    def test_extract_from_a_bigger_archive(self):
        build_archive(self.tmp / "world.pmtiles", (5.0, 49.0, 7.0, 51.0))
        src = pm.Reader(pm.FileSource(self.tmp / "world.pmtiles"))
        stats = pm.extract(src, [(5.9, 49.8, 6.3, 50.05)], self.tmp / "theater.pmtiles", 0, 10)
        small = pm.Reader(pm.FileSource(self.tmp / "theater.pmtiles"))
        self.assertEqual(small.header.addressed_tiles, stats["tiles"])
        self.assertLess(stats["tiles"], src.header.addressed_tiles)
        x, y = pm.lonlat_to_tile(6.1, 49.9, 9)
        self.assertEqual(small.tile(9, x, y), src.tile(9, x, y))
        x, y = pm.lonlat_to_tile(5.1, 49.1, 9)
        self.assertIsNone(small.tile(9, x, y))                    # outside the theater

    def test_impossible_root_size_fails_cleanly(self):
        tmpl = pm.Header(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, True, 2, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        tiles = {i: bytes([i % 256]) * (i % 7 + 1) for i in range(50)}
        with self.assertRaises(ValueError):
            pm.write_pmtiles(self.tmp / "x.pmtiles", tiles, tmpl, {}, (0, 0, 1, 1), 0, 3, root_max=8)

    def test_padded_bbox(self):
        from game.map_extract import padded
        self.assertEqual(padded((0, 0, 4, 2), 0.25), (-1.0, -0.5, 5.0, 2.5))


class TestMvt(unittest.TestCase):
    def test_decode(self):
        layers = mvt.decode(sample_tile("Vianden"))
        self.assertEqual(sorted(layers), ["landuse", "places", "roads", "water"])
        lake = layers["water"].features[0]
        self.assertEqual((lake.type, lake.props["kind"]), (mvt.POLYGON, "lake"))
        self.assertEqual(lake.rings[0][0], lake.rings[0][-1])       # ClosePath
        self.assertEqual(lake.rings[0][:4], LAKE[:4])
        place = layers["places"].features[0]
        self.assertEqual((place.props["name"], place.props["min_zoom"], place.rings), ("Vianden", 6, [[(2048, 2048)]]))


class TestRender(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="phoenix_render_"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_snapshot_from_our_archive(self):
        from PIL import Image
        build_archive(self.tmp / "w.pmtiles", (5.6, 49.6, 6.6, 50.3), range(0, 11))
        src = tm.ArchiveSource(self.tmp / "w.pmtiles")
        ao = AO("AO-1", "Ardennes", "Hill 400", [[5.9, 49.8], [6.1, 49.8], [6.1, 50.0], [5.9, 50.0]])
        out, sha3 = tm.snapshot([ao], [], [], self.tmp / "s.png", src, 512, 384, title="test")
        with Image.open(out) as img:
            self.assertEqual(img.size, (512, 384))
            colors = {c for _, c in img.getcolors(1 << 20)}
        self.assertIn(tm.WATER, colors)                             # the lake was drawn
        self.assertEqual(len(sha3), 128)

    def test_payload_points_at_our_tiles(self):
        ao = AO("AO-1", "Ardennes", "Hill 400", [[5.9, 49.8], [6.1, 49.8], [6.1, 50.0]])
        p = tm.map_payload("Ardennes", [ao], [], [], worker_url="https://w.example")
        self.assertEqual(p["tiles"], "https://w.example/tiles/{z}/{x}/{y}.mvt")
        self.assertEqual((p["tile_format"], p["attribution"]), ("mvt", "© OpenStreetMap contributors"))
        self.assertNotIn("maptiler", json.dumps(p).lower())


class TestWorkerReadsOurArchive(unittest.TestCase):
    """The JS PMTiles reader returns the same bytes Python wrote — cross-language."""

    def test_node_reader(self):
        self._run(pm.ROOT_MAX)

    def test_node_reader_through_leaf_directories(self):
        self._run(64)

    def _run(self, root_max):
        node = shutil.which("node")
        if not node:
            self.skipTest("node not installed")
        tmp = Path(tempfile.mkdtemp(prefix="phoenix_jsmaps_"))
        try:
            tiles = build_archive(tmp / "w.pmtiles", (5.9, 49.8, 6.3, 50.05), range(0, 11), root_max,
                                  unique=root_max < pm.ROOT_MAX)
            if root_max < pm.ROOT_MAX:
                self.assertGreater(pm.Reader(pm.FileSource(tmp / "w.pmtiles")).header.leaf_length, 0)
            picks = []
            for z in (0, 4, 8):
                x, y = pm.lonlat_to_tile(6.0, 49.9, z)
                picks.append({"z": z, "x": x, "y": y,
                              "sha3": __import__("hashlib").sha3_512(tiles[pm.zxy_to_tileid(z, x, y)]).hexdigest()})
            manifest = tmp / "m.json"
            manifest.write_text(json.dumps({"archive": str(tmp / "w.pmtiles"), "picks": picks}))
            r = subprocess.run([node, str(REPO_ROOT / "game" / "worker" / "test" / "worker.test.mjs"),
                                "--maps", str(manifest)], capture_output=True, text=True, timeout=120)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=1)
