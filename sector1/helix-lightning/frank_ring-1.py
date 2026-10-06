#!/usr/bin/env python3
"""
frank_ring.py — Frank Ring Lifecycle
Phoenix DevOps OS | jwl247 | GPL v3

Mount → Run → Sync → Die.
The ring is the unit of work.
Frank wears a suit. The suit runs. The ball tracks custody.
If PCS p3 >= 90, definitive=True and the snap-clone fires.

Snap clone: dual-hash (SHA3-256 + BLAKE2b-512), persist to
~/.phoenix/clonepool/ (guaranteed), then async S3 push if
PHOENIX_S3_BUCKET is set. The ball's custody chain bakes in.
That is the chain of evidence.
"""

import os
import sys
import time
import logging
import importlib
import importlib.util
import subprocess
import threading
import json
import hashlib
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Any
from enum import IntEnum

from franken5 import (
    Frank5, get_frank, RingRecord, RingState, Ball, PCS,
    DataFamily, FRANK_VERSION
)

RING_VERSION = "1.2.0"

log = logging.getLogger("frank_ring")


class SuitType(IntEnum):
    PYTHON = 0
    SHELL  = 1
    BINARY = 2
    NODE   = 3
    POWER  = 4


# Sector definitions — all four sectors, all sixteen core rings
SECTOR_MAP = {
    1: {"name": "Boot/Kernel",    "rings": {0: "frank3_slot_a", 1: "frank3_slot_b", 2: "phoenix_auth",  3: "concierge"}},
    2: {"name": "Intake/Package", "rings": {0: "intake",         1: "clone_pool",    2: "propagator",    3: "packages_worker"}},
    3: {"name": "Comms/Network",  "rings": {0: "romeo",          1: "juliet",        2: "dbl_juliet",    3: "quadengine"}},
    4: {"name": "Core Engine",    "rings": {0: "helix",          1: "freewheeling",  2: "propcoms",      3: "conductor"}},
}


@dataclass
class SuitSpec:
    name:        str
    suit_type:   SuitType
    entry:       str
    sector:      int
    ring_pos:    int
    family:      str  = DataFamily.SYSTEM
    permissions: dict = field(default_factory=dict)
    args:        list = field(default_factory=list)
    env:         dict = field(default_factory=dict)
    timeout:     float = 30.0
    description: str  = ""


def suit_for(sector: int, ring_pos: int, suit_type: SuitType = SuitType.PYTHON,
             entry: str = "") -> SuitSpec:
    """
    Build a SuitSpec for the named sector/ring_pos slot.
    Looks up the canonical ring name from SECTOR_MAP first.
    Falls back to a deterministic name if the slot is off-map.
    """
    name = (
        SECTOR_MAP.get(sector, {})
                  .get("rings", {})
                  .get(ring_pos, f"suit_s{sector}r{ring_pos}")
    )
    return SuitSpec(
        name        = name,
        suit_type   = suit_type,
        entry       = entry or name,
        sector      = sector,
        ring_pos    = ring_pos,
        family      = DataFamily.SYSTEM,
        permissions = {
            "read": True, "write": True, "clone": True,
            "translate": sector == 3, "delete": False, "kernel": sector == 1,
        },
    )


def wear(suit: SuitSpec, data: bytes = b"", channel: int = 1) -> Any:
    """Convenience — build a ring, ride it, return result."""
    ring = FrankRing(suit)
    return ring.ride(data=data, channel=channel)


class FrankRing:
    def __init__(self, suit: SuitSpec, frank: Optional[Frank5] = None):
        self.suit   = suit
        self.frank  = frank or get_frank()
        self.rec:   Optional[RingRecord] = None
        self._result: Any = None
        self._lock  = threading.Lock()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def mount(self, channel: int = 1, data: bytes = b"") -> RingRecord:
        self.rec = self.frank.spawn_ring(
            process_name = self.suit.name,
            channel      = channel,
            family       = self.suit.family,
            permissions  = self.suit.permissions,
            sector       = self.suit.sector,
            ring_pos     = self.suit.ring_pos,
        )
        if self.rec and self.rec.ball:
            self.rec.ball.hand_off("frank5_core", self.suit.name)
        return self.rec

    def run(self, data: bytes = b"", **kwargs) -> Any:
        if not self.rec or self.rec.state == RingState.DEAD:
            raise RuntimeError(
                f"Ring {self.rec.ring_id if self.rec else 'N/A'} is dead — cannot run"
            )

        self.frank.mark_running(self.rec.ring_id, os.getpid())
        self.rec.call2(data or self.suit.name.encode())

        try:
            if self.suit.suit_type == SuitType.PYTHON:
                self._result = self._run_python(data, **kwargs)
            else:
                self._result = self._run_subprocess(data)
            return self._result
        except Exception as e:
            log.error(f"Ring {self.rec.ring_id} execution failed: {e}")
            raise

    def sync(self, final_data: bytes = b"") -> bool:
        """
        Call3 closes the PCS chain.
        If p3 >= 90 the chain is definitive — fire the snap clone.
        Returns True when definitive.
        """
        if not self.rec:
            return False

        self.frank.mark_syncing(self.rec.ring_id)
        payload    = final_data or json.dumps({"result": str(self._result)}).encode()
        self.rec.call3(payload)

        definitive = bool(getattr(self.rec.pcs, "definitive", False))
        if definitive:
            # PCS chain is locked. Snap clone fires NOW.
            self._snap_clone()

        return definitive

    def die(self):
        if not self.rec:
            return
        self.rec.died  = time.monotonic()
        self.rec.state = RingState.DONE
        self.frank.bus.write_ring_state(self.rec.ring_id, RingState.DONE)
        custody = self.rec.to_custody_record()
        self.frank._commit_custody(custody)
        log.info(f"Ring {self.rec.ring_id} terminated cleanly")

    def ride(self, data: bytes = b"", channel: int = 1, **kwargs) -> Any:
        """Main entry: mount → run → sync (snap-clone if definitive) → die."""
        try:
            self.mount(channel=channel, data=data)
            if not self.rec or self.rec.state == RingState.DEAD:
                return None
            result = self.run(data=data, **kwargs)
            self.sync(final_data=data)
            return result
        finally:
            self.die()

    # ------------------------------------------------------------------
    # Snap Clone
    # ------------------------------------------------------------------

    def _snap_clone(self):
        """
        Snap clone — fires when PCS call3() returns definitive=True (p3 >= 90).

        Captures full ring state, dual-hashes with SHA3-256 + BLAKE2b-512,
        and persists:
          1. Local ~/.phoenix/clonepool/<ring_id>_<sha3[:16]>.json (synchronous,
             guaranteed — this is the chain of evidence)
          2. S3 bucket async push if PHOENIX_S3_BUCKET env var is set

        The ball's custody chain is embedded in the snapshot — every hand-off
        that led to this definitive state is recorded. The dual hash fingerprints
        the entire record. Together these constitute the tamper-evident chain of
        custody Frank was designed to provide.

        Never blocks the ring lifecycle — S3 push is daemon-thread fire-and-forget.
        Local write is synchronous and is the canonical copy.
        """
        if not self.rec:
            log.warning("[snap_clone] No ring record — cannot snap")
            return

        ring_id   = self.rec.ring_id
        suit_name = self.suit.name

        # ── Build snapshot ────────────────────────────────────────────
        try:
            ball      = self.rec.ball
            pcs       = self.rec.pcs

            ball_chain  = list(getattr(ball,  "custody_chain", [])) if ball else []
            ball_family = str(getattr(ball,   "family", ""))        if ball else ""
            ball_slot   = int(getattr(ball,   "slot",   0))         if ball else 0
            ball_zip    = str(getattr(ball,   "zipcode", ""))       if ball else ""

            pcs_str = pcs.string() if (pcs and hasattr(pcs, "string")) else ""
            p1      = float(getattr(pcs, "p1", 0.0)) if pcs else 0.0
            p2      = float(getattr(pcs, "p2", 0.0)) if pcs else 0.0
            p3      = float(getattr(pcs, "p3", 0.0)) if pcs else 0.0

            snap = {
                "schema_ver":     "1.0",
                "ring_id":        str(ring_id),
                "suit":           suit_name,
                "sector":         self.suit.sector,
                "ring_pos":       self.suit.ring_pos,
                "family":         str(self.suit.family),
                "pcs_string":     pcs_str,
                "pcs_p1":         p1,
                "pcs_p2":         p2,
                "pcs_p3":         p3,
                "ball_family":    ball_family,
                "ball_slot":      ball_slot,
                "ball_zipcode":   ball_zip,
                "ball_chain":     ball_chain,
                "result_preview": str(self._result)[:512] if self._result is not None else "",
                "born_at":        float(getattr(self.rec, "born", 0.0)),
                "snap_ts":        time.time(),
                "frank_version":  FRANK_VERSION,
                "ring_version":   RING_VERSION,
            }
        except Exception as e:
            log.error(f"[snap_clone] Snapshot build failed for ring {ring_id}: {e}")
            return

        # ── Dual hash ─────────────────────────────────────────────────
        # Sort keys so the hash is deterministic regardless of dict ordering.
        canonical = json.dumps(snap, sort_keys=True, default=str).encode("utf-8")

        sha3   = hashlib.sha3_256(canonical).hexdigest()
        blake2 = hashlib.blake2b(canonical, digest_size=64).hexdigest()

        snap["sha3_256"]    = sha3
        snap["blake2b_512"] = blake2

        # Re-encode with hashes included — this is the final, signed record.
        final_raw = json.dumps(snap, sort_keys=True, default=str).encode("utf-8")

        # ── Local write (synchronous, guaranteed) ─────────────────────
        clone_dir = Path(
            os.environ.get(
                "PHOENIX_CLONEPOOL_DIR",
                Path.home() / ".phoenix" / "clonepool",
            )
        )
        clone_file = None
        try:
            clone_dir.mkdir(parents=True, exist_ok=True)
            clone_file = clone_dir / f"{ring_id}_{sha3[:16]}.json"
            # Atomic write: temp file → rename
            tmp = clone_file.with_suffix(".tmp")
            tmp.write_bytes(final_raw)
            tmp.replace(clone_file)
            log.info(
                f"[snap_clone] ring={ring_id} suit={suit_name} "
                f"sha3:{sha3[:16]}… b2:{blake2[:16]}… → {clone_file}"
            )
        except Exception as e:
            log.error(f"[snap_clone] Local write failed for ring {ring_id}: {e}")

        # ── S3 push (async, fire-and-forget) ─────────────────────────
        # Local write is the canonical copy; S3 is backup / distributed sync.
        # Set PHOENIX_S3_BUCKET to enable. Uses boto3 if installed, else skips.
        s3_bucket = os.environ.get("PHOENIX_S3_BUCKET")
        if s3_bucket:
            snap_copy   = final_raw          # captured in closure
            key         = f"clonepool/{ring_id}_{sha3[:16]}.json"
            meta_ring   = str(ring_id)
            meta_sha3   = sha3
            meta_blake2 = blake2
            meta_suit   = suit_name

            def _s3_push():
                try:
                    import boto3  # optional dep; missing is silent
                    s3 = boto3.client("s3")
                    s3.put_object(
                        Bucket      = s3_bucket,
                        Key         = key,
                        Body        = snap_copy,
                        ContentType = "application/json",
                        Metadata    = {
                            "phoenix-ring-id":   meta_ring,
                            "phoenix-sha3":      meta_sha3,
                            "phoenix-blake2b":   meta_blake2,
                            "phoenix-suit":      meta_suit,
                        },
                    )
                    log.info(f"[snap_clone] S3 OK s3://{s3_bucket}/{key}")
                except ImportError:
                    log.debug("[snap_clone] boto3 not installed — S3 push skipped")
                except Exception as exc:
                    log.warning(
                        f"[snap_clone] S3 push failed (local copy preserved): {exc}"
                    )

            threading.Thread(
                target  = _s3_push,
                name    = f"snap_clone_s3_{ring_id}",
                daemon  = True,
            ).start()

    # ------------------------------------------------------------------
    # Executors
    # ------------------------------------------------------------------

    def _run_python(self, data: bytes, **kwargs) -> Any:
        entry = self.suit.entry
        try:
            mod = importlib.import_module(entry)
        except ImportError:
            spec = importlib.util.spec_from_file_location(self.suit.name, entry)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
            else:
                raise

        if hasattr(mod, "run"):
            return mod.run(data, self.rec.ball, self.rec.pcs, **kwargs)
        elif hasattr(mod, "main"):
            return mod.main()
        return None

    def _run_subprocess(self, data: bytes) -> bytes:
        env = os.environ.copy()
        env.update(self.suit.env)

        if self.rec and self.rec.ball:
            env["FRANK_BALL_FAMILY"] = str(self.rec.ball.family)
            env["FRANK_BALL_SLOT"]   = str(int(self.rec.ball.slot))
        if self.rec and self.rec.pcs:
            env["FRANK_PCS"]     = self.rec.pcs.string()
            env["FRANK_RING_ID"] = str(self.rec.ring_id)

        cmd = [self.suit.entry] if isinstance(self.suit.entry, str) else self.suit.entry
        if self.suit.args:
            cmd += self.suit.args

        result = subprocess.run(
            cmd,
            input          = data,
            capture_output = True,
            timeout        = self.suit.timeout,
            env            = env,
        )
        return result.stdout
