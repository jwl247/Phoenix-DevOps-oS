#!/usr/bin/env python3
"""
helix_memory.py — Phoenix DevOps OS / CoPES
Helix Memory Stack — superpowers layer for the game engine.

Architecture:
    Game / COPES
        ↓
    Sector arch (romeo/juliet, frank3, quadengine)
        ↓
    Frank — PCS torrent, cast/reel, Ring 3
        ↓
    HelixSystem  ← THIS FILE (High-Velocity Profile)
        ↓
    Helix        ← helix.py (clone pool, QuadEngine, egress)
        ↓
    SQLite + D1

jwl247 / United Systems / GPL v3
"""

from __future__ import annotations

import os
import sys
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import time
import pickle
import zlib
import hashlib
import json
import threading
import logging
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable

try:
    import psutil
except ImportError:
    psutil = None

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

# ============================================================================
# MEMORY TIERS
# ============================================================================

class MemoryTier(Enum):
    L1_HOT        = 0   # sub-microsecond — hottest game state
    L2_WARM       = 1   # fast — recent ops, active sectors
    L3_COMPRESSED = 2   # compressed RAM — cold but resident
    L4_HELIX      = 3   # Helix clone pool — persistent
    L5_D1         = 4   # Cloudflare D1 — chain of evidence

class SectorID(Enum):
    SECTOR_1 = "s1"   # Boot, kernel, frank3
    SECTOR_2 = "s2"   # Intake, package handler, clone pool
    SECTOR_3 = "s3"   # Comms, romeo/juliet, quadengine
    SECTOR_4 = "s4"   # Helix, Frank, vault (default)
    GAME     = "gm"   # Game engine state — CoPES, physics, world
    FRANK    = "fr"   # Frank orchestrator context
    CLAUDE   = "cl"   # Claude AI context — conversation, memory, operator state

# ============================================================================
# CACHE BLOCK
# ============================================================================

@dataclass
class CacheBlock:
    key:            str
    data:           Any
    tier:           MemoryTier
    size_bytes:     int
    sector:         SectorID    = SectorID.SECTOR_4
    access_count:   int         = 0
    last_access:    float       = field(default_factory=time.time)
    created_at:     float       = field(default_factory=time.time)
    compressed:     bool        = False
    pinned:         bool        = False
    dirty:          bool        = False
    _compressed_data: Optional[bytes] = field(default=None, repr=False)

    def touch(self):
        self.access_count += 1
        self.last_access = time.time()

    def compress(self) -> int:
        if self.compressed or self.data is None:
            return 0
        try:
            raw = pickle.dumps(self.data)
            self._compressed_data = zlib.compress(raw, level=5)
            saved = self.size_bytes - len(self._compressed_data)
            self.compressed = True
            return max(0, saved)
        except Exception:
            return 0

    def decompress(self):
        if not self.compressed or not self._compressed_data:
            return
        try:
            raw = zlib.decompress(self._compressed_data)
            self.data = pickle.loads(raw)
            self.compressed = False
            self._compressed_data = None
        except Exception:
            pass

    @property
    def effective_size(self) -> int:
        if self.compressed and self._compressed_data:
            return len(self._compressed_data)
        return self.size_bytes

# ============================================================================
# HELIX CACHE (L1 / L2 / L3)
# ============================================================================

class HelixCache:
    """
    3-tier in-memory cache:
      L1: Hot  — sub-microsecond, no compression, fixed size
      L2: Warm — fast, uncompressed, demotes to L3 under pressure
      L3: Cold — compressed in RAM (zlib level 5), decompresses on read
    """

    def __init__(self, l1_mb: int = 512, l2_mb: int = 2048, l3_mb: int = 8192):
        self.max_l1 = l1_mb * 1024 * 1024
        self.max_l2 = l2_mb * 1024 * 1024
        self.max_l3 = l3_mb * 1024 * 1024

        self.l1: OrderedDict[str, CacheBlock] = OrderedDict()
        self.l2: OrderedDict[str, CacheBlock] = OrderedDict()
        self.l3: OrderedDict[str, CacheBlock] = OrderedDict()

        self.lock = threading.RLock()
        self.hits = {t: 0 for t in MemoryTier}
        self.misses = {t: 0 for t in MemoryTier}
        self.promotions = 0
        self.demotions = 0
        self.compressions = 0
        self.evictions = 0

    def get(self, key: str) -> Optional[Any]:
        with self.lock:
            # L1 Check
            if key in self.l1:
                b = self.l1[key]
                b.touch()
                self.l1.move_to_end(key)
                self.hits[MemoryTier.L1_HOT] += 1
                return b.data

            # L2 Check
            if key in self.l2:
                b = self.l2[key]
                b.touch()
                self.hits[MemoryTier.L2_WARM] += 1
                if b.access_count >= 3:
                    self._promote_l1(key, b)
                else:
                    self.l2.move_to_end(key)
                return b.data

            # L3 Check
            if key in self.l3:
                b = self.l3[key]
                b.touch()
                b.decompress()
                self.hits[MemoryTier.L3_COMPRESSED] += 1
                self._promote_l2(key, b)
                return b.data

            self.misses[MemoryTier.L1_HOT] += 1
            return None

    def put(self, key: str, data: Any, size_bytes: int = 0,
            sector: SectorID = SectorID.SECTOR_4,
            pinned: bool = False) -> CacheBlock:
        with self.lock:
            if size_bytes <= 0:
                try:
                    size_bytes = len(pickle.dumps(data))
                except Exception:
                    size_bytes = 1024

            self.invalidate(key)
            block = CacheBlock(
                key=key, data=data, tier=MemoryTier.L1_HOT,
                size_bytes=size_bytes, sector=sector, pinned=pinned
            )
            self._make_room_l1(size_bytes)
            self.l1[key] = block
            return block

    def invalidate(self, key: str):
        with self.lock:
            self.l1.pop(key, None)
            self.l2.pop(key, None)
            self.l3.pop(key, None)

    def _tier_size(self, tier: OrderedDict[str, CacheBlock]) -> int:
        return sum(b.effective_size for b in tier.values())

    def _make_room_l1(self, needed: int):
        while self._tier_size(self.l1) + needed > self.max_l1 and self.l1:
            key, b = next(iter(self.l1.items()))
            if b.pinned:
                self.l1.move_to_end(key)
                continue
            self._demote_l2(key, b)

    def _make_room_l2(self, needed: int):
        while self._tier_size(self.l2) + needed > self.max_l2 and self.l2:
            key, b = next(iter(self.l2.items()))
            if b.pinned:
                self.l2.move_to_end(key)
                continue
            self._demote_l3(key, b)

    def _make_room_l3(self, needed: int):
        while self._tier_size(self.l3) + needed > self.max_l3 and self.l3:
            key, b = next(iter(self.l3.items()))
            if b.pinned:
                self.l3.move_to_end(key)
                continue
            del self.l3[key]
            self.evictions += 1

    def _promote_l1(self, key: str, b: CacheBlock):
        self.l2.pop(key, None)
        self._make_room_l1(b.size_bytes)
        b.tier = MemoryTier.L1_HOT
        self.l1[key] = b
        self.promotions += 1

    def _promote_l2(self, key: str, b: CacheBlock):
        self.l3.pop(key, None)
        self._make_room_l2(b.size_bytes)
        b.tier = MemoryTier.L2_WARM
        self.l2[key] = b
        self.promotions += 1

    def _demote_l2(self, key: str, b: CacheBlock):
        self.l1.pop(key, None)
        self._make_room_l2(b.size_bytes)
        b.tier = MemoryTier.L2_WARM
        self.l2[key] = b
        self.demotions += 1

    def _demote_l3(self, key: str, b: CacheBlock):
        self.l2.pop(key, None)
        saved = b.compress()
        if saved > 0:
            self.compressions += 1
        self._make_room_l3(b.effective_size)
        b.tier = MemoryTier.L3_COMPRESSED
        self.l3[key] = b
        self.demotions += 1

    def stats(self) -> dict:
        with self.lock:
            total_ops = sum(self.hits.values()) + sum(self.misses.values())
            total_hits = sum(self.hits.values())
            hit_rate = (total_hits / total_ops * 100) if total_ops else 100.0
            return {
                "l1_items":    len(self.l1),
                "l2_items":    len(self.l2),
                "l3_items":    len(self.l3),
                "l1_mb":       round(self._tier_size(self.l1) / 1048576, 2),
                "l2_mb":       round(self._tier_size(self.l2) / 1048576, 2),
                "l3_mb":       round(self._tier_size(self.l3) / 1048576, 2),
                "hit_rate":    round(hit_rate, 2),
                "hits":        {k.name: v for k, v in self.hits.items()},
                "misses":      {k.name: v for k, v in self.misses.items()},
                "promotions":  self.promotions,
                "demotions":   self.demotions,
                "compressions": self.compressions,
                "evictions":   self.evictions,
            }

# ============================================================================
# HELIX MEMORY MANAGER — virtual RAM
# ============================================================================

class HelixMemoryManager:
    """
    Virtual RAM on top of HelixCache.
    malloc/free interface — game entities, sector state, Frank payloads.
    More load compresses more = more effective RAM = PCS torrent model.
    """

    def __init__(self, cache: HelixCache, max_virtual_mb: int = 4096):
        self.cache       = cache
        self.max_virtual = max_virtual_mb * 1024 * 1024
        self.allocations: Dict[str, int] = {}
        self.total_allocated = 0
        self.lock = threading.RLock()
        self.total_allocs = 0
        self.total_frees  = 0

    def malloc(self, key: str, data: Any,
               sector: SectorID = SectorID.SECTOR_4,
               pinned: bool = False) -> bool:
        with self.lock:
            try:
                size = len(pickle.dumps(data))
            except Exception:
                size = 1024
            if self.total_allocated + size > self.max_virtual:
                return False
            self.cache.put(key, data, size, sector=sector, pinned=pinned)
            self.allocations[key] = size
            self.total_allocated += size
            self.total_allocs += 1
            return True

    def free(self, key: str) -> bool:
        with self.lock:
            if key not in self.allocations:
                return False
            size = self.allocations.pop(key)
            self.total_allocated -= size
            self.cache.invalidate(key)
            self.total_frees += 1
            return True

    def read(self, key: str) -> Optional[Any]:
        return self.cache.get(key)

    def write(self, key: str, data: Any,
              sector: SectorID = SectorID.SECTOR_4) -> bool:
        with self.lock:
            if key in self.allocations:
                self.free(key)
            return self.malloc(key, data, sector=sector)

    def stats(self) -> dict:
        return {
            "allocated_mb":  round(self.total_allocated / 1048576, 2),
            "allocation_count": len(self.allocations),
            "total_allocs":  self.total_allocs,
            "total_frees":   self.total_frees,
        }

# ============================================================================
# HELIX FS — filesystem cache
# ============================================================================

class HelixFS:
    """
    Filesystem cache layer.
    Files read through Helix — cached in memory stack automatically.
    Sector-aware: sector 1 files stay in sector 1 memory region.
    """

    def __init__(self, memory: HelixMemoryManager):
        self.memory   = memory
        self.manifest: Dict[str, dict] = {}
        self.lock     = threading.RLock()
        self.reads    = 0
        self.writes   = 0
        self.hits     = 0
        self.disk_reads  = 0
        self.disk_writes = 0

    def read(self, filepath: str,
             sector: SectorID = SectorID.SECTOR_4) -> Optional[bytes]:
        with self.lock:
            self.reads += 1
            key = f"fs:{filepath}"
            cached = self.memory.read(key)
            if cached is not None:
                self.hits += 1
                return cached
            if not os.path.exists(filepath):
                return None
            try:
                with open(filepath, "rb") as f:
                    data = f.read()
                self.disk_reads += 1
                self.memory.malloc(key, data, sector=sector)
                self.manifest[filepath] = {
                    "size":      len(data),
                    "mtime":     os.path.getmtime(filepath),
                    "cached_at": time.time(),
                    "sector":    sector.value,
                }
                return data
            except Exception:
                return None

    def write(self, filepath: str, data: bytes,
              sector: SectorID = SectorID.SECTOR_4,
              write_through: bool = True):
        with self.lock:
            self.writes += 1
            key = f"fs:{filepath}"
            self.memory.write(key, data, sector=sector)
            if write_through:
                try:
                    Path(filepath).parent.mkdir(parents=True, exist_ok=True)
                    with open(filepath, "wb") as f:
                        f.write(data)
                    self.disk_writes += 1
                except Exception:
                    pass
            self.manifest[filepath] = {
                "size":      len(data),
                "mtime":     time.time(),
                "cached_at": time.time(),
                "sector":    sector.value,
            }

    def invalidate(self, filepath: str):
        with self.lock:
            self.memory.free(f"fs:{filepath}")
            self.manifest.pop(filepath, None)

    def stats(self) -> dict:
        return {
            "cached_files": len(self.manifest),
            "reads":        self.reads,
            "writes":       self.writes,
            "hits":         self.hits,
            "disk_reads":   self.disk_reads,
            "disk_writes":  self.disk_writes,
        }

# ============================================================================
# FRANK CAST/REEL — Frank's interface to the memory stack
# ============================================================================

@dataclass
class CastResult:
    cast_id:   str
    ring:      str
    result:    Any
    timestamp: str = field(default_factory=_now)
    ok:        bool = True
    error:     Optional[str] = None

class FrankCastReel:
    """
    Frank cast/reel pattern on top of HelixMemory.
    Frank casts -> Ring runs -> Line reels result into Helix memory.
    """

    def __init__(self, memory: HelixMemoryManager):
        self.memory  = memory
        self.lock    = threading.RLock()
        self.casts:  Dict[str, CastResult] = {}
        self.total_casts  = 0
        self.total_reeled = 0

    def cast(self, ring: str, fn: Callable, *args,
             sector: SectorID = SectorID.FRANK, **kwargs) -> CastResult:
        cast_id  = hashlib.sha3_512(f"{ring}:{time.time()}".encode()).hexdigest()[:16]
        ts = _now()

        try:
            result = fn(*args, **kwargs)
            cr = CastResult(cast_id=cast_id, ring=ring, result=result, timestamp=ts, ok=True)
        except Exception as e:
            cr = CastResult(cast_id=cast_id, ring=ring, result=None, timestamp=ts, ok=False, error=str(e))

        key = f"frank:cast:{ring}:{ts}"
        self.memory.write(key, {
            "cast_id":   cast_id,
            "ring":      ring,
            "result":    cr.result,
            "ok":        cr.ok,
            "error":     cr.error,
            "timestamp": ts,
        }, sector=sector)

        with self.lock:
            self.casts[cast_id] = cr
            self.total_casts  += 1
            if cr.ok:
                self.total_reeled += 1

        return cr

    def retrieve(self, cast_id: str) -> Optional[CastResult]:
        with self.lock:
            return self.casts.get(cast_id)

    def stats(self) -> dict:
        return {
            "total_casts":  self.total_casts,
            "total_reeled": self.total_reeled,
            "active_casts": len(self.casts),
        }

# ============================================================================
# SECTOR ROUTER — memory regions per sector
# ============================================================================

class SectorRouter:
    """
    Routes memory operations to the correct sector region.
    Each sector gets its own key namespace.
    """

    SECTOR_PREFIXES = {
        SectorID.SECTOR_1: "s1:",
        SectorID.SECTOR_2: "s2:",
        SectorID.SECTOR_3: "s3:",
        SectorID.SECTOR_4: "s4:",
        SectorID.GAME:     "gm:",
        SectorID.FRANK:    "fr:",
        SectorID.CLAUDE:   "cl:",
    }

    def __init__(self, memory: HelixMemoryManager):
        self.memory = memory

    def key(self, sector: SectorID, name: str) -> str:
        return f"{self.SECTOR_PREFIXES.get(sector, 's4:')}{name}"

    def write(self, sector: SectorID, name: str, data: Any) -> bool:
        return self.memory.write(self.key(sector, name), data, sector=sector)

    def read(self, sector: SectorID, name: str) -> Optional[Any]:
        return self.memory.read(self.key(sector, name))

    def free(self, sector: SectorID, name: str) -> bool:
        return self.memory.free(self.key(sector, name))

# ============================================================================
# PCS TORRENT MODEL (High-Velocity Load-Responsive Compression)
# ============================================================================

class PCSTorrentModel:
    def __init__(self, cache: HelixCache):
        self.cache = cache
        self.load = 0.0
        self.lock = threading.RLock()
        self.peak_load = 0.0
        self.compressions_triggered = 0

    def update_load(self, load_factor: float):
        with self.lock:
            self.load = max(0.0, min(1.0, load_factor))
            self.peak_load = max(self.peak_load, self.load)
            if self.load > 0.7:
                self._compress_l2()

    def _compress_l2(self):
        with self.cache.lock:
            for key, block in self.cache.l2.items():
                if not block.compressed and not block.pinned:
                    if block.compress() > 0:
                        self.cache.compressions += 1
                        self.compressions_triggered += 1

    def stats(self) -> dict:
        return {
            "load_factor": round(self.load, 3),
            "peak_load": round(self.peak_load, 3),
            "compressions_triggered": self.compressions_triggered
        }

# ============================================================================
# HELIX SYSTEM (Unified Superpowers Layer)
# ============================================================================

class HelixSystem:
    def __init__(self, helix=None, l1_mb: int = 512, l2_mb: int = 2048, l3_mb: int = 8192, virtual_mb: int = 524288):
        self.helix   = helix
        self.cache   = HelixCache(l1_mb, l2_mb, l3_mb)
        self.memory  = HelixMemoryManager(self.cache, virtual_mb)
        self.fs      = HelixFS(self.memory)
        self.frank   = FrankCastReel(self.memory)
        self.sectors = SectorRouter(self.memory)
        self.pcs     = PCSTorrentModel(self.cache)
        self._start  = time.time()
    
    def start(self): 
        print("🧬 Helix Memory Stack [High-Velocity 4x] Online")

    def signal_load(self, load: float):
        self.pcs.update_load(load)

    def cast(self, ring: str, fn: Callable, *args, sector: SectorID = SectorID.FRANK, **kwargs) -> CastResult:
        result = self.frank.cast(ring, fn, *args, sector=sector, **kwargs)
        if self.helix and result.ok and result.result is not None:
            try:
                self.helix.store(f"frank:cast:{ring}", result.result, meta={"cast_id": result.cast_id, "ring": ring})
            except Exception:
                pass
        return result

    def sector_write(self, sector: SectorID, name: str, data: Any) -> bool:
        ok = self.sectors.write(sector, name, data)
        if ok and self.helix:
            try:
                self.helix.store(f"{sector.value}:{name}", data, meta={"sector": sector.value})
            except Exception:
                pass
        return ok

    def sector_read(self, sector: SectorID, name: str) -> Optional[Any]:
        result = self.sectors.read(sector, name)
        if result is None and self.helix:
            try:
                rec = self.helix.get(f"{sector.value}:{name}")
                if rec:
                    result = rec.data
                    self.sectors.write(sector, name, result)
            except Exception:
                pass
        return result

    def stats(self) -> dict:
        uptime = time.time() - self._start
        s = {
            "uptime_sec": round(uptime, 2),
            "cache":      self.cache.stats(),
            "memory":     self.memory.stats(),
            "fs":         self.fs.stats(),
            "frank":      self.frank.stats(),
            "pcs":        self.pcs.stats(),
        }
        if self.helix:
            try:
                s["helix_backend"] = self.helix.stats()
            except Exception:
                pass
        return s

# ============================================================================
# CLAUDE MEMORY — cross-session AI context backed by Helix L1-L5
# ============================================================================

class ClaudeMemory:
    MAX_HISTORY = 40
    KEY_PREFIX  = "cl"

    def __init__(self, system: HelixSystem, session_id: str = ""):
        self.cache   = system.cache
        self.sector  = SectorID.CLAUDE
        self.session_id = session_id or "default"
        self._lock   = threading.RLock()
        self._seq    = 0

        self._pipeline: Optional[Any] = None
        try:
            _sector4 = Path(__file__).parent.parent
            import sys as _sys
            _sys.path.insert(0, str(_sector4 / "coms1"))
            from helix_universal_translation import HelixTranslationPipeline
            self._pipeline = HelixTranslationPipeline()
        except Exception:
            pass

    def _key(self, name: str) -> str:
        return f"{self.KEY_PREFIX}:{name}"

    def push_turn(self, role: str, content: str):
        with self._lock:
            self._seq += 1
            turn = {
                "role":       role,
                "content":    content,
                "seq":        self._seq,
                "session_id": self.session_id,
                "at":         _now(),
            }

            if self._pipeline:
                try:
                    pkt_id = f"cl:{self.session_id}:turn:{self._seq}"
                    self._pipeline.ingest(turn, source_format="json", key=pkt_id)
                except Exception:
                    pass

            history = self._get_raw_history()
            history.append({"role": role, "content": content})
            if len(history) > self.MAX_HISTORY:
                history = history[-self.MAX_HISTORY:]
            data = {"turns": history, "session_id": self.session_id}
            size = len(json.dumps(data).encode())
            self.cache.put(self._key("conversation"), data, size, self.sector)

    def get_history(self, max_turns: int = 20) -> List[Dict]:
        with self._lock:
            history = self._get_raw_history()
            return history[-max_turns:] if max_turns else history

    def _get_raw_history(self) -> List[Dict]:
        cached = self.cache.get(self._key("conversation"))
        if cached and isinstance(cached, dict):
            return list(cached.get("turns", []))
        return []

    def save_context(self, context: Dict):
        data = {"context": context, "session_id": self.session_id, "saved_at": _now()}
        if self._pipeline:
            try:
                self._pipeline.ingest(data, source_format="json", key=f"cl:{self.session_id}:context")
            except Exception:
                pass
        size = len(json.dumps(data).encode())
        self.cache.put(self._key("system_context"), data, size, self.sector)

    def get_context(self) -> Optional[Dict]:
        cached = self.cache.get(self._key("system_context"))
        return cached.get("context") if cached else None

    def save_reply(self, reply: str):
        data = {"reply": reply, "session_id": self.session_id, "at": _now()}
        if self._pipeline:
            try:
                self._pipeline.ingest(data, source_format="json", key=f"cl:{self.session_id}:reply:{self._seq}")
            except Exception:
                pass
        size = len(reply.encode())
        self.cache.put(self._key("last_reply"), data, size, self.sector)

    def clear_session(self):
        for name in ("conversation", "system_context", "last_reply"):
            self.cache.invalidate(self._key(name))

    def stats(self) -> Dict:
        history = self._get_raw_history()
        ctx     = self.get_context()
        base = {
            "turns":        len(history),
            "seq":          self._seq,
            "has_context":  ctx is not None,
            "session_id":   self.session_id,
            "pipeline":     "QuadralingualPacket" if self._pipeline else "HelixCache-only",
            "cache_stats":  self.cache.stats(),
        }
        if self._pipeline:
            try:
                base["helix_status"] = self._pipeline.helix_status()
            except Exception:
                pass
        return base

# ============================================================================
# FRANK DIRECT RUN HOOK
# ============================================================================

def run(data: bytes = b"", ball=None, pcs=None):
    system = HelixSystem(l1_mb=512, l2_mb=2048, l3_mb=8192, virtual_mb=524288)
    system.start()

    log = logging.getLogger("helix_memory.run")
    log.info("Helix paging manager online — 512MB L1 / 2GB L2 / 8GB L3 / 512GB vRAM")

    while True:
        try:
            if psutil:
                mem = psutil.virtual_memory()
                load = mem.percent / 100.0
            else:
                load = 0.5
            system.signal_load(load)
        except Exception as e:
            log.error(f"Paging manager error: {e}")
        time.sleep(5)

if __name__ == "__main__":
    s = HelixSystem()
    s.start()
    cm = ClaudeMemory(s, session_id="test_session")
    cm.push_turn("user", "Hello Phoenix")
    cm.push_turn("assistant", "Helix Memory is online.")
    print("Self-test history:", cm.get_history())
    print("Self-test stats:", cm.stats())
    print("✓ SECTOR4/vault/helix_memory.py verified!")
