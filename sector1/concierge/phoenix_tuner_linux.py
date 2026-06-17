#!/usr/bin/env python3
"""
Phoenix Performance Tuner v1.0 — LINUX
One-shot OS optimizer for phoenix-ext.
Targets: 8GB RAM, Prometheus + Nextcloud + MySQL + Ollama + Phoenix kernel.

Run at boot (or via systemd): sudo python3 phoenix_tuner_linux.py --apply
Check current state:           sudo python3 phoenix_tuner_linux.py --status
Undo all tuning:               sudo python3 phoenix_tuner_linux.py --reset

Phoenix DevOps OS | jwl247 | GPL v3
"""

import os
import sys
import subprocess
import json
from pathlib import Path
from datetime import datetime

LOG = Path("/var/log/phoenix/tuner.log")


# ── Kernel parameters ────────────────────────────────────────────────────────
# Each entry: (sysctl_key, performance_value, default_value, description)

SYSCTL_PROFILE = [
    # RAM — keep data in RAM as long as possible
    ("vm.swappiness",                 "10",      "60",   "prefer RAM over swap"),
    ("vm.dirty_ratio",                "10",      "20",   "flush dirty pages sooner"),
    ("vm.dirty_background_ratio",     "5",       "10",   "background flush trigger"),
    ("vm.vfs_cache_pressure",         "50",      "100",  "keep filesystem cache longer"),
    ("vm.overcommit_memory",          "1",       "0",    "allow memory overcommit (faster alloc)"),

    # CPU scheduler — better for mixed server+desktop workload
    ("kernel.sched_autogroup_enabled","0",       "1",    "disable autogroup (server mode)"),
    ("kernel.sched_migration_cost_ns","5000000", "500000","reduce task migration cost"),

    # Network — for Prometheus, Nextcloud, Frank HTTP
    ("net.core.somaxconn",            "4096",    "4096", "listen backlog"),
    ("net.core.rmem_max",             "16777216","212992","socket recv buffer max"),
    ("net.core.wmem_max",             "16777216","212992","socket send buffer max"),
    ("net.ipv4.tcp_rmem",             "4096 87380 16777216", "4096 87380 6291456", "TCP recv"),
    ("net.ipv4.tcp_wmem",             "4096 65536 16777216", "4096 65536 6291456", "TCP send"),
    ("net.ipv4.tcp_fastopen",         "3",       "1",    "TCP Fast Open (client+server)"),
    ("net.ipv4.tcp_tw_reuse",         "1",       "0",    "reuse TIME_WAIT sockets"),

    # Filesystem — Nextcloud + inotify
    ("fs.inotify.max_user_watches",   "524288",  "8192", "Nextcloud file watch limit"),
    ("fs.file-max",                   "200000",  "100000","system-wide file handle limit"),
]

# ── Transparent Huge Pages ────────────────────────────────────────────────────
# THP hurts MySQL and the Helix memory engine. Disable at runtime.

THP_PATHS = [
    ("/sys/kernel/mm/transparent_hugepage/enabled", "never",  "always"),
    ("/sys/kernel/mm/transparent_hugepage/defrag",  "defer",  "always"),
]

# ── CPU governor ─────────────────────────────────────────────────────────────
# Switches all CPU cores to performance governor (max clock, no idle scaling).

CPU_GOVERNOR = "performance"
CPU_GOVERNOR_RESET = "ondemand"

# ── I/O scheduler ─────────────────────────────────────────────────────────────
# mq-deadline: low latency, good for SSD.  bfq: better for spinning disk.
# We detect block devices and set appropriately.

IO_SCHEDULER_SSD  = "mq-deadline"
IO_SCHEDULER_HDD  = "bfq"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _log(msg: str):
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.utcnow().isoformat()
        with open(LOG, "a") as f:
            f.write(f"{ts} [TUNER] {msg}\n")
    except Exception:
        pass
    print(msg)


def _sysctl_get(key: str) -> str:
    try:
        r = subprocess.run(["sysctl", "-n", key],
                           capture_output=True, text=True, timeout=5)
        return r.stdout.strip()
    except Exception:
        return ""


def _sysctl_set(key: str, value: str) -> bool:
    try:
        r = subprocess.run(["sysctl", "-w", f"{key}={value}"],
                           capture_output=True, text=True, timeout=10)
        return r.returncode == 0
    except Exception:
        return False


def _write_sys(path: str, value: str) -> bool:
    try:
        Path(path).write_text(value + "\n")
        return True
    except Exception as e:
        _log(f"  WARN: could not write {path}: {e}")
        return False


def _read_sys(path: str) -> str:
    try:
        return Path(path).read_text().strip().split()[0]
    except Exception:
        return ""


def _block_devices():
    devs = []
    try:
        r = subprocess.run(["lsblk", "-d", "-o", "NAME,ROTA", "--json"],
                           capture_output=True, text=True, timeout=5)
        data = json.loads(r.stdout)
        for dev in data.get("blockdevices", []):
            devs.append({"name": dev["name"], "rotational": dev.get("rota", "1") in (1, "1", True)})
    except Exception:
        pass
    return devs


# ── Apply ─────────────────────────────────────────────────────────────────────

def apply_sysctl():
    _log("\n[1/4] Kernel parameters")
    ok = fail = 0
    for key, perf_val, _, desc in SYSCTL_PROFILE:
        current = _sysctl_get(key)
        if current == perf_val:
            _log(f"  OK  {key} = {perf_val}  (already set)")
            ok += 1
            continue
        if _sysctl_set(key, perf_val):
            _log(f"  SET {key} = {perf_val}  ({desc})")
            ok += 1
        else:
            _log(f"  FAIL {key}")
            fail += 1
    _log(f"  -> {ok} set, {fail} failed")


def apply_thp():
    _log("\n[2/4] Transparent Huge Pages — disable for MySQL/Helix")
    for path, value, _ in THP_PATHS:
        cur = _read_sys(path)
        if cur == value:
            _log(f"  OK  {path} = {value}")
        elif _write_sys(path, value):
            _log(f"  SET {path} = {value}")
        else:
            _log(f"  FAIL {path}")


def apply_cpu_governor():
    _log("\n[3/4] CPU governor → performance")
    cores = list(Path("/sys/devices/system/cpu").glob("cpu[0-9]*/cpufreq/scaling_governor"))
    if not cores:
        _log("  SKIP — no cpufreq paths found (may be VM or unsupported)")
        return
    ok = 0
    for p in cores:
        cur = p.read_text().strip() if p.exists() else ""
        if cur == CPU_GOVERNOR:
            ok += 1
        elif _write_sys(str(p), CPU_GOVERNOR):
            ok += 1
    _log(f"  SET {ok}/{len(cores)} cores → {CPU_GOVERNOR}")


def apply_io_scheduler():
    _log("\n[4/4] I/O scheduler")
    devs = _block_devices()
    if not devs:
        _log("  SKIP — could not enumerate block devices")
        return
    for dev in devs:
        sched = IO_SCHEDULER_HDD if dev["rotational"] else IO_SCHEDULER_SSD
        sched_path = f"/sys/block/{dev['name']}/queue/scheduler"
        if not Path(sched_path).exists():
            continue
        cur = _read_sys(sched_path)
        if sched in cur:
            _log(f"  OK  {dev['name']} ({('HDD' if dev['rotational'] else 'SSD')}) = {sched}")
        elif _write_sys(sched_path, sched):
            _log(f"  SET {dev['name']} ({('HDD' if dev['rotational'] else 'SSD')}) → {sched}")
        else:
            _log(f"  FAIL {dev['name']}")


# ── Reset ─────────────────────────────────────────────────────────────────────

def reset_all():
    _log("Resetting to OS defaults...")
    for key, _, default_val, _ in SYSCTL_PROFILE:
        _sysctl_set(key, default_val)
        _log(f"  RESET {key} = {default_val}")
    for path, _, default_val in THP_PATHS:
        _write_sys(path, default_val)
        _log(f"  RESET {path} = {default_val}")
    cores = list(Path("/sys/devices/system/cpu").glob("cpu[0-9]*/cpufreq/scaling_governor"))
    for p in cores:
        _write_sys(str(p), CPU_GOVERNOR_RESET)
    _log(f"  RESET {len(cores)} cores → {CPU_GOVERNOR_RESET}")
    _log("Done — rebooting finalizes all defaults")


# ── Status ────────────────────────────────────────────────────────────────────

def show_status():
    print("\n" + "="*60)
    print("PHOENIX TUNER STATUS — LINUX")
    print("="*60)

    print("\nKernel parameters:")
    for key, perf_val, default_val, desc in SYSCTL_PROFILE:
        cur = _sysctl_get(key)
        tag = "TUNED" if cur == perf_val else ("DEFAULT" if cur == default_val else "CUSTOM")
        print(f"  [{tag:7s}]  {key} = {cur}  ({desc})")

    print("\nTransparent Huge Pages:")
    for path, perf_val, _ in THP_PATHS:
        cur = _read_sys(path)
        tag = "TUNED" if cur == perf_val else "DEFAULT"
        print(f"  [{tag}]  {path} = {cur}")

    print("\nCPU governor:")
    cores = list(Path("/sys/devices/system/cpu").glob("cpu[0-9]*/cpufreq/scaling_governor"))
    if cores:
        sample = cores[0].read_text().strip() if cores[0].exists() else "?"
        tag = "TUNED" if sample == CPU_GOVERNOR else "DEFAULT"
        print(f"  [{tag}]  {len(cores)} cores = {sample}")
    else:
        print("  [SKIP]  cpufreq not available")

    print("\nI/O scheduler:")
    for dev in _block_devices():
        sched_path = f"/sys/block/{dev['name']}/queue/scheduler"
        if Path(sched_path).exists():
            cur = _read_sys(sched_path)
            print(f"  {dev['name']} ({('HDD' if dev['rotational'] else 'SSD')}) = {cur}")

    print("\n" + "="*60)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    if os.geteuid() != 0:
        print("ERROR: requires root — run: sudo python3 phoenix_tuner_linux.py --apply")
        sys.exit(1)

    cmd = sys.argv[1] if len(sys.argv) > 1 else "--help"

    if cmd == "--apply":
        _log("="*60)
        _log("PHOENIX TUNER — APPLY")
        _log("="*60)
        apply_sysctl()
        apply_thp()
        apply_cpu_governor()
        apply_io_scheduler()
        _log("\nDone. Settings active immediately. Re-run after reboot or add to systemd.")
    elif cmd == "--status":
        show_status()
    elif cmd == "--reset":
        reset_all()
    else:
        print("Usage:")
        print("  sudo python3 phoenix_tuner_linux.py --apply   # apply performance profile")
        print("  sudo python3 phoenix_tuner_linux.py --status  # show current values")
        print("  sudo python3 phoenix_tuner_linux.py --reset   # restore OS defaults")


if __name__ == "__main__":
    main()
