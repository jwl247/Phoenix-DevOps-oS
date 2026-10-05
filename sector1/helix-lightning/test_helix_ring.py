#!/usr/bin/env python3
"""
test_helix_ring.py — the event ring loses nothing, across threads AND processes
Phoenix DevOps OS | jwl247 | GPL v3
    python sector1/helix-lightning/test_helix_ring.py
"""

from __future__ import annotations

import json
import multiprocessing as mp
import shutil
import sys
import tempfile
import threading
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from helix_ring import HelixRing, Cursor, RingFrank  # noqa: E402


def _producer(path: str, who: int, n: int) -> None:
    ring = HelixRing(Path(path))
    for i in range(n):
        ring.publish(5, json.dumps({"who": who, "i": i}).encode())
    ring.close()


class TestRing(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="helix_ring_"))
        self.path = self.tmp / "events.ring"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_burst_before_any_read_loses_nothing(self):
        """The exact failure of the slot bus: three events, one read."""
        ring = HelixRing(self.path)
        cur = ring.cursor_at_end()
        for e in ("enlistment", "wounded", "KIA"):
            ring.publish(5, json.dumps({"event": e}).encode())
        got = [json.loads(e.payload)["event"] for e in ring.read(cur)]
        self.assertEqual(got, ["enlistment", "wounded", "KIA"])
        self.assertEqual(cur.missed, 0)

    def test_readers_are_independent_and_nothing_is_cleared(self):
        ring = HelixRing(self.path)
        a, b = ring.cursor_at_end(), ring.cursor_at_end()
        for i in range(5):
            ring.publish(5, bytes([i]))
        self.assertEqual(len(ring.read(a)), 5)
        self.assertEqual(len(ring.read(b)), 5)                 # b still sees all of them
        self.assertEqual(ring.read(a), [])

    def test_many_threads_no_loss_no_duplicates(self):
        ring = HelixRing(self.path)
        cur = ring.cursor_at_end()
        threads = [threading.Thread(target=lambda w=w: [ring.publish(5, f"{w}:{i}".encode()) for i in range(500)])
                   for w in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        got = [e.payload.decode() for e in ring.read(cur, limit=100_000)]
        self.assertEqual(len(got), 4000)
        self.assertEqual(len(set(got)), 4000)
        self.assertEqual([e for e in got if e.startswith("3:")], [f"3:{i}" for i in range(500)])   # per-writer order

    def test_many_processes_no_loss(self):
        ring = HelixRing(self.path)
        cur = ring.cursor_at_end()
        procs = [mp.Process(target=_producer, args=(str(self.path), w, 300)) for w in range(4)]
        for p in procs:
            p.start()
        for p in procs:
            p.join(60)
            self.assertEqual(p.exitcode, 0)
        events = ring.read(cur, limit=100_000)
        got = {(json.loads(e.payload)["who"], json.loads(e.payload)["i"]) for e in events}
        self.assertEqual(len(events), 1200)
        self.assertEqual(len(got), 1200)
        self.assertEqual(sorted(e.seq for e in events), list(range(events[0].seq, events[0].seq + 1200)))

    def test_wrap_around_keeps_order(self):
        ring = HelixRing(self.path, capacity=4096)
        cur = ring.cursor_at_end()
        seen = []
        for i in range(300):                                   # many laps, reader keeps up
            ring.publish(5, f"e{i}".encode() * 3)
            seen += [e.payload for e in ring.read(cur)]
        self.assertEqual(seen, [f"e{i}".encode() * 3 for i in range(300)])
        self.assertEqual(cur.missed, 0)

    def test_slow_reader_is_told_what_it_missed(self):
        ring = HelixRing(self.path, capacity=4096)
        cur = ring.cursor_at_end()
        for i in range(1000):                                  # far more than 4 KiB
            ring.publish(5, b"x" * 40)
        self.assertEqual(ring.read(cur), [])
        self.assertEqual(cur.missed, 1000)                     # loud, exact, never silent
        ring.publish(5, b"after")
        self.assertEqual([e.payload for e in ring.read(cur)], [b"after"])

    def test_oversized_event_refused(self):
        ring = HelixRing(self.path, capacity=4096)
        with self.assertRaises(ValueError):
            ring.publish(5, b"x" * 2000)

    def test_ring_survives_reopen(self):
        HelixRing(self.path).publish(5, b"persisted")
        ring = HelixRing(self.path)
        self.assertEqual(ring.stats()["events"], 1)
        self.assertEqual(ring.read(Cursor())[0].payload, b"persisted")

    def test_ringfrank_is_a_drop_in_for_write_stage(self):
        ring = HelixRing(self.path)
        frank = RingFrank(ring)
        cur = ring.cursor_at_end()
        frank.bus.write_stage(4, b"one")
        frank.bus.write_stage(4, b"two")                       # the slot bus would lose "one"
        self.assertEqual([(e.channel, e.payload) for e in ring.read(cur)], [(5, b"one"), (5, b"two")])


if __name__ == "__main__":
    mp.freeze_support()
    unittest.main(verbosity=1)
