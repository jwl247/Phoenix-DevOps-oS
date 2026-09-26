"""
test_helix_vram.py - correctness suite for the userspace Helix (helix_vram.py).

    python -m pytest sector1/helix/test_helix_vram.py -q
    python sector1/helix/test_helix_vram.py          # no pytest needed

Runs standalone (use_kernel=False) so it passes on any box; the kernel-linked
path is exercised on a machine with helix.ko loaded (see the Compaq notes).
"""
import os
import random
import sys
import tempfile
import threading
import time
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helix_vram as hv  # noqa: E402


def mk(**kw):
    kw.setdefault("autostart", False)
    kw.setdefault("use_kernel", False)
    kw.setdefault("strand_b_dir", tempfile.mkdtemp(prefix="hvtest-"))
    return hv.HelixMemoryManager(**kw)


def payload(i, n=2048):
    rnd = random.Random(i)
    if i % 3 == 0:                                   # incompressible
        return bytes(rnd.getrandbits(8) for _ in range(n))
    return (f"block {i} " * (n // 8)).encode()[:n]   # compressible


def test_no_silent_loss_under_spill():
    m = mk(max_hot_mb=0.5, max_warm_mb=0.5, max_cold_mb=1, strand_b_mb=64)
    try:
        for i in range(3000):
            m.allocate(f"k{i}", payload(i))
        s = m.get_stats()
        assert s["cold_blocks"] > 0, "nothing reached Strand B"
        assert s["warm_blocks"] > 0, "nothing was compressed"
        for i in range(3000):
            assert m.read(f"k{i}") == payload(i), f"k{i} lost or corrupted"
        assert m.stats["zfail"] == 0
    finally:
        m.close()


def test_her_format_is_zlib5():
    m = mk()
    try:
        data = b"helix " * 2000
        m.allocate("z", data)
        ln = m._lane_of("z")
        with ln.lock:
            m._compress(ln, ln.blocks["z"])
            assert ln.blocks["z"].z == zlib.compress(data, 5)
        assert m.read("z") == data
    finally:
        m.close()


def test_rung_zero_copy_and_write_invalidates():
    m = mk()
    try:
        m.allocate("r", b"old" * 1000)
        ln = m._lane_of("r")
        with ln.lock:
            m._to_strand_b(ln, ln.blocks["r"])
        old_path = ln.blocks["r"].b_path
        assert os.path.exists(old_path)
        assert m.read("r") == b"old" * 1000             # back from B, rung kept
        with ln.lock:
            m._to_strand_b(ln, ln.blocks["r"])           # clean rung: zero copy
        assert m.stats["b_zero_copy"] == 1
        m.write("r", b"new" * 1000)                       # new version drops the rung
        assert not os.path.exists(old_path)
        with ln.lock:
            m._to_strand_b(ln, ln.blocks["r"])
        assert m.read("r") == b"new" * 1000
    finally:
        m.close()


def test_free_removes_strand_b_copy():
    m = mk()
    try:
        m.allocate("f", b"x" * 5000)
        ln = m._lane_of("f")
        with ln.lock:
            m._to_strand_b(ln, ln.blocks["f"])
        path = ln.blocks["f"].b_path
        assert m.free("f") and not os.path.exists(path)
        assert m.read("f") is None
        assert m._totals() == (0, 0, 0)
    finally:
        m.close()


def test_full_refuses_loudly_and_keeps_old_data():
    m = mk(max_hot_mb=0.25, max_warm_mb=0, max_cold_mb=0.25, strand_b_mb=0.5)
    try:
        stored = []
        try:
            for i in range(10000):
                m.allocate(f"k{i}", os.urandom(4096))
                stored.append(i)
        except hv.HelixFullError:
            pass
        else:
            raise AssertionError("never refused")
        assert m.stats["refused"] >= 1
        for i in stored:
            assert m.read(f"k{i}") is not None, f"k{i} dropped silently"
    finally:
        m.close()


def test_dandelion_heats_under_load_and_cools():
    m = mk()
    try:
        m._mem_pressure = lambda: 0.0
        for _ in range(8):
            m._ops += 50000                  # busy ticks: at her calibrated peak
            t = m.tick(1.0)
        assert m.heat > 0.5 and t["state"] in ("hot", "surging") and m.compression < 1.0
        for _ in range(40):
            t = m.tick(1.0)                  # idle
        assert m.heat == 0.0 and t["state"] == "cold" and m.compression == 1.0
    finally:
        m.close()


def test_she_cools_herself_with_data():
    m = mk()
    try:
        m._mem_pressure = lambda: 0.0
        for i in range(400):
            m.allocate(f"c{i}", b"cool data " * 200)
        for blk in (b for ln in m.lanes for b in ln.blocks.values()):
            blk.last -= 1000                 # everything cold (idle > 300 s)
            blk.win_hits = 0
        m.heat, m.compression, m.state = 0.9, 0.3, "surging"
        m._ops += 50000
        m._peak = 50000
        t = m.tick(1.0)
        assert t["freed"] > 0
        # load alone would add heat; data relief must have pulled it back down
        assert m.heat < 0.9 + t["load"] / 10
        assert m.stats["cooled_bytes"] > 0
    finally:
        m.close()


def test_prediction_protects_blocks_due_back():
    m = mk()
    try:
        m.allocate("due", b"d" * 8192)
        blk = m._lane_of("due").blocks["due"]
        blk.interval = 1.0
        blk.last = time.monotonic() - 0.5    # predicted back in ~0.5 s
        assert blk.due_soon()
        m.raw_budget = 0
        m._make_room()
        assert blk.raw is not None, "relieved a block that was due back"
    finally:
        m.close()


def test_temperatures_follow_access():
    m = mk()
    try:
        m.allocate("t", b"t")
        blk = m._lane_of("t").blocks["t"]
        assert blk.temp() == hv.Temp.COLD
        for _ in range(12):
            m.read("t")
        assert blk.temp() == hv.Temp.BLAZING
    finally:
        m.close()


def test_concurrent_lanes():
    m = mk(max_hot_mb=1, max_warm_mb=1, max_cold_mb=1, strand_b_mb=128)
    errors = []

    def worker(w):
        try:
            for i in range(400):
                k = f"w{w}-{i}"
                m.allocate(k, payload(w * 1000 + i, 1024))
                if i % 7 == 0:
                    assert m.read(k) == payload(w * 1000 + i, 1024)
            for i in range(400):
                assert m.read(f"w{w}-{i}") == payload(w * 1000 + i, 1024)
        except Exception as e:   # noqa: BLE001
            errors.append(repr(e))

    try:
        ts = [threading.Thread(target=worker, args=(w,)) for w in range(8)]
        for t in ts:
            t.start()
        m2 = threading.Thread(target=lambda: [m.tick(0.05) for _ in range(40)])
        m2.start()
        for t in ts:
            t.join()
        m2.join()
        assert not errors, errors[:3]
    finally:
        m.close()


def test_paging_feed_shape():
    m = mk()
    try:
        m.allocate("p", b"p" * 100)
        snap = m.get_tier_snapshot()
        for k in ("timestamp", "hot_mb", "warm_mb", "cold_mb", "frozen_mb", "hit_rate",
                  "promotions", "demotions", "evictions"):
            assert k in snap
    finally:
        m.close()


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            t0 = time.perf_counter_ns()
            try:
                fn()
                print(f"  ok   {name}  ({(time.perf_counter_ns() - t0) / 1e6:.1f} ms)")
            except Exception as e:   # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {e!r}")
    print(f"== {fails} failure(s)")
    sys.exit(fails)
