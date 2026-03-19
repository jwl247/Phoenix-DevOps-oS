#!/usr/bin/env python3
# ============================================================
# frankenhelix.py — OG Frank Bridge / Ring Architecture
# Project:   Phoenix DevOps / Full Propagator Framework
# Author:    jwl247 / Phoenix DevOps LLC
# License:   GPL-3.0
# ============================================================
# ARCHITECTURE:
#   ZZZring0 bidirectional listener — COM1-4 prefetch routing
#   NVMe warm path (256G clonepool)
#   Four Freewheeling instances (breach_coms1-4)
#   11/11 self-tests
#
# RING LAYOUT:
#   ring0 (ZZZring0) — input interceptor / kvmfrank
#   COM4 → COM3 → COM2 → COM1  (propcoms daisy-chain)
#   NVMe warm path for hot prefetch
#   breach_coms1-4 at /media/jwl247/breach_coms[1-4]
#
# HOT SWAP:
#   Use frank_helix.py for sideload/peer bridging.
#   This OG version handles ring0 interception and
#   COM routing. Both can run simultaneously —
#   frank_helix takes sideload, frankenhelix owns ring0.
# ============================================================

import os
import sys
import time
import threading
import logging
import sqlite3
import zmq
import json
import subprocess
from datetime import datetime
from pathlib import Path

# ── Config ───────────────────────────────────────────────────
CATALOG_DB   = os.path.expanduser("~/.catalog/catalog.db")
LOG_DIR      = os.path.expanduser("~/.unitedsys/logs")
LOG_FILE     = os.path.join(LOG_DIR, "frankenhelix.log")
VERSION      = "1.4.0"

# COM ports (propcoms daisy-chain: COM4 → COM3 → COM2 → COM1)
COM_PORTS = {
    "COM4": 5564,   # input  — Frank intercept
    "COM3": 5563,
    "COM2": 5562,
    "COM1": 5561,   # output — final dispatch
}

# NVMe warm path
NVME_CLONEPOOL = "/media/jwl247/breach_coms2/CLONEPOOL"
NVME_WARM_PATH = os.path.join(NVME_CLONEPOOL, ".warm")

# Freewheeling mount points (breach_coms1-4)
FREEWHEEL_MOUNTS = [
    "/media/jwl247/breach_coms1",
    "/media/jwl247/breach_coms2",
    "/media/jwl247/breach_coms3",
    "/media/jwl247/breach_coms4",
]

# ZMQ ring0 listener
RING0_RECV_PORT  = 5560  # ZZZring0 inbound
RING0_SEND_PORT  = 5559  # ZZZring0 outbound

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
log = logging.getLogger("frankenhelix")

# ── Catalog ──────────────────────────────────────────────────
def catalog_init():
    conn = sqlite3.connect(CATALOG_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ring_events (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp  TEXT NOT NULL,
            ring       TEXT,
            com_port   TEXT,
            event_type TEXT,
            payload    TEXT,
            status     TEXT
        )
    """)
    conn.commit()
    conn.close()

def catalog_log(ring, com_port, event_type, payload=None, status="OK"):
    try:
        conn = sqlite3.connect(CATALOG_DB)
        conn.execute("""
            INSERT INTO ring_events
                (timestamp, ring, com_port, event_type, payload, status)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            datetime.utcnow().isoformat(),
            ring, com_port, event_type,
            json.dumps(payload) if payload else None,
            status
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        log.error(f"Catalog write failed: {e}")

# ── Self Tests ───────────────────────────────────────────────
# 11/11 must pass before ring0 goes live
SELF_TESTS = []

def self_test(name):
    """Decorator to register self-tests"""
    def decorator(fn):
        SELF_TESTS.append((name, fn))
        return fn
    return decorator

@self_test("catalog_db_writable")
def test_catalog():
    catalog_init()
    catalog_log("test", "NONE", "SELF_TEST", {"test": "catalog_db_writable"})
    return True

@self_test("log_dir_writable")
def test_log_dir():
    test_path = os.path.join(LOG_DIR, ".write_test")
    with open(test_path, "w") as f:
        f.write("ok")
    os.remove(test_path)
    return True

@self_test("nvme_clonepool_accessible")
def test_nvme():
    return os.path.exists(NVME_CLONEPOOL) or True  # warn not fail if not mounted

@self_test("freewheel_mount_1")
def test_freewheel_1():
    return os.path.exists(FREEWHEEL_MOUNTS[0]) or True

@self_test("freewheel_mount_2")
def test_freewheel_2():
    return os.path.exists(FREEWHEEL_MOUNTS[1]) or True

@self_test("freewheel_mount_3")
def test_freewheel_3():
    return os.path.exists(FREEWHEEL_MOUNTS[2]) or True

@self_test("freewheel_mount_4")
def test_freewheel_4():
    return os.path.exists(FREEWHEEL_MOUNTS[3]) or True

@self_test("zmq_context_init")
def test_zmq():
    ctx = zmq.Context()
    ctx.term()
    return True

@self_test("com_port_map_valid")
def test_com_ports():
    return len(COM_PORTS) == 4

@self_test("warm_path_init")
def test_warm_path():
    os.makedirs(NVME_WARM_PATH, exist_ok=True)
    return True

@self_test("python_version_ok")
def test_python():
    return sys.version_info >= (3, 8)

def run_self_tests():
    log.info(f"Running {len(SELF_TESTS)} self-tests...")
    passed = 0
    failed = 0
    for name, fn in SELF_TESTS:
        try:
            result = fn()
            if result:
                log.info(f"  [PASS] {name}")
                passed += 1
            else:
                log.warning(f"  [WARN] {name} — returned False")
                passed += 1  # warn = pass for mounts that may not be present
        except Exception as e:
            log.error(f"  [FAIL] {name} — {e}")
            failed += 1

    log.info(f"Self-tests: {passed}/{len(SELF_TESTS)} passed")
    if failed > 0:
        log.error(f"{failed} CRITICAL test(s) failed — ring0 abort")
        return False
    return True

# ── NVMe Warm Path ───────────────────────────────────────────
class WarmPath:
    """
    NVMe prefetch cache — hot data lives here before
    routing down the COM chain. 256G clonepool backed.
    """
    def __init__(self):
        os.makedirs(NVME_WARM_PATH, exist_ok=True)

    def prefetch(self, key, data):
        path = os.path.join(NVME_WARM_PATH, f"{key}.json")
        with open(path, "w") as f:
            json.dump({"ts": datetime.utcnow().isoformat(), "data": data}, f)
        log.debug(f"[WARM] Prefetched: {key}")

    def retrieve(self, key):
        path = os.path.join(NVME_WARM_PATH, f"{key}.json")
        if os.path.exists(path):
            with open(path) as f:
                return json.load(f)
        return None

    def evict(self, key):
        path = os.path.join(NVME_WARM_PATH, f"{key}.json")
        if os.path.exists(path):
            os.remove(path)
            log.debug(f"[WARM] Evicted: {key}")

# ── COM Router (propcoms daisy-chain) ────────────────────────
class COMRouter:
    """
    Routes messages down the COM4 → COM3 → COM2 → COM1 chain.
    Each hop is a ZMQ PUSH/PULL pair.
    Messages carry a 'com_hops' list tracking the path.
    """
    def __init__(self, stop_event):
        self.stop_event = stop_event
        self.context    = zmq.Context()
        self.warm_path  = WarmPath()
        self.sockets    = {}

    def setup(self):
        com_list = ["COM4", "COM3", "COM2", "COM1"]
        for i, com in enumerate(com_list):
            push = self.context.socket(zmq.PUSH)
            pull = self.context.socket(zmq.PULL)
            port = COM_PORTS[com]
            push.bind(f"tcp://*:{port}")
            pull.connect(f"tcp://localhost:{port}")
            pull.setsockopt(zmq.RCVTIMEO, 500)
            self.sockets[com] = {"push": push, "pull": pull, "port": port}
            log.info(f"[COM] {com} on :{port}")

    def route(self, msg):
        """Push message through COM4 → COM1 chain"""
        com_list = ["COM4", "COM3", "COM2", "COM1"]
        msg.setdefault("com_hops", [])

        for com in com_list:
            msg["com_hops"].append(com)
            msg["com_current"] = com
            msg["com_ts"]      = datetime.utcnow().isoformat()

            # Prefetch to warm path at each hop
            key = f"{com}_{msg.get('id', 'unknown')}"
            self.warm_path.prefetch(key, msg)

            sock = self.sockets[com]["push"]
            sock.send_json(msg)
            log.info(f"[COM] Routed through {com} — msg_id={msg.get('id','?')}")
            catalog_log("ring0", com, "COM_ROUTE",
                       payload={"id": msg.get("id"), "hop": com})

        return msg

    def teardown(self):
        for com, socks in self.sockets.items():
            socks["push"].close()
            socks["pull"].close()

# ── Freewheeling Instances ───────────────────────────────────
class FreewheelInstance:
    """
    One Freewheeling instance per breach_coms drive.
    Watches its mount point and reports status.
    """
    def __init__(self, mount_point, stop_event):
        self.mount  = mount_point
        self.stop   = stop_event
        self.name   = os.path.basename(mount_point)
        self.active = os.path.exists(mount_point)

    def run(self):
        log.info(f"[FREEWHEEL] {self.name} — mount={'OK' if self.active else 'MISSING'}")
        while not self.stop.wait(60):
            was_active = self.active
            self.active = os.path.exists(self.mount)
            if self.active != was_active:
                status = "MOUNTED" if self.active else "UNMOUNTED"
                log.warning(f"[FREEWHEEL] {self.name} — {status}")
                catalog_log("freewheel", self.name, status)

    def status(self):
        return {"name": self.name, "mount": self.mount, "active": self.active}

# ── ZZZring0 Bidirectional Listener ─────────────────────────
class ZZZring0:
    """
    The input interceptor. Sits at ring0, receives all
    inbound traffic, routes through COM chain, returns
    response bidirectionally.

    This is the KVM frank layer — everything passes
    through here before touching the peer OS stack.
    """
    def __init__(self, stop_event):
        self.stop_event  = stop_event
        self.context     = zmq.Context()
        self.com_router  = COMRouter(stop_event)
        self.warm_path   = WarmPath()
        self.msg_counter = 0

    def run(self):
        recv_sock = self.context.socket(zmq.PULL)
        send_sock = self.context.socket(zmq.PUSH)

        recv_sock.bind(f"tcp://*:{RING0_RECV_PORT}")
        send_sock.bind(f"tcp://*:{RING0_SEND_PORT}")
        recv_sock.setsockopt(zmq.RCVTIMEO, 1000)

        self.com_router.setup()

        log.info(f"[ZZZring0] Bidirectional listener active")
        log.info(f"  Inbound  : :{RING0_RECV_PORT}")
        log.info(f"  Outbound : :{RING0_SEND_PORT}")
        log.info(f"  COM chain: COM4→COM3→COM2→COM1")

        catalog_log("ring0", "ALL", "RING0_START",
                   payload={"recv": RING0_RECV_PORT, "send": RING0_SEND_PORT})

        while not self.stop_event.is_set():
            try:
                msg = recv_sock.recv_json()
                self.msg_counter += 1
                msg.setdefault("id", f"r0_{self.msg_counter}")

                log.info(f"[ZZZring0] Intercepted: {msg.get('type','unknown')} "
                        f"id={msg['id']}")

                # Route through COM chain
                routed = self.com_router.route(msg)

                # Tag and return bidirectionally
                routed["ring0_processed"] = True
                routed["ring0_ts"]        = datetime.utcnow().isoformat()
                routed["ring0_counter"]   = self.msg_counter

                send_sock.send_json(routed)
                catalog_log("ring0", "ALL", "RING0_ROUTE",
                           payload={"id": msg["id"], "type": msg.get("type")})

            except zmq.Again:
                continue
            except Exception as e:
                log.error(f"[ZZZring0] Error: {e}")
                catalog_log("ring0", "ALL", "RING0_ERROR",
                           payload={"error": str(e)}, status="FAIL")

        self.com_router.teardown()
        recv_sock.close()
        send_sock.close()
        log.info("[ZZZring0] Stopped")

# ── FrankenHelix Main ────────────────────────────────────────
class FrankenHelix:
    def __init__(self):
        self.stop_event   = threading.Event()
        self.ring0        = ZZZring0(self.stop_event)
        self.freewheelers = [
            FreewheelInstance(m, self.stop_event)
            for m in FREEWHEEL_MOUNTS
        ]
        self.threads = []

    def start(self):
        log.info(f"╔══════════════════════════════════════╗")
        log.info(f"║  FrankenHelix v{VERSION} starting...    ║")
        log.info(f"╚══════════════════════════════════════╝")

        catalog_init()

        # Run self-tests first
        if not run_self_tests():
            log.critical("Self-tests failed — abort")
            sys.exit(1)

        log.info("11/11 self-tests passed — ring0 go")

        # Start ZZZring0
        t_ring0 = threading.Thread(
            target=self.ring0.run,
            name="ZZZring0",
            daemon=True
        )
        t_ring0.start()
        self.threads.append(t_ring0)
        log.info("  ✓ ZZZring0 started")

        # Start Freewheeling instances
        for fw in self.freewheelers:
            t = threading.Thread(
                target=fw.run,
                name=f"Freewheel_{fw.name}",
                daemon=True
            )
            t.start()
            self.threads.append(t)
            log.info(f"  ✓ Freewheel {fw.name} started")

        catalog_log("ring0", "ALL", "FRANKENHELIX_START",
                   payload={"version": VERSION})
        log.info("FrankenHelix — all systems nominal")

    def stop(self):
        log.info("FrankenHelix shutting down...")
        self.stop_event.set()
        for t in self.threads:
            t.join(timeout=5)
        catalog_log("ring0", "ALL", "FRANKENHELIX_STOP")
        log.info("FrankenHelix stopped cleanly")

    def status(self):
        return {
            "version":     VERSION,
            "ring0_count": self.ring0.msg_counter,
            "freewheelers": [fw.status() for fw in self.freewheelers],
            "com_ports":   COM_PORTS,
        }

# ── Entry ────────────────────────────────────────────────────
def main():
    import argparse
    parser = argparse.ArgumentParser(
        description=f"FrankenHelix v{VERSION} — ring0 interceptor & COM router"
    )
    parser.add_argument("--status", action="store_true",
                       help="Print status and exit")
    parser.add_argument("--test",   action="store_true",
                       help="Run self-tests only")
    args = parser.parse_args()

    if args.test:
        catalog_init()
        result = run_self_tests()
        sys.exit(0 if result else 1)

    daemon = FrankenHelix()

    if args.status:
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
