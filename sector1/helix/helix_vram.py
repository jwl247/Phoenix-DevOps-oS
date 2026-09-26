"""
helix_vram.py - Helix Virtual RAM / memory manager (userspace Helix)
jwl247 / Jerry Leftwich - GPL v3

A full Helix, not a cache with Helix's name on it. Every Helix has the
Dandelion at her center; the double adds Strand B and the rungs. This one is
double. Her rules mirror the kernel dm-helix (sector1/kernels/dm_helix.c)
one for one, so the two can't drift:

  Dandelion   64 lanes. Load = ops this tick against her own peak on this
              machine (decays ~1.5%/tick, floor 200 ops/s); memory pressure
              counts as load too. Load >= 0.5: heat += load/10, compression
              factor = max(0.3, 1 - 0.7*load), state hot (surging > 0.8).
              Otherwise heat -= 0.05, compression relaxes +0.1, state cooling
              until fully relaxed, then cold.
  Cooling     She cools herself with data: freeing 5% of what she holds takes
              0.05 off her heat.
  Blocks      Temperatures from accesses in a 60 s window (>10 blazing, >5 hot,
              >2 warm, touched within 300 s cold, else frozen). Access
              intervals are smoothed (7/8) to predict the next access; a block
              due back within 2 s is never relieved.
  Strand A    RAM. Raw blocks (her L1+L2) and zlib-5 compressed blocks (L3).
  Strand B    Relief strand on a fast disk. Cold blocks go there instead of
              being dropped.
  Rungs       A block read back from Strand B keeps its B copy while unchanged,
              so relieving it again is zero-copy (just drop the RAM copy).
  zlib 5      Her compression format. Not 6, not "default".

Her real size (helix_complete_package.py:624, CLAUDE.md "4GB of 8GB RAM"):
L1 256 MB / L2 1024 MB / L3 3072 MB. Those are the defaults here; never shrink
them below her real config without Jerry's say-so.

Nothing is ever dropped silently. If Strand A and Strand B are both full, an
allocation raises HelixFullError. (The old helix_vram "evicted" by setting
data=None and then answered reads with None, counted as a hit.)

When the kernel Helix (helix.ko) is loaded, the libhelix bridge links her to
it: one Helix underneath. She follows the kernel Dandelion's heat and
compression (the hotter/tighter of the two wins) and reports her tier moves
to the kernel ledger with MEM_SYNC. Without helix.ko she runs on her own.
"""

import hashlib
import os
import pickle
import shutil
import sys
import tempfile
import threading
import time
import zlib
from collections import OrderedDict
from enum import Enum
from typing import Any, Dict, Optional

# ============================================================================
# HER CONSTANTS (dm_helix.c)
# ============================================================================

HX_LANES = 64
HX_ZLEVEL = 5
HX_Z_KEEP_MAX = 0.90          # keep a compressed copy only if <= 90% of raw
HX_TICK_S = 1.0
HX_Z_PER_TICK = 1024          # relief work cap per tick (blocks)
HX_PREDICT_GUARD_S = 2.0
HX_PEAK_FLOOR = 200           # ops/s
HX_WINDOW_S = 60
HX_COLD_S = 300

MB = 1024 * 1024


class MemoryTier(Enum):
    HOT = 0      # Strand A, raw
    WARM = 1     # Strand A, zlib-5 compressed
    COLD = 2     # Strand B only (relief strand, on disk)
    FROZEN = 3   # kept for API compatibility; she never silently drops data


class Temp(Enum):
    FROZEN = 0
    COLD = 1
    WARM = 2
    HOT = 3
    BLAZING = 4


COOL_STATES = ("cold", "warm", "hot", "surging", "cooling")


class HelixFullError(MemoryError):
    """Strand A and Strand B are both full. Raised instead of losing data."""


# ============================================================================
# BLOCK
# ============================================================================

class _Block:
    __slots__ = ("key", "lane", "raw", "z", "size", "pickled", "b_path", "b_size",
                 "win_start", "win_hits", "last", "interval", "ver", "incompressible")

    def __init__(self, key, lane, raw, pickled):
        now = time.monotonic()
        self.key = key
        self.lane = lane
        self.raw = raw                 # bytes on Strand A (raw) or None
        self.z = None                  # bytes on Strand A (zlib 5) or None
        self.size = len(raw)
        self.pickled = pickled
        self.b_path = None             # Strand B copy (rung) or None
        self.b_size = 0
        self.win_start = now
        self.win_hits = 0
        self.last = now
        self.interval = 0.0
        self.ver = 0
        self.incompressible = False   # zlib 5 did not pay once; skip retrying

    def touch(self):
        now = time.monotonic()
        if now - self.win_start >= HX_WINDOW_S:
            self.win_start = now
            self.win_hits = 0
        self.win_hits += 1
        dt = now - self.last
        self.interval = (self.interval * 7 + dt) / 8 if self.interval else dt
        self.last = now

    def temp(self, now=None) -> Temp:
        now = time.monotonic() if now is None else now
        recent = self.win_hits if now - self.win_start < HX_WINDOW_S else 0
        if recent > 10:
            return Temp.BLAZING
        if recent > 5:
            return Temp.HOT
        if recent > 2:
            return Temp.WARM
        if now - self.last < HX_COLD_S:
            return Temp.COLD
        return Temp.FROZEN

    def due_soon(self, now=None) -> bool:
        """OG PageMetrics._predict_next_access: next = last + mean interval."""
        if not self.interval:
            return False
        now = time.monotonic() if now is None else now
        predicted = self.last + self.interval
        return now < predicted < now + HX_PREDICT_GUARD_S

    @property
    def tier(self) -> MemoryTier:
        if self.raw is not None:
            return MemoryTier.HOT
        if self.z is not None:
            return MemoryTier.WARM
        return MemoryTier.COLD


class _Lane:
    __slots__ = ("lock", "blocks", "raw_lru", "z_lru", "raw_bytes", "z_bytes", "b_bytes")

    def __init__(self):
        self.lock = threading.RLock()
        self.blocks: Dict[str, "_Block"] = {}
        # Per-kind LRUs (oldest first) so the coldest raw / compressed block is
        # found in O(1) instead of rescanning the lane.
        self.raw_lru: "OrderedDict[str, None]" = OrderedDict()
        self.z_lru: "OrderedDict[str, None]" = OrderedDict()
        self.raw_bytes = 0
        self.z_bytes = 0
        self.b_bytes = 0


# ============================================================================
# THE KERNEL BRIDGE (optional)
# ============================================================================

def _kernel_feed():
    """KernelHelixFeed from libhelix, or None when helix.ko/libhelix aren't here."""
    if os.environ.get("HELIX_VRAM_NO_KERNEL") == "1":
        return None
    here = os.path.dirname(os.path.abspath(__file__))
    cand = os.environ.get("HELIX_LIBHELIX_DIR") or os.path.join(here, "..", "kernels", "libhelix")
    if not os.path.exists(os.path.join(cand, "libhelix.so")):
        return None
    if cand not in sys.path:
        sys.path.insert(0, cand)
    try:
        from helix import KernelHelixFeed   # noqa: WPS433 (runtime-optional)
        feed = KernelHelixFeed(register_as="helix-vram")
        return feed if feed.dandelion() else None
    except Exception:
        return None


# ============================================================================
# HELIX MEMORY MANAGER
# ============================================================================

class HelixMemoryManager:
    """A full double Helix in userspace. API kept from the old helix_vram:
    allocate/read/write/free/compress_tier/get_stats/print_stats."""

    def __init__(self,
                 max_hot_mb: int = 256,       # L1, raw
                 max_warm_mb: int = 1024,     # L2, raw
                 max_cold_mb: int = 3072,     # L3, zlib-5 compressed
                 strand_b_mb: int = 8192,     # Strand B on a fast disk
                 strand_b_dir: Optional[str] = None,
                 autostart: bool = True,
                 use_kernel: bool = True):
        self.raw_budget = (max_hot_mb + max_warm_mb) * MB
        self.z_budget = max_cold_mb * MB
        self.b_budget = strand_b_mb * MB
        base = strand_b_dir or os.environ.get("HELIX_VRAM_STRAND_B") or tempfile.gettempdir()
        os.makedirs(base, exist_ok=True)
        self.b_dir = tempfile.mkdtemp(prefix="helix-strandB-", dir=base)

        self.lanes = [_Lane() for _ in range(HX_LANES)]
        self._stat_lock = threading.Lock()
        self.stats = dict(allocations=0, deallocations=0, promotions=0, demotions=0,
                          compressions=0, decompressions=0, evictions=0, hits=0,
                          misses=0, bytes_saved=0, b_writes=0, b_hits=0,
                          b_zero_copy=0, zfail=0, refused=0, cooled_bytes=0)
        self._ops = 0
        self._last_ops = 0
        self._peak = 0.0
        self.heat = 0.0
        self.compression = 1.0
        self.state = "cold"
        self._moved = [0, 0, 0, 0]     # bytes moved into each tier this tick (ledger)
        self._room_lane = 0

        self._feed = _kernel_feed() if use_kernel else None
        self._stop = threading.Event()
        self._ticker = None
        if autostart:
            self._ticker = threading.Thread(target=self._run, name="helix-dandelion", daemon=True)
            self._ticker.start()

    # ------------------------------------------------------------- helpers
    def _lane_of(self, key: str) -> _Lane:
        h = int.from_bytes(hashlib.blake2b(key.encode("utf-8"), digest_size=4).digest(), "little")
        return self.lanes[h % HX_LANES]

    def _count(self, name, n=1):
        with self._stat_lock:
            self.stats[name] += n

    # pickle: she only ever unpickles bytes this same process pickled. Strand B
    # files live in a private mkdtemp() directory (mode 0700), so no other user
    # can plant one there. Never point strand_b_dir at a shared, writable path.
    @staticmethod
    def _encode(data: Any):
        if isinstance(data, (bytes, bytearray, memoryview)):
            return bytes(data), False
        return pickle.dumps(data, protocol=pickle.HIGHEST_PROTOCOL), True

    @staticmethod
    def _decode(raw: bytes, pickled: bool):
        return pickle.loads(raw) if pickled else raw

    def _totals(self):
        raw = z = b = 0
        for ln in self.lanes:
            raw += ln.raw_bytes
            z += ln.z_bytes
            b += ln.b_bytes
        return raw, z, b

    # --------------------------------------------------- tier moves (lane locked)
    def _compress(self, ln: _Lane, blk: _Block) -> int:
        """Raw -> zlib 5 on Strand A. Returns bytes freed."""
        if blk.raw is None or blk.incompressible:
            return 0
        z = zlib.compress(blk.raw, HX_ZLEVEL)
        if len(z) > blk.size * HX_Z_KEEP_MAX:
            blk.incompressible = True  # doesn't pay; leave it raw, don't retry
            return 0
        blk.z = z
        blk.raw = None
        ln.raw_bytes -= blk.size
        ln.z_bytes += len(z)
        ln.raw_lru.pop(blk.key, None)
        ln.z_lru[blk.key] = None
        self._count("compressions")
        self._count("demotions")
        self._count("bytes_saved", blk.size - len(z))
        self._moved[MemoryTier.WARM.value] += len(z)
        return blk.size - len(z)

    def _to_strand_b(self, ln: _Lane, blk: _Block) -> int:
        """Strand A -> Strand B. Zero-copy when a clean rung already holds it."""
        freed = 0
        if blk.b_path is None:
            _, _, b_total = self._totals()
            if b_total >= self.b_budget:
                return 0               # Strand B full: don't spend a compress on it
            payload = blk.z if blk.z is not None else zlib.compress(blk.raw, HX_ZLEVEL)
            if b_total + len(payload) > self.b_budget:
                return 0
            sub = os.path.join(self.b_dir, "%02d" % (self.lanes.index(ln)))
            os.makedirs(sub, exist_ok=True)
            path = os.path.join(sub, hashlib.sha1(blk.key.encode("utf-8")).hexdigest())
            with open(path, "wb") as f:
                f.write(payload)
            blk.b_path, blk.b_size = path, len(payload)
            ln.b_bytes += len(payload)
            self._count("b_writes")
            self._moved[MemoryTier.COLD.value] += len(payload)
        else:
            self._count("b_zero_copy")
        if blk.raw is not None:
            freed += blk.size
            ln.raw_bytes -= blk.size
            blk.raw = None
        if blk.z is not None:
            freed += len(blk.z)
            ln.z_bytes -= len(blk.z)
            blk.z = None
        ln.raw_lru.pop(blk.key, None)
        ln.z_lru.pop(blk.key, None)
        self._count("demotions")
        self._count("evictions")
        return freed

    def _drop_rung(self, ln: _Lane, blk: _Block):
        if blk.b_path is not None:
            try:
                os.unlink(blk.b_path)
            except OSError:
                pass
            ln.b_bytes -= blk.b_size
            blk.b_path, blk.b_size = None, 0

    def _materialize(self, ln: _Lane, blk: _Block) -> bytes:
        """Bring a block back to raw on Strand A (the rung keeps its B copy)."""
        if blk.raw is not None:
            return blk.raw
        if blk.z is not None:
            try:
                raw = zlib.decompress(blk.z)
            except zlib.error:
                self._count("zfail")
                raise
            ln.z_bytes -= len(blk.z)
            blk.z = None
            ln.z_lru.pop(blk.key, None)
            self._count("decompressions")
        else:
            with open(blk.b_path, "rb") as f:
                raw = zlib.decompress(f.read())
            self._count("b_hits")
        blk.raw = raw
        ln.raw_bytes += blk.size
        ln.raw_lru[blk.key] = None
        self._count("promotions")
        self._moved[MemoryTier.HOT.value] += blk.size
        return raw

    # ------------------------------------------------------- capacity
    def _make_room(self, refuse: bool = False):
        """Keep Strand A inside her budgets: coldest raw -> zlib 5 (straight to
        Strand B if it won't compress), then coldest compressed -> Strand B.
        Blocks due back soon are skipped. With refuse=True (new allocations
        only) raises HelixFullError when nothing can move; reads and
        housekeeping never raise, they just relieve what they can."""
        now = time.monotonic()
        for kind in ("raw", "z"):
            raw, z, _ = self._totals()
            excess = (raw - self.raw_budget) if kind == "raw" else (z - self.z_budget)
            if excess <= 0:
                continue
            self._room_lane = (self._room_lane + 1) % HX_LANES
            for i in range(HX_LANES):
                if excess <= 0:
                    break
                ln = self.lanes[(self._room_lane + i) % HX_LANES]
                with ln.lock:
                    lru = ln.raw_lru if kind == "raw" else ln.z_lru
                    for key in list(lru):
                        if excess <= 0:
                            break
                        blk = ln.blocks[key]
                        if blk.due_soon(now):
                            continue
                        if kind == "raw":
                            freed = self._compress(ln, blk) or self._to_strand_b(ln, blk)
                        else:
                            freed = self._to_strand_b(ln, blk)
                        excess -= freed
        if not refuse:
            return
        raw, z, _ = self._totals()
        # Nothing could move and she's past her budget: refuse, loudly.
        # (Checking only raw: incompressible data never reaches the z tier, so
        # a "z is full too" condition would let raw grow without bound.)
        if raw > self.raw_budget * 1.25 or z > self.z_budget * 1.25:
            self._count("refused")
            raise HelixFullError("Helix: Strand A and Strand B are full; refusing rather than dropping data")

    # ------------------------------------------------------- public API
    def allocate(self, key: str, data: Any) -> bool:
        raw, pickled = self._encode(data)
        ln = self._lane_of(key)
        with ln.lock:
            old = ln.blocks.pop(key, None)
            if old is not None:
                self._forget(ln, old)
            blk = _Block(key, ln, raw, pickled)
            blk.touch()
            ln.blocks[key] = blk
            ln.raw_lru[key] = None
            ln.raw_bytes += blk.size
            self._moved[MemoryTier.HOT.value] += blk.size
        self._count("allocations")
        self._ops += 1
        try:
            self._make_room(refuse=True)
        except HelixFullError:
            with ln.lock:
                if ln.blocks.get(key) is blk:
                    del ln.blocks[key]
                    self._forget(ln, blk)
            raise
        return True

    def read(self, key: str) -> Optional[Any]:
        ln = self._lane_of(key)
        with ln.lock:
            blk = ln.blocks.get(key)
            if blk is None:
                self._count("misses")
                self._ops += 1
                return None
            raw = self._materialize(ln, blk)
            blk.touch()
            ln.raw_lru.move_to_end(key)
            self._count("hits")
            self._ops += 1
            value = self._decode(raw, blk.pickled)
        self._make_room()
        return value

    def write(self, key: str, data: Any) -> bool:
        ln = self._lane_of(key)
        raw, pickled = self._encode(data)
        with ln.lock:
            blk = ln.blocks.get(key)
            if blk is None:
                return self.allocate(key, data)
            self._forget(ln, blk, keep_entry=True)   # new version: old copies + rung go
            blk.raw, blk.size, blk.pickled = raw, len(raw), pickled
            blk.incompressible = False
            blk.ver += 1
            ln.raw_bytes += blk.size
            ln.raw_lru[key] = None
            blk.touch()
        self._ops += 1
        self._make_room()
        return True

    def _forget(self, ln: _Lane, blk: _Block, keep_entry=False):
        if blk.raw is not None:
            ln.raw_bytes -= blk.size
            blk.raw = None
        if blk.z is not None:
            ln.z_bytes -= len(blk.z)
            blk.z = None
        ln.raw_lru.pop(blk.key, None)
        ln.z_lru.pop(blk.key, None)
        self._drop_rung(ln, blk)

    def free(self, key: str) -> bool:
        ln = self._lane_of(key)
        with ln.lock:
            blk = ln.blocks.pop(key, None)
            if blk is None:
                return False
            self._forget(ln, blk)
        self._count("deallocations")
        return True

    def compress_tier(self, tier: MemoryTier) -> int:
        """Force every raw block of `tier` (HOT) to zlib 5."""
        n = 0
        if tier != MemoryTier.HOT:
            return 0
        for ln in self.lanes:
            with ln.lock:
                for key in list(ln.raw_lru):
                    if self._compress(ln, ln.blocks[key]):
                        n += 1
        return n

    # ------------------------------------------------------- the Dandelion
    def _mem_pressure(self) -> float:
        try:
            info = {}
            with open("/proc/meminfo") as f:
                for line in f:
                    k, v = line.split(":", 1)
                    info[k] = int(v.split()[0])
            return 1.0 - info["MemAvailable"] / info["MemTotal"]
        except (OSError, KeyError, ValueError):
            return 0.0

    def tick(self, dt: float = HX_TICK_S) -> Dict:
        """One Dandelion tick. Runs every second on her own thread; callable
        directly for tests."""
        ops = self._ops
        dops = ops - self._last_ops
        self._last_ops = ops
        rate = dops / max(dt, 1e-9)
        if rate > self._peak:
            self._peak = rate
        else:
            self._peak -= self._peak / 64
        ref = max(self._peak, HX_PEAK_FLOOR)
        io_load = min(1.0, rate / ref)
        load = max(io_load, self._mem_pressure())

        if load >= 0.5:
            self.heat = min(1.0, self.heat + load / 10)
            self.compression = max(0.3, 1.0 - load * 0.7)
            self.state = "surging" if load > 0.8 else "hot"
        else:
            self.heat = max(0.0, self.heat - 0.05)
            self.compression = min(1.0, self.compression + 0.1)
            self.state = "cooling" if self.compression < 1.0 else "cold"

        kernel = self._feed.dandelion() if self._feed is not None else {}
        if kernel:   # one Helix underneath: follow her kernel center when it's hotter
            self.heat = max(self.heat, kernel["heat"])
            self.compression = min(self.compression, kernel["compression"])
            if COOL_STATES.index(kernel["state"]) > COOL_STATES.index(self.state) \
                    if kernel["state"] in COOL_STATES else False:
                self.state = kernel["state"]

        freed = self._relieve() if self.compression < 1.0 else 0
        raw, z, b = self._totals()
        held = raw + z
        if freed:   # she cools herself with data
            self.heat = max(0.0, self.heat - freed / max(1, held + freed))
            self._count("cooled_bytes", freed)

        if self._feed is not None:
            # Her kernel ledger's tiers (helix.h): 0 HOT, 1 WARM, 2 COMPRESSED,
            # 3 COLD. Ours: raw -> HOT, zlib 5 -> COMPRESSED, Strand B -> COLD.
            ledger = {MemoryTier.HOT.value: 0, MemoryTier.WARM.value: 2,
                      MemoryTier.COLD.value: 3}
            for tier, nbytes in enumerate(self._moved):
                if nbytes and tier in ledger:
                    self._feed.mem_sync(0, nbytes, ledger[tier])
        self._moved = [0, 0, 0, 0]
        return {"heat": self.heat, "state": self.state, "compression": self.compression,
                "load": load, "freed": freed, "kernel": bool(kernel)}

    def _relieve(self) -> int:
        """Under load (dm_helix.c hx_relieve): keep only `compression` of each
        lane's blocks raw. Cold blocks go to Strand B; cool ones compress
        (warm ones too when surging). Blocks due back soon are left alone."""
        now = time.monotonic()
        budget = HX_Z_PER_TICK
        freed = 0
        surging = self.state == "surging"
        for ln in self.lanes:
            if budget <= 0:
                break
            with ln.lock:
                keep_raw = int(len(ln.blocks) * self.compression)
                for key in list(ln.raw_lru):
                    if len(ln.raw_lru) <= keep_raw or budget <= 0:
                        break
                    blk = ln.blocks[key]
                    if blk.due_soon(now):
                        continue
                    t = blk.temp(now)
                    if t.value <= Temp.COLD.value:
                        got = self._to_strand_b(ln, blk)
                    elif t.value <= (Temp.WARM.value if surging else Temp.COLD.value):
                        got = self._compress(ln, blk)
                    else:
                        continue
                    if got:
                        freed += got
                        budget -= 1
        return freed

    def _run(self):
        last = time.monotonic()
        while not self._stop.wait(HX_TICK_S):
            now = time.monotonic()
            try:
                self.tick(now - last)
            except Exception as e:   # the center must not die on one bad tick
                print(f"[helix-vram] tick error: {e}", file=sys.stderr)
            last = now

    # ------------------------------------------------------- telemetry
    def temperatures(self) -> Dict[str, int]:
        now = time.monotonic()
        out = {t.name.lower(): 0 for t in Temp}
        for ln in self.lanes:
            with ln.lock:
                for blk in ln.blocks.values():
                    out[blk.temp(now).name.lower()] += 1
        return out

    def get_tier_snapshot(self) -> Dict:
        """For sector4/paging.py (AIPagingManager.attach_helix)."""
        raw, z, b = self._totals()
        s = self.get_stats()
        return {"timestamp": time.time(), "hot_mb": raw / MB, "warm_mb": z / MB,
                "cold_mb": b / MB, "frozen_mb": 0.0 if not self.stats["refused"] else b / MB,
                "hit_rate": s["hit_rate"], "promotions": self.stats["promotions"],
                "demotions": self.stats["demotions"], "evictions": self.stats["evictions"],
                "dandelion_heat": self.heat, "dandelion_state": self.state}

    def get_stats(self) -> Dict:
        raw, z, b = self._totals()
        counts = {"hot": 0, "warm": 0, "cold": 0}
        rungs = 0
        for ln in self.lanes:
            with ln.lock:
                for blk in ln.blocks.values():
                    counts[blk.tier.name.lower()] += 1
                    if blk.b_path is not None and (blk.raw is not None or blk.z is not None):
                        rungs += 1
        with self._stat_lock:
            st = dict(self.stats)
        asked = st["hits"] + st["misses"]
        return {
            "total_blocks": sum(counts.values()),
            "hot_blocks": counts["hot"], "warm_blocks": counts["warm"],
            "cold_blocks": counts["cold"], "frozen_blocks": 0, "rungs": rungs,
            "hot_usage_mb": raw / MB, "warm_usage_mb": z / MB, "cold_usage_mb": b / MB,
            "total_usage_mb": (raw + z + b) / MB,
            "bytes_saved_mb": st["bytes_saved"] / MB,
            "hit_rate": (st["hits"] / asked * 100.0) if asked else 0.0,
            "dandelion": {"heat": round(self.heat, 3), "state": self.state,
                          "compression": round(self.compression, 3),
                          "kernel_linked": self._feed is not None},
            "temperatures": self.temperatures(),
            **st,
        }

    def print_stats(self):
        s = self.get_stats()
        d = s["dandelion"]
        print("\n" + "=" * 70)
        print("HELIX VIRTUAL RAM")
        print("=" * 70)
        print(f"  Dandelion: heat {d['heat']:.3f}  state {d['state']}  "
              f"compression {d['compression']:.2f}  kernel {'linked' if d['kernel_linked'] else 'standalone'}")
        print(f"  Strand A raw   : {s['hot_usage_mb']:9.2f} MB ({s['hot_blocks']:,} blocks)")
        print(f"  Strand A zlib5 : {s['warm_usage_mb']:9.2f} MB ({s['warm_blocks']:,} blocks)")
        print(f"  Strand B       : {s['cold_usage_mb']:9.2f} MB ({s['cold_blocks']:,} blocks, "
              f"{s['rungs']:,} rungs)")
        print(f"  Hit rate {s['hit_rate']:.1f}%  saved {s['bytes_saved_mb']:.2f} MB  "
              f"B hits {s['b_hits']:,}  zero-copy {s['b_zero_copy']:,}  refused {s['refused']:,}")
        print(f"  Temperatures: {s['temperatures']}")

    def close(self):
        self._stop.set()
        if self._ticker is not None:
            self._ticker.join(timeout=5)
        shutil.rmtree(self.b_dir, ignore_errors=True)
        if self._feed is not None:
            self._feed.close()
            self._feed = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


if __name__ == "__main__":
    with HelixMemoryManager() as m:
        for i in range(20000):
            m.allocate(f"block_{i}", {"id": i, "payload": "x" * 1000})
        for _ in range(3):
            for i in range(500):
                m.read(f"block_{i}")
        m.tick()
        m.print_stats()
