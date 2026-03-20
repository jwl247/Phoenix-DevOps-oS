#!/usr/bin/env python3
# ============================================================
# romeo.py — Ingress Handler
# Project:   Phoenix DevOps / Full Propagator Framework
# Author:    jwl247 / Phoenix DevOps LLC
# License:   GPL-3.0
# ============================================================
# Romeo handles all ingress. Manages the opt2 mount
# structure, validates incoming payloads, and hands off
# to Juliet for execution. Everything quadralingual on
# ingress — no translation until platform boundary.
#
# Romeo provides:
#   - opt2 mount verification
#   - Ingress payload validation
#   - Catalog logging on receipt
#   - ZMQ PUSH to Juliet execution queue
# ============================================================

import os
import sys
import json
import logging
import sqlite3
import threading
import zmq
from datetime import datetime
from pathlib import Path

CATALOG_DB      = os.path.expanduser("~/.catalog/catalog.db")
LOG_DIR         = os.path.expanduser("~/.unitedsys/logs")
LOG_FILE        = os.path.join(LOG_DIR, "romeo.log")
VERSION         = "2.0.0"

# Ports
ROMEO_RECV_PORT = 5580   # inbound from propagator/quadengine
ROMEO_SEND_PORT = 5581   # outbound to Juliet

# opt2 mount structure
OPT2_BASE       = "/opt2"
OPT2_VMCOMS     = "/opt2/VMCOMS"
OPT2_JULIET     = "/opt2/VMCOMS/julietshouse"
OPT2_ROMEO      = "/opt2/VMCOMS/romeoshouse"

os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [ROMEO] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger("romeo")

# ── Catalog ──────────────────────────────────────────────────
def catalog_init():
    conn = sqlite3.connect(CATALOG_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS romeo_ingress (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   TEXT NOT NULL,
            msg_id      TEXT,
            msg_type    TEXT,
            source      TEXT,
            payload     TEXT,
            opt2_status TEXT,
            status      TEXT
        )
    """)
    conn.commit()
    conn.close()

def catalog_log(msg_id, msg_type, source, payload, opt2_status, status="OK"):
    try:
        conn = sqlite3.connect(CATALOG_DB)
        conn.execute("""
            INSERT INTO romeo_ingress
                (timestamp, msg_id, msg_type, source, payload, opt2_status, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.utcnow().isoformat(),
            msg_id, msg_type, source,
            json.dumps(payload) if payload else None,
            opt2_status, status
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        log.error(f"Catalog write failed: {e}")

# ── opt2 Mount Check ─────────────────────────────────────────
def check_opt2():
    """Verify opt2 mount structure is intact"""
    paths = [OPT2_BASE, OPT2_VMCOMS, OPT2_JULIET, OPT2_ROMEO]
    status = {}
    for p in paths:
        exists = os.path.exists(p)
        status[p] = "OK" if exists else "MISSING"
        if not exists:
            log.warning(f"opt2 path missing: {p}")
            try:
                os.makedirs(p, exist_ok=True)
                status[p] = "CREATED"
                log.info(f"opt2 path created: {p}")
            except Exception as e:
                log.error(f"Cannot create {p}: {e}")
                status[p] = f"FAIL:{e}"
    return status

# ── Payload Validator ────────────────────────────────────────
def validate_payload(msg):
    """
    Validate incoming payload before handing to Juliet.
    Returns (valid, reason)
    """
    required = ["type", "id"]
    for field in required:
        if field not in msg:
            return False, f"missing field: {field}"

    if not isinstance(msg.get("id"), (str, int)):
        return False, "invalid id type"

    # Reject anything trying to inject translation prematurely
    if msg.get("pre_translated"):
        return False, "pre-translated payload rejected — translation is output only"

    return True, "OK"

# ── Romeo Ingress Handler ────────────────────────────────────
class Romeo:
    def __init__(self, stop_event):
        self.stop_event  = stop_event
        self.context     = zmq.Context()
        self.msg_count   = 0
        self.opt2_status = {}

    def run(self):
        recv_sock = self.context.socket(zmq.PULL)
        send_sock = self.context.socket(zmq.PUSH)

        recv_sock.bind(f"tcp://*:{ROMEO_RECV_PORT}")
        send_sock.connect(f"tcp://localhost:{ROMEO_SEND_PORT}")
        recv_sock.setsockopt(zmq.RCVTIMEO, 1000)

        catalog_init()
        self.opt2_status = check_opt2()

        log.info(f"Romeo v{VERSION} — ingress active")
        log.info(f"  Listening : :{ROMEO_RECV_PORT}")
        log.info(f"  → Juliet  : :{ROMEO_SEND_PORT}")
        log.info(f"  opt2      : {self.opt2_status}")

        while not self.stop_event.is_set():
            try:
                msg = recv_sock.recv_json()
                self.msg_count += 1

                log.info(f"Ingress #{self.msg_count} — "
                        f"type={msg.get('type','?')} id={msg.get('id','?')}")

                # Validate
                valid, reason = validate_payload(msg)
                if not valid:
                    log.warning(f"Rejected: {reason}")
                    catalog_log(
                        msg.get("id","?"), msg.get("type","?"),
                        msg.get("source","?"), msg,
                        str(self.opt2_status), f"REJECTED:{reason}"
                    )
                    continue

                # Tag for Juliet
                msg["romeo_ts"]       = datetime.utcnow().isoformat()
                msg["romeo_count"]    = self.msg_count
                msg["opt2_verified"]  = all(
                    v in ("OK","CREATED")
                    for v in self.opt2_status.values()
                )

                # Log ingress
                catalog_log(
                    msg["id"], msg["type"],
                    msg.get("source","unknown"), msg,
                    str(self.opt2_status)
                )

                # Hand to Juliet
                send_sock.send_json(msg)
                log.info(f"→ Juliet: {msg['id']}")

            except zmq.Again:
                continue
            except Exception as e:
                log.error(f"Romeo error: {e}")

        recv_sock.close()
        send_sock.close()
        log.info("Romeo stopped")

    def status(self):
        return {
            "version":    VERSION,
            "msg_count":  self.msg_count,
            "opt2":       self.opt2_status,
        }

# ── Entry ────────────────────────────────────────────────────
def main():
    import argparse
    parser = argparse.ArgumentParser(
        description=f"Romeo v{VERSION} — ingress handler"
    )
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()

    stop_event = threading.Event()
    romeo = Romeo(stop_event)

    if args.status:
        romeo.opt2_status = check_opt2()
        print(json.dumps(romeo.status(), indent=2))
        return

    t = threading.Thread(target=romeo.run, daemon=True)
    t.start()

    try:
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        stop_event.set()
        t.join(timeout=5)

if __name__ == "__main__":
    main()
