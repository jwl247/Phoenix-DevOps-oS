#!/usr/bin/env python3
"""
config_centralizer.py — Sector 2 / Ring 0 / SYSTEM
Phoenix DevOps OS | Helix Lightning Kernel | jwl247 | GPL v3

Config scanner, importer, desktop card writer.

Scans sector directories for .conf .env .yaml .yml .json .toml .ini files,
runs each through the TAV intake pipeline, then writes a desktop card
(human-readable summary) to ~/Phoenix/cards/<hex>.card.

Usage:
  python3 config_centralizer.py [path ...]   scan given paths
  python3 config_centralizer.py              scan default sector paths
"""

import sys
import os
import re
import json
import datetime as dt
from pathlib import Path

# ── Import path resolution ─────────────────────────────────────────────────────
# This file:  projects/phoenix-devops/sector2/config_centralizer.py
# parents[2]: projects/  — needed so "from unitedsys.core.intake import ..." works
_PROJECTS = Path(__file__).resolve().parents[2]
if str(_PROJECTS) not in sys.path:
    sys.path.insert(0, str(_PROJECTS))

from unitedsys.core.intake import (   # noqa: E402
    intake_file, hex_identity, CLONEPOOL_DIR,
)

# ── Constants ─────────────────────────────────────────────────────────────────
CARDS_DIR   = Path(os.environ.get("PHOENIX_CARDS", Path.home() / "Phoenix" / "cards"))
SECTOR_BASE = Path(__file__).resolve().parents[1]          # phoenix-devops/
PHOENIX_DIR = Path(os.environ.get("PHOENIX_HOME", Path.home() / "Phoenix"))

CONFIG_EXTS = {".conf", ".env", ".yaml", ".yml", ".json", ".toml", ".ini"}

# Directory names to never descend into
SKIP_DIRS = {
    "clonepool", "node_modules", ".git", "__pycache__",
    "cards", ".catalog", "logs", "intake",
}

# File suffixes to skip even when extension matches
SKIP_SUFFIXES = (".sidecar.json", ".card")

DEFAULT_SCAN_PATHS = [
    SECTOR_BASE / "sector1",
    SECTOR_BASE / "sector2",
    SECTOR_BASE / "sector3",
    SECTOR_BASE / "sector4",
    PHOENIX_DIR,
]

# ── Config value extraction ───────────────────────────────────────────────────

_PORT_RE = re.compile(r'(?:port|PORT|Listen)\s*[=:\s]+(\d{2,5})', re.I)
_KEY_RE  = re.compile(r'^([A-Z_][A-Z0-9_]{2,})\s*=', re.M)
_PATH_RE = re.compile(r'(?:path|dir|directory|file)\s*[=:]\s*([^\s\n#"\']{3,})', re.I)


def _extract_meta(path: Path) -> dict:
    result = {"ports": [], "keys": [], "paths": [], "type": path.suffix.lstrip(".")}
    try:
        text = path.read_text(errors="replace")[:8192]   # cap at 8 KB
    except Exception:
        return result
    result["ports"] = sorted(set(_PORT_RE.findall(text)))
    result["keys"]  = sorted(set(_KEY_RE.findall(text)))[:20]
    result["paths"] = sorted({p for p in _PATH_RE.findall(text) if len(p) > 2})[:10]
    return result


# ── Desktop card writer ───────────────────────────────────────────────────────

_WIDE = "═" * 52
_THIN = "─" * 52


def _section(title: str, items: list) -> list:
    lines = [_THIN, title]
    if not items:
        lines.append("  (none)")
        return lines
    # Wrap long item lists at ~48 chars per row
    row, accum = [], []
    for item in items:
        accum.append(item)
        if len("  ".join(accum)) > 46:
            row.append("  " + "  ".join(accum[:-1]))
            accum = [accum[-1]]
    if accum:
        row.append("  " + "  ".join(accum))
    lines.extend(row)
    return lines


def _write_card(sidecar_path: Path, source_path: Path) -> Path:
    with open(sidecar_path) as fh:
        s = json.load(fh)

    meta  = _extract_meta(source_path)
    b58   = s.get("b58", "?")
    hex_  = s.get("hex", "?")
    sha3  = s.get("sha3", "")
    now   = s.get("intaked_at", dt.datetime.now(dt.timezone.utc).isoformat())
    size  = s.get("size", 0)

    card_lines = [
        "PHOENIX CONFIG CARD",
        _WIDE,
        f"Name:     {source_path.name}",
        f"B58:      {b58}",
        f"Type:     {meta['type'] or 'config'}",
        f"Size:     {size:,} bytes",
        f"Intaked:  {now}",
    ]
    card_lines += _section("KEYS DETECTED", meta["keys"])
    card_lines += _section("PORTS DETECTED", meta["ports"])
    card_lines += _section("PATHS DETECTED", meta["paths"])
    card_lines += [
        _THIN,
        "CUSTODY",
        f"  Hex:    {hex_}",
        f"  SHA3:   {sha3[:32]}..." if sha3 else "  SHA3:   ?",
        f"  Header: USYS:{b58}:HEADER",
        f"  Footer: USYS:{b58}:FOOTER:{sha3[:16]}..." if sha3 else "  Footer: ?",
        _WIDE,
    ]

    CARDS_DIR.mkdir(parents=True, exist_ok=True)
    card_path = CARDS_DIR / f"{hex_}.card"
    card_path.write_text("\n".join(card_lines) + "\n")
    return card_path


# ── Scanner ───────────────────────────────────────────────────────────────────

def _find_configs(root: Path) -> list:
    found = []
    try:
        for item in root.rglob("*"):
            if not item.is_file():
                continue
            if item.suffix not in CONFIG_EXTS:
                continue
            if any(part in SKIP_DIRS for part in item.parts):
                continue
            if any(item.name.endswith(s) for s in SKIP_SUFFIXES):
                continue
            found.append(item)
    except PermissionError:
        pass
    return sorted(found)


def scan_and_import(paths: list) -> dict:
    results = {"scanned": 0, "intaked": 0, "cards": 0, "errors": []}

    all_configs = []
    for root in paths:
        root = Path(root).expanduser().resolve()
        if not root.exists():
            print(f"[cfg] skip (not found): {root}")
            continue
        configs = _find_configs(root)
        print(f"[cfg] {root.name}: {len(configs)} config file(s)")
        all_configs.extend(configs)

    results["scanned"] = len(all_configs)

    for cfg in all_configs:
        try:
            print(f"[cfg] intaking: {cfg.name}")
            intake_file(cfg)
            results["intaked"] += 1

            hex_id    = hex_identity(cfg.name)
            sidecar_p = CLONEPOOL_DIR / hex_id / f"{hex_id}.sidecar.json"
            if sidecar_p.exists():
                card_path = _write_card(sidecar_p, cfg)
                print(f"[cfg]   card → {card_path.name}")
                results["cards"] += 1
        except Exception as exc:
            msg = f"{cfg.name}: {exc}"
            print(f"[cfg] ERROR: {msg}")
            results["errors"].append(msg)

    return results


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    path_args = [a for a in sys.argv[1:] if not a.startswith("-")]
    paths     = [Path(a) for a in path_args] if path_args else DEFAULT_SCAN_PATHS

    print(f"[config_centralizer] sector 2 / ring 0 / SYSTEM  v1.0.0")
    print(f"[config_centralizer] cards dir:  {CARDS_DIR}")
    print(f"[config_centralizer] scan paths: {len(paths)}")
    for p in paths:
        print(f"  {p}")
    print()

    results = scan_and_import(paths)

    print()
    print("[config_centralizer] complete")
    print(f"  scanned: {results['scanned']}")
    print(f"  intaked: {results['intaked']}")
    print(f"  cards:   {results['cards']}")
    if results["errors"]:
        print(f"  errors:  {len(results['errors'])}")
        for e in results["errors"]:
            print(f"    {e}")


if __name__ == "__main__":
    main()
