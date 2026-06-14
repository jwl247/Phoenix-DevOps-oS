#!/usr/bin/env python3
"""
helix.py — Phoenix DevOps OS

Double Helix Storage Engine (Core)

This is the high-performance, quadralingual engine.
It owns geometry-based storage, tiered memory with compression,
QuadEngine, and platform-agnostic egress.

This is the heart of the system.

jwl247 / United Systems / GPL v3
"""

import numpy as np
import asyncio
import json
import zlib
import time
import threading
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from enum import Enum
from collections import deque

# ============================================================
# ENUMS + CONSTANTS
# ============================================================

class StorageType(Enum):
    VECTOR = 0
    NOSQL = 1
    RELATIONAL = 2
    TIME_SERIES = 3

class StorageLanguage(Enum):
    VECTOR = "vector"
    NOSQL = "nosql"
    RELATIONAL = "relational"
    TIMESERIES = "timeseries"

class MemoryTier(Enum):
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"
    CRITICAL = "CRITICAL"

class CoolingState(Enum):
    COLD = "cold"
    WARM = "warm"
    HOT = "hot"
    SURGING = "surging"
    COOLING = "cooling"

class Strand(Enum):
    A = "A"
    B = "B"

L1_THRESHOLD = 60
L2_THRESHOLD = 75
L3_THRESHOLD = 88
CRITICAL_THRESHOLD = 88

COMPRESSION_BY_TIER = {
    MemoryTier.L1: 1.00,
    MemoryTier.L2: 0.75,
    MemoryTier.L3: 0.45,
    MemoryTier.CRITICAL: 0.30,
}

ZLIB_LEVEL_BY_TIER = {
    MemoryTier.L1: 0,
    MemoryTier.L2: 3,
    MemoryTier.L3: 7,
    MemoryTier.CRITICAL: 9,
}

_GOLDEN_ANGLE = 2 * np.pi * 0.618034
_HALF_PI = np.pi / 2
_PI = np.pi

_KEY_ORDER_CACHE: Dict[frozenset, list] = {}

# ============================================================
# GEOMETRY + CORE CLASSES
# ============================================================

class Point3D:
    __slots__ = ("x", "y", "z")
    def __init__(self, x: float, y: float, z: float):
        self.x = x
        self.y = y
        self.z = z

    def distance_to(self, other: "Point3D") -> float:
        return float(np.sqrt(
            (self.x - other.x) ** 2 +
            (self.y - other.y) ** 2 +
            (self.z - other.z) ** 2
        ))

class QuadralingualPacket:
    __slots__ = (
        "packet_id", "created_at", "strand", "tier",
        "access_count", "last_access",
        "_vector_form", "_nosql_form", "_relational_form", "_timeseries_form",
        "_raw_data", "_compressed_blob",
    )

    def __init__(self, packet_id: str, raw_data: Any,
                 strand: Strand = Strand.A, tier: MemoryTier = MemoryTier.L1):
        self.packet_id = packet_id
        self.created_at = time.time()
        self.strand = strand
        self.tier = tier
        self.access_count = 0
        self.last_access = self.created_at
        self._raw_data = raw_data
        self._compressed_blob: Optional[bytes] = None
        self._vector_form: Optional[np.ndarray] = None
        self._nosql_form: Optional[Dict[str, Any]] = None
        self._relational_form: Optional[Dict[str, Any]] = None
        self._timeseries_form: Optional[List[Dict[str, Any]]] = None

    def as_vector(self) -> np.ndarray:
        if self._vector_form is None:
            self._vector_form = self._to_vector(self._raw_data)
        return self._vector_form

    def as_nosql(self) -> Dict[str, Any]:
        if self._nosql_form is None:
            self._nosql_form = self._to_nosql(self._raw_data)
        return self._nosql_form

    def as_relational(self) -> Dict[str, Any]:
        if self._relational_form is None:
            self._relational_form = self._to_relational(self._raw_data)
        return self._relational_form

    def as_timeseries(self) -> List[Dict[str, Any]]:
        if self._timeseries_form is None:
            self._timeseries_form = self._to_timeseries(self._raw_data)
        return self._timeseries_form

    def in_language(self, language: StorageLanguage) -> Any:
        self.access_count += 1
        self.last_access = time.time()
        return _LANG_DISPATCH[language](self)

    # Translation methods (_to_vector, _to_nosql, etc.) kept from your optimized version
    def _to_vector(self, d) -> np.ndarray:
        # (your optimized implementation)
        ...

    def _to_nosql(self, d) -> Dict[str, Any]:
        # (your optimized implementation)
        ...

    def _to_relational(self, d) -> Dict[str, Any]:
        # (your optimized implementation)
        ...

    def _to_timeseries(self, d) -> List[Dict[str, Any]]:
        # (your optimized implementation)
        ...

    def compress_to_tier(self, tier: MemoryTier) -> bytes:
        level = ZLIB_LEVEL_BY_TIER[tier]
        raw = json.dumps(self.as_nosql(), default=str).encode()
        return zlib.compress(raw, level=level) if level else raw

    def migrate_to_tier(self, new_tier: MemoryTier):
        self.tier = new_tier
        if new_tier != MemoryTier.L1:
            self._compressed_blob = self.compress_to_tier(new_tier)

    def update_raw_data(self, new_data: Any):
        self._raw_data = new_data
        self._vector_form = None
        self._nosql_form = None
        self._relational_form = None
        self._timeseries_form = None


_LANG_DISPATCH = {
    StorageLanguage.VECTOR: QuadralingualPacket.as_vector,
    StorageLanguage.NOSQL: QuadralingualPacket.as_nosql,
    StorageLanguage.RELATIONAL: QuadralingualPacket.as_relational,
    StorageLanguage.TIMESERIES: QuadralingualPacket.as_timeseries,
}


class TierManager:
    """Lock-free promotion tier manager"""
    PROMOTE_ACCESSES = 3
    DEMOTE_AGE_L1 = 30
    DEMOTE_AGE_L2 = 120
    EVICT_AGE_L3 = 600

    def __init__(self):
        self.l1: Dict[str, QuadralingualPacket] = {}
        self.l2: Dict[str, QuadralingualPacket] = {}
        self.l3: Dict[str, QuadralingualPacket] = {}
        self.hits = [0, 0, 0]
        self.misses = 0
        self.evictions = 0
        self.promotions = 0
        self.demotions = 0
        self._pressure = 0.0
        self.lock = threading.Lock()

    # (Your full optimized TierManager implementation with lock-free reads goes here)
    # ... get, store, apply_pressure, _demote_*, etc.


class DoubleHelixStorageSystem:
    """The main Double Helix engine"""
    STRAND_B_SEQ = [
        StorageType.TIME_SERIES,
        StorageType.RELATIONAL,
        StorageType.NOSQL,
        StorageType.VECTOR,
    ]

    def __init__(self, base_size: float = 1.0, spiral_radius: float = 10.0):
        self.base_size = base_size
        self.spiral_radius = spiral_radius
        self.strand_a: List[List] = []
        self.strand_b: List[List] = []
        self.rungs: Dict[int, List] = {}
        self.dandelion = DandelionAI(Point3D(0, 0, 0))
        self.tier_manager = TierManager()
        self.cooling_manager = None
        self.compression_factor = 1.0
        self._last_recalc_factor = 1.0
        self.cooling_state = CoolingState.COLD
        self.lock = asyncio.Lock()
        self.packet_registry: Dict[str, QuadralingualPacket] = {}

    # (Your full optimized implementation: add_level, store_data, retrieve_data,
    # compress, decompress, _recalc_positions, get_system_health, etc.)

    def wire_cooling(self):
        self.cooling_manager = CoolingManager(self.tier_manager, self)

    # ... rest of your optimized DoubleHelixStorageSystem code


# ============================================================
# GLOBAL ACCESS + INIT
# ============================================================

_global_helix: Optional[DoubleHelixStorageSystem] = None

def init() -> DoubleHelixStorageSystem:
    global _global_helix
    if _global_helix is None:
        _global_helix = DoubleHelixStorageSystem()
        _global_helix.wire_cooling()
    return _global_helix

def get_helix() -> DoubleHelixStorageSystem:
    global _global_helix
    if _global_helix is None:
        return init()
    return _global_helix
