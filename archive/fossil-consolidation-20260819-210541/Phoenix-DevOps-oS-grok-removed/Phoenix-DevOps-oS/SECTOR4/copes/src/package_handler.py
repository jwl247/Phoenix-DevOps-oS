#!/usr/bin/env python3
# =============================================================================
# package_handler.py — Phoenix DevOps OS / COPES
# Package Handler: intake authority. Helix's face to the outside world.
# Talks to the clone pool (which IS Helix). Knows where everything is.
# Pulls from Phoenix DB + 10 distros + personal DB.
# =============================================================================
# Author:  jwl247 / Phoenix DevOps LLC
# License: GPL v3
# =============================================================================

import os
import json
import hashlib
import sqlite3
import urllib.request
import urllib.error
import threading
import subprocess
from pathlib import Path
from datetime import datetime, timezone

def _now(): return datetime.now(timezone.utc).isoformat()

PH_VERSION = "2.0.0"

# ── Env ───────────────────────────────────────────────────────────────────────

PHOENIX_HOME  = Path(os.environ.get("PHOENIX_HOME", Path.home() / "Phoenix"))
PH_DB         = Path(os.environ.get("PH_DB",        PHOENIX_HOME / "db" / "packages.db"))
D1_WORKER_URL = os.environ.get("PHOENIX_WORKER_URL", "")
PHOENIX_AUTH  = os.environ.get("PHOENIX_AUTH",       "")

# ── Known distro backends ─────────────────────────────────────────────────────

BACKENDS = {
    "apt":     {"platforms": ["debian", "ubuntu", "kali"], "cmd": "apt-get"},
    "dnf":     {"platforms": ["rhel", "fedora"],           "cmd": "dnf"},
    "pacman":  {"platforms": ["arch"],                     "cmd": "pacman"},
    "brew":    {"platforms": ["macos"],                    "cmd": "brew"},
    "apk":     {"platforms": ["alpine"],                   "cmd": "apk"},
    "winget":  {"platforms": ["windows"],                  "cmd": "winget"},
    "pip":     {"platforms": ["all"],                      "cmd": "pip"},
    "npm":     {"platforms": ["all"],                      "cmd": "npm"},
    "snap":    {"platforms": ["ubuntu"],                   "cmd": "snap"},
    "flatpak": {"platforms": ["all"],                      "cmd": "flatpak"},
}

# ── QR state ──────────────────────────────────────────────────────────────────

QR_STATES   = {"active": "white", "deprecated": "grey", "retired": "black"}
TIER_COLORS = {"T1": "primary", "T2": "secondary", "T3": "tertiary", "T4": "tertiary"}

# ── File types to skip in directory intake ────────────────────────────────────

SKIP_EXTENSIONS = {
    ".pyc", ".pyo", ".pyd", ".so", ".o", ".a",
    ".git", ".DS_Store", ".swp", ".tmp", ".lock",
}

SKIP_DIRS = {
    "__pycache__", ".git", ".venv", "venv", "node_modules",
    "clonepool", ".mypy_cache", ".pytest_cache",
}


# ── Package record ────────────────────────────────────────────────────────────

class PackageRecord:
    def __init__(self, name: str, version: str = None, backend: str = None,
                 tav: str = None, tier: str = "T1", state: str = "active",
                 meta: dict = None):
        self.name        = name
        self.version     = version or "unknown"
        self.backend     = backend or "unknown"
        self.tav         = tav or self._gen_tav(name)
        self.fingerprint = hashlib.sha3_512(name.encode()).hexdigest()
        self.tier        = tier
        self.state       = state
        self.meta        = meta or {}
        self.timestamp   = _now()

    def _gen_tav(self, name: str) -> str:
        """SHA3-512 -> first 8 bytes -> base58 (max 11 chars). No external deps."""
        digest = hashlib.sha3_512(name.encode()).digest()[:8]
        alpha  = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
        n      = int.from_bytes(digest, 'big')
        result = ''
        while n:
            result = alpha[n % 58] + result
            n //= 58
        return result or '1'

    def header_qr(self) -> str:
        color = QR_STATES.get(self.state, "white")
        return f"USYS:{self.tav}:HEADER:{color}"

    def footer_qr(self) -> str:
        color = TIER_COLORS.get(self.tier, "primary")
        return f"USYS:{self.tav}:FOOTER:{self.fingerprint[:16]}:{color}"

    def to_dict(self) -> dict:
        return {
            "name":        self.name,
            "version":     self.version,
            "backend":     self.backend,
            "tav":         self.tav,
            "fingerprint": self.fingerprint,
            "tier":        self.tier,
            "state":       self.state,
            "header_qr":   self.header_qr(),
            "footer_qr":   self.footer_qr(),
            "timestamp":   self.timestamp,
            "meta":        self.meta,
        }


# ── Package Handler ───────────────────────────────────────────────────────────

class PackageHandler:
    """
    Intake authority. Helix's face to the outside world.
    Talks to the clone pool (Helix). Knows where everything is.
    Pulls from Phoenix DB + 10 distros + personal DB.
    Frank and Helix use Package Handler -- not the other way around.
    """

    def __init__(self):
        PH_DB.parent.mkdir(parents=True, exist_ok=True)
        self._lock  = threading.RLock()
        self._helix = None
        self._init_db()
        self._acquaint()

    # ── DB ────────────────────────────────────────────────────────────────────

    def _init_db(self):
        with sqlite3.connect(PH_DB) as cx:
            cx.executescript("""
                CREATE TABLE IF NOT EXISTS packages (
                    tav       TEXT PRIMARY KEY,
                    name      TEXT NOT NULL,
                    version   TEXT,
                    backend   TEXT,
                    tier      TEXT DEFAULT 'T1',
                    state     TEXT DEFAULT 'active',
                    timestamp TEXT,
                    meta      TEXT
                );
                CREATE TABLE IF NOT EXISTS catalog (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    tav       TEXT NOT NULL,
                    action    TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    note      TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_pkg_name  ON packages(name);
                CREATE INDEX IF NOT EXISTS idx_pkg_state ON packages(state);
            """)

    # ── Audit log (PH local) ─────────────────────────────────────────────────

    def _log(self, action: str, subject: str, meta: dict = None):
        """Local catalog log -- not Frank's immutable audit, just PH tracking."""
        with self._lock:
            with sqlite3.connect(PH_DB) as cx:
                cx.execute(
                    "INSERT INTO catalog (tav, action, timestamp, note) VALUES (?,?,?,?)",
                    (subject, action, _now(), json.dumps(meta or {}))
                )

    # ── Acquaint -- learn the clone pool ──────────────────────────────────────

    def _acquaint(self):
        """Acquaint with where everything is in the clone pool."""
        helix = self._get_helix()
        if not helix:
            return
        try:
            items = helix.list_all()
            with sqlite3.connect(PH_DB) as cx:
                for item in items:
                    cx.execute(
                        "INSERT OR IGNORE INTO packages "
                        "(tav, name, tier, state, timestamp, meta) VALUES (?,?,?,?,?,?)",
                        (item["tav"], item["name"], item.get("tier", "T1"),
                         item.get("state", "active"), _now(), "{}")
                    )
        except Exception:
            pass

    # ── Lazy Helix loader ─────────────────────────────────────────────────────

    def _get_helix(self):
        if self._helix is None:
            try:
                import helix as helix_mod
                self._helix = helix_mod._get_global_helix()
            except Exception:
                pass
        return self._helix

    # ── Install ───────────────────────────────────────────────────────────────

    def install(self, name: str, backend: str = None,
                version: str = None, target: str = None) -> dict:
        helix = self._get_helix()
        b     = backend or self._detect_backend(name, target)
        cmd   = self._build_install_cmd(name, b, version, target)
        rec   = PackageRecord(name, version, b)

        self._register(rec)

        if helix:
            try:
                helix.store(f"pkg:{name}", rec.to_dict(), meta={"cmd": cmd})
            except Exception:
                pass

        try:
            result  = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            executed = result.returncode == 0
            stdout   = result.stdout.strip()
            stderr   = result.stderr.strip()
        except Exception as e:
            executed = False
            stdout   = ""
            stderr   = str(e)

        d1_result = self._d1_push("install", rec.to_dict())

        return {
            "ok":      True,
            "name":    name,
            "backend": b,
            "version": version or "latest",
            "cmd":     cmd,
            "tav":     rec.tav,
            "d1":      d1_result,
            "executed": executed,
            "stdout":   stdout,
            "stderr":   stderr,
        }

    def _build_install_cmd(self, name: str, backend: str,
                           version: str = None, target: str = None) -> str:
        ver_str = f"=={version}" if version else ""
        cmds = {
            "apt":     f"sudo apt-get install -y {name}",
            "dnf":     f"sudo dnf install -y {name}",
            "pacman":  f"sudo pacman -S --noconfirm {name}",
            "brew":    f"brew install {name}",
            "apk":     f"sudo apk add {name}",
            "winget":  f"winget install {name}",
            "pip":     f"pip install {name}{ver_str}",
            "npm":     f"npm install -g {name}",
            "snap":    f"sudo snap install {name}",
            "flatpak": f"flatpak install -y {name}",
        }
        if backend in cmds:
            return cmds[backend]
        helix = self._get_helix()
        if helix:
            try:
                return helix.egress_pkg(
                    f"{name}=={version}" if version else name, target
                )
            except Exception:
                pass
        return f"# install {name}"

    def _detect_backend(self, name: str, target: str = None) -> str:
        helix = self._get_helix()
        if helix:
            try:
                platform = target or helix.quad.current
                for backend, info in BACKENDS.items():
                    if platform in info["platforms"] or "all" in info["platforms"]:
                        return backend
            except Exception:
                pass
        return "apt"

    # ── Intake -- single file ─────────────────────────────────────────────────

    def intake(self, path: str, notes: str = None) -> dict:
        """
        Intake a file directly into the clone pool via Helix.
        Generates TAV, writes sidecar, stores in Helix, logs audit trail.
        This is the file intake path -- package install goes through install().
        """
        p = Path(path).resolve()
        if not p.exists():
            return {"ok": False, "error": f"File not found: {path}"}
        if not p.is_file():
            return {"ok": False, "error": f"Not a file: {path} (use intake-dir for directories)"}

        name = p.name
        rec  = PackageRecord(name)

        helix = self._get_helix()
        if not helix:
            return {"ok": False, "error": "Helix offline"}

        data = {
            "path":  str(p),
            "name":  name,
            "tav":   rec.tav,
            "size":  p.stat().st_size,
            "notes": notes or "",
        }

        helix.store(name, data, meta={"source": str(p), "notes": notes or ""})
        self._register(rec)
        self._log("ph.intake", rec.tav, {
            "name": name,
            "path": str(p),
            "size": p.stat().st_size,
        })

        return {
            "ok":          True,
            "name":        name,
            "tav":         rec.tav,
            "path":        str(p),
            "fingerprint": rec.fingerprint,
            "size":        p.stat().st_size,
        }

    # ── Intake -- package by name ─────────────────────────────────────────────

    def intake_package(self, name: str, version: str = None,
                       backend: str = None, notes: str = None) -> dict:
        """
        Intake a package by name into the clone pool.
        Does NOT install it -- intake only. Records TAV, registers in DB,
        stores metadata in Helix, logs audit trail.
        Use install() to actually execute the install command.

        intake-package numpy
        intake-package requests --version 2.31.0 --backend pip
        """
        b   = backend or self._detect_backend(name)
        rec = PackageRecord(name, version, b, meta={"notes": notes or ""})

        helix = self._get_helix()
        if not helix:
            return {"ok": False, "error": "Helix offline"}

        # Check if already in clone pool
        already = False
        try:
            already = helix.exists(f"pkg:{name}")
        except Exception:
            pass

        data = {
            "name":    name,
            "version": version or "unknown",
            "backend": b,
            "tav":     rec.tav,
            "notes":   notes or "",
            "type":    "package",
        }

        helix.store(f"pkg:{name}", data,
                    meta={"source": "intake-package", "notes": notes or ""})
        self._register(rec)
        self._log("ph.intake_package", rec.tav, {
            "name":    name,
            "version": version or "unknown",
            "backend": b,
        })

        d1_result = self._d1_push("intake_package", rec.to_dict())

        return {
            "ok":          True,
            "name":        name,
            "version":     version or "unknown",
            "backend":     b,
            "tav":         rec.tav,
            "fingerprint": rec.fingerprint,
            "header_qr":   rec.header_qr(),
            "footer_qr":   rec.footer_qr(),
            "already_in_pool": already,
            "d1":          d1_result,
        }

    # ── Intake -- directory ───────────────────────────────────────────────────

    def intake_dir(self, path: str, recursive: bool = True,
                   notes: str = None, dry_run: bool = False) -> dict:
        """
        Walk a directory and intake every file into the clone pool.
        Skips: __pycache__, .git, .venv, node_modules, clonepool, .pyc, .o etc.
        Returns a full summary: ok / skipped / failed counts + per-file results.

        intake-dir ~/Phoenix/src
        intake-dir ~/docs --no-recursive
        intake-dir ~/incoming --dry-run
        """
        d = Path(path).resolve()
        if not d.exists():
            return {"ok": False, "error": f"Directory not found: {path}"}
        if not d.is_dir():
            return {"ok": False, "error": f"Not a directory: {path} (use intake for files)"}

        results  = []
        ok_count = skipped = failed = 0

        # Walk — recursive or flat
        if recursive:
            file_iter = d.rglob("*")
        else:
            file_iter = d.glob("*")

        for item in sorted(file_iter):
            # Skip directories themselves
            if item.is_dir():
                continue

            # Skip unwanted dirs anywhere in path
            if any(part in SKIP_DIRS for part in item.parts):
                skipped += 1
                results.append({
                    "file":   str(item),
                    "status": "skipped",
                    "reason": "skip_dir",
                })
                continue

            # Skip unwanted extensions
            if item.suffix.lower() in SKIP_EXTENSIONS:
                skipped += 1
                results.append({
                    "file":   str(item),
                    "status": "skipped",
                    "reason": f"skip_ext:{item.suffix}",
                })
                continue

            if dry_run:
                results.append({
                    "file":   str(item),
                    "status": "dry_run",
                    "name":   item.name,
                })
                ok_count += 1
                continue

            # Intake the file
            result = self.intake(str(item), notes=notes)
            if result.get("ok"):
                ok_count += 1
                results.append({
                    "file":   str(item),
                    "status": "ok",
                    "tav":    result["tav"],
                    "size":   result["size"],
                })
            else:
                failed += 1
                results.append({
                    "file":   str(item),
                    "status": "failed",
                    "error":  result.get("error", "unknown"),
                })

        self._log("ph.intake_dir", path, {
            "path":      str(d),
            "recursive": recursive,
            "ok":        ok_count,
            "skipped":   skipped,
            "failed":    failed,
            "dry_run":   dry_run,
        })

        return {
            "ok":        True,
            "directory": str(d),
            "recursive": recursive,
            "dry_run":   dry_run,
            "total":     ok_count + skipped + failed,
            "ingested":  ok_count,
            "skipped":   skipped,
            "failed":    failed,
            "results":   results,
        }

    # ── Search ────────────────────────────────────────────────────────────────

    def search(self, query: str) -> list:
        with sqlite3.connect(PH_DB) as cx:
            rows = cx.execute(
                "SELECT name, version, backend, tav, state, tier FROM packages "
                "WHERE name LIKE ? OR meta LIKE ? ORDER BY name LIMIT 50",
                (f"%{query}%", f"%{query}%")
            ).fetchall()
        helix   = self._get_helix()
        results = []
        for name, version, backend, tav, state, tier in rows:
            in_pool = False
            if helix:
                try:
                    in_pool = helix.exists(f"pkg:{name}")
                except Exception:
                    pass
            results.append({
                "name": name, "version": version, "backend": backend,
                "tav": tav, "state": state, "tier": tier,
                "in_clone_pool": in_pool,
            })
        return results

    # ── Info ──────────────────────────────────────────────────────────────────

    def info(self, name: str) -> dict | None:
        with sqlite3.connect(PH_DB) as cx:
            row = cx.execute(
                "SELECT name, version, backend, tav, state, tier, timestamp, meta "
                "FROM packages WHERE name=?", (name,)
            ).fetchone()
        if not row:
            return None
        rec = PackageRecord(row[0], row[1], row[2], row[3], row[5], row[4])
        return {**rec.to_dict(), "timestamp": row[6]}

    # ── List ──────────────────────────────────────────────────────────────────

    def list_packages(self, state: str = "active", tier: str = None) -> list:
        query  = "SELECT name, version, backend, tav, state, tier FROM packages WHERE state=?"
        params = [state]
        if tier:
            query  += " AND tier=?"
            params.append(tier)
        query += " ORDER BY name"
        with sqlite3.connect(PH_DB) as cx:
            rows = cx.execute(query, params).fetchall()
        return [{"name": r[0], "version": r[1], "backend": r[2],
                 "tav": r[3], "state": r[4], "tier": r[5]} for r in rows]

    # ── Register ──────────────────────────────────────────────────────────────

    def _register(self, rec: PackageRecord):
        with self._lock:
            with sqlite3.connect(PH_DB) as cx:
                existing = cx.execute(
                    "SELECT tav FROM packages WHERE tav=?", (rec.tav,)
                ).fetchone()
                if existing:
                    cx.execute(
                        "UPDATE packages SET version=?, state='active', timestamp=? WHERE tav=?",
                        (rec.version, rec.timestamp, rec.tav)
                    )
                else:
                    cx.execute(
                        "INSERT INTO packages "
                        "(tav, name, version, backend, tier, state, timestamp, meta) "
                        "VALUES (?,?,?,?,?,?,?,?)",
                        (rec.tav, rec.name, rec.version, rec.backend,
                         rec.tier, rec.state, rec.timestamp, json.dumps(rec.meta))
                    )
                cx.execute(
                    "INSERT INTO catalog (tav, action, timestamp) VALUES (?,?,?)",
                    (rec.tav, "register", rec.timestamp)
                )

    # ── D1 sync ───────────────────────────────────────────────────────────────

    def _d1_push(self, action: str, data: dict) -> dict:
        if not D1_WORKER_URL or not PHOENIX_AUTH:
            return {"ok": False, "reason": "D1 not configured"}
        try:
            payload = json.dumps({
                "action":    action,
                "timestamp": _now(),
                "hex_id":    data.get("fingerprint", ""),
                "b58":       data.get("tav", ""),
                "name":      data.get("name", ""),
                "data":      data,
            }).encode()
            req = urllib.request.Request(
                f"{D1_WORKER_URL}/clonepool",
                data=payload,
                method="POST",
                headers={
                    "Content-Type":   "application/json",
                    "X-Phoenix-Auth": PHOENIX_AUTH,
                    "User-Agent":     "CoPES-PackageHandler/2.0",
                }
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                return {"ok": True, "status": resp.status}
        except urllib.error.URLError as e:
            return {"ok": False, "error": str(e)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def d1_sync(self) -> dict:
        packages = self.list_packages()
        results  = []
        for pkg in packages:
            r = self._d1_push("sync", pkg)
            results.append({"name": pkg["name"], "d1": r})
        return {"ok": True, "synced": len(results), "results": results}

    # ── Glossary ──────────────────────────────────────────────────────────────

    def glossary(self) -> dict:
        packages = self.list_packages()
        helix    = self._get_helix()
        pool     = []
        if helix:
            try:
                pool = helix.list_all()
            except Exception:
                pass
        return {
            "packages":   len(packages),
            "clone_pool": len(pool),
            "toc":        [p["name"] for p in packages],
            "pool_index": [i["name"] for i in pool],
            "generated":  _now(),
        }

    # ── Full status ───────────────────────────────────────────────────────────

    def full_status(self) -> dict:
        helix = self._get_helix()
        with sqlite3.connect(PH_DB) as cx:
            total  = cx.execute("SELECT COUNT(*) FROM packages").fetchone()[0]
            active = cx.execute(
                "SELECT COUNT(*) FROM packages WHERE state='active'"
            ).fetchone()[0]
        return {
            "ph_version":      PH_VERSION,
            "packages_total":  total,
            "packages_active": active,
            "helix_online":    helix is not None,
            "helix_stats":     helix.stats() if helix else None,
            "d1_configured":   bool(D1_WORKER_URL and PHOENIX_AUTH),
            "worker_url":      D1_WORKER_URL or "not set",
        }

    # ── Print status ──────────────────────────────────────────────────────────

    def print_status(self):
        s = self.full_status()
        print("")
        print("  ╔══════════════════════════════════════╗")
        print("  ║       PACKAGE HANDLER — COPES        ║")
        print("  ╚══════════════════════════════════════╝")
        print(f"  Version    : {s['ph_version']}")
        print(f"  DB         : {PH_DB}")
        print(f"  Packages   : {s['packages_total']} total / {s['packages_active']} active")
        print(f"  Helix      : {'online' if s['helix_online'] else 'offline'}")
        print(f"  D1         : {'configured' if s['d1_configured'] else 'not configured'}")
        print(f"  Worker     : {s['worker_url']}")
        print("")


# ── Global instance ───────────────────────────────────────────────────────────

_ph: PackageHandler | None = None

def get_ph() -> PackageHandler:
    global _ph
    if _ph is None:
        _ph = PackageHandler()
    return _ph


# ── CLI entry points (wired as globals in pyproject.toml) ─────────────────────

def intake_package_main():
    """
    Global entry point: intake-package
    Usage: intake-package <name> [--version X] [--backend Y] [--notes Z]
    """
    import argparse
    parser = argparse.ArgumentParser(
        prog="intake-package",
        description="Intake a package by name into the CoPES clone pool (no install)."
    )
    parser.add_argument("name",              help="Package name")
    parser.add_argument("--version",         default=None, help="Version (optional)")
    parser.add_argument("--backend",         default=None, help="Backend: pip/apt/npm/etc")
    parser.add_argument("--notes",           default="",   help="Notes")
    args = parser.parse_args()
    ph   = get_ph()
    result = ph.intake_package(args.name, args.version, args.backend, args.notes)
    print(json.dumps(result, indent=2))


def intake_dir_main():
    """
    Global entry point: intake-dir
    Usage: intake-dir <path> [--no-recursive] [--notes Z] [--dry-run]
    """
    import argparse
    parser = argparse.ArgumentParser(
        prog="intake-dir",
        description="Walk a directory and intake every file into the CoPES clone pool."
    )
    parser.add_argument("path",              help="Directory path")
    parser.add_argument("--no-recursive",    action="store_true",
                        help="Flat scan only (no subdirectories)")
    parser.add_argument("--notes",           default="",   help="Notes applied to all files")
    parser.add_argument("--dry-run",         action="store_true",
                        help="Show what would be ingested without storing anything")
    parser.add_argument("--summary",         action="store_true",
                        help="Print summary only (no per-file detail)")
    args = parser.parse_args()
    ph   = get_ph()

    result = ph.intake_dir(
        args.path,
        recursive=not args.no_recursive,
        notes=args.notes,
        dry_run=args.dry_run,
    )

    if args.summary:
        print(f"\n[intake-dir] {result['directory']}")
        print(f"  Total   : {result['total']}")
        print(f"  Ingested: {result['ingested']}")
        print(f"  Skipped : {result['skipped']}")
        print(f"  Failed  : {result['failed']}")
        if result['dry_run']:
            print("  (dry run — nothing stored)")
        print()
    else:
        print(json.dumps(result, indent=2))


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Phoenix Package Handler — COPES")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("status",   help="Full status")
    sub.add_parser("glossary", help="TOC and index of clone pool")
    sub.add_parser("sync",     help="Sync catalog to D1")
    sub.add_parser("acquaint", help="Re-acquaint with clone pool")

    si = sub.add_parser("install", help="Install a package")
    si.add_argument("name")
    si.add_argument("--backend", default=None)
    si.add_argument("--version", default=None)
    si.add_argument("--target",  default=None)

    ss = sub.add_parser("search", help="Search packages")
    ss.add_argument("query")

    sp = sub.add_parser("info", help="Package info")
    sp.add_argument("name")

    sl = sub.add_parser("list", help="List packages")
    sl.add_argument("--state", default="active")
    sl.add_argument("--tier",  default=None)

    # intake -- file
    si2 = sub.add_parser("intake", help="Intake a file into the clone pool")
    si2.add_argument("path")
    si2.add_argument("--notes", default="")

    # intake-package -- package by name
    sip = sub.add_parser("intake-package",
                         help="Intake a package by name (no install)")
    sip.add_argument("name")
    sip.add_argument("--version", default=None)
    sip.add_argument("--backend", default=None)
    sip.add_argument("--notes",   default="")

    # intake-dir -- whole directory
    sid = sub.add_parser("intake-dir",
                         help="Intake all files in a directory")
    sid.add_argument("path")
    sid.add_argument("--no-recursive", action="store_true")
    sid.add_argument("--notes",        default="")
    sid.add_argument("--dry-run",      action="store_true")
    sid.add_argument("--summary",      action="store_true")

    args = parser.parse_args()
    ph   = get_ph()

    if args.cmd == "status":
        ph.print_status()
    elif args.cmd == "glossary":
        print(json.dumps(ph.glossary(), indent=2))
    elif args.cmd == "sync":
        print(json.dumps(ph.d1_sync(), indent=2))
    elif args.cmd == "acquaint":
        ph._acquaint()
        print("[ph] acquainted with clone pool.")
    elif args.cmd == "install":
        print(json.dumps(
            ph.install(args.name, args.backend, args.version, args.target), indent=2))
    elif args.cmd == "search":
        print(json.dumps(ph.search(args.query), indent=2))
    elif args.cmd == "info":
        info = ph.info(args.name)
        print(json.dumps(info, indent=2) if info else f"Not found: {args.name}")
    elif args.cmd == "list":
        pkgs = ph.list_packages(args.state, args.tier)
        if pkgs:
            for p in pkgs:
                print(f"  {p['name']:30} {(p['version'] or 'unknown'):15} "
                      f"{(p['backend'] or ''):10} [{p['state']}]")
        else:
            print("[ph] no packages found.")
    elif args.cmd == "intake":
        print(json.dumps(ph.intake(args.path, args.notes), indent=2))
    elif args.cmd == "intake-package":
        print(json.dumps(
            ph.intake_package(args.name, args.version, args.backend, args.notes),
            indent=2))
    elif args.cmd == "intake-dir":
        result = ph.intake_dir(
            args.path,
            recursive=not args.no_recursive,
            notes=args.notes,
            dry_run=args.dry_run,
        )
        if args.summary:
            print(f"\n[intake-dir] {result['directory']}")
            print(f"  Total   : {result['total']}")
            print(f"  Ingested: {result['ingested']}")
            print(f"  Skipped : {result['skipped']}")
            print(f"  Failed  : {result['failed']}")
            if result['dry_run']:
                print("  (dry run -- nothing stored)")
            print()
        else:
            print(json.dumps(result, indent=2))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
