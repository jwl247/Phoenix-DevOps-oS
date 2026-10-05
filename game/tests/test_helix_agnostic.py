#!/usr/bin/env python3
"""
test_helix_agnostic.py — Helix Lightning Kernel agnostic integration test
Phoenix DevOps OS | jwl247 | GPL v3

Proves Helix-I + Helix-E + franken5 bus can transport Phoenix game state
on ANY platform (Windows + Linux) without POSIX-specific signals.

Five proofs:
  1. Bus agnostic      — SharedMemoryBus (file-mmap) writes/reads cross-platform
  2. Interrupt agnostic — _fire_interrupt monkeypatched to threading.Event
  3. Emit agnostic     — HelixE.emit() bypasses bus+signals entirely
  4. FrankWorld → Helix-E — game events: enlist → wound → KIA
  5. Platform contract  — AST confirms os.kill confined to _fire_interrupt only

Run from repo root:
  python -m pytest game/tests/test_helix_agnostic.py -v
  python game/tests/test_helix_agnostic.py
"""

import ast
import inspect
import json
import os
import platform
import shutil
import socket
import struct
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

# ── Path setup ─────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "sector1" / "helix-lightning"))
sys.path.insert(0, str(REPO_ROOT))   # game is a package (relative imports)

# ── Constants ──────────────────────────────────────────────────────────────────
# Use high port numbers offset from prod to avoid collision with a live Helix
TEST_HELIX_I_PORT = 17700
TEST_HELIX_E_PORT = 17800

HEADER_FMT  = "!4sBBHI"
HEADER_SIZE = struct.calcsize(HEADER_FMT)


# ══════════════════════════════════════════════════════════════════════════════
# AgnosticInterruptBridge
# Replaces helixi._fire_interrupt() on Windows where SIGUSR1 does not exist.
# threading.Event is the cross-platform equivalent: Frank polls the event
# instead of waking on a Unix signal.
# ══════════════════════════════════════════════════════════════════════════════

class AgnosticInterruptBridge:
    """
    Drop-in replacement for HelixI._fire_interrupt().
    threading.Event — works on Windows and Linux.
    Frank polls this event instead of handling SIGUSR1.
    """
    def __init__(self):
        self._event = threading.Event()
        self._count = 0
        self._lock  = threading.Lock()

    def fire(self):
        with self._lock:
            self._count += 1
        self._event.set()

    def wait(self, timeout: float = 2.0) -> bool:
        fired = self._event.wait(timeout)
        if fired:
            self._event.clear()
        return fired

    @property
    def count(self) -> int:
        with self._lock:
            return self._count


def _make_tmp_env(prefix: str) -> tuple[str, dict]:
    """Create isolated temp dir and return (path, env_overrides)."""
    d = tempfile.mkdtemp(prefix=prefix)
    return d, {
        "PHOENIX_SHM":   str(Path(d) / "phoenix_shm"),
        "PHOENIX_AUDIT": str(Path(d) / "phoenix_audit.log"),
        "PHOENIX_ARCHIVE_ROOT":   str(Path(d) / "archive"),
        "PHOENIX_FRANK_KEY_FILE": str(Path(d) / "frank_world.key"),
    }


def _apply_env(overrides: dict):
    for k, v in overrides.items():
        os.environ[k] = v


def _clear_env(overrides: dict):
    for k in overrides:
        os.environ.pop(k, None)


# ══════════════════════════════════════════════════════════════════════════════
# 1 — Bus agnostic
# ══════════════════════════════════════════════════════════════════════════════

class TestBusAgnostic(unittest.TestCase):
    """SharedMemoryBus uses file-based mmap (tempfile.gettempdir()).
    This is NOT POSIX shm — works identically on Windows and Linux."""

    def setUp(self):
        self._tmp, self._env = _make_tmp_env("phoenix_test_bus_")
        _apply_env(self._env)
        import importlib, franken5 as _f5
        importlib.reload(_f5)
        from franken5 import SharedMemoryBus
        self.bus = SharedMemoryBus()
        self.bus.mount()   # Frank5.boot() mounts in prod; boot also installs POSIX signals, so tests mount directly

    def tearDown(self):
        try:
            self.bus.unmount()
        except Exception:
            pass
        _clear_env(self._env)
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_write_read_roundtrip(self):
        """Bytes written to slot N come back from slot N unchanged."""
        payload = b"HISX\x01\x41\x00\x04\x00\x00\x00\x01TEST_BUS"
        self.bus.write_stage(0, payload)
        result = self.bus.read_stage(0)
        self.assertIsNotNone(result)
        self.assertTrue(
            result[:len(payload)] == payload or payload in result,
            f"payload not found in result: {result!r}"
        )

    def test_multiple_slots_are_independent(self):
        """Each slot is independent — write to 0 does not clobber slot 3."""
        self.bus.write_stage(0, b"SLOT_ZERO_DATA")
        self.bus.write_stage(3, b"SLOT_THREE_DATA")
        r0 = self.bus.read_stage(0)
        r3 = self.bus.read_stage(3)
        self.assertIn(b"SLOT_ZERO", r0)
        self.assertIn(b"SLOT_THREE", r3)

    def test_shm_path_under_tempdir(self):
        """SHM_PATH must be under gettempdir() — not /dev/shm or any POSIX path."""
        import importlib, franken5 as _f5
        importlib.reload(_f5)
        from franken5 import SHM_PATH
        env_val = os.environ.get("PHOENIX_SHM", "")
        tmp_root = str(Path(tempfile.gettempdir()))
        self.assertTrue(
            str(SHM_PATH).startswith(tmp_root) or str(SHM_PATH) == env_val,
            f"SHM_PATH {SHM_PATH!r} is not under tempdir — breaks on Windows"
        )

    def test_platform_info(self):
        print(f"\n  [platform] {platform.system()} {platform.release()}")
        print(f"  [tempdir]  {tempfile.gettempdir()}")
        print(f"  [shm_path] {self._env['PHOENIX_SHM']}")


# ══════════════════════════════════════════════════════════════════════════════
# 2 — Interrupt agnostic
# ══════════════════════════════════════════════════════════════════════════════

class TestInterruptAgnostic(unittest.TestCase):
    """
    _fire_interrupt() in helixi.py calls os.kill(PID, SIGUSR1) — the ONLY
    non-agnostic call in the entire Helix chain. Monkeypatching it to use
    AgnosticInterruptBridge makes the full ingress pipeline cross-platform.
    """

    def setUp(self):
        self._tmp, self._env = _make_tmp_env("phoenix_test_int_")
        self._env["HELIX_I_PORT"] = str(TEST_HELIX_I_PORT)
        _apply_env(self._env)

        import importlib
        import franken5 as _f5; importlib.reload(_f5)
        import helixi as _hi;   importlib.reload(_hi)
        from franken5 import get_frank
        from helixi import HelixI

        self.frank   = get_frank()
        self.frank.bus.mount()
        self.bridge  = AgnosticInterruptBridge()
        self.helix_i = HelixI(self.frank)
        # The monkeypatch: swap SIGUSR1-based interrupt for threading.Event
        self.helix_i._fire_interrupt = self.bridge.fire

    def tearDown(self):
        self.helix_i.stop()
        try:
            self.frank.shutdown()
        except Exception:
            pass
        _clear_env(self._env)
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_pull_fires_bridge_not_signal(self):
        """pull() writes to bus and fires the agnostic bridge — no os.kill()."""
        data = json.dumps({"event": "enlist", "soldier": "PVT_TEST"}).encode()
        ok = self.helix_i.pull(1, data, {"type": "game_event"})
        self.assertTrue(ok, "pull() returned False — check franken5 bus init")
        fired = self.bridge.wait(timeout=1.0)
        self.assertTrue(fired, "AgnosticInterruptBridge.fire() never called")
        self.assertEqual(self.bridge.count, 1)

    def test_os_kill_not_called(self):
        """With monkeypatch in place, os.kill is never invoked."""
        with patch("os.kill") as mock_kill:
            self.helix_i.pull(2, b"no_kill_please")
            mock_kill.assert_not_called()

    def test_stage_lands_in_bus_with_hisx_magic(self):
        """After pull(), the HISX-packed stage is readable from shared memory."""
        data = b"game_state_payload_agnostic"
        self.helix_i.pull(1, data, {"test": True})
        raw = self.helix_i.bus.read_stage(0)  # channel 1 → slot 0
        self.assertIsNotNone(raw)
        self.assertGreater(len(raw), HEADER_SIZE, "Stage too small — header missing")
        magic, ch, strand, data_len, seq = struct.unpack(HEADER_FMT, raw[:HEADER_SIZE])
        self.assertEqual(magic, b"HISX", "HISX magic missing — pack_stage broken")
        self.assertEqual(ch, 1, "Channel mismatch in packed stage")

    def test_rapid_fire_all_register(self):
        """10 rapid pull() calls all fire the bridge without loss."""
        for i in range(10):
            self.helix_i.pull(1, f"packet_{i}".encode())
        time.sleep(0.05)
        self.assertGreaterEqual(self.bridge.count, 10,
                                f"Only {self.bridge.count}/10 fires registered")

    def test_channel_slot_mapping(self):
        """Channels 1-4 map to slots 0-3 as declared in helixi.py."""
        slot_map = {1: 0, 2: 1, 3: 2, 4: 3}
        for ch_num, expected_slot in slot_map.items():
            ch = self.helix_i.channels.get(ch_num)
            self.assertIsNotNone(ch, f"Channel {ch_num} not found")
            self.assertEqual(ch.slot, expected_slot,
                             f"Ch{ch_num} slot={ch.slot}, expected {expected_slot}")


# ══════════════════════════════════════════════════════════════════════════════
# 3 — Emit path (definitively agnostic)
# ══════════════════════════════════════════════════════════════════════════════

class TestEmitAgnostic(unittest.TestCase):
    """
    HelixE.emit() is the definitive agnostic egress path:
    translate + push to output handlers. No bus read. No signal. No fork.
    """

    def setUp(self):
        self._tmp, self._env = _make_tmp_env("phoenix_test_emit_")
        self._env["HELIX_E_PORT"] = str(TEST_HELIX_E_PORT)
        _apply_env(self._env)

        import importlib
        import franken5 as _f5; importlib.reload(_f5)
        import helixe as _he;   importlib.reload(_he)
        from franken5 import get_frank
        from helixe import HelixE

        self.frank   = get_frank()
        self.frank.bus.mount()
        self.helix_e = HelixE(self.frank)
        self._received: list[tuple] = []
        self.helix_e.on_output(self._capture)

    def _capture(self, channel, data, meta):
        self._received.append((channel, data, meta))

    def tearDown(self):
        self.helix_e.stop()
        try:
            self.frank.shutdown()
        except Exception:
            pass
        _clear_env(self._env)
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_emit_raw_hits_output_handler(self):
        """emit() delivers payload to registered output handler."""
        payload = json.dumps({"event": "wound", "soldier": "SGT_EMIT"}).encode()
        ok = self.helix_e.emit(5, payload, target_lang="raw")
        self.assertTrue(ok, "emit() returned False")
        self.assertEqual(len(self._received), 1)
        ch, data, _ = self._received[0]
        self.assertEqual(ch, 5)
        self.assertEqual(data, payload)

    def test_emit_json_translator_registered(self):
        """emit() with target_lang='json' pretty-prints via built-in translator."""
        payload = b'{"event":"kia","soldier":"CPL_EMIT"}'
        self.helix_e.emit(5, payload, target_lang="json")
        self.assertEqual(len(self._received), 1)
        _, data, _ = self._received[0]
        parsed = json.loads(data)
        self.assertEqual(parsed["event"], "kia")
        self.assertEqual(parsed["soldier"], "CPL_EMIT")

    def test_emit_never_reads_bus(self):
        """emit() must not call bus.read_stage() — it is a direct push path."""
        read_calls: list = []
        original_read = self.helix_e.bus.read_stage

        def spy_read(slot):
            read_calls.append(slot)
            return original_read(slot)

        self.helix_e.bus.read_stage = spy_read
        self.helix_e.emit(5, b"no_bus_read_please")
        self.assertEqual(len(read_calls), 0,
                         f"emit() called bus.read_stage on slots: {read_calls}")

    def test_emit_socket_delivery(self):
        """Bytes emitted via socket server arrive at a connected consumer."""
        self.helix_e.start_output_sockets()
        time.sleep(0.15)

        port = TEST_HELIX_E_PORT + 5  # channel 5
        received: list[bytes] = []
        consumer_ready = threading.Event()
        consumer_done  = threading.Event()

        def consumer():
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(3.0)
                s.connect(("127.0.0.1", port))
                consumer_ready.set()
                data = s.recv(4096)
                received.append(data)
                s.close()
            except Exception as ex:
                received.append(b"ERR:" + str(ex).encode())
            finally:
                consumer_done.set()

        t = threading.Thread(target=consumer, daemon=True)
        t.start()
        consumer_ready.wait(timeout=2.0)
        time.sleep(0.05)

        expected = b"socket_delivery_confirmed"
        self.helix_e.emit(5, expected)
        consumer_done.wait(timeout=2.0)

        self.assertTrue(len(received) > 0, "Consumer received nothing from socket")
        self.assertIn(expected, received[0],
                      f"Expected {expected!r} not found in {received[0]!r}")


# ══════════════════════════════════════════════════════════════════════════════
# 4 — FrankWorld → Helix-E game event flow
# ══════════════════════════════════════════════════════════════════════════════

class TestFrankWorldHelixFlow(unittest.TestCase):
    """
    FrankWorld._broadcast_event() writes game state to bus slot 4.
    Helix-E channel 5 (slot 4) flushes it as output.
    AgnosticInterruptBridge replaces SIGUSR1 throughout.
    """

    def setUp(self):
        self._tmp, self._env = _make_tmp_env("phoenix_test_fw_")
        self._env["HELIX_I_PORT"] = str(TEST_HELIX_I_PORT + 200)
        self._env["HELIX_E_PORT"] = str(TEST_HELIX_E_PORT + 200)
        _apply_env(self._env)

        import importlib
        import franken5 as _f5; importlib.reload(_f5)
        import helixi as _hi;   importlib.reload(_hi)
        import helixe as _he;   importlib.reload(_he)
        import game.frank_world as _fw; importlib.reload(_fw)

        from franken5 import get_frank
        from helixi import HelixI
        from helixe import HelixE
        from game.frank_world import FrankWorld

        self.frank    = get_frank()
        self.frank.bus.mount()
        self.bridge   = AgnosticInterruptBridge()
        self.helix_i  = HelixI(self.frank)
        self.helix_i._fire_interrupt = self.bridge.fire
        self.helix_e  = HelixE(self.frank)
        self.world    = FrankWorld(self.frank)

        self._events: list[dict] = []

        def capture(ch, data, meta):
            raw = data.rstrip(b"\x00")
            if not raw:
                return
            try:
                for line in raw.split(b"\n"):
                    line = line.strip()
                    if line:
                        self._events.append(json.loads(line))
            except Exception:
                self._events.append({"raw": raw.decode(errors="replace")})

        self.helix_e.on_output(capture)

    def _drain(self):
        """Read whatever FrankWorld wrote to bus slot 4, emit via Helix-E ch5."""
        raw = self.helix_e.bus.read_stage(4)
        if raw:
            stripped = raw.rstrip(b"\x00")
            if stripped:
                self.helix_e.emit(5, stripped, target_lang="raw")

    def tearDown(self):
        self.helix_i.stop()
        self.helix_e.stop()
        try:
            self.frank.shutdown()
        except Exception:
            pass
        _clear_env(self._env)
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _types(self):
        return [e.get("event") for e in self._events]

    def test_enlist_event_flows_through_helix(self):
        """enlist() → FrankWorld → bus slot 4 → Helix-E ch5 → output handler."""
        self.world.enlist("PVT_FLOW_TEST", b"k-enlist" * 4, "Alpha")
        self._drain()
        self.assertIn("enlistment", self._types(), f"enlistment not in output: {self._events}")

    def test_wound_event_flows_through_helix(self):
        """wound() → bus → Helix-E output."""
        from game.hospital import WoundSeverity
        card = self.world.enlist("SGT_WOUND_TEST", b"k-wound!" * 4, "Bravo")
        card.field()
        self._events.clear()
        self.world.wound(card, "GSW_CHEST", WoundSeverity.WOUNDED)
        self._drain()
        self.assertIn("wounded", self._types(), f"wounded not in output: {self._events}")

    def test_kia_event_flows_through_helix(self):
        """kill() → bus → Helix-E output."""
        card = self.world.enlist("CPL_KIA_TEST", b"k-kia!!!" * 4, "Charlie")
        card.field()
        self._events.clear()
        self.world.kill(card, "HOSTILE_FIRE")
        self._drain()
        self.assertIn("KIA", self._types(), f"KIA not in output: {self._events}")

    def test_full_lifecycle_zero_os_kill(self):
        """Complete enlist → wound → KIA lifecycle with zero os.kill() calls."""
        from game.hospital import WoundSeverity
        with patch("os.kill") as mock_kill:
            card = self.world.enlist("PFC_LIFECYCLE", b"k-cycle!" * 4, "Delta")
            card.field()
            self.world.wound(card, "IED_BLAST", WoundSeverity.WOUNDED)
            self.world.kill(card, "WOUNDS")
            self._drain()
            mock_kill.assert_not_called()
        self.assertTrue(
            any(t in self._types() for t in ("enlistment", "wounded", "KIA")),
            f"No game events reached Helix-E output: {self._events}",
        )


# ══════════════════════════════════════════════════════════════════════════════
# 5 — Platform contract (static analysis)
# ══════════════════════════════════════════════════════════════════════════════

class TestPlatformContract(unittest.TestCase):
    """
    AST-level checks: confirm the non-agnostic call (os.kill) is
    confined to _fire_interrupt only, and the rest of the chain is clean.
    """

    def _src_of(self, cls) -> str:
        return Path(inspect.getfile(cls)).read_text(encoding="utf-8")

    def _kill_lines(self, src: str) -> list[int]:
        tree = ast.parse(src)
        lines = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                f = node.func
                if isinstance(f, ast.Attribute) and f.attr == "kill":
                    lines.append(node.lineno)
                elif isinstance(f, ast.Name) and f.id == "kill":
                    lines.append(node.lineno)
        return lines

    def test_os_kill_only_in_fire_interrupt(self):
        """helixi.py: os.kill() must appear ONLY inside _fire_interrupt."""
        from helixi import HelixI
        src = self._src_of(HelixI)
        kill_lines = self._kill_lines(src)
        src_lines = src.splitlines()
        for lineno in kill_lines:
            ctx_start = max(0, lineno - 8)
            ctx = "\n".join(src_lines[ctx_start:lineno])
            self.assertIn(
                "_fire_interrupt", ctx,
                f"os.kill() on line {lineno} is OUTSIDE _fire_interrupt — "
                "this call breaks Windows. Move it inside _fire_interrupt."
            )

    def test_franken5_no_posix_shm_dep(self):
        """franken5.py must NOT import posix_ipc or hardcode /dev/shm."""
        from franken5 import SharedMemoryBus
        src = self._src_of(SharedMemoryBus)
        self.assertNotIn(
            "posix_ipc", src,
            "franken5 imports posix_ipc — not available on Windows"
        )
        self.assertNotIn(
            "/dev/shm", src,
            "franken5 hardcodes /dev/shm — does not exist on Windows"
        )

    def test_emit_method_signal_free(self):
        """helixe.py emit() must reference neither os.kill nor signal."""
        from helixe import HelixE
        src = self._src_of(HelixE)
        tree = ast.parse(src)

        emit_start = emit_end = None
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name == "emit":
                    emit_start = node.lineno
                    emit_end   = node.end_lineno

        self.assertIsNotNone(emit_start, "emit() not found in helixe.py")
        emit_src = "\n".join(src.splitlines()[emit_start - 1:emit_end])

        for forbidden in ("os.kill", "signal.", "SIGUSR", "FrankSignal"):
            self.assertNotIn(
                forbidden, emit_src,
                f"emit() references '{forbidden}' — not agnostic"
            )

    def test_flush_async_uses_threading_not_fork(self):
        """helixe.flush_async() must use threading.Thread, not os.fork()."""
        from helixe import HelixE
        src = self._src_of(HelixE)
        tree = ast.parse(src)

        fa_start = fa_end = None
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name == "flush_async":
                    fa_start = node.lineno
                    fa_end   = node.end_lineno

        if fa_start is None:
            self.skipTest("flush_async not found — skipping")

        fa_src = "\n".join(src.splitlines()[fa_start - 1:fa_end])
        self.assertIn("threading.Thread", fa_src,
                      "flush_async() doesn't use threading.Thread")
        self.assertNotIn("os.fork", fa_src,
                         "flush_async() uses os.fork — not Windows-safe")

    def test_helix_i_strand_mapping(self):
        """Channels 1-2 strand A, 3-4 strand B per helixi.py spec."""
        from helixi import STRAND_A_CHANNELS, STRAND_B_CHANNELS
        self.assertEqual(set(STRAND_A_CHANNELS), {1, 2})
        self.assertEqual(set(STRAND_B_CHANNELS), {3, 4})

    def test_helix_e_strand_mapping(self):
        """Channels 5-6 strand A, 7-8 strand B per helixe.py spec."""
        from helixe import STRAND_A_CHANNELS, STRAND_B_CHANNELS
        self.assertEqual(set(STRAND_A_CHANNELS), {5, 6})
        self.assertEqual(set(STRAND_B_CHANNELS), {7, 8})


# ══════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import logging
    logging.basicConfig(
        level=logging.WARNING,
        format="%(name)-12s %(levelname)-8s %(message)s"
    )
    print("=" * 60)
    print("Phoenix | Helix Agnostic Integration Test Suite")
    print(f"Platform : {platform.system()} {platform.release()}")
    print(f"Python   : {sys.version.split()[0]}")
    print(f"Repo     : {REPO_ROOT}")
    print("=" * 60)
    print()
    unittest.main(verbosity=2, failfast=False)
