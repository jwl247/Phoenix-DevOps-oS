#!/usr/bin/env python3
"""
intake.py — Phoenix DevOps / UnitedSys TAV intake engine
Location:  ~/projects/unitedsys/core/intake.py
Called by: sector4/intake/intake.sh

Pipeline: file → dup check → hex → sidecar → clonepool → custody → D1

TAV address: SHA3-512(filename) → first 8 bytes → base58
Content hash: SHA3-512(file content) → custody + footer QR

Authors: Jerry Leftwich + Jerilynn Leftwich
License: GPL v3
"""

import hashlib
import json
import logging
import os
import shutil
import sqlite3
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CLONEPOOL_DIR = Path(os.environ.get("CLONEPOOL_DIR", str(Path.home() / "Phoenix" / "clonepool")))
CATALOG_DB    = Path.home() / ".catalog" / "catalog.db"
LOG_DIR       = Path.home() / ".unitedsys" / "logs"
LOG_FILE      = LOG_DIR / "intake.log"
ENV_FILE      = Path.home() / ".phoenix_env"

VERSION = "1.0.0"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [intake:%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(str(LOG_FILE)),
        logging.StreamHandler(sys.stderr),
    ],
)
log = logging.getLogger("intake")

# ---------------------------------------------------------------------------
# Env / auth — read ~/.phoenix_env if env vars not already set
# ---------------------------------------------------------------------------

def _load_phoenix_env():
    if not ENV_FILE.exists():
        return
    with open(str(ENV_FILE)) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key in ("PHOENIX_WORKER_URL", "PHOENIX_AUTH"):
                os.environ.setdefault(key, val)

_load_phoenix_env()

WORKER_URL   = os.environ.get("PHOENIX_WORKER_URL", "https://packages-worker.phoenix-jwl.workers.dev")
PHOENIX_AUTH = os.environ.get("PHOENIX_AUTH", "")

# ---------------------------------------------------------------------------
# Base58 — inline, no external deps
# Bitcoin alphabet — same as TAV spec
# ---------------------------------------------------------------------------

_B58_ALPHA = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"

def hex_identity(name):
    """Return the hex-encoded filename — canonical pool dir key."""
    return name.encode().hex()


def b58encode(data):
    n = int.from_bytes(data, "big")
    result = []
    while n:
        n, rem = divmod(n, 58)
        result.append(_B58_ALPHA[rem])
    leading = len(data) - len(data.lstrip(b"\x00"))
    return _B58_ALPHA[0] * leading + "".join(reversed(result))

# ---------------------------------------------------------------------------
# TAV address
# filename → SHA3-512 → first 8 bytes → base58
# ---------------------------------------------------------------------------

def tav_address(filename):
    digest = hashlib.sha3_512(filename.encode()).digest()
    return b58encode(digest[:8])

# ---------------------------------------------------------------------------
# Filetype detection
# ---------------------------------------------------------------------------

_EXT_MAP = {
    "sh":      "script:shell",
    "bash":    "script:shell",
    "zsh":     "script:shell",
    "py":      "script:python",
    "js":      "script:javascript",
    "mjs":     "script:javascript",
    "cjs":     "script:javascript",
    "ts":      "script:typescript",
    "json":    "config:json",
    "yaml":    "config:yaml",
    "yml":     "config:yaml",
    "toml":    "config:toml",
    "env":     "config:env",
    "conf":    "config:conf",
    "cfg":     "config:conf",
    "ini":     "config:conf",
    "service": "systemd:service",
    "timer":   "systemd:timer",
    "socket":  "systemd:socket",
    "sql":     "database:sql",
    "md":      "docs:markdown",
    "markdown":"docs:markdown",
    "txt":     "docs:text",
    "xml":     "config:xml",
    "html":    "web:html",
    "htm":     "web:html",
    "css":     "web:css",
    "c":       "source:c",
    "h":       "source:c",
    "cpp":     "source:cpp",
    "hpp":     "source:cpp",
    "rs":      "source:rust",
    "go":      "source:go",
}

_CAT_HEX = {
    "script":   "73637269707473",
    "config":   "636f6e666967",
    "systemd":  "73797374656d",
    "database": "6461746162617365",
    "docs":     "646f6373",
    "web":      "776f726b657273",
    "source":   "737562737973",
    "package":  "7061636b61676573",
}

def detect_filetype(name):
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return _EXT_MAP.get(ext, "unknown:unknown")

def category_hex(filetype):
    prefix = filetype.split(":")[0]
    return _CAT_HEX.get(prefix, "756e6b6e6f776e")

# ---------------------------------------------------------------------------
# Companion detection
# ---------------------------------------------------------------------------

_COMPANION_EXTS = ("service", "timer", "socket", "conf", "env", "yaml", "yml", "toml", "json", "md")

def detect_companions(filepath):
    stem   = filepath.stem
    parent = filepath.parent
    companions = []
    for ext in _COMPANION_EXTS:
        candidate = parent / "{}.{}".format(stem, ext)
        if candidate.exists() and candidate.resolve() != filepath.resolve():
            companions.append(candidate)
            log.info("companion found: %s", candidate.name)
    return companions

# ---------------------------------------------------------------------------
# Version bumping
# ---------------------------------------------------------------------------

def next_version(pool_dir):
    if not pool_dir.exists():
        return "v1"
    nums = []
    for p in pool_dir.iterdir():
        if p.is_file() and p.name.startswith("v") and "_" in p.name:
            try:
                nums.append(int(p.name.split("_")[0][1:]))
            except ValueError:
                pass
    return "v{}".format(max(nums) + 1) if nums else "v1"

# ---------------------------------------------------------------------------
# Dup check — by SHA3-512 of file content
# Returns (hex_name, version) if already registered, else None
# ---------------------------------------------------------------------------

def find_dup(content_sha3):
    if not CLONEPOOL_DIR.exists():
        return None
    for sidecar in CLONEPOOL_DIR.rglob("*.sidecar.json"):
        try:
            with open(str(sidecar)) as f:
                d = json.load(f)
            if d.get("hash_sha3") == content_sha3:
                return d.get("hex_name", "?"), d.get("version", "?")
        except Exception:
            continue
    return None

# ---------------------------------------------------------------------------
# Sidecar
# ---------------------------------------------------------------------------

def write_sidecar(pool_dir, hex_name, content_sha3, b58, orig,
                  version, filetype, cat_hex, size, companions, notes=""):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    companion_list = [
        {
            "file":     c.name,
            "path":     str(c),
            "type":     c.suffix.lstrip("."),
            "editable": c.suffix.lstrip(".") in (
                "service", "timer", "socket", "conf", "env",
                "yaml", "yml", "toml", "json"
            ),
        }
        for c in companions
    ]
    sidecar = {
        "usys_intake":    VERSION,
        # primary keys
        "hex_name":       hex_name,
        "hex":            hex_name,       # alias — config_centralizer reads this
        "hash_sha3":      content_sha3,
        "sha3":           content_sha3,   # alias — config_centralizer reads this
        "b58":            b58,
        "original_name":  orig,
        "state":          "white",
        "version":        version,
        "filetype":       filetype,
        "category_hex":   cat_hex,
        "size_bytes":     size,
        "size":           size,           # alias — config_centralizer reads this
        "pool_path":      str(pool_dir),
        "companions":     companion_list,
        "notes":          notes,
        "qr": {
            "header": "USYS:{}:HEADER".format(b58),
            "footer": "USYS:{}:FOOTER:{}".format(b58, content_sha3),
        },
        "auto_hotswap":   False,
        "registered_at":  now,
        "intaked_at":     now,            # alias — config_centralizer reads this
        "updated_at":     now,
        "clone_history":  [{"version": version, "at": now}],
    }
    path = pool_dir / "{}.sidecar.json".format(hex_name)
    pool_dir.mkdir(parents=True, exist_ok=True)
    with open(str(path), "w") as f:
        json.dump(sidecar, f, indent=2)
    log.info("sidecar written: %s", path.name)
    return path

# ---------------------------------------------------------------------------
# Local custody (SQLite)
# ---------------------------------------------------------------------------

def custody_local(hex_name, name, action, version, source, destination,
                  state="white", actor="usys"):
    CATALOG_DB.parent.mkdir(parents=True, exist_ok=True)
    try:
        con = sqlite3.connect(str(CATALOG_DB))
        con.execute("""
            CREATE TABLE IF NOT EXISTS custody (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                hex_id      TEXT NOT NULL,
                name        TEXT NOT NULL,
                action      TEXT NOT NULL,
                version     TEXT,
                source      TEXT,
                destination TEXT,
                state       TEXT DEFAULT 'white',
                actor       TEXT DEFAULT 'usys',
                validated   INTEGER DEFAULT 0,
                intaked_at  TEXT DEFAULT (datetime('now'))
            )
        """)
        con.execute(
            "INSERT INTO custody (hex_id, name, action, version, source, destination, state, actor) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (hex_name, name, action, version, source, destination, state, actor),
        )
        con.commit()
        con.close()
        log.info("custody logged: %s → %s", name, action)
    except Exception as e:
        log.warning("custody local write failed: %s", e)

# ---------------------------------------------------------------------------
# D1 reporter
# ---------------------------------------------------------------------------

def _post_d1(endpoint, payload):
    if not PHOENIX_AUTH:
        log.warning("PHOENIX_AUTH not set — skipping D1: %s", endpoint)
        return
    url  = WORKER_URL.rstrip("/") + endpoint
    data = json.dumps(payload).encode()
    req  = urllib.request.Request(
        url, data=data,
        headers={
            "Content-Type":  "application/json",
            "Authorization": "Bearer {}".format(PHOENIX_AUTH),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            log.info("D1 OK → %s (%s)", endpoint, resp.status)
    except urllib.error.HTTPError as e:
        log.warning("D1 HTTP %s → %s", e.code, endpoint)
    except Exception as e:
        log.warning("D1 failed → %s: %s", endpoint, e)

def _report_clonepool(hex_name, b58, name, version, pool_dir, sidecar_path, size):
    _post_d1("/clonepool", {
        "hex_id":       hex_name,
        "b58":          b58,
        "name":         name,
        "original_name":name,
        "version":      version,
        "state":        "white",
        "pool_path":    str(pool_dir),
        "sidecar_path": str(sidecar_path),
        "tier":         1,
        "size":         size,
    })

def _report_custody(hex_name, name, action, actor):
    _post_d1("/custody", {
        "hex_id": hex_name,
        "name":   name,
        "action": action,
        "state":  "white",
        "actor":  actor,
    })

def _report_glossary(hex_name, b58, name, filetype, cat_hex, version, size, pool_dir):
    _post_d1("/glossary", {
        "hex":          hex_name,
        "b58":          b58,
        "name":         name,
        "description":  "Intaked: {}".format(filetype),
        "category_hex": cat_hex,
        "version":      version,
        "size":         size,
        "pool_path":    str(pool_dir),
        "state":        "white",
    })

# ---------------------------------------------------------------------------
# Core intake
# ---------------------------------------------------------------------------

def intake_file(filepath_str, notes=""):
    filepath = Path(filepath_str).resolve()

    if not filepath.is_file():
        print("[intake:ERROR] not a file: {}".format(filepath))
        return 1

    orig         = filepath.name
    content      = filepath.read_bytes()
    size         = len(content)
    content_sha3 = hashlib.sha3_512(content).hexdigest()
    b58          = tav_address(orig)
    hex_name     = orig.encode().hex()
    filetype     = detect_filetype(orig)
    cat_hex      = category_hex(filetype)

    # -- Dup check (by content) ----------------------------------------------
    dup = find_dup(content_sha3)
    if dup:
        dup_hex, dup_ver = dup
        print("[intake:DUP]  {}".format(orig))
        print("[intake:DUP]  already registered: hex={} version={}".format(dup_hex, dup_ver))
        print("[intake:DUP]  SHA3: {}...".format(content_sha3[:32]))
        return 0

    # -- Pool dir + version --------------------------------------------------
    pool_dir = CLONEPOOL_DIR / hex_name
    pool_dir.mkdir(parents=True, exist_ok=True)
    version = next_version(pool_dir)

    log.info("intaking: %s (%s) as %s", orig, filetype, version)

    # -- Companions ----------------------------------------------------------
    companions = detect_companions(filepath)
    for comp in companions:
        shutil.copy2(str(comp), str(pool_dir / "{}_{}".format(version, comp.name)))
        log.info("companion stored: %s", comp.name)

    # -- Copy main file ------------------------------------------------------
    shutil.copy2(str(filepath), str(pool_dir / "{}_{}".format(version, orig)))
    log.info("stored: %s/%s_%s", pool_dir, version, orig)

    # -- Sidecar -------------------------------------------------------------
    sidecar_path = write_sidecar(
        pool_dir, hex_name, content_sha3, b58, orig,
        version, filetype, cat_hex, size, companions, notes,
    )

    # -- Custody (local) -----------------------------------------------------
    custody_local(
        hex_name, orig, "intake", version,
        str(filepath), str(pool_dir / "{}_{}".format(version, orig)),
        "white", "intake",
    )

    # -- D1 ------------------------------------------------------------------
    _report_clonepool(hex_name, b58, orig, version, pool_dir, sidecar_path, size)
    _report_custody(hex_name, orig, "intake", "intake")
    _report_glossary(hex_name, b58, orig, filetype, cat_hex, version, size, pool_dir)

    # -- Done ----------------------------------------------------------------
    print("[intake:OK]  {} → clonepool {}".format(orig, version))
    print("[intake:OK]  hex:  {}".format(hex_name))
    print("[intake:OK]  sha3: {}...".format(content_sha3[:32]))
    print("[intake:OK]  b58:  {}  (TAV address)".format(b58))
    print("[intake:OK]  qr_h: USYS:{}:HEADER".format(b58))
    print("[intake:OK]  qr_f: USYS:{}:FOOTER:{}...".format(b58, content_sha3[:16]))
    print("[intake:OK]  type: {}".format(filetype))
    if companions:
        print("[intake:OK]  companions: {}".format(len(companions)))
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: intake.py <filepath> [notes]")
        sys.exit(1)
    notes_arg = sys.argv[2] if len(sys.argv) > 2 else ""
    sys.exit(intake_file(sys.argv[1], notes_arg))
