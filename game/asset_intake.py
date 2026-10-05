#!/usr/bin/env python3
"""
asset_intake.py — Vehicle photo → Frank import → live art
Sacrifice | Phoenix DevOps OS | jwl247 | GPL v3

JW shoots a real vehicle. This is the whole path from that photo to what the
game draws, through Frank's import method — no manual asset management:

  1. stage   — copy the photo to a content-named file:
               <sha3-512[:16]>_<model_id>.<ext>
               (intake keys objects by file NAME, so every distinct photo
               gets a distinct name — sidesteps the known basename collision)
  2. intake  — scripts/hsf-intake.sh → hex identity + sidecar → clone pool
               (R2) → D1 custody receipt. Integrity checked against the
               sidecar's hash before anything is registered.
  3. version — the photo becomes a new version in the model's AssetSlot
               (PENDING_CUTOUT). Older versions are kept, never deleted.
  4. cutout  — background removal runs LOCALLY (rembg, CPU) — no vendor.
               The cutout is intaked the same way and becomes LIVE.
               No rembg on this machine → the photo waits as pending, or
               goes live as-is when asked (--no-cutout).

Upgrading the art later is the same command with a new photo.

    python -m game.asset_intake list
    python -m game.asset_intake add mbt D:/photos/tank_front.jpg
    python -m game.asset_intake add mbt D:/photos/tank_front.jpg --no-cutout
    python -m game.asset_intake promote mbt 3
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol

from .vehicle import VehicleRegistry, AssetStatus, AssetVersion, default_registry

log = logging.getLogger("asset_intake")

REPO_ROOT = Path(__file__).resolve().parents[1]
PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".heic"}
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


# ---------------------------------------------------------------------------
# Identity — matches sector2/package-handler/intake.sh exactly
# ---------------------------------------------------------------------------

def intake_hex(filename: str) -> str:
    """intake.sh: hex = to_hex(basename)."""
    return filename.encode("utf-8").hex()


def tav_address(filename: str) -> str:
    """intake.sh: USYS short address = base58 of the hex identity's first 8 bytes."""
    data = bytes.fromhex(intake_hex(filename)[:16])
    n, out = int.from_bytes(data, "big"), ""
    while n:
        n, r = divmod(n, 58)
        out = B58[r] + out
    for b in data:
        if b:
            break
        out = B58[0] + out
    return out


def _digest(path: Path, algo: str) -> str:
    h = hashlib.new(algo)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def _game_root() -> Path:
    archive = Path(os.environ.get("PHOENIX_ARCHIVE_ROOT", "/var/lib/phoenix/archive"))
    return archive.parent


def staging_dir() -> Path:
    return Path(os.environ.get("PHOENIX_ASSET_STAGING", str(_game_root() / "asset_staging")))


def registry_path() -> Path:
    return Path(os.environ.get("PHOENIX_VEHICLE_REGISTRY", str(_game_root() / "vehicle_registry.json")))


def stage_photo(src: Path, model_id: str, suffix: str = "") -> tuple[Path, str]:
    """Copy into staging under a content name. Returns (staged path, sha3-512)."""
    src = Path(src)
    if not src.is_file():
        raise FileNotFoundError(f"Photo not found: {src}")
    ext = src.suffix.lower()
    if ext not in PHOTO_EXTS:
        raise ValueError(f"{src.name}: not a photo ({sorted(PHOTO_EXTS)})")
    if not model_id.replace("_", "").isalnum():
        raise ValueError(f"Bad model id: {model_id!r}")
    sha3 = _digest(src, "sha3_512")
    out = staging_dir() / f"{sha3[:16]}_{model_id}{suffix}{ext}"
    out.parent.mkdir(parents=True, exist_ok=True)
    if not out.exists():
        shutil.copy2(src, out)
    return out, sha3


# ---------------------------------------------------------------------------
# Intake — Frank's import method
# ---------------------------------------------------------------------------

@dataclass
class IntakeReceipt:
    filename: str
    hex_id:   str
    tav:      str
    sha3_512: str
    version:  str
    sidecar:  Optional[str] = None


class Intaker(Protocol):
    def intake(self, path: Path) -> IntakeReceipt: ...


def _find_bash() -> str:
    """Git Bash on Windows (never WSL's System32 bash); plain bash elsewhere."""
    explicit = os.environ.get("PHOENIX_BASH")
    if explicit:
        return explicit
    if os.name == "nt":
        for c in (r"C:\Program Files\Git\bin\bash.exe", r"C:\Program Files (x86)\Git\bin\bash.exe"):
            if Path(c).exists():
                return c
        raise RuntimeError("Git Bash not found — set PHOENIX_BASH to bash.exe")
    found = shutil.which("bash")
    if not found:
        raise RuntimeError("bash not found")
    return found


def _clonepool_dir() -> Path:
    raw = os.environ.get("CLONEPOOL_DIR")
    if not raw and os.name == "nt":
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
            raw = winreg.QueryValueEx(k, "CLONEPOOL_DIR")[0]
    if not raw:
        raise RuntimeError("CLONEPOOL_DIR is not set")
    return Path(raw)


class HsfIntaker:
    """Runs scripts/hsf-intake.sh, then proves the pool holds these exact bytes."""

    def __init__(self, script: Optional[Path] = None, timeout: int = 600):
        self.script  = Path(script or REPO_ROOT / "scripts" / "hsf-intake.sh")
        self.timeout = timeout

    def command(self, path: Path) -> list[str]:
        return [_find_bash(), str(self.script).replace("\\", "/"), str(path).replace("\\", "/")]

    def intake(self, path: Path) -> IntakeReceipt:
        path = Path(path)
        r = subprocess.run(self.command(path), capture_output=True, text=True,
                           timeout=self.timeout, cwd=str(REPO_ROOT))
        if r.returncode != 0:
            raise RuntimeError(f"intake failed ({r.returncode}): {(r.stderr or r.stdout)[-800:]}")
        hex_id = intake_hex(path.name)
        sidecar = _clonepool_dir() / "T1" / hex_id / f"{hex_id}.sidecar.json"
        if not sidecar.exists():
            raise RuntimeError(f"intake reported OK but no sidecar at {sidecar}")
        meta = json.loads(sidecar.read_text(encoding="utf-8"))
        sha256 = _digest(path, "sha256")
        if meta.get("sha256") and meta["sha256"] != sha256:
            raise RuntimeError(f"Pool hash {meta['sha256'][:12]} ≠ photo {sha256[:12]} — not registered")
        return IntakeReceipt(path.name, hex_id, tav_address(path.name), _digest(path, "sha3_512"),
                             str(meta.get("version", "")), str(sidecar))


# ---------------------------------------------------------------------------
# Background removal — local, CPU, no vendor
# ---------------------------------------------------------------------------

class CutoutUnavailable(RuntimeError):
    pass


class Cutter(Protocol):
    def cut(self, src: Path, dst: Path) -> Path: ...


class RembgCutter:
    def cut(self, src: Path, dst: Path) -> Path:
        try:
            from rembg import remove
        except ImportError as e:
            raise CutoutUnavailable("rembg is not installed on this machine") from e
        dst.write_bytes(remove(Path(src).read_bytes()))
        return dst


# ---------------------------------------------------------------------------
# The pipeline
# ---------------------------------------------------------------------------

@dataclass
class PhotoResult:
    model_id: str
    photo:    AssetVersion
    cutout:   Optional[AssetVersion]
    live:     AssetVersion
    note:     str


def add_vehicle_photo(
    registry:     VehicleRegistry,
    model_id:     str,
    photo:        Path,
    intaker:      Optional[Intaker] = None,
    cutter:       Optional[Cutter]  = None,
    no_cutout:    bool = False,
) -> PhotoResult:
    """Photo → intake → new art version → (cutout → intake → LIVE)."""
    model   = registry.model(model_id)
    intaker = intaker or HsfIntaker()
    cutter  = cutter or RembgCutter()

    staged, sha3 = stage_photo(photo, model_id)
    for v in model.asset.versions:
        if v.sha3_512 == sha3 and v.source == "photo":
            raise ValueError(f"That photo is already version {v.version} of {model_id}")
    rec = intaker.intake(staged)
    if rec.sha3_512 != sha3:
        raise RuntimeError("Intake receipt does not match the staged photo")

    if no_cutout:
        pv = model.asset.add(AssetStatus.LIVE, "photo", tav=rec.tav, hex_id=rec.hex_id,
                             sha3_512=sha3, filename=rec.filename)
        return PhotoResult(model_id, pv, None, pv, "photo live as shot (no cutout)")

    pv = model.asset.add(AssetStatus.PENDING_CUTOUT, "photo", tav=rec.tav, hex_id=rec.hex_id,
                         sha3_512=sha3, filename=rec.filename)
    cut_path = staged.with_name(f"{staged.stem}_cutout.png")
    try:
        cutter.cut(staged, cut_path)
    except CutoutUnavailable as e:
        return PhotoResult(model_id, pv, None, model.asset.live(),
                           f"photo intaked as v{pv.version}, waiting for a cutout ({e}); "
                           f"`promote {model_id} {pv.version}` to use it as shot")
    final = cut_path.with_name(f"{_digest(cut_path, 'sha3_512')[:16]}_{model_id}_cutout.png")
    cut_path.replace(final)
    crec = intaker.intake(final)
    cv = model.asset.add(AssetStatus.LIVE, "cutout", tav=crec.tav, hex_id=crec.hex_id,
                         sha3_512=crec.sha3_512, filename=crec.filename, derived_from=pv.version)
    return PhotoResult(model_id, pv, cv, cv, f"cutout live as v{cv.version}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _load_registry(path: Path) -> VehicleRegistry:
    reg = default_registry()
    reg.load_assets(path)
    return reg


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m game.asset_intake",
                                 description="Vehicle photos → Frank import → game art")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="art status for every vehicle model")
    a = sub.add_parser("add", help="intake a photo as a model's new art version")
    a.add_argument("model_id")
    a.add_argument("photo", type=Path)
    a.add_argument("--no-cutout", action="store_true", help="use the photo as shot")
    p = sub.add_parser("promote", help="make a pending photo version live")
    p.add_argument("model_id")
    p.add_argument("version", type=int)
    args = ap.parse_args(argv)
    try:
        return _run(args)
    except (FileNotFoundError, ValueError, RuntimeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


def _run(args) -> int:
    path = registry_path()
    reg = _load_registry(path)

    if args.cmd == "list":
        for m in reg.models.values():
            live = m.asset.live()
            pend = [v.version for v in m.asset.versions if v.status == AssetStatus.PENDING_CUTOUT]
            print(f"{m.model_id:<13} {m.name:<27} v{live.version} {live.status.value:<12}"
                  f"{live.tav or '-':<12} pending={pend or '-'}")
        return 0
    if args.cmd == "add":
        res = add_vehicle_photo(reg, args.model_id, args.photo, no_cutout=args.no_cutout)
        reg.save(path)
        print(f"{res.model_id}: {res.note} (photo TAV {res.photo.tav})")
        return 0
    if args.cmd == "promote":
        v = reg.model(args.model_id).asset.promote(args.version)
        reg.save(path)
        print(f"{args.model_id}: v{v.version} is live ({v.tav})")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
