"""
test_frank_ollama.py — Frank × Ollama3 test suite

Two layers:
  1. Unit tests — Frank packet mechanics, no network deps
  2. Integration tests — AI packet lifecycle end-to-end with Ollama3

Run:
  python3 test_frank_ollama.py             # both layers (skips Ollama tests if not running)
  python3 test_frank_ollama.py -v          # verbose
  python3 -m pytest test_frank_ollama.py  # via pytest

Ollama3 must be running at localhost:11434 for integration tests:
  ollama serve           # start server
  ollama pull llama3     # pull the model if needed

Authors: Jerry Leftwich + Jerilynn Leftwich
License: GPL v3
"""

import json
import os
import socket
import struct
import sys
import http.client
import unittest

# Make frank importable from here
sys.path.insert(0, os.path.dirname(__file__))

from frank import (
    AUTH_LANE_SIZE,
    FRANK_MAGIC,
    HEADER_SIZE,
    MIRROR_OFFSET,
    TOKEN_OFFSET,
    Frank,
    DoubleHelixPacket,
    PacketType,
    Ring,
    build_packet,
    build_ring_chain,
)

# ---------------------------------------------------------------------------
# Ollama connection helpers
# ---------------------------------------------------------------------------

OLLAMA_HOST  = "localhost"
OLLAMA_PORT  = 11434
OLLAMA_MODEL = "llama3"   # change to "llama3:8b" or "llama3:latest" if needed


def ollama_reachable() -> bool:
    """Return True if Ollama is listening on localhost:11434."""
    try:
        s = socket.create_connection((OLLAMA_HOST, OLLAMA_PORT), timeout=2)
        s.close()
        return True
    except OSError:
        return False


def ollama_generate(prompt: str, model: str = OLLAMA_MODEL) -> str:
    """
    POST to Ollama /api/generate (non-streaming).
    Returns the raw response string from the model.
    """
    body = json.dumps({
        "model":  model,
        "prompt": prompt,
        "stream": False,
    }).encode()

    conn = http.client.HTTPConnection(OLLAMA_HOST, OLLAMA_PORT, timeout=60)
    conn.request(
        "POST", "/api/generate", body=body,
        headers={"Content-Type": "application/json"},
    )
    resp = conn.getresponse()
    raw  = resp.read().decode()
    conn.close()

    data = json.loads(raw)
    return data.get("response", "")


def ollama_list_models() -> list:
    """Return list of locally available model names."""
    conn = http.client.HTTPConnection(OLLAMA_HOST, OLLAMA_PORT, timeout=10)
    conn.request("GET", "/api/tags")
    resp = conn.getresponse()
    data = json.loads(resp.read().decode())
    conn.close()
    return [m["name"] for m in data.get("models", [])]


# ---------------------------------------------------------------------------
# Helper — dispatch an AI prompt through Frank's packet pipeline
# ---------------------------------------------------------------------------

def frank_ai_dispatch(frank: Frank, process_id: int, prompt: str) -> tuple:
    """
    Full Frank AI dispatch cycle:
      1. Frank writes import
      2. Prompt encoded into payload_a (AI lane A2)
      3. Packet built and sent through Frank.receive_packet
      4. Returns (packet, import_record) on success, (None, None) on failure
    Does NOT call Ollama — caller decides what to do with validated packet.
    """
    record = frank.write_import(process_id=process_id, packet_type=PacketType.AI)

    raw = build_packet(
        ring_origin=Ring.KERNEL,
        packet_type=PacketType.AI,
        token_a1=record.token_a1,
        token_b1=record.token_b1,
        process_id=process_id,
        import_id=record.import_id,
        payload_a=prompt.encode(),
        payload_b=b"",
    )

    pkt = frank.receive_packet(raw)
    return pkt, record


# ---------------------------------------------------------------------------
# 1. UNIT TESTS — Frank packet mechanics, no external deps
# ---------------------------------------------------------------------------

class TestFrankRingChain(unittest.TestCase):
    """Ring chain construction and sovereign identity."""

    def test_ring_chain_builds(self):
        f0 = build_ring_chain()
        self.assertEqual(f0.ring, Ring.KERNEL)

    def test_frank_below_installed(self):
        f0 = build_ring_chain()
        self.assertIsNotNone(f0._frank_below)
        self.assertEqual(f0._frank_below.ring, Ring.ONE)

    def test_full_chain_depth(self):
        f0 = build_ring_chain()
        f1 = f0._frank_below
        f2 = f1._frank_below
        f3 = f2._frank_below
        self.assertEqual(f3.ring, Ring.THREE)
        self.assertIsNone(f3._frank_below)

    def test_status_shape(self):
        f0 = Frank(Ring.KERNEL)
        s = f0.status()
        self.assertIn("ring", s)
        self.assertIn("active_imports", s)
        self.assertIn("total_imports", s)
        self.assertIn("ai_instances", s)


class TestFrankImportLifecycle(unittest.TestCase):
    """Import write → use → expire."""

    def setUp(self):
        self.frank = Frank(Ring.KERNEL)

    def test_write_import_registers(self):
        rec = self.frank.write_import(process_id=100, packet_type=PacketType.INTERNAL)
        self.assertIn(rec.import_id, self.frank._imports)
        self.assertTrue(rec.is_valid)

    def test_token_registered(self):
        rec = self.frank.write_import(process_id=101, packet_type=PacketType.INTERNAL)
        self.assertIn(rec.token_a1, self.frank._tokens)

    def test_expire_invalidates_import(self):
        rec = self.frank.write_import(process_id=102, packet_type=PacketType.INTERNAL)
        self.frank.expire_import(rec.import_id)
        self.assertFalse(rec.is_valid)

    def test_expire_removes_token(self):
        rec = self.frank.write_import(process_id=103, packet_type=PacketType.INTERNAL)
        self.frank.expire_import(rec.import_id)
        self.assertNotIn(rec.token_a1, self.frank._tokens)

    def test_expire_closes_window(self):
        rec = self.frank.write_import(process_id=104, packet_type=PacketType.INTERNAL)
        self.frank.expire_import(rec.import_id)
        window = self.frank._windows.get(rec.import_id)
        self.assertTrue(window.closed)

    def test_status_counts_active(self):
        rec = self.frank.write_import(process_id=105, packet_type=PacketType.INTERNAL)
        self.assertEqual(self.frank.status()["active_imports"], 1)
        self.frank.expire_import(rec.import_id)
        self.assertEqual(self.frank.status()["active_imports"], 0)


class TestFrankPacketValidation(unittest.TestCase):
    """Proxy wall — valid and invalid packet scenarios."""

    def setUp(self):
        self.frank = Frank(Ring.KERNEL)
        self.rec = self.frank.write_import(
            process_id=200, packet_type=PacketType.INTERNAL
        )
        self.raw = build_packet(
            ring_origin=Ring.KERNEL,
            packet_type=PacketType.INTERNAL,
            token_a1=self.rec.token_a1,
            token_b1=self.rec.token_b1,
            process_id=200,
            import_id=self.rec.import_id,
            payload_a=b"test payload",
            payload_b=b"",
        )

    def test_valid_packet_accepted(self):
        ok, pkt = self.frank.validate_packet(self.raw)
        self.assertTrue(ok)
        self.assertIsNotNone(pkt)

    def test_payload_preserved(self):
        ok, pkt = self.frank.validate_packet(self.raw)
        self.assertTrue(ok)
        self.assertEqual(pkt.payload_a, b"test payload")

    def test_too_small_rejected(self):
        ok, pkt = self.frank.validate_packet(b"\x00" * 10)
        self.assertFalse(ok)
        self.assertIsNone(pkt)

    def test_bad_magic_rejected(self):
        tampered = bytearray(self.raw)
        tampered[0] = 0xDE  # corrupt magic
        ok, pkt = self.frank.validate_packet(bytes(tampered))
        self.assertFalse(ok)

    def test_bad_token_rejected(self):
        tampered = bytearray(self.raw)
        # Corrupt A1 token
        tampered[TOKEN_OFFSET] ^= 0xFF
        ok, pkt = self.frank.validate_packet(bytes(tampered))
        self.assertFalse(ok)

    def test_bad_mirror_rejected(self):
        tampered = bytearray(self.raw)
        # Corrupt B1 mirror
        tampered[MIRROR_OFFSET] ^= 0xFF
        ok, pkt = self.frank.validate_packet(bytes(tampered))
        self.assertFalse(ok)

    def test_expired_import_rejected(self):
        self.frank.expire_import(self.rec.import_id)
        ok, pkt = self.frank.validate_packet(self.raw)
        self.assertFalse(ok)

    def test_receive_returns_packet(self):
        pkt = self.frank.receive_packet(self.raw)
        self.assertIsNotNone(pkt)

    def test_receive_after_expire_returns_none(self):
        self.frank.expire_import(self.rec.import_id)
        pkt = self.frank.receive_packet(self.raw)
        self.assertIsNone(pkt)


class TestHelixWindow(unittest.TestCase):
    """Window lifecycle — expand, contract, close."""

    def setUp(self):
        self.frank = Frank(Ring.KERNEL)
        self.rec = self.frank.write_import(
            process_id=300, packet_type=PacketType.INTERNAL
        )

    def test_window_starts_at_one(self):
        window = self.frank._windows[self.rec.import_id]
        self.assertEqual(window.max_replicas, 1)

    def test_expand_window(self):
        self.frank.adjust_window(self.rec.import_id, load_delta=3)
        window = self.frank._windows[self.rec.import_id]
        self.assertEqual(window.max_replicas, 4)

    def test_contract_window(self):
        self.frank.adjust_window(self.rec.import_id, load_delta=4)
        self.frank.adjust_window(self.rec.import_id, load_delta=-2)
        window = self.frank._windows[self.rec.import_id]
        self.assertEqual(window.max_replicas, 3)

    def test_contract_floor_is_one(self):
        self.frank.adjust_window(self.rec.import_id, load_delta=-99)
        window = self.frank._windows[self.rec.import_id]
        self.assertEqual(window.max_replicas, 1)

    def test_closed_window_ignores_expand(self):
        self.frank.expire_import(self.rec.import_id)
        self.frank.adjust_window(self.rec.import_id, load_delta=5)
        window = self.frank._windows[self.rec.import_id]
        self.assertEqual(window.max_replicas, 1)  # unchanged


class TestPacketRoundtrip(unittest.TestCase):
    """Raw bytes → DoubleHelixPacket → raw bytes round-trip."""

    def test_roundtrip_lossless(self):
        token_a1 = bytes(range(32))
        token_b1 = bytes(b ^ 0xAA for b in token_a1)
        raw = build_packet(
            ring_origin=Ring.ONE,
            packet_type=PacketType.AI,
            token_a1=token_a1,
            token_b1=token_b1,
            process_id=999,
            import_id=12345,
            payload_a=b"hello strand A",
            payload_b=b"hello strand B",
        )
        pkt = DoubleHelixPacket.from_bytes(raw)
        self.assertEqual(pkt.magic, FRANK_MAGIC)
        self.assertEqual(pkt.ring_origin, Ring.ONE)
        self.assertEqual(pkt.packet_type, PacketType.AI)
        self.assertEqual(pkt.payload_a, b"hello strand A")
        self.assertEqual(pkt.payload_b, b"hello strand B")

    def test_empty_payloads(self):
        token = bytes(32)
        raw = build_packet(
            ring_origin=Ring.KERNEL,
            packet_type=PacketType.INTERNAL,
            token_a1=token,
            token_b1=token,
            process_id=0,
            import_id=0,
        )
        pkt = DoubleHelixPacket.from_bytes(raw)
        self.assertEqual(pkt.payload_a, b"")
        self.assertEqual(pkt.payload_b, b"")


# ---------------------------------------------------------------------------
# 2. INTEGRATION TESTS — Frank AI lane → Ollama3
# ---------------------------------------------------------------------------

OLLAMA_UP = ollama_reachable()
SKIP_MSG  = "Ollama not running at localhost:11434 (run: ollama serve)"


@unittest.skipUnless(OLLAMA_UP, SKIP_MSG)
class TestOllamaConnection(unittest.TestCase):
    """Baseline Ollama3 reachability and model availability."""

    def test_ollama_reachable(self):
        self.assertTrue(ollama_reachable())

    def test_llama3_available(self):
        models = ollama_list_models()
        names  = [m.split(":")[0] for m in models]
        self.assertIn(
            "llama3", names,
            f"llama3 not found — run: ollama pull llama3\nAvailable: {models}",
        )

    def test_simple_generate(self):
        resp = ollama_generate("Reply with only the word: PONG")
        self.assertIsInstance(resp, str)
        self.assertGreater(len(resp), 0)

    def test_generate_returns_text(self):
        resp = ollama_generate("What is 2 + 2? Answer with only the number.")
        self.assertIn("4", resp)


@unittest.skipUnless(OLLAMA_UP, SKIP_MSG)
class TestFrankAILaneOllama(unittest.TestCase):
    """
    Full AI packet lifecycle through Frank, with Ollama3 as the AI backend.

    Flow:
      Frank.write_import(AI) → build_packet(payload_a=prompt)
        → Frank.receive_packet (validates lanes A1/B1, routes AI)
        → extract prompt from validated packet
        → ollama_generate(prompt)
        → assert response received
        → Frank.expire_import (window closes, nothing left behind)
    """

    def setUp(self):
        # Use Ring.KERNEL so Helix spawn warning fires at most once
        self.frank = Frank(Ring.KERNEL)

    def _dispatch_and_query(self, process_id: int, prompt: str) -> str:
        """
        Dispatch prompt through Frank's AI lane, call Ollama, return response.
        """
        pkt, record = frank_ai_dispatch(self.frank, process_id, prompt)

        # Frank must have accepted the AI packet
        self.assertIsNotNone(pkt, f"Frank rejected AI packet for PID={process_id}")
        self.assertEqual(pkt.packet_type, PacketType.AI)

        # Extract prompt from validated packet (payload_a is the AI content lane)
        extracted_prompt = pkt.payload_a.decode()
        self.assertEqual(extracted_prompt, prompt)

        # Send validated payload to Ollama3
        response = ollama_generate(extracted_prompt)

        # Clean up — import expires, window closes, nothing left behind
        self.frank.expire_import(record.import_id)

        return response

    def test_basic_ai_dispatch(self):
        """Single AI packet through Frank → Ollama3 → response received."""
        resp = self._dispatch_and_query(
            process_id=1000,
            prompt="Reply with only the word: PONG",
        )
        self.assertIsInstance(resp, str)
        self.assertGreater(len(resp), 0)

    def test_import_expires_after_dispatch(self):
        """After dispatch + expire, the token is gone."""
        pkt, record = frank_ai_dispatch(self.frank, process_id=1001, prompt="test")
        self.assertIsNotNone(pkt)
        self.frank.expire_import(record.import_id)
        self.assertNotIn(record.token_a1, self.frank._tokens)

    def test_replay_after_expire_rejected(self):
        """Replayed packet rejected once import expires — custody enforced."""
        rec = self.frank.write_import(process_id=1002, packet_type=PacketType.AI)
        raw = build_packet(
            ring_origin=Ring.KERNEL,
            packet_type=PacketType.AI,
            token_a1=rec.token_a1,
            token_b1=rec.token_b1,
            process_id=1002,
            import_id=rec.import_id,
            payload_a=b"replay attempt",
            payload_b=b"",
        )
        # First pass — accepted
        self.assertIsNotNone(self.frank.receive_packet(raw))
        # Expire
        self.frank.expire_import(rec.import_id)
        # Replay — must be rejected
        self.assertIsNone(self.frank.receive_packet(raw))

    def test_multiple_independent_ai_imports(self):
        """Frank handles concurrent AI imports without cross-contamination."""
        prompts = [
            (2000, "Reply with only: ALPHA"),
            (2001, "Reply with only: BETA"),
            (2002, "Reply with only: GAMMA"),
        ]
        responses = []
        records   = []

        for pid, prompt in prompts:
            pkt, rec = frank_ai_dispatch(self.frank, pid, prompt)
            self.assertIsNotNone(pkt)
            resp = ollama_generate(pkt.payload_a.decode())
            responses.append(resp)
            records.append(rec)

        # All three returned something
        for resp in responses:
            self.assertGreater(len(resp), 0)

        # Clean up all imports
        for rec in records:
            self.frank.expire_import(rec.import_id)

        # All tokens gone
        for rec in records:
            self.assertNotIn(rec.token_a1, self.frank._tokens)

    def test_ai_response_coherent(self):
        """Ollama3 response via Frank is semantically coherent."""
        resp = self._dispatch_and_query(
            process_id=3000,
            prompt="What is the capital of France? Answer in one word.",
        )
        self.assertIn("Paris", resp)

    def test_frank_status_during_dispatch(self):
        """Status reflects active AI import during dispatch lifecycle."""
        pkt, rec = frank_ai_dispatch(self.frank, process_id=4000, prompt="status test")
        self.assertIsNotNone(pkt)
        # Import is still live (not yet expired)
        self.assertGreaterEqual(self.frank.status()["active_imports"], 1)
        self.frank.expire_import(rec.import_id)
        # After expire, count drops
        self.assertEqual(
            self.frank.status()["active_imports"],
            0,
        )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("""
╔══════════════════════════════════════════════╗
║  Frank × Ollama3 — Test Suite                ║
║  Unit: packet mechanics, import lifecycle     ║
║  Integration: AI lane → Ollama3 dispatch      ║
╚══════════════════════════════════════════════╝
""")
    if not OLLAMA_UP:
        print(f"[WARN] {SKIP_MSG}")
        print("[WARN] Integration tests will be SKIPPED.\n")
    else:
        print(f"[OK] Ollama running at {OLLAMA_HOST}:{OLLAMA_PORT}")
        try:
            models = ollama_list_models()
            print(f"[OK] Available models: {models}\n")
        except Exception:
            print("[WARN] Could not list models — ensure llama3 is pulled.\n")

    unittest.main(verbosity=2)
