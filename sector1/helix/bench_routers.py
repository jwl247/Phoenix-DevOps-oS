#!/usr/bin/env python3
"""
bench_routers.py — the router bench: Capulet (Frank + Helix) vs Helix Slim, the same message stream.
Phoenix DevOps OS | sector1/helix | jwl247 | GPL v3

Jerry 2026-10-07: his nominations in "Testing Facilty/". Capulet and Slim don't store data — they route
messages — so they get this test instead of bench_three.py's store/fetch test. It is also the audition for
the Compaq's router job. Jerry runs it; the numbers are printed by this script and saved next to it.
Claude built the test and does not run the bench (docs/helix/BENCH-BY-HAND.md).

    python bench_routers.py --check        # 10 messages each: does every one come out the other side? PASS/FAIL
    python bench_routers.py                # the bench: capulet, then slim
    python bench_routers.py --only slim --messages 50000 --size 1024

How (identical for both): the router is started as its own program from Testing Facilty (its own main(),
unchanged), the bench connects to its IN and OUT ports on 127.0.0.1, sends --messages JSON messages as
fast as it can, and collects everything that comes out until --idle seconds pass with nothing new. Each
message carries its send time, so the delay through the router is measured per message.

    capulet  in 5555 -> out 5556   (python capulet.py)
    slim     in 5560 -> out 5559   (python helix_slim.py)

Reported: messages sent / received / LOST, throughput (messages/s out), delay p50 / p90 / p99 / max (ms),
and where it stopped if it stalled. Both routers bind every network interface ("tcp://*"), so Windows may
show a firewall prompt for Python the first time — "Cancel"/deny is fine, the bench only uses 127.0.0.1.
The routers' own log output goes to a file in your temp folder (printed at the end), not the screen.
"""

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

try:
    import zmq
except ImportError:
    sys.exit("pyzmq is not installed: python -m pip install pyzmq psutil")

HERE = Path(__file__).resolve().parent
TESTING = HERE.parents[1] / "Testing Facilty"
ROUTERS = {
    "capulet": {"label": "Capulet (Frank + Helix)", "file": "capulet.py",    "inp": 5555, "out": 5556},
    "slim":    {"label": "Helix Slim",              "file": "helix_slim.py", "inp": 5560, "out": 5559},
}


def port_busy(port):
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def wait_listening(port, seconds=20):
    end = time.time() + seconds
    while time.time() < end:
        if port_busy(port):
            return True
        time.sleep(0.2)
    return False


def pct(sorted_ms, q):
    return round(sorted_ms[min(len(sorted_ms) - 1, int(q * len(sorted_ms)))], 3) if sorted_ms else None


def run_router(name, a, n):
    r = ROUTERS[name]
    path = Path(a.testing) / r["file"]
    if not path.is_file():
        return {"router": name, "error": f"{path} not found"}
    for p in (r["inp"], r["out"]):
        if port_busy(p):
            return {"router": name, "error": f"port {p} is already in use by another program — stop it first"}

    log = Path(tempfile.gettempdir()) / f"bench_routers_{name}.log"
    with open(log, "w", encoding="utf-8") as lf:
        proc = subprocess.Popen([sys.executable, str(path)], cwd=str(path.parent), stdout=lf, stderr=subprocess.STDOUT)
    try:
        if not (wait_listening(r["inp"]) and wait_listening(r["out"])):
            return {"router": name, "error": f"never started listening on {r['inp']}/{r['out']} (see {log})", "log": str(log)}

        ctx = zmq.Context()
        push = ctx.socket(zmq.PUSH); push.setsockopt(zmq.LINGER, 0); push.setsockopt(zmq.SNDTIMEO, 2000)
        pull = ctx.socket(zmq.PULL); pull.setsockopt(zmq.LINGER, 0); pull.setsockopt(zmq.RCVTIMEO, 200)
        push.connect(f"tcp://127.0.0.1:{r['inp']}")
        pull.connect(f"tcp://127.0.0.1:{r['out']}")
        time.sleep(0.5)                                      # let both connections settle

        pad = "x" * a.size
        got = {}                                             # id -> delay ns
        bad = 0
        done = threading.Event()

        def receiver():
            nonlocal bad
            last_new = time.time()
            while not done.is_set() or time.time() - last_new < a.idle:
                try:
                    m = pull.recv_json()
                except zmq.Again:
                    if done.is_set() and time.time() - last_new >= a.idle:
                        break
                    continue
                now = time.time_ns()
                i = m.get("bench_id")
                if isinstance(i, int) and 0 <= i < n and i not in got:
                    got[i] = now - m.get("bench_t", now)
                else:
                    bad += 1
                last_new = time.time()

        rt = threading.Thread(target=receiver, daemon=True)
        rt.start()
        sent = 0
        stalled_at = None
        t0 = time.time()
        for i in range(n):
            try:
                push.send_json({"type": "bench", "bench_id": i, "bench_t": time.time_ns(), "pad": pad})
                sent += 1
            except zmq.Again:                               # the router stopped taking messages
                stalled_at = i
                break
        t_sent = time.time() - t0
        done.set()
        rt.join(timeout=a.idle + 60)
        t_total = time.time() - t0
        push.close(); pull.close(); ctx.term()

        delays = sorted(d / 1e6 for d in got.values())
        return {"router": name, "label": r["label"], "messages": n, "size": a.size,
                "sent": sent, "received": len(got), "lost": sent - len(got), "garbled_or_duplicate": bad,
                "stalled_at_message": stalled_at,
                "send_seconds": round(t_sent, 3),
                "throughput_msgs_per_s": round(len(got) / max(t_total - a.idle, 1e-9), 1) if got else 0,
                "delay_ms": {"p50": pct(delays, .5), "p90": pct(delays, .9), "p99": pct(delays, .99),
                             "max": round(delays[-1], 3) if delays else None},
                "router_log": str(log)}
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def main():
    p = argparse.ArgumentParser(description="Capulet vs Helix Slim — same message stream, Jerry runs it")
    p.add_argument("--only", choices=list(ROUTERS))
    p.add_argument("--messages", type=int, default=20000)
    p.add_argument("--size", type=int, default=256, help="padding bytes per message")
    p.add_argument("--idle", type=float, default=5.0, help="stop collecting after this many quiet seconds")
    p.add_argument("--check", action="store_true", help="10 messages each, PASS/FAIL only")
    p.add_argument("--testing", default=str(TESTING), help="folder holding capulet.py and helix_slim.py")
    p.add_argument("--out", default=str(HERE / f"bench_routers-{time.strftime('%Y%m%d-%H%M%S')}.json"))
    a = p.parse_args()

    order = [a.only] if a.only else ["capulet", "slim"]
    results = []
    for name in order:
        print(f"\n== {ROUTERS[name]['label']} ...", flush=True)
        if a.check:
            r = run_router(name, argparse.Namespace(**{**vars(a), "size": 16, "idle": 3.0}), 10)
            verdict = r.get("error") or ("PASS" if r.get("received") == 10 and not r.get("garbled_or_duplicate")
                                         else f"FAIL ({r.get('received')}/10 came out)")
            print(f"   {name}: {verdict}")
            continue
        r = run_router(name, a, a.messages)
        results.append(r)
        print("   " + json.dumps(r))

    if a.check:
        return
    Path(a.out).write_text(json.dumps(results, indent=1), encoding="utf-8")
    print(f"\n{'router':26} {'sent':>7} {'received':>9} {'LOST':>7} {'msgs/s':>9} {'p50 ms':>8} {'p99 ms':>8} {'max ms':>8} stalled")
    for r in results:
        if "error" in r:
            print(f"{ROUTERS[r['router']]['label']:26} ERROR {r['error']}")
            continue
        d = r["delay_ms"]
        print(f"{r['label']:26} {r['sent']:>7} {r['received']:>9} {r['lost']:>7} {r['throughput_msgs_per_s']:>9} "
              f"{str(d['p50']):>8} {str(d['p99']):>8} {str(d['max']):>8} {r['stalled_at_message']}")
    print(f"\nfull results: {a.out}")


if __name__ == "__main__":
    main()
