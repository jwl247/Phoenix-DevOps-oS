"""
helix_predictive.py — Helix Predictive Prefetch Engine
CoPES / sector4/helix/

Helix watches both strands A and B together.
One pattern window across both engines — peer-optimized.
When A sees a sequence, B already knows about it.
She pulls data before it's asked for.
If she needs more room she requests another instance via ReplicaTarget.HELIX.
Frank sets the window. She works within it.

Drop this into CoPES/src/kernel/ and import into helix.py:
    from helix_predictive import HelixPredictiveEngine

Wire it into Helix.__init__:
    self.predictive = HelixPredictiveEngine(self.engine_a, self.engine_b)

Wire it into Helix._handle_packet:
    self.predictive.observe(key, pkt.payload_a)
    prefetch_keys = self.predictive.get_prefetch_queue()

Authors: Jerry Leftwich + Jerilynn Leftwich
License: GPL v3
"""

import time
import threading
import zlib
from collections import deque, defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Set, TYPE_CHECKING
from enum import Enum

if TYPE_CHECKING:
    from helix import HelixEngine


# ── Access pattern types ──────────────────────────────────────────────────────

class Pattern(Enum):
    SEQUENTIAL  = "sequential"   # keys arrive in a predictable sequence
    TEMPORAL    = "temporal"     # same key accessed repeatedly in bursts
    SPATIAL     = "spatial"      # nearby keys (hash proximity) accessed together
    RANDOM      = "random"       # no detectable pattern — don't prefetch
    CYCLIC      = "cyclic"       # pattern repeats on a timer


# ── Per-key temperature ───────────────────────────────────────────────────────

@dataclass
class KeyTemperature:
    """
    Thermodynamic model for one key.
    Heat rises on access. Cools over time.
    Prefetch when trending hot before peak.
    """
    key:          int
    heat:         float = 0.0
    last_access:  float = field(default_factory=time.monotonic)
    access_count: int   = 0
    pattern:      Pattern = Pattern.RANDOM

    # Heat constants
    HEAT_ON_ACCESS   = 25.0   # heat added per access
    COOL_RATE        = 0.15   # heat lost per second (passive cooling)
    PREFETCH_THRESHOLD = 40.0 # if trending up and above this → prefetch
    HOT_THRESHOLD    = 70.0   # considered hot — L1 candidate
    COLD_THRESHOLD   = 5.0    # considered cold — eviction candidate

    def access(self):
        now = time.monotonic()
        elapsed = now - self.last_access
        # Cool first, then heat
        self.heat = max(0.0, self.heat - self.COOL_RATE * elapsed)
        self.heat = min(100.0, self.heat + self.HEAT_ON_ACCESS)
        self.last_access = now
        self.access_count += 1

    def cool(self):
        now = time.monotonic()
        elapsed = now - self.last_access
        self.heat = max(0.0, self.heat - self.COOL_RATE * elapsed)
        self.last_access = now

    @property
    def is_hot(self) -> bool:
        return self.heat >= self.HOT_THRESHOLD

    @property
    def is_cold(self) -> bool:
        return self.heat <= self.COLD_THRESHOLD

    @property
    def trending_up(self) -> bool:
        return self.heat >= self.PREFETCH_THRESHOLD and self.access_count > 2


# ── Access event ─────────────────────────────────────────────────────────────

@dataclass
class AccessEvent:
    key:       int
    timestamp: float
    strand:    str    # "A" or "B"
    size:      int    # payload size in bytes


# ── Predictive prefetch engine ────────────────────────────────────────────────

class HelixPredictiveEngine:
    """
    Watches both strands A and B together.
    One pattern window — peer-optimized, same as the engines themselves.

    What she does:
    1. Observes every key that flows through either strand
    2. Tracks temperature (heat/cool thermodynamic model)
    3. Detects access patterns (sequential, temporal, spatial, cyclic)
    4. Builds a prefetch queue of what she thinks will be needed next
    5. Engines pull from that queue proactively — data is warm before asked

    What she does NOT do:
    - Write new imports (Frank's authority only)
    - Exceed the replication window Frank set
    - Prefetch when pattern is RANDOM (waste of cycles)
    - Evict — that's the tier manager's job
    """

    # Tuning
    HISTORY_WINDOW    = 64      # last N access events to analyze
    SEQUENCE_LOOKAHEAD = 4      # how many keys ahead to prefetch in a sequence
    TEMPORAL_BURST    = 3       # accesses within this many seconds = temporal burst
    SPATIAL_RADIUS    = 16      # hash proximity for spatial pattern detection
    CYCLE_MIN_REPEATS = 3       # minimum repeats to call it cyclic
    PREFETCH_MAX      = 8       # max keys in prefetch queue at once
    COOL_INTERVAL     = 5.0     # seconds between passive cooling sweeps

    def __init__(self, engine_a: "HelixEngine", engine_b: "HelixEngine"):
        self.engine_a = engine_a
        self.engine_b = engine_b

        # Access history — shared across both strands
        self._history: deque[AccessEvent] = deque(maxlen=self.HISTORY_WINDOW)

        # Per-key temperature
        self._temps: Dict[int, KeyTemperature] = {}

        # Sequence tracking — key → what typically comes next
        self._next_key: Dict[int, Dict[int, int]] = defaultdict(lambda: defaultdict(int))
        self._last_key: Optional[int] = None

        # Cyclic pattern tracking — key → list of inter-access intervals
        self._intervals: Dict[int, List[float]] = defaultdict(list)
        self._last_access_time: Dict[int, float] = {}

        # Prefetch queue — keys she thinks will be needed soon
        self._prefetch_queue: List[int] = []
        self._prefetched: Set[int] = set()  # already prefetched this cycle

        # Stats
        self.stats = {
            "observations":    0,
            "prefetch_hits":   0,   # key was prefetched, then actually accessed
            "prefetch_misses": 0,   # key was prefetched, never accessed (wasted)
            "patterns_detected": defaultdict(int),
        }

        self._lock = threading.Lock()

        # Start passive cooling thread
        self._alive = True
        self._cool_thread = threading.Thread(
            target=self._passive_cool_loop,
            daemon=True,
            name="helix-predictive-cool"
        )
        self._cool_thread.start()

    # ── Observation — called on every packet ──────────────────────────────────

    def observe(self, key: int, payload: bytes, strand: str = "A"):
        """
        Called every time a key flows through either strand.
        This is the learning input — she sees everything.
        """
        with self._lock:
            now = time.monotonic()
            self.stats["observations"] += 1

            # Record access event
            event = AccessEvent(key=key, timestamp=now, strand=strand, size=len(payload))
            self._history.append(event)

            # Update temperature
            if key not in self._temps:
                self._temps[key] = KeyTemperature(key=key)
            self._temps[key].access()

            # Track sequence — what came before this key?
            if self._last_key is not None and self._last_key != key:
                self._next_key[self._last_key][key] += 1
            self._last_key = key

            # Track intervals for cyclic detection
            if key in self._last_access_time:
                interval = now - self._last_access_time[key]
                self._intervals[key].append(interval)
                if len(self._intervals[key]) > 20:
                    self._intervals[key].pop(0)
            self._last_access_time[key] = now

            # Check prefetch hit
            if key in self._prefetched:
                self.stats["prefetch_hits"] += 1
                self._prefetched.discard(key)

            # Detect pattern and update prefetch queue
            pattern = self._detect_pattern(key, now)
            self._temps[key].pattern = pattern
            self.stats["patterns_detected"][pattern.value] += 1

            self._update_prefetch_queue(key, pattern, now)

    # ── Pattern detection ─────────────────────────────────────────────────────

    def _detect_pattern(self, key: int, now: float) -> Pattern:
        """
        Analyze recent history to classify this key's access pattern.
        Priority: CYCLIC > SEQUENTIAL > TEMPORAL > SPATIAL > RANDOM
        """
        # CYCLIC — does this key arrive on a regular interval?
        if self._is_cyclic(key):
            return Pattern.CYCLIC

        # SEQUENTIAL — does this key follow a predictable predecessor?
        if self._last_key is not None:
            predecessors = self._next_key.get(self._last_key, {})
            if key in predecessors and predecessors[key] >= 2:
                return Pattern.SEQUENTIAL

        # TEMPORAL — is this key being hit rapidly in a burst?
        recent = [e for e in self._history
                  if e.key == key and (now - e.timestamp) < self.TEMPORAL_BURST]
        if len(recent) >= 3:
            return Pattern.TEMPORAL

        # SPATIAL — are nearby keys (hash proximity) also being accessed?
        nearby = [e for e in self._history
                  if abs(e.key - key) <= self.SPATIAL_RADIUS and e.key != key]
        if len(nearby) >= 3:
            return Pattern.SPATIAL

        return Pattern.RANDOM

    def _is_cyclic(self, key: int) -> bool:
        """
        True if this key's access intervals are regular enough to predict.
        Regular = std deviation < 20% of mean interval.
        """
        intervals = self._intervals.get(key, [])
        if len(intervals) < self.CYCLE_MIN_REPEATS:
            return False
        mean = sum(intervals) / len(intervals)
        if mean < 0.1:  # too fast to be meaningful
            return False
        variance = sum((i - mean) ** 2 for i in intervals) / len(intervals)
        std = variance ** 0.5
        return (std / mean) < 0.20   # within 20% = regular enough

    # ── Prefetch queue ────────────────────────────────────────────────────────

    def _update_prefetch_queue(self, key: int, pattern: Pattern, now: float):
        """
        Based on detected pattern, decide what to prefetch next.
        She only prefetches when she's confident. RANDOM = don't bother.
        """
        if pattern == Pattern.RANDOM:
            return

        candidates = []

        if pattern == Pattern.SEQUENTIAL:
            # Prefetch the most likely next keys in sequence
            next_keys = self._next_key.get(key, {})
            sorted_next = sorted(next_keys.items(), key=lambda x: x[1], reverse=True)
            candidates = [k for k, _ in sorted_next[:self.SEQUENCE_LOOKAHEAD]]

        elif pattern == Pattern.TEMPORAL:
            # She'll be asked for this same key again — keep it hot
            candidates = [key]

        elif pattern == Pattern.SPATIAL:
            # Prefetch nearby keys that are trending hot
            candidates = [
                k for k, t in self._temps.items()
                if abs(k - key) <= self.SPATIAL_RADIUS
                and k != key
                and t.trending_up
            ][:self.SEQUENCE_LOOKAHEAD]

        elif pattern == Pattern.CYCLIC:
            # Prefetch this key slightly before its next expected arrival
            intervals = self._intervals.get(key, [])
            if intervals:
                mean_interval = sum(intervals) / len(intervals)
                # Schedule: she'll prefetch when 80% of interval has elapsed
                candidates = [key]  # self-referential — warm it before next hit

        # Add to queue, cap at max
        for c in candidates:
            if c not in self._prefetch_queue and len(self._prefetch_queue) < self.PREFETCH_MAX:
                self._prefetch_queue.append(c)
                self._prefetched.add(c)

    def get_prefetch_queue(self) -> List[int]:
        """
        Called by Helix after every observation.
        Returns keys she wants warmed up now.
        Caller passes these through the engines to promote to L1.
        Clears the queue — she'll rebuild it on next observation.
        """
        with self._lock:
            queue = list(self._prefetch_queue)
            self._prefetch_queue.clear()
            return queue

    # ── Passive cooling — thermodynamic decay ────────────────────────────────

    def _passive_cool_loop(self):
        """
        Background thread. Cools all tracked keys over time.
        Cold keys fall out of prefetch consideration automatically.
        She self-regulates — no manual eviction needed.
        """
        while self._alive:
            time.sleep(self.COOL_INTERVAL)
            with self._lock:
                cold_keys = []
                for key, temp in self._temps.items():
                    temp.cool()
                    if temp.is_cold and temp.access_count > 0:
                        cold_keys.append(key)
                # Drop very cold keys from tracking to save memory
                for key in cold_keys:
                    if self._temps[key].heat <= 1.0:
                        del self._temps[key]
                        self._next_key.pop(key, None)
                        self._intervals.pop(key, None)

    # ── Hot keys snapshot ─────────────────────────────────────────────────────

    def hot_keys(self) -> List[Tuple[int, float]]:
        """
        Returns (key, heat) pairs currently above HOT_THRESHOLD.
        Tier manager uses this to decide what stays in L1.
        """
        with self._lock:
            return sorted(
                [(k, t.heat) for k, t in self._temps.items() if t.is_hot],
                key=lambda x: x[1],
                reverse=True
            )

    def trending_keys(self) -> List[int]:
        """
        Keys that are trending up — good prefetch candidates.
        """
        with self._lock:
            return [k for k, t in self._temps.items() if t.trending_up]

    # ── Status ────────────────────────────────────────────────────────────────

    def status(self) -> dict:
        with self._lock:
            hit_rate = 0.0
            total = self.stats["prefetch_hits"] + self.stats["prefetch_misses"]
            if total > 0:
                hit_rate = self.stats["prefetch_hits"] / total

            return {
                "observations":       self.stats["observations"],
                "tracked_keys":       len(self._temps),
                "hot_keys":           len([t for t in self._temps.values() if t.is_hot]),
                "trending_keys":      len([t for t in self._temps.values() if t.trending_up]),
                "prefetch_hit_rate":  f"{hit_rate:.1%}",
                "prefetch_hits":      self.stats["prefetch_hits"],
                "prefetch_misses":    self.stats["prefetch_misses"],
                "queue_depth":        len(self._prefetch_queue),
                "patterns":           dict(self.stats["patterns_detected"]),
                "sequence_map_size":  len(self._next_key),
            }

    def shutdown(self):
        self._alive = False


# ── Integration instructions ──────────────────────────────────────────────────
#
# In CoPES/src/kernel/helix.py, add to Helix.__init__:
#
#   from helix_predictive import HelixPredictiveEngine
#   self.predictive = HelixPredictiveEngine(self.engine_a, self.engine_b)
#
# In Helix._handle_packet, after engines process:
#
#   key = hash(pkt.token_a1 + bytes([pkt.process_id & 0xFF]))
#   self.predictive.observe(key, pkt.payload_a, strand="A")
#   self.predictive.observe(key, pkt.payload_b, strand="B")
#
#   # Pull prefetch queue and warm those keys in both engines
#   for prefetch_key in self.predictive.get_prefetch_queue():
#       cached = self.engine_a._cache.get(prefetch_key)
#       if cached is not None:
#           self.engine_b._cache[prefetch_key] = cached  # warm B from A
#
# In Helix.status():
#   "predictive": self.predictive.status()
#
# In Helix.shutdown():
#   self.predictive.shutdown()
#
# In helix_complete_stack.py TierManager, wire hot_keys() to pin L1:
#   for key, heat in helix.predictive.hot_keys():
#       if key in self.l1:
#           self.l1[key].pinned = True  # don't evict hot predicted keys
#
# ─────────────────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    import sys

    # Minimal stub engines for standalone test
    class StubEngine:
        def __init__(self, name):
            self.name = name
            self._cache = {}
            self._ops = 0
        def set_peer(self, peer): self.peer = peer
        def process(self, key, data):
            self._ops += 1
            self._cache[key] = data
            return data

    print("🧬 Helix Predictive Engine — standalone test")
    print()

    a = StubEngine("A"); b = StubEngine("B")
    a.set_peer(b); b.set_peer(a)
    engine = HelixPredictiveEngine(a, b)

    # Simulate sequential pattern
    print("[ TEST 1 ] Sequential pattern — keys 1→2→3→4 repeating")
    sequence = [1, 2, 3, 4, 1, 2, 3, 4, 1, 2, 3, 4]
    for k in sequence:
        engine.observe(k, b"payload", strand="A")
        queue = engine.get_prefetch_queue()
        if queue:
            print(f"  key={k} → prefetch queue: {queue}")
    print()

    # Simulate temporal burst
    print("[ TEST 2 ] Temporal burst — key 99 hit 5 times fast")
    for _ in range(5):
        engine.observe(99, b"hot data", strand="B")
    queue = engine.get_prefetch_queue()
    print(f"  prefetch queue after burst: {queue}")
    print()

    # Simulate cyclic pattern
    print("[ TEST 3 ] Cyclic pattern — key 42 every ~0.05s")
    for _ in range(6):
        engine.observe(42, b"cyclic data", strand="A")
        time.sleep(0.05)
    queue = engine.get_prefetch_queue()
    print(f"  prefetch queue after cyclic: {queue}")
    print()

    print("[ STATUS ]")
    s = engine.status()
    for k, v in s.items():
        print(f"  {k}: {v}")

    print()
    print("[ HOT KEYS ]", engine.hot_keys()[:5])
    print("[ TRENDING ]", engine.trending_keys()[:5])
    print()
    print("✅ Predictive engine ready.")
    engine.shutdown()
