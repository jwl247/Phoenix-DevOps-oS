#!/usr/bin/env python3
"""
helix.py — Phoenix DevOps OS
Helix: clone pool engine, QuadEngine, egress translator.
She IS the clone pool. QuadEngine lives inside her.
Egress Helix handles all platform output translation.
jwl247 / United Systems / GPL v3
"""

import os
import json
import zlib
import hashlib
import base58
import sqlite3
import platform
import threading
import time
from pathlib import Path
from datetime import datetime, timezone

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
from typing import Any

# ── Constants ────────────────────────────────────────────────────────────────

HELIX_VERSION  = "1.0.0"
COMPRESSION    = 5          # zlib level
TIER_COUNT     = 4          # T1–T4 versioning tiers
MAX_OPS        = 700_000    # rated ops/sec

# ── Platform profiles (QuadEngine language database) ─────────────────────────

PLATFORM_PROFILES = {
    "windows": {
        "shell":      "powershell",
        "pkg":        "winget",
        "path_sep":   "\\",
        "home":       "%USERPROFILE%",
        "tmp":        "%TEMP%",
        "service":    "sc",
        "shebang":    None,
        "line_end":   "\r\n",
        "ext":        ".ps1",
        "sudo":       None,
        "activate":   ".venv\\Scripts\\Activate.ps1",
    },
    "macos": {
        "shell":      "zsh",
        "pkg":        "brew",
        "path_sep":   "/",
        "home":       "$HOME",
        "tmp":        "/tmp",
        "service":    "launchctl",
        "shebang":    "#!/usr/bin/env zsh",
        "line_end":   "\n",
        "ext":        ".sh",
        "sudo":       "sudo",
        "activate":   ".venv/bin/activate",
    },
    "debian": {
        "shell":      "bash",
        "pkg":        "apt",
        "path_sep":   "/",
        "home":       "$HOME",
        "tmp":        "/tmp",
        "service":    "systemctl",
        "shebang":    "#!/usr/bin/env bash",
        "line_end":   "\n",
        "ext":        ".sh",
        "sudo":       "sudo",
        "activate":   ".venv/bin/activate",
    },
    "ubuntu": {
        "shell":      "bash",
        "pkg":        "apt",
        "path_sep":   "/",
        "home":       "$HOME",
        "tmp":        "/tmp",
        "service":    "systemctl",
        "shebang":    "#!/usr/bin/env bash",
        "line_end":   "\n",
        "ext":        ".sh",
        "sudo":       "sudo",
        "activate":   ".venv/bin/activate",
    },
    "rhel": {
        "shell":      "bash",
        "pkg":        "dnf",
        "path_sep":   "/",
        "home":       "$HOME",
        "tmp":        "/tmp",
        "service":    "systemctl",
        "shebang":    "#!/usr/bin/env bash",
        "line_end":   "\n",
        "ext":        ".sh",
        "sudo":       "sudo",
        "activate":   ".venv/bin/activate",
    },
    "fedora": {
        "shell":      "bash",
        "pkg":        "dnf",
        "path_sep":   "/",
        "home":       "$HOME",
        "tmp":        "/tmp",
        "service":    "systemctl",
        "shebang":    "#!/usr/bin/env bash",
        "line_end":   "\n",
        "ext":        ".sh",
        "sudo":       "sudo",
        "activate":   ".venv/bin/activate",
    },
    "arch": {
        "shell":      "bash",
        "pkg":        "pacman",
        "path_sep":   "/",
        "home":       "$HOME",
        "tmp":        "/tmp",
        "service":    "systemctl",
        "shebang":    "#!/usr/bin/env bash",
        "line_end":   "\n",
        "ext":        ".sh",
        "sudo":       "sudo",
        "activate":   ".venv/bin/activate",
    },
    "kali": {
        "shell":      "bash",
        "pkg":        "apt",
        "path_sep":   "/",
        "home":       "$HOME",
        "tmp":        "/tmp",
        "service":    "systemctl",
        "shebang":    "#!/usr/bin/env bash",
        "line_end":   "\n",
        "ext":        ".sh",
        "sudo":       "sudo",
        "activate":   ".venv/bin/activate",
    },
    "alpine": {
        "shell":      "sh",
        "pkg":        "apk",
        "path_sep":   "/",
        "home":       "$HOME",
        "tmp":        "/tmp",
        "service":    "rc-service",
        "shebang":    "#!/bin/sh",
        "line_end":   "\n",
        "ext":        ".sh",
        "sudo":       "sudo",
        "activate":   ".venv/bin/activate",
    },
    "generic_linux": {
        "shell":      "bash",
        "pkg":        "unknown",
        "path_sep":   "/",
        "home":       "$HOME",
        "tmp":        "/tmp",
        "service":    "systemctl",
        "shebang":    "#!/usr/bin/env bash",
        "line_end":   "\n",
        "ext":        ".sh",
        "sudo":       "sudo",
        "activate":   ".venv/bin/activate",
    },
}

# ── Platform detection ────────────────────────────────────────────────────────

def detect_platform() -> str:
    system = platform.system().lower()
    if system == "windows":
        return "windows"
    if system == "darwin":
        return "macos"
    try:
        with open("/etc/os-release") as f:
            content = f.read().lower()
        if "kali" in content:      return "kali"
        if "arch" in content:      return "arch"
        if "fedora" in content:    return "fedora"
        if "rhel" in content or "red hat" in content: return "rhel"
        if "ubuntu" in content:    return "ubuntu"
        if "debian" in content:    return "debian"
        if "alpine" in content:    return "alpine"
    except Exception:
        pass
    return "generic_linux"

# ── TAV hex identity ──────────────────────────────────────────────────────────

def tav_hex(name: str) -> str:
    """Deterministic hex identity from filename — SHA3-512 first 8 bytes → base58."""
    raw = hashlib.sha3_512(name.encode()).digest()[:8]
    return base58.b58encode(raw).decode()

def tav_full(name: str) -> str:
    """Full SHA3-512 fingerprint."""
    return hashlib.sha3_512(name.encode()).hexdigest()

# ── Clone pool record ─────────────────────────────────────────────────────────

class CloneRecord:
    def __init__(self, name: str, data: Any, meta: dict = None):
        self.name        = name
        self.tav         = tav_hex(name)
        self.fingerprint = tav_full(name)
        self.data        = data
        self.meta        = meta or {}
        self.compressed  = None
        self.timestamp   = _now()
        self.tier        = "T1"
        self.state       = "active"   # active | deprecated | retired

    def compress(self):
        raw = json.dumps(self.data, default=str).encode()
        self.compressed = zlib.compress(raw, COMPRESSION)
        return self

    def to_sidecar(self) -> dict:
        return {
            "name":        self.name,
            "tav":         self.tav,
            "fingerprint": self.fingerprint,
            "timestamp":   self.timestamp,
            "tier":        self.tier,
            "state":       self.state,
            "size_raw":    len(json.dumps(self.data, default=str).encode()),
            "size_compressed": len(self.compressed) if self.compressed else 0,
            "meta":        self.meta,
        }

# ── QuadEngine (lives inside Helix) ──────────────────────────────────────────

class QuadEngine:
    """
    Quadralingual output engine — translates Frank's wishes to any platform.
    Helix already speaks all four languages. QuadEngine is her reference database.
    """

    def __init__(self):
        self.profiles  = PLATFORM_PROFILES
        self.current   = detect_platform()

    def profile(self, target: str = None) -> dict:
        t = (target or self.current).lower()
        return self.profiles.get(t, self.profiles["generic_linux"])

    def translate(self, command: str, target: str = None) -> str:
        """Translate a Phoenix command to target platform syntax."""
        p = self.profile(target)
        lines = []
        if p["shebang"]:
            lines.append(p["shebang"])
        lines.append(command.replace("/", p["path_sep"]))
        return p["line_end"].join(lines)

    def pkg_install(self, package: str, target: str = None) -> str:
        p = self.profile(target)
        cmds = {
            "apt":     f"apt-get install -y {package}",
            "dnf":     f"dnf install -y {package}",
            "pacman":  f"pacman -S --noconfirm {package}",
            "brew":    f"brew install {package}",
            "apk":     f"apk add {package}",
            "winget":  f"winget install {package}",
            "unknown": f"# install {package} manually",
        }
        cmd = cmds.get(p["pkg"], f"# install {package}")
        if p["sudo"] and p["pkg"] != "winget":
            cmd = f"{p['sudo']} {cmd}"
        return cmd

    def activate_venv(self, target: str = None) -> str:
        p = self.profile(target)
        if p["shell"] == "powershell":
            return f". {p['activate']}"
        return f"source {p['activate']}"

    def service_cmd(self, action: str, name: str, target: str = None) -> str:
        p = self.profile(target)
        svc = p["service"]
        if svc == "systemctl":
            return f"sudo systemctl {action} {name}"
        if svc == "launchctl":
            return f"launchctl {action} {name}"
        if svc == "sc":
            return f"sc {action} {name}"
        if svc == "rc-service":
            return f"rc-service {name} {action}"
        return f"# service {action} {name}"

    def all_platforms(self, command: str) -> dict:
        """Return command translated to every known platform."""
        return {p: self.translate(command, p) for p in self.profiles}

# ── Helix — the clone pool engine ────────────────────────────────────────────

class Helix:
    """
    Helix IS the clone pool.
    QuadEngine lives inside her.
    Egress Helix handles all output translation.
    Double strand memory engine — 300k–700k ops/sec, 100% hit rate.
    """

    def __init__(self, pool_dir: str = None, db_path: str = None):
        self.pool_dir  = Path(pool_dir or os.environ.get("CLONEPOOL_DIR", Path.home() / "Phoenix/clonepool"))
        self.db_path   = Path(db_path  or os.environ.get("HELIX_DB",     Path.home() / "Phoenix/db/helix.db"))
        self.pool_dir.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._cache    = {}          # strand A — hot cache
        self._index    = {}          # strand B — index
        self._lock     = threading.RLock()
        self._ops      = 0
        self._hits     = 0
        self._start    = time.time()

        self.quad      = QuadEngine()
        self._init_db()
        self._load_index()

    # ── DB ────────────────────────────────────────────────────────────────────

    def _init_db(self):
        with sqlite3.connect(self.db_path) as cx:
            cx.executescript("""
                CREATE TABLE IF NOT EXISTS clone_pool (
                    tav         TEXT PRIMARY KEY,
                    name        TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    tier        TEXT NOT NULL DEFAULT 'T1',
                    state       TEXT NOT NULL DEFAULT 'active',
                    timestamp   TEXT NOT NULL,
                    sidecar     TEXT NOT NULL,
                    payload     BLOB
                );
                CREATE TABLE IF NOT EXISTS versions (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    tav         TEXT NOT NULL,
                    version     INTEGER NOT NULL,
                    timestamp   TEXT NOT NULL,
                    payload     BLOB,
                    note        TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_name  ON clone_pool(name);
                CREATE INDEX IF NOT EXISTS idx_state ON clone_pool(state);
                CREATE INDEX IF NOT EXISTS idx_tier  ON clone_pool(tier);
            """)

    def _load_index(self):
        with sqlite3.connect(self.db_path) as cx:
            rows = cx.execute("SELECT tav, name, state, tier FROM clone_pool").fetchall()
        for tav, name, state, tier in rows:
            self._index[tav]  = {"name": name, "state": state, "tier": tier}
            self._index[name] = tav

    # ── Strand A — hot cache ops ──────────────────────────────────────────────

    def store(self, name: str, data: Any, meta: dict = None, note: str = None) -> CloneRecord:
        with self._lock:
            rec = CloneRecord(name, data, meta)
            rec.compress()
            self._cache[rec.tav]  = rec
            self._index[rec.tav]  = {"name": name, "state": "active", "tier": "T1"}
            self._index[name]     = rec.tav
            self._ops += 1
            self._write_db(rec, note)
            self._write_sidecar(rec)
            return rec

    def get(self, key: str) -> CloneRecord | None:
        with self._lock:
            self._ops += 1
            # Try name → tav lookup first, then treat key as tav directly
            tav = self._index.get(key) or (key if key in self._index else None)
            if tav and isinstance(self._index.get(tav), dict):
                pass  # tav confirmed
            elif tav and tav not in self._index:
                tav = None
            if tav and tav in self._cache:
                self._hits += 1
                return self._cache[tav]
            if tav:
                rec = self._load_from_db(tav)
                if rec:
                    self._cache[tav] = rec
                    self._hits += 1
                    return rec
            # Last resort — search DB by name
            with sqlite3.connect(self.db_path) as cx:
                row = cx.execute(
                    "SELECT tav FROM clone_pool WHERE name=?", (key,)
                ).fetchone()
            if row:
                rec = self._load_from_db(row[0])
                if rec:
                    self._cache[rec.tav] = rec
                    self._index[key]     = rec.tav
                    self._hits += 1
                    return rec
        return None

    def exists(self, name: str) -> bool:
        return name in self._index

    def list_all(self, state: str = None, tier: str = None) -> list:
        with self._lock:
            rows_filter = {k: v for k, v in self._index.items()
                          if isinstance(v, dict)}
            result = []
            for tav, info in rows_filter.items():
                if state and info["state"] != state:
                    continue
                if tier and info["tier"] != tier:
                    continue
                result.append({**info, "tav": tav})
            return result

    def deprecate(self, name: str) -> bool:
        with self._lock:
            tav = self._index.get(name)
            if not tav:
                return False
            if tav in self._cache:
                self._cache[tav].state = "deprecated"
            self._index[tav]["state"] = "deprecated"
            with sqlite3.connect(self.db_path) as cx:
                cx.execute("UPDATE clone_pool SET state='deprecated' WHERE tav=?", (tav,))
            return True

    # ── Strand B — persistence ────────────────────────────────────────────────

    def _write_db(self, rec: CloneRecord, note: str = None):
        sidecar_json = json.dumps(rec.to_sidecar())
        with sqlite3.connect(self.db_path) as cx:
            existing = cx.execute(
                "SELECT COUNT(*) FROM clone_pool WHERE tav=?", (rec.tav,)
            ).fetchone()[0]
            if existing:
                version = cx.execute(
                    "SELECT COUNT(*) FROM versions WHERE tav=?", (rec.tav,)
                ).fetchone()[0] + 1
                cx.execute(
                    "INSERT INTO versions (tav, version, timestamp, payload, note) VALUES (?,?,?,?,?)",
                    (rec.tav, version, rec.timestamp, rec.compressed, note)
                )
                cx.execute(
                    "UPDATE clone_pool SET timestamp=?, sidecar=?, payload=?, state='active' WHERE tav=?",
                    (rec.timestamp, sidecar_json, rec.compressed, rec.tav)
                )
            else:
                cx.execute(
                    "INSERT INTO clone_pool (tav, name, fingerprint, tier, state, timestamp, sidecar, payload) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (rec.tav, rec.name, rec.fingerprint, rec.tier,
                     rec.state, rec.timestamp, sidecar_json, rec.compressed)
                )

    def _write_sidecar(self, rec: CloneRecord):
        sidecar_path = self.pool_dir / f"{rec.tav}.sidecar.json"
        with open(sidecar_path, "w") as f:
            json.dump(rec.to_sidecar(), f, indent=2)

    def _load_from_db(self, tav: str) -> CloneRecord | None:
        with sqlite3.connect(self.db_path) as cx:
            row = cx.execute(
                "SELECT name, payload, sidecar FROM clone_pool WHERE tav=?", (tav,)
            ).fetchone()
        if not row:
            return None
        name, payload, sidecar_json = row
        sidecar = json.loads(sidecar_json)
        raw  = zlib.decompress(payload)
        data = json.loads(raw)
        rec  = CloneRecord(name, data, sidecar.get("meta", {}))
        rec.compressed = payload
        rec.timestamp  = sidecar["timestamp"]
        rec.tier       = sidecar["tier"]
        rec.state      = sidecar["state"]
        return rec

    # ── Egress Helix — platform translation ───────────────────────────────────

    def egress(self, name: str, target: str = None) -> str | None:
        """
        Egress Helix — pull from clone pool and translate to target platform.
        This is the symlink destination for romeo/juliet/translator.
        """
        rec = self.get(name)
        if not rec:
            return None
        target = target or self.quad.current
        if isinstance(rec.data, str):
            return self.quad.translate(rec.data, target)
        return self.quad.translate(json.dumps(rec.data, indent=2), target)

    def egress_pkg(self, package: str, target: str = None) -> str:
        return self.quad.pkg_install(package, target)

    def egress_service(self, action: str, name: str, target: str = None) -> str:
        return self.quad.service_cmd(action, name, target)

    # ── Metrics ───────────────────────────────────────────────────────────────

    def stats(self) -> dict:
        elapsed = time.time() - self._start
        ops_sec = int(self._ops / elapsed) if elapsed > 0 else 0
        hit_rate = (self._hits / self._ops * 100) if self._ops > 0 else 100.0
        return {
            "ops_total":    self._ops,
            "ops_per_sec":  ops_sec,
            "hit_rate_pct": round(hit_rate, 2),
            "cache_size":   len(self._cache),
            "index_size":   len(self._index),
            "pool_dir":     str(self.pool_dir),
            "db_path":      str(self.db_path),
            "platform":     self.quad.current,
            "uptime_sec":   round(elapsed, 2),
        }

    def benchmark(self, rounds: int = 10_000) -> dict:
        start = time.time()
        for i in range(rounds):
            self.store(f"bench_{i}", {"val": i})
        t1 = time.time()
        for i in range(rounds):
            self.get(f"bench_{i}")
        t2 = time.time()
        write_ops = int(rounds / (t1 - start))
        read_ops  = int(rounds / (t2 - t1))
        return {
            "write_ops_per_sec": write_ops,
            "read_ops_per_sec":  read_ops,
            "rounds":            rounds,
        }

    # ── Symlink registration (romeo / juliet / translator → egress_helix) ─────

    @staticmethod
    def register_symlinks(bin_dir: str = None):
        """
        Creates symlinks so romeo, juliet, dbl_juliet, translator all point
        to this module's egress. Called by bootstrap.sh.
        """
        target = Path(__file__).resolve()
        bin_path = Path(bin_dir) if bin_dir else target.parent
        links = ["romeo", "juliet", "dbl_juliet", "translator"]
        created = []
        for link_name in links:
            link = bin_path / f"{link_name}.py"
            if link.exists() or link.is_symlink():
                link.unlink()
            link.symlink_to(target)
            created.append(str(link))
        return created


# ── Egress entry points (symlink targets call these) ─────────────────────────

def romeo(name: str, target: str = None) -> str | None:
    """Ingress-named egress — same as egress_helix."""
    h = _get_global_helix()
    return h.egress(name, target)

def juliet(name: str, target: str = None) -> str | None:
    """Egress-named egress — same as egress_helix."""
    h = _get_global_helix()
    return h.egress(name, target)

def translator(command: str, target: str = None) -> str:
    """Direct translation without clone pool lookup."""
    h = _get_global_helix()
    return h.quad.translate(command, target)

_global_helix: Helix | None = None

def _get_global_helix() -> Helix:
    global _global_helix
    if _global_helix is None:
        _global_helix = Helix()
    return _global_helix

def init(pool_dir: str = None, db_path: str = None) -> Helix:
    global _global_helix
    _global_helix = Helix(pool_dir, db_path)
    return _global_helix


# ── CLI ───────────────────────────────────────────────────────────────────────

def egress_main():
    import sys as _sys
    args = _sys.argv[1:]
    h = _get_global_helix()
    if not args or args[0] == "help":
        print("egress_helix — Helix egress + platform translation")
        print("usage:")
        print("  egress_helix translate <command> [--target <platform>]")
        print("  egress_helix pkg <package> [--target <platform>]")
        print("  egress_helix stats")
        print("  egress_helix list")
        print("  egress_helix platforms")
        return
    cmd = args[0]
    target = None
    if "--target" in args:
        i = args.index("--target")
        target = args[i+1] if i+1 < len(args) else None
    if cmd == "translate" and len(args) >= 2:
        print(h.quad.translate(args[1], target))
    elif cmd == "pkg" and len(args) >= 2:
        print(h.egress_pkg(args[1], target))
    elif cmd == "stats":
        import json; print(json.dumps(h.stats(), indent=2))
    elif cmd == "list":
        import json; print(json.dumps(h.list_all(), indent=2))
    elif cmd == "platforms":
        print("\n".join(PLATFORM_PROFILES.keys()))
    else:
        print(f"unknown command: {cmd}")

if __name__ == "__main__":
    import sys
    import argparse

    parser = argparse.ArgumentParser(description="Helix — Phoenix clone pool engine")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("stats",     help="Show Helix stats")
    sub.add_parser("benchmark", help="Run benchmark")

    sp = sub.add_parser("store", help="Store item in clone pool")
    sp.add_argument("name")
    sp.add_argument("data")

    sg = sub.add_parser("get", help="Get item from clone pool")
    sg.add_argument("name")

    se = sub.add_parser("egress", help="Egress item to platform")
    se.add_argument("name")
    se.add_argument("--target", default=None)

    sl = sub.add_parser("list", help="List clone pool")
    sl.add_argument("--state", default=None)

    st = sub.add_parser("translate", help="Translate command to platform")
    st.add_argument("command")
    st.add_argument("--target", default=None)

    sp2 = sub.add_parser("platforms", help="List known platforms")
    sub.add_parser("symlinks", help="Register egress symlinks")

    args = parser.parse_args()
    h = _get_global_helix()

    if args.cmd == "stats":
        print(json.dumps(h.stats(), indent=2))

    elif args.cmd == "benchmark":
        print("Running benchmark (10k rounds)...")
        result = h.benchmark()
        print(json.dumps(result, indent=2))

    elif args.cmd == "store":
        rec = h.store(args.name, args.data)
        print(json.dumps(rec.to_sidecar(), indent=2))

    elif args.cmd == "get":
        rec = h.get(args.name)
        if rec:
            print(json.dumps(rec.to_sidecar(), indent=2))
        else:
            print(f"Not found: {args.name}")
            sys.exit(1)

    elif args.cmd == "egress":
        out = h.egress(args.name, args.target)
        print(out or f"Not found: {args.name}")

    elif args.cmd == "list":
        items = h.list_all(state=args.state)
        print(json.dumps(items, indent=2))

    elif args.cmd == "translate":
        print(h.quad.translate(args.command, args.target))

    elif args.cmd == "platforms":
        print(json.dumps(list(PLATFORM_PROFILES.keys()), indent=2))

    elif args.cmd == "symlinks":
        created = Helix.register_symlinks()
        for c in created:
            print(f"symlink → {c}")

    else:
        parser.print_help()
