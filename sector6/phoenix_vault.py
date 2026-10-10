#!/usr/bin/env python3
"""
phoenix_vault.py — Phoenix secrets: encrypted push from the vault, pull onto any box
Phoenix DevOps OS | jwl247 | GPL v3

Standalone on purpose (stdlib + `cryptography`; Debian: apt install python3-cryptography)
so a bare new box can run it before it has the repo.

    # on the PC that holds the vault (F:\\Phoenix\\Vault\\secrets)
    python sector6/phoenix_vault.py push                 # encrypt + upload + register fetch key
    python sector6/phoenix_vault.py verify               # pull back to memory, compare, write nothing

    # on a new box — type the passphrase, nothing else
    python3 phoenix_vault.py pull --only phoenix-secrets.env          --dest /etc/phoenix/secrets
    python3 phoenix_vault.py pull --keys PHOENIX_AUTH,PHOENIX_WORKER_URL --dest /etc/phoenix/secrets
    python3 phoenix_vault.py list                        # names only, never values

Security model:
  - Cloudflare (R2, D1, the worker) never holds a readable secret. The vault is
    encrypted HERE with AES-256-GCM; the key is scrypt(passphrase, random salt).
  - Fetching the encrypted file needs a fetch token, also derived from the
    passphrase (separate scrypt, separate salt). The worker stores only
    sha256(token). So a box types ONE thing — the passphrase.
  - The passphrase is read with getpass (or PHOENIX_VAULT_PASSPHRASE for
    automation) — never from the command line.
  - Pulled secrets are written 0600 in a 0700 directory; only names are printed.
  - Forget the passphrase and the cloud copies are unopenable by anyone. The
    vault on the home PC stays the master copy.
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import io
import json
import os
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

MAGIC = b"PHXVAULT"
FORMAT = 1
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2 ** 17, 8, 1        # ~0.3–1 s and 128 MiB per derivation
FETCH_SALT = b"phoenix-vault/fetch/v1"
OBJECT = "phoenix-vault.enc"
USER_AGENT = "phoenix-vault/1.0"
DEFAULT_VAULT = Path(os.environ.get("PHOENIX_VAULT_SECRETS", r"F:\Phoenix\Vault\secrets"))
DEFAULT_URL = os.environ.get("PHOENIX_VAULT_URL", "https://phoenix-vault-worker.phoenix-jwl.workers.dev")
SKIP = {".template", ".md"}                          # docs and templates stay home


# ---------------------------------------------------------------------------
# Crypto
# ---------------------------------------------------------------------------

def _scrypt(passphrase: str, salt: bytes) -> bytes:
    return hashlib.scrypt(passphrase.encode("utf-8"), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P,
                          maxmem=256 * 1024 * 1024, dklen=32)


def fetch_token(passphrase: str) -> str:
    """What a box shows the worker. The worker keeps only sha256 of this."""
    return _scrypt(passphrase, FETCH_SALT).hex()


def fetch_hash(passphrase: str) -> str:
    return hashlib.sha256(fetch_token(passphrase).encode()).hexdigest()


def seal(files: dict[str, bytes], passphrase: str) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    salt, nonce = os.urandom(16), os.urandom(12)
    header = MAGIC + struct.pack("<BIII", FORMAT, SCRYPT_N, SCRYPT_R, SCRYPT_P) + salt + nonce
    body = json.dumps({"created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                       "files": {k: v.decode("utf-8") for k, v in sorted(files.items())}}).encode()
    return header + AESGCM(_scrypt(passphrase, salt)).encrypt(nonce, body, header)


def unseal(blob: bytes, passphrase: str) -> dict:
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    if blob[:8] != MAGIC:
        raise ValueError("not a Phoenix vault file")
    fmt, n, r, p = struct.unpack("<BIII", blob[8:21])
    if fmt != FORMAT:
        raise ValueError(f"vault format {fmt} — this tool reads {FORMAT}")
    salt, nonce, header = blob[21:37], blob[37:49], blob[:49]
    key = hashlib.scrypt(passphrase.encode(), salt=salt, n=n, r=r, p=p, maxmem=256 * 1024 * 1024, dklen=32)
    try:
        return json.loads(AESGCM(key).decrypt(nonce, blob[49:], header))
    except InvalidTag:
        raise ValueError("wrong passphrase, or the vault file was altered") from None


# ---------------------------------------------------------------------------
# Vault contents
# ---------------------------------------------------------------------------

def read_vault(vault: Path) -> dict[str, bytes]:
    files = {}
    for p in sorted(vault.iterdir()):
        # backups (*.bak*) stay home too: a rotation once wrote the live key into one (2026-10-08)
        if p.is_file() and p.suffix.lower() not in SKIP and ".bak" not in p.name.lower():
            data = p.read_bytes()
            data.decode("utf-8")                       # secrets are text; refuse anything else
            files[p.name] = data
    if not files:
        raise ValueError(f"no secret files in {vault}")
    return files


def env_values(text: str) -> dict[str, str]:
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip().removeprefix("export ").strip()] = v.strip().strip('"').strip("'")
    return out


def ask_passphrase(confirm: bool = False) -> str:
    pw = os.environ.get("PHOENIX_VAULT_PASSPHRASE")
    if pw:
        return pw
    pw = getpass.getpass("Vault passphrase: ")
    if confirm:
        if len(pw) < 16:
            raise SystemExit("Use at least 16 characters — a few random words works well.")
        if getpass.getpass("Again: ") != pw:
            raise SystemExit("The two passphrases differ.")
    return pw


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------

def fetch(url: str, token: str, name: str = OBJECT) -> bytes:
    req = urllib.request.Request(f"{url.rstrip('/')}/vault/{name}",
                                 headers={"Authorization": f"Bearer {token}", "User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise SystemExit("The vault refused the passphrase (or the vault has not been pushed yet).") from None
        raise


# ---------------------------------------------------------------------------
# Writing on the box
# ---------------------------------------------------------------------------

def _secure_dir(d: Path) -> None:
    d.mkdir(parents=True, exist_ok=True)
    if os.name == "posix":
        os.chmod(d, 0o700)


def _write_secret(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    os.replace(tmp, path)
    if os.name == "posix":
        os.chmod(path, 0o600)


def place(vault: dict, dest: Path, only: list[str] | None, keys: list[str] | None) -> list[str]:
    files = vault["files"]
    _secure_dir(dest)
    written = []
    if keys:
        merged = {}
        for text in files.values():
            merged.update(env_values(text))
        missing = [k for k in keys if k not in merged]
        if missing:
            raise SystemExit(f"Not in the vault: {', '.join(missing)}")
        body = "".join(f"{k}={merged[k]}\n" for k in keys)
        _write_secret(dest / "phoenix.env", body.encode())
        written.append(f"phoenix.env ({', '.join(keys)})")
    if only or not keys:
        names = only or sorted(files)
        missing = [n for n in names if n not in files]
        if missing:
            raise SystemExit(f"Not in the vault: {', '.join(missing)}")
        for n in names:
            _write_secret(dest / n, files[n].encode())
            written.append(n)
    return written


# ---------------------------------------------------------------------------
# Push (home PC only — needs wrangler logged in to the account)
# ---------------------------------------------------------------------------

def _npx() -> str:
    return "npx.cmd" if os.name == "nt" else "npx"


def push(vault_dir: Path, out: Path, worker_dir: Path, passphrase: str) -> None:
    files = read_vault(vault_dir)
    blob = seal(files, passphrase)
    assert unseal(blob, passphrase)["files"].keys() == {k for k in files}   # round-trip before upload
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(blob)
    print(f"sealed {len(files)} files -> {out} ({len(blob)} bytes): {', '.join(sorted(files))}")
    run = lambda *a, **kw: subprocess.run([_npx(), "wrangler", *a], cwd=worker_dir, check=True, **kw)
    run("r2", "object", "put", f"phoenix-vault/{OBJECT}", "--file", str(out), "--remote")
    run("r2", "object", "put", "phoenix-vault/phoenix_vault.py", "--file", str(Path(__file__).resolve()),
        "--content-type", "text/x-python", "--remote")
    run("secret", "put", "FETCH_HASH", input=fetch_hash(passphrase), text=True)   # stdin, never argv
    print("uploaded; fetch key registered")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="phoenix_vault.py", description="Phoenix secrets, encrypted end to end")
    ap.add_argument("--url", default=DEFAULT_URL, help="vault worker URL")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("push", help="encrypt the vault and upload it (home PC)")
    p.add_argument("--vault", type=Path, default=DEFAULT_VAULT)
    p.add_argument("--out", type=Path, default=Path("F:/Phoenix/bundles/phoenix-vault.enc"))
    p.add_argument("--worker-dir", type=Path,
                   default=Path(__file__).resolve().parents[1] / "sector4" / "vault" / "worker")
    sub.add_parser("list", help="names in the vault (no values)")
    sub.add_parser("verify", help="pull back and compare with the local vault; writes nothing")
    q = sub.add_parser("pull", help="write secrets onto this box")
    q.add_argument("--dest", type=Path, default=Path("/etc/phoenix/secrets") if os.name == "posix"
                   else Path.home() / ".phoenix" / "secrets")
    q.add_argument("--only", help="comma-separated file names (default: all)")
    q.add_argument("--keys", help="comma-separated KEY names → one phoenix.env with just those")
    a = ap.parse_args(argv)

    if a.cmd == "push":
        pw = ask_passphrase(confirm=True)
        push(a.vault, a.out, a.worker_dir, pw)
        return 0
    pw = ask_passphrase()
    vault = unseal(fetch(a.url, fetch_token(pw)), pw)
    if a.cmd == "list":
        print(f"vault sealed {vault['created_utc']}")
        for name, text in sorted(vault["files"].items()):
            print(f"  {name}: {', '.join(sorted(env_values(text))) or '(not KEY=value)'}")
    elif a.cmd == "verify":
        local = read_vault(DEFAULT_VAULT)
        remote = {k: v.encode() for k, v in vault["files"].items()}
        same = local == remote
        print("cloud copy matches the local vault" if same else
              f"DIFFERS — local only: {sorted(set(local) - set(remote))}, cloud only: {sorted(set(remote) - set(local))}, "
              f"changed: {sorted(k for k in set(local) & set(remote) if local[k] != remote[k])}")
        return 0 if same else 1
    elif a.cmd == "pull":
        split = lambda s: [x.strip() for x in s.split(",") if x.strip()] if s else None
        for w in place(vault, a.dest, split(a.only), split(a.keys)):
            print(f"  wrote {a.dest / w.split(' ')[0]}  {w[len(w.split(' ')[0]):]}".rstrip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
