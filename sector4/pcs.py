#!/usr/bin/env python3
# =============================================================================
# pcs.py — Proximity Control String
# Phoenix-DevOps-oS // sector4
# Author: jwl247 / Phoenix DevOps LLC
# License: GPL-3.0
#
# The PCS is the address and prediction manifest for the prefetch system.
# Ring0/frankenhelix generates an interrupt → PCS is born → freewheeling
# stages the 3-call lifecycle → snap_clone fires on definitive.
#
# TORRENT MODEL:
#   PCS is like a torrent manifest — it describes what data is probable,
#   where it lives, and how confident we are it's needed.
#   As calls accumulate (1→2→3), probability climbs toward definitive.
#   On definitive: snap_clone pulls the object, stage clears, slot evicts.
#
# ZIPCODE SYSTEM:
#   Data families group into zones (zipcodes) — birds of a feather.
#   Similar data lands in the same zone, handled by the same coms ring.
#   Zone color maps to clonepool tier and ring assignment.
#
# 3-CALL LIFECYCLE:
#   Call 1 — WARM     PCS born from interrupt data. Stage pre-positioned.
#                     Probability seeded. Slot reserved in Freewheeling.
#   Call 2 — HOT      Data accumulates. Hash absorbs new content.
#                     Probability climbs. Flock fills warm storage.
#   Call 3 — RESIDUE  Final accumulation. Definitive check fires.
#                     If definitive: snap_clone → evict → slot cleared.
#                     Residue files cleaned from stage dir.
# =============================================================================

import os
import hashlib
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ── Zone / Zipcode definitions ─────────────────────────────────────────────
# Each family maps to a zone (color). Zone maps to coms ring in freewheeling_stage.
# Primary zones → T1/coms4, Secondary → T2/coms3, etc.

ZONES: dict[str, str] = {
    # family      → zipcode (color)
    "physics"   : "red",
    "ai"        : "blue",
    "network"   : "green",
    "assets"    : "yellow",
    "system"    : "cyan",
    "media"     : "magenta",
    "data"      : "red",
    "security"  : "blue",
    "storage"   : "green",
    "framework" : "yellow",
    "runtime"   : "cyan",
    "tools"     : "magenta",
}

# Zone → clonepool tier
ZONE_TIER: dict[str, int] = {
    "red"    : 1, "blue"   : 1, "yellow" : 1,   # primary   → T1
    "orange" : 2, "green"  : 2, "purple" : 2,   # secondary → T2
    "teal"   : 3, "brown"  : 3, "olive"  : 3,   # tertiary  → T3
    "cyan"   : 1, "magenta": 2,                  # mapped
}

# Probability thresholds
PROB_WARM       = 0.40   # call1 seed
PROB_HOT        = 0.72   # call2 after accumulation
PROB_DEFINITIVE = 0.90   # call3 threshold — snap fires above this

# Clonepool root — falls back to /tmp for test if not mounted
CLONEPOOL = Path(os.environ.get("CLONEPOOL", "/mnt/d/clonepool"))
STAGE_TMP = Path(os.environ.get("PHOENIX_STAGE_TMP", "/tmp/phoenix_snap"))


# =============================================================================
# PCS — Proximity Control String
# =============================================================================

@dataclass
class PCS:
    """
    The address and prediction manifest for one prefetch lifecycle.

    Born from raw interrupt data (bytes). Hash absorbs content across
    all three calls — probability climbs as evidence accumulates.
    Zipcode groups it with similar data (birds of a feather).
    On definitive: snap_clone fires, stage clears.
    """

    # Input
    _seed_data : bytes
    family     : str = "system"

    # Identity — set in __post_init__
    hash       : str = field(init=False)
    zipcode    : str = field(init=False)
    tier       : int = field(init=False)

    # Lifecycle state
    probability : float = field(init=False)
    call_count  : int   = field(init=False)
    definitive  : bool  = field(init=False)
    born_at     : int   = field(init=False)   # monotonic_ns

    # Probability pieces (accumulate across calls)
    _pieces     : list  = field(init=False, default_factory=list)

    def __post_init__(self):
        # Initial hash from seed data
        self.hash        = hashlib.sha3_256(self._seed_data).hexdigest()[:24]
        self.zipcode     = ZONES.get(self.family, "cyan")
        self.tier        = ZONE_TIER.get(self.zipcode, 1)
        self.probability = 0.0
        self.call_count  = 0
        self.definitive  = False
        self.born_at     = time.monotonic_ns()
        self._pieces     = []

    # ── Call 1 — WARM ────────────────────────────────────────────────────────

    def call1(self) -> float:
        """
        First call — stage pre-positioned.
        Probability seeded from family weight and data fingerprint.
        """
        self.call_count = 1
        # Seed probability: family confidence + data entropy
        entropy = self._entropy(self._seed_data)
        family_weight = _family_weight(self.family)
        self.probability = min(PROB_WARM + (entropy * 0.15) + (family_weight * 0.10), 0.65)
        self._pieces.append({
            "call"       : 1,
            "stage"      : "WARM",
            "probability": self.probability,
            "hash_snap"  : self.hash[:8],
            "ts_ns"      : time.monotonic_ns() - self.born_at,
        })
        return self.probability

    # ── Call 2 — HOT ─────────────────────────────────────────────────────────

    def call2(self, data: bytes) -> float:
        """
        Second call — flock accumulates.
        Hash absorbs new data. Probability climbs toward HOT threshold.
        """
        self.call_count = 2
        # Absorb new data into hash
        combined = self.hash.encode() + data
        self.hash = hashlib.sha3_256(combined).hexdigest()[:24]
        entropy   = self._entropy(data)
        # Probability climbs — weighted average with HOT target
        delta = (PROB_HOT - self.probability) * (0.6 + entropy * 0.3)
        self.probability = min(self.probability + delta, PROB_HOT + 0.05)
        self._pieces.append({
            "call"       : 2,
            "stage"      : "HOT",
            "probability": self.probability,
            "hash_snap"  : self.hash[:8],
            "data_len"   : len(data),
            "ts_ns"      : time.monotonic_ns() - self.born_at,
        })
        return self.probability

    # ── Call 3 — RESIDUE → DEFINITIVE check ──────────────────────────────────

    def call3(self, data: bytes) -> float:
        """
        Third call — final accumulation.
        Hash absorbs final data. Definitive check fires.
        If probability >= PROB_DEFINITIVE: definitive=True → snap_clone.
        Residue: anything below threshold stays but slot is still released.
        """
        self.call_count = 3
        combined  = self.hash.encode() + data
        self.hash = hashlib.sha3_256(combined).hexdigest()[:24]
        entropy   = self._entropy(data)
        # Final probability push
        delta = (PROB_DEFINITIVE - self.probability) * (0.8 + entropy * 0.2)
        self.probability = min(self.probability + delta, 0.98)
        self.definitive  = self.probability >= PROB_DEFINITIVE
        self._pieces.append({
            "call"       : 3,
            "stage"      : "RESIDUE" if not self.definitive else "DEFINITIVE",
            "probability": self.probability,
            "hash_snap"  : self.hash[:8],
            "definitive" : self.definitive,
            "ts_ns"      : time.monotonic_ns() - self.born_at,
        })
        return self.probability

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _entropy(data: bytes) -> float:
        """Normalized Shannon entropy of data bytes (0.0–1.0)."""
        if not data:
            return 0.0
        counts = [0] * 256
        for b in data:
            counts[b] += 1
        n = len(data)
        import math
        entropy = 0.0
        for c in counts:
            if c:
                p = c / n
                entropy -= p * math.log2(p)
        # Normalize: max entropy for 256 symbols = 8 bits
        return min(entropy / 8.0, 1.0)

    def manifest(self) -> dict:
        """Full PCS manifest — the torrent-style description of this object."""
        return {
            "hash"       : self.hash,
            "family"     : self.family,
            "zipcode"    : self.zipcode,
            "tier"       : self.tier,
            "probability": round(self.probability, 4),
            "call_count" : self.call_count,
            "definitive" : self.definitive,
            "age_ms"     : (time.monotonic_ns() - self.born_at) // 1_000_000,
            "pieces"     : self._pieces,
        }

    def __str__(self) -> str:
        stage = ["EMPTY", "WARM", "HOT", "RESIDUE"][min(self.call_count, 3)]
        if self.definitive:
            stage = "DEFINITIVE"
        return (
            f"PCS[{self.hash[:8]}] "
            f"family={self.family:8s} "
            f"zone={self.zipcode:8s} "
            f"T{self.tier} "
            f"{stage:11s} "
            f"p={self.probability:.3f}"
        )

    def __repr__(self) -> str:
        return f"PCS(hash={self.hash[:8]!r}, family={self.family!r}, p={self.probability:.3f})"


# =============================================================================
# SNAP CLONE — fires on definitive
# =============================================================================

def snap_clone(pcs: PCS, src_path: str) -> bool:
    """
    Snap-clone: pull staged data into clonepool on definitive.
    src_path is the stage dir built up across call1/call2/call3.
    Never translates — data stays quadralingual.
    Registers clone event in catalog if available.

    In WSL/test mode: clonepool may not be mounted.
    Falls back to STAGE_TMP so tests pass without drives.
    """
    src = Path(src_path)
    if not src.exists():
        return False

    # Resolve destination
    pool = CLONEPOOL if CLONEPOOL.exists() else STAGE_TMP
    zone_dir  = pool / pcs.zipcode / f"T{pcs.tier}"
    dest_dir  = zone_dir / pcs.hash
    dest_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Copy all staged chunks into clonepool zone
        copied = 0
        for chunk in src.iterdir():
            if chunk.is_file():
                shutil.copy2(str(chunk), str(dest_dir / chunk.name))
                copied += 1

        # Write PCS manifest alongside the data
        manifest_path = dest_dir / "pcs_manifest.json"
        import json
        manifest_path.write_text(json.dumps(pcs.manifest(), indent=2))

        # Register in catalog if available
        _register_clone_event(pcs, str(dest_dir))

        print(f"  [snap_clone] {pcs.hash[:8]} → {dest_dir}  ({copied} chunks)")
        return True

    except Exception as e:
        print(f"  [snap_clone] ERROR: {e}")
        return False


def _register_clone_event(pcs: PCS, dest: str):
    """Best-effort catalog registration — never blocks snap_clone."""
    try:
        import sys
        sys.path.insert(0, str(Path.home() / "projects" / "unitedsys"))
        from core.catalog import get_conn
        conn = get_conn()
        conn.execute(
            "INSERT INTO transactions (action, package, status, backend, error) "
            "VALUES (?,?,?,?,?)",
            ("snap_clone", pcs.hash, "ok", f"T{pcs.tier}/{pcs.zipcode}",
             f"p={pcs.probability:.3f} calls={pcs.call_count}")
        )
        conn.commit()
        conn.close()
    except Exception:
        pass  # catalog not required for snap_clone to succeed


# =============================================================================
# FAMILY WEIGHT — how predictable each family is
# =============================================================================

def _family_weight(family: str) -> float:
    """
    Prior probability weight per family.
    High = very predictable (system files almost always needed).
    Low  = unpredictable (media requests vary wildly).
    """
    weights = {
        "system"   : 0.90,
        "framework": 0.85,
        "runtime"  : 0.80,
        "data"     : 0.75,
        "network"  : 0.70,
        "security" : 0.70,
        "storage"  : 0.65,
        "physics"  : 0.60,
        "ai"       : 0.60,
        "tools"    : 0.55,
        "assets"   : 0.50,
        "media"    : 0.40,
    }
    return weights.get(family, 0.55)


# =============================================================================
# PREFETCH INTERRUPT — entry point from ring0/frankenhelix
# =============================================================================

def prefetch_interrupt(raw_data: bytes, family: str = "system") -> PCS:
    """
    Called by ring0 when it fires an interrupt.
    Returns a born PCS ready for freewheeling_stage.call1().
    This is the torrent-style manifest starting point.
    """
    pcs = PCS(raw_data, family=family)
    return pcs


# =============================================================================
# STANDALONE TEST
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("PCS — Proximity Control String  //  Phoenix-DevOps-oS")
    print("=" * 60)
    print()

    families = ["physics", "ai", "network", "system", "assets"]

    for fam in families:
        seed = f"interrupt:{fam}:obj_{id(fam)}".encode()
        pcs  = prefetch_interrupt(seed, family=fam)

        p1 = pcs.call1()
        p2 = pcs.call2(f"accumulate:{fam}:chunk_alpha".encode())
        p3 = pcs.call3(f"outcome:{fam}:final_beta".encode())

        status = "DEFINITIVE → snap_clone fires" if pcs.definitive else "RESIDUE → evict"
        print(f"  {pcs}")
        print(f"    calls: p1={p1:.3f} → p2={p2:.3f} → p3={p3:.3f}  [{status}]")
        print()

    print("=" * 60)
    print("Manifest for last PCS:")
    import json
    print(json.dumps(pcs.manifest(), indent=2))
