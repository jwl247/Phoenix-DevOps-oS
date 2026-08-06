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

import os
import time
import pickle
import zlib
import hashlib
import json
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable

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
    SECTOR_1 = "s1"
    SECTOR_2 = "s2"
    SECTOR_3 = "s3"
    SECTOR_4 = "s4"
    GAME     = "gm"   # game engine state — CoPES, physics, world
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
# HELIX CACHE — L1 / L2 / L3 (High-Velocity Config)
# ============================================================================

class HelixCache:
    def __init__(self, l1_mb: int, l2_mb: int, l3_mb: int):
        self.l1_max = l1_mb * 1024 * 1024
        self.l2_max = l2_mb * 1024 * 1024
        self.l3_max = l3_mb * 1024 * 1024

        self.l1: OrderedDict[str, CacheBlock] = OrderedDict()
        self.l2: OrderedDict[str, CacheBlock] = OrderedDict()
        self.l3: OrderedDict[str, CacheBlock] = OrderedDict()

        self.lock = threading.RLock()
        self.hits = {"l1": 0, "l2": 0, "l3": 0}
        self.misses = {"l1": 0, "l2": 0, "l3": 0}
        self.promotions = 0
        self.demotions = 0
        self.compressions = 0
        self.evictions = 0

    def get(self, key: str) -> Optional[Any]:
        with self.lock:
            if key in self.l1:
                self.hits["l1"] += 1
                b = self.l1[key]
                b.touch()
                self.l1.move_to_end(key)
                return b.data

            self.misses["l1"] += 1
            if key in self.l2:
                self.hits["l2"] += 1
                b = self.l2[key]
                b.touch()
                # Higher threshold for promotion in high-velocity mode
                if b.access_count >= 10:
                    self._promote_l1(key, b)
                else:
                    self.l2.move_to_end(key)
                return b.data

            self.misses["l2"] += 1
            if key in self.l3:
                self.hits["l3"] += 1
                b = self.l3[key]
                b.touch()
                if b.compressed: b.decompress()
                if b.access_count >= 5:
                    self._promote_l2(key, b)
                else:
                    self.l3.move_to_end(key)
                return b.data

            self.misses["l3"] += 1
            return None

    def put(self, key: str, data: Any, size: int, sector: SectorID = SectorID.SECTOR_4, pinned: bool = False):
        with self.lock:
            self.l2.pop(key, None)
            self.l3.pop(key, None)
            b = CacheBlock(key=key, data=data, tier=MemoryTier.L1_HOT, size_bytes=size, sector=sector, pinned=pinned)
            self._make_room_l1(size)
            self.l1[key] = b

    def invalidate(self, key: str):
        with self.lock:
            self.l1.pop(key, None); self.l2.pop(key, None); self.l3.pop(key, None)

    def _tier_size(self, tier: OrderedDict) -> int:
        return sum(b.effective_size for b in tier.values())

    def _make_room_l1(self, needed: int):
        while self._tier_size(self.l1) + needed > self.l1_max and self.l1:
            key, b = next(iter(self.l1.items()))
            if b.pinned: self.l1.move_to_end(key); continue
            self._demote_l2(key, b)

    def _make_room_l2(self, needed: int):
        while self._tier_size(self.l2) + needed > self.l2_max and self.l2:
            key, b = next(iter(self.l2.items()))
            if b.pinned: self.l2.move_to_end(key); continue
            self._demote_l3(key, b)

    def _make_room_l3(self, needed: int):
        while self._tier_size(self.l3) + needed > self.l3_max and self.l3:
            key, b = next(iter(self.l3.items()))
            if b.pinned: self.l3.move_to_end(key); continue
            del self.l3[key]; self.evictions += 1

    def _promote_l1(self, key: str, b: CacheBlock):
        self.l2.pop(key, None); self._make_room_l1(b.size_bytes); b.tier = MemoryTier.L1_HOT; self.l1[key] = b; self.promotions += 1

    def _promote_l2(self, key: str, b: CacheBlock):
        self.l3.pop(key, None); self._make_room_l2(b.size_bytes); b.tier = MemoryTier.L2_WARM; self.l2[key] = b; self.promotions += 1

    def _demote_l2(self, key: str, b: CacheBlock):
        self.l1.pop(key, None); self._make_room_l2(b.size_bytes); b.tier = MemoryTier.L2_WARM; self.l2[key] = b; self.demotions += 1

    def _demote_l3(self, key: str, b: CacheBlock):
        self.l2.pop(key, None); saved = b.compress(); self._make_room_l3(b.effective_size); b.tier = MemoryTier.L3_COMPRESSED; self.l3[key] = b; self.demotions += 1

    def stats(self) -> dict:
        with self.lock:
            total_ops = sum(self.hits.values()) + sum(self.misses.values())
            hit_rate = (sum(self.hits.values()) / total_ops * 100) if total_ops else 100.0
            return {"l1_items": len(self.l1), "l2_items": len(self.l2), "l3_items": len(self.l3),
                    "l1_mb": round(self._tier_size(self.l1) / 1048576, 2), "l2_mb": round(self._tier_size(self.l2) / 1048576, 2),
                    "l3_mb": round(self._tier_size(self.l3) / 1048576, 2), "hit_rate": round(hit_rate, 2),
                    "hits": self.hits, "misses": self.misses, "promotions": self.promotions, "demotions": self.demotions,
                    "compressions": self.compressions, "evictions": self.evictions}

# [Other classes: HelixMemoryManager, HelixFS, FrankCastReel, SectorRouter remain functionally same]

# ============================================================================
# PCS TORRENT MODEL (High-Velocity Trigger)
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
            # High-velocity trigger: only compress at 95%+ load
            if self.load > 0.95:
                self._compress_l2()

    def _compress_l2(self):
        with self.cache.lock:
            for key, block in self.cache.l2.items():
                if not block.compressed and not block.pinned:
                    if block.compress() > 0:
                        self.cache.compressions += 1
                        self.compressions_triggered += 1

    def stats(self) -> dict:
        return {"load_factor": round(self.load, 3), "peak_load": round(self.peak_load, 3), "compressions_triggered": self.compressions_triggered}

# ============================================================================
# HELIX SYSTEM (High-Velocity Init)
# ============================================================================
#!/usr/bin/env python3
import time
import pickle
import threading
import psutil
import logging
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Optional

# [Helix Classes: MemoryManager, FS, Frank, Router, Cache, PCS, HelixSystem defined above]

class HelixSystem:
    def __init__(self, l1_mb=512, l2_mb=2048, l3_mb=8192, virtual_mb=524288):
        self.cache = HelixCache(l1_mb, l2_mb, l3_mb)
        self.memory = HelixMemoryManager(self.cache, virtual_mb)
        self.fs = HelixFS(self.memory)
        self.frank = FrankCastReel(self.memory)
        self.sectors = SectorRouter(self.memory)
        self.pcs = PCSTorrentModel(self.cache)
        self._start = time.time()
    
    def start(self): 
        print("🧬 Helix Memory Stack [High-Velocity 4x] Online")

    def signal_load(self, load: float):
        self.pcs.update_load(load)

# ============================================================================
# CLAUDE MEMORY — cross-session AI context backed by Helix L1-L5
# ============================================================================
#
# Game and Claude share the same HelixSystem instance.
# Game state lives under SectorID.GAME.
# Claude context lives under SectorID.CLAUDE.
# Same L1→L5 pipeline, same persistence guarantees, same PCS torrent pressure model.
#
# Key layout (L1/L2/L3 cache):
#   cl:conversation        → list of {role, content} dicts (last N turns)
#   cl:system_context      → injected Phoenix system state at last call
#   cl:last_reply          → most recent Claude response
#   cl:session_id          → boot-time UUID, rotates each Phoenix boot
#
# L4 (clone pool) and L5 (D1) persistence are handled by the parent HelixSystem
# when the system flushes dirty blocks on graceful shutdown or pressure.

class ClaudeMemory:
    """
    Claude's memory interface — rides the full Helix stack.

    Every turn is stored as a QuadralingualPacket via HelixTranslationPipeline:
      - NOSQL view   → conversation history (what the HUD reads back)
      - VECTOR view  → embedding for similarity search (game can query semantically)
      - RELATIONAL   → flat row for D1/SQL queries
      - TIMESERIES   → temporal replay of the conversation arc

    Same sector, same packets, same pipeline as the game engine.
    SectorID.CLAUDE keeps Claude's data partitioned without isolation.

    Usage:
        mem = ClaudeMemory(helix_system)
        mem.push_turn("user", "what is the helix engine?")
        mem.push_turn("assistant", "Helix is a double-strand...")
        history = mem.get_history(max_turns=20)
        mem.save_context({"glossary_total": 138, ...})
    """

    MAX_HISTORY = 40
    KEY_PREFIX  = "cl"

    def __init__(self, system: 'HelixSystem', session_id: str = ""):
        self.cache   = system.cache
        self.sector  = SectorID.CLAUDE
        self.session_id = session_id or "default"
        self._lock   = threading.RLock()
        self._seq    = 0   # monotonic turn counter for timeseries ordering

        # Wire into HelixTranslationPipeline (QuadralingualPacket store)
        # Import deferred — coms1/freewheeling.py must be on path
        self._pipeline: Optional[Any] = None
        try:
            _sector4 = Path(__file__).parent
            import sys as _sys
            _sys.path.insert(0, str(_sector4 / "coms1"))
            from helix_universal_translation import HelixTranslationPipeline
            self._pipeline = HelixTranslationPipeline()
        except Exception as _e:
            pass  # pipeline unavailable — fall back to HelixCache only

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

            # Store individual turn as QuadralingualPacket in DoubleHelixStorage
            if self._pipeline:
                pkt_id = f"cl:{self.session_id}:turn:{self._seq}"
                self._pipeline.ingest(turn, source_format="json", key=pkt_id)

            # Also keep rolling list in HelixCache L1/L2/L3 for fast sequential retrieval
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
        """Save Phoenix system state snapshot as a QuadralingualPacket."""
        data = {"context": context, "session_id": self.session_id, "saved_at": _now()}
        if self._pipeline:
            self._pipeline.ingest(data, source_format="json", key=f"cl:{self.session_id}:context")
        size = len(json.dumps(data).encode())
        self.cache.put(self._key("system_context"), data, size, self.sector)

    def get_context(self) -> Optional[Dict]:
        cached = self.cache.get(self._key("system_context"))
        return cached.get("context") if cached else None

    def save_reply(self, reply: str):
        data = {"reply": reply, "session_id": self.session_id, "at": _now()}
        if self._pipeline:
            self._pipeline.ingest(data, source_format="json", key=f"cl:{self.session_id}:reply:{self._seq}")
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
            base["helix_status"] = self._pipeline.helix_status()
        return base


# ============================================================================
# FRANK DIRECT RUN HOOK
# ============================================================================

def run(data: bytes = b"", ball=None, pcs=None):
    """
    Frank-direct entry point. 
    High-Velocity profile: 512MB L1 / 2GB L2 / 8GB L3 / 512GB vRAM.
    """
    system = HelixSystem(
        l1_mb=512,
        l2_mb=2048,
        l3_mb=8192,
        virtual_mb=524288
    )
    system.start()

    log = logging.getLogger("helix_memory.run")
    log.info("Helix paging manager — 512MB L1 / 2GB L2 / 8GB L3 / 512GB vRAM")
    log.info("PCS torrent model active — load-responsive throughput enabled")

    while True:
        try:
            mem = psutil.virtual_memory()
            load = mem.percent / 100.0
            system.signal_load(load)
            
            if load > 0.7:
                log.info(f"Memory pressure {mem.percent:.1f}% — compressing L2/L3")
            if load > 0.9:
                log.warning(f"High pressure {mem.percent:.1f}% — aggressive compression")
        except Exception as e:
            log.error(f"Paging manager error: {e}")
        time.sleep(5)

if __name__ == "__main__":
    run()