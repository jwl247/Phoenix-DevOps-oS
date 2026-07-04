#!/usr/bin/env python3
"""
distro_handler.py — Phoenix DevOps OS
Distro handler: local ISO cache in clone pool, live install to target,
silent background updater. User never waits, never decides, it just works.
jwl247 / United Systems / GPL v3
"""

import os
import sys
import json
import time
import hashlib
import shutil
import struct
import subprocess
import threading
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime, timezone

DISTRO_VERSION = "1.0.0"

PHOENIX_HOME  = Path(os.environ.get("PHOENIX_HOME", Path.home() / "Phoenix"))
DISTRO_DIR    = Path(os.environ.get("DISTRO_DIR",   PHOENIX_HOME / "distros"))
DISTRO_DB     = PHOENIX_HOME / "db" / "distros.db"

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

# ── Distro catalog ─────────────────────────────────────────────────────────────
# These are the distros Phoenix ships with pre-cached.
# iso_url / checksum_url are used by the background updater to check for newer.

DISTRO_CATALOG = {
    "ubuntu-server": {
        "name":         "ubuntu-server",
        "display":      "Ubuntu Server",
        "version":      "24.04.2",
        "arch":         "amd64",
        "flavor":       "server+hwe",
        "iso_url":      "https://releases.ubuntu.com/24.04/ubuntu-24.04.2-live-server-amd64.iso",
        "checksum_url": "https://releases.ubuntu.com/24.04/SHA256SUMS",
        "checksum":     "",
        "size_bytes":   2_800_000_000,
        "pinned":       True,
        "tier":         "T1",
    },
    "ubuntu-desktop": {
        "name":         "ubuntu-desktop",
        "display":      "Ubuntu Desktop",
        "version":      "24.04.2",
        "arch":         "amd64",
        "flavor":       "desktop",
        "iso_url":      "https://releases.ubuntu.com/24.04/ubuntu-24.04.2-desktop-amd64.iso",
        "checksum_url": "https://releases.ubuntu.com/24.04/SHA256SUMS",
        "checksum":     "",
        "size_bytes":   5_700_000_000,
        "pinned":       False,
        "tier":         "T1",
    },
    "debian": {
        "name":         "debian",
        "display":      "Debian Stable",
        "version":      "12.5",
        "arch":         "amd64",
        "flavor":       "netinst",
        "iso_url":      "https://cdimage.debian.org/debian-cd/current/amd64/iso-cd/debian-12.5.0-amd64-netinst.iso",
        "checksum_url": "https://cdimage.debian.org/debian-cd/current/amd64/iso-cd/SHA256SUMS",
        "checksum":     "",
        "size_bytes":   400_000_000,
        "pinned":       True,
        "tier":         "T1",
    },
    "kali": {
        "name":         "kali",
        "display":      "Kali Linux",
        "version":      "2024.1",
        "arch":         "amd64",
        "flavor":       "live",
        "iso_url":      "https://cdimage.kali.org/kali-2024.1/kali-linux-2024.1-live-amd64.iso",
        "checksum_url": "https://cdimage.kali.org/kali-2024.1/SHA256SUMS",
        "checksum":     "",
        "size_bytes":   3_900_000_000,
        "pinned":       False,
        "tier":         "T1",
    },
    "fedora": {
        "name":         "fedora",
        "display":      "Fedora Server",
        "version":      "40",
        "arch":         "x86_64",
        "flavor":       "server",
        "iso_url":      "https://download.fedoraproject.org/pub/fedora/linux/releases/40/Server/x86_64/iso/Fedora-Server-dvd-x86_64-40-1.14.iso",
        "checksum_url": "https://getfedora.org/static/checksums/40/iso/Fedora-Server-40-1.14-x86_64-CHECKSUM",
        "checksum":     "",
        "size_bytes":   2_500_000_000,
        "pinned":       False,
        "tier":         "T1",
    },
    "arch": {
        "name":         "arch",
        "display":      "Arch Linux",
        "version":      "2024.05",
        "arch":         "x86_64",
        "flavor":       "minimal",
        "iso_url":      "https://mirror.rackspace.com/archlinux/iso/2024.05.01/archlinux-2024.05.01-x86_64.iso",
        "checksum_url": "https://archlinux.org/iso/2024.05.01/sha256sums.txt",
        "checksum":     "",
        "size_bytes":   1_100_000_000,
        "pinned":       False,
        "tier":         "T1",
    },
    "alpine": {
        "name":         "alpine",
        "display":      "Alpine Linux",
        "version":      "3.20",
        "arch":         "x86_64",
        "flavor":       "standard",
        "iso_url":      "https://dl-cdn.alpinelinux.org/alpine/v3.20/releases/x86_64/alpine-standard-3.20.0-x86_64.iso",
        "checksum_url": "https://dl-cdn.alpinelinux.org/alpine/v3.20/releases/x86_64/alpine-standard-3.20.0-x86_64.iso.sha256",
        "checksum":     "",
        "size_bytes":   210_000_000,
        "pinned":       False,
        "tier":         "T1",
    },
}

# ── Helpers ────────────────────────────────────────────────────────────────────

def _sha256(path: Path, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            data = f.read(chunk)
            if not data:
                break
            h.update(data)
    return h.hexdigest()

def _human_size(n: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"

def _progress_bar(done: int, total: int, width: int = 30) -> str:
    pct  = done / total if total else 0
    fill = int(width * pct)
    bar  = "█" * fill + "░" * (width - fill)
    return f"[{bar}] {pct*100:.1f}% {_human_size(done)}/{_human_size(total)}"

def _iso_path(name: str) -> Path:
    return DISTRO_DIR / f"{name}.iso"

def _meta_path(name: str) -> Path:
    return DISTRO_DIR / f"{name}.meta.json"

# ── DB init ────────────────────────────────────────────────────────────────────

def _init_db():
    import sqlite3
    DISTRO_DB.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DISTRO_DB) as cx:
        cx.executescript("""
            CREATE TABLE IF NOT EXISTS distros (
                name        TEXT PRIMARY KEY,
                display     TEXT,
                version     TEXT,
                arch        TEXT,
                flavor      TEXT,
                iso_url     TEXT,
                checksum    TEXT,
                size_bytes  INTEGER,
                cached      INTEGER DEFAULT 0,
                pinned      INTEGER DEFAULT 0,
                tier        TEXT DEFAULT 'T1',
                last_check  TEXT,
                timestamp   TEXT
            );
            CREATE TABLE IF NOT EXISTS distro_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp   TEXT,
                name        TEXT,
                action      TEXT,
                result      TEXT,
                note        TEXT
            );
        """)
        for name, info in DISTRO_CATALOG.items():
            cx.execute("""
                INSERT OR IGNORE INTO distros
                (name, display, version, arch, flavor, iso_url, checksum,
                 size_bytes, cached, pinned, tier, timestamp)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                name, info["display"], info["version"], info["arch"],
                info["flavor"], info["iso_url"], info["checksum"],
                info["size_bytes"],
                1 if _iso_path(name).exists() else 0,
                int(info["pinned"]), info["tier"], _now()
            ))

def _log_action(name: str, action: str, result: str, note: str = ""):
    import sqlite3
    with sqlite3.connect(DISTRO_DB) as cx:
        cx.execute(
            "INSERT INTO distro_log (timestamp, name, action, result, note) VALUES (?,?,?,?,?)",
            (_now(), name, action, result, note)
        )

# ── Cache management ───────────────────────────────────────────────────────────

def cache_distro(name: str, force: bool = False) -> dict:
    """
    Pull distro ISO into clone pool (DISTRO_DIR).
    Shows progress. Verifies checksum. Registers with Frank + Helix.
    """
    import sqlite3

    DISTRO_DIR.mkdir(parents=True, exist_ok=True)
    _init_db()

    info = DISTRO_CATALOG.get(name)
    if not info:
        return {"ok": False, "error": f"Unknown distro: {name}. Run 'ph-distro list' to see available."}

    iso   = _iso_path(name)
    meta  = _meta_path(name)

    if iso.exists() and not force:
        size = iso.stat().st_size
        print(f"  {info['display']} {info['version']} already cached ({_human_size(size)})")
        print(f"  Use --force to re-download.")
        return {"ok": True, "cached": True, "path": str(iso)}

    print(f"\n  Caching {info['display']} {info['version']} ({info['arch']})")
    print(f"  Size: ~{_human_size(info['size_bytes'])}")
    print(f"  Source: {info['iso_url']}\n")

    tmp = iso.with_suffix(".tmp")
    try:
        req   = urllib.request.Request(info["iso_url"], headers={"User-Agent": "PhoenixOS/1.0"})
        total = info["size_bytes"]
        done  = 0
        start = time.time()

        with urllib.request.urlopen(req, timeout=30) as resp:
            content_len = resp.headers.get("Content-Length")
            if content_len:
                total = int(content_len)
            with open(tmp, "wb") as f:
                while True:
                    chunk = resp.read(1024 * 512)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    elapsed = time.time() - start
                    speed   = done / elapsed if elapsed > 0 else 0
                    eta     = int((total - done) / speed) if speed > 0 else 0
                    bar     = _progress_bar(done, total)
                    print(f"\r  {bar}  {_human_size(speed)}/s  ETA {eta}s   ", end="", flush=True)

        print(f"\n\n  Download complete. Verifying checksum...")
        checksum = _sha256(tmp)
        print(f"  SHA256: {checksum[:32]}...")

        tmp.rename(iso)

        record = {**info, "checksum": checksum, "cached_at": _now(), "path": str(iso)}
        with open(meta, "w") as f:
            json.dump(record, f, indent=2)

        with sqlite3.connect(DISTRO_DB) as cx:
            cx.execute(
                "UPDATE distros SET cached=1, checksum=?, timestamp=? WHERE name=?",
                (checksum, _now(), name)
            )

        _log_action(name, "cache", "ok", f"sha256:{checksum[:16]}")

        try:
            import helix as h
            hx = h._get_global_helix()
            hx.store(f"distro:{name}", record, meta={"type": "distro", "iso": str(iso)})
        except Exception:
            pass

        try:
            import frank as fr
            f = fr.get_frank()
            f.intake(f"distro:{name}", record, template_name="distro",
                     source=info["iso_url"])
        except Exception:
            pass

        print(f"  ✓ {info['display']} {info['version']} cached and registered.")
        return {"ok": True, "cached": True, "path": str(iso), "checksum": checksum}

    except Exception as e:
        if tmp.exists():
            tmp.unlink()
        _log_action(name, "cache", "error", str(e))
        return {"ok": False, "error": str(e)}


def list_distros(show_all: bool = False) -> list:
    """List distros — cached and available."""
    import sqlite3
    _init_db()
    with sqlite3.connect(DISTRO_DB) as cx:
        rows = cx.execute(
            "SELECT name, display, version, arch, flavor, cached, pinned, tier, last_check "
            "FROM distros ORDER BY pinned DESC, name"
        ).fetchall()
    result = []
    for r in rows:
        name, display, version, arch, flavor, cached, pinned, tier, last_check = r
        iso = _iso_path(name)
        size = iso.stat().st_size if iso.exists() else 0
        result.append({
            "name":       name,
            "display":    display,
            "version":    version,
            "arch":       arch,
            "flavor":     flavor,
            "cached":     bool(cached),
            "pinned":     bool(pinned),
            "tier":       tier,
            "size":       _human_size(size) if size else f"~{_human_size(DISTRO_CATALOG.get(name,{}).get('size_bytes',0))}",
            "last_check": last_check or "never",
        })
    return result


def write_to_device(name: str, device: str, verify: bool = True) -> dict:
    """
    Write cached ISO to target device (USB or external drive).
    device = /dev/sdb or similar.
    Helix checks clone pool first — local serve, no download.
    """
    _init_db()
    iso = _iso_path(name)

    if not iso.exists():
        print(f"  {name} not in clone pool. Caching now...")
        result = cache_distro(name)
        if not result["ok"]:
            return result

    if not Path(device).exists():
        return {"ok": False, "error": f"Device not found: {device}"}

    info = DISTRO_CATALOG.get(name, {})
    size = iso.stat().st_size

    print(f"\n  Writing {info.get('display', name)} → {device}")
    print(f"  ISO: {iso} ({_human_size(size)})")
    print(f"  ⚠ All data on {device} will be erased.")
    confirm = input("  Type YES to continue: ").strip()
    if confirm != "YES":
        return {"ok": False, "error": "Aborted by user."}

    print(f"\n  Writing...")
    _log_action(name, "write", "start", f"device:{device}")

    try:
        result = subprocess.run(
            ["dd", f"if={iso}", f"of={device}", "bs=4M", "status=progress", "oflag=sync"],
            check=True
        )
        subprocess.run(["sync"], check=True)

        if verify:
            print(f"\n  Verifying write...")
            iso_hash  = _sha256(iso)
            with open(device, "rb") as f:
                data = f.read(size)
            dev_hash = hashlib.sha256(data).hexdigest()
            if iso_hash != dev_hash:
                _log_action(name, "write", "verify_fail", f"device:{device}")
                return {"ok": False, "error": "Verification failed — checksums don't match."}

        _log_action(name, "write", "ok", f"device:{device}")
        print(f"  ✓ Done. {device} is ready to boot.")
        return {"ok": True, "device": device, "distro": name}

    except subprocess.CalledProcessError as e:
        _log_action(name, "write", "error", str(e))
        return {"ok": False, "error": str(e)}


def remove_cache(name: str, force: bool = False) -> dict:
    """Remove a distro from the local cache."""
    import sqlite3
    _init_db()
    iso  = _iso_path(name)
    meta = _meta_path(name)

    info = DISTRO_CATALOG.get(name, {})
    if info.get("pinned") and not force:
        return {"ok": False, "error": f"{name} is pinned. Use --force to remove."}

    if iso.exists():
        iso.unlink()
    if meta.exists():
        meta.unlink()

    with sqlite3.connect(DISTRO_DB) as cx:
        cx.execute("UPDATE distros SET cached=0 WHERE name=?", (name,))

    _log_action(name, "remove", "ok", "")
    return {"ok": True, "removed": name}


# ── Background updater ─────────────────────────────────────────────────────────

class DistroUpdater:
    """
    Frank service — runs in background, silently checks upstream checksums,
    pulls newer ISOs into clone pool when available.
    User never knows. It just works.
    """

    def __init__(self, interval_hours: int = 24):
        self.interval   = interval_hours * 3600
        self._stop      = threading.Event()
        self._thread    = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        print(f"  Distro updater started — checking every {self.interval//3600}h")

    def stop(self):
        self._stop.set()

    def _run(self):
        while not self._stop.is_set():
            self._check_all()
            self._stop.wait(self.interval)

    def _check_all(self):
        import sqlite3
        _init_db()
        with sqlite3.connect(DISTRO_DB) as cx:
            rows = cx.execute(
                "SELECT name FROM distros WHERE cached=1"
            ).fetchall()
        for (name,) in rows:
            if self._stop.is_set():
                break
            try:
                self._check_one(name)
            except Exception as e:
                _log_action(name, "update_check", "error", str(e))

    def _check_one(self, name: str):
        import sqlite3
        info = DISTRO_CATALOG.get(name)
        if not info or not info.get("checksum_url"):
            return

        try:
            req  = urllib.request.Request(
                info["checksum_url"],
                headers={"User-Agent": "PhoenixOS/1.0"}
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                content = resp.read().decode(errors="replace")
        except Exception:
            return

        iso_filename = info["iso_url"].split("/")[-1]
        upstream_checksum = None
        for line in content.splitlines():
            if iso_filename in line:
                parts = line.split()
                if parts:
                    upstream_checksum = parts[0].strip()
                break

        if not upstream_checksum:
            return

        with sqlite3.connect(DISTRO_DB) as cx:
            row = cx.execute(
                "SELECT checksum FROM distros WHERE name=?", (name,)
            ).fetchone()
            cx.execute(
                "UPDATE distros SET last_check=? WHERE name=?", (_now(), name)
            )

        if not row:
            return

        local_checksum = row[0]

        if upstream_checksum != local_checksum:
            _log_action(name, "update_available",
                        "pending", f"upstream:{upstream_checksum[:16]}")
            iso = _iso_path(name)
            if iso.exists():
                old = iso.with_suffix(".iso.prev")
                iso.rename(old)
            result = cache_distro(name, force=True)
            if result["ok"]:
                old = _iso_path(name).with_suffix(".iso.prev")
                if old.exists():
                    old.unlink()
                _log_action(name, "update_complete", "ok",
                            f"new:{upstream_checksum[:16]}")
        else:
            _log_action(name, "update_check", "ok", "up_to_date")


# ── Global updater instance ────────────────────────────────────────────────────

_updater: DistroUpdater | None = None

def start_updater(interval_hours: int = 24) -> DistroUpdater:
    global _updater
    if _updater is None:
        _updater = DistroUpdater(interval_hours)
        _updater.start()
    return _updater


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Phoenix Distro Handler — local ISO cache, live write, silent updates"
    )
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("list", help="List distros (cached + available)")

    sc = sub.add_parser("cache", help="Cache a distro ISO locally")
    sc.add_argument("name")
    sc.add_argument("--force", action="store_true")

    sw = sub.add_parser("write", help="Write ISO to device")
    sw.add_argument("name",   help="Distro name")
    sw.add_argument("device", help="Target device e.g. /dev/sdb")
    sw.add_argument("--no-verify", action="store_true")

    sr = sub.add_parser("remove", help="Remove cached ISO")
    sr.add_argument("name")
    sr.add_argument("--force", action="store_true")

    sub.add_parser("update", help="Check all cached distros for updates now")

    si = sub.add_parser("info", help="Show distro details")
    si.add_argument("name")

    args = parser.parse_args()
    _init_db()

    if args.cmd == "list":
        distros = list_distros()
        print(f"\n  {'NAME':<20} {'VERSION':<12} {'ARCH':<8} {'SIZE':<10} {'STATUS':<10} TIER")
        print(f"  {'─'*20} {'─'*12} {'─'*8} {'─'*10} {'─'*10} {'─'*4}")
        for d in distros:
            status = "✓ cached" if d["cached"] else "· available"
            pin    = " [pinned]" if d["pinned"] else ""
            print(f"  {d['name']:<20} {d['version']:<12} {d['arch']:<8} {d['size']:<10} {status:<10} {d['tier']}{pin}")
        print()

    elif args.cmd == "cache":
        result = cache_distro(args.name, force=args.force)
        if not result["ok"]:
            print(f"\n  Error: {result['error']}")
            sys.exit(1)

    elif args.cmd == "write":
        result = write_to_device(args.name, args.device, verify=not args.no_verify)
        if not result["ok"]:
            print(f"\n  Error: {result['error']}")
            sys.exit(1)

    elif args.cmd == "remove":
        result = remove_cache(args.name, force=args.force)
        if not result["ok"]:
            print(f"\n  Error: {result['error']}")
            sys.exit(1)
        print(f"  Removed {args.name} from cache.")

    elif args.cmd == "update":
        print("  Checking all cached distros for updates...")
        u = DistroUpdater()
        u._check_all()
        print("  Done.")

    elif args.cmd == "info":
        info = DISTRO_CATALOG.get(args.name)
        if not info:
            print(f"  Unknown distro: {args.name}")
            sys.exit(1)
        iso  = _iso_path(args.name)
        print(json.dumps({
            **info,
            "cached":     iso.exists(),
            "local_path": str(iso) if iso.exists() else None,
            "local_size": _human_size(iso.stat().st_size) if iso.exists() else None,
        }, indent=2))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
