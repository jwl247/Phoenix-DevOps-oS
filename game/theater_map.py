#!/usr/bin/env python3
"""
theater_map.py — The theater map: what Godot draws, and Frank's own snapshot
Sacrifice | Phoenix DevOps OS | jwl247 | GPL v3

Maps are our own (JW, 2026-10-05): OpenStreetMap vector tiles in a PMTiles
archive we cut from the Protomaps planet build (pmtiles.py), kept in the clone
pool, served from our R2 by the sacrifice-worker. No map vendor, no key, no
terms but ODbL's: credit "© OpenStreetMap contributors".

Two outputs:

1. map_payload()  — the live map for the Godot client: our vector-tile URL
   (/tiles/{z}/{x}/{y}.mvt) plus GeoJSON for AO boundaries, named ground and
   King of Theater markers.

2. snapshot()     — Frank's strategic overview PNG, drawn here from the same
   vector tiles in a theater style (terrain, water, roads, places) with the
   game's layers on top. Tiles come from a local archive or the worker and may
   be cached freely — the data is ours.
"""

from __future__ import annotations

import hashlib
import math
import os
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Iterable, Optional, Protocol

from . import mvt
from .pmtiles import Reader, FileSource, lonlat_to_tile

ATTRIBUTION = "© OpenStreetMap contributors"
TILE_SIZE = 256
USER_AGENT = "phoenix-sacrifice/1.0"

CONTROL_COLORS = {          # RGBA — AO fill by control state
    "neutral":   (149, 165, 166, 70),
    "held":      (39, 174, 96, 80),
    "contested": (192, 57, 43, 95),
}
OFFICER_GOLD  = (241, 196, 15, 255)
PLAYER_WHITE  = (236, 240, 241, 255)
KING_RED      = (192, 57, 43, 255)

# Theater style — muted topo palette, readable under the game's overlays.
EARTH = (233, 228, 212)
FILL = {
    "forest": (176, 200, 158), "wood": (176, 200, 158), "nature_reserve": (190, 210, 170),
    "scrub": (200, 210, 172), "heath": (210, 208, 175), "grass": (214, 226, 184),
    "meadow": (218, 228, 186), "park": (200, 222, 176), "farmland": (238, 232, 196),
    "orchard": (214, 226, 184), "vineyard": (220, 220, 180), "residential": (222, 214, 204),
    "urban_area": (218, 210, 200), "industrial": (214, 206, 214), "commercial": (226, 210, 206),
    "military": (226, 190, 180), "quarry": (210, 200, 190), "cemetery": (200, 212, 190),
    "barren": (226, 220, 206), "sand": (236, 226, 190), "glacier": (240, 246, 250),
}
WATER = (156, 192, 221)
ROADS = {   # kind → (casing, fill, width at z12)
    "highway":    ((120, 70, 40), (214, 120, 70), 3.2),
    "major_road": ((130, 110, 80), (240, 196, 110), 2.4),
    "minor_road": ((150, 145, 135), (255, 255, 255), 1.4),
    "path":       (None, (150, 120, 90), 0.8),
    "other":      (None, (170, 165, 155), 0.8),
}
RAIL = (90, 90, 90)
BOUNDARY = (140, 90, 160)
BUILDING = (200, 190, 180)


def _font(size: int):
    """A real TrueType face so labels read at map scale; Pillow's own as the floor."""
    from PIL import ImageFont
    for name in ("DejaVuSans-Bold.ttf", "arialbd.ttf", "Arial Bold.ttf", "LiberationSans-Bold.ttf",
                 "C:/Windows/Fonts/arialbd.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


# ---------------------------------------------------------------------------
# Tile sources — all ours
# ---------------------------------------------------------------------------

class VectorSource(Protocol):
    max_zoom: int

    def tile(self, z: int, x: int, y: int) -> Optional[bytes]: ...


class ArchiveSource:
    """A local PMTiles archive (e.g. the theater extract before it goes to R2)."""

    def __init__(self, path: Path):
        self.reader = Reader(FileSource(path))
        self.max_zoom = self.reader.header.max_zoom

    def tile(self, z, x, y):
        return self.reader.tile(z, x, y)


class WorkerSource:
    """Tiles from the sacrifice-worker, cached on disk (our own data — caching is fine)."""

    def __init__(self, base_url: Optional[str] = None, cache_dir: Optional[Path] = None, max_zoom: int = 15):
        self.base = (base_url or os.environ.get("SACRIFICE_WORKER_URL", "")).rstrip("/")
        if not self.base:
            raise RuntimeError("SACRIFICE_WORKER_URL is not set")
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.max_zoom = max_zoom

    def tile(self, z, x, y):
        path = self.cache_dir / str(z) / str(x) / f"{y}.mvt" if self.cache_dir else None
        if path and path.exists():
            return path.read_bytes() or None
        req = urllib.request.Request(f"{self.base}/tiles/{z}/{x}/{y}.mvt", headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = r.read()
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise
            data = b""
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        return data or None


# ---------------------------------------------------------------------------
# Web Mercator
# ---------------------------------------------------------------------------

def world_px(lon: float, lat: float, z: int) -> tuple[float, float]:
    lat = max(-85.05112878, min(85.05112878, lat))
    scale = TILE_SIZE * 2 ** z
    x = (lon + 180.0) / 360.0 * scale
    s = math.sin(math.radians(lat))
    y = (0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)) * scale
    return x, y


def fit_zoom(bbox: tuple[float, float, float, float], width: int, height: int,
             pad: float = 0.1, max_zoom: int = 16) -> int:
    """Highest zoom at which the bbox (minlon, minlat, maxlon, maxlat) fits, with padding."""
    minlon, minlat, maxlon, maxlat = bbox
    for z in range(max_zoom, -1, -1):
        x1, y1 = world_px(minlon, maxlat, z)
        x2, y2 = world_px(maxlon, minlat, z)
        if (x2 - x1) <= width * (1 - 2 * pad) and (y2 - y1) <= height * (1 - 2 * pad):
            return z
    return 0


# ---------------------------------------------------------------------------
# Payload for the Godot client
# ---------------------------------------------------------------------------

def feature_collection(aos: Iterable, grounds: Iterable, kings: Iterable) -> dict:
    """aos: territory.AO; grounds: named_ground.NamedGround; kings: (KingTheaterState, AO)."""
    feats = [a.to_feature() for a in aos]
    feats += [g.to_feature() for g in grounds]
    for state, ao in kings:
        lon, lat = ao.centroid()
        feats.append({
            "type": "Feature", "id": f"king:{ao.ao_id}",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {"kind": "king", "ao_id": ao.ao_id, "king_id": state.king_id,
                           "king_callsign": state.king_callsign, "paid_crown": state.paid_crown},
        })
    return {"type": "FeatureCollection", "features": feats}


def map_payload(theater: str, aos: list, grounds: list, kings: list,
                worker_url: Optional[str] = None, max_zoom: int = 15) -> dict:
    base = (worker_url or os.environ.get("SACRIFICE_WORKER_URL", "")).rstrip("/")
    lons = [p[0] for a in aos for p in a.polygon]
    lats = [p[1] for a in aos for p in a.polygon]
    return {
        "theater": theater,
        "tiles": f"{base}/tiles/{{z}}/{{x}}/{{y}}.mvt",   # our own OSM vector tiles
        "tile_format": "mvt",
        "tile_compression": "gzip",
        "max_zoom": max_zoom,
        "attribution": ATTRIBUTION,
        "bbox": [min(lons), min(lats), max(lons), max(lats)] if aos else None,
        "geojson": feature_collection(aos, grounds, kings),
    }


# ---------------------------------------------------------------------------
# Frank's snapshot — drawn from our vector tiles
# ---------------------------------------------------------------------------

def _signed_area(ring) -> float:
    return sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(ring, ring[1:]))


def _draw_base(d, layers_by_tile, to_px, z: int, scale: float, f_place) -> None:
    """Paint the OSM layers in map order across every tile, then the place labels."""
    def polys(feature):
        for ring in feature.rings:
            if len(ring) >= 3:
                yield ring, _signed_area(ring) > 0      # MVT: exterior rings are clockwise (positive here)

    def each(name):
        for key, layers in layers_by_tile:
            layer = layers.get(name)
            if layer:
                for f in layer.features:
                    yield key, layer.extent, f

    # landcover then landuse fills
    for name in ("landcover", "landuse"):
        for key, ext, f in each(name):
            color = FILL.get(f.props.get("kind"))
            if color and f.type == mvt.POLYGON:
                for ring, outer in polys(f):
                    d.polygon([to_px(key, ext, p) for p in ring], fill=color if outer else EARTH)
    # water
    for key, ext, f in each("water"):
        if f.type == mvt.POLYGON:
            for ring, outer in polys(f):
                d.polygon([to_px(key, ext, p) for p in ring], fill=WATER if outer else EARTH)
        elif f.type == mvt.LINESTRING and z >= 10:
            w = 2.0 if f.props.get("kind") == "river" else 1.0
            for ring in f.rings:
                d.line([to_px(key, ext, p) for p in ring], fill=WATER, width=max(1, int(w * scale)))
    if z >= 14:
        for key, ext, f in each("buildings"):
            for ring, outer in polys(f):
                if outer:
                    d.polygon([to_px(key, ext, p) for p in ring], fill=BUILDING)
    for key, ext, f in each("boundaries"):
        if f.props.get("kind") in ("country", "region"):
            for ring in f.rings:
                d.line([to_px(key, ext, p) for p in ring], fill=BOUNDARY, width=max(1, int(2 * scale)))
    # roads: all casings, then all fills, minor first
    order = ["other", "path", "minor_road", "major_road", "highway"]
    roads = sorted((x for x in each("roads") if x[2].type == mvt.LINESTRING),
                   key=lambda t: order.index(t[2].props.get("kind")) if t[2].props.get("kind") in order else 0)
    for casing_pass in (True, False):
        for key, ext, f in roads:
            kind = f.props.get("kind")
            if kind == "rail":
                if not casing_pass:
                    for ring in f.rings:
                        d.line([to_px(key, ext, p) for p in ring], fill=RAIL, width=max(1, int(scale)))
                continue
            casing, fill, w = ROADS.get(kind, ROADS["other"])
            if kind in ("path", "other") and z < 12:
                continue
            width = max(1, int(round(w * scale)))
            for ring in f.rings:
                pts = [to_px(key, ext, p) for p in ring]
                if casing_pass and casing:
                    d.line(pts, fill=casing, width=width + 2)
                elif not casing_pass:
                    d.line(pts, fill=fill, width=width)
    # place names, biggest first, no duplicates or overlaps
    seen, boxes = set(), []
    places = [x for x in each("places") if x[2].props.get("name") and x[2].type == mvt.POINT
              and (x[2].props.get("min_zoom") or 0) < z]            # one level in hand: towns first, villages as you zoom
    places.sort(key=lambda t: (t[2].props.get("population_rank") or 0), reverse=True)
    for key, ext, f in places:
        name = f.props["name"]
        if name in seen:
            continue
        x, y = to_px(key, ext, f.rings[0][0])
        b = d.textbbox((x, y), name, font=f_place, anchor="mm")
        box = (b[0] - 6, b[1] - 4, b[2] + 6, b[3] + 4)                 # breathing room
        if any(not (box[2] < b[0] or box[0] > b[2] or box[3] < b[1] or box[1] > b[3]) for b in boxes):
            continue
        seen.add(name)
        boxes.append(box)
        d.text((x, y), name, font=f_place, anchor="mm", fill=(60, 55, 50),
               stroke_width=2, stroke_fill=(255, 255, 255))


def snapshot(
    aos:     list,
    grounds: list,
    kings:   list,
    out:     Path,
    source:  VectorSource,
    width:   int = 1024,
    height:  int = 768,
    title:   Optional[str] = None,
) -> tuple[Path, str]:
    """Render the theater overview to PNG from our own vector tiles. Returns (path, sha3-512)."""
    from PIL import Image, ImageDraw

    if not aos:
        raise ValueError("No AOs to draw")
    lons = [p[0] for a in aos for p in a.polygon]
    lats = [p[1] for a in aos for p in a.polygon]
    view_z = fit_zoom((min(lons), min(lats), max(lons), max(lats)), width, height)
    z = min(view_z, source.max_zoom)                  # data zoom; drawn scaled up beyond it
    scale = 2 ** (view_z - z)
    cx, cy = world_px((min(lons) + max(lons)) / 2, (min(lats) + max(lats)) / 2, view_z)
    ox, oy = cx - width / 2, cy - height / 2

    t0x, t0y = int(ox / scale // TILE_SIZE), int(oy / scale // TILE_SIZE)
    t1x, t1y = int((ox + width) / scale // TILE_SIZE), int((oy + height) / scale // TILE_SIZE)
    need = [(tx, ty) for ty in range(t0y, t1y + 1) if 0 <= ty < 2 ** z
            for tx in range(t0x, t1x + 1)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        raw = list(pool.map(lambda t: source.tile(z, t[0] % (2 ** z), t[1]), need))
    layers_by_tile = [((tx, ty), mvt.decode(b)) for (tx, ty), b in zip(need, raw) if b]

    def to_px(key, extent, p):
        tx, ty = key
        return ((tx + p[0] / extent) * TILE_SIZE * scale - ox,
                (ty + p[1] / extent) * TILE_SIZE * scale - oy)

    base = Image.new("RGB", (width, height), EARTH)
    _draw_base(ImageDraw.Draw(base), layers_by_tile, to_px, view_z, max(1.0, scale ** 0.5), _font(12))
    base = base.convert("RGBA")

    def px(lon, lat):
        x, y = world_px(lon, lat, view_z)
        return (x - ox, y - oy)

    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    f_ao, f_lbl, f_small = _font(17), _font(14), _font(11)
    halo = {"stroke_width": 3, "stroke_fill": (0, 0, 0, 230)}
    for a in aos:
        pts = [px(lon, lat) for lon, lat in a.polygon]
        fill = CONTROL_COLORS[a.control.value]
        d.polygon(pts, fill=fill, outline=fill[:3] + (255,))
        d.line(pts, fill=fill[:3] + (255,), width=3)
        cxp, cyp = px(*a.centroid())
        d.text((cxp, cyp + 14), a.name, fill=(255, 255, 255, 255), font=f_ao, anchor="mt", **halo)
    for g in grounds:
        x, y = px(g.lon, g.lat)
        color = OFFICER_GOLD if g.kind.value == "officer_fallen" else PLAYER_WHITE
        d.ellipse((x - 6, y - 6, x + 6, y + 6), fill=color, outline=(0, 0, 0, 255), width=2)
        d.text((x + 10, y), g.name, fill=color, font=f_lbl, anchor="lm", **halo)
    for state, a in kings:
        x, y = px(*a.centroid())
        d.polygon([(x - 9, y + 6), (x - 9, y - 4), (x - 4, y + 1), (x, y - 8),
                   (x + 4, y + 1), (x + 9, y - 4), (x + 9, y + 6)], fill=KING_RED, outline=(0, 0, 0, 255))
        if state.king_callsign:
            d.text((x, y - 12), f"King {state.king_callsign}", fill=(255, 255, 255, 255),
                   font=f_lbl, anchor="mb", stroke_width=3, stroke_fill=KING_RED[:3] + (255,))
    if title:
        d.rectangle((0, 0, width, 30), fill=(0, 0, 0, 160))
        d.text((10, 15), title, fill=(255, 255, 255, 255), font=f_ao, anchor="lm")
    tw = d.textlength(ATTRIBUTION, font=f_small)
    d.rectangle((width - tw - 12, height - 18, width, height), fill=(255, 255, 255, 190))
    d.text((width - 6, height - 9), ATTRIBUTION, fill=(0, 0, 0, 255), font=f_small, anchor="rm")

    img = Image.alpha_composite(base, layer).convert("RGB")
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "PNG", optimize=True)
    return out, hashlib.sha3_512(out.read_bytes()).hexdigest()
