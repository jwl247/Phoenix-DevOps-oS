#!/usr/bin/env python3
"""
paging_helix.py — the paging manager, wired to Helix instead of the pagefile.
Phoenix DevOps OS | jwl247 | GPL v3

Runs on every OS (Windows first: paging_windows.py's pagefile commands need a
reboot to do anything, so they can't follow load). Two wires:

  LOAD  -> her Dandelion.
      He plugs himself in as her memory-pressure source. Pressure is the worse
      of physical RAM in use and commit charge (RAM + pagefile against the
      commit limit — where paging actually shows up on Windows). Her own rules
      then do the rest: load >= 0.5 heats her, tightens compression, and her
      tiered eviction runs (raw -> zlib 5 -> Strand B). He never touches her
      L1/L2/L3 budgets — those are her real config.

  HER TIERED EVICTION -> Doppelgangers.
      He watches her tiers each cycle (the PredictiveEngine idea from
      paging.py: velocity, not thresholds). When Strand B is filling toward
      full — or she has started refusing — he spawns a Doppelganger: a
      temporary, self-expiring extension of her Strand B budget, sized from
      how fast she is evicting, bounded by the free space on Strand B's own
      disk. When a Doppelganger expires and the pressure is gone and what she
      holds on B fits without it, it retires and the budget shrinks back.
      Never below her configured Strand B, never below what she already holds.

Every non-hold decision is logged and kept (last 50), so "what did you just
do" always has an inspectable answer (GET /kernel on the Genie control socket).
"""

import logging
import os
import shutil
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, asdict
from typing import Callable, Deque, Dict, List, Optional

log = logging.getLogger("paging_helix")

MB = 1024 * 1024

INTERVAL_S        = float(os.environ.get("PHOENIX_PAGER_INTERVAL", "5"))
WINDOW            = 12        # cycles of history for velocity (~1 min at 5 s)
GROW_AT           = 0.85      # Strand B fraction full that spawns a Doppelganger
ETA_GROW_S        = 120.0     # spawn when B is predicted full within this
DG_TTL_S          = 600.0     # a Doppelganger lives 10 min, renewed while needed
CALM_LOAD         = 0.5       # her Dandelion's own hot threshold
CALM_CYCLES       = 12        # this many calm cycles before a retirement
DISK_RESERVE_FRAC = 0.10      # never let Strand B's disk go below 10% free ...
DISK_RESERVE_MIN  = 20 * 1024 # ... or 20 GB, whichever is larger (MB)
DG_MIN_MB         = 1024


@dataclass
class Doppelganger:
    id:         str
    size_mb:    int
    created_at: float
    expires_at: float
    reason:     str


class HelixPager:
    def __init__(self, helix, memory_fn: Callable[[], Dict[str, float]],
                 interval: float = INTERVAL_S, max_b_mb: Optional[int] = None):
        self.helix     = helix
        self.memory_fn = memory_fn
        self.interval  = interval
        env_max = os.environ.get("PHOENIX_HELIX_B_MAX_MB")
        self.max_b_mb  = max_b_mb or (int(env_max) if env_max else None)
        self.dgs: List[Doppelganger] = []
        self.history: Deque[tuple] = deque(maxlen=WINDOW)
        self.decisions: Deque[dict] = deque(maxlen=50)
        self.last_mem: Dict[str, float] = {}
        self.pressure_now = 0.0
        self._calm = 0
        self._last_refused = 0
        self._last_blocked = 0.0
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    # ── LOAD wire ──────────────────────────────────────────────────────────
    def pressure(self) -> float:
        """Her memory-pressure source: max(RAM in use, commit charge)."""
        m = self.memory_fn()
        self.last_mem = m
        self.pressure_now = max(m.get("ram", 0.0), m.get("commit", 0.0))
        return self.pressure_now

    def attach(self):
        self.helix.set_pressure_source(self.pressure)
        log.info("  Paging manager  wired to Helix (load -> Dandelion, eviction -> Doppelgangers)")

    # ── Doppelgangers ─────────────────────────────────────────────────────
    def _b_ceiling_mb(self) -> int:
        """Most Strand B may grow to: what she holds now + usable free disk."""
        st = self.helix.get_stats()
        try:
            du = shutil.disk_usage(self.helix.b_dir)
            reserve = max(du.total * DISK_RESERVE_FRAC / MB, DISK_RESERVE_MIN)
            ceiling = st["cold_usage_mb"] + max(0.0, du.free / MB - reserve)
        except OSError:
            ceiling = st["strand_b_budget_mb"]
        if self.max_b_mb:
            ceiling = min(ceiling, self.max_b_mb)
        return int(ceiling)

    def _apply_budget(self) -> int:
        base = self.helix.b_base // MB
        want = base + sum(d.size_mb for d in self.dgs)
        return self.helix.set_strand_b_budget(want)

    def _spawn(self, size_mb: int, reason: str) -> Optional[Doppelganger]:
        cur = self.helix.b_budget // MB
        room = self._b_ceiling_mb() - cur
        size_mb = int(min(size_mb, room))
        if size_mb < DG_MIN_MB // 4:
            if time.time() - self._last_blocked >= 60:     # say it once a minute, not every cycle
                self._last_blocked = time.time()
                self._record("blocked", 0, f"{reason}; no disk room for a Doppelganger (ceiling {self._b_ceiling_mb()} MB)")
            return None
        now = time.time()
        dg = Doppelganger(id=uuid.uuid4().hex[:8], size_mb=size_mb, created_at=now,
                          expires_at=now + DG_TTL_S, reason=reason)
        self.dgs.append(dg)
        new = self._apply_budget()
        self._record("spawn", size_mb, f"{reason}; Doppelganger {dg.id} +{size_mb} MB -> Strand B {new} MB")
        return dg

    def _retire(self, dg: Doppelganger, reason: str):
        self.dgs.remove(dg)
        new = self._apply_budget()
        self._record("retire", dg.size_mb, f"{reason}; Doppelganger {dg.id} -{dg.size_mb} MB -> Strand B {new} MB")

    def _record(self, action: str, mb: int, why: str):
        d = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "action": action, "mb": mb, "why": why}
        self.decisions.append(d)
        (log.warning if action == "blocked" else log.info)("[PAGER] %s", why)

    # ── one cycle ─────────────────────────────────────────────────────────
    def cycle(self) -> str:
        with self._lock:
            st = self.helix.get_stats()
            now = time.time()
            b_used = st["cold_usage_mb"]
            b_budget = st["strand_b_budget_mb"]
            refused = st.get("refused", 0)
            load = st["dandelion"].get("load", self.pressure_now)
            self.history.append((now, b_used))

            vel = 0.0
            if len(self.history) >= 2:
                (t0, b0), (t1, b1) = self.history[0], self.history[-1]
                vel = (b1 - b0) / max(t1 - t0, 1e-6)          # MB/s into Strand B
            eta = (b_budget - b_used) / vel if vel > 0 else None
            frac = b_used / b_budget if b_budget else 0.0

            reason = None
            if refused > self._last_refused:
                reason = f"she refused {refused - self._last_refused} allocation(s)"
            elif frac >= GROW_AT:
                reason = f"Strand B {frac:.0%} full"
            elif eta is not None and eta < ETA_GROW_S:
                reason = f"Strand B full in ~{eta:.0f}s at {vel:.1f} MB/s"
            self._last_refused = refused

            if reason:
                self._calm = 0
                size = max(DG_MIN_MB, int(b_budget * 0.25), int(vel * DG_TTL_S))
                fresh = [d for d in self.dgs if d.expires_at > now]
                for d in fresh:                      # still needed: keep them alive
                    d.expires_at = now + DG_TTL_S
                self._spawn(size, reason)
                return "spawn"

            self._calm = self._calm + 1 if load < CALM_LOAD else 0
            for d in sorted(self.dgs, key=lambda x: x.created_at, reverse=True):
                if d.expires_at > now or self._calm < CALM_CYCLES:
                    continue
                remaining = b_budget - d.size_mb
                if b_used <= remaining * 0.6:         # what she holds fits without it
                    self._retire(d, f"expired, calm {self._calm} cycles, B {b_used:.0f}/{remaining:.0f} MB without it")
                    return "retire"
                d.expires_at = now + DG_TTL_S        # still carrying her load: renew
            return "hold"

    # ── thread ────────────────────────────────────────────────────────────
    def _run(self):
        while not self._stop.wait(self.interval):
            try:
                self.cycle()
            except Exception as e:
                log.error("[PAGER] cycle error: %s", e)

    def start(self):
        self.attach()
        self._thread = threading.Thread(target=self._run, name="helix-pager", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self.helix.set_pressure_source(None)

    def status(self) -> dict:
        with self._lock:
            m = self.last_mem
            return {
                "pressure": round(self.pressure_now, 3),
                "ram": round(m.get("ram", 0.0), 3), "commit": round(m.get("commit", 0.0), 3),
                "strand_b_budget_mb": self.helix.b_budget // MB,
                "strand_b_base_mb": self.helix.b_base // MB,
                "strand_b_ceiling_mb": self._b_ceiling_mb(),
                "doppelgangers": [asdict(d) for d in self.dgs],
                "calm_cycles": self._calm,
                "decisions": list(self.decisions)[-10:],
            }


def clean_stale_strand_b(base: str, keep: str):
    """Strand B dirs left by a kernel that was killed (taskkill /F skips
    close()). Only helix-strandB-* dirs inside Helix's own Strand B base,
    never the live one."""
    try:
        for name in os.listdir(base):
            p = os.path.join(base, name)
            if name.startswith("helix-strandB-") and os.path.isdir(p) and os.path.abspath(p) != os.path.abspath(keep):
                shutil.rmtree(p, ignore_errors=True)
                log.info("  Helix Strand B  cleared stale %s", name)
    except OSError:
        pass
