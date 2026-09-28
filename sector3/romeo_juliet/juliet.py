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
# The boundary translator (sector3/translator/translator.sh) as deployed:
# TRANSLATOR_SH env first, then the repo at /opt/phoenix (Compaq/pbm3), then
# the repo this file sits in, then the two legacy locations.
_HERE = os.path.dirname(os.path.abspath(__file__))
TRANSLATOR_SH    = os.environ.get("TRANSLATOR_SH") or "/opt/phoenix/sector3/translator/translator.sh"
TRANSLATOR_FALLBACK = os.path.join(_HERE, "..", "translator", "translator.sh")
TRANSLATOR_LEGACY = ["/etc/systemd/system/translator.sh",
                     os.path.expanduser("~/projects/phoenix/translator/translator.sh")]
VERSION          = "2.0.0"

# Ports
JULIET_RECV_PORT = 5581   # inbound from Romeo
JULIET_SEND_PORT = 5582   # egress outbound
# Listeners are unauthenticated (plain ZMQ PULL -> package install/remove via
# translator.sh), so they bind to loopback only. Every in-tree peer
# (romeo->juliet, dbl_juliet, quadengine) connects via localhost. Widen only
# deliberately, e.g. PHOENIX_RJ_BIND=0.0.0.0, and only behind real auth.
BIND_ADDR = os.environ.get("PHOENIX_RJ_BIND", "127.0.0.1")
# Peered hop auth (see romeo.py): with PHOENIX_RJ_SECRET set, every message
# must carry a valid HMAC-SHA256 `sig`; without it Juliet only ever binds
# loopback. Binding elsewhere without a secret is refused at start.
RJ_SECRET = os.environ.get("PHOENIX_RJ_SECRET", "")
_LOOPBACK = ("127.0.0.1", "localhost", "::1")


RJ_MAX_SKEW_S = int(os.environ.get("PHOENIX_RJ_MAX_SKEW", "300"))
_recent_ids = {}          # id -> monotonic time first seen (replay guard, RJ_MAX_SKEW window)


def verify_signature(msg, secret):
    """Valid HMAC over the canonical body, romeo_ts within RJ_MAX_SKEW_S of now,
    and an id not seen in that window: a captured message cannot be replayed."""
    import hmac, hashlib, time
    sig = msg.get("sig")
    if not isinstance(sig, str):
        return False
    body = {k: v for k, v in msg.items() if k != "sig"}
    canon = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode()
    want = hmac.new(secret.encode(), canon, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, want):
        return False
    try:
        ts = datetime.fromisoformat(str(msg.get("romeo_ts")))
    except (TypeError, ValueError):
        return False
    if abs((datetime.utcnow() - ts).total_seconds()) > RJ_MAX_SKEW_S:
        return False
    now = time.monotonic()
    for k in [k for k, t in _recent_ids.items() if now - t > RJ_MAX_SKEW_S]:
        del _recent_ids[k]
    key = str(msg.get("id"))
    if key in _recent_ids:
        return False
    _recent_ids[key] = now
    return True


def barrel_ports(barrel_id):
    """Barrel N listens on 5581+2(N-1) and emits on 5582+2(N-1): barrel 1 =
    5581/5582, barrel 2 = 5583/5584. Before 2026-09-28 barrel 1's emit port
    and barrel 2's listen port were both 5582, so the double barrel could
    never start."""
    off = 2 * (barrel_id - 1)
    return JULIET_RECV_PORT + off, JULIET_SEND_PORT + off

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
    os.makedirs(os.path.dirname(CATALOG_DB), exist_ok=True)
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
    translator = next((c for c in [TRANSLATOR_SH, TRANSLATOR_FALLBACK, *TRANSLATOR_LEGACY]
                       if os.path.exists(c)), None)
    if translator is None:
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
        self.rejected   = 0
        self.loaded     = [False] * 9  # load1-9 state

    def run(self):
        recv_sock = self.context.socket(zmq.PULL)
        send_sock = self.context.socket(zmq.PUSH)

        if BIND_ADDR not in _LOOPBACK and not RJ_SECRET:
            log.error(f"refusing to bind {BIND_ADDR} without PHOENIX_RJ_SECRET (unauthenticated package execution)")
            self.stop_event.set()
            return
        recv_port, send_port = barrel_ports(self.barrel_id)
        recv_sock.bind(f"tcp://{BIND_ADDR}:{recv_port}")
        send_sock.bind(f"tcp://{BIND_ADDR}:{send_port}")
        recv_sock.setsockopt(zmq.RCVTIMEO, 1000)
        send_sock.setsockopt(zmq.LINGER, 2000)

        catalog_init()

        log.info(f"Juliet v{VERSION} barrel={self.barrel_id} — execution runner active")
        log.info(f"  Listening : {BIND_ADDR}:{recv_port} ({'signed messages only' if RJ_SECRET else 'unsigned, loopback'})")
        log.info(f"  Egress    : {BIND_ADDR}:{send_port}")
        log.info(f"  Commands  : load1-9 | stop1-9 | stat1-9")

        while not self.stop_event.is_set():
            try:
                msg = recv_sock.recv_json()
                self.msg_count += 1

                log.info(f"[barrel={self.barrel_id}] Received #{self.msg_count} "
                        f"— {msg.get('type','?')} id={msg.get('id','?')}")

                if RJ_SECRET and not verify_signature(msg, RJ_SECRET):
                    self.rejected += 1
                    log.warning(f"[barrel={self.barrel_id}] REJECTED id={msg.get('id','?')}: bad or missing signature")
                    catalog_log(msg.get("id"), msg.get("type"), "rejected", False, "REJECTED:signature")
                    continue

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

    import signal
    signal.signal(signal.SIGTERM, lambda *_: stop_event.set())   # systemd / run-team.sh stop
    try:
        while not stop_event.is_set() and t.is_alive():
            time.sleep(1)
    except KeyboardInterrupt:
        stop_event.set()
    t.join(timeout=5)
    if not stop_event.is_set():
        # the worker died on its own (exception in run()): the process must not
        # sit here looking alive while nothing is listening
        log.error("worker thread died; exiting 1")
        sys.exit(1)

if __name__ == "__main__":
    main()
