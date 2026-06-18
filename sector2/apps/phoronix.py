#!/usr/bin/env python3
"""
phoronix.py — Frank Suit: Phoronix Test Suite benchmark runner
Runs system benchmarks on phoenix-ext, logs results to D1 custody.
No GPU benchmarks — GPU is blacklisted in Phoenix.

Benchmark suite (CPU + memory + I/O + network):
  pts/compress-7zip   — CPU integer (compression)
  pts/build-php       — CPU real-world build time
  pts/ramspeed        — memory bandwidth (alloc, copy, scale, add, triad)
  pts/fio             — I/O throughput (breach_coms drives)
  pts/network-loopback — TCP loopback latency/throughput

SUIT_ID:  phoronix
CHANNEL:  benchmark
FRANK:    port 7347

Install: sudo apt-get install phoronix-test-suite
Run:     python3 phoronix.py --run
         python3 phoronix.py --run --suite quick   (compress + ramspeed only)
         python3 phoronix.py --list
         python3 phoronix.py --status

Phoenix DevOps OS | jwl247 | GPL v3
"""

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

SUIT_ID   = "phoronix"
CHANNEL   = "benchmark"

FRANK_URL  = os.environ.get("FRANK_HTTP_URL",  "http://localhost:7347")
D1_WORKER  = os.environ.get("D1_WORKER_URL",   "https://packages-worker.phoenix-jwl.workers.dev")
PHOENIX_AUTH = os.environ.get("PHOENIX_AUTH",  "")
AUDIT_LOG  = Path(os.environ.get("PHOENIX_AUDIT", "/var/log/phoenix/audit.log"))

PTS = "phoronix-test-suite"

# ── Benchmark suites ──────────────────────────────────────────────────────────

SUITES = {
    "quick": [
        "pts/compress-7zip",
        "pts/ramspeed",
    ],
    "full": [
        "pts/compress-7zip",
        "pts/build-php",
        "pts/ramspeed",
        "pts/fio",
        "pts/network-loopback",
    ],
    "cpu": [
        "pts/compress-7zip",
        "pts/build-php",
    ],
    "memory": [
        "pts/ramspeed",
    ],
    "io": [
        "pts/fio",
    ],
    "network": [
        "pts/network-loopback",
    ],
}

SUITE_DESCRIPTIONS = {
    "pts/compress-7zip":       "CPU integer — 7-zip MIPS compression",
    "pts/build-php":           "CPU real-world — PHP build time",
    "pts/ramspeed":            "Memory bandwidth — alloc/copy/scale/add/triad",
    "pts/fio":                 "I/O throughput — sequential/random read+write",
    "pts/network-loopback":    "Network — TCP loopback latency + throughput",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _audit(msg: str):
    try:
        AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
        entry = json.dumps({"ts": datetime.now(timezone.utc).isoformat(),
                            "op": SUIT_ID, "msg": msg})
        with open(AUDIT_LOG, "a") as f:
            f.write(entry + "\n")
    except Exception:
        pass


def _post_d1(payload: dict) -> dict:
    data = json.dumps(payload).encode()
    headers = {
        "Content-Type":  "application/json",
        "Authorization": f"Bearer {PHOENIX_AUTH}",
    }
    req = urllib.request.Request(f"{D1_WORKER}/custody", data=data,
                                 headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"error": str(e)}


def _pts_installed() -> bool:
    return subprocess.run(
        ["which", PTS], capture_output=True
    ).returncode == 0


def _install_pts():
    print(f"[phoronix] Installing phoronix-test-suite...")
    result = subprocess.run(
        ["sudo", "apt-get", "install", "-y", "phoronix-test-suite"],
        capture_output=False
    )
    return result.returncode == 0


def _run_benchmark(test: str) -> dict:
    """Run a single pts benchmark, return parsed result."""
    print(f"\n[phoronix] Running: {test}")
    print(f"           {SUITE_DESCRIPTIONS.get(test, '')}")
    print(f"           (non-interactive — batch mode)")

    env = os.environ.copy()
    env["PHORONIX_TEST_SUITE_BATCH_MODE"] = "1"
    env["TEST_RESULTS_IDENTIFIER"]        = f"phoenix_{int(time.time())}"

    t0 = time.time()
    result = subprocess.run(
        [PTS, "batch-benchmark", test],
        capture_output=True, text=True, env=env, timeout=1800
    )
    elapsed = time.time() - t0

    return {
        "test":       test,
        "returncode": result.returncode,
        "elapsed_s":  round(elapsed, 1),
        "stdout":     result.stdout[-4000:] if result.stdout else "",
        "stderr":     result.stderr[-1000:] if result.stderr else "",
        "ts":         datetime.now(timezone.utc).isoformat(),
    }


def _parse_result(raw: dict) -> dict:
    """Extract key metrics from pts stdout."""
    stdout = raw.get("stdout", "")
    lines  = stdout.splitlines()

    results = []
    for line in lines:
        # pts output format: "Result: 12345.67 ..."
        if "Result:" in line or "Average:" in line:
            results.append(line.strip())

    return {
        **raw,
        "results": results,
        "passed":  raw["returncode"] == 0,
    }


# ── Phoronix Suit ─────────────────────────────────────────────────────────────

class PhoronixSuit:

    def check(self) -> dict:
        installed = _pts_installed()
        return {
            "suit":      SUIT_ID,
            "installed": installed,
            "suites":    list(SUITES.keys()),
            "tests":     list(SUITE_DESCRIPTIONS.keys()),
            "install":   "sudo apt-get install phoronix-test-suite" if not installed else "ok",
        }

    def run(self, suite: str = "quick", install_if_missing: bool = True) -> dict:
        if not _pts_installed():
            if install_if_missing:
                if not _install_pts():
                    return {"error": "phoronix-test-suite install failed"}
            else:
                return {"error": "phoronix-test-suite not installed — run: sudo apt-get install phoronix-test-suite"}

        tests = SUITES.get(suite)
        if tests is None:
            return {"error": f"unknown suite '{suite}' — choose from: {list(SUITES.keys())}"}

        run_id  = f"phoenix_bench_{int(time.time())}"
        session = {
            "run_id":   run_id,
            "suite":    suite,
            "tests":    tests,
            "started":  datetime.now(timezone.utc).isoformat(),
            "results":  [],
        }

        print(f"\n{'='*65}")
        print(f"FRANK SUIT — PHORONIX  [{SUIT_ID}]")
        print(f"Suite: {suite}  |  {len(tests)} tests  |  Run ID: {run_id}")
        print(f"{'='*65}")

        _audit(f"benchmark start — run_id={run_id} suite={suite} tests={tests}")

        for test in tests:
            raw    = _run_benchmark(test)
            parsed = _parse_result(raw)
            session["results"].append(parsed)

            status = "PASS" if parsed["passed"] else "FAIL"
            print(f"\n  [{status}] {test}  ({parsed['elapsed_s']}s)")
            for r in parsed["results"]:
                print(f"         {r}")

        session["finished"]  = datetime.now(timezone.utc).isoformat()
        session["all_passed"] = all(r["passed"] for r in session["results"])

        # Log to D1
        d1_payload = {
            "hex_id":  run_id,
            "name":    f"benchmark_{suite}",
            "action":  "phoronix_benchmark",
            "actor":   "phoronix_suit",
            "state":   "complete" if session["all_passed"] else "partial",
            "qr_top":  f"USYS:BENCH:{run_id}:HEADER",
            "qr_bottom": f"USYS:BENCH:{run_id}:FOOTER",
        }
        d1_r = _post_d1(d1_payload)
        session["d1"] = d1_r

        _audit(f"benchmark complete — run_id={run_id} passed={session['all_passed']} d1={d1_r}")

        return session

    def install(self) -> bool:
        return _install_pts()


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Frank Suit: Phoronix benchmarks")
    parser.add_argument("--run",    action="store_true",    help="run benchmark suite")
    parser.add_argument("--suite",  default="quick",        help="suite: quick/full/cpu/memory/io/network (default: quick)")
    parser.add_argument("--list",   action="store_true",    help="list available suites + tests")
    parser.add_argument("--status", action="store_true",    help="check install status")
    parser.add_argument("--install",action="store_true",    help="install phoronix-test-suite")
    parser.add_argument("--no-install", action="store_true", help="don't auto-install pts")
    args = parser.parse_args()

    suit = PhoronixSuit()

    if args.list:
        print("\nAvailable suites:")
        for name, tests in SUITES.items():
            print(f"  {name:<10} {', '.join(tests)}")
        print("\nAvailable tests:")
        for test, desc in SUITE_DESCRIPTIONS.items():
            print(f"  {test:<30} {desc}")

    elif args.install:
        ok = suit.install()
        print("Installed." if ok else "Install failed — check apt output.")

    elif args.status:
        s = suit.check()
        print(json.dumps(s, indent=2))

    elif args.run:
        result = suit.run(suite=args.suite, install_if_missing=not args.no_install)
        print(f"\n{'='*65}")
        print(f"RESULT: {'ALL PASSED' if result.get('all_passed') else 'SOME FAILED'}")
        print(f"Run ID: {result.get('run_id')}")
        print(f"D1:     {result.get('d1')}")
        print(f"{'='*65}\n")

    else:
        parser.print_help()
        print("\nExamples:")
        print("  python3 phoronix.py --run                    # quick suite (7zip + ramspeed)")
        print("  python3 phoronix.py --run --suite full       # all 5 benchmarks")
        print("  python3 phoronix.py --run --suite cpu        # CPU only")
        print("  python3 phoronix.py --run --suite memory     # RAM only")
        print("  python3 phoronix.py --run --suite io         # I/O only (breach_coms drives)")
        print("  python3 phoronix.py --list")
        print("  python3 phoronix.py --status")


if __name__ == "__main__":
    main()
