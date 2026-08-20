#!/usr/bin/env python3
"""
freewheeling_stage.py — PCS lifecycle manager for SECTOR4
Phoenix DevOps OS

This is the stage manager for the 3-call PCS lifecycle.
It owns all active PCS slots, fires snap_clone on definitive,
and signals phoenix-cpt@{hash}.service via systemctl post-stage.

Pipeline position:
    DATA IN → PCS born → FreewheelStage (call1/call2/call3) → snap_clone → Cpt_conductor

Usage (from conductor.py or directly):
    from freewheeling_stage import FreewheelStage

    stage = FreewheelStage()
    pcs       = stage.call1(b"physics:collision:obj_1", "physics")
    orig_hash = pcs.hash                  # SAVE THIS — hash mutates on call2/call3
    stage.call2(orig_hash, b"chunk:data")
    pcs, committed = stage.call3(orig_hash, b"final:data")
    # if committed: snap_clone fired, slot released, stage dir cleaned
"""

import os
import time
import logging
import subprocess
from pathlib import Path
from threading import Lock
from typing import Optional, Tuple, Dict

from pcs import PCS, snap_clone, prefetch_interrupt

# ── Logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [FREEWHEELING] %(message)s'
)

# ── Stage config ─────────────────────────────────────────────────────────────

STAGE_TMP   = Path(os.environ.get("PHOENIX_STAGE_TMP", "/tmp/phoenix_snap"))
PHOENIX_ROOT = Path(os.environ.get("PHOENIX_ROOT", Path.home() / "Phoenix" / "Phoenix-DevOps-oS"))


# ══════════════════════════════════════════════════════════════════════════════
# FREEWHEELING STAGE
# ══════════════════════════════════════════════════════════════════════════════

class FreewheelStage:
    """
    Stage manager — owns the 3-call PCS lifecycle.

    Storage IS the stage. Every active PCS has a slot here.
    Birds of a feather flock together — same family stays in same zone.

    Thread-safe. Multiple callers can push data concurrently.
    """

    def __init__(self):
        self._slots: Dict[str, dict] = {}   # orig_hash → {pcs, stage_dir, chunks}
        self._lock  = Lock()
        STAGE_TMP.mkdir(parents=True, exist_ok=True)
        logging.info(f"FreewheelStage online — stage dir: {STAGE_TMP}")

    # ── Call 1 — WARM ────────────────────────────────────────────────────────

    def call1(self, data: bytes, family: str = "system") -> PCS:
        """
        Pre-position the stage. PCS is born here.
        Returns the PCS — SAVE pcs.hash before calling call2/call3
        because the hash mutates as data accumulates.
        """
        pcs = prefetch_interrupt(data, family=family)
        pcs.call1()

        orig_hash = pcs.hash    # capture before it mutates

        # Create stage directory for this slot
        stage_dir = STAGE_TMP / orig_hash
        stage_dir.mkdir(parents=True, exist_ok=True)

        # Write call1 chunk
        chunk_path = stage_dir / "call1.bin"
        chunk_path.write_bytes(data)

        with self._lock:
            self._slots[orig_hash] = {
                "pcs"      : pcs,
                "stage_dir": stage_dir,
                "chunks"   : [str(chunk_path)],
                "born_at"  : time.monotonic(),
            }

        logging.info(f"[call1] slot={orig_hash[:8]} family={family} p={pcs.probability:.3f}")
        return pcs

    # ── Call 2 — HOT ─────────────────────────────────────────────────────────

    def call2(self, orig_hash: str, data: bytes) -> PCS:
        """
        Accumulate new data. Hash absorbs the chunk.
        Use the ORIGINAL hash from call1 to look up the slot —
        not the mutated hash on the PCS object.
        """
        with self._lock:
            slot = self._slots.get(orig_hash)

        if not slot:
            raise KeyError(f"FreewheelStage: no slot for orig_hash={orig_hash[:8]} "
                           f"— did you save pcs.hash before calling call2?")

        pcs = slot["pcs"]
        pcs.call2(data)

        # Write chunk to stage dir
        chunk_n = len(slot["chunks"])
        chunk_path = slot["stage_dir"] / f"call2_{chunk_n}.bin"
        chunk_path.write_bytes(data)
        slot["chunks"].append(str(chunk_path))

        logging.info(f"[call2] slot={orig_hash[:8]} p={pcs.probability:.3f}")
        return pcs

    # ── Call 3 — RESIDUE / DEFINITIVE ────────────────────────────────────────

    def call3(self, orig_hash: str, data: bytes) -> Tuple[PCS, bool]:
        """
        Final accumulation + definitive check.
        Returns (pcs, committed).

        If committed=True:
          - snap_clone fired (data moved to clonepool zone)
          - phoenix-cpt@{hash}.service signalled via systemctl
          - stage dir cleaned
          - slot released from memory
        """
        with self._lock:
            slot = self._slots.get(orig_hash)

        if not slot:
            raise KeyError(f"FreewheelStage: no slot for orig_hash={orig_hash[:8]}")

        pcs = slot["pcs"]
        pcs.call3(data)

        # Write final chunk
        chunk_path = slot["stage_dir"] / "call3_final.bin"
        chunk_path.write_bytes(data)
        slot["chunks"].append(str(chunk_path))

        committed = pcs.definitive

        if committed:
            logging.info(f"[call3] DEFINITIVE slot={orig_hash[:8]} p={pcs.probability:.3f} → snap_clone")
            self._post_stage(pcs, slot["stage_dir"])
        else:
            logging.info(f"[call3] RESIDUE slot={orig_hash[:8]} p={pcs.probability:.3f} → evict")
            self._cleanup_slot(orig_hash, slot["stage_dir"])

        return pcs, committed

    # ── Post-stage ───────────────────────────────────────────────────────────

    def _post_stage(self, pcs: PCS, stage_dir: Path):
        """
        On definitive commit:
        1. snap_clone — copy staged data into clonepool zone
        2. Signal phoenix-cpt@{hash}.service via systemctl (Linux only)
        3. Cleanup stage dir
        """
        # 1. Snap clone
        success = snap_clone(pcs, str(stage_dir))
        if success:
            logging.info(f"[snap_clone] {pcs.hash[:8]} committed to clonepool zone={pcs.zipcode}")
        else:
            logging.warning(f"[snap_clone] {pcs.hash[:8]} snap_clone returned False — check stage dir")

        # 2. Signal systemd service (Linux only — no-op on Windows)
        self._signal_cpt_service(pcs)

        # 3. Cleanup
        self._cleanup_slot(pcs.hash, stage_dir)

    def _signal_cpt_service(self, pcs: PCS):
        """
        Signal phoenix-cpt@{hash}.service via systemctl.
        Silently skipped on Windows or if systemctl not available.
        """
        try:
            svc = f"phoenix-cpt@{pcs.hash}.service"
            result = subprocess.run(
                ["systemctl", "--user", "start", svc],
                capture_output=True, timeout=5
            )
            if result.returncode == 0:
                logging.info(f"[cpt_signal] started {svc}")
            else:
                # Service not installed yet — not an error in development
                logging.debug(f"[cpt_signal] {svc} not found (expected during dev)")
        except (FileNotFoundError, subprocess.TimeoutExpired):
            # systemctl not available (Windows, or no systemd)
            pass

    def _cleanup_slot(self, orig_hash: str, stage_dir: Path):
        """Remove stage dir and release slot from memory."""
        try:
            if stage_dir.exists():
                import shutil
                shutil.rmtree(str(stage_dir))
        except Exception as e:
            logging.warning(f"[cleanup] could not remove stage dir {stage_dir}: {e}")

        with self._lock:
            self._slots.pop(orig_hash, None)

    # ── Status ───────────────────────────────────────────────────────────────

    def flock_status(self) -> dict:
        """Snapshot of all active flocks — safe to call any time."""
        with self._lock:
            return {
                h[:8]: {
                    "family" : slot["pcs"].family,
                    "zipcode": slot["pcs"].zipcode,
                    "calls"  : slot["pcs"].call_count,
                    "p"      : round(slot["pcs"].probability, 3),
                    "age_ms" : int((time.monotonic() - slot["born_at"]) * 1000),
                }
                for h, slot in self._slots.items()
            }

    def active_count(self) -> int:
        """How many slots are currently in-flight."""
        with self._lock:
            return len(self._slots)


# ══════════════════════════════════════════════════════════════════════════════
# STANDALONE TEST
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("FreewheelStage — standalone test")
    print("Phoenix DevOps OS / SECTOR4")
    print("=" * 60)

    stage = FreewheelStage()

    test_cases = [
        (b"physics:collision:obj_1",  "physics"),
        (b"ai:inference:model_gpt",   "ai"),
        (b"network:packet:frame_001", "network"),
    ]

    for seed, family in test_cases:
        print(f"\n--- {family} ---")
        pcs = stage.call1(seed, family)
        orig_hash = pcs.hash          # save BEFORE call2 mutates it
        print(f"  call1: {pcs}")

        stage.call2(orig_hash, f"chunk:{family}:alpha".encode())
        print(f"  call2: p={pcs.probability:.3f}")

        pcs, committed = stage.call3(orig_hash, f"final:{family}:beta".encode())
        status = "COMMITTED → snap_clone" if committed else "RESIDUE → evicted"
        print(f"  call3: p={pcs.probability:.3f}  [{status}]")

    print(f"\nActive slots remaining: {stage.active_count()}")
    print("=" * 60)
