#!/usr/bin/env python3
"""
helix_ring.py — Helix's lossless event ring (multi-writer, multi-reader, cross-process)
Phoenix DevOps OS | jwl247 | GPL v3

Why it exists: the SharedMemoryBus slot model (franken5.write_stage) keeps ONE
4 KiB payload per slot — last writer wins, so two game events written before
anyone reads the slot lose the first one silently, the lock only works inside
one process, and Helix-E's read-then-clear can wipe an event that arrived in
between. With several players acting at once that is real data loss.

The ring fixes the event path without touching the slot bus:
  - append-only: every event gets a sequence number; nothing is overwritten
    until the ring wraps
  - readers keep their own cursor (seq + position); reading never clears
  - one lock across threads AND processes (file lock + in-process lock)
  - if a reader falls a full ring behind, it is told exactly how many events
    it missed — never silent — and resyncs to the newest
  - events larger than the ring's quarter are refused loudly

File layout (memory-mapped, little-endian):
  header 64 B: magic b"HXRING1\\0" | capacity u64 | head u64 (bytes written, ever)
               | next_seq u64 | reserved
  data: capacity bytes, circular. Record = u32 length | u32 channel | u64 seq
               | payload | pad to 8. length == 0xFFFFFFFF is a wrap marker.

Channels follow Helix-Lightning: 1-4 ingress strand A, 5-8 egress strand B.
"""

from __future__ import annotations

import mmap
import os
import struct
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator, Optional

MAGIC = b"HXRING1\0"
HEADER = 64
REC_HDR = struct.Struct("<IIQ")          # length, channel, seq
WRAP = 0xFFFFFFFF
DEFAULT_CAPACITY = 16 * 1024 * 1024      # 16 MiB of events


def _pad8(n: int) -> int:
    return (n + 7) & ~7


class _FileLock:
    """Exclusive lock on a sidecar lock file — holds across processes on Windows and Linux."""

    def __init__(self, path: Path):
        self._fh = open(path, "a+b")
        if os.name == "nt":
            self._fh.seek(0, 2)
            if self._fh.tell() == 0:
                self._fh.write(b"\0")
                self._fh.flush()

    def acquire(self) -> None:
        if os.name == "nt":
            import msvcrt
            self._fh.seek(0)
            while True:
                try:
                    msvcrt.locking(self._fh.fileno(), msvcrt.LK_LOCK, 1)   # retries for ~10 s
                    return
                except OSError:
                    continue
        else:
            import fcntl
            fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX)

    def release(self) -> None:
        if os.name == "nt":
            import msvcrt
            self._fh.seek(0)
            msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)

    def close(self) -> None:
        self._fh.close()


@dataclass
class Event:
    seq:     int
    channel: int
    payload: bytes


@dataclass
class Cursor:
    seq: int = 0          # next sequence number this reader expects
    pos: int = 0          # absolute byte position (head-relative, never wrapped)
    missed: int = 0       # events lost to a lap, ever — callers must surface this


class HelixRing:
    def __init__(self, path: Path, capacity: int = DEFAULT_CAPACITY):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._tlock = threading.Lock()
        self._flock = _FileLock(self.path.with_suffix(self.path.suffix + ".lock"))
        with self._locked():
            new = not self.path.exists() or self.path.stat().st_size < HEADER
            if new:
                with open(self.path, "wb") as f:
                    f.truncate(HEADER + capacity)
            self._fh = open(self.path, "r+b")
            self._mm = mmap.mmap(self._fh.fileno(), 0)
            if new or self._mm[:8] != MAGIC:
                self._mm[:HEADER] = MAGIC + struct.pack("<QQQ", capacity, 0, 0) + b"\0" * (HEADER - 32)
        self.capacity = struct.unpack_from("<Q", self._mm, 8)[0]
        self.max_payload = self.capacity // 4 - REC_HDR.size

    # -- locking --------------------------------------------------------------

    def _locked(self):
        ring = self

        class _Ctx:
            def __enter__(self_inner):
                ring._tlock.acquire()
                ring._flock.acquire()

            def __exit__(self_inner, *exc):
                ring._flock.release()
                ring._tlock.release()
        return _Ctx()

    def _head(self) -> tuple[int, int]:
        return struct.unpack_from("<QQ", self._mm, 16)

    # -- write ----------------------------------------------------------------

    def publish(self, channel: int, payload: bytes) -> int:
        """Append one event. Returns its sequence number."""
        if not 1 <= channel <= 255:
            raise ValueError(f"channel {channel} out of range")
        if len(payload) > self.max_payload:
            raise ValueError(f"event of {len(payload)} bytes exceeds the ring's limit ({self.max_payload})")
        size = _pad8(REC_HDR.size + len(payload))
        with self._locked():
            head, seq = self._head()
            off = head % self.capacity
            if off + size > self.capacity:                       # no room before the end: wrap
                if self.capacity - off >= 4:
                    struct.pack_into("<I", self._mm, HEADER + off, WRAP)
                head += self.capacity - off
                off = 0
            base = HEADER + off
            REC_HDR.pack_into(self._mm, base, len(payload), channel, seq)
            self._mm[base + REC_HDR.size: base + REC_HDR.size + len(payload)] = payload
            struct.pack_into("<QQ", self._mm, 16, head + size, seq + 1)
            return seq

    # -- read -----------------------------------------------------------------

    def cursor_at_end(self) -> Cursor:
        with self._locked():
            head, seq = self._head()
        return Cursor(seq=seq, pos=head)

    def read(self, cur: Cursor, channel: Optional[int] = None, limit: int = 10_000) -> list[Event]:
        """Events after the cursor (advancing it). Never clears anything."""
        out: list[Event] = []
        with self._locked():
            head, next_seq = self._head()
            if head - cur.pos > self.capacity:                   # lapped: the oldest bytes are gone
                cur.missed += next_seq - cur.seq
                cur.seq, cur.pos = next_seq, head
                return out
            while cur.pos < head and len(out) < limit:
                off = cur.pos % self.capacity
                if self.capacity - off < 4 or struct.unpack_from("<I", self._mm, HEADER + off)[0] == WRAP:
                    cur.pos += self.capacity - off
                    continue
                length, ch, seq = REC_HDR.unpack_from(self._mm, HEADER + off)
                if seq != cur.seq:                               # never silent about gaps
                    cur.missed += max(0, seq - cur.seq)
                start = HEADER + off + REC_HDR.size
                if channel is None or ch == channel:
                    out.append(Event(seq, ch, bytes(self._mm[start:start + length])))
                cur.pos += _pad8(REC_HDR.size + length)
                cur.seq = seq + 1
        return out

    def drain_to(self, cur: Cursor, emit: Callable[[int, bytes], None], channel: Optional[int] = None) -> int:
        """Hand every new event to `emit(channel, payload)` — e.g. HelixE.emit. Returns how many."""
        events = self.read(cur, channel)
        for e in events:
            emit(e.channel, e.payload)
        return len(events)

    def stats(self) -> dict:
        head, seq = self._head()
        return {"capacity": self.capacity, "bytes_written": head, "events": seq}

    def close(self) -> None:
        self._mm.close()
        self._fh.close()
        self._flock.close()


class RingBus:
    """
    Drop-in for code that calls `frank.bus.write_stage(slot, data)` (the game's
    modules do): routes the write into the ring on channel slot+1 instead of
    overwriting the slot.
    """

    def __init__(self, ring: HelixRing):
        self.ring = ring

    def write_stage(self, slot: int, data: bytes) -> int:
        return self.ring.publish(slot + 1, data)


class RingFrank:
    """Looks like a Frank to the game modules (has `.bus`), backed by the ring."""

    def __init__(self, ring: HelixRing):
        self.bus = RingBus(ring)
        self.ring = ring


def default_ring_path() -> Path:
    base = os.environ.get("PHOENIX_SHM") or os.path.join(os.environ.get("TEMP", "/tmp"), "phoenix_shm")
    return Path(base).parent / "helix_events.ring" if Path(base).suffix else Path(base) / "helix_events.ring"
