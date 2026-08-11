#!/usr/bin/env python3
# =============================================================================
# intake.py — Phoenix DevOps TAV Intake
# Author:  jwl247 / Phoenix DevOps LLC
# Sector:  4 (breach_coms4 / master vault)
# Role:    Content-address a single file:
#            1. Compute SHA3-512 hex ID
#            2. Compute BLAKE2b-512 hex ID
#            3. Write/update sidecar.json alongside the file
#            4. Append a row to the local clone pool (SQLite catalog)
#
# Usage:
#   python3 intake.py <file_path>
#
# Environment (optional):
#   CLONEPOOL_DIR   — path to clonepool root   (default: ~/Documents/clonepool)
#   CATALOG_DB      — path to catalog.db       (default: ~/.catalog/catalog.db)
#   PHOENIX_ROOT    — repo root                (informational only)
# =============================================================================

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
CLONEPOOL_DIR    = Path(os.environ.get("CLONEPOOL_DIR",    Path.home() / "Documents" / "clonepool"))
CATALOG_DB       = Path(os.environ.get("CATALOG_DB",       Path.home() / ".catalog" / "catalog.db"))
WORKER_URL       = os.environ.get("PHOENIX_WORKER_URL", "").rstrip("/")
WORKER_AUTH      = os.environ.get("PHOENIX_AUTH", "")
VERSION = "0.3.0"


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------

def sha3_512_hex(path: Path) -> str:
    """Return the SHA3-512 hex digest of a file's contents."""
    h = hashlib.sha3_512()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def blake2b_hex(path: Path) -> str:
    """Return the BLAKE2b-512 hex digest of a file's contents."""
    h = hashlib.blake2b(digest_size=64)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Sidecar
# ---------------------------------------------------------------------------

def sidecar_path(file_path: Path) -> Path:
    """Return the sidecar JSON path for a given file."""
    return file_path.parent / (file_path.name + ".sidecar.json")


def read_sidecar(sc_path: Path) -> dict:
    """Read existing sidecar or return empty dict."""
    if sc_path.exists():
        try:
            return json.loads(sc_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def write_sidecar(sc_path: Path, data: dict) -> None:
    """Write sidecar JSON (pretty-printed, UTF-8)."""
    sc_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def update_sidecar(file_path: Path, sha3_hex: str, blake2_hex: str) -> Path:
    """
    Create or update the sidecar.json for file_path.
    Fills hash_sha3, hash_blake2, and intake metadata.
    Returns the sidecar path.
    """
    sc_path = sidecar_path(file_path)
    sidecar = read_sidecar(sc_path)

    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # Preserve any existing top-level fields (name, version, etc.)
    sidecar.update({
        "file":         file_path.name,
        "file_path":    str(file_path.resolve()),
        "hash_sha3":    sha3_hex,
        "hash_blake2":  blake2_hex,
        "hex_id":       sha3_hex,          # canonical content address used by clonepool
        "intake_ts":    now_iso,
        "intake_ver":   VERSION,
        "size_bytes":   file_path.stat().st_size,
    })

    # QR placeholder — real QR generation requires 'qrcode' or similar lib
    if not sidecar.get("qr_sha3"):
        sidecar["qr_sha3"]   = f"qr:sha3:{sha3_hex[:16]}"   # stub; replace with real QR encode
    if not sidecar.get("qr_blake2"):
        sidecar["qr_blake2"] = f"qr:blake2:{blake2_hex[:16]}"

    write_sidecar(sc_path, sidecar)
    return sc_path


# ---------------------------------------------------------------------------
# Catalog (SQLite)
# ---------------------------------------------------------------------------

CATALOG_SCHEMA = """
CREATE TABLE IF NOT EXISTS packages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    hex_id      TEXT    NOT NULL,
    file_name   TEXT    NOT NULL,
    file_path   TEXT    NOT NULL,
    sidecar_path TEXT,
    hash_sha3   TEXT    NOT NULL,
    hash_blake2 TEXT    NOT NULL,
    size_bytes  INTEGER,
    intake_ts   TEXT    NOT NULL,
    intake_ver  TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_packages_hex_id ON packages(hex_id);
"""


def ensure_catalog() -> sqlite3.Connection:
    """Open (and initialise if needed) the catalog SQLite DB."""
    CATALOG_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(CATALOG_DB))
    conn.executescript(CATALOG_SCHEMA)
    # Migrate older DBs that pre-date the hex_id column
    cols = {row[1] for row in conn.execute("PRAGMA table_info(packages)")}
    if "hex_id" not in cols:
        conn.execute("ALTER TABLE packages ADD COLUMN hex_id TEXT NOT NULL DEFAULT ''")
        conn.execute("UPDATE packages SET hex_id = hash_sha3 WHERE hex_id = ''")
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_packages_hex_id ON packages(hex_id)"
        )
    conn.commit()
    return conn


def catalog_upsert(
    conn: sqlite3.Connection,
    hex_id: str,
    file_path: Path,
    sc_path: Path,
    sha3_hex: str,
    blake2_hex: str,
) -> None:
    """
    Insert or update the catalog row for this file.
    Uses hex_id (SHA3-512) as the unique key — never mutates existing rows,
    inserts a new row if the hex_id is new.
    """
    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn.execute(
        """
        INSERT INTO packages
            (hex_id, file_name, file_path, sidecar_path, hash_sha3, hash_blake2,
             size_bytes, intake_ts, intake_ver)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(hex_id) DO UPDATE SET
            file_path    = excluded.file_path,
            sidecar_path = excluded.sidecar_path,
            intake_ts    = excluded.intake_ts,
            intake_ver   = excluded.intake_ver
        """,
        (
            hex_id,
            file_path.name,
            str(file_path.resolve()),
            str(sc_path.resolve()),
            sha3_hex,
            blake2_hex,
            file_path.stat().st_size,
            now_iso,
            VERSION,
        ),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# D1 sync — best-effort POST to packages-worker
# ---------------------------------------------------------------------------

_B58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"

def _base58(data: bytes) -> str:
    n = int.from_bytes(data, "big")
    result = ""
    while n:
        n, r = divmod(n, 58)
        result = _B58_ALPHABET[r] + result
    for byte in data:
        if byte == 0:
            result = _B58_ALPHABET[0] + result
        else:
            break
    return result


def d1_sync(
    hex_id: str,
    file_path: Path,
    sha3_hex: str,
    blake2_hex: str,
    clonepool_dest: Path | None,
    sidecar: Path,
) -> bool:
    """
    POST intake record to /clonepool and /custody on the packages-worker.
    Returns True on success. Non-fatal — never raises.
    """
    if not WORKER_URL or not WORKER_AUTH:
        return False

    b58 = _base58(bytes.fromhex(hex_id[:16]))
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    clonepool_payload = json.dumps({
        "hex_id":        hex_id,
        "b58":           b58,
        "name":          file_path.name,
        "original_name": file_path.name,
        "pool_path":     str(clonepool_dest) if clonepool_dest else None,
        "sidecar_path":  str(sidecar),
        "hash_sha3":     sha3_hex,
        "hash_blake2":   blake2_hex,
        "state":         "white",
        "tier":          1,
        "size":          file_path.stat().st_size,
        "version":       "v1",
    }).encode()

    custody_payload = json.dumps({
        "hex_id":  hex_id,
        "name":    file_path.name,
        "qr_top":  f"USYS:{b58}:HEADER",
        "qr_bottom": f"USYS:{b58}:FOOTER:{hex_id}",
        "state":   "white",
        "action":  "intake",
        "actor":   "intake.py",
    }).encode()

    headers = {
        "Content-Type":  "application/json",
        "Authorization": f"Bearer {WORKER_AUTH}",
        "User-Agent":    "Phoenix-Intake/0.3.0",
    }

    for endpoint, payload in (
        ("/clonepool", clonepool_payload),
        ("/custody",   custody_payload),
    ):
        try:
            req = urllib.request.Request(
                f"{WORKER_URL}{endpoint}",
                data=payload,
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                pass  # 200 is enough — no body needed
        except Exception as e:
            print(f"  [warn] D1 sync {endpoint} failed: {e}")
            return False

    return True


# ---------------------------------------------------------------------------
# Clone-pool copy
# ---------------------------------------------------------------------------

def clonepool_copy(file_path: Path, hex_id: str) -> Path:
    """
    Copy the file into the local clone pool under:
      CLONEPOOL_DIR/<hex_id[:2]>/<hex_id[2:4]>/<hex_id>/
    Returns the destination directory.
    Skips copy if the destination file already exists (content-addressed = immutable).
    """
    dest_dir = CLONEPOOL_DIR / hex_id[:2] / hex_id[2:4] / hex_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_file = dest_dir / file_path.name
    if not dest_file.exists():
        import shutil
        shutil.copy2(str(file_path), str(dest_file))
    return dest_dir


# ---------------------------------------------------------------------------
# Main intake
# ---------------------------------------------------------------------------

def intake_file(file_path: Path, *, skip_clone: bool = False) -> dict:
    """
    Full intake pipeline for a single file.
    Returns a result dict with all computed values.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    if not file_path.is_file():
        raise ValueError(f"Not a regular file: {file_path}")

    print(f"[intake] {file_path}")

    # 1. Hash
    sha3_hex  = sha3_512_hex(file_path)
    blake2_hex = blake2b_hex(file_path)
    print(f"  sha3-512  : {sha3_hex[:24]}...")
    print(f"  blake2b   : {blake2_hex[:24]}...")

    # 2. Sidecar
    sc_path = update_sidecar(file_path, sha3_hex, blake2_hex)
    print(f"  sidecar   : {sc_path}")

    # 3. Catalog
    conn = ensure_catalog()
    catalog_upsert(conn, sha3_hex, file_path, sc_path, sha3_hex, blake2_hex)
    conn.close()
    print(f"  catalog   : {CATALOG_DB}")

    # 4. Clone pool
    if not skip_clone:
        dest_dir = clonepool_copy(file_path, sha3_hex)
        print(f"  clonepool : {dest_dir}")
    else:
        dest_dir = None

    # 5. D1 sync (best-effort)
    synced = d1_sync(sha3_hex, file_path, sha3_hex, blake2_hex, dest_dir, sc_path)
    if synced:
        print(f"  d1 sync  : ok")
    elif WORKER_URL:
        print(f"  d1 sync  : skipped (check PHOENIX_AUTH / PHOENIX_WORKER_URL)")
    else:
        print(f"  d1 sync  : offline (PHOENIX_WORKER_URL not set)")

    print(f"  OK hex_id={sha3_hex[:16]}...")

    return {
        "hex_id":     sha3_hex,
        "hash_sha3":  sha3_hex,
        "hash_blake2": blake2_hex,
        "file_path":  str(file_path.resolve()),
        "sidecar":    str(sc_path),
        "catalog":    str(CATALOG_DB),
        "clonepool":  str(dest_dir) if dest_dir else None,
        "d1_synced":  synced,
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description=f"Phoenix TAV intake v{VERSION} — content-address a file into the clone pool",
    )
    parser.add_argument("file", help="path to the file to ingest")
    parser.add_argument("--no-clone", action="store_true",
                        help="skip copying the file into the clone pool (hash + sidecar + catalog only)")
    args = parser.parse_args()

    try:
        result = intake_file(Path(args.file), skip_clone=args.no_clone)
        return 0
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"FATAL: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
