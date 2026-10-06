"""
Helix Complete Memory Stack
Virtual RAM + Cache + Filesystem Integration

Components:
  HelixCache        -- Multi-level LRU cache (L1 hot / L2 warm / L3 compressed)
  HelixMemoryManager -- Virtual RAM allocator backed by the cache tiers
  HelixFS           -- Filesystem read/write layer with cache pass-through
  HelixSystem       -- Unified entry point wiring all three together

Platform: Any — Windows, Linux, macOS, Android/Termux, ARM SBC (Raspberry Pi etc.)
          Userspace Python is fully cross-platform. HelixHostProfile (below) auto-
          detects OS, architecture, and available RAM at startup and scales cache
          tiers accordingly. No platform-specific syscalls in userspace code.

Status:   Userspace implementation. Future kernel integration paths remain Linux-
          specific (FUSE, LD_PRELOAD, kernel module) but are not required for
          operation on any supported platform.

Integration paths:
  A) FUSE filesystem  -- mount point; transparent to any application
  B) LD_PRELOAD       -- intercept libc malloc/free; no kernel changes needed
  C) Kernel module    -- hook into page fault handler; highest performance
  D) Userspace (this) -- explicit API; use directly from Python applications
"""

import time
import math
import hashlib
import pickle
import zlib
import os
import sys
import platform as _platform
import json
import logging
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Optional, Dict, Tuple
from enum import Enum
import threading
import struct

log = logging.getLogger("helix_stack")

# ---------------------------------------------------------------------------
# Dandelion constants — mirrors kernel dm_helix.c / helix.h
# ---------------------------------------------------------------------------

HX_LANES      = 64     # number of thermal lanes
HX_ZLEVEL     = 5      # kernel-side zlib level (Python cache uses 6 — independent)
HX_TICK_MS    = 1000   # ms between Dandelion thermal ticks
HX_PEAK_FLOOR = 200    # ops/s — lane is "hot" above this threshold


# ---------------------------------------------------------------------------
# Dandelion Controller — 64-lane heat/compression controller
# ---------------------------------------------------------------------------

class DandelionController:
    """
    Python-userspace mirror of the kernel's Dandelion (dm_helix.c hx_aggr[]).

    Each of the 64 lanes tracks smoothed ops/s via EMA (α=0.3).
    Lane assignment: hash(key) % HX_LANES.
    Above HX_PEAK_FLOOR ops/s → lane is hot → HelixCache promotes aggressively.
    Below floor under global pressure → demote L2→L3, compress L3 early.

    The background tick thread fires every HX_TICK_MS milliseconds and
    rolls raw per-lane counts into smoothed heat figures. Daemon thread —
    dies silently when the process exits.
    """

    def __init__(self):
        self._ops:      list  = [0]   * HX_LANES   # raw op counts since last tick
        self._heat:     list  = [0.0] * HX_LANES   # smoothed ops/s
        self._lock      = threading.Lock()
        self._last_tick = time.monotonic()
        self._running   = True
        t = threading.Thread(
            target=self._tick_loop, daemon=True, name="dandelion_tick"
        )
        t.start()

    # -- public API --

    def touch(self, key: str) -> None:
        """Record one cache op on this key's lane."""
        lane = abs(hash(key)) % HX_LANES
        with self._lock:
            self._ops[lane] += 1

    def heat(self, key: str) -> float:
        """Smoothed ops/s for this key's lane."""
        lane = abs(hash(key)) % HX_LANES
        with self._lock:
            return self._heat[lane]

    def is_hot(self, key: str) -> bool:
        """True if this lane exceeds HX_PEAK_FLOOR ops/s."""
        return self.heat(key) >= HX_PEAK_FLOOR

    def lane_pressure(self) -> float:
        """
        Global thermal pressure: mean lane heat, normalized 0.0–1.0.
        0.0 = all lanes idle. 1.0 = mean heat at 10× HX_PEAK_FLOOR.
        """
        with self._lock:
            mean = sum(self._heat) / HX_LANES
        return min(mean / (HX_PEAK_FLOOR * 10.0), 1.0)

    def snapshot(self) -> dict:
        """Per-lane heat snapshot for diagnostics and get_tier_snapshot()."""
        with self._lock:
            heat = list(self._heat)
        hot = sum(1 for h in heat if h >= HX_PEAK_FLOOR)
        return {
            "lanes":      HX_LANES,
            "mean_heat":  sum(heat) / HX_LANES,
            "peak_heat":  max(heat),
            "hot_lanes":  hot,
            "pressure":   min(sum(heat) / HX_LANES / (HX_PEAK_FLOOR * 10.0), 1.0),
        }

    # -- internal tick --

    def _tick_loop(self) -> None:
        interval = HX_TICK_MS / 1000.0
        while self._running:
            time.sleep(interval)
            now = time.monotonic()
            with self._lock:
                dt = now - self._last_tick
                self._last_tick = now
                for i in range(HX_LANES):
                    raw = self._ops[i] / dt if dt > 0 else 0.0
                    # EMA smoothing α=0.3
                    self._heat[i] = 0.7 * self._heat[i] + 0.3 * raw
                    self._ops[i]  = 0


# ---------------------------------------------------------------------------
# Shared types
# ---------------------------------------------------------------------------

class MemoryTier(Enum):
    L1_HOT        = 0   # Frequently accessed; served without eviction pressure
    L2_WARM       = 1   # Occasionally accessed; promoted on repeated access
    L3_COMPRESSED = 2   # Compressed; decompressed on promotion
    L4_COLD       = 3   # Candidate for eviction
    L5_DISK       = 4   # Disk-backed (not yet implemented)


class AccessPattern(Enum):
    SEQUENTIAL = "sequential"
    RANDOM     = "random"
    TEMPORAL   = "temporal"
    SPATIAL    = "spatial"


@dataclass
class CacheBlock:
    key:            str
    data:           Any
    tier:           MemoryTier
    size_bytes:     int
    access_count:   int            = 0
    last_access:    float          = field(default_factory=time.time)
    access_pattern: AccessPattern  = AccessPattern.RANDOM
    compressed:     bool           = False
    dirty:          bool           = False
    pinned:         bool           = False
    _compressed_data: Optional[bytes] = None
    _hash:          Optional[str]  = None

    def __post_init__(self):
        if not self._hash:
            self._hash = hashlib.md5(str(self.key).encode()).hexdigest()[:16]

    def access(self):
        self.access_count += 1
        now = time.time()
        if now - self.last_access < 1.0:
            self.access_pattern = AccessPattern.TEMPORAL
        self.last_access = now

    def compress(self) -> int:
        """Compress in place. Returns bytes saved (0 if already compressed)."""
        if not self.compressed and self.data is not None:
            try:
                serialized = pickle.dumps(self.data)
                self._compressed_data = zlib.compress(serialized, level=5)  # HX_ZLEVEL=5 — mirrors dm_helix.c constant
                saved = self.size_bytes - len(self._compressed_data)
                self.compressed = True
                return max(0, saved)
            except Exception:
                return 0
        return 0

    def decompress(self):
        """Decompress in place."""
        if self.compressed and self._compressed_data:
            try:
                serialized = zlib.decompress(self._compressed_data)
                self.data = pickle.loads(serialized)
                self.compressed = False
                self._compressed_data = None
            except Exception:
                pass


# ---------------------------------------------------------------------------
# HelixCache -- Multi-level LRU cache
# ---------------------------------------------------------------------------

class HelixCache:
    """
    Three-tier LRU cache with automatic promotion, compression, and disk paging.

    L1 (hot)        -- most recently/frequently accessed blocks
    L2 (warm)       -- blocks demoted from L1; promoted back on repeated access
    L3 (compressed) -- blocks demoted from L2; compressed at rest
    L5 (disk)       -- blocks evicted from L3; serialized to page_dir on disk

    Eviction policy: LRU within each tier. Pinned blocks are skipped.
    Promotion thresholds: L3->L2 after 2 accesses; L2->L1 after 3 accesses.

    page_dir: directory for L5 disk pages. None disables disk paging (evictions
    are dropped). Each page is written as <page_dir>/<hash>.page — compressed
    pickle, same format as L3 in-memory blocks.
    """

    def __init__(self,
                 l1_size_mb: int = 128,
                 l2_size_mb: int = 512,
                 l3_size_mb: int = 1024,
                 page_dir: Optional[str] = None,
                 dandelion: Optional["DandelionController"] = None):

        self.l1_max = l1_size_mb * 1024 * 1024
        self.l2_max = l2_size_mb * 1024 * 1024
        self.l3_max = l3_size_mb * 1024 * 1024

        self.l1_cache: OrderedDict[str, CacheBlock] = OrderedDict()
        self.l2_cache: OrderedDict[str, CacheBlock] = OrderedDict()
        self.l3_cache: OrderedDict[str, CacheBlock] = OrderedDict()

        # key -> filename stem for blocks paged out to disk
        self._disk_index: Dict[str, str] = {}

        self.page_dir: Optional[str] = page_dir
        if page_dir:
            os.makedirs(page_dir, exist_ok=True)

        # Dandelion thermal controller — None until wired by HelixSystem
        self._dandelion: Optional[DandelionController] = dandelion

        self.stats = {
            'l1_hits': 0, 'l1_misses': 0,
            'l2_hits': 0, 'l2_misses': 0,
            'l3_hits': 0, 'l3_misses': 0,
            'disk_hits': 0, 'disk_misses': 0,
            'promotions': 0, 'demotions': 0,
            'evictions': 0, 'compressions': 0,
            'pages_written': 0, 'pages_read': 0,
            'disk_bytes_written': 0,
        }

        self.lock = threading.RLock()

    # --- public API ---

    def get(self, key: str) -> Optional[Any]:
        with self.lock:
            # Dandelion thermal accounting
            if self._dandelion:
                self._dandelion.touch(key)
                _hot = self._dandelion.is_hot(key)
            else:
                _hot = False

            if key in self.l1_cache:
                self.stats['l1_hits'] += 1
                block = self.l1_cache[key]
                block.access()
                self.l1_cache.move_to_end(key)
                return block.data

            self.stats['l1_misses'] += 1

            if key in self.l2_cache:
                self.stats['l2_hits'] += 1
                block = self.l2_cache[key]
                block.access()
                # Thermal promote: hot lane skips access_count threshold
                if _hot or block.access_count > 3:
                    self._promote_to_l1(key, block)
                else:
                    self.l2_cache.move_to_end(key)
                return block.data

            self.stats['l2_misses'] += 1

            if key in self.l3_cache:
                self.stats['l3_hits'] += 1
                block = self.l3_cache[key]
                block.access()
                if block.compressed:
                    block.decompress()
                # Thermal promote: hot lane skips access_count threshold
                if _hot or block.access_count > 2:
                    self._promote_to_l2(key, block)
                else:
                    self.l3_cache.move_to_end(key)
                return block.data

            self.stats['l3_misses'] += 1

            # L5: check disk
            if key in self._disk_index:
                self.stats['disk_hits'] += 1
                data = self._read_from_disk(key)
                if data is not None:
                    self.stats['pages_read'] += 1
                    # promote back to L3
                    size = len(pickle.dumps(data))
                    self._make_room_l3(size)
                    block = CacheBlock(
                        key=key, data=data,
                        tier=MemoryTier.L3_COMPRESSED,
                        size_bytes=size,
                    )
                    self.l3_cache[key] = block
                    del self._disk_index[key]
                    # remove page file
                    page_path = self._page_path(key)
                    if page_path and os.path.exists(page_path):
                        try: os.unlink(page_path)
                        except Exception: pass
                    return data
            self.stats['disk_misses'] += 1
            return None

    def put(self, key: str, data: Any, size: int, pinned: bool = False):
        with self.lock:
            if self._dandelion:
                self._dandelion.touch(key)
            self.l2_cache.pop(key, None)
            self.l3_cache.pop(key, None)
            block = CacheBlock(
                key=key, data=data,
                tier=MemoryTier.L1_HOT,
                size_bytes=size, pinned=pinned,
            )
            self._make_room_l1(size)
            self.l1_cache[key] = block

    def drop(self, key: str) -> bool:
        """Remove `key` from every tier, including its L5 disk page. Used when
        the underlying data changes (write-through invalidation)."""
        with self.lock:
            found = False
            for tier in (self.l1_cache, self.l2_cache, self.l3_cache):
                if tier.pop(key, None) is not None:
                    found = True
            if key in self._disk_index:
                path = self._page_path(key)
                del self._disk_index[key]
                if path and os.path.exists(path):
                    try: os.unlink(path)
                    except Exception: pass
                found = True
            return found

    # --- internal helpers ---

    def _get_tier_size(self, tier_dict: OrderedDict) -> int:
        total = 0
        for block in tier_dict.values():
            if block.compressed and block._compressed_data:
                total += len(block._compressed_data)
            else:
                total += block.size_bytes
        return total

    def _make_room_l1(self, needed: int):
        # Under high thermal pressure compress L2 threshold: drop L1 30% earlier
        pressure = self._dandelion.lane_pressure() if self._dandelion else 0.0
        effective_max = int(self.l1_max * (1.0 - 0.3 * pressure))
        current = self._get_tier_size(self.l1_cache)
        while current + needed > effective_max and self.l1_cache:
            key, block = next(iter(self.l1_cache.items()))
            if block.pinned:
                self.l1_cache.move_to_end(key)
                continue
            self._demote_to_l2(key, block)
            current = self._get_tier_size(self.l1_cache)

    def _make_room_l2(self, needed: int):
        # Under high thermal pressure compress L3 threshold: drop L2 30% earlier
        pressure = self._dandelion.lane_pressure() if self._dandelion else 0.0
        effective_max = int(self.l2_max * (1.0 - 0.3 * pressure))
        current = self._get_tier_size(self.l2_cache)
        while current + needed > effective_max and self.l2_cache:
            key, block = next(iter(self.l2_cache.items()))
            if block.pinned:
                self.l2_cache.move_to_end(key)
                continue
            self._demote_to_l3(key, block)
            current = self._get_tier_size(self.l2_cache)

    def _make_room_l3(self, needed: int):
        current = self._get_tier_size(self.l3_cache)
        while current + needed > self.l3_max and self.l3_cache:
            key, block = next(iter(self.l3_cache.items()))
            if block.pinned:
                self.l3_cache.move_to_end(key)
                continue
            del self.l3_cache[key]
            self.stats['evictions'] += 1
            self._demote_to_disk(key, block)
            current = self._get_tier_size(self.l3_cache)

    def _promote_to_l1(self, key: str, block: CacheBlock):
        self.l2_cache.pop(key, None)
        self._make_room_l1(block.size_bytes)
        block.tier = MemoryTier.L1_HOT
        self.l1_cache[key] = block
        self.stats['promotions'] += 1

    def _promote_to_l2(self, key: str, block: CacheBlock):
        self.l3_cache.pop(key, None)
        self._make_room_l2(block.size_bytes)
        block.tier = MemoryTier.L2_WARM
        self.l2_cache[key] = block
        self.stats['promotions'] += 1

    def _demote_to_l2(self, key: str, block: CacheBlock):
        self.l1_cache.pop(key, None)
        self._make_room_l2(block.size_bytes)
        block.tier = MemoryTier.L2_WARM
        self.l2_cache[key] = block
        self.stats['demotions'] += 1

    def _demote_to_l3(self, key: str, block: CacheBlock):
        self.l2_cache.pop(key, None)
        saved = block.compress()
        if saved > 0:
            self.stats['compressions'] += 1
        size = len(block._compressed_data) if block._compressed_data else block.size_bytes
        self._make_room_l3(size)
        block.tier = MemoryTier.L3_COMPRESSED
        self.l3_cache[key] = block
        self.stats['demotions'] += 1

    def _page_path(self, key: str) -> Optional[str]:
        if not self.page_dir:
            return None
        stem = self._disk_index.get(key) or hashlib.md5(key.encode()).hexdigest()
        return os.path.join(self.page_dir, f"{stem}.page")

    def _demote_to_disk(self, key: str, block: CacheBlock):
        """Serialize evicted L3 block to disk. No-op if page_dir is unset."""
        if not self.page_dir:
            return
        try:
            # ensure compressed
            if not block.compressed:
                block.compress()
            payload = block._compressed_data or pickle.dumps(block.data)
            stem = hashlib.md5(key.encode()).hexdigest()
            path = os.path.join(self.page_dir, f"{stem}.page")
            # header: 8-byte size + key length (4 bytes) + key bytes
            key_bytes = key.encode('utf-8')
            header = struct.pack('>QI', len(payload), len(key_bytes)) + key_bytes
            with open(path, 'wb') as f:
                f.write(header)
                f.write(payload)
            self._disk_index[key] = stem
            self.stats['pages_written'] += 1
            self.stats['disk_bytes_written'] += len(payload)
        except Exception:
            pass  # disk write failure is non-fatal; block is simply dropped

    def _read_from_disk(self, key: str) -> Optional[Any]:
        """Read and deserialize a paged-out block. Returns None on any error."""
        path = self._page_path(key)
        if not path or not os.path.exists(path):
            return None
        try:
            with open(path, 'rb') as f:
                size_bytes, key_len = struct.unpack('>QI', f.read(12))
                f.read(key_len)          # skip stored key
                payload = f.read(size_bytes)
            # payload is zlib-compressed pickle
            return pickle.loads(zlib.decompress(payload))
        except Exception:
            return None

    def disk_pages_count(self) -> int:
        return len(self._disk_index)

    def disk_bytes_used(self) -> int:
        """Approximate disk usage of paged blocks."""
        return self.stats['disk_bytes_written']


# ---------------------------------------------------------------------------
# HelixMemoryManager -- Virtual RAM allocator
# ---------------------------------------------------------------------------

class HelixMemoryManager:
    """
    Key-addressed virtual memory allocator backed by HelixCache.

    malloc(key, data)  -- allocate and store
    free(key)          -- release allocation
    read(key)          -- retrieve (cache-aware)
    write(key, data)   -- overwrite existing allocation
    """

    def __init__(self, cache: HelixCache, max_virtual_mb: int = 8192):
        self.cache = cache
        self.max_virtual = max_virtual_mb * 1024 * 1024
        self.allocations: Dict[str, int] = {}
        self.total_allocated = 0
        self.stats = {
            'total_allocations': 0,
            'total_deallocations': 0,
            'virtual_memory_used': 0,
        }
        self.lock = threading.RLock()

    def malloc(self, key: str, data: Any) -> bool:
        with self.lock:
            try:
                size = len(pickle.dumps(data))
            except Exception:
                size = 1024
            if self.total_allocated + size > self.max_virtual:
                return False
            self.cache.put(key, data, size)
            self.allocations[key] = size
            self.total_allocated += size
            self.stats['total_allocations'] += 1
            self.stats['virtual_memory_used'] = self.total_allocated
            return True

    def free(self, key: str) -> bool:
        with self.lock:
            if key not in self.allocations:
                return False
            size = self.allocations.pop(key)
            self.total_allocated -= size
            self.cache.l1_cache.pop(key, None)
            self.cache.l2_cache.pop(key, None)
            self.cache.l3_cache.pop(key, None)
            self.stats['total_deallocations'] += 1
            self.stats['virtual_memory_used'] = self.total_allocated
            return True

    def read(self, key: str) -> Optional[Any]:
        return self.cache.get(key)

    def write(self, key: str, data: Any) -> bool:
        with self.lock:
            if key in self.allocations:
                self.free(key)
            return self.malloc(key, data)


# ---------------------------------------------------------------------------
# HelixFS -- Filesystem cache layer
# ---------------------------------------------------------------------------

class HelixFS:
    """
    Transparent read/write cache for filesystem paths.

    read_file(path)             -- read through cache; populates on miss
    write_file(path, data)      -- write to cache; write-through to disk by default
    invalidate(path)            -- evict path from cache

    Stale-cache detection: mtime is stored at cache time. Callers that need
    strict freshness should call invalidate() before read_file() if the file
    may have changed outside this process.
    """

    def __init__(self, memory_manager: HelixMemoryManager):
        self.memory = memory_manager
        self.file_cache:    Dict[str, str]  = {}   # filepath -> cache_key
        self.file_metadata: Dict[str, Dict] = {}   # filepath -> {size, mtime, cached_at}
        self.stats = {
            'file_reads': 0, 'file_writes': 0,
            'cache_hits': 0, 'cache_misses': 0,
            'disk_reads': 0, 'disk_writes': 0,
        }
        self.lock = threading.RLock()

    def read_file(self, filepath: str) -> Optional[bytes]:
        with self.lock:
            self.stats['file_reads'] += 1
            cache_key = f"file:{filepath}"
            cached = self.memory.read(cache_key)
            if cached is not None:
                self.stats['cache_hits'] += 1
                return cached
            self.stats['cache_misses'] += 1
            if not os.path.exists(filepath):
                return None
            try:
                with open(filepath, 'rb') as f:
                    data = f.read()
                self.stats['disk_reads'] += 1
                self.memory.malloc(cache_key, data)
                self.file_cache[filepath] = cache_key
                self.file_metadata[filepath] = {
                    'size': len(data),
                    'mtime': os.path.getmtime(filepath),
                    'cached_at': time.time(),
                }
                return data
            except Exception:
                return None

    def write_file(self, filepath: str, data: bytes, write_through: bool = True):
        with self.lock:
            self.stats['file_writes'] += 1
            cache_key = f"file:{filepath}"
            self.memory.write(cache_key, data)
            self.file_cache[filepath] = cache_key
            if write_through:
                try:
                    os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)
                    with open(filepath, 'wb') as f:
                        f.write(data)
                    self.stats['disk_writes'] += 1
                except Exception:
                    pass
            self.file_metadata[filepath] = {
                'size': len(data),
                'mtime': time.time(),
                'cached_at': time.time(),
            }

    def invalidate(self, filepath: str):
        with self.lock:
            if filepath in self.file_cache:
                self.memory.free(self.file_cache.pop(filepath))
                self.file_metadata.pop(filepath, None)


# ---------------------------------------------------------------------------
# HelixHostProfile -- OS / hardware detection and auto-configuration
# ---------------------------------------------------------------------------

class HelixHostProfile:
    """
    Detects the current OS, CPU architecture, and physical RAM, then derives
    appropriate Helix cache/RAM/page-dir defaults for this specific machine.

    No external dependencies — stdlib only (ctypes on Windows, /proc/meminfo
    on Linux/Android, sysctl on macOS). Falls back gracefully on any error.

    Supported platforms:
        win32   — Windows x86_64 / ARM64
        linux   — Debian, Ubuntu, Arch, Termux/Android, Raspberry Pi OS, etc.
        darwin  — macOS (Apple Silicon + Intel)
        cygwin  — treated as Linux for path/memory purposes

    Usage:
        profile = HelixHostProfile()
        config  = profile.config()   # dict fed into HelixSystem.__init__
        info    = profile.info()     # full fingerprint for mesh / get_stats()

    _get_helix() calls this when env vars (HELIX_L1_MB etc.) are not set.
    Env vars always override the profile — explicit config beats auto-detect.
    """

    # RAM tier bands: (min_ram_gb, l1_mb, l2_mb, l3_mb, vram_mb)
    # Covers phones/SBCs (< 2 GB) through workstations (32 GB+)
    _TIER_BANDS = [
        ( 0,   32,   128,   256,   512),   # < 2 GB  — phone / Pi Zero / very old HW
        ( 2,   64,   256,   512,  1024),   # 2–4 GB  — Pi 4 / older laptops
        ( 4,  128,   512,  1024,  2048),   # 4–8 GB  — typical dev laptop
        ( 8,  256,  1024,  2048,  4096),   # 8–16 GB — modern workstation
        (16,  512,  2048,  4096,  8192),   # 16–32 GB
        (32, 1024,  4096,  8192, 16384),   # 32 GB+  — high-end node
    ]

    def __init__(self):
        self._os      = sys.platform          # 'linux', 'win32', 'darwin', 'cygwin'
        self._arch    = _platform.machine()   # 'x86_64', 'AMD64', 'aarch64', 'armv7l'
        self._node    = _platform.node()      # hostname
        self._ram_gb  = self._detect_ram_gb()
        self._page_dir = self._default_page_dir()

    # ── public API ──────────────────────────────────────────────────────────

    def config(self) -> dict:
        """Return HelixSystem __init__ kwargs scaled to this machine's RAM."""
        l1, l2, l3, vram = self._scale_to_ram()
        return {
            "l1_cache_mb":    l1,
            "l2_cache_mb":    l2,
            "l3_cache_mb":    l3,
            "virtual_ram_mb": vram,
            "page_dir":       self._page_dir,
        }

    def info(self) -> dict:
        """Full host fingerprint — stored on the singleton for get_stats()."""
        l1, l2, l3, vram = self._scale_to_ram()
        return {
            "os":             self._os,
            "arch":           self._arch,
            "hostname":       self._node,
            "ram_gb":         round(self._ram_gb, 1),
            "page_dir":       self._page_dir,
            "helix_l1_mb":    l1,
            "helix_l2_mb":    l2,
            "helix_l3_mb":    l3,
            "helix_vram_mb":  vram,
        }

    # ── RAM detection ────────────────────────────────────────────────────────

    def _detect_ram_gb(self) -> float:
        """Total physical RAM in GB. Returns 2.0 on any failure."""
        try:
            if self._os == "win32":
                return self._ram_windows()
            elif self._os == "darwin":
                return self._ram_macos()
            else:
                # Linux, Android/Termux, Cygwin — all have /proc/meminfo
                return self._ram_proc_meminfo()
        except Exception:
            return 2.0

    def _ram_windows(self) -> float:
        import ctypes
        class _MEMSTATEX(ctypes.Structure):
            _fields_ = [
                ("dwLength",                ctypes.c_ulong),
                ("dwMemoryLoad",            ctypes.c_ulong),
                ("ullTotalPhys",            ctypes.c_ulonglong),
                ("ullAvailPhys",            ctypes.c_ulonglong),
                ("ullTotalPageFile",        ctypes.c_ulonglong),
                ("ullAvailPageFile",        ctypes.c_ulonglong),
                ("ullTotalVirtual",         ctypes.c_ulonglong),
                ("ullAvailVirtual",         ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]
        stat = _MEMSTATEX()
        stat.dwLength = ctypes.sizeof(_MEMSTATEX)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
        return stat.ullTotalPhys / (1024 ** 3)

    def _ram_macos(self) -> float:
        import subprocess
        out = subprocess.check_output(
            ["sysctl", "-n", "hw.memsize"], text=True, timeout=3
        ).strip()
        return int(out) / (1024 ** 3)

    def _ram_proc_meminfo(self) -> float:
        """Works on Linux, Android/Termux, any /proc/meminfo OS."""
        with open("/proc/meminfo", "r") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    kb = int(line.split()[1])
                    return kb / (1024 ** 2)
        raise RuntimeError("MemTotal not in /proc/meminfo")

    # ── tier scaling ─────────────────────────────────────────────────────────

    def _scale_to_ram(self):
        """Return (l1_mb, l2_mb, l3_mb, vram_mb) for this machine's RAM."""
        best = self._TIER_BANDS[0][1:]
        for min_gb, l1, l2, l3, vram in self._TIER_BANDS:
            if self._ram_gb >= min_gb:
                best = (l1, l2, l3, vram)
        return best

    # ── page_dir defaults ────────────────────────────────────────────────────

    def _default_page_dir(self) -> str:
        """Platform-appropriate default directory for L5 disk pages."""
        if self._os == "win32":
            # %LOCALAPPDATA%\Phoenix\helix\pages  (e.g. C:\Users\JW\AppData\Local\...)
            base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
            return os.path.join(base, "Phoenix", "helix", "pages")
        else:
            # Linux / macOS / Android/Termux / Cygwin
            # Respect XDG_DATA_HOME; fall back to ~/.local/share
            xdg = os.environ.get("XDG_DATA_HOME") or os.path.join(
                os.path.expanduser("~"), ".local", "share"
            )
            return os.path.join(xdg, "phoenix", "helix", "pages")


# ---------------------------------------------------------------------------
# HelixSystem -- Unified entry point
# ---------------------------------------------------------------------------

class HelixSystem:
    """
    Wires HelixCache + HelixMemoryManager + HelixFS into a single object.

    Typical usage:
        helix = HelixSystem(l1_cache_mb=256, l2_cache_mb=1024,
                            l3_cache_mb=3072, virtual_ram_mb=8192,
                            page_dir='/var/lib/helix/pages')
        helix.memory.malloc('key', payload)
        data = helix.memory.read('key')
        helix.fs.write_file('/path/to/file', content)

    page_dir: path where L5 disk pages are written when L3 is full.
              Set via PHOENIX_HELIX_PAGE_DIR env var, or pass directly.
              Omit to disable disk paging (evictions are dropped).
    """

    def __init__(self,
                 l1_cache_mb: int = 128,
                 l2_cache_mb: int = 512,
                 l3_cache_mb: int = 1024,
                 virtual_ram_mb: int = 4096,
                 page_dir: Optional[str] = None):
        _page_dir = page_dir or os.environ.get('PHOENIX_HELIX_PAGE_DIR')
        self.dandelion = DandelionController()
        self.cache  = HelixCache(l1_cache_mb, l2_cache_mb, l3_cache_mb,
                                 page_dir=_page_dir, dandelion=self.dandelion)
        self.memory = HelixMemoryManager(self.cache, virtual_ram_mb)
        self.fs     = HelixFS(self.memory)
        self.start_time = time.time()

    def get_tier_snapshot(self) -> Dict:
        """
        Returns real tier pressure data for the paging manager.

        This is the live feed that replaces the hardcoded /proc/meminfo
        ratio guessing in paging.py's _get_vrram_snapshot(). Wire it in:

            snap = helix.get_tier_snapshot()
            engine.record(TierSnapshot(**snap), swap_pct, ram_pct)

        Keys match paging.py's TierSnapshot fields exactly.
        """
        l1 = self.cache._get_tier_size(self.cache.l1_cache)
        l2 = self.cache._get_tier_size(self.cache.l2_cache)
        l3 = self.cache._get_tier_size(self.cache.l3_cache)
        disk_bytes = self.cache.disk_bytes_used()

        ops  = sum(self.cache.stats[k] for k in
                   ('l1_hits','l1_misses','l2_hits','l2_misses',
                    'l3_hits','l3_misses','disk_hits','disk_misses'))
        hits = (self.cache.stats['l1_hits'] + self.cache.stats['l2_hits'] +
                self.cache.stats['l3_hits'] + self.cache.stats['disk_hits'])

        return {
            'timestamp':  time.time(),
            'hot_mb':     l1 / (1024**2),
            'warm_mb':    l2 / (1024**2),
            'cold_mb':    l3 / (1024**2),
            'frozen_mb':  disk_bytes / (1024**2),   # paged to disk = frozen
            'hit_rate':   (hits / ops * 100) if ops else 0.0,
            'promotions': self.cache.stats['promotions'],
            'demotions':  self.cache.stats['demotions'],
            'evictions':  self.cache.stats['evictions'],
            'pages_on_disk':      self.cache.disk_pages_count(),
            'disk_bytes_written': disk_bytes,
            'dandelion':          self.dandelion.snapshot(),
        }

    def get_stats(self) -> Dict:
        uptime = time.time() - self.start_time
        l1 = self.cache._get_tier_size(self.cache.l1_cache)
        l2 = self.cache._get_tier_size(self.cache.l2_cache)
        l3 = self.cache._get_tier_size(self.cache.l3_cache)
        disk_bytes = self.cache.disk_bytes_used()
        ops = sum(self.cache.stats[k] for k in
                  ('l1_hits','l1_misses','l2_hits','l2_misses',
                   'l3_hits','l3_misses','disk_hits','disk_misses'))
        hits = (self.cache.stats['l1_hits'] + self.cache.stats['l2_hits'] +
                self.cache.stats['l3_hits'] + self.cache.stats['disk_hits'])
        return {
            'uptime': uptime,
            'cache': {
                'l1_size_mb':    l1 / (1024**2),
                'l2_size_mb':    l2 / (1024**2),
                'l3_size_mb':    l3 / (1024**2),
                'l5_disk_mb':    disk_bytes / (1024**2),
                'total_size_mb': (l1+l2+l3) / (1024**2),
                'hit_rate':      (hits / ops * 100) if ops else 0,
                'l1_items':      len(self.cache.l1_cache),
                'l2_items':      len(self.cache.l2_cache),
                'l3_items':      len(self.cache.l3_cache),
                'l5_pages':      self.cache.disk_pages_count(),
                **self.cache.stats,
            },
            'memory': {
                'allocated_mb':     self.memory.total_allocated / (1024**2),
                'allocation_count': len(self.memory.allocations),
                **self.memory.stats,
            },
            'filesystem': {
                'cached_files': len(self.fs.file_cache),
                **self.fs.stats,
            },
        }

    def print_stats(self):
        s = self.get_stats()
        print()
        print("=" * 60)
        print("HELIX SYSTEM STATISTICS")
        print("=" * 60)
        print(f"Uptime:          {s['uptime']:.3f}s")
        print()
        print("CACHE")
        print(f"  L1 (hot):        {s['cache']['l1_size_mb']:8.3f} MB  ({s['cache']['l1_items']:,} items)")
        print(f"  L2 (warm):       {s['cache']['l2_size_mb']:8.3f} MB  ({s['cache']['l2_items']:,} items)")
        print(f"  L3 (compressed): {s['cache']['l3_size_mb']:8.3f} MB  ({s['cache']['l3_items']:,} items)")
        print(f"  L5 (disk):       {s['cache']['l5_disk_mb']:8.3f} MB  ({s['cache']['l5_pages']:,} pages)")
        print(f"  Total:           {s['cache']['total_size_mb']:8.3f} MB")
        print(f"  Hit rate:        {s['cache']['hit_rate']:8.1f}%")
        print(f"  L1 hits/misses:  {s['cache']['l1_hits']:,} / {s['cache']['l1_misses']:,}")
        print(f"  L2 hits/misses:  {s['cache']['l2_hits']:,} / {s['cache']['l2_misses']:,}")
        print(f"  L3 hits/misses:  {s['cache']['l3_hits']:,} / {s['cache']['l3_misses']:,}")
        print(f"  L5 hits/misses:  {s['cache']['disk_hits']:,} / {s['cache']['disk_misses']:,}")
        print(f"  Promotions:      {s['cache']['promotions']:,}")
        print(f"  Demotions:       {s['cache']['demotions']:,}")
        print(f"  Compressions:    {s['cache']['compressions']:,}")
        print(f"  Evictions:       {s['cache']['evictions']:,}")
        print(f"  Pages written:   {s['cache']['pages_written']:,}")
        print()
        print("VIRTUAL MEMORY")
        print(f"  Allocated:       {s['memory']['allocated_mb']:8.3f} MB")
        print(f"  Live allocs:     {s['memory']['allocation_count']:,}")
        print(f"  Total mallocs:   {s['memory']['total_allocations']:,}")
        print(f"  Total frees:     {s['memory']['total_deallocations']:,}")
        print()
        print("FILESYSTEM")
        print(f"  Cached files:    {s['filesystem']['cached_files']:,}")
        print(f"  Reads:           {s['filesystem']['file_reads']:,}  (hits {s['filesystem']['cache_hits']:,} / disk {s['filesystem']['disk_reads']:,})")
        print(f"  Writes:          {s['filesystem']['file_writes']:,}  (disk {s['filesystem']['disk_writes']:,})")
        print("=" * 60)


# ---------------------------------------------------------------------------
# Frank Ring entry point
# ---------------------------------------------------------------------------
#
# _run_python() in frank_ring.py loads this module and calls:
#
#     mod.run(data, ball, pcs, **kwargs)
#
# All 9 suits pointing to helix_complete_stack.py come through here.
# The suit name is recovered from ball.custody_chain and dispatched below.
# A module-level singleton HelixSystem (with Dandelion) is shared across
# all rings in the same process lifetime.

_helix_singleton: Optional[HelixSystem]          = None
_helix_lock                                       = threading.Lock()


def _get_helix() -> HelixSystem:
    """
    Return (or create) the process-wide HelixSystem + Dandelion instance.

    Auto-detects host OS / RAM via HelixHostProfile on first call.
    Env vars (HELIX_L1_MB, HELIX_L2_MB, HELIX_L3_MB, HELIX_VRAM_MB,
    PHOENIX_HELIX_PAGE_DIR) always override the auto-detected profile.
    """
    global _helix_singleton
    with _helix_lock:
        if _helix_singleton is None:
            # Detect host — scales cache tiers to actual available RAM
            _profile = HelixHostProfile()
            _cfg     = _profile.config()

            l1   = int(os.environ.get("HELIX_L1_MB")   or _cfg["l1_cache_mb"])
            l2   = int(os.environ.get("HELIX_L2_MB")   or _cfg["l2_cache_mb"])
            l3   = int(os.environ.get("HELIX_L3_MB")   or _cfg["l3_cache_mb"])
            vram = int(os.environ.get("HELIX_VRAM_MB") or _cfg["virtual_ram_mb"])
            pdir = os.environ.get("PHOENIX_HELIX_PAGE_DIR") or _cfg["page_dir"]

            _helix_singleton = HelixSystem(
                l1_cache_mb=l1, l2_cache_mb=l2, l3_cache_mb=l3,
                virtual_ram_mb=vram, page_dir=pdir,
            )
            # Attach host fingerprint so get_stats() can report it to the mesh
            _helix_singleton._host_profile = _profile.info()

            _hi = _helix_singleton._host_profile
            log.info(
                f"HelixSystem online — "
                f"host={_hi['hostname']} os={_hi['os']} arch={_hi['arch']} "
                f"ram={_hi['ram_gb']}GB "
                f"L1={l1}MB L2={l2}MB L3={l3}MB vRAM={vram}MB "
                f"pages={pdir} Dandelion lanes={HX_LANES}"
            )
        return _helix_singleton


def _suit_name_from_ball(ball) -> str:
    """
    Extract suit name from ball.custody_chain.
    mount() in frank_ring.py appends ("frank5_core", suit_name) as the
    last handoff — that is the canonical source.
    """
    try:
        chain = list(getattr(ball, "custody_chain", []))
        if chain:
            last = chain[-1]
            if isinstance(last, (list, tuple)) and len(last) >= 2:
                return str(last[1])
    except Exception:
        pass
    return "helix"


def _parse_data(data: bytes) -> dict:
    """Best-effort JSON decode of ring data payload. Returns {} on failure."""
    if not data:
        return {}
    try:
        return json.loads(data)
    except Exception:
        return {"raw": data.decode("utf-8", errors="replace")}


# ── Suit dispatchers ─────────────────────────────────────────────────────────

def _run_boot_slot(helix: HelixSystem, suit_name: str,
                   data: bytes, ball, pcs) -> dict:
    """
    frank3_slot_a (1,0) / frank3_slot_b (1,1) — Boot/Kernel sector.

    Reports helix readiness to the boot ledger. Checks that page_dir is
    accessible (or marks it absent). Returns tier snapshot so Frank5 can
    decide whether helix is healthy enough to proceed.
    """
    snap = helix.get_tier_snapshot()
    page_dir_ok = bool(helix.cache.page_dir and
                       os.path.isdir(helix.cache.page_dir))
    result = {
        "suit":        suit_name,
        "helix_ready": True,
        "page_dir_ok": page_dir_ok,
        "page_dir":    helix.cache.page_dir,
        "tier":        snap,
    }
    log.info(f"[{suit_name}] boot check — page_dir_ok={page_dir_ok}")
    return result


def _run_concierge(helix: HelixSystem, data: bytes, ball, pcs) -> dict:
    """
    concierge (1,3) — Routing concierge.

    Accepts an envelope payload from data, caches it under the PCS hash,
    and returns a routing decision (which sector/ring should handle it next).
    Falls back gracefully if PCS is not yet definitive.
    """
    payload = _parse_data(data)
    pcs_hash = getattr(pcs, "hash", None) or payload.get("pcs_hash", "")
    family   = getattr(pcs, "family", "system")

    if pcs_hash:
        cache_key = f"concierge:{pcs_hash}"
        helix.memory.malloc(cache_key, payload)

    # Route based on family
    routing = {
        "system":   {"sector": 1, "ring": 0},
        "framework":{"sector": 1, "ring": 1},
        "network":  {"sector": 3, "ring": 0},
        "storage":  {"sector": 2, "ring": 1},
        "ai":       {"sector": 4, "ring": 0},
    }
    route = routing.get(family, {"sector": 4, "ring": 0})
    result = {
        "suit":    "concierge",
        "pcs":     pcs_hash,
        "family":  family,
        "route":   route,
        "cached":  bool(pcs_hash),
    }
    log.info(f"[concierge] pcs={pcs_hash[:8] if pcs_hash else 'none'} → {route}")
    return result


def _run_clone_pool(helix: HelixSystem, data: bytes, ball, pcs) -> dict:
    """
    clone_pool (2,1) — Clonepool chunk staging.

    Receives a chunk payload for clonepool staging. Caches the chunk in
    helix L1 under the PCS hash so freewheeling can retrieve it on
    snap_clone. Returns tier placement and Dandelion heat.
    """
    payload  = _parse_data(data)
    pcs_hash = getattr(pcs, "hash", None) or payload.get("pcs_hash", "")
    chunk_id = payload.get("chunk_id", "0")

    if pcs_hash and data:
        cache_key = f"clone_pool:{pcs_hash}:{chunk_id}"
        helix.memory.malloc(cache_key, data)
        hot = helix.dandelion.is_hot(cache_key)
        tier_placed = "L1" if hot else "L2"
    else:
        hot, tier_placed = False, "none"

    result = {
        "suit":       "clone_pool",
        "pcs":        pcs_hash,
        "chunk":      chunk_id,
        "tier":       tier_placed,
        "lane_hot":   hot,
        "dandelion":  helix.dandelion.snapshot(),
    }
    log.info(f"[clone_pool] pcs={pcs_hash[:8] if pcs_hash else 'none'} chunk={chunk_id} tier={tier_placed}")
    return result


def _run_packages_worker(helix: HelixSystem, data: bytes, ball, pcs) -> dict:
    """
    packages_worker (2,3) — Package coordination.

    Looks up a package in helix cache (previously staged by clone_pool or
    the TAV intake pipeline). Returns cache status so the ClonepoolBackend
    can skip a disk read if the .deb is already hot.
    """
    payload  = _parse_data(data)
    pkg_name = payload.get("package", "")
    cache_key = f"pkg:{pkg_name}"

    cached = helix.memory.read(cache_key) is not None
    snap   = helix.get_tier_snapshot()

    result = {
        "suit":    "packages_worker",
        "package": pkg_name,
        "cached":  cached,
        "tier":    snap,
    }
    log.info(f"[packages_worker] pkg={pkg_name!r} cached={cached}")
    return result


def _run_helix_core(helix: HelixSystem, data: bytes, ball, pcs) -> dict:
    """
    helix (4,0) — Core cache service.

    Processes one data chunk: stores it in cache, returns the live tier
    snapshot. This is the main operational ring for the helix stack.
    """
    payload  = _parse_data(data)
    pcs_hash = getattr(pcs, "hash", None) or payload.get("pcs_hash", "")

    if pcs_hash and data:
        cache_key = f"helix:{pcs_hash}"
        helix.memory.malloc(cache_key, data)

    snap = helix.get_tier_snapshot()
    log.debug(f"[helix] pcs={pcs_hash[:8] if pcs_hash else 'none'} "
              f"hit_rate={snap['hit_rate']:.1f}%")
    return {"suit": "helix", "pcs": pcs_hash, "tier": snap}


def _run_freewheeling(helix: HelixSystem, data: bytes, ball, pcs) -> dict:
    """
    freewheeling (4,1) — PCS lifecycle / staged data management.

    Checks PCS state. If the PCS is definitive (p3 ≥ 0.90), retrieves
    staged chunks from helix cache and emits them for snap_clone.
    Otherwise reports current probability and returns.
    """
    pcs_hash    = getattr(pcs, "hash", "")
    probability = getattr(pcs, "probability", 0.0)
    definitive  = getattr(pcs, "definitive", False)

    staged_keys: list = []
    if definitive and pcs_hash:
        # Gather all chunks staged under this PCS
        prefix = f"clone_pool:{pcs_hash}:"
        for k in list(helix.cache.l1_cache.keys()) + list(helix.cache.l2_cache.keys()):
            if k.startswith(prefix):
                staged_keys.append(k)

    result = {
        "suit":        "freewheeling",
        "pcs":         pcs_hash,
        "probability": round(probability, 4),
        "definitive":  definitive,
        "staged_keys": staged_keys,
        "ready":       definitive and bool(staged_keys),
    }
    log.info(f"[freewheeling] pcs={pcs_hash[:8]} p={probability:.3f} "
             f"definitive={definitive} staged={len(staged_keys)}")
    return result


def _run_propcoms(helix: HelixSystem, data: bytes, ball, pcs) -> dict:
    """
    propcoms (4,2) — Property communications propagation.

    Reads a property delta from data, updates it in the helix cache,
    and returns confirmation. Properties live under 'prop:<key>' in cache.
    Stays quadralingual — no translation here, translator.sh fires at
    the sector3 boundary on OUTPUT ONLY.
    """
    payload = _parse_data(data)
    props   = payload.get("properties", {})
    updated = []

    for prop_key, prop_val in props.items():
        cache_key = f"prop:{prop_key}"
        helix.memory.write(cache_key, prop_val)
        updated.append(prop_key)

    result = {
        "suit":    "propcoms",
        "updated": updated,
        "count":   len(updated),
        "tier":    helix.get_tier_snapshot(),
    }
    log.info(f"[propcoms] updated {len(updated)} properties")
    return result


def _run_conductor(helix: HelixSystem, data: bytes, ball, pcs) -> dict:
    """
    conductor (4,3) — Sector 4 orchestrator.

    Polls the aggregate health of the sector 4 stack (helix, freewheeling,
    propcoms) via the helix cache stats and Dandelion thermal state.
    Returns a health report that Frank5 uses for scheduling decisions.
    """
    snap      = helix.get_tier_snapshot()
    dand      = helix.dandelion.snapshot()
    mem_used  = helix.memory.total_allocated
    mem_max   = helix.memory.max_virtual

    health = "green"
    if dand["pressure"] > 0.8:
        health = "yellow"
    if snap["hit_rate"] < 20.0 and snap["evictions"] > 1000:
        health = "red"

    result = {
        "suit":        "conductor",
        "health":      health,
        "hit_rate":    round(snap["hit_rate"], 2),
        "evictions":   snap["evictions"],
        "mem_pct":     round(mem_used / mem_max * 100, 1) if mem_max else 0.0,
        "dandelion":   dand,
        "tier":        snap,
    }
    log.info(f"[conductor] health={health} hit_rate={snap['hit_rate']:.1f}% "
             f"pressure={dand['pressure']:.2f}")
    return result


# ── Frank Ring run() ─────────────────────────────────────────────────────────

def run(data: bytes, ball, pcs, **kwargs) -> dict:
    """
    Frank Ring entry point — called by frank_ring._run_python() for all 9
    helix-stack suits:

        frank3_slot_a, frank3_slot_b, concierge, clone_pool, packages_worker,
        helix, freewheeling, propcoms, conductor

    Signature: run(data: bytes, ball: Ball, pcs: PCS, **kwargs) → dict

    The suit name is recovered from ball.custody_chain (last handoff from
    frank5_core). A shared HelixSystem (with Dandelion) is used across
    all ring firings in this process.
    """
    helix     = _get_helix()
    suit_name = _suit_name_from_ball(ball)

    try:
        if suit_name in ("frank3_slot_a", "frank3_slot_b"):
            return _run_boot_slot(helix, suit_name, data, ball, pcs)
        elif suit_name == "concierge":
            return _run_concierge(helix, data, ball, pcs)
        elif suit_name == "clone_pool":
            return _run_clone_pool(helix, data, ball, pcs)
        elif suit_name == "packages_worker":
            return _run_packages_worker(helix, data, ball, pcs)
        elif suit_name == "helix":
            return _run_helix_core(helix, data, ball, pcs)
        elif suit_name == "freewheeling":
            return _run_freewheeling(helix, data, ball, pcs)
        elif suit_name == "propcoms":
            return _run_propcoms(helix, data, ball, pcs)
        elif suit_name == "conductor":
            return _run_conductor(helix, data, ball, pcs)
        else:
            log.warning(f"[run] unknown suit={suit_name!r} — returning tier snapshot")
            return {"suit": suit_name, "tier": helix.get_tier_snapshot()}
    except Exception as exc:
        log.error(f"[run] suit={suit_name!r} failed: {exc}", exc_info=True)
        raise


# ---------------------------------------------------------------------------
# Benchmark -- measures real latency and throughput
# ---------------------------------------------------------------------------

def benchmark():
    """
    Allocate, read, and evict blocks across all cache tiers including disk.
    Prints actual latency (microseconds), hit rates, and disk page stats.
    """
    import tempfile, shutil
    page_dir = tempfile.mkdtemp(prefix='helix_pages_')
    print("=" * 60)
    print("HELIX BENCHMARK")
    print("=" * 60)
    print(f"  page_dir: {page_dir}")

    helix = HelixSystem(
        l1_cache_mb=16,
        l2_cache_mb=48,
        l3_cache_mb=64,
        virtual_ram_mb=2048,
        page_dir=page_dir,
    )

    BLOCK_SIZE  = 65536  # 64 KB payload per block
    WARM_COUNT  = 1000   # ~64 MB — well overflows 16+48+64 MB of RAM tiers
    COLD_COUNT  = 400    # push overflow blocks to disk (L5)
    HOT_READS   = 10     # re-reads per hot block to drive promotions

    # --- phase 1: write WARM_COUNT blocks ---
    t0 = time.perf_counter()
    for i in range(WARM_COUNT):
        helix.memory.malloc(f'b{i}', b'w' * BLOCK_SIZE)
    write_us = (time.perf_counter() - t0) / WARM_COUNT * 1e6
    print(f"\nWrite phase    {WARM_COUNT:,} blocks x {BLOCK_SIZE} B")
    print(f"  avg latency  {write_us:.1f} us/block")

    # --- phase 2: hot reads on first 100 blocks ---
    t0 = time.perf_counter()
    hits = 0
    for i in range(100):
        for _ in range(HOT_READS):
            if helix.memory.read(f'b{i}') is not None:
                hits += 1
    read_us = (time.perf_counter() - t0) / (100 * HOT_READS) * 1e6
    print(f"\nHot-read phase 100 blocks x {HOT_READS} reads")
    print(f"  avg latency  {read_us:.1f} us/read")
    print(f"  hit rate     {hits / (100 * HOT_READS) * 100:.1f}%")

    # --- phase 3: cold flood to trigger demotion and compression ---
    t0 = time.perf_counter()
    for i in range(WARM_COUNT, WARM_COUNT + COLD_COUNT):
        helix.memory.malloc(f'b{i}', b'c' * BLOCK_SIZE * 2)
    flood_us = (time.perf_counter() - t0) / COLD_COUNT * 1e6
    print(f"\nCold-flood     {COLD_COUNT:,} blocks x {BLOCK_SIZE*2} B")
    print(f"  avg latency  {flood_us:.1f} us/block")

    # --- phase 4: re-read hot blocks (should still be in L1/L2 after promotions) ---
    t0 = time.perf_counter()
    hits = 0
    for i in range(100):
        if helix.memory.read(f'b{i}') is not None:
            hits += 1
    reread_us = (time.perf_counter() - t0) / 100 * 1e6
    print(f"\nPost-flood re-read of 100 hot blocks")
    print(f"  avg latency  {reread_us:.1f} us/read")
    print(f"  hit rate     {hits / 100 * 100:.1f}%")

    # --- compression ratio ---
    l3_items = len(helix.cache.l3_cache)
    if l3_items:
        raw = sum(b.size_bytes for b in helix.cache.l3_cache.values())
        compressed = sum(
            len(b._compressed_data) if b._compressed_data else b.size_bytes
            for b in helix.cache.l3_cache.values()
        )
        ratio = raw / compressed if compressed else 1.0
        print(f"\nCompression    {l3_items:,} blocks in L3")
        print(f"  raw          {raw / 1024:.1f} KB")
        print(f"  compressed   {compressed / 1024:.1f} KB")
        print(f"  ratio        {ratio:.2f}x")

    # --- disk paging stats ---
    snap = helix.get_tier_snapshot()
    print(f"\nTier snapshot  (paging manager feed)")
    print(f"  hot_mb       {snap['hot_mb']:.3f}")
    print(f"  warm_mb      {snap['warm_mb']:.3f}")
    print(f"  cold_mb      {snap['cold_mb']:.3f}")
    print(f"  frozen_mb    {snap['frozen_mb']:.3f}  (paged to disk)")
    print(f"  pages_on_disk {snap['pages_on_disk']:,}")
    print(f"  hit_rate     {snap['hit_rate']:.1f}%")

    helix.print_stats()

    shutil.rmtree(page_dir, ignore_errors=True)


if __name__ == "__main__":
    benchmark()
