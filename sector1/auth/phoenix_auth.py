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
import platform
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


# ── CoPES guardian feed ─────────────────────────────────────────────────────
# Auth is GuardianAlpha's event source. Best-effort only: if the guardian
# layer isn't importable or isn't armed, dispatch() no-ops. Auth must never
# break because of the security layer.
def _guardian(event_type, **fields):
    try:
        from pathlib import Path as _P
        _s = str(_P(__file__).resolve().parent.parent)   # sector1/
        if _s not in sys.path:
            sys.path.insert(0, _s)
        from security import copes_runtime
        copes_runtime.dispatch({"type": event_type, **fields})
    except Exception:
        pass

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

    def only_lines(text, prefixes):
        # Keep only stable fields. Raw /proc/cpuinfo ("cpu MHz"), /proc/meminfo
        # (MemFree...), full lsblk (USB sticks) and `uname -r` (kernel updates)
        # change run to run, which made every call a "new machine".
        keep = sorted({l.strip() for l in text.splitlines()
                       if l.split(":", 1)[0].strip() in prefixes})
        return "\n".join(keep) or "unavailable"

    cpuinfo = safe_read(["cat", "/proc/cpuinfo"])

    # 1. CPU identity (model, not live clock speed)
    signals.append(only_lines(cpuinfo, {"vendor_id", "cpu family", "model",
                                        "model name", "stepping"}))
    # 2. Machine ID
    signals.append(safe_read(["cat", "/etc/machine-id"]))
    # 3. DMI board serial
    signals.append(safe_read(["cat", "/sys/class/dmi/id/board_serial"]))
    # 4. DMI product UUID
    signals.append(safe_read(["cat", "/sys/class/dmi/id/product_uuid"]))
    # 5. Fixed (non-removable) disk serials — removable media excluded
    disks = safe_read(["lsblk", "-dn", "-o", "SERIAL,RM"])
    signals.append("\n".join(sorted(
        l.rsplit(None, 1)[0] for l in disks.splitlines()
        if l.strip() and l.split()[-1] == "0" and len(l.split()) > 1
    )) or "unavailable")
    # 6. Network MACs of physical interfaces (eth0 rarely exists on modern
    #    Debian — predictable names like enp3s0)
    macs = []
    try:
        for dev in sorted(os.listdir("/sys/class/net")):
            if os.path.exists(f"/sys/class/net/{dev}/device"):
                with open(f"/sys/class/net/{dev}/address") as fh:
                    macs.append(fh.read().strip())
    except Exception:
        pass
    signals.append("\n".join(macs) or "unavailable")
    # 7. Total memory (not free/cached counters)
    signals.append(only_lines(safe_read(["cat", "/proc/meminfo"]), {"MemTotal"}))
    # 8. CPU serial (ARM/embedded)
    signals.append(only_lines(cpuinfo, {"Serial", "Hardware"}))
    # 9. DMI system vendor (was `uname -r` — changed on every kernel update)
    signals.append(safe_read(["cat", "/sys/class/dmi/id/sys_vendor"]))
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
        """, (fp, platform.node(), now, now))
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
        _guardian("auth_success", source=fp[:16])
        return True
    elif reason == "NOT_REGISTERED":
        print(f"[PHOENIX_AUTH] New machine — registering...")
        authorize_machine(fp)
        print(f"[PHOENIX_AUTH] AUTHORIZED (first run)")
        _guardian("auth_success", source=fp[:16], first_run=True)
        return True
    else:
        print(f"[PHOENIX_AUTH] DENIED — {reason}")
        record_failed_attempt(fp)
        _guardian("auth_failure", source=fp[:16], reason=reason)
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
