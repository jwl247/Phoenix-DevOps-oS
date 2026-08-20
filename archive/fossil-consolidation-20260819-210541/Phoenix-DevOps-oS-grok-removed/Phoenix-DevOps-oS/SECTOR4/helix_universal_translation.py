#!/usr/bin/env python3
"""
helix_universal_translation.py — Helix translation pipeline for SECTOR4
Phoenix DevOps OS

Replaces the passthrough stub in cpt_conductor.py with a real implementation
backed by the working QuadralingualPacket from freewheeling.py.

Used by ComsConductor in cpt_conductor.py:
    from helix_universal_translation import HelixTranslationPipeline
    pipeline = HelixTranslationPipeline()
    packet   = pipeline.ingest(data, source_format="json", key=msg_id)
    raw      = pipeline.to_bytes(packet)

Also wires into dashboard "HELIX ENGINE" button via usys status output.
"""

import json
import time
import sys
import os
from typing import Any, Optional
from pathlib import Path

# Locate freewheeling.py — it lives in coms1/ (canonical copy)
_SECTOR4_DIR = Path(__file__).parent
_COMS1_DIR   = _SECTOR4_DIR / "coms1"

# Try importing the working DoubleHelixStorage from coms1/freewheeling.py
_helix_db = None
try:
    sys.path.insert(0, str(_COMS1_DIR))
    from freewheeling import HelixDB, StorageLanguage, QuadralingualPacket
    _helix_db = HelixDB(initial_levels=5)
    _HELIX_OK = True
except ImportError as e:
    _HELIX_OK = False
    _import_error = str(e)


# ══════════════════════════════════════════════════════════════════════════════
# HELIX TRANSLATION PIPELINE
# ══════════════════════════════════════════════════════════════════════════════

class HelixTranslationPipeline:
    """
    Real Helix translation pipeline.

    Wraps DoubleHelixStorage from coms1/freewheeling.py.
    Every piece of data that passes through a ComsConductor
    is stored as a QuadralingualPacket — simultaneously accessible
    as VECTOR, NOSQL, RELATIONAL, or TIMESERIES.

    Falls back to passthrough if freewheeling.py unavailable.
    """

    def __init__(self):
        self._online = _HELIX_OK
        self._db     = _helix_db
        self._stats  = {
            "ingested"    : 0,
            "passthrough" : 0,
            "errors"      : 0,
            "started_at"  : time.time(),
        }
        if self._online:
            print("[HelixTranslation] online — QuadralingualPacket backed by DoubleHelixStorage")
        else:
            print(f"[HelixTranslation] passthrough mode — freewheeling.py unavailable: {_import_error if not _HELIX_OK else ''}")

    def ingest(self, data: Any, source_format: str = "json", key: str = "") -> Any:
        """
        Translate data into a QuadralingualPacket.
        Stores it in the Helix and returns the packet.

        Falls back to returning data unchanged if Helix unavailable.
        """
        if not self._online or not self._db:
            self._stats["passthrough"] += 1
            return data

        try:
            packet_id = key or f"pkt_{int(time.time()*1000)}"

            # Normalise input to something HelixDB understands
            if source_format == "json" and isinstance(data, str):
                try:
                    raw = json.loads(data)
                except json.JSONDecodeError:
                    raw = data
            else:
                raw = data

            packet = self._db.store(packet_id, raw)
            self._stats["ingested"] += 1
            return packet

        except Exception as e:
            self._stats["errors"] += 1
            # Never block the caller — return data unchanged
            return data

    def to_bytes(self, data: Any) -> bytes:
        """
        Serialise a packet (or any data) to bytes for transport.
        If data is a QuadralingualPacket, returns its NOSQL form as JSON.
        Otherwise falls back to json.dumps or str encoding.
        """
        try:
            # QuadralingualPacket — use NOSQL view as canonical bytes form
            if _HELIX_OK and isinstance(data, QuadralingualPacket):
                return json.dumps(data.as_nosql(), default=str).encode()

            if isinstance(data, (dict, list)):
                return json.dumps(data, default=str).encode()

            if isinstance(data, bytes):
                return data

            return str(data).encode()

        except Exception:
            return b""

    def get_in_language(self, packet: Any, language: str) -> Any:
        """
        Retrieve a packet in a specific storage language.
        language: "vector" | "nosql" | "relational" | "timeseries"
        Returns None if packet is not a QuadralingualPacket.
        """
        if not _HELIX_OK or not isinstance(packet, QuadralingualPacket):
            return None
        try:
            lang_map = {
                "vector"    : StorageLanguage.VECTOR,
                "nosql"     : StorageLanguage.NOSQL,
                "relational": StorageLanguage.RELATIONAL,
                "timeseries": StorageLanguage.TIMESERIES,
            }
            lang = lang_map.get(language.lower())
            if lang is None:
                return None
            return packet.in_language(lang)
        except Exception:
            return None

    def helix_status(self) -> dict:
        """
        Returns a status dict compatible with the dashboard
        'HELIX ENGINE' display (dashboard.js showHelixEngine()).

        Fields match what the dashboard terminal expects.
        """
        uptime_s = int(time.time() - self._stats["started_at"])
        base = {
            "online"      : self._online,
            "uptime_s"    : uptime_s,
            "ingested"    : self._stats["ingested"],
            "passthrough" : self._stats["passthrough"],
            "errors"      : self._stats["errors"],
        }

        if self._online and self._db:
            try:
                helix_stats = self._db.stats()
                base.update({
                    "levels"             : helix_stats.get("levels", 0),
                    "total_blocks"       : helix_stats.get("total_blocks", 0),
                    "total_packets"      : helix_stats.get("total_packets", 0),
                    "compression_factor" : helix_stats.get("compression_factor", 1.0),
                    "dandelion_heat"     : helix_stats.get("dandelion_heat", 0.0),
                    "active_lanes"       : helix_stats.get("active_lanes", 0),
                    "storage_distribution": helix_stats.get("storage_distribution", {}),
                    # Dashboard-facing fields
                    "languages"          : 4,
                    "status"             : "OPERATIONAL",
                })
            except Exception:
                base["status"] = "DEGRADED"
        else:
            base["status"] = "PASSTHROUGH"

        return base

    def print_status(self):
        """
        Print status in the format the dashboard terminal overlay expects.
        Called when dashboard button action='helix' fires executeCommand().
        """
        s = self.helix_status()
        print("=== HELIX ENGINE STATUS ===")
        print(f"Status       : {s['status']}")
        print(f"Online       : {'YES' if s['online'] else 'NO (passthrough)'}")
        print(f"Uptime       : {s['uptime_s']}s")
        print(f"Packets      : {s.get('total_packets', 0)} stored")
        print(f"Levels       : {s.get('levels', 0)} helix rungs")
        print(f"Blocks       : {s.get('total_blocks', 0)} octahedron blocks")
        print(f"Languages    : {s.get('languages', 4)} (VECTOR/NOSQL/RELATIONAL/TIMESERIES)")
        print(f"Compression  : {s.get('compression_factor', 1.0):.2f} (1.0=expanded)")
        print(f"Heat         : {s.get('dandelion_heat', 0.0):.2f}")
        print(f"Ingested     : {s['ingested']} packets translated")
        dist = s.get("storage_distribution", {})
        if dist:
            print(f"Distribution : {dist}")


# ══════════════════════════════════════════════════════════════════════════════
# STANDALONE TEST / usys status hook
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    pipeline = HelixTranslationPipeline()
    pipeline.print_status()

    if pipeline._online:
        print("\n--- Translation test ---")

        # Test: ingest a dict (mimics a ComsConductor message)
        msg = {"id": "test_001", "target_ring": "coms1", "data": {"value": 42}}
        packet = pipeline.ingest(msg, source_format="json", key="test_001")
        print(f"Ingested: {type(packet).__name__}")

        # Show all 4 language views
        print(f"  NOSQL     : {pipeline.get_in_language(packet, 'nosql')}")
        print(f"  VECTOR    : {pipeline.get_in_language(packet, 'vector')}")
        print(f"  RELATIONAL: {pipeline.get_in_language(packet, 'relational')}")

        # Round-trip to bytes
        raw = pipeline.to_bytes(packet)
        print(f"  to_bytes  : {len(raw)} bytes")
