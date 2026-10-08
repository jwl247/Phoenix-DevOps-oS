#!/usr/bin/env python3
"""
bench_ring.py — step 0 of docs/plans/ring-build-plan.md: the BASELINE of today's ring, before anything changes.
Phoenix DevOps OS | SECTOR4 | jwl247 | GPL v3

Runs the real ring (rebound.py + its members, unchanged) in a SCRATCH home — PHOENIX_RING_HOME points every
ring (coms4 and the coms3 it escalates to) at a temp folder, so nothing touches a breach_coms drive — then:

  1. IDLE (--idle-secs): CPU % and file writes/s of rebound + all members with no work at all.
  2. ONE AT A TIME (--single): drop one ball into doors/in, wait until it reaches doors/done, repeat.
     That is the pure in -> done time of one ball through franken -> freewheeling -> propcoms.
  3. BURST (--burst): drop N balls at once; time until the last one is accounted for = throughput.

Every ball is accounted for: done, escalated (sent to the next ring's doors/in), breach, or MISSING.
Times come from this script's own clock (the ring's trail stamps are whole seconds only).

    python bench_ring.py                  # defaults: 15 s idle, 20 single, 500 burst
    python bench_ring.py --keep           # keep the scratch home afterwards to look at it
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

try:
    import psutil
except ImportError:
    sys.exit("psutil is needed: python -m pip install psutil")

RING_DIR = Path(__file__).resolve().parent
RING = json.loads((RING_DIR / "ring.json").read_text(encoding="utf-8"))
NAME, NEXT = RING["ring"], RING.get("next")
TEAM = json.loads((RING_DIR / "team.json").read_text(encoding="utf-8"))["members"]


def ring_procs(root):
    try:
        return [root] + root.children(recursive=True)
    except psutil.NoSuchProcess:
        return []


def sample(root, secs):
    """CPU % (sum over the ring's processes, 100 = one full core) and file write ops/s over secs."""
    procs = ring_procs(root)
    for p in procs:
        try: p.cpu_percent(None)
        except psutil.Error: pass
    w0 = 0
    for p in procs:
        try: w0 += p.io_counters().write_count
        except psutil.Error: pass
    time.sleep(secs)
    cpu = w1 = 0
    for p in procs:
        try:
            cpu += p.cpu_percent(None)
            w1 += p.io_counters().write_count
        except psutil.Error: pass
    return round(cpu, 1), round((w1 - w0) / secs, 1), len(procs)


def put(dirp, ball):
    tmp = dirp / f"{ball['id']}.json.tmp"
    tmp.write_text(json.dumps(ball), encoding="utf-8")
    os.replace(tmp, dirp / f"{ball['id']}.json")


def where(home, next_home, bid):
    if (home / "doors" / "done" / f"{bid}.json").exists():
        return "done"
    if next_home and (next_home / "doors" / "in" / f"{bid}.json").exists():
        return "escalated"
    if (home / "breach" / "escalated" / f"{bid}.json").exists() or (home / "breach" / f"bad_{bid}.json").exists():
        return "breach"
    return None


def pct(xs, q):
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int(q * len(xs)))], 1) if xs else None


def main():
    ap = argparse.ArgumentParser(description="baseline of today's ring (step 0)")
    ap.add_argument("--idle-secs", type=float, default=15)
    ap.add_argument("--single", type=int, default=20)
    ap.add_argument("--burst", type=int, default=500)
    ap.add_argument("--timeout", type=float, default=120, help="give up on a ball / the burst after this many s")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--out", default=str(RING_DIR / f"bench_ring-{time.strftime('%Y%m%d-%H%M%S')}.json"))
    a = ap.parse_args()

    scratch = Path(tempfile.mkdtemp(prefix="ring_bench_"))
    env = {**os.environ, "PHOENIX_RING_HOME": str(scratch)}
    for k in list(env):
        if k.startswith("PHOENIX_RING_HOME_"):
            del env[k]                                  # nothing may redirect a ring onto a real drive
    home, next_home = scratch / NAME, (scratch / NEXT if NEXT else None)
    print(f"scratch ring home: {scratch}")
    log = open(scratch / "rebound.out", "w", encoding="utf-8")
    proc = subprocess.Popen([sys.executable, str(RING_DIR / "rebound.py")], cwd=str(RING_DIR), env=env,
                            stdout=log, stderr=subprocess.STDOUT)
    root = psutil.Process(proc.pid)
    res = {"ring": NAME, "platform": sys.platform, "python": sys.version.split()[0], "scratch": str(scratch)}
    try:
        # wait for every member to report once
        t0 = time.time()
        status = home / "status"
        while time.time() - t0 < 90:
            have = {p.stem for p in status.glob("*.json")} if status.exists() else set()
            if set(TEAM) <= have:
                break
            time.sleep(0.5)
        states = {}
        for n in TEAM:
            try: states[n] = json.loads((status / f"{n}.json").read_text(encoding="utf-8")).get("state")
            except (OSError, ValueError): states[n] = "no status"
        res["startup_s"] = round(time.time() - t0, 1)
        res["members"] = states
        print(f"members after {res['startup_s']} s: {states}")
        din = home / "doors" / "in"
        din.mkdir(parents=True, exist_ok=True)

        cpu, wps, n = sample(root, a.idle_secs)
        res["idle"] = {"processes": n, "cpu_percent": cpu, "file_writes_per_s": wps, "seconds": a.idle_secs}
        print(f"idle: {n} processes, CPU {cpu}% (100 = one core), {wps} file writes/s")

        single, single_where = [], {}
        for i in range(a.single):
            bid = f"bench_s{i:04d}"
            s = time.perf_counter()
            put(din, {"id": bid, "type": "bench", "payload": {"n": i}})
            w = None
            while time.perf_counter() - s < a.timeout:
                w = where(home, next_home, bid)
                if w: break
                time.sleep(0.005)
            single_where[w or "MISSING"] = single_where.get(w or "MISSING", 0) + 1
            if w == "done":
                single.append((time.perf_counter() - s) * 1000)
        res["single"] = {"balls": a.single, "outcome": single_where, "in_to_done_ms": {
            "p50": pct(single, .5), "p90": pct(single, .9), "max": round(max(single), 1) if single else None}}
        print(f"one at a time: {single_where}, in->done ms p50 {res['single']['in_to_done_ms']['p50']} "
              f"max {res['single']['in_to_done_ms']['max']}")

        ids = [f"bench_b{i:05d}" for i in range(a.burst)]
        s = time.perf_counter()
        for i, bid in enumerate(ids):
            put(din, {"id": bid, "type": "bench", "payload": {"n": i}})
        pending, outcome, finish = set(ids), {}, {}
        while pending and time.perf_counter() - s < a.timeout:
            for bid in list(pending):
                w = where(home, next_home, bid)
                if w:
                    outcome[w] = outcome.get(w, 0) + 1
                    finish[bid] = time.perf_counter() - s
                    pending.discard(bid)
            time.sleep(0.01)
        if pending:
            outcome["MISSING"] = len(pending)
        span = max(finish.values()) if finish else None
        res["burst"] = {"balls": a.burst, "outcome": outcome,
                        "seconds_to_account_for_all": round(span, 2) if span else None,
                        "balls_per_s": round(len(finish) / span, 1) if span else None}
        print(f"burst of {a.burst}: {outcome}, {res['burst']['seconds_to_account_for_all']} s, "
              f"{res['burst']['balls_per_s']} balls/s")
    finally:
        try:
            (home / "status").mkdir(parents=True, exist_ok=True)
            (home / "status" / "stop").write_text("bench", encoding="utf-8")   # rebound's clean stop
            proc.wait(timeout=30)
        except Exception:
            pass
        for p in ring_procs(root) if proc.poll() is None else []:
            try: p.kill()
            except psutil.Error: pass
        log.close()
        Path(a.out).write_text(json.dumps(res, indent=1), encoding="utf-8")
        print(f"results: {a.out}")
        if not a.keep:
            shutil.rmtree(scratch, ignore_errors=True)


if __name__ == "__main__":
    main()
