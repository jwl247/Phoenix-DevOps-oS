"""
Helix Complete Memory Stack
Virtual RAM + Cache + Filesystem Integration

Components:
  HelixCache        -- Multi-level LRU cache (L1 hot / L2 warm / L3 compressed)
  HelixMemoryManager -- Virtual RAM allocator backed by the cache tiers
  HelixFS           -- Filesystem read/write layer with cache pass-through
  HelixSystem       -- Unified entry point wiring all three together

Platform: Linux (mmap/madvise/FUSE integration targets Linux kernel interfaces)
Status:   Userspace implementation. Transparent kernel integration via FUSE or
          LD_PRELOAD is the next integration phase.

Integration paths:
  A) FUSE filesystem  -- mount point; transparent to any application
  B) LD_PRELOAD       -- intercept libc malloc/free; no kernel changes needed
  C) Kernel module    -- hook into page fault handler; highest performance
  D) Userspace (this) -- explicit API; use directly from Python applications
"""

import time
import hashlib
import pickle
import zlib
import os
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Optional, Dict
from enum import Enum
import threading
import struct


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
                self._compressed_data = zlib.compress(serialized, level=6)
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
                 page_dir: Optional[str] = None):

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
                if block.access_count > 3:
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
                if block.access_count > 2:
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
            self.l2_cache.pop(key, None)
            self.l3_cache.pop(key, None)
            block = CacheBlock(
                key=key, data=data,
                tier=MemoryTier.L1_HOT,
                size_bytes=size, pinned=pinned,
            )
            self._make_room_l1(size)
            self.l1_cache[key] = block

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
        current = self._get_tier_size(self.l1_cache)
        while current + needed > self.l1_max and self.l1_cache:
            key, block = next(iter(self.l1_cache.items()))
            if block.pinned:
                self.l1_cache.move_to_end(key)
                continue
            self._demote_to_l2(key, block)
            current = self._get_tier_size(self.l1_cache)

    def _make_room_l2(self, needed: int):
        current = self._get_tier_size(self.l2_cache)
        while current + needed > self.l2_max and self.l2_cache:
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
        self.cache  = HelixCache(l1_cache_mb, l2_cache_mb, l3_cache_mb,
                                 page_dir=_page_dir)
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
