#!/usr/bin/env python3
"""
system_snapshot.py — the whole Phoenix system as ONE custody object
Phoenix DevOps OS | jwl247 | GPL v3

    python scripts/system_snapshot.py                      # → F:/Phoenix/bundles/phoenix-system.tar
    python scripts/system_snapshot.py --out D:/x.tar --dry-run

Why one archive instead of a per-file directory intake: intake keys every
file by its bare NAME. The repo has 13 CONNECTIONS.md, many index.js,
README.md, __init__.py … — a per-file whole-repo intake makes them overwrite
each other's current bytes in R2 and interleave their versions. One stable
name (phoenix-system.tar) means each re-intake is simply the next version of
the whole system, collision-free, restorable in one piece.

What goes in: the working tree as it is right now — committed AND
uncommitted work — minus build/cache dirs (intake's own SKIP_DIRS list) and
minus anything that holds real secret material. Secrets are found by CONTENT
(private keys, live tokens, filled-in KEY=value secrets), not by file name,
so code like phoenix_auth.py is kept and a key hidden in an innocent-looking
file is not. Excluded files are listed by name only in the manifest.

Inside the tar: _SNAPSHOT_MANIFEST.json — every file with its sha256 and
size, the git commit, and the exclusions — so the snapshot is auditable
without unpacking it.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# Same list intake.sh uses for directory intake (SKIP_DIRS), plus git's own.
SKIP_DIRS = {"node_modules", ".git", "__pycache__", ".svn", "vendor", "dist", "build", ".next", ".nuxt",
             "venv", ".venv", "env", ".tox", "coverage", ".nyc_output", "target", "out", ".wrangler",
             ".idea", ".gradle", "clonepool", "archive"}

SECRET_NAMES = re.compile(r"(^\.env$|\.env$|\.pem$|\.key$|\.pfx$|\.p12$|\.kdbx$|^id_(rsa|ed25519|ecdsa)(\.|$))", re.I)
SECRET_CONTENT = [
    (re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "private key"),
    (re.compile(rb"\b(sk|rk)_live_[0-9A-Za-z]{16,}"), "Stripe live key"),
    (re.compile(rb"\bsk_test_[0-9A-Za-z]{16,}"), "Stripe test key"),
    (re.compile(rb"\bwhsec_[0-9A-Za-z]{16,}"), "Stripe webhook secret"),
    (re.compile(rb"\bAKIA[0-9A-Z]{16}\b"), "AWS access key"),
    (re.compile(rb"\bgh[pousr]_[0-9A-Za-z]{30,}"), "GitHub token"),
    (re.compile(rb"\bxox[abpr]-[0-9A-Za-z-]{20,}"), "Slack token"),
    # KEY=value / KEY: value where the key name says secret and the value is long and literal
    (re.compile(rb"(?im)^[ \t]*(?:export[ \t]+|\$env:)?[A-Z0-9_]*(?:SECRET|TOKEN|PASSWORD|API_KEY|PRIVATE_KEY|AUTH)[A-Z0-9_]*"
                rb"[ \t]*[:=][ \t]*[\"']?(?![\"']?\$|[\"']?<|[\"']?\{|[\"']?process\.env|[\"']?os\.environ)"
                rb"[A-Za-z0-9+/_\-\.]{24,}"), "secret assignment"),
]
MAX_SCAN = 8 * 1024 * 1024     # scan the first 8 MiB of each file
PLACEHOLDER = re.compile(rb"(?i)(your[-_]|change[-_]?(me|this)|replace[-_]?me|example|placeholder|xxxxxx|in[-_]production)")


def git_head() -> str:
    try:
        return subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True,
                              text=True, check=True).stdout.strip()
    except Exception:
        return "unknown"


def secret_reason(path: Path) -> str | None:
    if SECRET_NAMES.search(path.name):
        return "secret file type"
    try:
        with open(path, "rb") as f:
            head = f.read(MAX_SCAN)
    except OSError as e:
        return f"unreadable ({e.__class__.__name__})"
    for rx, why in SECRET_CONTENT:
        for m in rx.finditer(head):
            if why == "secret assignment" and PLACEHOLDER.search(m.group(0)):
                continue                     # "change-this-secret-key-in-production" is not a secret
            return why
    return None


def walk(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in sorted(filenames):
            p = Path(dirpath) / name
            if p.is_file() and not p.is_symlink():
                yield p


def build(out: Path, dry_run: bool = False) -> dict:
    files, excluded = [], []
    for p in walk(REPO):
        rel = p.relative_to(REPO).as_posix()
        if p.resolve() == out.resolve():
            continue
        why = secret_reason(p)
        if why:
            excluded.append({"path": rel, "reason": why})
            continue
        files.append((p, rel))

    manifest = {
        "snapshot": "phoenix-system",
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "git_head": git_head(),
        "root": "Phoenix-DevOps-oS",
        "skip_dirs": sorted(SKIP_DIRS),
        "excluded_secret_files": excluded,
        "files": [],
    }
    total = 0
    if dry_run:
        for p, rel in files:
            total += p.stat().st_size
        return {"files": len(files), "bytes": total, "excluded": excluded, "out": None}

    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    with tarfile.open(tmp, "w", format=tarfile.PAX_FORMAT) as tar:
        for p, rel in files:
            data = p.read_bytes()
            total += len(data)
            manifest["files"].append({"path": rel, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()})
            info = tarfile.TarInfo(rel)
            info.size, info.mtime, info.mode = len(data), int(p.stat().st_mtime), 0o644
            tar.addfile(info, io.BytesIO(data))
        blob = json.dumps(manifest, indent=1).encode()
        info = tarfile.TarInfo("_SNAPSHOT_MANIFEST.json")
        info.size, info.mtime, info.mode = len(blob), int(time.time()), 0o644
        tar.addfile(info, io.BytesIO(blob))
    tmp.replace(out)
    return {"files": len(files), "bytes": total, "excluded": excluded, "out": str(out)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Snapshot the whole Phoenix system into one archive for intake")
    ap.add_argument("--out", type=Path, default=Path("F:/Phoenix/bundles/phoenix-system.tar"))
    ap.add_argument("--dry-run", action="store_true", help="count and list exclusions, write nothing")
    a = ap.parse_args(argv)
    t = time.time()
    r = build(a.out, a.dry_run)
    print(f"{r['files']} files, {r['bytes'] / 1e6:.1f} MB{'' if a.dry_run else ' -> ' + r['out']} "
          f"({time.time() - t:.1f}s)")
    print(f"excluded for secret content: {len(r['excluded'])}")
    for e in r["excluded"]:
        print(f"  - {e['path']}  ({e['reason']})")
    if not a.dry_run:
        print("next: bash scripts/hsf-intake.sh " + str(a.out).replace("\\", "/"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
