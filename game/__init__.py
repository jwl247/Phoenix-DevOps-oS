"""
Sacrifice — Game Systems
Phoenix DevOps OS | jwl247 | GPL v3

Phase 2 — Military Systems (COMPLETE)
  draft_card   : player identity, cryptographic signing
  mos          : Military Occupational Specialty assignment
  rank         : rank system, Frank-issued unit commands
  hospital     : wound management, real-time recovery
  archive      : permadeath, permanent draft card archive
  jacket       : complete service record
  frank_world  : Frank world-orchestrator integration

Phase 3 — Jacket and Accords (COMPLETE)
  accord       : accord system — challenge, sign, conclude, world history
  tribunal     : player-run tribunal — charges, jury, verdict, sentence
  king_theater : King of Theater — crown, challenge, disruptor, AO control
  footage      : footage and kill board — clips, top kills, jacket entries

All systems wire into the Frank kernel via franken5.
Nothing in game/ makes decisions Frank hasn't sanctioned.
Frank witnesses. Frank archives. Frank never forgets.
"""

# Phase 2
from .draft_card  import DraftCard, issue_draft_card, load_draft_card
from .mos         import MOS, MOSAssignment, assess_mos
from .rank        import Rank, RankRecord, promote, issue_unit
from .hospital    import WoundSeverity, HospitalRecord, admit, discharge
from .archive     import Archive, archive_fallen, load_archive
from .jacket      import Jacket, JacketEntry, JacketCategory
from .frank_world import FrankWorld, get_world

# Phase 3
from .accord import (
    Accord, AccordTerms, AccordStatus, AccordOutcome, AccordType,
    propose_accord, countersign_accord, activate_accord,
    conclude_accord, void_accord, add_observer, check_expiry,
    world_history_entry as accord_history_entry,
)
from .tribunal import (
    TribunalCharge, TribunalRecord, TribunalStatus,
    TribunalVerdict, TribunalSentence, Testimony, JuryVote,
    file_charges, open_tribunal, add_testimony, cast_vote,
    render_verdict, execute_sentence,
    world_history_entry as tribunal_history_entry,
)
from .king_theater import (
    KingTheaterState, KingEvent,
    crown_king, challenge_king, conclude_challenge,
    grant_disruptor, use_disruptor, set_spawn_rules,
    world_history_entry as king_history_entry,
)
from .footage import (
    FootageClip, FootageType, AOKillBoard,
    record_footage, set_r2_key, try_flag_top_kill,
    get_top_kills, kill_rank,
    jacket_entry as footage_jacket_entry,
    world_history_entry as footage_history_entry,
)

__all__ = [
    # Phase 2
    "DraftCard", "issue_draft_card", "load_draft_card",
    "MOS", "MOSAssignment", "assess_mos",
    "Rank", "RankRecord", "promote", "issue_unit",
    "WoundSeverity", "HospitalRecord", "admit", "discharge",
    "Archive", "archive_fallen", "load_archive",
    "Jacket", "JacketEntry", "JacketCategory",
    "FrankWorld", "get_world",
    # Phase 3
    "Accord", "AccordTerms", "AccordStatus", "AccordOutcome", "AccordType",
    "propose_accord", "countersign_accord", "activate_accord",
    "conclude_accord", "void_accord", "add_observer", "check_expiry",
    "accord_history_entry",
    "TribunalCharge", "TribunalRecord", "TribunalStatus",
    "TribunalVerdict", "TribunalSentence", "Testimony", "JuryVote",
    "file_charges", "open_tribunal", "add_testimony", "cast_vote",
    "render_verdict", "execute_sentence", "tribunal_history_entry",
    "KingTheaterState", "KingEvent",
    "crown_king", "challenge_king", "conclude_challenge",
    "grant_disruptor", "use_disruptor", "set_spawn_rules",
    "king_history_entry",
    "FootageClip", "FootageType", "AOKillBoard",
    "record_footage", "set_r2_key", "try_flag_top_kill",
    "get_top_kills", "kill_rank",
    "footage_jacket_entry", "footage_history_entry",
    # Phase 4
    "Provenance", "Quality", "ServiceRequirement", "ItemSpec", "ItemCategory",
    "Item", "Loadout", "default_items",
    "VehicleClass", "VehicleModel", "VehicleRegistry", "Vehicle", "VehicleStatus",
    "UpgradeSpec", "UpgradeSlot", "UpgradeKind", "AssetSlot", "AssetStatus",
    "default_registry",
]

# Phase 4
from .equipment import (
    Provenance, Quality, ServiceRequirement, ItemSpec, ItemCategory, Item, Loadout,
    default_items,
)
from .vehicle import (
    VehicleClass, VehicleModel, VehicleRegistry, Vehicle, VehicleStatus,
    UpgradeSpec, UpgradeSlot, UpgradeKind, AssetSlot, AssetStatus, default_registry,
)
