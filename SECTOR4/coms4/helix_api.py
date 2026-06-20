#!/usr/bin/env python3
"""
helix_api.py — SECTOR4 coms ring API
Each coms ring (coms1-4) has its own instance of this file.

Three classes — one ring:
  Franken2     — load balancer, routes balls to the right system
  Freewheeling — memory bank, warm (RAM) + cold (breach_coms drive)
  Propcoms     — ring validator, heartbeat, tick

Freewheeling is wired to freewheeling.py (HelixDB) for warm storage
and to the breach_coms drive path for cold storage.

Cold storage path per ring (breach_coms drives on phoenix-ext):
  coms1 → /media/jwl247/breach_coms1  (T4 TERTIARY  — 4-day window)
  coms2 → /media/jwl247/breach_coms2  (T3 TERTIARY  — day-2 mirror)
  coms3 → /media/jwl247/breach_coms3  (T2 SECONDARY — day-1 mirror)
  coms4 → /media/jwl247/breach_coms4  (T1 PRIMARY   — master vault)

In WSL dev: cold storage falls back to /tmp/phoenix_cold_{ring}/

jwl247 / United Systems / GPL v3
"""

import os
import json
import time
import threading
import logging
from pathlib import Path

log = logging.getLogger(__name__)

# ── Detect which ring this instance is ───────────────────────────────────────
_THIS_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
_RING_NAME = _THIS_DIR.name   # "coms1", "coms2", "coms3", "coms4"
_RING_NUM  = int(_RING_NAME.replace("coms", "")) if _RING_NAME.startswith("coms") else 1

# ── Cold storage paths — breach_coms drives ───────────────────────────────────
_COLD_PATHS = {
    1: Path("/media/jwl247/breach_coms1"),
    2: Path("/media/jwl247/breach_coms2"),
    3: Path("/media/jwl247/breach_coms3"),
    4: Path("/media/jwl247/breach_coms4"),
}
_COLD_FALLBACK = Path(f"/tmp/phoenix_cold_{_RING_NAME}")
_COLD_ROOT = _COLD_PATHS.get(_RING_NUM, _COLD_FALLBACK)

# Use fallback if drive not mounted
if not _COLD_ROOT.exists():
    _COLD_ROOT = _COLD_FALLBACK
    _COLD_ROOT.mkdir(parents=True, exist_ok=True)
    log.info(f"[{_RING_NAME}] Cold storage → fallback: {_COLD_ROOT}")
else:
    log.info(f"[{_RING_NAME}] Cold storage → breach_coms: {_COLD_ROOT}")

# ── Import HelixDB from freewheeling.py (same directory) ─────────────────────
try:
    import sys
    sys.path.insert(0, str(_THIS_DIR))
    from freewheeling import HelixDB
    _HELIX_DB_AVAILABLE = True
except ImportError:
    _HELIX_DB_AVAILABLE = False
    HelixDB = None
    log.warning(f"[{_RING_NAME}] freewheeling.py not found — warm storage in-memory only")


# ============================================================================
# COLD STORAGE — breach_coms drive interface
# ============================================================================

class ColdStorage:
    """
    Interface to the breach_coms drive for this ring.
    Writes are JSON files on the drive.
    Reads scan by key.
    Never translates — data stays quadralingual.
    """
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def write(self, key: str, value):
        """Write to cold storage. Key becomes filename."""
        with self._lock:
            safe_key = key.replace("/", "_").replace(":", "_")
            path = self.root / f"{safe_key}.json"
            try:
                path.write_text(json.dumps({
                    "key":     key,
                    "value":   value,
                    "ts":      time.time(),
                    "ring":    _RING_NAME,
                }, default=str))
                return True
            except Exception as e:
                log.error(f"[{_RING_NAME}] Cold write failed {key}: {e}")
                return False

    def read(self, key: str):
        """Read from cold storage by key."""
        safe_key = key.replace("/", "_").replace(":", "_")
        path = self.root / f"{safe_key}.json"
        try:
            if path.exists():
                data = json.loads(path.read_text())
                return data.get("value")
            return None
        except Exception as e:
            log.error(f"[{_RING_NAME}] Cold read failed {key}: {e}")
            return None

    def delete(self, key: str) -> bool:
        safe_key = key.replace("/", "_").replace(":", "_")
        path = self.root / f"{safe_key}.json"
        try:
            if path.exists():
                path.unlink()
                return True
            return False
        except Exception as e:
            log.error(f"[{_RING_NAME}] Cold delete failed {key}: {e}")
            return False

    def exists(self, key: str) -> bool:
        safe_key = key.replace("/", "_").replace(":", "_")
        return (self.root / f"{safe_key}.json").exists()

    def stats(self) -> dict:
        try:
            files = list(self.root.glob("*.json"))
            total_bytes = sum(f.stat().st_size for f in files)
            return {
                "root":        str(self.root),
                "items":       len(files),
                "total_bytes": total_bytes,
                "total_mb":    round(total_bytes / 1048576, 2),
            }
        except Exception:
            return {"root": str(self.root), "items": 0}


# ============================================================================
# FRANKEN2 — load balancer
# ============================================================================

class Franken2:
    IDENTITY = "Franken2"
    ROLE     = "load_balancing"
    PATH          = str(_THIS_DIR)
    IDENT_PATH    = str(_THIS_DIR / "ident.card")
    RESPONSIBILITY_PATH = str(_THIS_DIR / "responsibility.json")  # FIXED: was OVERFLOW_PATH

    def __init__(self):
        self.ident          = self._load_ident()
        self.responsibility = self._load_responsibility()

    def _load_ident(self):
        try:
            with open(self.IDENT_PATH) as f:
                return f.read().strip()
        except Exception:
            return f"{self.IDENTITY}:{_RING_NAME}"

    def _load_responsibility(self):
        try:
            with open(self.RESPONSIBILITY_PATH) as f:  # FIXED: was OVERFLOW_PATH
                return json.load(f)
        except Exception:
            return {"role": "load_balancing", "ring": _RING_NAME}

    def propose_route(self, ball):
        """Route ball to the right system based on type."""
        ball_type = ball.get("type", "default")
        routing_table = {
            "physics": "system_1",
            "ai":      "system_2",
            "network": "system_3",
            "assets":  "system_4",
        }
        target = routing_table.get(ball_type, "system_1")
        return {"target": target, "ring": _RING_NAME}

    def broadcast(self, ball):
        return {"peer": self.ident, "status": "ok", "ring": _RING_NAME}

    def heartbeat(self):
        return {"peer": self.ident, "alive": True, "ring": _RING_NAME}


# ============================================================================
# FREEWHEELING — memory bank (warm=HelixDB, cold=breach_coms drive)
# ============================================================================

class Freewheeling:
    IDENTITY = "Freewheeling"
    ROLE     = "memory_bank"
    PATH          = str(_THIS_DIR)
    IDENT_PATH    = str(_THIS_DIR / "ident.card")
    RESPONSIBILITY_PATH = str(_THIS_DIR / "responsibility.json")

    def __init__(self):
        self.ident          = self._load_ident()
        self.responsibility = self._load_responsibility()

        # Warm memory — HelixDB (quadralingual, in-memory, fast)
        self.warm_memory: dict = {}           # simple dict fallback
        self._helix_db = None
        if _HELIX_DB_AVAILABLE:
            try:
                self._helix_db = HelixDB(initial_levels=3)
                log.info(f"[{_RING_NAME}] Freewheeling warm storage → HelixDB (3 levels)")
            except Exception as e:
                log.warning(f"[{_RING_NAME}] HelixDB init failed: {e} — using dict")

        # Cold storage — breach_coms drive
        self.cold_storage = ColdStorage(_COLD_ROOT)
        log.info(f"[{_RING_NAME}] Freewheeling cold storage → {_COLD_ROOT}")

        # Load tracking
        self.load = {
            "system_1": 0,
            "system_2": 0,
            "system_3": 0,
            "system_4": 0,
        }
        self.threshold = 5
        self._lock = threading.Lock()

    def _load_ident(self):
        try:
            with open(self.IDENT_PATH) as f:
                return f.read().strip()
        except Exception:
            return f"{self.IDENTITY}:{_RING_NAME}"

    def _load_responsibility(self):
        try:
            with open(self.RESPONSIBILITY_PATH) as f:
                return json.load(f)
        except Exception:
            return {"role": "memory_bank", "ring": _RING_NAME}

    # ── Warm storage (HelixDB → dict fallback) ────────────────────────────────

    def store_warm(self, key, value):
        """Store in warm memory (HelixDB if available, dict fallback)."""
        with self._lock:
            if self._helix_db:
                try:
                    self._helix_db.store(key, value)
                    return True
                except Exception as e:
                    log.warning(f"[{_RING_NAME}] HelixDB store failed: {e}")
            self.warm_memory[key] = value
            return True

    def load_warm(self, key):
        """Load from warm memory."""
        with self._lock:
            if self._helix_db:
                try:
                    result = self._helix_db.get(key)
                    if result is not None:
                        return result
                except Exception:
                    pass
            return self.warm_memory.get(key)

    # ── Cold storage (breach_coms drive) ─────────────────────────────────────

    def store_cold(self, key, value):
        """Store to breach_coms drive."""
        return self.cold_storage.write(key, value)

    def load_cold(self, key):
        """Load from breach_coms drive."""
        return self.cold_storage.read(key)

    # ── Eviction — warm → cold ────────────────────────────────────────────────

    def evict_to_cold(self, key):
        """Move a key from warm to cold storage."""
        value = self.load_warm(key)
        if value is not None:
            self.store_cold(key, value)
            # Remove from warm
            with self._lock:
                self.warm_memory.pop(key, None)
                if self._helix_db:
                    try:
                        # HelixDB doesn't have delete — overwrite with None marker
                        pass
                    except Exception:
                        pass
            return True
        return False

    # ── Load tracking ─────────────────────────────────────────────────────────

    def record_load(self, system: str):
        with self._lock:
            if system in self.load:
                self.load[system] += 1
                if self.load[system] >= self.threshold:
                    log.info(f"[{_RING_NAME}] Load threshold hit on {system}")

    def get_load(self) -> dict:
        with self._lock:
            return dict(self.load)

    # ── Stats ─────────────────────────────────────────────────────────────────

    def status(self) -> dict:
        warm_count = len(self.warm_memory)
        if self._helix_db:
            try:
                warm_count = self._helix_db.stats().get("total_packets", warm_count)
            except Exception:
                pass
        return {
            "ring":         _RING_NAME,
            "warm_items":   warm_count,
            "cold":         self.cold_storage.stats(),
            "load":         self.load,
            "helix_db":     self._helix_db is not None,
        }


# ============================================================================
# PROPCOMS — ring validator + heartbeat
# ============================================================================

class Propcoms:
    IDENTITY = "Propcoms"
    ROLE     = "ring_validator"

    def __init__(self):
        self.ident         = f"{self.IDENTITY}:{_RING_NAME}"
        self._alive        = True
        self._last_tick    = 0
        self._lock         = threading.Lock()
        self.valid_targets = ["system_1", "system_2", "system_3", "system_4"]

    def validate(self, ball, contextual):
        """Validate a ball for this ring."""
        if contextual.get("escalate"):
            return {"escalate": True}
        target = contextual.get("target")
        if target not in self.valid_targets:
            return {"escalate": True}
        return {"validated": True, "target": target, "ring": _RING_NAME}

    def tick(self, peer_a, peer_b):
        with self._lock:
            self._last_tick += 1
            return {"tick": self._last_tick, "ring": _RING_NAME}

    def ring_alive(self):
        return self._alive

    def ring_status(self):
        return {
            "alive":      self._alive,
            "last_tick":  self._last_tick,
            "ring":       _RING_NAME,
        }

    def broadcast(self, ball):
        return {"peer": self.ident, "status": "ok", "ring": _RING_NAME}

    def heartbeat(self):
        return {
            "peer":       self.ident,
            "alive":      self._alive,
            "last_tick":  self._last_tick,
            "ring":       _RING_NAME,
        }


# ============================================================================
# RING — convenience wrapper (all three together)
# ============================================================================

class Ring:
    """
    One coms ring — Franken2 + Freewheeling + Propcoms together.
    Frank imports this. The ring does the work.
    """
    def __init__(self):
        self.franken2     = Franken2()
        self.freewheeling = Freewheeling()
        self.propcoms     = Propcoms()
        self.name         = _RING_NAME
        log.info(f"Ring {_RING_NAME} initialized")

    def status(self) -> dict:
        return {
            "ring":      self.name,
            "franken2":  self.franken2.heartbeat(),
            "freewheel": self.freewheeling.status(),
            "propcoms":  self.propcoms.ring_status(),
        }


# ── Singleton ─────────────────────────────────────────────────────────────────
_ring: Ring = None

def get_ring() -> Ring:
    global _ring
    if _ring is None:
        _ring = Ring()
    return _ring


# ── Standalone test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(name)s] %(message)s")
    print(f"\n🔥 helix_api.py — {_RING_NAME}")
    ring = get_ring()

    # Test warm storage
    ring.freewheeling.store_warm("test:warm", {"data": "hello from warm", "ring": _RING_NAME})
    result = ring.freewheeling.load_warm("test:warm")
    print(f"  warm store/load: {result}")

    # Test cold storage
    ring.freewheeling.store_cold("test:cold", {"data": "hello from cold", "ring": _RING_NAME})
    result = ring.freewheeling.load_cold("test:cold")
    print(f"  cold store/load: {result}")

    # Test eviction
    ring.freewheeling.store_warm("test:evict", {"data": "moving to cold"})
    ring.freewheeling.evict_to_cold("test:evict")
    result = ring.freewheeling.load_cold("test:evict")
    print(f"  evict warm→cold: {result}")

    # Status
    import json as _json
    print(f"\n  Status:\n{_json.dumps(ring.status(), indent=2)}")
    print(f"\n✅ {_RING_NAME} helix_api ready.")
