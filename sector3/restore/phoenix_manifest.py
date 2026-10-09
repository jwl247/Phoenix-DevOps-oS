#!/usr/bin/env python3
"""phoenix_manifest.py — what "good" looks like for a box: the restoration disc's contents list.
Phoenix DevOps OS | jwl247 | GPL v3

Jerry 2026-10-09: "like an old restoration CD that runs itself." A CD worked because it knew exactly
what a good system looks like. This is that knowledge for Phoenix: every file of the system at a
known-good moment, with its SHA3-512, signed. The restorer (next step) reads it and puts back,
by hash, whatever does not match.

What a manifest covers (v1): the Phoenix repo exactly as one COMMIT checks out on this box — the
bytes git writes to disk here (line endings and all), not the working tree. Uncommitted edits are
therefore never baked in as "good"; `check` shows them as drift.

  python phoenix_manifest.py make   [--box NAME] [--commit REV] [--out FILE]   snapshot + sign
  python phoenix_manifest.py verify FILE                                       signature only
  python phoenix_manifest.py check  FILE [--root DIR]                          disk vs manifest, read-only

Signed with the Phoenix config key (vault: phoenix-config-sign_ed25519) under its OWN namespace
"phoenix-system-manifest": an ssh signature is bound to its namespace, so a manifest signature can
never pass as a mesh-config signature or the other way round. The private key never leaves a temp
copy locked to this user. Exit codes: 0 ok/clean | 1 drift (check) | 2 bad/unsigned/unreadable.
"""

import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

NS = "phoenix-system-manifest"
KIND = "phoenix-system-manifest"
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
VAULT = Path(os.environ.get("PHOENIX_VAULT", r"F:\Phoenix\Vault\secrets"))
SIGN_KEY = VAULT / "phoenix-config-sign_ed25519"
OUT_DIR = Path.home() / ".phoenix" / "manifests"


def git(*args, inp=None) -> bytes:
    r = subprocess.run(["git", "-C", str(REPO), *args], input=inp, capture_output=True)
    if r.returncode != 0:
        raise SystemExit(f"git {' '.join(args[:2])} failed: {r.stderr.decode(errors='replace').strip()}")
    return r.stdout


def canonical(manifest: dict) -> bytes:
    return json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _locked_copy(src: Path, td: str) -> Path:
    # The vault drive is exFAT (no ACLs): ssh-keygen refuses a key "readable by all" there.
    k = Path(td) / "k"
    k.write_bytes(src.read_bytes())
    if os.name == "nt":
        subprocess.run(["icacls", str(k), "/inheritance:r", "/grant:r", f"{os.environ['USERNAME']}:F"],
                       check=True, capture_output=True)
    else:
        k.chmod(0o600)
    return k


def sign(data: bytes) -> str:
    if not SIGN_KEY.exists():
        raise SystemExit(f"no signing key at {SIGN_KEY} (python sector3/mesh/phoenix_buddy.py keys)")
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "m"
        f.write_bytes(data)
        k = _locked_copy(SIGN_KEY, td)
        subprocess.run(["ssh-keygen", "-q", "-Y", "sign", "-f", str(k), "-n", NS, str(f)], check=True, capture_output=True)
        return (Path(td) / "m.sig").read_text()


def verify_sig(data: bytes, sig: str, pub: Path) -> bool:
    kt, kb = pub.read_text().split()[:2]
    with tempfile.TemporaryDirectory() as td:
        allowed = Path(td) / "allowed"
        allowed.write_text(f'phoenix-manifest namespaces="{NS}" {kt} {kb}\n')
        s = Path(td) / "m.sig"
        s.write_text(sig)
        r = subprocess.run(["ssh-keygen", "-Y", "verify", "-f", str(allowed), "-I", "phoenix-manifest", "-n", NS,
                            "-s", str(s)], input=data, capture_output=True)
        return r.returncode == 0


def tracked_bytes(commit: str):
    """(path, mode, blob, canonical bytes, bytes as checkout writes them here) for every file in the
    commit. Canonical = git's own stored content (raw blob); the checkout form comes from `git archive`
    (same line-ending conversion a checkout does). Two git processes for the whole tree."""
    import io
    import tarfile
    entries = []
    for rec in git("ls-tree", "-r", "-z", "--full-tree", commit).split(b"\0"):
        if not rec:
            continue
        meta, path = rec.split(b"\t", 1)
        mode, typ, blob = meta.decode().split()
        if typ != "blob" or mode == "120000":          # submodules and symlinks: not files to restore
            continue
        entries.append((path.decode("utf-8"), mode, blob))
    raw, pos = {}, 0
    out = git("cat-file", "--batch", inp="".join(f"{b}\n" for _, _, b in entries).encode())
    for path, _, blob in entries:                       # raw blobs: the header size is exact
        nl = out.index(b"\n", pos)
        size = int(out[pos:nl].split()[2])
        raw[path] = out[nl + 1:nl + 1 + size]
        pos = nl + 1 + size + 1
    disk = {}
    with tarfile.open(fileobj=io.BytesIO(git("archive", "--format=tar", commit))) as t:
        for m in t.getmembers():
            if m.isfile():
                disk[m.name] = t.extractfile(m).read()
    for path, mode, blob in entries:
        yield path, mode, blob, raw[path], disk.get(path, raw[path])


def normalized(data: bytes) -> bytes:
    """Content with line endings taken out of the comparison (text only: a NUL byte = binary)."""
    return data if b"\0" in data else data.replace(b"\r\n", b"\n")



def cmd_make(a):
    commit = git("rev-parse", a.commit).decode().strip()
    files, total = {}, 0
    for path, mode, blob, canon, ondisk in tracked_bytes(commit):
        files[path] = {"sha3": hashlib.sha3_512(normalized(canon)).hexdigest(),       # content (line endings out)
                       "sha3_disk": hashlib.sha3_512(ondisk).hexdigest(),          # exactly what checkout writes here
                       "size": len(ondisk), "mode": mode, "blob": blob}
        total += len(ondisk)
    box = a.box or socket.gethostname().lower()
    manifest = {
        "kind": KIND, "v": 1, "box": box, "root": str(REPO).replace("\\", "/"),
        "commit": commit, "subject": git("log", "-1", "--format=%s", commit).decode().strip()[:200],
        "made_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "count": len(files), "total_bytes": total, "files": files,
    }
    doc = {"manifest": manifest, "sig": sign(canonical(manifest)),
           "signer": " ".join(Path(str(SIGN_KEY) + ".pub").read_text().split()[:2])}
    out = Path(a.out) if a.out else OUT_DIR / f"phoenix-manifest-{box}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
    print(f"manifest: {box} @ {commit[:12]} ({manifest['subject'][:60]})")
    print(f"  {len(files)} files, {total / 1048576:.1f} MB, signed ({NS})")
    print(f"  -> {out}")
    return 0


def load(path: str, pub=None):
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
        m, sig = doc["manifest"], doc["sig"]
    except (OSError, ValueError, KeyError) as e:
        print(f"not a Phoenix manifest: {e}", file=sys.stderr)
        sys.exit(2)
    if m.get("kind") != KIND:
        print(f"not a Phoenix manifest (kind={m.get('kind')!r})", file=sys.stderr)
        sys.exit(2)
    pub = Path(pub) if pub else Path(str(SIGN_KEY) + ".pub")
    if not verify_sig(canonical(m), sig, pub):
        print("SIGNATURE BAD — this manifest was not made by Phoenix or was changed after signing; not used",
              file=sys.stderr)
        sys.exit(2)
    return m


def cmd_verify(a):
    m = load(a.file, a.pub)
    print(f"signature OK: {m['box']} @ {m['commit'][:12]}, {m['count']} files, made {m['made_at']}")
    return 0


def cmd_check(a):
    m = load(a.file, a.pub)
    root = Path(a.root or m["root"])
    changed, missing, eol, ok = [], [], [], 0
    for path, want in sorted(m["files"].items()):
        f = root / path
        try:
            data = f.read_bytes()
        except FileNotFoundError:
            missing.append(path)
            continue
        if hashlib.sha3_512(data).hexdigest() == want["sha3_disk"]:
            ok += 1
        elif hashlib.sha3_512(normalized(data)).hexdigest() == want["sha3"]:
            eol.append(path)                            # same content, other line endings
        else:
            changed.append(path)
    print(f"check: {m['box']} @ {m['commit'][:12]} vs {root}")
    print(f"  {ok} match | {len(eol)} line-endings only | {len(changed)} changed | {len(missing)} missing  (of {m['count']})")
    for p in changed[:a.show]:
        print(f"  CHANGED  {p}")
    for p in missing[:a.show]:
        print(f"  MISSING  {p}")
    more = len(changed) + len(missing) - min(len(changed), a.show) - min(len(missing), a.show)
    if more > 0:
        print(f"  ... and {more} more (--show N)")
    if a.json:
        Path(a.json).write_text(json.dumps({"changed": changed, "missing": missing, "eol_only": eol}, indent=1), encoding="utf-8")
    return 0 if not (changed or missing) else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    mk = sub.add_parser("make")
    mk.add_argument("--box")
    mk.add_argument("--commit", default="HEAD")
    mk.add_argument("--out")
    for name in ("verify", "check"):
        p = sub.add_parser(name)
        p.add_argument("file")
        p.add_argument("--pub", help="the signer's .pub (default: the vault's config key)")
        if name == "check":
            p.add_argument("--root")
            p.add_argument("--show", type=int, default=20)
            p.add_argument("--json", help="write the drift list here")
    a = ap.parse_args()
    return {"make": cmd_make, "verify": cmd_verify, "check": cmd_check}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
