#!/usr/bin/env python3
"""
mvt.py — Mapbox Vector Tile decoder, no dependencies
Sacrifice | Phoenix DevOps OS | jwl247 | GPL v3

Reads the OpenStreetMap vector tiles in our own PMTiles archives (Protomaps
basemap layers: earth, water, landcover, landuse, roads, boundaries,
buildings, places, pois). Just enough protobuf to read the MVT 2.1 spec:
layers → features → tags + geometry commands. Geometry comes back in tile
coordinates (0..extent, usually 4096).

Spec: https://github.com/mapbox/vector-tile-spec/tree/master/2.1
"""

from __future__ import annotations

import gzip
import struct
from dataclasses import dataclass, field

POINT, LINESTRING, POLYGON = 1, 2, 3


def _varint(buf: bytes, pos: int) -> tuple[int, int]:
    result = shift = 0
    while True:
        b = buf[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if not b & 0x80:
            return result, pos
        shift += 7


def _fields(buf: bytes):
    """Yield (field_number, wire_type, value) — value is int or bytes."""
    pos, end = 0, len(buf)
    while pos < end:
        key, pos = _varint(buf, pos)
        num, wt = key >> 3, key & 7
        if wt == 0:
            v, pos = _varint(buf, pos)
        elif wt == 1:
            v, pos = buf[pos:pos + 8], pos + 8
        elif wt == 2:
            n, pos = _varint(buf, pos)
            v, pos = buf[pos:pos + n], pos + n
        elif wt == 5:
            v, pos = buf[pos:pos + 4], pos + 4
        else:
            raise ValueError(f"Unsupported protobuf wire type {wt}")
        yield num, wt, v


def _packed(buf: bytes) -> list[int]:
    out, pos = [], 0
    while pos < len(buf):
        v, pos = _varint(buf, pos)
        out.append(v)
    return out


def _zigzag(n: int) -> int:
    return (n >> 1) ^ -(n & 1)


def _value(buf: bytes):
    for num, wt, v in _fields(buf):
        if num == 1:
            return v.decode("utf-8", "replace")
        if num == 2:
            return struct.unpack("<f", v)[0]
        if num == 3:
            return struct.unpack("<d", v)[0]
        if num == 4:
            return v - (1 << 64) if v >= 1 << 63 else v
        if num == 5:
            return v
        if num == 6:
            return _zigzag(v)
        if num == 7:
            return bool(v)
    return None


@dataclass
class Feature:
    type:  int                         # POINT / LINESTRING / POLYGON
    props: dict
    rings: list                        # list of [(x, y), ...] in tile coords
    id:    int | None = None


@dataclass
class Layer:
    name:     str
    extent:   int = 4096
    features: list = field(default_factory=list)


def decode_geometry(cmds: list[int], gtype: int) -> list:
    rings, cur, x, y, i = [], [], 0, 0, 0
    while i < len(cmds):
        cmd, count = cmds[i] & 7, cmds[i] >> 3
        i += 1
        if cmd == 1:                                   # MoveTo
            for _ in range(count):
                x += _zigzag(cmds[i]); y += _zigzag(cmds[i + 1]); i += 2
                if gtype == POINT:
                    rings.append([(x, y)])
                else:
                    if cur:
                        rings.append(cur)
                    cur = [(x, y)]
        elif cmd == 2:                                 # LineTo
            for _ in range(count):
                x += _zigzag(cmds[i]); y += _zigzag(cmds[i + 1]); i += 2
                cur.append((x, y))
        elif cmd == 7:                                 # ClosePath
            if cur:
                cur.append(cur[0])
        else:
            raise ValueError(f"Bad geometry command {cmd}")
    if cur:
        rings.append(cur)
    return rings


def decode(tile: bytes) -> dict[str, Layer]:
    """Decode one tile (gzip or raw). Returns {layer name: Layer}."""
    if tile[:2] == b"\x1f\x8b":
        tile = gzip.decompress(tile)
    layers: dict[str, Layer] = {}
    for num, _, lbuf in _fields(tile):
        if num != 3:
            continue
        name, extent, keys, values, raw_feats = "", 4096, [], [], []
        for n, _, v in _fields(lbuf):
            if n == 1:
                name = v.decode("utf-8", "replace")
            elif n == 2:
                raw_feats.append(v)
            elif n == 3:
                keys.append(v.decode("utf-8", "replace"))
            elif n == 4:
                values.append(_value(v))
            elif n == 5:
                extent = v
        layer = Layer(name, extent)
        for fbuf in raw_feats:
            fid, tags, gtype, geom = None, [], 0, []
            for n, wt, v in _fields(fbuf):
                if n == 1:
                    fid = v
                elif n == 2:
                    tags = _packed(v) if wt == 2 else [v]
                elif n == 3:
                    gtype = v
                elif n == 4:
                    geom = _packed(v)
            props = {keys[tags[i]]: values[tags[i + 1]] for i in range(0, len(tags) - 1, 2)}
            layer.features.append(Feature(gtype, props, decode_geometry(geom, gtype), fid))
        layers[name] = layer
    return layers
