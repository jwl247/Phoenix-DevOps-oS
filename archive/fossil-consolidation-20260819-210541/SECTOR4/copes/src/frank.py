#!/usr/bin/env python3
# =============================================================================
# frank.py — Phoenix DevOps OS / COPES
# Frank: output coordinator + sideload importer + Ring 3 comms stub
# Grows with the office suite. Not intake (Package Handler). Not egress (Helix).
# Frank deals output to the right destination and sideloads what the suite needs.
# =============================================================================
# Author:  jwl247 / Phoenix DevOps LLC
# License: GPL v3
# =============================================================================

import os
import json
import sqlite3
import logging
from datetime import datetime, timezone
from pathlib import Path

PHOENIX_HOME = Path(os.environ.get("PHOENIX_HOME", Path.home() / "Phoenix"))
FRANK_DB     = PHOENIX_HOME / "db" / "frank.db"
LOG_DIR      = PHOENIX_HOME / "logs"
LOG_FILE     = LOG_DIR / "frank.log"

LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [frank:%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("frank")

def init_db():
    FRANK_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(FRANK_DB)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS output_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source TEXT NOT NULL, destination TEXT NOT NULL,
        payload TEXT, status TEXT DEFAULT 'delivered',
        coordinated_at TEXT DEFAULT (datetime('now')))""")
    c.execute("""CREATE TABLE IF NOT EXISTS sideloads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE, process TEXT NOT NULL,
        version TEXT, status TEXT DEFAULT 'active',
        loaded_at TEXT DEFAULT (datetime('now')))""")
    c.execute("""CREATE TABLE IF NOT EXISTS ring3_routes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        app TEXT NOT NULL UNIQUE, endpoint TEXT NOT NULL,
        status TEXT DEFAULT 'stub',
        registered_at TEXT DEFAULT (datetime('now')))""")
    conn.commit()
    conn.close()
    log.info("Frank DB initialized.")

def coordinate(source, destination, payload=None):
    try:
        conn = sqlite3.connect(FRANK_DB)
        conn.execute("INSERT INTO output_log (source, destination, payload, status) VALUES (?,?,?,?)",
            (source, destination, json.dumps(payload) if payload else None, "delivered"))
        conn.commit()
        conn.close()
        log.info(f"coordinated: {source} → {destination}")
        return True
    except Exception as e:
        log.error(f"coordinate failed: {e}")
        return False

def sideload(name, process, version=None):
    try:
        conn = sqlite3.connect(FRANK_DB)
        conn.execute("""INSERT INTO sideloads (name, process, version, status)
            VALUES (?,?,?,'active') ON CONFLICT(name) DO UPDATE SET
            process=excluded.process, version=excluded.version,
            status='active', loaded_at=datetime('now')""", (name, process, version))
        conn.commit()
        conn.close()
        log.info(f"sideloaded: {name} ({process} {version or 'unknown'})")
        return True
    except Exception as e:
        log.error(f"sideload failed: {e}")
        return False

def register_route(app, endpoint):
    try:
        conn = sqlite3.connect(FRANK_DB)
        conn.execute("""INSERT INTO ring3_routes (app, endpoint, status)
            VALUES (?,?,'stub') ON CONFLICT(app) DO UPDATE SET
            endpoint=excluded.endpoint, registered_at=datetime('now')""", (app, endpoint))
        conn.commit()
        conn.close()
        log.info(f"ring3 route registered: {app} → {endpoint}")
        return True
    except Exception as e:
        log.error(f"register_route failed: {e}")
        return False

def status():
    try:
        conn = sqlite3.connect(FRANK_DB)
        outputs   = conn.execute("SELECT COUNT(*) FROM output_log").fetchone()[0]
        sideloads = conn.execute("SELECT COUNT(*) FROM sideloads WHERE status='active'").fetchone()[0]
        routes    = conn.execute("SELECT COUNT(*) FROM ring3_routes").fetchone()[0]
        conn.close()
        print("")
        print("  ╔══════════════════════════════════════╗")
        print("  ║           FRANK — COPES              ║")
        print("  ╚══════════════════════════════════════╝")
        print(f"  DB         : {FRANK_DB}")
        print(f"  Outputs    : {outputs} coordinated")
        print(f"  Sideloads  : {sideloads} active")
        print(f"  Ring 3     : {routes} routes registered")
        print("")
    except Exception as e:
        log.error(f"status failed: {e}")

def llm_dispatch(payload: dict) -> dict:
    """
    Frank's Ring 3 LLM handler.
    Routes payload to the LLM engine (Phoenix_Universal_Kernel/llm_engine.py).
    Called by Life First modules and any other app via Ring 3.

    Payload: {user_id, message, intent, system?, options?}
    Returns: {response, model, intent, source, error}
    """
    try:
        import importlib.util, sys as _sys
        _here = Path(__file__).parent.parent.parent / "Phoenix_Universal_Kernel"
        spec = importlib.util.spec_from_file_location(
            "llm_engine", _here / "llm_engine.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.frank_handler(payload)
    except Exception as e:
        log.error(f"llm_dispatch failed: {e}")
        return {"response": "", "model": "none", "error": str(e)}


def lifefirst_dispatch(module: str, data: dict) -> dict:
    """
    Frank's Ring 3 Life First bridge.
    Sends a request to the Life First PHP API on localhost and returns the JSON.
    module: 'schedule' | 'messenger' | 'memory' | 'notification' | 'voice'
    """
    import urllib.request, urllib.error, json as _json, os as _os
    api_url    = _os.environ.get("LIFEFIRST_API",    "http://localhost/lifefirst/api.php")
    api_secret = _os.environ.get("LF_API_SECRET",   "")
    payload = _json.dumps({**data, "intent": module}).encode()
    req = urllib.request.Request(
        api_url,
        data    = payload,
        headers = {
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {api_secret}",
        },
        method  = "POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return _json.loads(r.read())
    except Exception as e:
        log.error(f"lifefirst_dispatch failed: {e}")
        return {"status": "error", "message": str(e)}


def init():
    init_db()
    stub_routes = [
        ("office",        "workers/office-worker"),
        ("glossary",      "workers/glossary-worker"),
        ("review",        "workers/review-worker"),
        ("sketchpad",     "workers/sketchpad-worker"),
        ("notation",      "workers/notation-worker"),
        ("desktop",       "workers/desktop-worker"),
        # Life First AI system — Ring 3 bridge to PHP modules on localhost
        ("lifefirst",     "lifefirst_dispatch"),
        # LLM engine — paged vRAM, bigger than hardware models
        ("llm_engine",    "llm_dispatch"),
    ]
    for app, endpoint in stub_routes:
        register_route(app, endpoint)
    log.info("Frank online — output coordinator ready.")
    print("[frank] online — output coordinator + Ring 3 stub ready")

def main():
    import sys as _sys
    cmd = _sys.argv[1] if len(_sys.argv) > 1 else "status"
    init_db()
    if cmd == "init":
        init()
    elif cmd == "status":
        status()
    elif cmd == "sideload" and len(_sys.argv) >= 4:
        sideload(_sys.argv[2], _sys.argv[3], _sys.argv[4] if len(_sys.argv) > 4 else None)
    elif cmd == "coordinate" and len(_sys.argv) >= 4:
        coordinate(_sys.argv[2], _sys.argv[3])
    else:
        print("frank — COPES output coordinator")
        print("usage: frank [init|status|sideload|coordinate]")

if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    init_db()
    if cmd == "init":
        init()
    elif cmd == "status":
        status()
    elif cmd == "sideload" and len(sys.argv) >= 4:
        sideload(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else None)
    elif cmd == "coordinate" and len(sys.argv) >= 4:
        coordinate(sys.argv[2], sys.argv[3])
    else:
        print("frank — COPES output coordinator")
        print("usage:")
        print("  frank init")
        print("  frank status")
        print("  frank sideload <name> <process> [version]")
        print("  frank coordinate <source> <destination>")
