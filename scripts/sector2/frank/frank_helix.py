#!/usr/bin/env python3
# ============================================================
# frank_helix.py — Frank3 Bridge / RAM Management Daemon
# Project:   Phoenix DevOps / Full Propagator Framework
# Author:    jwl247 / Phoenix DevOps LLC
# License:   GPL-3.0
# ============================================================
# ARCHITECTURE:
#   Frank sits as the input interceptor (kvmfrank) with
#   L1/L2/L3 Helix tier management. Pressure thresholds
#   at 60/75/88% trigger tier escalation. Keepalive monitor
#   uses threading.Event.wait(). Sideload option allows
#   Frank-to-Frank bridging across peer nodes (WSL2/Win10).
#
# TIERS:
#   L1 — Hot cache  (below 60% pressure)
#   L2 — Warm pool  (60–75% pressure)
#   L3 — Cold store (75–88% pressure)
#   CRITICAL — above 88%, emergency flush to vault
#
# SIDELOAD:
#   Frank-to-Frank direct bridge via ZeroMQ PUSH/PULL
#   Used for peer node handoff without going through
#   the full propagator chain. Quadralingual until
#   platform boundary — translator.sh handles the edge.
# ============================================================

import os
import sys
import time
import threading
import logging
import sqlite3
import psutil
import zmq
import json
from datetime import datetime
from pathlib import Path

# ── Config ───────────────────────────────────────────────────
CATALOG_DB      = os.path.expanduser("~/.catalog/catalog.db")
LOG_DIR         = os.path.expanduser("~/.unitedsys/logs")
LOG_FILE        = os.path.join(LOG_DIR, "frank_helix.log")
VAULT_PATH      = "/media/jwl247/breach_coms2/CLONEPOOL"
VERSION         = "0.3.0"

# Pressure thresholds (percent RAM used)
L1_THRESHOLD    = 60    # below this = L1 hot cache
L2_THRESHOLD    = 75    # 60-75 = L2 warm pool
L3_THRESHOLD    = 88    # 75-88 = L3 cold store
CRITICAL_THRESHOLD = 88 # above this = emergency flush

# ZeroMQ ports
FRANK_RECV_PORT = 5555  # inbound from propagator / peers
FRANK_SEND_PORT = 5556  # outbound to Jupyter / peers
SIDELOAD_PORT   = 5557  # Frank-to-Frank direct bridge

# Keepalive
KEEPALIVE_INTERVAL = 30  # seconds between heartbeats
POLL_INTERVAL      = 5   # seconds between pressure checks

# ── Bootstrap ────────────────────────────────────────────────
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(os.path.dirname(CATALOG_DB), exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger("frank_helix")

# ── Catalog ──────────────────────────────────────────────────
def catalog_init():
    conn = sqlite3.connect(CATALOG_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS frank_events (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   TEXT    NOT NULL,
            event_type  TEXT    NOT NULL,
            tier        TEXT,
            pressure    REAL,
            payload     TEXT,
            peer        TEXT,
            status      TEXT
        )
    """)
    conn.commit()
    conn.close()

def catalog_log(event_type, tier=None, pressure=None, payload=None, peer=None, status="OK"):
    try:
        conn = sqlite3.connect(CATALOG_DB)
        conn.execute("""
            INSERT INTO frank_events
                (timestamp, event_type, tier, pressure, payload, peer, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.utcnow().isoformat(),
            event_type,
            tier,
            pressure,
            json.dumps(payload) if payload else None,
            peer,
            status
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        log.error(f"Catalog write failed: {e}")

# ── Pressure Monitor ─────────────────────────────────────────
class PressureMonitor:
    def __init__(self, stop_event):
        self.stop_event = stop_event
        self.current_tier = "L1"
        self.current_pressure = 0.0

    def get_pressure(self):
        mem = psutil.virtual_memory()
        return mem.percent

    def get_tier(self, pressure):
        if pressure < L1_THRESHOLD:
            return "L1"
        elif pressure < L2_THRESHOLD:
            return "L2"
        elif pressure < L3_THRESHOLD:
            return "L3"
        else:
            return "CRITICAL"

    def run(self):
        log.info("PressureMonitor started")
        while not self.stop_event.wait(POLL_INTERVAL):
            pressure = self.get_pressure()
            tier = self.get_tier(pressure)

            if tier != self.current_tier:
                log.warning(f"Tier transition: {self.current_tier} → {tier} @ {pressure:.1f}%")
                catalog_log("TIER_CHANGE", tier=tier, pressure=pressure)

                if tier == "CRITICAL":
                    log.critical(f"CRITICAL pressure {pressure:.1f}% — initiating emergency flush")
                    self.emergency_flush()

            self.current_tier = tier
            self.current_pressure = pressure

        log.info("PressureMonitor stopped")

    def emergency_flush(self):
        """Flush L3 contents to vault on critical pressure"""
        try:
            flush_path = os.path.join(VAULT_PATH, f"flush_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}")
            os.makedirs(flush_path, exist_ok=True)
            log.warning(f"Emergency flush target: {flush_path}")
            catalog_log("EMERGENCY_FLUSH", tier="CRITICAL",
                       pressure=self.current_pressure,
                       payload={"flush_path": flush_path})
        except Exception as e:
            log.error(f"Emergency flush failed: {e}")
            catalog_log("EMERGENCY_FLUSH", status=f"FAIL:{e}")

# ── Keepalive Monitor ────────────────────────────────────────
class KeepaliveMonitor:
    def __init__(self, stop_event):
        self.stop_event = stop_event
        self.heartbeat_count = 0

    def run(self):
        log.info("KeepaliveMonitor started")
        while not self.stop_event.wait(KEEPALIVE_INTERVAL):
            self.heartbeat_count += 1
            log.info(f"[HEARTBEAT #{self.heartbeat_count}] Frank alive — "
                    f"{datetime.utcnow().isoformat()}")
            catalog_log("HEARTBEAT", payload={"count": self.heartbeat_count})
        log.info("KeepaliveMonitor stopped")

# ── ZeroMQ Router ────────────────────────────────────────────
class FrankRouter:
    def __init__(self, stop_event, pressure_monitor):
        self.stop_event = stop_event
        self.pressure_monitor = pressure_monitor
        self.context = zmq.Context()

    def run(self):
        recv_sock = self.context.socket(zmq.PULL)
        send_sock = self.context.socket(zmq.PUSH)

        recv_sock.bind(f"tcp://*:{FRANK_RECV_PORT}")
        send_sock.bind(f"tcp://*:{FRANK_SEND_PORT}")

        recv_sock.setsockopt(zmq.RCVTIMEO, 1000)  # 1s timeout for clean shutdown

        log.info(f"FrankRouter listening on :{FRANK_RECV_PORT} → :{FRANK_SEND_PORT}")

        while not self.stop_event.is_set():
            try:
                msg = recv_sock.recv_json()
                tier = self.pressure_monitor.current_tier
                pressure = self.pressure_monitor.current_pressure

                log.info(f"[ROUTER] Received: {msg.get('type','unknown')} "
                        f"tier={tier} pressure={pressure:.1f}%")

                # Tag message with current tier before forwarding
                msg["frank_tier"]     = tier
                msg["frank_pressure"] = pressure
                msg["frank_ts"]       = datetime.utcnow().isoformat()

                send_sock.send_json(msg)
                catalog_log("ROUTE", tier=tier, pressure=pressure,
                           payload={"msg_type": msg.get("type")})

            except zmq.Again:
                continue  # timeout, check stop_event
            except Exception as e:
                log.error(f"Router error: {e}")

        recv_sock.close()
        send_sock.close()
        log.info("FrankRouter stopped")

# ── Sideload Bridge (Frank-to-Frank) ─────────────────────────
class SideloadBridge:
    """
    Direct Frank-to-Frank bridge for peer node handoff.
    Bypasses the full propagator chain for hot transfers.
    Everything stays quadralingual until platform boundary.
    translator.sh handles edge conversion on output.

    Usage:
        bridge = SideloadBridge(stop_event, peer_host="192.168.x.x")
        threading.Thread(target=bridge.run).start()
    """
    def __init__(self, stop_event, peer_host=None, mode="server"):
        self.stop_event  = stop_event
        self.peer_host   = peer_host
        self.mode        = mode   # "server" listens, "client" connects
        self.context     = zmq.Context()
        self.active      = False

    def run(self):
        sock = self.context.socket(zmq.PAIR)  # PAIR = bidirectional 1:1

        if self.mode == "server":
            sock.bind(f"tcp://*:{SIDELOAD_PORT}")
            log.info(f"[SIDELOAD] Server listening on :{SIDELOAD_PORT}")
        else:
            if not self.peer_host:
                log.error("[SIDELOAD] Client mode requires peer_host")
                return
            sock.connect(f"tcp://{self.peer_host}:{SIDELOAD_PORT}")
            log.info(f"[SIDELOAD] Connected to peer {self.peer_host}:{SIDELOAD_PORT}")

        sock.setsockopt(zmq.RCVTIMEO, 1000)
        self.active = True
        catalog_log("SIDELOAD_START", peer=self.peer_host,
                   payload={"mode": self.mode})

        while not self.stop_event.is_set():
            try:
                msg = sock.recv_json()
                log.info(f"[SIDELOAD] Received from peer: {msg.get('type','unknown')}")

                # Echo ACK back to peer
                ack = {
                    "type":   "sideload_ack",
                    "ts":     datetime.utcnow().isoformat(),
                    "status": "OK"
                }
                sock.send_json(ack)
                catalog_log("SIDELOAD_MSG", peer=self.peer_host,
                           payload=msg)

            except zmq.Again:
                continue
            except Exception as e:
                log.error(f"[SIDELOAD] Error: {e}")

        sock.close()
        self.active = False
        log.info("[SIDELOAD] Bridge stopped")

    def send(self, sock, payload):
        """Send payload to peer — call from client mode"""
        try:
            sock.send_json(payload)
            log.info(f"[SIDELOAD] Sent to peer: {payload.get('type','unknown')}")
        except Exception as e:
            log.error(f"[SIDELOAD] Send failed: {e}")

# ── Frank Daemon ─────────────────────────────────────────────
class FrankDaemon:
    def __init__(self, sideload_peer=None, sideload_mode="server"):
        self.stop_event      = threading.Event()
        self.pressure_mon    = PressureMonitor(self.stop_event)
        self.keepalive_mon   = KeepaliveMonitor(self.stop_event)
        self.router          = FrankRouter(self.stop_event, self.pressure_mon)
        self.sideload_bridge = SideloadBridge(
            self.stop_event,
            peer_host=sideload_peer,
            mode=sideload_mode
        )
        self.threads = []

    def start(self):
        log.info(f"Frank Helix Daemon v{VERSION} starting...")
        catalog_init()
        catalog_log("FRANK_START", payload={"version": VERSION})

        targets = [
            ("PressureMonitor", self.pressure_mon.run),
            ("KeepaliveMonitor", self.keepalive_mon.run),
            ("FrankRouter",     self.router.run),
            ("SideloadBridge",  self.sideload_bridge.run),
        ]

        for name, target in targets:
            t = threading.Thread(target=target, name=name, daemon=True)
            t.start()
            self.threads.append(t)
            log.info(f"  ✓ {name} started")

        log.info("Frank Helix Daemon — all systems nominal")

    def stop(self):
        log.info("Frank Helix Daemon shutting down...")
        self.stop_event.set()
        for t in self.threads:
            t.join(timeout=5)
        catalog_log("FRANK_STOP")
        log.info("Frank Helix Daemon stopped cleanly")

    def status(self):
        pressure = self.pressure_mon.current_pressure
        tier     = self.pressure_mon.current_tier
        return {
            "version":         VERSION,
            "tier":            tier,
            "pressure":        f"{pressure:.1f}%",
            "sideload_active": self.sideload_bridge.active,
            "sideload_peer":   self.sideload_bridge.peer_host,
            "heartbeats":      self.keepalive_mon.heartbeat_count,
        }

# ── Entry ────────────────────────────────────────────────────
def main():
    import argparse

    parser = argparse.ArgumentParser(
        description=f"Frank Helix Daemon v{VERSION} — RAM manager & bridge"
    )
    parser.add_argument(
        "--sideload-peer",
        help="Peer host IP for Frank-to-Frank sideload bridge",
        default=None
    )
    parser.add_argument(
        "--sideload-mode",
        choices=["server", "client"],
        default="server",
        help="Sideload bridge mode: server (listen) or client (connect)"
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Print status and exit"
    )
    args = parser.parse_args()

    daemon = FrankDaemon(
        sideload_peer=args.sideload_peer,
        sideload_mode=args.sideload_mode
    )

    if args.status:
        daemon.pressure_mon.current_pressure = daemon.pressure_mon.get_pressure()
        daemon.pressure_mon.current_tier     = daemon.pressure_mon.get_tier(
            daemon.pressure_mon.current_pressure
        )
        print(json.dumps(daemon.status(), indent=2))
        return

    daemon.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        daemon.stop()

if __name__ == "__main__":
    main()
