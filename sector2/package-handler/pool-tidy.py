#!/usr/bin/env python3
"""pool-tidy.py — the local clone pool is a small cache, R2 is the home.

Jerry, 2026-09-29: "it needs to be looking in R2 — it isn't saving any room if
it's local, then I might as well install it." So: everything lives in R2
(checked against D1); a local copy is kept only when it is EARMARKED (pinned)
— e.g. a VM image a runtime must read from disk. Everything else is removed
locally once its exact bytes are proven to be in R2. `intake clone` pulls from
R2 (checked against D1) whenever there is no local copy.

  python pool-tidy.py audit              what would go, what stays, and why
  python pool-tidy.py tidy [--apply]     remove local copies proven in R2 (dry run without --apply)
  python pool-tidy.py pin <name|hex>     earmark: keep this item local
  python pool-tidy.py unpin <name|hex>
  python pool-tidy.py pins

Proof of "in R2", per pool layout <pool>/[T1..T4/]<hex>/…:
  a file   <ver>_<name>          -> R2 key <hex>/versions/<sha3[0:16]> exists
  a dir    <hex>.sidecar.json    -> a directory manifest: R2 has <hex> and D1's hash
                                    for <hex> equals this sidecar's SHA3 (then the
                                    whole snapshot is rebuildable from R2)
Anything not provable (not in the intake layout, network error, missing key)
is KEPT. Pins live in <first pool>/.pins (one name or hex per line).
Env: PHOENIX_WORKER_URL, PHOENIX_AUTH, CF_ACCESS_CLIENT_ID, CF_ACCESS_CLIENT_SECRET, CLONEPOOL_DIR
"""
import argparse
import hashlib
import http.client
import json
import os
import re
import shutil
import sys
import urllib.parse

HEX = re.compile(r"^[0-9a-f]{2,}$")
UA = "phoenix-pool-tidy/1.0"


def pools(arg):
    if arg:
        return [p for p in arg.split(",") if os.path.isdir(p)]
    main = os.environ.get("CLONEPOOL_DIR", os.path.expanduser("~/Phoenix/clonepool"))
    extra = ["D:/Phoenix/clonepool", "E:/Phoenix/clonepool", "F:/Phoenix/clonepool"]
    out = []
    for p in [main] + extra:
        if os.path.isdir(p) and os.path.normcase(os.path.abspath(p)) not in [os.path.normcase(os.path.abspath(x)) for x in out]:
            out.append(p)
    return out


def pins_file(pl):
    return os.path.join(pl[0], ".pins")


def load_pins(pl):
    try:
        names = [l.strip() for l in open(pins_file(pl), encoding="utf-8") if l.strip() and not l.startswith("#")]
    except OSError:
        return set()
    return {n if HEX.match(n) else n.encode().hex() for n in names} | set(names)


class R2:
    """Existence checks through the worker: status + headers only, body never read."""
    def __init__(self):
        u = urllib.parse.urlparse(os.environ.get("PHOENIX_WORKER_URL", "https://packages-worker.phoenix-jwl.workers.dev"))
        self.host, self.base = u.netloc, u.path.rstrip("/")
        self.h = {"Authorization": f"Bearer {os.environ['PHOENIX_AUTH']}", "User-Agent": UA,
                  "CF-Access-Client-Id": os.environ.get("CF_ACCESS_CLIENT_ID", ""),
                  "CF-Access-Client-Secret": os.environ.get("CF_ACCESS_CLIENT_SECRET", "")}
        self.cache = {}

    def _conn(self, timeout):
        # plain HTTP only for a local test worker on loopback; everything else is HTTPS
        local = self.host.split(":")[0] in ("127.0.0.1", "localhost")
        return (http.client.HTTPConnection if local else http.client.HTTPSConnection)(self.host, timeout=timeout)

    def _get(self, path):
        c = self._conn(30)
        try:
            c.request("GET", self.base + path, headers=self.h)
            r = c.getresponse()
            ctype = r.getheader("Content-Type") or ""
            body = r.read() if "json" in ctype else b""      # never pull object bytes
            return r.status, ctype, body
        finally:
            c.close()

    def has_object(self, key):
        """True only when R2 serves bytes for key (the worker falls back to D1 JSON otherwise)."""
        if key not in self.cache:
            try:
                st, ctype, _ = self._get(f"/clonepool/{key}")
                self.cache[key] = st == 200 and "octet-stream" in ctype
            except OSError:
                self.cache[key] = False
        return self.cache[key]

    def bytes_sha3(self, key):
        """SHA3-512 of the bytes R2 actually serves for key, streamed (None if it serves none).
        The proof before a local delete: a key that merely exists could hold other bytes (S2CORE-S26)."""
        c = self._conn(120)
        try:
            c.request("GET", self.base + f"/clonepool/{key}", headers=self.h)
            r = c.getresponse()
            if r.status != 200 or "octet-stream" not in (r.getheader("Content-Type") or ""):
                return None
            h = hashlib.sha3_512()
            for chunk in iter(lambda: r.read(1 << 20), b""):
                h.update(chunk)
            return h.hexdigest()
        except OSError:
            return None
        finally:
            c.close()

    def d1_hash(self, hexid):
        try:
            st, _, body = self._get(f"/clonepool/{hexid}?meta=true")
            return json.loads(body).get("hash_sha3") if st == 200 else None
        except (OSError, ValueError):
            return None


def sha3_file(p):
    h = hashlib.sha3_512()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def hex_dirs(pool):
    for top in os.listdir(pool):
        p = os.path.join(pool, top)
        if not os.path.isdir(p):
            continue
        if top in ("T1", "T2", "T3", "T4"):
            for h in os.listdir(p):
                if os.path.isdir(os.path.join(p, h)):
                    yield h, os.path.join(p, h)
        else:
            yield top, p


def dir_size(p):
    return sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(p) for f in fs)


def plan(pl, r2):
    pins = load_pins(pl)
    go, keep = [], []            # (path, bytes, why)
    for pool in pl:
        for hexid, path in hex_dirs(pool):
            size = dir_size(path)
            if not HEX.match(hexid):
                keep.append((path, size, "not in the intake layout (unmanaged) — upload it first"))
                continue
            if hexid in pins:
                keep.append((path, size, "pinned (earmarked local)"))
                continue
            side = os.path.join(path, f"{hexid}.sidecar.json")
            is_dir = os.path.isfile(side) and '"type": "directory"' in open(side, encoding="utf-8", errors="replace").read()
            if is_dir:
                ok = r2.has_object(hexid) and r2.d1_hash(hexid) == sha3_file(side)
                (go if ok else keep).append((path, size, "directory: manifest in R2 matches D1" if ok
                                             else "directory: manifest not provably in R2"))
                continue
            files = [f for f in os.listdir(path) if os.path.isfile(os.path.join(path, f)) and not f.endswith(".sidecar.json")
                     and not f.startswith(".")]
            if not files:
                go.append((path, size, "empty (only a sidecar)"))
                continue
            proven = [f for f in files if r2.has_object(f"{hexid}/versions/{sha3_file(os.path.join(path, f))[:16]}")]
            if len(proven) == len(files):
                go.append((path, size, f"all {len(files)} version(s) in R2 by exact hash"))
            else:
                keep.append((path, size, f"{len(files) - len(proven)} of {len(files)} version(s) not in R2"))
    return go, keep


def proven_by_bytes(path, r2):
    """Before deleting a local copy: download what R2 serves and hash it. Existence was only the plan."""
    hexid = os.path.basename(path)
    side = os.path.join(path, f"{hexid}.sidecar.json")
    files = [f for f in os.listdir(path) if os.path.isfile(os.path.join(path, f)) and not f.endswith(".sidecar.json")
             and not f.startswith(".")]
    if not files:
        return True                                   # only a sidecar: nothing to lose
    if os.path.isfile(side) and '"type": "directory"' in open(side, encoding="utf-8", errors="replace").read():
        return r2.bytes_sha3(hexid) == sha3_file(side)
    for f in files:
        want = sha3_file(os.path.join(path, f))
        if r2.bytes_sha3(f"{hexid}/versions/{want[:16]}") != want:
            return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["audit", "tidy", "pin", "unpin", "pins"])
    ap.add_argument("name", nargs="?")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--pools", default="")
    a = ap.parse_args()
    pl = pools(a.pools)
    if not pl:
        sys.exit("no pool found")
    if a.cmd in ("pin", "unpin", "pins"):
        cur = []
        try:
            cur = [l.strip() for l in open(pins_file(pl), encoding="utf-8") if l.strip()]
        except OSError:
            pass
        if a.cmd == "pin" and a.name and a.name not in cur:
            cur.append(a.name)
        if a.cmd == "unpin" and a.name in cur:
            cur.remove(a.name)
        if a.cmd != "pins":
            open(pins_file(pl), "w", encoding="utf-8").write("\n".join(cur) + ("\n" if cur else ""))
        print("pinned (kept local):", ", ".join(cur) or "(none)")
        return
    go, keep = plan(pl, R2())
    gb = lambda n: f"{n / 1073741824:.2f} GB"
    print(f"pools: {', '.join(pl)}")
    print(f"remove locally (proven in R2): {len(go)} items, {gb(sum(s for _, s, _ in go))}")
    print(f"keep: {len(keep)} items, {gb(sum(s for _, s, _ in keep))}")
    reasons = {}
    for p, s, why in keep:
        k = why.split(" — ")[0] if "layout" in why else why.split(":")[0] if why.startswith("directory") else re.sub(r"\d+", "N", why)
        reasons.setdefault(k, [0, 0]); reasons[k][0] += 1; reasons[k][1] += s
    for k, (n, s) in sorted(reasons.items(), key=lambda x: -x[1][1]):
        print(f"   keep {n:5d} · {gb(s):>9}  {k}")
    for p, s, why in sorted(keep, key=lambda x: -x[1])[:6]:
        print(f"      e.g. {gb(s):>9}  {p}  ({why})")
    if a.cmd == "tidy" and a.apply:
        freed, removed, r2 = 0, 0, R2()
        for p, s, _ in go:
            if not proven_by_bytes(p, r2):
                print(f"   kept {p}: R2's bytes do not hash to the local copy")
                continue
            shutil.rmtree(p, ignore_errors=True)
            freed += s; removed += 1
        print(f"removed {removed} local copies (each re-hashed from R2 first), freed {gb(freed)}")
    elif a.cmd == "tidy":
        print("dry run — nothing removed (add --apply)")


if __name__ == "__main__":
    main()
