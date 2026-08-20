#!/usr/bin/env python3
# =============================================================================
# propagator.py — Phoenix DevOps Signal Propagator
# Author:  jwl247 / Phoenix DevOps LLC
# Sector:  2 (Backup/Buffer layer)
# Role:    Routes signals through COM4->COM1 chain, dispatches to all targets
#          defined in dispatch.json: vault, sql, d1, frank3, peer, windows
# =============================================================================

import json
import os
import sqlite3
import time
import logging
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime, timezone

ROOT          = Path(__file__).parent
DISPATCH      = ROOT / "dispatch.json"
CATALOG_DB    = Path.home() / ".catalog" / "catalog.db"
LOG_DIR       = Path.home() / ".unitedsys" / "logs"
LOG_FILE      = LOG_DIR / "propagator.log"
VERSION       = "0.1.0"
D1_WORKER_URL = os.environ.get("D1_WORKER_URL", "")

LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
)
log = logging.getLogger("propagator")


def load_dispatch():
    if not DISPATCH.exists():
        log.error(f"dispatch.json not found at {DISPATCH}")
        return {}
    with open(DISPATCH) as f:
        return json.load(f)


def get_db():
    CATALOG_DB.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(CATALOG_DB)
    db.execute("""CREATE TABLE IF NOT EXISTS propagator_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT, target TEXT, signal TEXT, status TEXT, detail TEXT)""")
    db.commit()
    return db


def catalog_log(db, target, signal, status, detail=""):
    db.execute(
        "INSERT INTO propagator_log (timestamp,target,signal,status,detail) VALUES (?,?,?,?,?)",
        (datetime.now(timezone.utc).isoformat(), target, signal, status, detail))
    db.commit()


def dispatch_vault(cfg, signal, db):
    vault_path = Path(cfg.get("path", "/mnt/e/CLONEPOOL")).expanduser()
    try:
        vault_path.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out = vault_path / f"signal_{ts}.json"
        out.write_text(json.dumps(signal, indent=2))
        log.info(f"[vault] written -> {out}")
        catalog_log(db, "vault", signal.get("id", "?"), "OK", str(out))
    except Exception as e:
        log.warning(f"[vault] FAILED: {e}")
        catalog_log(db, "vault", signal.get("id", "?"), "FAIL", str(e))


def dispatch_sql(cfg, signal, db):
    try:
        db.execute("""CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT, signal_id TEXT, payload TEXT)""")
        db.execute("INSERT INTO signals (timestamp,signal_id,payload) VALUES (?,?,?)",
            (datetime.now(timezone.utc).isoformat(), signal.get("id", ""), json.dumps(signal)))
        db.commit()
        log.info("[sql] signal logged to catalog.db")
        catalog_log(db, "sql", signal.get("id", "?"), "OK")
    except Exception as e:
        log.warning(f"[sql] FAILED: {e}")
        catalog_log(db, "sql", signal.get("id", "?"), "FAIL", str(e))


def dispatch_d1(cfg, signal, db):
    if not D1_WORKER_URL:
        log.warning("[d1] D1_WORKER_URL not set -- skipping")
        catalog_log(db, "d1", signal.get("id", "?"), "SKIP", "D1_WORKER_URL not set")
        return
    try:
        payload = json.dumps(signal).encode()
        req = urllib.request.Request(D1_WORKER_URL, data=payload,
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            log.info(f"[d1] pushed -> {resp.status}")
            catalog_log(db, "d1", signal.get("id", "?"), "OK", str(resp.status))
    except Exception as e:
        log.warning(f"[d1] FAILED: {e}")
        catalog_log(db, "d1", signal.get("id", "?"), "FAIL", str(e))


def dispatch_frank3(cfg, signal, db):
    port = cfg.get("zmq_port", 5555)
    try:
        import zmq
        ctx = zmq.Context.instance()
        sock = ctx.socket(zmq.PUSH)
        sock.connect(f"tcp://127.0.0.1:{port}")
        sock.send_json(signal)
        sock.close()
        log.info(f"[frank3] pushed -> zmq port {port}")
        catalog_log(db, "frank3", signal.get("id", "?"), "OK", f"port {port}")
    except ImportError:
        log.info("[frank3] zmq not installed -- logging only")
        catalog_log(db, "frank3", signal.get("id", "?"), "SKIP", "zmq not installed")
    except Exception as e:
        log.warning(f"[frank3] FAILED: {e}")
        catalog_log(db, "frank3", signal.get("id", "?"), "FAIL", str(e))


def dispatch_peer(cfg, signal, db):
    port = cfg.get("zmq_port", 5560)
    try:
        import zmq
        ctx = zmq.Context.instance()
        sock = ctx.socket(zmq.PUSH)
        sock.connect(f"tcp://127.0.0.1:{port}")
        sock.send_json(signal)
        sock.close()
        log.info(f"[peer] pushed -> zmq port {port}")
        catalog_log(db, "peer", signal.get("id", "?"), "OK", f"port {port}")
    except ImportError:
        log.info("[peer] zmq not installed -- logging only")
        catalog_log(db, "peer", signal.get("id", "?"), "SKIP", "zmq not installed")
    except Exception as e:
        log.warning(f"[peer] FAILED: {e}")
        catalog_log(db, "peer", signal.get("id", "?"), "FAIL", str(e))


def dispatch_windows(cfg, signal, db):
    log.info("[windows] routing via translator -- signal queued")
    catalog_log(db, "windows", signal.get("id", "?"), "QUEUED", "translator")


DISPATCHERS = {
    "vault":   dispatch_vault,
    "sql":     dispatch_sql,
    "d1":      dispatch_d1,
    "frank3":  dispatch_frank3,
    "peer":    dispatch_peer,
    "windows": dispatch_windows,
}
COM_CHAIN = ["COM4", "COM3", "COM2", "COM1"]


def run_com_chain(signal, db):
    log.info("COM chain: COM4 -> COM3 -> COM2 -> COM1")
    for com in COM_CHAIN:
        catalog_log(db, com, signal.get("id", "?"), "RELAY")
        time.sleep(0.05)
    log.info("COM chain complete")


def propagate(signal):
    cfg = load_dispatch()
    if not cfg:
        log.error("No dispatch config -- abort")
        return
    db = get_db()
    log.info(f"propagator v{VERSION} -- signal {signal.get('id', '?')}")
    run_com_chain(signal, db)
    for name, target_cfg in cfg.get("targets", {}).items():
        if not target_cfg.get("active", False):
            continue
        fn = DISPATCHERS.get(name)
        if fn:
            fn(target_cfg, signal, db)
    db.close()
    log.info(f"propagation complete -- {signal.get('id', '?')}")


if __name__ == "__main__":
    import sys
    import hashlib

    if len(sys.argv) < 2 or sys.argv[1] == "help":
        print(f"propagator.py v{VERSION}")
        print("Usage:")
        print("  python3 propagator.py <payload>   propagate a signal")
        print("  python3 propagator.py status      show dispatch config")
        sys.exit(0)

    if sys.argv[1] == "status":
        print(json.dumps(load_dispatch(), indent=2))
        sys.exit(0)

    raw = " ".join(sys.argv[1:])
    sig_id = hashlib.sha3_256(raw.encode()).hexdigest()[:16]
    propagate({
        "id":        sig_id,
        "payload":   raw,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source":    "cli",
    })
