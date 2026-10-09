#!/usr/bin/env python3
"""phoenix_restore.py — the restorer: puts a box back the way its signed manifest says, by hash.
Phoenix DevOps OS | jwl247 | GPL v3

Step 2 of the restoration disc (Jerry 2026-10-09: "like an old restoration CD that runs itself").
phoenix_manifest.py knows what good looks like; this puts it back.

  python phoenix_restore.py plan  MANIFEST [--root DIR] [--no-git] [--no-r2]
  python phoenix_restore.py apply MANIFEST (--all | PATH ...) [--root DIR] [--no-git] [--no-r2]

  * the manifest's signature is checked first; a bad or unsigned manifest is never used;
  * plan changes nothing: every changed / missing file and where a good copy of it exists;
  * apply puts back ONLY the files named (or --all). The file it replaces is first copied to
    ~/.phoenix/restore/<time>/<path> (quarantine), so every restore can be undone; nothing is
    deleted. Files that differ only in line endings are left alone (same content);
  * sources, in order: this box's git objects (fast), then R2's write-once version copies
    (<hex>/versions/<sha3[:16]>, the way a box with broken git still gets its files back). Every
    copy must hash to the manifest's exact checkout bytes before it is written, or it is not used;
  * every apply is logged to ~/.phoenix/restore/restore.log (one JSON line per file).
Exit: 0 nothing to do / all restored · 1 drift found (plan) · 2 bad manifest · 3 some files had no good copy.
"""

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("phoenix_manifest", HERE / "phoenix_manifest.py")
pm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pm)

RESTORE_HOME = Path.home() / ".phoenix" / "restore"


def sha3(b: bytes) -> str:
    return hashlib.sha3_512(b).hexdigest()


# ── sources ─────────────────────────────────────────────────────────────────
def from_git(m: dict, path: str):
    """The checkout bytes of PATH at the manifest's commit, from this box's own git objects."""
    try:
        r = subprocess.run(["git", "-C", str(pm.REPO), "archive", "--format=tar", m["commit"], "--", path],
                           capture_output=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    import io
    import tarfile
    try:
        with tarfile.open(fileobj=io.BytesIO(r.stdout)) as t:
            for mem in t.getmembers():
                if mem.isfile() and mem.name == path:
                    return t.extractfile(mem).read()
    except tarfile.TarError:
        return None
    return None


def _worker():
    base = os.environ.get("PHOENIX_WORKER_URL", "https://packages-worker.phoenix-jwl.workers.dev").rstrip("/")
    auth = os.environ.get("PHOENIX_AUTH")
    if not auth:
        return None, None
    h = {"Authorization": f"Bearer {auth}", "User-Agent": "phoenix-restore"}
    if os.environ.get("CF_ACCESS_CLIENT_ID") and os.environ.get("CF_ACCESS_CLIENT_SECRET"):
        h["CF-Access-Client-Id"] = os.environ["CF_ACCESS_CLIENT_ID"]
        h["CF-Access-Client-Secret"] = os.environ["CF_ACCESS_CLIENT_SECRET"]
    return base, h


def from_r2(m: dict, path: str, want_disk: str):
    """A write-once R2 version copy with exactly these bytes: first where `phoenix_manifest.py push`
    put it (the hex of its repo path), then the pool's own ids (bare name, or folder/name)."""
    base, h = _worker()
    if not base:
        return None
    p = Path(path)
    ids = [path] + ([p.name, f"{p.parent.name}/{p.name}"] if p.parent.name else [p.name])   # manifest push id first
    for ident in dict.fromkeys(ids):
        hx = ident.encode("utf-8").hex()
        url = f"{base}/clonepool/{urllib.parse.quote(hx)}/versions/{want_disk[:16]}"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=30) as r:
                data = r.read()
        except (urllib.error.URLError, OSError):
            continue
        if sha3(data) == want_disk:
            return data
    return None


def find_good(m, path, want, use_git, use_r2):
    for name, fn in (("git", lambda: from_git(m, path) if use_git else None),
                     ("r2", lambda: from_r2(m, path, want["sha3_disk"]) if use_r2 else None)):
        data = fn()
        if data is not None and sha3(data) == want["sha3_disk"]:   # only exact, verified bytes
            return name, data
    return None, None


# ── drift (same rules as phoenix_manifest.py check) ────────────────────────
def drift(m: dict, root: Path):
    out = []
    for path, want in sorted(m["files"].items()):
        f = pm.longp(root / path)
        try:
            data = f.read_bytes()
        except FileNotFoundError:
            out.append((path, "missing"))
            continue
        if sha3(data) == want["sha3_disk"]:
            continue
        if sha3(pm.normalized(data)) == want["sha3"]:
            continue                                    # line endings only: same content, left alone
        out.append((path, "changed"))
    return out


def cmd_plan(a):
    m = pm.load(a.manifest, a.pub)
    root = Path(a.root or m["root"])
    d = drift(m, root)
    print(f"plan: {m['box']} @ {m['commit'][:12]} vs {root}: {len(d)} file(s) to put back")
    none = 0
    for path, why in d:
        src, _ = find_good(m, path, m["files"][path], not a.no_git, not a.no_r2)
        none += src is None
        print(f"  {why.upper():8} {path}  <- {src or 'NO GOOD COPY'}")
    if none:
        print(f"  {none} file(s) have no good copy in the sources allowed")
    return 0 if not d else 1


def cmd_apply(a):
    m = pm.load(a.manifest, a.pub)
    root = Path(a.root or m["root"])
    d = dict(drift(m, root))
    if a.all:
        todo = sorted(d)
    else:
        unknown = [p for p in a.paths if p not in m["files"]]
        if unknown:
            print(f"not in the manifest (nothing done): {', '.join(unknown)}", file=sys.stderr)
            return 2
        todo = [p for p in a.paths if p in d]
        for p in a.paths:
            if p not in d:
                print(f"  OK       {p}  (already matches; left alone)")
    if not todo:
        print("nothing to put back")
        return 0
    stamp = time.strftime("%Y%m%d-%H%M%S")
    quarantine = RESTORE_HOME / stamp
    RESTORE_HOME.mkdir(parents=True, exist_ok=True)
    failed = 0
    # fetch every good copy in parallel (speed: a whole-box rebuild was 3,030 GETs one at a time);
    # the writes below stay one by one, in order, each verified
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        goods = dict(zip(todo, ex.map(lambda p: find_good(m, p, m["files"][p], not a.no_git, not a.no_r2), todo)))
    with open(RESTORE_HOME / "restore.log", "a", encoding="utf-8") as logf:
        for path in todo:
            want = m["files"][path]
            src, data = goods[path]
            entry = {"at": stamp, "box": m["box"], "commit": m["commit"], "root": str(root), "path": path,
                     "was": d[path], "source": src}
            if data is None:
                failed += 1
                entry["result"] = "no good copy"
                print(f"  SKIPPED  {path}  (no good copy)")
            else:
                try:
                    f = pm.longp(root / path)
                    if f.exists():
                        q = pm.longp(quarantine / path)
                        q.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(f, q)
                        entry["quarantined"] = str(quarantine / path)
                    f.parent.mkdir(parents=True, exist_ok=True)
                    tmp = f.with_name(f.name + ".phoenix-restore.tmp")
                    tmp.write_bytes(data)
                    os.replace(tmp, f)                   # whole file or nothing
                    ok = sha3(f.read_bytes()) == want["sha3_disk"]
                    entry["result"] = "restored" if ok else "WRITE DID NOT VERIFY"
                except OSError as e:                     # one bad file never stops the rest
                    ok = False
                    entry["result"] = f"write failed: {e}"
                failed += not ok
                print(f"  {'RESTORED' if ok else 'FAILED  '} {path}  <- {src}"
                      + (f"  (old copy: {entry['quarantined']})" if "quarantined" in entry else "")
                      + ("" if ok else f"  [{entry['result']}]"))
            logf.write(json.dumps(entry) + "\n")
    print(f"apply: {len(todo) - failed} restored, {failed} not" + (f"; old copies in {quarantine}" if quarantine.exists() else ""))
    return 3 if failed else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("plan", "apply"):
        p = sub.add_parser(name)
        p.add_argument("manifest")
        p.add_argument("--root")
        p.add_argument("--pub")
        p.add_argument("--no-git", action="store_true", help="do not use this box's git objects")
        p.add_argument("--no-r2", action="store_true", help="do not use R2 version copies")
        if name == "apply":
            p.add_argument("paths", nargs="*")
            p.add_argument("--all", action="store_true")
    a = ap.parse_args()
    if a.cmd == "apply" and not a.all and not a.paths:
        ap.error("apply needs the paths to put back, or --all")
    return {"plan": cmd_plan, "apply": cmd_apply}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
