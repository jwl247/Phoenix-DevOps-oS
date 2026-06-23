#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║  Phoenix Bridge Kernel                                       ║
║  Runs in WSL2 / Linux                                        ║
║                                                              ║
║  Listens on TCP 9900 — reachable from Windows side          ║
║  and from Linux side (linux_concierge.py)                   ║
║                                                              ║
║  Chops incoming envelopes.                                   ║
║  Hands chunks to Frank for pressure-aware routing.          ║
║  Returns native output back to whoever asked.               ║
║                                                              ║
║  Does not care what the data is.                            ║
║  Does not care who sent it.                                  ║
║  Just chops and routes.                                      ║
╚══════════════════════════════════════════════════════════════╝
"""

import os
import sys
import json
import socket
import threading
import time
import hashlib
import struct

BRIDGE_HOST  = os.environ.get("PHOENIX_BRIDGE_HOST", "0.0.0.0")
BRIDGE_PORT  = int(os.environ.get("PHOENIX_BRIDGE_PORT", "9900"))
FRANK_HOST   = os.environ.get("PHOENIX_FRANK_HOST",  "127.0.0.1")
FRANK_PORT   = int(os.environ.get("PHOENIX_FRANK_PORT",  "7347"))  # frank HTTP bridge
CHUNK_SIZE   = int(os.environ.get("PHOENIX_CHUNK_SIZE", "4096"))
MAX_CHUNKS   = int(os.environ.get("PHOENIX_MAX_CHUNKS", "256"))

# ── CHUNK HEADER ──────────────────────────────────────────────────────────────
# Each chunk gets a lightweight header Frank can read at ring 0 speed:
#   magic(4) + seq(4) + total(4) + size(4) + checksum(8) = 24 bytes
CHUNK_MAGIC  = b"PHNX"
HEADER_FMT   = "!4sIII8s"   # big-endian
HEADER_SIZE  = struct.calcsize(HEADER_FMT)  # 24 bytes

def make_chunk(seq: int, total: int, data: bytes) -> bytes:
    chk = hashlib.blake2b(data, digest_size=8).digest()
    hdr = struct.pack(HEADER_FMT, CHUNK_MAGIC, seq, total, len(data), chk)
    return hdr + data

def parse_chunk(raw: bytes) -> dict:
    if len(raw) < HEADER_SIZE:
        return None
    magic, seq, total, size, chk = struct.unpack_from(HEADER_FMT, raw)
    if magic != CHUNK_MAGIC:
        return None
    data = raw[HEADER_SIZE: HEADER_SIZE + size]
    expected = hashlib.blake2b(data, digest_size=8).digest()
    return {
        "seq":      seq,
        "total":    total,
        "size":     size,
        "checksum_ok": chk == expected,
        "data":     data,
    }

# ── CHOPPER ───────────────────────────────────────────────────────────────────
def chop(payload: bytes) -> list[bytes]:
    """
    Split payload into CHUNK_SIZE chunks.
    Each chunk gets a header Frank can validate independently.
    """
    chunks = []
    total  = (len(payload) + CHUNK_SIZE - 1) // CHUNK_SIZE or 1
    for seq, off in enumerate(range(0, max(len(payload), 1), CHUNK_SIZE)):
        data = payload[off: off + CHUNK_SIZE]
        chunks.append(make_chunk(seq, total, data))
    return chunks

def reassemble(chunks: list[bytes]) -> bytes:
    """Reassemble validated chunks back into original payload."""
    parsed = [parse_chunk(c) for c in chunks]
    parsed = [p for p in parsed if p and p["checksum_ok"]]
    parsed.sort(key=lambda p: p["seq"])
    return b"".join(p["data"] for p in parsed)

# ── FRANK ROUTER ──────────────────────────────────────────────────────────────
def route_to_frank(envelope: dict, chunks: list[bytes]) -> dict:
    """
    Hand envelope + chunks to Frank3 HTTP bridge at port 7347.
    Frank decides tier, pressure, vault path.
    Falls back gracefully if Frank is offline.
    """
    try:
        import urllib.request
        import urllib.error

        payload = json.dumps({
            "doc_id":   envelope.get("source", "bridge"),
            "title":    envelope.get("source", "bridge"),
            "doc_type": envelope.get("family", "system"),
            "content":  reassemble(chunks).decode(errors="replace"),
        }).encode()

        req = urllib.request.Request(
            f"http://{FRANK_HOST}:{FRANK_PORT}/save",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=3) as r:
            return json.loads(r.read())

    except Exception as exc:
        # Frank offline — return the data anyway, log the miss
        return {
            "ok":      True,
            "routed":  False,
            "frank":   str(exc),
            "chunks":  len(chunks),
            "payload": reassemble(chunks).decode(errors="replace")[:256],
        }

# ── BRIDGE STATS ──────────────────────────────────────────────────────────────
class BridgeStats:
    def __init__(self):
        self.received  = 0
        self.chopped   = 0
        self.routed    = 0
        self.errors    = 0
        self.bytes_in  = 0
        self.bytes_out = 0
        self._lock     = threading.Lock()

    def bump(self, **kwargs):
        with self._lock:
            for k, v in kwargs.items():
                setattr(self, k, getattr(self, k) + v)

    def snapshot(self) -> dict:
        with self._lock:
            return {k: v for k, v in self.__dict__.items()
                    if not k.startswith("_")}

stats = BridgeStats()

# ── CONNECTION HANDLER ────────────────────────────────────────────────────────
def handle(conn: socket.socket, addr):
    """
    One connection from either side — Windows concierge or Linux concierge.
    Receive envelope. Chop. Route to Frank. Return result.
    """
    try:
        chunks_raw = []
        while True:
            chunk = conn.recv(65536)
            if not chunk:
                break
            chunks_raw.append(chunk)

        raw = b"".join(chunks_raw)
        if not raw:
            return

        stats.bump(received=1, bytes_in=len(raw))

        # parse envelope
        try:
            envelope = json.loads(raw)
        except Exception:
            envelope = {
                "source": str(addr),
                "family": "raw",
                "data":   raw.decode(errors="replace"),
            }

        # get data bytes
        data_str = envelope.get("data", "")
        data_bytes = (data_str.encode()
                      if isinstance(data_str, str)
                      else data_str)

        # chop
        chopped = chop(data_bytes)
        stats.bump(chopped=len(chopped))

        log(f"← {addr}  family={envelope.get('family','?')}  "
            f"{len(data_bytes)}b → {len(chopped)} chunks")

        # route to Frank
        result = route_to_frank(envelope, chopped)
        result["chunks_sent"] = len(chopped)
        result["bridge"] = "phoenix-bridge-kernel"

        stats.bump(routed=1, bytes_out=len(json.dumps(result)))

        conn.sendall(json.dumps(result).encode())

    except Exception as exc:
        stats.bump(errors=1)
        try:
            conn.sendall(json.dumps({"ok": False, "error": str(exc)}).encode())
        except Exception:
            pass
    finally:
        conn.close()

# ── STATUS THREAD ─────────────────────────────────────────────────────────────
def status_loop():
    """Print bridge stats every 30s — visible in WSL2 terminal."""
    while True:
        time.sleep(30)
        s = stats.snapshot()
        log(f"stats  recv={s['received']}  chopped={s['chopped']}  "
            f"routed={s['routed']}  err={s['errors']}  "
            f"in={s['bytes_in']}b  out={s['bytes_out']}b")

def log(msg: str):
    print(f"[bridge] {msg}", flush=True)

# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((BRIDGE_HOST, BRIDGE_PORT))
    srv.listen(128)

    log(f"Phoenix Bridge Kernel")
    log(f"listening  {BRIDGE_HOST}:{BRIDGE_PORT}")
    log(f"frank3     {FRANK_HOST}:{FRANK_PORT}")
    log(f"chunk_size {CHUNK_SIZE}b  max_chunks {MAX_CHUNKS}")
    log(f"WSL2 gap bridged — Windows concierge can reach this on 127.0.0.1:{BRIDGE_PORT}")

    threading.Thread(target=status_loop, daemon=True).start()

    while True:
        try:
            conn, addr = srv.accept()
            threading.Thread(
                target=handle,
                args=(conn, addr),
                daemon=True
            ).start()
        except KeyboardInterrupt:
            break
        except Exception as exc:
            log(f"accept error: {exc}")

    srv.close()
    log("stopped")

if __name__ == "__main__":
    main()
