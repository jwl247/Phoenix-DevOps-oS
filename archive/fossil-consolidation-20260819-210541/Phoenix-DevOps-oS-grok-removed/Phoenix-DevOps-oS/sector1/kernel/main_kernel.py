#!/usr/bin/env python3
"""
main_kernel.py — Phoenix Universal Kernel
Boots the Helix Lightning Kernel (CoPES substrate).

Frank5 → ProcessLibrary → FrankSpawn → HelixI/HelixE — fully operational.
LLM Engine (llm_engine.py) + File Tree Service (file_tree_service.py) boot
alongside — LLMs bigger than hardware via paged vRAM, drag-drop clone ops.

Phoenix DevOps OS | jwl247 | GPL v3
"""

import sys
import logging
import time
from pathlib import Path

# HLK is the sibling submodule in the phoenix-devops repo
HLK = Path(__file__).parent.parent / "helix_lightning_kernel"
sys.path.insert(0, str(HLK))

from franken5 import get_frank
from process_library import boot_library
from frank_spawn import start_spawn
from helixi import HelixI
from helixe import HelixE

# Phoenix extensions (always in same dir as this file)
_here = Path(__file__).parent
sys.path.insert(0, str(_here))

log = logging.getLogger("phoenix_uk")


def _boot_llm_engine(helix_system=None):
    """Start the LLM offload engine + async model warmup."""
    try:
        from llm_engine import get_engine
        engine = get_engine(helix_system=helix_system)
        log.info("  LLM engine   online  (Ollama paged-vRAM)")
        log.info("  Models: large=%s medium=%s small=%s",
                 engine.ollama.available_models()[:3] or "pending warmup",
                 "", "")
        return engine
    except Exception as e:
        log.warning("  LLM engine not started: %s", e)
        return None


def _boot_file_tree():
    """Start file tree + clone socket service on ports 7703-7704."""
    try:
        from file_tree_service import start
        start()
        log.info("  FileTree svc online  (clone/drag-drop on 7703-7704)")
    except Exception as e:
        log.warning("  FileTree service not started: %s", e)


def boot():
    log.info("=== Phoenix Universal Kernel — CoPES Substrate Booting ===")

    frank   = get_frank()
    frank.boot()

    library = boot_library(frank)
    from helix_suit_override import apply as _helix_fix
    _helix_fix(library)
    spawner = start_spawn(frank, process_library=library)

    helix_i = HelixI(frank)
    helix_i.start_socket_listeners()

    helix_e = HelixE(frank)
    helix_e.start_output_sockets()
    spawner.helix_e = helix_e          # wire egress into the spawner (bridge)

    # ── Phoenix extensions ────────────────────────────────────────────────────
    # Try to connect Helix memory stack (CoPES) — graceful if not present
    helix_system = None
    try:
        copes = Path(__file__).parent.parent / "CoPES" / "src"
        sys.path.insert(0, str(copes))
        from helix_memory import HelixSystem
        import helix as _helix_mod
        helix_system = HelixSystem(helix=_helix_mod._get_global_helix())
        helix_system.start()
    except Exception as e:
        log.info("  Helix memory stack not connected: %s (standalone mode)", e)

    llm_engine = _boot_llm_engine(helix_system)
    _boot_file_tree()

    # Status server — Seelen UI toolbar plugins poll localhost:8765
    try:
        from phoenix_status_server import start as _start_status
        _start_status()
        log.info("  Status server online  http://localhost:8765")
    except Exception as e:
        log.warning("  Status server not started: %s", e)
    # ─────────────────────────────────────────────────────────────────────────

    log.info("=== Phoenix Universal Kernel OPERATIONAL ===")
    log.info("  Helix-I  intake   7701-7704")
    log.info("  Helix-E  output   7805-7808")
    log.info("  Suits in closet:  %d", len(library))

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        spawner.stop()
        helix_i.stop()
        helix_e.stop()
        frank.shutdown()
        log.info("Kernel shutdown complete.")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    )
    boot()
