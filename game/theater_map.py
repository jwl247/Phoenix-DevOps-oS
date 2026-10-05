#!/usr/bin/env python3
"""
theater_map.py — The theater map: what Godot draws, and Frank's own snapshot
Sacrifice | Phoenix DevOps OS | jwl247 | GPL v3

Two outputs:

1. map_payload()  — the live map for the Godot client: a key-free tile URL
   (the sacrifice-worker proxies tiles, so the MapTiler key never leaves the
   server and the tile vendor can be swapped without touching the client)
   plus GeoJSON for AO boundaries, named ground and King of Theater markers.

2. snapshot()     — the strategic overview as a PNG, built here: raster tiles
   stitched in Web Mercator and Frank's layers drawn on top. No static-map
   API needed (the MapTiler plan doesn't include one, and any XYZ tile
   source works). Tiles are cached on disk — fetched once, drawn many times.
   The PNG goes to the clone pool through Frank's import method.

The key: MAPTILER_API_KEY / PHOENIX_MAPTILER_KEY in the environment, else
the vault file (PHOENIX_VAULT_SECRETS, default F:\\Phoenix\\Vault\\secrets\\maptiler.env).
Never logged, never written into a payload, never in the repo.
"""

from __future__ import annotations

import hashlib
import io
import math
import os
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Iterable, Optional

ATTRIBUTION = "© MapTiler © OpenStreetMap contributors"
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


# ---------------------------------------------------------------------------
# Key and tile source
# ---------------------------------------------------------------------------

def load_maptiler_key() -> str:
    for var in ("MAPTILER_API_KEY", "PHOENIX_MAPTILER_KEY"):
        if os.environ.get(var):
            return os.environ[var].strip()
    vault = Path(os.environ.get("PHOENIX_VAULT_SECRETS", r"F:\Phoenix\Vault\secrets")) / "maptiler.env"
    if vault.exists():
        for line in vault.read_text(encoding="utf-8-sig").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                if k.strip() in ("MAPTILER_API_KEY", "PHOENIX_MAPTILER_KEY"):
                    return v.strip().strip('"').strip("'")
    raise RuntimeError("MapTiler key not found (env MAPTILER_API_KEY or the vault's maptiler.env)")


class TileSource:
    """XYZ raster tiles with a disk cache. Default: MapTiler, key from the vault."""

    def __init__(
        self,
        template:  Optional[str] = None,          # with {z} {x} {y}; may include {key}
        cache_dir: Optional[Path] = None,
        fetch:     Optional[Callable[[str], bytes]] = None,
        key:       Optional[str] = None,
        map_id:    str = "outdoor-v2",
    ):
        self.template  = template or f"https://api.maptiler.com/maps/{map_id}/256/{{z}}/{{x}}/{{y}}.png?key={{key}}"
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self._fetch    = fetch or _http_get
        self._key      = key
        self.cache_id  = hashlib.sha256(self.template.encode()).hexdigest()[:12]

    def _url(self, z: int, x: int, y: int) -> str:
        if "{key}" in self.template and self._key is None:
            self._key = load_maptiler_key()
        return self.template.format(z=z, x=x, y=y, key=self._key or "")

    def tile(self, z: int, x: int, y: int) -> bytes:
        n = 2 ** z
        x %= n
        if not (0 <= y < n):
            raise ValueError(f"Tile y={y} outside zoom {z}")
        path = self.cache_dir / self.cache_id / str(z) / str(x) / f"{y}.png" if self.cache_dir else None
        if path and path.exists():
            return path.read_bytes()
        data = self._fetch(self._url(z, x, y))
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(data)
            tmp.replace(path)
        return data


def _http_get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


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
                worker_url: Optional[str] = None) -> dict:
    base = (worker_url or os.environ.get("SACRIFICE_WORKER_URL", "")).rstrip("/")
    lons = [p[0] for a in aos for p in a.polygon]
    lats = [p[1] for a in aos for p in a.polygon]
    return {
        "theater": theater,
        "tiles": f"{base}/tiles/{{z}}/{{x}}/{{y}}.png",     # key-free: the worker proxies
        "tile_size": TILE_SIZE,
        "attribution": ATTRIBUTION,
        "bbox": [min(lons), min(lats), max(lons), max(lats)] if aos else None,
        "geojson": feature_collection(aos, grounds, kings),
    }


# ---------------------------------------------------------------------------
# Frank's snapshot
# ---------------------------------------------------------------------------

def snapshot(
    aos:     list,
    grounds: list,
    kings:   list,
    out:     Path,
    source:  Optional[TileSource] = None,
    width:   int = 1024,
    height:  int = 768,
    title:   Optional[str] = None,
) -> tuple[Path, str]:
    """Render the theater overview to PNG. Returns (path, sha3-512)."""
    from PIL import Image, ImageDraw

    if not aos:
        raise ValueError("No AOs to draw")
    source = source or TileSource()
    lons = [p[0] for a in aos for p in a.polygon]
    lats = [p[1] for a in aos for p in a.polygon]
    z = fit_zoom((min(lons), min(lats), max(lons), max(lats)), width, height)
    cx, cy = world_px((min(lons) + max(lons)) / 2, (min(lats) + max(lats)) / 2, z)
    ox, oy = cx - width / 2, cy - height / 2                       # world px of image origin

    base = Image.new("RGBA", (width, height), (40, 44, 52, 255))
    need = [(tx, ty)
            for ty in range(int(oy // TILE_SIZE), int((oy + height) // TILE_SIZE) + 1) if 0 <= ty < 2 ** z
            for tx in range(int(ox // TILE_SIZE), int((ox + width) // TILE_SIZE) + 1)]
    with ThreadPoolExecutor(max_workers=8) as pool:            # fetch in parallel, paste in order
        tiles = list(pool.map(lambda t: source.tile(z, t[0], t[1]), need))
    for (tx, ty), data in zip(need, tiles):
        tile = Image.open(io.BytesIO(data)).convert("RGBA")
        base.paste(tile, (int(tx * TILE_SIZE - ox), int(ty * TILE_SIZE - oy)))

    def px(lon, lat):
        x, y = world_px(lon, lat, z)
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
