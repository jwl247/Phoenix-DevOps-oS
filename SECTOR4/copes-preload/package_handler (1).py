#!/usr/bin/env python3
"""
package_handler.py — Phoenix DevOps OS
Package Handler: Helix's face to the outside world.
Talks to the clone pool (which IS Helix).
Acquaints herself with where everything is.
jwl247 / United Systems / GPL v3
"""

import os
import json
import hashlib
import sqlite3
import urllib.request
import urllib.error
import urllib.parse
import threading
import time
from pathlib import Path
from datetime import datetime, timezone

def _now(): return datetime.now(timezone.utc).isoformat()
from typing import Any

PH_VERSION = "1.0.0"

# ── Env ───────────────────────────────────────────────────────────────────────

PHOENIX_HOME   = Path(os.environ.get("PHOENIX_HOME",       Path.home() / "Phoenix"))
PH_DB          = Path(os.environ.get("PH_DB",              PHOENIX_HOME / "db" / "packages.db"))
D1_WORKER_URL  = os.environ.get("PHOENIX_WORKER_URL",      "")
PHOENIX_AUTH   = os.environ.get("PHOENIX_AUTH",            "")

# ── Known distro backends ─────────────────────────────────────────────────────

BACKENDS = {
    "apt":    {"platforms": ["debian","ubuntu","kali"], "cmd": "apt-get"},
    "dnf":    {"platforms": ["rhel","fedora"],          "cmd": "dnf"},
    "pacman": {"platforms": ["arch"],                   "cmd": "pacman"},
    "brew":   {"platforms": ["macos"],                  "cmd": "brew"},
    "apk":    {"platforms": ["alpine"],                 "cmd": "apk"},
    "winget": {"platforms": ["windows"],                "cmd": "winget"},
    "pip":    {"platforms": ["all"],                    "cmd": "pip"},
    "npm":    {"platforms": ["all"],                    "cmd": "npm"},
    "snap":   {"platforms": ["ubuntu"],                 "cmd": "snap"},
    "flatpak":{"platforms": ["all"],                    "cmd": "flatpak"},
}

# ── QR state ──────────────────────────────────────────────────────────────────

QR_STATES = {
    "active":      "white",
    "deprecated":  "grey",
    "retired":     "black",
}

TIER_COLORS = {
    "T1": "primary",
    "T2": "secondary",
    "T3": "tertiary",
    "T4": "tertiary",
}

# ── Package record ────────────────────────────────────────────────────────────

class PackageRecord:
    def __init__(self, name: str, version: str = None, backend: str = None,
                 tav: str = None, tier: str = "T1", state: str = "active",
                 meta: dict = None):
        self.name     = name
        self.version  = version or "unknown"
        self.backend  = backend or "unknown"
        self.tav      = tav or self._gen_tav(name)
        self.tier     = tier
        self.state    = state
        self.meta     = meta or {}
        self.timestamp= _now()

    def _gen_tav(self, name: str) -> str:
        import base58
        raw = hashlib.sha3_512(name.encode()).digest()[:8]
        return base58.b58encode(raw).decode()

    def header_qr(self) -> str:
        color = QR_STATES.get(self.state, "white")
        return f"USYS:{self.tav}:HEADER:{color}"

    def footer_qr(self) -> str:
        fp = hashlib.sha3_512(self.name.encode()).hexdigest()
        color = TIER_COLORS.get(self.tier, "primary")
        return f"USYS:{self.tav}:FOOTER:{fp[:16]}:{color}"

    def to_dict(self) -> dict:
        return {
            "name":       self.name,
            "version":    self.version,
            "backend":    self.backend,
            "tav":        self.tav,
            "tier":       self.tier,
            "state":      self.state,
            "header_qr":  self.header_qr(),
            "footer_qr":  self.footer_qr(),
            "timestamp":  self.timestamp,
            "meta":       self.meta,
        }


# ── Package Handler ───────────────────────────────────────────────────────────

class PackageHandler:
    """
    Helix's face to the outside world.
    Talks to the clone pool (Helix). Knows where everything is.
    Pulls from Phoenix DB + 10 distros + personal DB.
    """

    def __init__(self):
        PH_DB.parent.mkdir(parents=True, exist_ok=True)
        self._lock   = threading.RLock()
        self._helix  = None
        self._frank  = None
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

    # ── Acquaint — learn the clone pool ───────────────────────────────────────

    def _acquaint(self):
        """
        Package handler acquaints herself with where everything is.
        Reads Helix's index and syncs to local catalog.
        """
        helix = self._get_helix()
        if not helix:
            return
        items = helix.list_all()
        with sqlite3.connect(PH_DB) as cx:
            for item in items:
                cx.execute(
                    "INSERT OR IGNORE INTO packages (tav, name, tier, state, timestamp, meta) "
                    "VALUES (?,?,?,?,?,?)",
                    (item["tav"], item["name"], item.get("tier","T1"),
                     item.get("state","active"), _now(), "{}")
                )

    # ── Lazy loaders ──────────────────────────────────────────────────────────

    def _get_helix(self):
        if self._helix is None:
            try:
                import helix as helix_mod
                self._helix = helix_mod._get_global_helix()
            except ImportError:
                pass
        return self._helix

    def _get_frank(self):
        if self._frank is None:
            try:
                import frank as frank_mod
                self._frank = frank_mod.get_frank()
            except ImportError:
                pass
        return self._frank

    # ── Install ───────────────────────────────────────────────────────────────

    def install(self, name: str, backend: str = None,
                version: str = None, target: str = None) -> dict:
        helix  = self._get_helix()
        frank  = self._get_frank()

        b = backend or self._detect_backend(name, target)
        cmd = self._build_install_cmd(name, b, version, target)

        if frank:
            frank._log(__import__('frank').AuditEntry(
                "ph.install.start", name, {"backend": b, "cmd": cmd}
            ))

        rec = PackageRecord(name, version, b)
        self._register(rec)

        if helix:
            helix.store(f"pkg:{name}", rec.to_dict(), meta={"cmd": cmd})

        d1_result = self._d1_push("install", rec.to_dict())

        result = {
            "ok":      True,
            "name":    name,
            "backend": b,
            "version": version or "latest",
            "cmd":     cmd,
            "tav":     rec.tav,
            "d1":      d1_result,
        }

        if frank:
            frank._log(__import__('frank').AuditEntry(
                "ph.install.complete", name, result
            ))

        return result

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
            return helix.egress_pkg(
                f"{name}=={version}" if version else name, target
            )
        return f"# install {name}"

    def _detect_backend(self, name: str, target: str = None) -> str:
        helix = self._get_helix()
        if helix:
            platform = target or helix.quad.current
            for backend, info in BACKENDS.items():
                if platform in info["platforms"] or "all" in info["platforms"]:
                    return backend
        return "apt"

    # ── Search ────────────────────────────────────────────────────────────────

    def search(self, query: str) -> list:
        with sqlite3.connect(PH_DB) as cx:
            rows = cx.execute(
                "SELECT name, version, backend, tav, state, tier FROM packages "
                "WHERE name LIKE ? OR meta LIKE ? ORDER BY name LIMIT 50",
                (f"%{query}%", f"%{query}%")
            ).fetchall()
        results = []
        helix   = self._get_helix()
        for name, version, backend, tav, state, tier in rows:
            results.append({
                "name": name, "version": version, "backend": backend,
                "tav": tav, "state": state, "tier": tier,
                "in_clone_pool": helix.exists(f"pkg:{name}") if helix else False,
            })
        return results

    # ── Status ────────────────────────────────────────────────────────────────

    def status(self, name: str) -> dict | None:
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
            query += " AND tier=?"
            params.append(tier)
        query += " ORDER BY name"
        with sqlite3.connect(PH_DB) as cx:
            rows = cx.execute(query, params).fetchall()
        return [{"name":r[0],"version":r[1],"backend":r[2],
                 "tav":r[3],"state":r[4],"tier":r[5]} for r in rows]

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
                        "INSERT INTO packages (tav, name, version, backend, tier, state, timestamp, meta) "
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
                "data":      data,
            }).encode()
            req = urllib.request.Request(
                f"{D1_WORKER_URL}/clonepool",
                data=payload,
                method="POST",
                headers={
                    "Content-Type":  "application/json",
                    "Authorization": f"Bearer {PHOENIX_AUTH}",
                }
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                return {"ok": True, "status": resp.status}
        except urllib.error.URLError as e:
            return {"ok": False, "error": str(e)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def d1_sync(self) -> dict:
        """Push full local catalog to D1."""
        packages = self.list_packages()
        results  = []
        for pkg in packages:
            r = self._d1_push("sync", pkg)
            results.append({"name": pkg["name"], "d1": r})
        return {"ok": True, "synced": len(results), "results": results}

    # ── Glossary ──────────────────────────────────────────────────────────────

    def glossary(self) -> dict:
        """TOC and index of clone pool and D1."""
        packages = self.list_packages()
        helix    = self._get_helix()
        pool     = helix.list_all() if helix else []
        return {
            "packages":    len(packages),
            "clone_pool":  len(pool),
            "toc":         [p["name"] for p in packages],
            "pool_index":  [i["name"] for i in pool],
            "generated":   _now(),
        }

    def full_status(self) -> dict:
        helix = self._get_helix()
        frank = self._get_frank()
        with sqlite3.connect(PH_DB) as cx:
            total  = cx.execute("SELECT COUNT(*) FROM packages").fetchone()[0]
            active = cx.execute(
                "SELECT COUNT(*) FROM packages WHERE state='active'"
            ).fetchone()[0]
        return {
            "ph_version":    PH_VERSION,
            "packages_total":  total,
            "packages_active": active,
            "helix_online":    helix is not None,
            "helix_stats":     helix.stats() if helix else None,
            "frank_online":    frank is not None,
            "d1_configured":   bool(D1_WORKER_URL and PHOENIX_AUTH),
            "worker_url":      D1_WORKER_URL or "not set",
        }


# ── Global instance ───────────────────────────────────────────────────────────

_ph: PackageHandler | None = None

def get_ph() -> PackageHandler:
    global _ph
    if _ph is None:
        _ph = PackageHandler()
    return _ph


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Phoenix Package Handler")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("status",   help="Full status")
    sub.add_parser("glossary", help="TOC and index")
    sub.add_parser("sync",     help="Sync to D1")
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

    args = parser.parse_args()
    ph = get_ph()

    if args.cmd == "status":
        print(json.dumps(ph.full_status(), indent=2))

    elif args.cmd == "glossary":
        print(json.dumps(ph.glossary(), indent=2))

    elif args.cmd == "sync":
        print(json.dumps(ph.d1_sync(), indent=2))

    elif args.cmd == "acquaint":
        ph._acquaint()
        print("Acquainted with clone pool.")

    elif args.cmd == "install":
        print(json.dumps(ph.install(args.name, args.backend, args.version, args.target), indent=2))

    elif args.cmd == "search":
        results = ph.search(args.query)
        print(json.dumps(results, indent=2))

    elif args.cmd == "info":
        info = ph.status(args.name)
        print(json.dumps(info, indent=2) if info else f"Not found: {args.name}")

    elif args.cmd == "list":
        packages = ph.list_packages(args.state, args.tier)
        for p in packages:
            print(f"  {p['name']:30} {p['version']:15} {p['backend']:10} [{p['state']}]")

    else:
        parser.print_help()
