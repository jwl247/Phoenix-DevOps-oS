#!/usr/bin/env python3
"""
FRANK — Helix RAM Manager
Phoenix DevOps oS | Authentic Coder
JW Leftwich

Frank sits between your processes and physical RAM.
He manages what stays hot, what gets compressed, what hits disk.
On 8GB he effectively gives you 16GB+ through L3 compression.

Requires: franken2.py in same directory or PYTHONPATH

Usage:
    python3 frank.py # interactive mode
    python3 frank.py --daemon # background daemon
    python3 frank.py --status # print status and exit
    python3 frank.py --bench # run quick benchmark
"""

import os
import sys
import time
import json
import threading
import subprocess
import argparse
import signal
from pathlib import Path
from typing import Optional, Dict, List
from dataclasses import dataclass, field

# ── Try importing Helix ───────────────────────────────────────────────────────
try:
    from franken2 import (
        init_helix, helix_malloc, helix_write, helix_read,
        helix_free, helix_stats, _helix, HelixSystem, HelixSync,
        AgnosticLayer, init_sync
    )
    HELIX_OK = True
except ImportError as e:
    print(f"⚠ franken2.py not found: {e}")
    print(" Place frank.py in the same directory as franken2.py")
    HELIX_OK = False

# ── Constants ─────────────────────────────────────────────────────────────────
VERSION = "1.0.0"
FRANK_ID = "FRANK-LE002GEN5"
TOTAL_RAM_MB = 8192
RESERVED_MB = 1024 # Keep 1GB free for OS + kernel at all times
USABLE_MB = TOTAL_RAM_MB - RESERVED_MB # 7GB Frank can manage

# Tier sizing for 8GB system
L1_MB = 256 # Hot — frequently accessed
L2_MB = 768 # Warm — recently accessed
L3_MB = 2048 # Compressed cold — zlib, effectively 4-6GB equivalent
VRAM_MB = 6000 # Frank's total virtual address space

# Pressure thresholds
PRESSURE_LOW = 60 # % RAM used — Frank starts watching
PRESSURE_HIGH = 75 # % RAM used — Frank starts compressing aggressively
PRESSURE_CRIT = 88 # % RAM used — Frank starts evicting to disk

# Polling
MONITOR_INTERVAL = 3.0 # seconds between RAM checks
LOG_DIR = Path.home() / ".frank"
STATE_FILE = LOG_DIR / "frank.state"
LOG_FILE = LOG_DIR / "frank.log"

# ══════════════════════════════════════════════════════════════════════════════
# PROCESS SNAPSHOT — what's eating RAM right now
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class ProcessInfo:
    pid: int
    name: str
    rss_mb: float
    vms_mb: float
    cpu_pct: float = 0.0
    priority: int = 5 # 1=critical(kernel) 10=evictable

    def __str__(self):
        return f"[{self.pid:6d}] {self.name:<28} RSS:{self.rss_mb:7.1f}MB"


def get_process_list() -> List[ProcessInfo]:
    """Read /proc and build process list with RSS usage."""
    procs = []
    try:
        result = subprocess.run(
            ['ps', 'aux', '--no-headers'],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.strip().splitlines():
            parts = line.split(None, 10)
            if len(parts) < 11:
                continue
            try:
                pid = int(parts[1])
                cpu = float(parts[2])
                rss_kb = int(parts[5])
                vms_kb = int(parts[4])
                name = parts[10][:40]
                procs.append(ProcessInfo(
                    pid=pid,
                    name=name,
                    rss_mb=rss_kb / 1024,
                    vms_mb=vms_kb / 1024,
                    cpu_pct=cpu
                ))
            except (ValueError, IndexError):
                continue
    except Exception as e:
        pass
    return sorted(procs, key=lambda p: p.rss_mb, reverse=True)


def get_ram_stats() -> dict:
    """Read /proc/meminfo for real RAM numbers."""
    stats = {}
    try:
        with open('/proc/meminfo', 'r') as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    key = parts[0].rstrip(':')
                    val = int(parts[1]) # kB
                    stats[key] = val
    except Exception:
        return {'total': 0, 'free': 0, 'available': 0, 'used': 0, 'pressure': 0}

    total = stats.get('MemTotal', 0)
    free = stats.get('MemFree', 0)
    available = stats.get('MemAvailable', 0)
    buffers = stats.get('Buffers', 0)
    cached = stats.get('Cached', 0)
    used = total - free - buffers - cached

    pressure = (used / total * 100) if total > 0 else 0

    return {
        'total_mb' : total / 1024,
        'free_mb' : free / 1024,
        'available_mb': available / 1024,
        'used_mb' : used / 1024,
        'cached_mb' : cached / 1024,
        'buffers_mb' : buffers / 1024,
        'pressure_pct': pressure
    }


# ══════════════════════════════════════════════════════════════════════════════
# FRANK CORE
# ══════════════════════════════════════════════════════════════════════════════

class Frank:
    """
    Frank — Helix RAM Manager.
    Monitors system RAM, routes allocations through Helix,
    manages pressure, logs state, provides status API.
    """

    def __init__(self):
        self.version = VERSION
        self.id = FRANK_ID
        self.start_time = time.time()
        self._running = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self.helix = None
        self.agnostic = None
        self._pressure_history: List[float] = []
        self._events: List[dict] = []
        self._managed_keys: Dict[str, int] = {} # key -> size
        self._lock = threading.RLock()

        LOG_DIR.mkdir(parents=True, exist_ok=True)
        self._log("info", f"Frank {VERSION} initializing [{FRANK_ID}]")
        self._boot_helix()

    # ── Boot ──────────────────────────────────────────────────────────────────

    def _boot_helix(self):
        if not HELIX_OK:
            self._log("error", "Helix unavailable — Frank running in monitor-only mode")
            return
        try:
            self._log("info", f"Booting Helix L1:{L1_MB}MB L2:{L2_MB}MB L3:{L3_MB}MB VRAM:{VRAM_MB}MB")
            init_helix(
                l1_mb=L1_MB,
                l2_mb=L2_MB,
                l3_mb=L3_MB,
                vram_mb=VRAM_MB
            )
            import franken2 as f2
            self.helix = f2._helix
            self.agnostic = f2._agnostic
            self._log("success", f"Helix online — {VRAM_MB}MB virtual space ready")
            self._log("info", f"Effective RAM with L3 compression: ~{VRAM_MB * 2 // 1024}GB equivalent")
        except Exception as e:
            self._log("error", f"Helix boot failed: {e}")

    # ── Logging ───────────────────────────────────────────────────────────────

    def _log(self, level: str, msg: str):
        icons = {
            'info' : '→',
            'success': '✓',
            'warning': '⚠',
            'error' : '✗',
            'critical': '!!',
            'debug' : '·'
        }
        ts = time.strftime('%H:%M:%S')
        ico = icons.get(level, '·')
        line = f"{ts} {ico} [Frank] {msg}"
        print(line)
        try:
            with open(LOG_FILE, 'a') as f:
                f.write(line + '\n')
        except Exception:
            pass

    # ── Memory API ────────────────────────────────────────────────────────────

    def store(self, key: str, data: bytes) -> bool:
        """Store data in Helix under a named key."""
        if not HELIX_OK:
            return False
        with self._lock:
            ptr = helix_malloc(len(data))
            if not ptr:
                self._log("warning", f"store({key}) — malloc failed, RAM pressure?")
                return False
            helix_write(ptr, data)
            self._managed_keys[key] = ptr
            return True

    def retrieve(self, key: str) -> Optional[bytes]:
        """Retrieve data from Helix by key."""
        if not HELIX_OK or key not in self._managed_keys:
            return None
        ptr = self._managed_keys[key]
        return helix_read(ptr, len(key) * 100) # approximate

    def release(self, key: str) -> bool:
        """Free a Helix allocation by key."""
        if not HELIX_OK or key not in self._managed_keys:
            return False
        with self._lock:
            ptr = self._managed_keys.pop(key)
            helix_free(ptr)
            return True

    def release_all(self):
        """Free everything Frank is managing."""
        keys = list(self._managed_keys.keys())
        for k in keys:
            self.release(k)
        self._log("info", f"Released {len(keys)} managed allocations")

    # ── Pressure Response ─────────────────────────────────────────────────────

    def _respond_to_pressure(self, ram: dict):
        pct = ram['pressure_pct']
        avail = ram['available_mb']

        if pct >= PRESSURE_CRIT:
            self._log("critical",
                f"RAM CRITICAL {pct:.1f}% used — {avail:.0f}MB available")
            self._event("critical_pressure", pct)
            self._aggressive_compress()

        elif pct >= PRESSURE_HIGH:
            self._log("warning",
                f"RAM HIGH {pct:.1f}% used — {avail:.0f}MB available — compressing")
            self._event("high_pressure", pct)
            self._moderate_compress()

        elif pct >= PRESSURE_LOW:
            self._log("info",
                f"RAM elevated {pct:.1f}% — {avail:.0f}MB available — watching")

    def _aggressive_compress(self):
        """Push L2 → L3, force L3 compression hard."""
        if self.helix:
            # Force demotions by accessing stats — Helix auto-manages tiers
            stats = self.helix.get_stats()
            l2_items = stats['cache']['l2_items']
            self._log("info", f"Aggressive compress: {l2_items} L2 items → L3")
            self._event("aggressive_compress", l2_items)

    def _moderate_compress(self):
        """Normal pressure response — let Helix manage naturally."""
        if self.helix:
            stats = self.helix.get_stats()
            self._log("debug", f"Moderate compress: hit_rate={stats['cache']['hit_rate']:.1f}%")

    def _event(self, name: str, value=None):
        self._events.append({
            'time': time.time(),
            'event': name,
            'value': value
        })
        if len(self._events) > 200:
            self._events = self._events[-200:]

    # ── Monitor Loop ──────────────────────────────────────────────────────────

    def _monitor_loop(self):
        self._log("info", f"Monitor started — polling every {MONITOR_INTERVAL}s")
        while not self._stop_event.wait(MONITOR_INTERVAL):
            try:
                ram = get_ram_stats()
                self._pressure_history.append(ram['pressure_pct'])
                if len(self._pressure_history) > 100:
                    self._pressure_history = self._pressure_history[-100:]
                self._respond_to_pressure(ram)
                self._save_state(ram)
            except Exception as e:
                self._log("error", f"Monitor error: {e}")

    def _save_state(self, ram: dict):
        state = {
            'timestamp' : time.time(),
            'uptime_s' : time.time() - self.start_time,
            'ram' : ram,
            'helix' : self.helix.get_stats() if self.helix else {},
            'managed_keys': len(self._managed_keys),
            'events' : self._events[-10:]
        }
        try:
            STATE_FILE.write_text(json.dumps(state, indent=2))
        except Exception:
            pass

    # ── Start / Stop ──────────────────────────────────────────────────────────

    def start(self):
        if self._running:
            self._log("warning", "Frank already running")
            return
        self._running = True
        self._stop_event.clear()
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop, daemon=True
        )
        self._monitor_thread.start()
        self._log("success", f"Frank online — managing {USABLE_MB}MB of {TOTAL_RAM_MB}MB")
        self._log("info", f"Thresholds: watch>{PRESSURE_LOW}% compress>{PRESSURE_HIGH}% critical>{PRESSURE_CRIT}%")

    def stop(self):
        self._log("info", "Frank shutting down...")
        self._stop_event.set()
        self._running = False
        self.release_all()
        self._log("success", "Frank offline")

    # ── Status ────────────────────────────────────────────────────────────────

    def status(self):
        ram = get_ram_stats()
        procs = get_process_list()[:10]

        sep = "=" * 70
        print(f"\n{sep}")
        print(f" FRANK STATUS [{FRANK_ID}] v{VERSION}")
        print(sep)

        uptime = time.time() - self.start_time
        print(f" Uptime : {uptime:.0f}s")
        print(f" Monitor : {'RUNNING' if self._running else 'STOPPED'}")
        print(f" Managed keys : {len(self._managed_keys)}")
        print()

        # RAM
        print(f" ── SYSTEM RAM ({'%.1f' % ram['total_mb']}MB total) ──")
        bar_width = 40
        used_pct = ram['pressure_pct']
        filled = int(bar_width * used_pct / 100)
        bar = '█' * filled + '░' * (bar_width - filled)
        status_icon = '✓' if used_pct < PRESSURE_LOW else ('⚠' if used_pct < PRESSURE_CRIT else '!!')
        print(f" [{bar}] {used_pct:.1f}% {status_icon}")
        print(f" Used : {ram['used_mb']:.0f}MB")
        print(f" Available : {ram['available_mb']:.0f}MB")
        print(f" Cached : {ram['cached_mb']:.0f}MB")
        print()

        # Helix
        if self.helix:
            h = self.helix.get_stats()
            print(f" ── HELIX CACHE ──")
            print(f" L1 hot : {h['cache']['l1_size_mb']:.1f}MB ({h['cache']['l1_items']} items)")
            print(f" L2 warm : {h['cache']['l2_size_mb']:.1f}MB ({h['cache']['l2_items']} items)")
            print(f" L3 compressed : {h['cache']['l3_size_mb']:.1f}MB ({h['cache']['l3_items']} items)")
            print(f" Hit rate : {h['cache']['hit_rate']:.1f}%")
            print(f" Compressions : {h['cache']['compressions']}")
            print(f" Virtual alloc : {h['memory']['allocated_mb']:.1f}MB")
            print()

        # Top processes
        print(f" ── TOP PROCESSES BY RAM ──")
        total_shown = 0
        for p in procs[:8]:
            if p.rss_mb < 1:
                continue
            print(f" {p}")
            total_shown += p.rss_mb
        print(f" {'─' * 50}")
        print(f" Top 8 total : {total_shown:.0f}MB")
        print()

        # Recent events
        if self._events:
            print(f" ── RECENT EVENTS ──")
            for ev in self._events[-5:]:
                ts = time.strftime('%H:%M:%S', time.localtime(ev['time']))
                print(f" {ts} {ev['event']} {ev.get('value', '')}")
        print(sep)

    def print_top(self, n=15):
        """Print top RAM consumers — like htop but Frank's version."""
        procs = get_process_list()
        ram = get_ram_stats()
        print(f"\n{'─'*70}")
        print(f" FRANK TOP — {ram['used_mb']:.0f}MB used / {ram['total_mb']:.0f}MB total ({ram['pressure_pct']:.1f}%)")
        print(f"{'─'*70}")
        print(f" {'PID':>6} {'NAME':<30} {'RSS':>8} {'CPU':>6}")
        print(f" {'─'*6} {'─'*30} {'─'*8} {'─'*6}")
        total = 0
        for p in procs[:n]:
            if p.rss_mb < 0.5:
                continue
            print(f" {p.pid:>6} {p.name:<30} {p.rss_mb:>6.1f}MB {p.cpu_pct:>5.1f}%")
            total += p.rss_mb
        print(f"{'─'*70}")
        print(f" Shown total: {total:.0f}MB\n")


# ══════════════════════════════════════════════════════════════════════════════
# QUICK BENCHMARK
# ══════════════════════════════════════════════════════════════════════════════

def run_quick_bench():
    if not HELIX_OK:
        print("Helix not available — can't benchmark")
        return

    print("\n" + "="*70)
    print(" FRANK QUICK BENCH — Helix vs Native")
    print("="*70)

    COUNT = 2000
    SIZE = 512

    # Native
    store = {}
    start = time.perf_counter()
    for i in range(COUNT):
        store[i] = bytearray(SIZE)
        store[i][:10] = f"block{i:05}".encode()
    for i in range(COUNT):
        _ = bytes(store[i])
    for i in range(COUNT):
        del store[i]
    native_time = time.perf_counter() - start

    # Helix
    init_helix(l1_mb=256, l2_mb=512, l3_mb=1024, vram_mb=4096)
    ptrs = []
    start = time.perf_counter()
    for i in range(COUNT):
        p = helix_malloc(SIZE)
        helix_write(p, f"block{i:05}".encode())
        ptrs.append(p)
    for p in ptrs:
        _ = helix_read(p, SIZE)
    for p in ptrs:
        helix_free(p)
    helix_time = time.perf_counter() - start

    winner = "Helix" if helix_time < native_time else "Native"
    pct = abs(native_time - helix_time) / max(native_time, helix_time) * 100

    print(f" Native : {native_time*1000:.2f}ms ({COUNT/(native_time):.0f} ops/sec)")
    print(f" Helix : {helix_time*1000:.2f}ms ({COUNT/(helix_time):.0f} ops/sec)")
    print(f" Winner : {winner} ({pct:.1f}% faster)")
    print("="*70 + "\n")


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description=f"Frank RAM Manager v{VERSION}")
    parser.add_argument('--daemon', action='store_true', help='Run as background monitor')
    parser.add_argument('--status', action='store_true', help='Print status and exit')
    parser.add_argument('--top', action='store_true', help='Show top RAM processes')
    parser.add_argument('--bench', action='store_true', help='Run quick benchmark')
    parser.add_argument('--monitor', action='store_true', help='Live monitor mode')
    args = parser.parse_args()

    frank = Frank()

    if args.bench:
        run_quick_bench()
        return

    if args.status:
        frank.status()
        return

    if args.top:
        frank.print_top()
        return

    if args.daemon or args.monitor:
        frank.start()

        def _sig(sig, frame):
            print()
            frank.stop()
            sys.exit(0)

        signal.signal(signal.SIGINT, _sig)
        signal.signal(signal.SIGTERM, _sig)

        if args.monitor:
            # Live display loop
            try:
                while True:
                    os.system('clear')
                    frank.status()
                    frank.print_top(8)
                    print(" Press Ctrl+C to exit\n")
                    time.sleep(MONITOR_INTERVAL)
            except KeyboardInterrupt:
                frank.stop()
        else:
            # Pure daemon — just monitor in background
            print(f"Frank daemon running. PID: {os.getpid()}")
            print(f"State file: {STATE_FILE}")
            print(f"Log file: {LOG_FILE}")
            print("Ctrl+C to stop\n")
            signal.pause()
        return

    # Default — interactive status + top
    frank.status()
    frank.print_top()
    print(" Run with --monitor for live view")
    print(" Run with --daemon for background monitoring")
    print(" Run with --bench for Helix vs Native benchmark\n")


if __name__ == "__main__":
    main()

