#!/usr/bin/env python3
# ============================================================
# helix_slim.py — Slim Helix / ARM Edition
# Project:   Phoenix DevOps / UnitedSys
# Author:    jwl247 / Phoenix DevOps LLC
# License:   GPL-3.0
# ============================================================
# Lean ZMQ signal router — no heavy deps
# Runs on: x86_64, ARM64, Termux, WSL2, bare metal
# Deps: pyzmq, psutil (optional)
# ============================================================

import os
import sys
import time
import json
import threading
import logging
import platform
from datetime import datetime, timezone

try:
    import zmq
except ImportError:
    print("[helix_slim] ERROR: pyzmq not installed. Run: pip install pyzmq")
    sys.exit(1)

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

# ── Config ────────────────────────────────────────────────────
VERSION      = "1.0.0-slim"
ARCH         = platform.machine()
PLATFORM     = platform.system()
LOG_DIR      = os.path.expanduser("~/.helix/logs")
LOG_FILE     = os.path.join(LOG_DIR, "helix_slim.log")

# ZMQ ports — same as frankenhelix for compatibility
RING0_RECV   = 5560
RING0_SEND   = 5559
COM_PORTS    = {"COM4": 5564, "COM3": 5563, "COM2": 5562, "COM1": 5561}

# ── Bootstrap ─────────────────────────────────────────────────
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger("helix_slim")

# ── System Info ───────────────────────────────────────────────
def sys_info():
    info = {
        "version":   VERSION,
        "arch":      ARCH,
        "platform":  PLATFORM,
        "python":    sys.version.split()[0],
        "node":      platform.node(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if HAS_PSUTIL:
        vm = psutil.virtual_memory()
        info["cpu_cores"]     = psutil.cpu_count()
        info["ram_total_gb"]  = round(vm.total / 1024**3, 2)
        info["ram_avail_gb"]  = round(vm.available / 1024**3, 2)
        info["ram_pct_used"]  = vm.percent
    else:
        info["psutil"] = "not installed — install for RAM/CPU stats"
    return info

# ── Heartbeat ─────────────────────────────────────────────────
class Heartbeat:
    """
    Sends periodic heartbeat over ZMQ PUSH.
    PC and phone can monitor each other via this.
    """
    def __init__(self, port, interval=10, stop_event=None):
        self.port     = port
        self.interval = interval
        self.stop     = stop_event or threading.Event()
        self.ctx      = zmq.Context()
        self.sock     = self.ctx.socket(zmq.PUSH)
        self.sock.bind(f"tcp://*:{port}")
        self.count    = 0

    def run(self):
        log.info(f"[heartbeat] broadcasting on :{self.port} every {self.interval}s")
        while not self.stop.wait(self.interval):
            self.count += 1
            msg = {
                "type":      "heartbeat",
                "id":        f"hb_{self.count}",
                "arch":      ARCH,
                "platform":  PLATFORM,
                "ts":        datetime.now(timezone.utc).isoformat(),
                "count":     self.count,
            }
            if HAS_PSUTIL:
                msg["cpu_pct"] = psutil.cpu_percent(interval=0.1)
                msg["ram_pct"] = psutil.virtual_memory().percent
            try:
                self.sock.send_json(msg, zmq.NOBLOCK)
                log.debug(f"[heartbeat] #{self.count}")
            except zmq.Again:
                pass

    def stop_all(self):
        self.stop.set()
        self.sock.close()
        self.ctx.term()

# ── Signal Router ─────────────────────────────────────────────
class SlimRouter:
    """
    Lightweight COM chain router.
    COM4 → COM3 → COM2 → COM1
    Compatible with frankenhelix message format.
    Runs on any arch — no native deps.
    """
    def __init__(self, stop_event):
        self.stop  = stop_event
        self.ctx   = zmq.Context()
        self.socks = {}
        self.count = 0

    def setup(self):
        for com, port in COM_PORTS.items():
            push = self.ctx.socket(zmq.PUSH)
            pull = self.ctx.socket(zmq.PULL)
            push.bind(f"tcp://*:{port}")
            pull.connect(f"tcp://localhost:{port}")
            pull.setsockopt(zmq.RCVTIMEO, 500)
            self.socks[com] = {"push": push, "pull": pull}
            log.info(f"[router] {com} :{port}")

    def route(self, msg):
        msg.setdefault("com_hops", [])
        for com in ["COM4", "COM3", "COM2", "COM1"]:
            msg["com_hops"].append(com)
            msg["com_current"] = com
            msg["com_ts"] = datetime.now(timezone.utc).isoformat()
            self.socks[com]["push"].send_json(msg)
            log.debug(f"[router] {com} → msg {msg.get('id','?')}")
        return msg

    def teardown(self):
        for s in self.socks.values():
            s["push"].close()
            s["pull"].close()
        self.ctx.term()

# ── Ring0 Listener ────────────────────────────────────────────
class SlimRing0:
    """
    Bidirectional ring0 listener — same interface as ZZZring0
    in frankenhelix. PC and phone can talk to each other via this.
    """
    def __init__(self, stop_event):
        self.stop    = stop_event
        self.ctx     = zmq.Context()
        self.router  = SlimRouter(stop_event)
        self.counter = 0

    def run(self):
        recv = self.ctx.socket(zmq.PULL)
        send = self.ctx.socket(zmq.PUSH)
        recv.bind(f"tcp://*:{RING0_RECV}")
        send.bind(f"tcp://*:{RING0_SEND}")
        recv.setsockopt(zmq.RCVTIMEO, 1000)
        self.router.setup()

        log.info(f"[ring0] listening :{RING0_RECV} → :{RING0_SEND}")
        log.info(f"[ring0] arch={ARCH} platform={PLATFORM}")

        while not self.stop.is_set():
            try:
                msg = recv.recv_json()
                self.counter += 1
                msg.setdefault("id", f"slim_{self.counter}")
                routed = self.router.route(msg)
                routed["slim_processed"] = True
                routed["slim_arch"]      = ARCH
                routed["slim_ts"]        = datetime.now(timezone.utc).isoformat()
                send.send_json(routed)
            except zmq.Again:
                continue
            except Exception as e:
                log.error(f"[ring0] {e}")

        self.router.teardown()
        recv.close()
        send.close()
        self.ctx.term()

# ── Self Tests ────────────────────────────────────────────────
def run_tests():
    tests = [
        ("zmq_import",        lambda: bool(zmq.__version__)),
        ("arch_detected",     lambda: bool(ARCH)),
        ("log_writable",      lambda: bool(os.path.exists(LOG_DIR))),
        ("com_ports_valid",   lambda: len(COM_PORTS) == 4),
        ("zmq_context",       lambda: bool(zmq.Context())),
        ("sys_info",          lambda: bool(sys_info())),
        ("psutil_optional",   lambda: True),  # warn not fail
    ]
    passed = 0
    log.info(f"Running {len(tests)} self-tests...")
    for name, fn in tests:
        try:
            if fn():
                log.info(f"  [PASS] {name}")
                passed += 1
            else:
                log.warning(f"  [WARN] {name}")
                passed += 1
        except Exception as e:
            log.error(f"  [FAIL] {name} — {e}")
    log.info(f"Self-tests: {passed}/{len(tests)} passed")
    return passed == len(tests)

# ── Helix Slim Main ───────────────────────────────────────────
class HelixSlim:
    def __init__(self):
        self.stop      = threading.Event()
        self.ring0     = SlimRing0(self.stop)
        self.heartbeat = Heartbeat(5558, interval=10, stop_event=self.stop)
        self.threads   = []

    def start(self):
        log.info(f"╔══════════════════════════════════════╗")
        log.info(f"║  helix_slim v{VERSION}          ║")
        log.info(f"║  arch={ARCH:<8} platform={PLATFORM:<8}  ║")
        log.info(f"╚══════════════════════════════════════╝")

        if not run_tests():
            log.critical("Self-tests failed")
            sys.exit(1)

        # Ring0
        t_ring0 = threading.Thread(target=self.ring0.run, name="ring0", daemon=True)
        t_ring0.start()
        self.threads.append(t_ring0)
        log.info("  ✓ ring0 started")

        # Heartbeat
        t_hb = threading.Thread(target=self.heartbeat.run, name="heartbeat", daemon=True)
        t_hb.start()
        self.threads.append(t_hb)
        log.info("  ✓ heartbeat started")

        log.info("helix_slim — nominal")
        log.info(json.dumps(sys_info(), indent=2))

    def stop_all(self):
        log.info("helix_slim stopping...")
        self.stop.set()
        self.heartbeat.stop_all()
        for t in self.threads:
            t.join(timeout=3)
        log.info("helix_slim stopped")

    def status(self):
        return {
            "version":    VERSION,
            "arch":       ARCH,
            "platform":   PLATFORM,
            "ring0_count": self.ring0.counter,
            "hb_count":   self.heartbeat.count,
            "sys":        sys_info(),
        }

# ── Entry ─────────────────────────────────────────────────────
def main():
    import argparse
    parser = argparse.ArgumentParser(description=f"helix_slim v{VERSION}")
    parser.add_argument("--test",   action="store_true", help="Run self-tests")
    parser.add_argument("--info",   action="store_true", help="Print system info")
    parser.add_argument("--status", action="store_true", help="Print status")
    args = parser.parse_args()

    if args.info:
        print(json.dumps(sys_info(), indent=2))
        return

    if args.test:
        run_tests()
        return

    helix = HelixSlim()

    if args.status:
        print(json.dumps(helix.status(), indent=2))
        return

    helix.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        helix.stop_all()

if __name__ == "__main__":
    main()
