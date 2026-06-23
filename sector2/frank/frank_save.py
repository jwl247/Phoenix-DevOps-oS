"""
frank_save.py — Phoenix Office save scheduler
Frank3 decides when, where, and how documents get written.
No passwords. No config. Frank reads the drives and decides.
"""

import os
import time
import json
import hashlib
import sqlite3
import threading
import subprocess
from pathlib import Path
from datetime import datetime
from collections import deque

# ── CONSTANTS ────────────────────────────────────────────────────────────────
DRIVES = [
    "/mnt/d",
    "/mnt/e",   # CLONEPOOL primary
    "/mnt/f",
    "/mnt/g",
]
CLONEPOOL     = "/mnt/e/CLONEPOOL"
CATALOG_DB    = os.path.expanduser("~/.catalog/catalog.db")
VAULT_BASE    = CLONEPOOL
DISPATCH_JSON = os.path.expanduser("~/projects/phoenix/dispatch.json")

# Frank3 pressure thresholds (mirrors frankenhelix.py)
PRESSURE_LOW  = 60   # write freely
PRESSURE_MED  = 75   # prefer less-loaded drive
PRESSURE_HIGH = 88   # buffer in L2, defer write

# Helix L2 buffer — holds pending saves when all drives are hot
_l2_buffer: deque = deque(maxlen=256)
_buffer_lock = threading.Lock()

# ── DRIVE PRESSURE ────────────────────────────────────────────────────────────
def drive_pressure(path: str) -> float:
    """Return used% for the filesystem containing path. Returns 100 if offline."""
    try:
        st = os.statvfs(path)
        used = (st.f_blocks - st.f_bfree) * st.f_frsize
        total = st.f_blocks * st.f_frsize
        return round((used / total) * 100, 1) if total else 100.0
    except OSError:
        return 100.0   # drive offline → treat as full

def best_drive() -> str | None:
    """Frank picks the drive with the lowest pressure that's under PRESSURE_MED."""
    candidates = []
    for d in DRIVES:
        if os.path.exists(d):
            p = drive_pressure(d)
            if p < PRESSURE_MED:
                candidates.append((p, d))
    if not candidates:
        return None   # all hot — buffer it
    candidates.sort()
    return candidates[0][1]

def system_pressure() -> dict:
    """Snapshot of all drive pressures — fed to the Frank3 UI bar."""
    return {
        d.split("/")[-1]: drive_pressure(d)
        for d in DRIVES
    }

# ── CATALOG ───────────────────────────────────────────────────────────────────
def _ensure_catalog():
    os.makedirs(os.path.dirname(CATALOG_DB), exist_ok=True)
    con = sqlite3.connect(CATALOG_DB)
    con.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id          TEXT PRIMARY KEY,
            title       TEXT,
            doc_type    TEXT,
            vault_path  TEXT,
            checksum    TEXT,
            saved_at    TEXT,
            drive       TEXT,
            size_bytes  INTEGER,
            version     INTEGER DEFAULT 1
        )
    """)
    con.commit()
    return con

def catalog_register(doc_id, title, doc_type, vault_path, checksum, drive, size):
    con = _ensure_catalog()
    now = datetime.utcnow().isoformat()
    # bump version if exists
    row = con.execute("SELECT version FROM documents WHERE id=?", (doc_id,)).fetchone()
    version = (row[0] + 1) if row else 1
    con.execute("""
        INSERT OR REPLACE INTO documents
            (id, title, doc_type, vault_path, checksum, saved_at, drive, size_bytes, version)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, (doc_id, title, doc_type, vault_path, checksum, now, drive, size, version))
    con.commit()
    con.close()
    return version

# ── VAULT WRITE ───────────────────────────────────────────────────────────────
def vault_write(doc_id: str, title: str, doc_type: str, content: str | bytes, drive: str) -> dict:
    """
    Write document into the vault with versioned path:
      <drive>/VAULT/<doc_type>/<doc_id>/<timestamp>.<ext>
    Returns metadata dict.
    """
    if isinstance(content, str):
        content = content.encode("utf-8")

    ext = {"doc": "txt", "sheet": "csv", "slide": "json", "draw": "svg"}.get(doc_type, "bin")
    ts  = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    vault_dir = Path(drive) / "VAULT" / doc_type / doc_id
    vault_dir.mkdir(parents=True, exist_ok=True)
    vault_path = vault_dir / f"{ts}.{ext}"

    vault_path.write_bytes(content)

    checksum = hashlib.blake2b(content, digest_size=32).hexdigest()
    size     = len(content)
    version  = catalog_register(doc_id, title, doc_type, str(vault_path), checksum, drive, size)

    return {
        "vault_path": str(vault_path),
        "checksum":   checksum,
        "version":    version,
        "drive":      drive,
        "size":       size,
        "ts":         ts,
    }

# ── DISPATCH ──────────────────────────────────────────────────────────────────
def _load_dispatch() -> dict:
    try:
        return json.loads(Path(DISPATCH_JSON).read_text())
    except Exception:
        # default routing if dispatch.json missing
        return {"targets": ["vault", "sql"], "d1_sync": False, "frank3": True}

def _dispatch_d1(doc_id, title, doc_type, content_str, meta):
    """Fan out to D1 via propagator.py if dispatch says so."""
    try:
        payload = json.dumps({
            "action":   "upsert",
            "table":    "documents",
            "id":       doc_id,
            "title":    title,
            "doc_type": doc_type,
            "content":  content_str[:4096],   # D1 summary, not full blob
            "checksum": meta["checksum"],
            "version":  meta["version"],
        })
        propagator = Path("~/projects/phoenix/propagator.py").expanduser()
        if propagator.exists():
            subprocess.Popen(
                ["python3", str(propagator), "--target", "d1", "--payload", payload],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
    except Exception:
        pass   # D1 sync is best-effort, never blocks the save

# ── BUFFER FLUSH ──────────────────────────────────────────────────────────────
def _flush_buffer():
    """Frank drains the L2 buffer when drives cool down. Runs in background."""
    while True:
        time.sleep(2)
        with _buffer_lock:
            if not _l2_buffer:
                continue
            drive = best_drive()
            if drive is None:
                continue   # still hot, wait
            # flush oldest item
            item = _l2_buffer.popleft()

        try:
            meta = vault_write(
                item["doc_id"], item["title"], item["doc_type"],
                item["content"], drive
            )
            dispatch = _load_dispatch()
            if dispatch.get("d1_sync"):
                _dispatch_d1(item["doc_id"], item["title"], item["doc_type"],
                             item["content"] if isinstance(item["content"], str)
                             else item["content"].decode("utf-8", errors="replace"), meta)
        except Exception:
            # re-queue on failure
            with _buffer_lock:
                _l2_buffer.appendleft(item)

_flush_thread = threading.Thread(target=_flush_buffer, daemon=True)
_flush_thread.start()

# ── PUBLIC API ────────────────────────────────────────────────────────────────
def frank_save(doc_id: str, title: str, doc_type: str, content: str | bytes) -> dict:
    """
    The one function Phoenix Office calls to save anything.
    Frank handles the rest.

    Returns:
        { status, drive, pressure, version, vault_path, buffered }
    """
    pressures = system_pressure()
    drive = best_drive()

    content_str = content if isinstance(content, str) else content.decode("utf-8", errors="replace")

    # ── ALL DRIVES HOT → buffer in L2 ────────────────────────────────────────
    if drive is None:
        with _buffer_lock:
            _l2_buffer.append({
                "doc_id":   doc_id,
                "title":    title,
                "doc_type": doc_type,
                "content":  content,
            })
        return {
            "status":    "buffered",
            "buffered":  True,
            "pressure":  pressures,
            "queue_len": len(_l2_buffer),
            "message":   "All drives above threshold — Frank buffered in L2 Helix. Will flush when pressure drops.",
        }

    # ── NORMAL WRITE ─────────────────────────────────────────────────────────
    meta = vault_write(doc_id, title, doc_type, content, drive)

    # fan out to D1 if dispatch says so
    dispatch = _load_dispatch()
    if dispatch.get("d1_sync"):
        _dispatch_d1(doc_id, title, doc_type, content_str, meta)

    drive_name = Path(drive).name
    p = pressures.get(drive_name, 0)

    return {
        "status":     "saved",
        "buffered":   False,
        "drive":      drive,
        "drive_name": drive_name,
        "pressure":   pressures,
        "this_drive": p,
        "vault_path": meta["vault_path"],
        "checksum":   meta["checksum"],
        "version":    meta["version"],
        "size":       meta["size"],
        "message":    f"Saved to {drive_name} at {p}% pressure (v{meta['version']})",
    }

def frank_status() -> dict:
    """Lightweight poll endpoint for the Frank3 UI bar."""
    pressures = system_pressure()
    drive = best_drive()
    buf_len = len(_l2_buffer)
    total = sum(pressures.values())
    avg   = round(total / len(pressures), 1) if pressures else 0
    tier  = "L1" if avg < PRESSURE_LOW else "L2" if avg < PRESSURE_MED else "L3"
    return {
        "drives":    pressures,
        "avg":       avg,
        "tier":      tier,
        "best":      Path(drive).name if drive else None,
        "buffered":  buf_len,
        "thresholds": {"low": PRESSURE_LOW, "med": PRESSURE_MED, "high": PRESSURE_HIGH},
    }

# ── CLI SMOKE TEST ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("── Frank3 save scheduler ──")
    print("Status:", json.dumps(frank_status(), indent=2))
    print()
    result = frank_save(
        doc_id   = "test-doc-001",
        title    = "Test Document",
        doc_type = "doc",
        content  = "Hello from Phoenix Office. Frank3 picked this drive."
    )
    print("Save result:", json.dumps(result, indent=2))
