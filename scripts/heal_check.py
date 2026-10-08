#!/usr/bin/env python3
"""
heal_check.py — healing step 1: CHECK ONLY. Reads a box, changes nothing.
Phoenix DevOps OS | scripts | jwl247 | GPL v3

Jerry 2026-10-07: each box keeps a REFERENCE pulled from the master (the pool) at deploy time; a heal compares
the box to it. Step 1 builds the first reference from what is deployed NOW and reports drift — nothing is
restored, installed or written on the box.

    python scripts/heal_check.py --box pbmiii        # over SSH (ssh config host "pbm-compaq"), read-only
    python scripts/heal_check.py --box pbmii         # this PC: the repo working tree vs the pool

For every deployed file it records path, size and SHA3-512, then compares:
  repo   — the repo's copy at the same relative path: same / DIFFERENT / not in repo
  pool   — the pool's current row for that file (by name, longest folder-qualified match first): matches /
           DIFFERENT from the pool's current version / NOT IN POOL
Writes reference + report to docs/heal/<box>-<date>.json and prints a summary. PHOENIX_WORKER_URL,
PHOENIX_AUTH, CF_ACCESS_CLIENT_ID/SECRET (user env vars) are used to read the pool (read-only GETs).
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "docs" / "heal"

# What counts as "deployed" on a Linux box (read-only listing).
REMOTE = r'''
import hashlib, json, os, sys
roots = ["/opt/phoenix"]
skip_dirs = {".git", "__pycache__", "node_modules", "logs", ".venv", "venv"}
skip_ext = (".pyc", ".log", ".db", ".sqlite", ".sock", ".pid", ".tmp")
out = []
for root in roots:
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if x not in skip_dirs]
        for f in files:
            p = os.path.join(d, f)
            if f.endswith(skip_ext) or not os.path.isfile(p) or os.path.islink(p):
                continue
            try:
                h = hashlib.sha3_512(open(p, "rb").read()).hexdigest()
                out.append({"path": p, "rel": os.path.relpath(p, root), "size": os.path.getsize(p), "sha3": h})
            except OSError as e:
                out.append({"path": p, "error": str(e)})
units = []
for d in ("/etc/systemd/system",):
    for f in sorted(os.listdir(d)):
        p = os.path.join(d, f)
        if os.path.isfile(p) and not os.path.islink(p) and any(k in f for k in ("phoenix", "helix", "jarvis", "nebula", "mesh", "hands", "genie", "frank", "llama")):
            units.append({"path": p, "rel": "units/" + f, "size": os.path.getsize(p),
                          "sha3": hashlib.sha3_512(open(p, "rb").read()).hexdigest()})
print(json.dumps({"files": out, "units": units}))
'''


def env(n):
    v = os.environ.get(n)
    if not v and os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
                v = winreg.QueryValueEx(k, n)[0]
        except OSError:
            v = None
    return v


def pool_rows():
    url = (env("PHOENIX_WORKER_URL") or "").rstrip("/")
    if not url:
        sys.exit("PHOENIX_WORKER_URL is not set")
    req = urllib.request.Request(url + "/clonepool?limit=100000")
    req.add_header("Authorization", f"Bearer {env('PHOENIX_AUTH') or ''}")
    req.add_header("CF-Access-Client-Id", env("CF_ACCESS_CLIENT_ID") or "")
    req.add_header("CF-Access-Client-Secret", env("CF_ACCESS_CLIENT_SECRET") or "")
    req.add_header("User-Agent", "phoenix-heal-check/1")
    with urllib.request.urlopen(req, timeout=60) as r:
        return {row["name"]: row for row in json.loads(r.read())["clonepool"]}


def sha3_file(p):
    return hashlib.sha3_512(Path(p).read_bytes()).hexdigest()


def pool_match(rel, sha3, rows):
    parts = rel.replace("\\", "/").split("/")
    for d in range(min(len(parts), 6), 0, -1):          # longest folder-qualified name first
        name = "/".join(parts[-d:])
        row = rows.get(name)
        if row:
            want = (row.get("hash_sha3") or "").lower()
            if not want:
                return name, "pool row has no SHA3"
            return name, "matches" if want == sha3 else "DIFFERENT from pool's current version"
    return None, "NOT IN POOL"


def repo_match(rel, sha3):
    p = REPO / rel
    if not p.is_file():
        return "not in repo"
    a = p.read_bytes()
    if hashlib.sha3_512(a).hexdigest() == sha3:
        return "same"
    if hashlib.sha3_512(a.replace(b"\r\n", b"\n")).hexdigest() == sha3:
        return "same except line endings"
    return "DIFFERENT"


def main():
    ap = argparse.ArgumentParser(description="healing step 1: check only, changes nothing")
    ap.add_argument("--box", choices=["pbmiii", "pbmii"], required=True)
    ap.add_argument("--ssh-host", default="pbm-compaq")
    a = ap.parse_args()

    rows = pool_rows()
    if a.box == "pbmiii":
        r = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", a.ssh_host, "sudo", "-n", "python3", "-"],
                           input=REMOTE, capture_output=True, text=True, timeout=600)
        if r.returncode != 0:
            sys.exit(f"ssh read failed: {r.stderr[-400:]}")
        data = json.loads(r.stdout)
        items = data["files"] + data["units"]
    else:
        tracked = subprocess.run(["git", "ls-files", "-co", "--exclude-standard"], cwd=REPO,
                                 capture_output=True, text=True).stdout.splitlines()
        items = []
        for rel in tracked:
            if rel.startswith("archive/"):
                continue
            p = REPO / rel
            if p.is_file():
                items.append({"path": str(p), "rel": rel, "size": p.stat().st_size, "sha3": sha3_file(p)})

    report, counts = [], {}
    for it in items:
        if "error" in it:
            it["repo"], it["pool"] = "unreadable", "unreadable"
        else:
            it["pool_name"], it["pool"] = pool_match(it["rel"], it["sha3"], rows)
            it["repo"] = repo_match(it["rel"], it["sha3"]) if a.box == "pbmiii" and not it["rel"].startswith("units/") else "-"
        key = f"repo:{it['repo']} | pool:{it['pool']}"
        counts[key] = counts.get(key, 0) + 1
        report.append(it)

    OUT.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out = OUT / f"{a.box}-{stamp}.json"
    out.write_text(json.dumps({"box": a.box, "taken": stamp, "pool_rows": len(rows),
                               "note": "reference v1 = what was deployed at this moment; check only, nothing changed",
                               "summary": counts, "files": report}, indent=1), encoding="utf-8")
    print(f"{a.box}: {len(report)} deployed files checked against {len(rows)} pool rows (nothing changed)")
    for k, v in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {v:6}  {k}")
    print(f"reference + report: {out}")


if __name__ == "__main__":
    main()
