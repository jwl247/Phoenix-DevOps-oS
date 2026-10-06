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
# (in this repo it lives at sector1/helix-lightning; the old submodule name
# helix_lightning_kernel is kept as a fallback)
HLK = Path(__file__).parent.parent / "helix-lightning"
if not HLK.is_dir():
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
sys.path.insert(0, str(_here.parent))   # sector1/ — for `security` (CoPES guardians)

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

    # Addressed stages: a stage whose payload is JSON with {"suit": "<name>"}
    # goes to that suit — but only to suits imported through Genie (custody-
    # verified, tag "genie"). Everything else falls through to the channel
    # resolver as before. Without this, every ch1 stage lands on the `helix`
    # core suit, which has no run() and returns nothing (audit S1-F28).
    import json as _json
    def _addressed_resolver(packet):
        try:
            msg = _json.loads(packet.data)
        except (ValueError, TypeError, UnicodeDecodeError):
            return None
        name = msg.get("suit") if isinstance(msg, dict) else None
        if not isinstance(name, str):
            return None
        entry = library._suits.get(name)
        if entry is None or "genie" not in entry.tags:
            log.warning("  addressed stage for %r refused: not a Genie-imported suit", name)
            return None
        return library.get(name)
    spawner.register_resolver(_addressed_resolver)

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

    # ── Userspace Helix (sector1/helix/helix_vram.py) + the paging manager ──
    # The canonical double Helix: Dandelion at her center, zlib-5 on Strand A,
    # Strand B relief on disk. The paging manager (sector4/paging_helix.py) is
    # her memory-pressure source (RAM + commit charge) and grows/retires
    # Strand B with Doppelgangers as her tiered eviction needs it. Non-fatal.
    helix_vram = None
    pager = None
    try:
        import importlib.util as _hilu
        _repo = Path(__file__).resolve().parents[2]
        def _load(name, rel):
            sp = _hilu.spec_from_file_location(name, _repo / rel)
            mod = _hilu.module_from_spec(sp)
            sys.modules[name] = mod
            sp.loader.exec_module(mod)
            return mod
        _hv = _load("helix_vram", "sector1/helix/helix_vram.py")
        _ph = _load("paging_helix", "sector4/paging_helix.py")
        import os as _os
        _b_base = _os.environ.get("HELIX_VRAM_STRAND_B") or str(Path.home() / ".phoenix" / "helix" / "strandB")
        helix_vram = _hv.HelixMemoryManager(strand_b_dir=_b_base)
        _ph.clean_stale_strand_b(_b_base, keep=helix_vram.b_dir)
        _st = helix_vram.get_stats()
        log.info("  Helix (userspace) online  L1+L2 %d MB raw, L3 %d MB zlib-5, Strand B %d MB at %s, kernel-linked=%s",
                 _st["raw_budget_mb"], _st["z_budget_mb"], _st["strand_b_budget_mb"], helix_vram.b_dir,
                 _st["dandelion"]["kernel_linked"])
        pager = _ph.HelixPager(helix_vram, memory_fn=_hv.machine_memory)
        pager.start()
        # Suits run in this process; `import phoenix_ctx` gives them the live
        # Helix (and pager) instead of each suit building its own.
        import types as _types
        _ctx = _types.ModuleType("phoenix_ctx")
        _ctx.helix, _ctx.pager = helix_vram, pager
        sys.modules["phoenix_ctx"] = _ctx
    except Exception as e:
        log.warning("  Helix (userspace) / paging manager not started: %s", e)

    # ── CoPES guardian rotation — moving-target defense, armed before the ──────
    # rest comes up. Non-fatal: a boot without guardians is worse than nothing
    # but must not stop Phoenix from starting.
    try:
        from security import copes_runtime
        copes_runtime.boot(on_escalate=lambda inc: log.critical(
            "  GUARDIAN ESCALATION %s/%s", inc.get("type"), inc.get("guardian")))
        log.info("  CoPES guardians  armed   (%s)",
                 copes_runtime.status().get("active_guardian"))
    except Exception as e:
        log.warning("  CoPES guardians NOT armed: %s", e)

    llm_engine = _boot_llm_engine(helix_system)
    _boot_file_tree()

    # Status server — Seelen UI toolbar plugins poll localhost:8765
    try:
        from phoenix_status_server import start as _start_status
        _start_status()
        log.info("  Status server online  http://localhost:8765")
    except Exception as e:
        log.warning("  Status server not started: %s", e)

    # Genie control socket — PS7 (genie.ps1) talks to the RUNNING kernel:
    # live closet view + hot-load of custody-verified suits. Loopback only,
    # token-gated. Non-fatal: the kernel runs without it, Genie just can't
    # hot-load.
    genie_ctl = None
    try:
        import importlib.util as _ilu
        _gspec = _ilu.spec_from_file_location("genie_control", _here / "genie" / "genie_control.py")
        _gmod = _ilu.module_from_spec(_gspec)
        _gspec.loader.exec_module(_gmod)
        start_control = _gmod.start_control
        genie_ctl = start_control(library, frank=frank, spawner=spawner,
                                  helix_i=helix_i, helix_e=helix_e,
                                  helix=helix_vram, pager=pager)
    except Exception as e:
        log.warning("  Genie control not started: %s", e)
    # ─────────────────────────────────────────────────────────────────────────

    log.info("=== Phoenix Universal Kernel OPERATIONAL ===")
    log.info("  Helix-I  intake   7701-7704")
    log.info("  Helix-E  output   7805-7808")
    log.info("  Suits in closet:  %d", len(library))

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        if genie_ctl:
            genie_ctl.stop()
        if pager:
            pager.stop()
        if helix_vram:
            helix_vram.close()
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
