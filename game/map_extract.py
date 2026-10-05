#!/usr/bin/env python3
"""
map_extract.py — cut Sacrifice's theater maps out of the OpenStreetMap planet
Sacrifice | Phoenix DevOps OS | jwl247 | GPL v3

    python -m game.map_extract extract F:/Phoenix/maps/sacrifice-world.pmtiles --bbox 5.9,49.8,6.3,50.05
    python -m game.map_extract info F:/Phoenix/maps/sacrifice-world.pmtiles

Reads only the boxes asked for (HTTP range requests) from the newest Protomaps
daily build — never the whole planet. Data © OpenStreetMap contributors, ODbL.
The archive then goes through Frank's import method (hsf-intake.sh) to R2.
"""

from __future__ import annotations

import json
from pathlib import Path

from .pmtiles import (Reader, FileSource, HttpSource, extract, USER_AGENT,
                      TILE_TYPE, COMPRESSION)

PLANET_INDEX = "https://build-metadata.protomaps.dev/builds.json"
PLANET_BASE = "https://build.protomaps.com/"


def latest_planet() -> str:
    """URL of the newest Protomaps daily OSM build."""
    import urllib.request
    req = urllib.request.Request(PLANET_INDEX, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as r:
        builds = json.loads(r.read())
    return PLANET_BASE + builds[-1]["key"]


def padded(bbox: tuple[float, float, float, float], pad: float) -> tuple[float, float, float, float]:
    """Grow a bbox by `pad` of its size on every side — the map around a theater, not just inside it."""
    minlon, minlat, maxlon, maxlat = bbox
    dx, dy = (maxlon - minlon) * pad, (maxlat - minlat) * pad
    return (max(-180.0, minlon - dx), max(-85.0, minlat - dy), min(180.0, maxlon + dx), min(85.0, maxlat + dy))


def main(argv=None) -> int:
    import argparse
    import sys
    import time
    ap = argparse.ArgumentParser(prog="python -m game.map_extract",
                                 description="Cut theater maps out of the OpenStreetMap planet (no vendor)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("extract", help="extract one or more boxes into a PMTiles archive")
    e.add_argument("out", type=Path)
    e.add_argument("--bbox", action="append", required=True,
                   help="minlon,minlat,maxlon,maxlat (repeat for several theaters)")
    e.add_argument("--pad", type=float, default=0.25, help="extra map around each box (fraction, default 0.25)")
    e.add_argument("--max-zoom", type=int, default=15)
    e.add_argument("--source", help="PMTiles URL or file (default: newest Protomaps planet build)")
    i = sub.add_parser("info", help="show an archive's header")
    i.add_argument("archive", type=Path)
    a = ap.parse_args(argv)

    if a.cmd == "info":
        h = Reader(FileSource(a.archive)).header
        print(f"z{h.min_zoom}-{h.max_zoom}  {h.addressed_tiles} tiles  "
              f"bounds {h.min_lon:.4f},{h.min_lat:.4f},{h.max_lon:.4f},{h.max_lat:.4f}  "
              f"{TILE_TYPE.get(h.tile_type)}/{COMPRESSION.get(h.tile_compression)}")
        return 0
    try:
        boxes = [padded(tuple(float(v) for v in b.split(",")), a.pad) for b in a.bbox]
        for b in boxes:
            if len(b) != 4 or b[0] >= b[2] or b[1] >= b[3]:
                raise ValueError(f"bad bbox {b}")
    except ValueError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    src_url = a.source or latest_planet()
    source = FileSource(Path(src_url)) if Path(src_url).exists() else HttpSource(src_url)
    print(f"source: {src_url}")
    t = time.time()
    stats = extract(Reader(source), boxes, a.out, 0, a.max_zoom,
                    progress=lambda d, n: print(f"\r  {d}/{n} reads", end="", flush=True))
    print(f"\n{a.out}: {stats['tiles']} tiles, {stats['bytes'] / 1e6:.1f} MB in {time.time() - t:.1f}s")
    print('next: intake it - & "C:\\Program Files\\Git\\bin\\bash.exe" scripts/hsf-intake.sh '
          + str(a.out).replace("\\", "/"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
