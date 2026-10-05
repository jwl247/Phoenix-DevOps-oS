#!/usr/bin/env python3
"""
paging_kernel_helix.py — the paging manager, wired to the KERNEL Helix (dm-helix)
Phoenix DevOps OS | jwl247 | GPL v3

He clears and feeds her (JW). Two powers, both read from HER, nothing hard-coded:

  DOPPELGANGERS  — paging_helix.HelixPager, unchanged: he watches her tiers and load,
                   and when Strand B fills (velocity, not thresholds) he grows her
                   budget with a self-expiring Doppelganger; calm again, it retires.
                   Driven here through KernelHelix (dmsetup status / message b_budget).

  PREDICTIVE FETCH — he reads what she was asked for and didn't have (her miss ring,
                   `misses <since>`), finds the patterns in it — streams moving forward,
                   regular strides — measures how fast each moves, and feeds her ahead of
                   it (`prefetch`). How far ahead is learned, per stream: still missing at
                   the front → reach further; prefetched blocks going unused → pull back.

    sudo python3 paging_kernel_helix.py --dm helix0 --b-file /path/strandB.img [--interval 0.25]

Needs root (dmsetup). Every decision is logged (journal / stdout) — "what did you just do"
always has an answer.
"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paging_helix import HelixPager, MB  # noqa: E402

log = logging.getLogger("paging_kernel_helix")
BLOCK = 4096
SECTORS_PER_BLOCK = 8


# ---------------------------------------------------------------------------
# Her, as the pager sees her
# ---------------------------------------------------------------------------

class KernelHelix:
    """Speaks to a dm-helix target through dmsetup. Same face HelixPager expects."""

    def __init__(self, dm_name: str, b_file: Optional[str] = None):
        self.dm = dm_name
        self.b_dir = str(Path(b_file).parent) if b_file else "/"
        st = self._status()
        self.b_base = st["b_base_slots"] * BLOCK
        self._pressure_fn = None

    def _run(self, *args: str) -> str:
        return subprocess.run(["dmsetup", *args], capture_output=True, text=True, check=True).stdout.strip()

    def message(self, *words) -> str:
        return self._run("message", self.dm, "0", *[str(w) for w in words])

    def _status(self) -> Dict:
        words = self._run("status", self.dm).split()
        v: Dict[str, float] = {}
        for i, w in enumerate(words[:-1]):
            nxt = words[i + 1]
            try:
                v.setdefault(w, float(nxt))
            except ValueError:
                pass
        table = self._run("table", self.dm).split()     # 0 len helix origin ram [B b_mb] [warm_write]
        b_mb = int(table[6]) if len(table) >= 7 and table[6].isdigit() else 0
        i = words.index("slots") if "slots" in words else -1
        return {
            "heat": v.get("heat", 0.0),
            "b_slots": int(words[i + 1]) if i >= 0 else 0,
            "b_used": int(words[i + 3]) if i >= 0 else 0,
            "b_evictions": int(v.get("b_evictions", 0)),
            "b_cap_slots": int(v.get("b_cap_slots", 0)),
            "b_base_slots": b_mb * MB // BLOCK,
            "hits": int(v.get("hits", 0)), "misses": int(v.get("misses", 0)),
            "b_hits": int(v.get("b_hits", 0)), "warmed": int(v.get("warmed", 0)),
            "warm_dropped": int(v.get("warm_dropped", 0)),
        }

    # -- the face paging_helix.HelixPager uses ---------------------------------
    def set_pressure_source(self, fn):
        self._pressure_fn = fn          # the kernel Helix reads memory pressure herself; kept for parity

    def get_stats(self) -> Dict:
        s = self._status()
        return {
            "cold_usage_mb": s["b_used"] * BLOCK / MB,
            "strand_b_budget_mb": s["b_slots"] * BLOCK / MB,
            "refused": s["b_evictions"],                # B full → she throws her oldest away
            "dandelion": {"load": s["heat"]},
            "raw": s,
        }

    @property
    def b_budget(self) -> int:
        return self._status()["b_slots"] * BLOCK

    def set_strand_b_budget(self, mb: int) -> int:
        self.message("b_budget", int(mb))
        return self.b_budget // MB

    def misses(self, since: int) -> Tuple[int, int, List[Tuple[int, int]]]:
        """(sequence now, lost, [(first_block, blocks), ...]) since `since`."""
        w = self.message("misses", since).split()
        seq, lost = int(w[1]), int(w[3])
        runs = []
        for t in w[5:]:
            if ":" in t:
                a, b = t.split(":")
                runs.append((int(a), int(b)))
        return seq, lost, runs

    def prefetch(self, first_block: int, blocks: int) -> None:
        self.message("prefetch", first_block * SECTORS_PER_BLOCK, blocks * SECTORS_PER_BLOCK)


# ---------------------------------------------------------------------------
# His edge: predictive fetch, learned from her misses
# ---------------------------------------------------------------------------

@dataclass
class Stream:
    head: int                  # end (exclusive) of the furthest ask she missed
    last_first: int            # start of the previous ask
    run: int                   # blocks per ask
    stride: int                # distance between asks (== run for a plain forward stream)
    seen_t: float              # when she last missed on it
    rate: float = 0.0          # blocks/s, measured from her misses
    confirmed: int = 0         # asks that matched (evidence before he acts)
    lead_s: float = 0.5        # how far ahead, in seconds of the stream's own speed — learned
    fed_to: int = 0            # prefetched up to (exclusive)


class PredictiveFetch:
    """
    When his feeding works she stops missing, so he can't see the stream any more.
    So a confirmed stream COASTS: silence is read as "still moving at its speed" and he
    keeps feeding ahead. A miss inside or past what he fed means he was late: the
    stream's lead grows. Silence past the coast window: the stream is dropped.
    """

    def __init__(self, helix: KernelHelix, interval: float = 0.25):
        self.helix = helix
        self.interval = interval
        self.streams: List[Stream] = []
        self.cursor = 0
        self.fed_blocks = 0
        self.decisions = 0
        self.last_lost = 0
        self._stop = threading.Event()
        self._t: Optional[threading.Thread] = None

    @staticmethod
    def coast_s(s: Stream) -> float:
        return max(2.0, 8 * s.lead_s)

    def observe(self, runs: List[Tuple[int, int]], now: float) -> None:
        for first, n in runs:
            s = next((x for x in self.streams
                      if x.head - 4 * x.run - 16 <= first <= max(x.head, x.fed_to) + 4 * x.run + 16), None)
            if s is None:
                self.streams.append(Stream(head=first + n, last_first=first, run=n, stride=n, seen_t=now))
                continue
            step = first - s.last_first
            dt = now - s.seen_t
            if step > 0:
                s.stride = step
                if dt > 1e-3:
                    inst = step / dt
                    s.rate = inst if not s.rate else 0.7 * s.rate + 0.3 * inst
            if s.fed_to:                          # missed although he was feeding it: he was late
                s.lead_s = min(s.lead_s * 1.25, 10.0)
            s.last_first, s.run, s.seen_t = first, n, now
            s.head = max(s.head, first + n)
            s.confirmed += 1
        self.streams = [s for s in self.streams if now - s.seen_t < self.coast_s(s)][-64:]

    def feed(self, now: float) -> None:
        for s in self.streams:
            if s.confirmed < 2 or s.rate <= 0:    # a pattern needs evidence first
                continue
            est_head = s.head + int(s.rate * (now - s.seen_t))      # silent = being served = moving
            end = est_head + int(s.rate * s.lead_s) + s.run
            start = max(s.fed_to, s.head)
            if end <= start:
                continue
            if s.stride <= s.run:                 # plain forward stream: one span
                self.helix.prefetch(start, end - start)
            else:                                 # strided: feed only the asks it will make
                b = s.last_first + s.stride
                while b < end:
                    if b + s.run > start:
                        self.helix.prefetch(b, s.run)
                    b += s.stride
            self.fed_blocks += end - start
            self.decisions += 1
            s.fed_to = end

    def cycle(self) -> None:
        seq, lost, runs = self.helix.misses(self.cursor)
        self.cursor = seq
        if lost:
            self.last_lost += lost
            log.warning("[FETCH] fell behind her miss ring: %d misses unseen", lost)
        now = time.monotonic()
        self.observe(runs, now)
        self.feed(now)

    def _run(self):
        self.cursor = self.helix.misses(0)[0]          # start from now
        while not self._stop.wait(self.interval):
            try:
                self.cycle()
            except subprocess.CalledProcessError as e:
                log.error("[FETCH] dmsetup failed: %s", e)

    def start(self):
        self._t = threading.Thread(target=self._run, name="helix-predictive-fetch", daemon=True)
        self._t.start()

    def stop(self):
        self._stop.set()
        if self._t:
            self._t.join(timeout=5)

    def status(self) -> Dict:
        return {"streams": len(self.streams), "fed_blocks": self.fed_blocks, "decisions": self.decisions,
                "lost": self.last_lost,
                "leads_s": [round(s.lead_s, 2) for s in self.streams if s.confirmed >= 2][:8]}


def linux_memory() -> Dict[str, float]:
    m = {}
    with open("/proc/meminfo") as f:
        for line in f:
            k, v = line.split(":")
            m[k] = float(v.split()[0])
    ram = 1 - m.get("MemAvailable", 0) / max(m.get("MemTotal", 1), 1)
    commit = m.get("Committed_AS", 0) / max(m.get("CommitLimit", 1), 1)
    return {"ram": ram, "commit": min(commit, 1.0)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="The paging manager, driving the kernel Helix")
    ap.add_argument("--dm", required=True, help="device-mapper name of her target, e.g. helix0")
    ap.add_argument("--b-file", help="Strand B image/device path (for disk-room checks)")
    ap.add_argument("--interval", type=float, default=0.25, help="predictive fetch cycle, seconds")
    ap.add_argument("--pager-interval", type=float, default=5.0, help="Doppelganger cycle, seconds")
    ap.add_argument("--no-doppelgangers", action="store_true")
    ap.add_argument("--no-fetch", action="store_true")
    ap.add_argument("--seconds", type=float, default=0, help="run this long then report (0 = forever)")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    import signal
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    helix = KernelHelix(a.dm, a.b_file)
    pager = fetch = None
    if not a.no_doppelgangers and helix.b_base:
        # her real ceiling is the Strand B DEVICE, not the free space of the folder it sits in
        cap_mb = helix._status()["b_cap_slots"] * BLOCK // MB
        pager = HelixPager(helix, linux_memory, interval=a.pager_interval, max_b_mb=cap_mb)
        pager.start()
    if not a.no_fetch:
        fetch = PredictiveFetch(helix, a.interval)
        fetch.start()
    t0 = time.time()
    while not stop.is_set() and (not a.seconds or time.time() - t0 < a.seconds):
        stop.wait(0.5)
    if fetch:
        fetch.stop()
        log.info("[FETCH] %s", fetch.status())
    if pager:
        pager.stop()
        log.info("[PAGER] %s", {k: v for k, v in pager.status().items() if k != "decisions"})
    return 0


if __name__ == "__main__":
    sys.exit(main())
