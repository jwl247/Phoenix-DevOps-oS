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

# ── Paths ─────────────────────────────────────────────────────────────────────

PHOENIX_HOME = Path(os.environ.get("PHOENIX_HOME", Path.home() / "Phoenix"))
FRANK_DB     = PHOENIX_HOME / "db" / "frank.db"
LOG_DIR      = PHOENIX_HOME / "logs"
LOG_FILE     = LOG_DIR / "frank.log"

# ── Logging ───────────────────────────────────────────────────────────────────

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

# ── DB init ───────────────────────────────────────────────────────────────────

def init_db():
    """Initialize Frank's DB — output log + sideload registry + Ring 3 routing table."""
    FRANK_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(FRANK_DB)
    c = conn.cursor()

    # Output log — Frank records every output he coordinates
    c.execute("""
        CREATE TABLE IF NOT EXISTS output_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            source      TEXT NOT NULL,
            destination TEXT NOT NULL,
            payload     TEXT,
            status      TEXT DEFAULT 'delivered',
            coordinated_at TEXT DEFAULT (datetime('now'))
        )
    """)

    # Sideload registry — external processes Frank imports for the suite
    c.execute("""
        CREATE TABLE IF NOT EXISTS sideloads (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL UNIQUE,
            process     TEXT NOT NULL,
            version     TEXT,
            status      TEXT DEFAULT 'active',
            loaded_at   TEXT DEFAULT (datetime('now'))
        )
    """)

    # Ring 3 routing table — grows as each office app comes online
    c.execute("""
        CREATE TABLE IF NOT EXISTS ring3_routes (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            app         TEXT NOT NULL UNIQUE,
            endpoint    TEXT NOT NULL,
            status      TEXT DEFAULT 'stub',
            registered_at TEXT DEFAULT (datetime('now'))
        )
    """)

    conn.commit()
    conn.close()
    log.info("Frank DB initialized.")

# ── Output coordination ───────────────────────────────────────────────────────

def coordinate(source: str, destination: str, payload: dict = None) -> bool:
    """
    Deal output from source to destination.
    Logs every coordination. Destination can be Helix, a worker, an office app.
    """
    try:
        conn = sqlite3.connect(FRANK_DB)
        conn.execute(
            "INSERT INTO output_log (source, destination, payload, status) VALUES (?, ?, ?, ?)",
            (source, destination, json.dumps(payload) if payload else None, "delivered")
        )
        conn.commit()
        conn.close()
        log.info(f"coordinated: {source} → {destination}")
        return True
    except Exception as e:
        log.error(f"coordinate failed: {e}")
        return False

# ── Sideload importer ─────────────────────────────────────────────────────────

def sideload(name: str, process: str, version: str = None) -> bool:
    """
    Import an external process the suite needs (e.g. LibreOffice in reverse).
    Registers it so Frank knows what's available.
    """
    try:
        conn = sqlite3.connect(FRANK_DB)
        conn.execute(
            """INSERT INTO sideloads (name, process, version, status)
               VALUES (?, ?, ?, 'active')
               ON CONFLICT(name) DO UPDATE SET
               process=excluded.process, version=excluded.version,
               status='active', loaded_at=datetime('now')""",
            (name, process, version)
        )
        conn.commit()
        conn.close()
        log.info(f"sideloaded: {name} ({process} {version or 'unknown'})")
        return True
    except Exception as e:
        log.error(f"sideload failed: {e}")
        return False

# ── Ring 3 routing ────────────────────────────────────────────────────────────

def register_route(app: str, endpoint: str) -> bool:
    """
    Register a Ring 3 (office suite) app route.
    Stub now — grows as each app comes online.
    """
    try:
        conn = sqlite3.connect(FRANK_DB)
        conn.execute(
            """INSERT INTO ring3_routes (app, endpoint, status)
               VALUES (?, ?, 'stub')
               ON CONFLICT(app) DO UPDATE SET
               endpoint=excluded.endpoint, registered_at=datetime('now')""",
            (app, endpoint)
        )
        conn.commit()
        conn.close()
        log.info(f"ring3 route registered: {app} → {endpoint}")
        return True
    except Exception as e:
        log.error(f"register_route failed: {e}")
        return False

# ── Status ────────────────────────────────────────────────────────────────────

def status():
    """Frank's current status — output log count, sideloads, Ring 3 routes."""
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

# ── Init ──────────────────────────────────────────────────────────────────────

def init():
    """Frank comes online. DB initialized. Ready to coordinate."""
    init_db()

    # Stub Ring 3 routes — grow as each app comes online
    stub_routes = [
        ("office",      "workers/office-worker"),
        ("glossary",    "workers/glossary-worker"),
        ("review",      "workers/review-worker"),
        ("sketchpad",   "workers/sketchpad-worker"),
        ("notation",    "workers/notation-worker"),
        ("desktop",     "workers/desktop-worker"),
    ]
    for app, endpoint in stub_routes:
        register_route(app, endpoint)

    log.info("Frank online — output coordinator ready.")
    print("[frank] online — output coordinator + Ring 3 stub ready")

# ── Entry ─────────────────────────────────────────────────────────────────────

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