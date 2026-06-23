#!/usr/bin/env python3
# ============================================================
# phoenix_auth.py — Hardware Fingerprint Authentication
# Project:   Phoenix DevOps / Full Propagator Framework
# Author:    jwl247 / Phoenix DevOps LLC
# License:   GPL-3.0
# ============================================================
# SHA3-512 + BLAKE2b double hashing across 10 hardware signals.
# No passwords. One-time machine authorization.
# Progressive lockout on failure.
# ============================================================

import os
import sys
import hashlib
import json
import sqlite3
import subprocess
import time
from datetime import datetime
from pathlib import Path

CATALOG_DB    = os.path.expanduser("~/.catalog/catalog.db")
AUTH_DB       = os.path.expanduser("~/.catalog/phoenix_auth.db")
LOG_DIR       = os.path.expanduser("~/.unitedsys/logs")
VERSION       = "0.1.0"
MAX_ATTEMPTS  = 3
LOCKOUT_BASE  = 30   # seconds, doubles each lockout

os.makedirs(LOG_DIR, exist_ok=True)

# ── Hardware Signal Collectors ───────────────────────────────
def get_hw_signals():
    """Collect 10 hardware signals for fingerprint"""
    signals = []

    def safe_read(cmd):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
            return r.stdout.strip()
        except Exception:
            return "unavailable"

    # 1. CPU info
    signals.append(safe_read(["cat", "/proc/cpuinfo"]))
    # 2. Machine ID
    signals.append(safe_read(["cat", "/etc/machine-id"]))
    # 3. DMI board serial
    signals.append(safe_read(["cat", "/sys/class/dmi/id/board_serial"]))
    # 4. DMI product UUID
    signals.append(safe_read(["cat", "/sys/class/dmi/id/product_uuid"]))
    # 5. Block device list
    signals.append(safe_read(["lsblk", "-o", "NAME,SERIAL,SIZE"]))
    # 6. Network interface MACs
    signals.append(safe_read(["cat", "/sys/class/net/eth0/address"]))
    # 7. Memory info
    signals.append(safe_read(["cat", "/proc/meminfo"]))
    # 8. CPU serial (ARM/embedded)
    signals.append(safe_read(["cat", "/proc/cpuinfo"]))
    # 9. Kernel version
    signals.append(safe_read(["uname", "-r"]))
    # 10. BIOS version
    signals.append(safe_read(["cat", "/sys/class/dmi/id/bios_version"]))

    return signals

def fingerprint(signals):
    """SHA3-512 + BLAKE2b double hash of all 10 signals"""
    combined = "|".join(signals).encode("utf-8")
    sha3     = hashlib.sha3_512(combined).hexdigest()
    blake2b  = hashlib.blake2b(combined).hexdigest()
    final    = hashlib.sha3_512((sha3 + blake2b).encode()).hexdigest()
    return final

# ── Auth DB ──────────────────────────────────────────────────
def auth_db_init():
    conn = sqlite3.connect(AUTH_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS authorized_machines (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            fingerprint  TEXT    NOT NULL UNIQUE,
            hostname     TEXT,
            authorized_at TEXT,
            last_seen    TEXT,
            attempt_count INTEGER DEFAULT 0,
            locked_until  TEXT
        )
    """)
    conn.commit()
    conn.close()

def is_authorized(fp):
    auth_db_init()
    conn = sqlite3.connect(AUTH_DB)
    row = conn.execute(
        "SELECT locked_until, attempt_count FROM authorized_machines WHERE fingerprint=?",
        (fp,)
    ).fetchone()
    conn.close()

    if not row:
        return False, "NOT_REGISTERED"

    locked_until, attempts = row
    if locked_until:
        lock_time = datetime.fromisoformat(locked_until)
        if datetime.utcnow() < lock_time:
            return False, f"LOCKED_UNTIL:{locked_until}"

    return True, "OK"

def authorize_machine(fp):
    """One-time machine authorization"""
    auth_db_init()
    conn = sqlite3.connect(AUTH_DB)
    now  = datetime.utcnow().isoformat()
    try:
        conn.execute("""
            INSERT INTO authorized_machines
                (fingerprint, hostname, authorized_at, last_seen)
            VALUES (?, ?, ?, ?)
        """, (fp, os.uname().nodename, now, now))
        conn.commit()
        print(f"[PHOENIX_AUTH] Machine authorized: {fp[:16]}...")
    except sqlite3.IntegrityError:
        conn.execute(
            "UPDATE authorized_machines SET last_seen=? WHERE fingerprint=?",
            (now, fp)
        )
        conn.commit()
    conn.close()

def record_failed_attempt(fp):
    auth_db_init()
    conn = sqlite3.connect(AUTH_DB)
    row = conn.execute(
        "SELECT attempt_count FROM authorized_machines WHERE fingerprint=?",
        (fp,)
    ).fetchone()

    attempts = (row[0] if row else 0) + 1
    lockout_secs = LOCKOUT_BASE * (2 ** (attempts - 1))
    locked_until = None

    if attempts >= MAX_ATTEMPTS:
        from datetime import timedelta
        locked_until = (
            datetime.utcnow() + timedelta(seconds=lockout_secs)
        ).isoformat()
        print(f"[PHOENIX_AUTH] Lockout: {lockout_secs}s")

    if row:
        conn.execute("""
            UPDATE authorized_machines
            SET attempt_count=?, locked_until=?
            WHERE fingerprint=?
        """, (attempts, locked_until, fp))
    conn.commit()
    conn.close()

# ── Main Auth Flow ───────────────────────────────────────────
def authenticate():
    print(f"[PHOENIX_AUTH] v{VERSION} — Hardware fingerprint check")
    signals = get_hw_signals()
    fp      = fingerprint(signals)
    print(f"[PHOENIX_AUTH] Fingerprint: {fp[:32]}...")

    authorized, reason = is_authorized(fp)

    if authorized:
        authorize_machine(fp)  # update last_seen
        print(f"[PHOENIX_AUTH] AUTHORIZED")
        return True
    elif reason == "NOT_REGISTERED":
        print(f"[PHOENIX_AUTH] New machine — registering...")
        authorize_machine(fp)
        print(f"[PHOENIX_AUTH] AUTHORIZED (first run)")
        return True
    else:
        print(f"[PHOENIX_AUTH] DENIED — {reason}")
        record_failed_attempt(fp)
        return False

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description=f"Phoenix Hardware Auth v{VERSION}"
    )
    parser.add_argument("--check",  action="store_true", help="Auth check only")
    parser.add_argument("--status", action="store_true", help="Show auth DB")
    args = parser.parse_args()

    if args.status:
        auth_db_init()
        conn = sqlite3.connect(AUTH_DB)
        rows = conn.execute(
            "SELECT hostname, authorized_at, last_seen, attempt_count FROM authorized_machines"
        ).fetchall()
        for r in rows:
            print(f"  host={r[0]} auth={r[1]} last={r[2]} attempts={r[3]}")
        conn.close()
    else:
        result = authenticate()
        sys.exit(0 if result else 1)
