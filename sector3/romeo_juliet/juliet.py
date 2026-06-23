#!/usr/bin/env python3
# ============================================================
# juliet.py — Execution Runner / Egress Handler
# Project:   Phoenix DevOps / Full Propagator Framework
# Author:    jwl247 / Phoenix DevOps LLC
# License:   GPL-3.0
# ============================================================
# Juliet is the execution runner. Receives from Romeo,
# executes the payload, then handles egress — translation
# fires HERE at the platform boundary on output only.
# Everything was quadralingual until this moment.
#
# Juliet provides:
#   - Payload execution
#   - Platform boundary detection
#   - Translation on output (calls translator.sh)
#   - Egress logging to catalog.db
#   - ZMQ PUSH result back up the chain
#
# Commands (Double-Barrel mode):
#   load1-9    single barrel load
#   load1a/1b  split barrel
#   stop1-9    fire
#   stat1-9    status
# ============================================================

import os
import sys
import json
import logging
import sqlite3
import threading
import subprocess
import zmq
from datetime import datetime

CATALOG_DB       = os.path.expanduser("~/.catalog/catalog.db")
LOG_DIR          = os.path.expanduser("~/.unitedsys/logs")
LOG_FILE         = os.path.join(LOG_DIR, "juliet.log")
TRANSLATOR_SH    = "/etc/systemd/system/translator.sh"
TRANSLATOR_FALLBACK = os.path.expanduser("~/projects/phoenix/translator/translator.sh")
VERSION          = "2.0.0"

# Ports
JULIET_RECV_PORT = 5581   # inbound from Romeo
JULIET_SEND_PORT = 5582   # egress outbound

os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [JULIET] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger("juliet")

# ── Catalog ──────────────────────────────────────────────────
def catalog_init():
    conn = sqlite3.connect(CATALOG_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS juliet_egress (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp    TEXT NOT NULL,
            msg_id       TEXT,
            msg_type     TEXT,
            platform     TEXT,
            translated   INTEGER,
            exec_result  TEXT,
            status       TEXT
        )
    """)
    conn.commit()
    conn.close()

def catalog_log(msg_id, msg_type, platform, translated, exec_result, status="OK"):
    try:
        conn = sqlite3.connect(CATALOG_DB)
        conn.execute("""
            INSERT INTO juliet_egress
                (timestamp, msg_id, msg_type, platform, translated, exec_result, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.utcnow().isoformat(),
            msg_id, msg_type, platform,
            1 if translated else 0,
            exec_result, status
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        log.error(f"Catalog write failed: {e}")

# ── Translator Bridge ────────────────────────────────────────
def call_translator(verb, package=""):
    """
    Call translator.sh at platform boundary.
    This is the ONLY place translation fires — output only.
    """
    translator = TRANSLATOR_SH
    if not os.path.exists(translator):
        translator = TRANSLATOR_FALLBACK
    if not os.path.exists(translator):
        log.warning("translator.sh not found — passthrough mode")
        return f"{verb} {package}".strip(), False

    cmd = [translator, verb]
    if package:
        cmd.append(package)

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30
        )
        return result.stdout.strip(), True
    except Exception as e:
        log.error(f"Translator error: {e}")
        return f"{verb} {package}".strip(), False

# ── Executor ─────────────────────────────────────────────────
def execute_payload(msg):
    """
    Execute payload. Returns (result, translated, platform)
    Translation fires here on output — nowhere else.
    """
    msg_type = msg.get("type", "unknown")
    verb     = msg.get("verb", "list")
    package  = msg.get("package", "")
    platform = msg.get("platform", "auto")

    log.info(f"Executing: type={msg_type} verb={verb} pkg={package}")

    # Check if this needs platform translation on output
    needs_translation = msg_type in (
        "package_install", "package_remove", "package_update",
        "package_upgrade", "package_search", "package_info",
        "package_list", "package_clean"
    )

    if needs_translation:
        result, translated = call_translator(verb, package)
        log.info(f"Translated output: {result[:80]}...")
        return result, translated, platform
    else:
        # Quadralingual passthrough — no translation needed
        result = json.dumps(msg)
        log.info(f"Quad passthrough: {msg_type}")
        return result, False, "quad"

# ── Juliet Execution Runner ──────────────────────────────────
class Juliet:
    def __init__(self, stop_event, barrel_id=1):
        self.stop_event = stop_event
        self.barrel_id  = barrel_id   # 1 = single, 2 = double-barrel instance
        self.context    = zmq.Context()
        self.msg_count  = 0
        self.loaded     = [False] * 9  # load1-9 state

    def run(self):
        recv_sock = self.context.socket(zmq.PULL)
        send_sock = self.context.socket(zmq.PUSH)

        recv_sock.bind(f"tcp://*:{JULIET_RECV_PORT + (self.barrel_id - 1)}")
        send_sock.bind(f"tcp://*:{JULIET_SEND_PORT + (self.barrel_id - 1)}")
        recv_sock.setsockopt(zmq.RCVTIMEO, 1000)

        catalog_init()

        log.info(f"Juliet v{VERSION} barrel={self.barrel_id} — execution runner active")
        log.info(f"  Listening : :{JULIET_RECV_PORT + (self.barrel_id - 1)}")
        log.info(f"  Egress    : :{JULIET_SEND_PORT + (self.barrel_id - 1)}")
        log.info(f"  Commands  : load1-9 | stop1-9 | stat1-9")

        while not self.stop_event.is_set():
            try:
                msg = recv_sock.recv_json()
                self.msg_count += 1

                log.info(f"[barrel={self.barrel_id}] Received #{self.msg_count} "
                        f"— {msg.get('type','?')} id={msg.get('id','?')}")

                # Execute
                result, translated, platform = execute_payload(msg)

                # Build egress payload
                egress = {
                    "id":           msg.get("id"),
                    "type":         msg.get("type"),
                    "barrel":       self.barrel_id,
                    "result":       result,
                    "translated":   translated,
                    "platform":     platform,
                    "juliet_ts":    datetime.utcnow().isoformat(),
                    "juliet_count": self.msg_count,
                    "romeo_ts":     msg.get("romeo_ts"),
                    "com_hops":     msg.get("com_hops", []),
                }

                # Log egress
                catalog_log(
                    msg.get("id"), msg.get("type"),
                    platform, translated,
                    result[:256]
                )

                # Send egress
                send_sock.send_json(egress)
                log.info(f"[barrel={self.barrel_id}] Egress: "
                        f"id={egress['id']} translated={translated}")

            except zmq.Again:
                continue
            except Exception as e:
                log.error(f"Juliet barrel={self.barrel_id} error: {e}")

        recv_sock.close()
        send_sock.close()
        log.info(f"Juliet barrel={self.barrel_id} stopped")

    def load(self, slot):
        """load1-9 — arm a barrel slot"""
        if 1 <= slot <= 9:
            self.loaded[slot - 1] = True
            log.info(f"[barrel={self.barrel_id}] load{slot} armed")

    def fire(self, slot):
        """stop1-9 — fire a barrel slot"""
        if 1 <= slot <= 9 and self.loaded[slot - 1]:
            self.loaded[slot - 1] = False
            log.info(f"[barrel={self.barrel_id}] stop{slot} fired")
            return True
        return False

    def stat(self, slot):
        """stat1-9 — status of a barrel slot"""
        if 1 <= slot <= 9:
            return self.loaded[slot - 1]
        return False

    def status(self):
        return {
            "version":   VERSION,
            "barrel_id": self.barrel_id,
            "msg_count": self.msg_count,
            "loaded":    self.loaded,
        }

# ── Entry ────────────────────────────────────────────────────
def main():
    import argparse
    import time
    parser = argparse.ArgumentParser(
        description=f"Juliet v{VERSION} — execution runner"
    )
    parser.add_argument("--barrel", type=int, default=1,
                       help="Barrel ID (1=single, 2=double-barrel instance)")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()

    stop_event = threading.Event()
    juliet = Juliet(stop_event, barrel_id=args.barrel)

    if args.status:
        print(json.dumps(juliet.status(), indent=2))
        return

    t = threading.Thread(target=juliet.run, daemon=True)
    t.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        stop_event.set()
        t.join(timeout=5)

if __name__ == "__main__":
    main()
