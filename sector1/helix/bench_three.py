#!/usr/bin/env python3
"""
bench_three.py — the same test, three contenders: Frank's storage system, New Horizon, the OG Double Helix.
Phoenix DevOps OS | sector1/helix | jwl247 | GPL v3

Jerry 2026-10-07: "lets bench frank then new horizon then the old helix herself". Jerry runs it; the numbers
are printed by this script on his screen and written to a JSON file next to it. Claude built the test and
does not run it (see docs/helix/BENCH-BY-HAND.md: "Claude advises only for this bench").

    python bench_three.py --check                 # 10 items each: can every contender store + return the
                                                  # exact bytes? PASS/FAIL only, no timings
    python bench_three.py                         # the bench: frank, then new horizon, then og
    python bench_three.py --only og --items 50000 --data text

The contenders (each runs in its OWN fresh Python process, one after another, so none inherits another's
memory or warmed caches):
    frank  C:\\Users\\jwlef\\Music\\franken.py      HelixSystem -> memory.malloc(key, data) / memory.read(key)
    nh     sector4/ring/helix_new_horizon.py       DoubleHelixStorageSystem.store_data / retrieve_data
    og     C:\\Users\\jwlef\\helix_recovery\\og_double_helix.py   DoubleHelixStorageSystem.store_data / retrieve_data
Paths can be changed with --frank / --nh / --og.

What every contender gets, identically:
  1. WRITE: --items values of --size bytes, keys "k000000"..; per-op latency recorded.
  2. READ:  --reads lookups; key chosen by a zipf(1.1) draw with a fixed --seed (some keys hot, most cold);
            per-op latency recorded; EVERY returned value checked byte-for-byte against what was written
            (SHA-256), so a wrong or missing answer is counted, never hidden.
  --data random = incompressible bytes (honest default; zeros or text would flatter zlib)
  --data text   = repetitive text (compresses well), to see the other side.

Reported per contender: write and read ops/s, p50 / p90 / p99 / max latency (microseconds), wrong answers,
missing answers, peak memory of its process, and for nh/og the size of their packet_registry — a plain dict
that keeps EVERY packet forever, so reads can be answered from it even when the tiers evicted the packet.
If the registry holds every item, their read speed is a dict lookup, not their tiers. Read that column.
"""

import argparse
import asyncio
import hashlib
import importlib.util
import json
import os
import random
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
TESTING = REPO / "Testing Facilty"          # Jerry's nominations (10/7)
DEFAULTS = {
    "frank": TESTING / "franken.py",
    "nh":    TESTING / "helix_new_horizon.py",    # Jerry's original, not the sector4/ring copy
    "free":  REPO / "sector4" / "ring" / "freewheeling.py",
    "orig":  Path("F:/Phoenix/Vault/OG_double_helix_complete.py"),   # the ORIGINAL OG, before the 9/30 fixes   # the old timer: standalone Helix, HelixDB
    "og":    Path(r"C:\Users\jwlef\helix_recovery\og_double_helix.py") if os.name == "nt" else Path.home() / "helix_recovery/og_double_helix.py",
}
NAMES = {"frank": "Frank's storage system (franken.py)", "nh": "New Horizon", "og": "OG Double Helix",
         "free": "Freewheeling (HelixDB)", "orig": "OG Double Helix ORIGINAL"}


def peak_memory_mb():
    """Peak resident memory of THIS process, MB (Windows: PeakWorkingSetSize; Linux: VmHWM)."""
    try:
        import psutil                                   # the ctypes path below read 0.0 on Windows (10/7)
        mi = psutil.Process().memory_info()
        return round(getattr(mi, "peak_wset", 0) / 2**20, 1) or round(mi.rss / 2**20, 1)
    except Exception:
        pass
    try:
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes

            class PMC(ctypes.Structure):
                _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                            ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                            ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
            pmc = PMC(); pmc.cb = ctypes.sizeof(PMC)
            ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb)
            return round(pmc.PeakWorkingSetSize / 2**20, 1)
        for line in open("/proc/self/status"):
            if line.startswith("VmHWM:"):
                return round(int(line.split()[1]) / 1024, 1)
    except Exception:
        pass
    return None


def load_module(name, path):
    if not Path(path).is_file():
        raise FileNotFoundError(f"{name}: {path} not found (pass --{name} <path>)")
    sys.path.insert(0, str(Path(path).parent))
    spec = importlib.util.spec_from_file_location(f"bench_{name}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Frank:
    def __init__(self, path, _t3):
        m = load_module("frank", path)
        self.sys = m.HelixSystem(l1_mb=512, l2_mb=2048, l3_mb=6000, vram_mb=8096)   # his own defaults
        self.registry = None

    async def put(self, k, v):
        if not self.sys.memory.malloc(k, v):
            raise MemoryError("malloc refused (virtual limit)")

    async def get(self, k):
        return self.sys.memory.read(k)


class _DoubleHelix:
    def __init__(self, name, path, t3):
        m = load_module(name, path)
        self.np = getattr(m, "np", None)
        cls = m.DoubleHelixStorageSystem
        try:
            self.sys = cls(t3_path=t3)          # New Horizon: T3 on a temp folder, not /mnt/nvme
        except TypeError:
            self.sys = cls()                    # OG: no T3 path argument

    @property
    def registry(self):
        return len(getattr(self.sys, "packet_registry", {}) or {})

    async def put(self, k, v):
        await self.sys.store_data(k, v)

    async def get(self, k):
        r = await self.sys.retrieve_data(k)
        if r is None or isinstance(r, (bytes, bytearray)):
            return r
        if self.np is not None and isinstance(r, self.np.ndarray):
            return r.tobytes()
        return r if isinstance(r, (bytes, bytearray)) else bytes(r) if isinstance(r, (list, tuple)) else r


class Free:
    """Freewheeling's HelixDB: store(key, data) / get(key) — sync, quad packets, Dandelion lanes."""
    def __init__(self, path, _t3):
        m = load_module("free", path)
        self.db = m.HelixDB(initial_levels=5)
        self.registry = None

    async def put(self, k, v):
        self.db.store(k, v)

    async def get(self, k):
        r = self.db.get(k)
        if r is None or isinstance(r, (bytes, bytearray)):
            return r
        return getattr(r, "_raw_data", None) or getattr(r, "raw_data", None) or r


ADAPTERS = {"frank": Frank, "free": Free,
            "nh": lambda p, t3: _DoubleHelix("nh", p, t3),
            "og": lambda p, t3: _DoubleHelix("og", p, t3),
            "orig": lambda p, t3: _DoubleHelix("orig", p, t3)}


def make_values(n, size, kind, seed):
    rnd = random.Random(seed)
    if kind == "text":
        words = b"helix strand dandelion rung tier warm hot cold quad phoenix frank conductor ".split()
        out = []
        for _ in range(n):
            b = bytearray()
            while len(b) < size:
                b += rnd.choice(words) + b" "
            out.append(bytes(b[:size]))
        return out
    return [rnd.randbytes(size) for _ in range(n)]


def pct(sorted_us, q):
    if not sorted_us:
        return None
    return round(sorted_us[min(len(sorted_us) - 1, int(q * len(sorted_us)))], 1)


def summarize(lat_ns, seconds):
    us = sorted(x / 1000 for x in lat_ns)
    return {"ops": len(us), "ops_per_s": round(len(us) / seconds, 1) if seconds else None,
            "p50_us": pct(us, .50), "p90_us": pct(us, .90), "p99_us": pct(us, .99),
            "max_us": round(us[-1], 1) if us else None}


async def run_one(name, path, a):
    t3 = tempfile.mkdtemp(prefix=f"bench_{name}_t3_")
    sut = ADAPTERS[name](path, t3)
    keys = [f"k{i:06d}" for i in range(a.items)]
    values = make_values(a.items, a.size, a.data, a.seed)
    want = [hashlib.sha256(v).digest() for v in values]

    def same(got, i):
        if isinstance(got, (bytes, bytearray)):
            return hashlib.sha256(bytes(got)).digest() == want[i]
        return False

    lat = []
    t0 = time.perf_counter()
    for k, v in zip(keys, values):
        s = time.perf_counter_ns(); await sut.put(k, v); lat.append(time.perf_counter_ns() - s)
    wsec = time.perf_counter() - t0
    write = summarize(lat, wsec)

    rnd = random.Random(a.seed)
    wrong = missing = 0
    lat = []
    t0 = time.perf_counter()
    for _ in range(a.reads):
        z = rnd.paretovariate(0.1 + 1.0)            # zipf-like: low ranks hot, long cold tail
        i = min(a.items - 1, int(z) - 1)
        s = time.perf_counter_ns(); got = await sut.get(keys[i]); lat.append(time.perf_counter_ns() - s)
        if got is None:
            missing += 1
        elif not same(got, i):
            wrong += 1
    rsec = time.perf_counter() - t0
    read = summarize(lat, rsec)
    return {"contender": name, "label": NAMES[name], "python": sys.version.split()[0], "platform": sys.platform,
            "items": a.items, "size": a.size, "data": a.data, "reads": a.reads, "seed": a.seed,
            "write": write, "read": read, "wrong_answers": wrong, "missing_answers": missing,
            "peak_mem_mb": peak_memory_mb(), "registry_items": getattr(sut, "registry", None)}


async def check_one(name, path):
    t3 = tempfile.mkdtemp(prefix=f"check_{name}_t3_")
    sut = ADAPTERS[name](path, t3)
    vals = make_values(10, 4096, "random", 1)
    for i, v in enumerate(vals):
        await sut.put(f"c{i}", v)
    bad = 0
    for i, v in enumerate(vals):
        got = await sut.get(f"c{i}")
        if not isinstance(got, (bytes, bytearray)) or bytes(got) != v:
            bad += 1
    return bad


def child(a):
    """Runs ONE contender in this (fresh) process and prints one JSON line."""
    path = getattr(a, a.one)
    import contextlib, io
    noise = io.StringIO()
    try:
        with contextlib.redirect_stdout(noise):          # the contenders print banners; keep them out of the result
            if a.check:
                bad = asyncio.run(check_one(a.one, path))
                res = {"contender": a.one, "check": "PASS" if bad == 0 else f"FAIL ({bad}/10 wrong or missing)"}
            else:
                res = asyncio.run(run_one(a.one, path, a))
                if a.hold:
                    time.sleep(a.hold)
    except Exception as e:
        res = {"contender": a.one, "error": f"{type(e).__name__}: {e}"}
    print("RESULT " + json.dumps(res))


def main():
    p = argparse.ArgumentParser(description="Frank vs New Horizon vs OG Double Helix — same test, Jerry runs it")
    p.add_argument("--only", choices=["frank", "nh", "og", "free", "orig"], help="run just one contender")
    p.add_argument("--items", type=int, default=20000)
    p.add_argument("--size", type=int, default=4096, help="bytes per value")
    p.add_argument("--reads", type=int, default=100000)
    p.add_argument("--data", choices=["random", "text"], default="random")
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--check", action="store_true", help="10 items each, PASS/FAIL only")
    p.add_argument("--hold", type=float, default=0, help="seconds each contender stays alive after its run (to read it in Process Explorer)")
    p.add_argument("--out", default=str(HERE / f"bench_three-{time.strftime('%Y%m%d-%H%M%S')}.json"))
    for k, v in DEFAULTS.items():
        p.add_argument(f"--{k}", default=str(v), help=f"path to {NAMES[k]}")
    p.add_argument("--one", help=argparse.SUPPRESS)
    a = p.parse_args()
    if a.one:
        return child(a)

    order = [a.only] if a.only else ["frank", "nh", "og", "free", "orig"]
    results = []
    for name in order:
        print(f"\n== {NAMES[name]} ...", flush=True)
        cmd = [sys.executable, str(Path(__file__).resolve()), "--one", name,
               "--items", str(a.items), "--size", str(a.size), "--reads", str(a.reads),
               "--data", a.data, "--seed", str(a.seed), "--hold", str(a.hold),
               "--frank", a.frank, "--nh", a.nh, "--og", a.og, "--free", a.free, "--orig", a.orig] + (["--check"] if a.check else [])
        out = subprocess.run(cmd, capture_output=True, text=True)
        line = next((l for l in out.stdout.splitlines() if l.startswith("RESULT ")), None)
        res = json.loads(line[7:]) if line else {"contender": name, "error": (out.stderr or out.stdout)[-800:]}
        results.append(res)
        print("   " + json.dumps(res))

    if a.check:
        return
    Path(a.out).write_text(json.dumps(results, indent=1), encoding="utf-8")
    print(f"\n{'contender':34} {'write ops/s':>12} {'read ops/s':>12} {'read p50 us':>12} {'read p99 us':>12} "
          f"{'wrong':>6} {'missing':>8} {'peak MB':>8} {'registry':>9}")
    for r in results:
        if "error" in r:
            print(f"{NAMES[r['contender']]:34} ERROR {r['error'][:90]}")
            continue
        print(f"{r['label']:34} {r['write']['ops_per_s']:>12} {r['read']['ops_per_s']:>12} {r['read']['p50_us']:>12} "
              f"{r['read']['p99_us']:>12} {r['wrong_answers']:>6} {r['missing_answers']:>8} "
              f"{str(r['peak_mem_mb']):>8} {str(r['registry_items']):>9}")
    print(f"\nfull results: {a.out}")


if __name__ == "__main__":
    main()
