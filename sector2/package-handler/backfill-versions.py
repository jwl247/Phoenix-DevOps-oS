#!/usr/bin/env python3
"""backfill-versions.py — put the missing per-version bytes into R2.

Until 2026-09-29 intake.sh logged a D1 `versions` row (store_path =
<hex>/versions/<sha3[0:16]>) on every content change but never uploaded those
bytes (audit S2CORE-F21). This finds each missing version's EXACT bytes by its
recorded SHA3-512 and uploads them to its store_path. Nothing is guessed: only
bytes whose SHA3 equals D1's row are sent.

Where the bytes are looked for:
  1. the local clone pools (default D:, E:, F: Phoenix\\clonepool), files of a
     size some missing row needs;
  2. every blob in this repo's git history, as stored (LF) AND with CRLF line
     endings (intakes on Windows hashed the CRLF working copy).

  python backfill-versions.py            dry run: what can be recovered
  python backfill-versions.py --upload   upload what was found
Env: PHOENIX_WORKER_URL, PHOENIX_AUTH, CF_ACCESS_CLIENT_ID, CF_ACCESS_CLIENT_SECRET
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

UA = "phoenix-backfill/1.0"


def hdrs():
    return {"Authorization": f"Bearer {os.environ['PHOENIX_AUTH']}",
            "CF-Access-Client-Id": os.environ.get("CF_ACCESS_CLIENT_ID", ""),
            "CF-Access-Client-Secret": os.environ.get("CF_ACCESS_CLIENT_SECRET", ""),
            "User-Agent": UA}


def sha3(b):
    return hashlib.sha3_512(b).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--upload", action="store_true")
    ap.add_argument("--pools", default="D:/Phoenix/clonepool,E:/Phoenix/clonepool,F:/Phoenix/clonepool")
    a = ap.parse_args()
    W = os.environ.get("PHOENIX_WORKER_URL", "https://packages-worker.phoenix-jwl.workers.dev").rstrip("/")

    with urllib.request.urlopen(urllib.request.Request(f"{W}/versions?limit=100000", headers=hdrs()), timeout=60) as r:
        rows = json.loads(r.read())["versions"]
    valid = [x for x in rows if x.get("store_path") and len(x.get("hash_sha3") or "") == 128]
    bad = len(rows) - len(valid)
    want = {}                                   # sha3 -> [rows]
    for x in valid:
        want.setdefault(x["hash_sha3"], []).append(x)
    sizes = {x.get("size") for x in valid if x.get("size")}
    print(f"versions rows: {len(rows)} · with a real SHA3 + store_path: {len(valid)} · unusable (no/placeholder hash): {bad}")
    print(f"distinct contents wanted: {len(want)}")

    found = {}                                  # sha3 -> (source, bytes)

    # 1. local pools (size-filtered)
    for root in a.pools.split(","):
        if not os.path.isdir(root):
            continue
        for d, _, fs in os.walk(root):
            for f in fs:
                p = os.path.join(d, f)
                try:
                    if os.path.getsize(p) not in sizes:
                        continue
                    b = open(p, "rb").read()
                except OSError:
                    continue
                h = sha3(b)
                if h in want and h not in found:
                    found[h] = (f"pool {p}", b)
    n_pool = len(found)

    # 2. git history: every blob, as stored and as CRLF
    objs = subprocess.run(["git", "rev-list", "--all", "--objects"], capture_output=True, text=True).stdout.split("\n")
    shas = sorted({line.split(" ", 1)[0] for line in objs if " " in line})
    batch = subprocess.Popen(["git", "cat-file", "--batch"], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    for s in shas:
        batch.stdin.write((s + "\n").encode()); batch.stdin.flush()
        head = batch.stdout.readline().split()
        if len(head) < 3 or head[1] != b"blob":
            if len(head) >= 3:
                batch.stdout.read(int(head[2]) + 1)
            continue
        b = batch.stdout.read(int(head[2])); batch.stdout.read(1)
        for variant, label in ((b, "git"), (b.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"), "git+crlf")):
            h = sha3(variant)
            if h in want and h not in found:
                found[h] = (f"{label} {s[:10]}", variant)
    batch.stdin.close(); batch.wait()

    n_git = len(found) - n_pool
    miss = [x for h, xs in want.items() if h not in found for x in xs]
    print(f"recovered: {len(found)} of {len(want)} contents  (pools {n_pool}, git history {n_git})")
    print(f"not recoverable here: {len(miss)} rows — e.g. " + ", ".join(f"{m['package']} {m['version']}" for m in miss[:8]))

    if not a.upload:
        print("dry run — nothing uploaded (use --upload)")
        return
    ok = fail = 0
    for h, (src, b) in found.items():
        for x in want[h]:
            req = urllib.request.Request(f"{W}/clonepool/{x['store_path']}", data=b, method="PUT",
                                         headers={**hdrs(), "X-Phoenix-SHA3": h, "Content-Type": "application/octet-stream"})
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    ok += r.status == 200
            except urllib.error.HTTPError as e:
                fail += 1
                print(f"  FAIL {x['store_path']}: {e.code}", file=sys.stderr)
    print(f"uploaded: {ok} version keys, {fail} failed")


if __name__ == "__main__":
    main()
