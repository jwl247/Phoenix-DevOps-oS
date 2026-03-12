#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║  Phoenix Bridge Kernel — Phoenix-DevOps-oS                  ║
║  Slot 1  //  c_sideload  //  NOSQL layer                    ║
║                                                              ║
║  Only job: coms between Linux concierge and Windows          ║
║  concierge. Nothing else.                                    ║
║                                                              ║
║  Input   — raw, whatever the source sends. No translation.  ║
║  Internal — quadralingual from PCS.call1() forward.         ║
║  Output  — QuadPacket.native() in requester's language.     ║
║                                                              ║
║  No loops. No collisions. No bottlenecks.                   ║
║  Sync the interrupter. Get the raw data. Hand to PCS.       ║
╚══════════════════════════════════════════════════════════════╝
"""

import sys
import os
import json
import time
import threading
import hashlib
from collections import deque
from ipykernel.kernelbase import Kernel

# ── Path: sector4 source lives in the phoenix import ─────────
_SECTOR4 = os.path.join(
    os.path.dirname(__file__),
    "..", "..", "_kali_import", "phoenix", "sector4"
)
sys.path.insert(0, os.path.abspath(_SECTOR4))

from pcs import PCS, snap_clone
from freewheeling_stage import FreewheelStage
from conductor import CptConductor

# ── Concierge endpoints ───────────────────────────────────────
LINUX_CONCIERGE_SOCK  = os.environ.get("PHOENIX_LINUX_SOCK",  "/tmp/phoenix_linux.sock")
WIN_CONCIERGE_SOCK    = os.environ.get("PHOENIX_WIN_SOCK",    r"\\.\pipe\phoenix_windows")

# ── Interrupter ───────────────────────────────────────────────

class Interrupter:
    """
    Syncs at earliest input intercept.
    Catches raw signal from either concierge.
    Hands raw bytes directly to PCS — no preprocessing.
    Capacity: dynamic. Tested baseline: 5 concurrent.
    No hard ceiling.
    """

    def __init__(self):
        self._queue: deque = deque()
        self._lock  = threading.Lock()
        self._ev    = threading.Event()

    def intercept(self, raw: bytes, source: str, family: str) -> dict:
        """
        Sync point. Raw data arrives here first.
        Returns the ticket — caller polls for result via ticket_id.
        """
        ticket_id = hashlib.blake2s(
            raw + source.encode() + str(time.monotonic_ns()).encode(),
            digest_size=8
        ).hexdigest()

        with self._lock:
            self._queue.append({
                "ticket_id": ticket_id,
                "raw":       raw,
                "source":    source,
                "family":    family,
                "ts":        time.monotonic_ns(),
            })

        self._ev.set()
        return {"ticket_id": ticket_id, "source": source}

    def drain(self) -> list:
        """Pull all pending intercepts. Non-blocking."""
        self._ev.clear()
        with self._lock:
            items = list(self._queue)
            self._queue.clear()
        return items

    def wait(self, timeout: float = 0.05) -> bool:
        return self._ev.wait(timeout=timeout)


# ── Bridge Kernel ─────────────────────────────────────────────

class PhoenixBridgeKernel(Kernel):
    """
    Registered Jupyter kernel — slot 1, c_sideload.
    Only role: relay between Linux concierge and Windows concierge.
    Input is raw. Internal is quadralingual. Output is native().
    """

    implementation         = "phoenix_bridge"
    implementation_version = "1.0.0"
    language               = "phoenix"
    language_version       = "1.0"
    language_info          = {
        "name":           "phoenix",
        "mimetype":       "text/plain",
        "file_extension": ".ph",
    }
    banner = "Phoenix Bridge Kernel — slot 1 / c_sideload"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._interrupter = Interrupter()
        self._stage       = FreewheelStage()
        self._captain     = CptConductor()

        # Result store: ticket_id → QuadPacket or error
        self._results: dict = {}
        self._results_lock  = threading.Lock()

        # Processor thread — drains interrupter, runs lifecycle
        self._proc_thread = threading.Thread(
            target=self._processor,
            daemon=True,
            name="bridge-processor"
        )
        self._proc_thread.start()

    # ── Processor — interrupter drain loop ───────────────────

    def _processor(self):
        """
        Drains the interrupter.
        Runs PCS 3-call lifecycle for each raw intercept.
        No loops in the signal path — one pass per item.
        """
        while True:
            self._interrupter.wait(timeout=0.05)
            items = self._interrupter.drain()

            for item in items:
                self._run_lifecycle(item)

    def _run_lifecycle(self, item: dict):
        """
        Raw → PCS → Freewheeling → Captain → result.
        One direction. No return path.
        """
        raw      = item["raw"]
        family   = item["family"]
        tid      = item["ticket_id"]

        try:
            # Call 1 — stage set, PCS born at interrupter
            pcs = self._stage.call1(raw, family)

            # Call 2 — source metadata accumulates
            source_data = item["source"].encode()
            self._stage.call2(pcs.hash, source_data)

            # Call 3 — outcome, definitive check, snap-clone if threshold met
            pcs, committed = self._stage.call3(
                pcs.hash,
                raw + source_data
            )

            # Captain — ingress, slot selection, propcoms, egress
            packet = self._captain.ingress(pcs, {
                "raw":       raw.decode(errors="replace"),
                "source":    item["source"],
                "family":    family,
                "committed": committed,
            })

            with self._results_lock:
                self._results[tid] = {
                    "ok":        True,
                    "ticket_id": tid,
                    "pcs":       str(pcs),
                    "committed": committed,
                    "packet_id": packet.packet_id if packet else None,
                    "slot":      packet.slot      if packet else None,
                    # Output — only translation in the system
                    "output":    packet.native()  if packet else None,
                    "language":  packet.language.value if packet else None,
                }

        except Exception as exc:
            with self._results_lock:
                self._results[tid] = {
                    "ok":        False,
                    "ticket_id": tid,
                    "error":     str(exc),
                }

    # ── Jupyter execute handler ───────────────────────────────

    def do_execute(self, code, silent, store_history=True,
                   user_expressions=None, allow_stdin=False):
        """
        Receives raw input from any source via Jupyter protocol.
        Parses the source envelope, hands raw payload to interrupter.
        Returns native output to the requester.
        """
        try:
            # Expect JSON envelope: {source, family, data}
            # Source can send bare string — treat as system/raw
            try:
                env    = json.loads(code)
                source = env.get("source", "unknown")
                family = env.get("family", "system")
                raw    = env.get("data", code).encode()
            except (json.JSONDecodeError, AttributeError):
                # Bare input — accept raw, family=system
                source = "unknown"
                family = "system"
                raw    = code.encode() if isinstance(code, str) else code

            # Sync the interrupter — raw data, no translation
            ticket = self._interrupter.intercept(raw, source, family)
            tid    = ticket["ticket_id"]

            # Wait for processor (non-blocking poll — no busy loop)
            deadline = time.monotonic() + 2.0
            result   = None
            while time.monotonic() < deadline:
                with self._results_lock:
                    result = self._results.pop(tid, None)
                if result is not None:
                    break
                time.sleep(0.005)

            if result is None:
                result = {"ok": False, "ticket_id": tid, "error": "timeout"}

            if not silent:
                output = json.dumps(result, indent=2, default=str)
                self.send_response(
                    self.iopub_socket,
                    "execute_result",
                    {
                        "execution_count": self.execution_count,
                        "data":            {"text/plain": output},
                        "metadata":        {},
                    }
                )

            return {
                "status":          "ok",
                "execution_count": self.execution_count,
                "payload":         [],
                "user_expressions": {},
            }

        except Exception as exc:
            return {
                "status":     "error",
                "ename":      type(exc).__name__,
                "evalue":     str(exc),
                "traceback":  [],
            }

    def do_shutdown(self, restart):
        return {"status": "ok", "restart": restart}


# ── Entry point ───────────────────────────────────────────────

if __name__ == "__main__":
    from ipykernel.kernelapp import IPKernelApp
    IPKernelApp.launch_instance(kernel_class=PhoenixBridgeKernel)
