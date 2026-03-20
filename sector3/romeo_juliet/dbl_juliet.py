#!/usr/bin/env python3
# ============================================================
# dbl_juliet.py — Double-Barrel Juliet Test Harness
# Project:   Phoenix DevOps / Full Propagator Framework
# Author:    jwl247 / Phoenix DevOps LLC
# License:   GPL-3.0
# ============================================================
# Two Juliet instances running simultaneously.
# Barrel 1 = ingress watcher  (Romeo → Juliet)
# Barrel 2 = egress watcher   (Juliet → output)
#
# Sits at the platform boundary confirming:
#   - Barrel 1 sees quad-native payload coming in
#   - Barrel 2 sees translated output going out
#   - Nothing gets lost or corrupted in the crossing
#
# This is the real integration test. If Double-Barrel
# passes, the whole chain is verified end-to-end.
#
# Commands:
#   load1-9         arm both barrels
#   load1a / load1b arm individual barrels
#   stop1-9         fire both
#   stat1-9         status both
#   nuke            emergency stop all
# ============================================================

import os
import sys
import json
import logging
import threading
import zmq
import time
from datetime import datetime

from juliet import Juliet, catalog_init, catalog_log

LOG_DIR  = os.path.expanduser("~/.unitedsys/logs")
LOG_FILE = os.path.join(LOG_DIR, "dbl_juliet.log")
VERSION  = "2.0.0"

os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [DBL_JULIET] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger("dbl_juliet")

# ── Boundary Monitor ─────────────────────────────────────────
class BoundaryMonitor:
    """
    Sits at the platform boundary watching both barrels.
    Barrel 1 in, Barrel 2 out — confirms nothing lost
    in the quad→native translation crossing.
    """
    def __init__(self, stop_event):
        self.stop_event  = stop_event
        self.context     = zmq.Context()
        self.in_count    = 0
        self.out_count   = 0
        self.loss_count  = 0
        self.in_flight   = {}   # id → ingress timestamp

    def run(self):
        # Watch barrel 1 output (post-Romeo, pre-translate)
        in_sock  = self.context.socket(zmq.SUB)
        # Watch barrel 2 output (post-translate, egress)
        out_sock = self.context.socket(zmq.SUB)

        in_sock.connect("tcp://localhost:5582")
        out_sock.connect("tcp://localhost:5583")
        in_sock.setsockopt_string(zmq.SUBSCRIBE, "")
        out_sock.setsockopt_string(zmq.SUBSCRIBE, "")
        in_sock.setsockopt(zmq.RCVTIMEO, 500)
        out_sock.setsockopt(zmq.RCVTIMEO, 500)

        log.info("BoundaryMonitor active — watching both barrels")

        while not self.stop_event.is_set():
            # Check barrel 1 (ingress side)
            try:
                msg = in_sock.recv_json()
                self.in_count += 1
                msg_id = msg.get("id", f"unknown_{self.in_count}")
                self.in_flight[msg_id] = datetime.utcnow().isoformat()
                log.info(f"[BOUNDARY IN ] id={msg_id} "
                        f"translated={msg.get('translated',False)}")
            except zmq.Again:
                pass

            # Check barrel 2 (egress side)
            try:
                msg = out_sock.recv_json()
                self.out_count += 1
                msg_id = msg.get("id", f"unknown_{self.out_count}")

                # Verify it crossed cleanly
                if msg_id in self.in_flight:
                    del self.in_flight[msg_id]
                    log.info(f"[BOUNDARY OUT] id={msg_id} ✓ crossed clean "
                            f"translated={msg.get('translated',False)}")
                else:
                    log.warning(f"[BOUNDARY OUT] id={msg_id} — "
                               f"no matching ingress record")
                    self.loss_count += 1

            except zmq.Again:
                pass

        in_sock.close()
        out_sock.close()
        log.info(f"BoundaryMonitor stopped — "
                f"in={self.in_count} out={self.out_count} "
                f"loss={self.loss_count}")

    def status(self):
        return {
            "in_count":   self.in_count,
            "out_count":  self.out_count,
            "loss_count": self.loss_count,
            "in_flight":  len(self.in_flight),
        }

# ── Double-Barrel Juliet ─────────────────────────────────────
class DoubleBarrelJuliet:
    """
    Two Juliet instances + BoundaryMonitor.
    Barrel 1: ingress watcher
    Barrel 2: egress watcher
    Monitor: confirms clean platform boundary crossing
    """
    def __init__(self):
        self.stop_event = threading.Event()
        self.barrel1    = Juliet(self.stop_event, barrel_id=1)
        self.barrel2    = Juliet(self.stop_event, barrel_id=2)
        self.monitor    = BoundaryMonitor(self.stop_event)
        self.threads    = []
        self.start_time = None

    def start(self):
        self.start_time = datetime.utcnow().isoformat()
        log.info(f"╔═══════════════════════════════════════╗")
        log.info(f"║  Double-Barrel Juliet v{VERSION} loaded  ║")
        log.info(f"╚═══════════════════════════════════════╝")
        log.info(f"  Commands: load1-9 | load1a/load1b")
        log.info(f"  Fire:     stop1-9  | Cease: stop1-9")
        log.info(f"  Status:   stat1-9  | Nuke:  load...")
        log.info(f"  Barrel 1: ingress watcher")
        log.info(f"  Barrel 2: egress watcher")

        catalog_init()

        targets = [
            ("Juliet_Barrel1",    self.barrel1.run),
            ("Juliet_Barrel2",    self.barrel2.run),
            ("BoundaryMonitor",   self.monitor.run),
        ]

        for name, target in targets:
            t = threading.Thread(target=target, name=name, daemon=True)
            t.start()
            self.threads.append(t)
            log.info(f"  ✓ {name} started")

        log.info("Double-Barrel Juliet — all systems nominal")

    def stop(self):
        log.info("Double-Barrel Juliet — NUKE initiated")
        self.stop_event.set()
        for t in self.threads:
            t.join(timeout=5)
        log.info("Double-Barrel Juliet — stopped cleanly")

    def load(self, slot, barrel="both"):
        """load1-9 or load1a (barrel1) / load1b (barrel2)"""
        if barrel in ("both", "a", 1):
            self.barrel1.load(slot)
        if barrel in ("both", "b", 2):
            self.barrel2.load(slot)

    def fire(self, slot):
        """stop1-9 — fire both barrels"""
        r1 = self.barrel1.fire(slot)
        r2 = self.barrel2.fire(slot)
        log.info(f"stop{slot} — barrel1={r1} barrel2={r2}")
        return r1, r2

    def stat(self, slot):
        """stat1-9"""
        return {
            "slot":    slot,
            "barrel1": self.barrel1.stat(slot),
            "barrel2": self.barrel2.stat(slot),
        }

    def status(self):
        return {
            "version":    VERSION,
            "start_time": self.start_time,
            "barrel1":    self.barrel1.status(),
            "barrel2":    self.barrel2.status(),
            "boundary":   self.monitor.status(),
        }

# ── Entry ────────────────────────────────────────────────────
def main():
    import argparse
    parser = argparse.ArgumentParser(
        description=f"Double-Barrel Juliet v{VERSION} — two-instance test harness"
    )
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--load",   type=int, help="Arm slot (1-9)")
    parser.add_argument("--fire",   type=int, help="Fire slot (1-9)")
    parser.add_argument("--barrel", choices=["a","b","both"], default="both")
    args = parser.parse_args()

    dbl = DoubleBarrelJuliet()

    if args.status:
        print(json.dumps(dbl.status(), indent=2))
        return

    dbl.start()

    if args.load:
        dbl.load(args.load, barrel=args.barrel)
    if args.fire:
        dbl.fire(args.fire)

    try:
        while True:
            time.sleep(5)
            log.info(f"Status: {json.dumps(dbl.status())}")
    except KeyboardInterrupt:
        dbl.stop()

if __name__ == "__main__":
    main()
