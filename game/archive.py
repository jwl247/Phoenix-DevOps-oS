#!/usr/bin/env python3
"""
archive.py — Permadeath & Permanent Archive
Phoenix DevOps OS | jwl247 | GPL v3

A character's death is not an ending. It is a conclusion.
The draft card is archived permanently.
The jacket remains public.
The sacrifice log is preserved.
New recruits in boot camp may hear the name of those who died with honour.

Re-enlistment is permitted. A new draft card is issued.
The old record stands.

GDD §5.3 — Death & Legacy.

Archive storage: JSON files under PHOENIX_ARCHIVE_ROOT
(env var, default: /var/lib/phoenix/archive).
Every write is atomic. Nothing is ever deleted.
"""

from __future__ import annotations

import json
import os
import time
import hashlib
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Archive paths
# ---------------------------------------------------------------------------

def _archive_root() -> Path:
    root = os.environ.get("PHOENIX_ARCHIVE_ROOT", "/var/lib/phoenix/archive")
    return Path(root)


def _card_path(card_id: str) -> Path:
    # Shard by first 2 chars of card_id to avoid huge flat directories
    shard = card_id[:2]
    return _archive_root() / "cards" / shard / f"{card_id}.json"


def _index_path() -> Path:
    return _archive_root() / "index.json"


def _sacrifice_log_path() -> Path:
    return _archive_root() / "sacrifice_log.json"


def _boot_camp_legends_path() -> Path:
    return _archive_root() / "boot_camp_legends.json"


# ---------------------------------------------------------------------------
# Archive entry
# ---------------------------------------------------------------------------

@dataclass
class ArchiveEntry:
    """
    The permanent public record of a fallen or re-enlisted soldier.
    Immutable after creation — Frank never rewrites the dead.
    """
    card_id:            str
    player_id:          str
    callsign:           str
    enlistment_ts:      float
    death_ts:           Optional[float]
    cause_of_death:     Optional[str]
    theater:            Optional[str]
    mos_code:           Optional[str]
    rank_code:          Optional[str]
    archived_ts:        float       = field(default_factory=time.time)
    archive_type:       str         = "KIA"             # "KIA" | "REENLIST"
    service_days:       float       = 0.0
    honour_score:       float       = 0.0               # 0..1 — from jacket
    sacrifice_entries:  list        = field(default_factory=list)
    promoted_to_legend: bool        = False
    integrity_hash:     str         = ""

    def __post_init__(self):
        if not self.integrity_hash:
            self.integrity_hash = self._compute_hash()
        if self.death_ts and self.enlistment_ts:
            self.service_days = (self.death_ts - self.enlistment_ts) / 86400

    def _compute_hash(self) -> str:
        """SHA3-256 of the immutable record fields — tamper detection."""
        blob = json.dumps({
            "card_id":      self.card_id,
            "player_id":    self.player_id,
            "callsign":     self.callsign,
            "death_ts":     self.death_ts,
            "archived_ts":  self.archived_ts,
        }, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha3_256(blob).hexdigest()

    def verify_integrity(self) -> bool:
        return self.integrity_hash == self._compute_hash()

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ArchiveEntry":
        return cls(**d)


# ---------------------------------------------------------------------------
# Sacrifice Log
# ---------------------------------------------------------------------------

@dataclass
class SacrificeEntry:
    """
    GDD §9.2 — The Sacrifice System.
    Recorded when a player sacrifices for an objective, a friend, or honour.
    Never deleted. Referenced in boot camp briefings.
    """
    card_id:        str
    player_id:      str
    callsign:       str
    ts:             float
    sacrifice_type: str     # "objective" | "friend" | "honor" | "last_stand"
    description:    str
    theater:        str
    witnessed_by:   list    = field(default_factory=list)   # list of player_ids


# ---------------------------------------------------------------------------
# Archive class
# ---------------------------------------------------------------------------

class Archive:
    """
    Phoenix permanent archive.
    All reads are public. No entry is ever deleted or modified after creation.
    """

    def __init__(self, root: Optional[Path] = None):
        self._root = root or _archive_root()
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        for sub in ("cards", "index", "logs"):
            (self._root / sub).mkdir(parents=True, exist_ok=True)

    # -----------------------------------------------------------------------
    # Write — atomic
    # -----------------------------------------------------------------------

    def save_entry(self, entry: ArchiveEntry) -> Path:
        """
        Persist a new archive entry. Atomic write — never partial.
        Returns the path written.
        """
        path = _card_path(entry.card_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            # Archive entries are immutable — refuse overwrite
            existing = ArchiveEntry.from_dict(json.loads(path.read_text()))
            if existing.integrity_hash == entry.integrity_hash:
                return path   # idempotent
            raise ValueError(
                f"Archive entry {entry.card_id} already exists and differs — "
                f"the dead cannot be rewritten"
            )
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(entry.to_dict(), indent=2), encoding="utf-8")
        tmp.replace(path)
        self._update_index(entry)
        return path

    def log_sacrifice(self, entry: SacrificeEntry) -> None:
        """Append to the permanent sacrifice log."""
        log_path = _sacrifice_log_path()
        entries = self._load_json_list(log_path)
        entries.append(asdict(entry))
        self._atomic_write(log_path, entries)

    def promote_to_legend(self, card_id: str) -> None:
        """
        GDD §11.3 — mark an entry as boot camp legend.
        Recruits in basic training will hear their story.
        """
        path = _card_path(card_id)
        if not path.exists():
            raise FileNotFoundError(f"No archive entry for {card_id}")
        entry = ArchiveEntry.from_dict(json.loads(path.read_text()))
        if entry.promoted_to_legend:
            return   # already a legend
        entry.promoted_to_legend = True
        # Legend promotion updates the record — only field allowed post-death
        tmp = path.with_suffix(".leg")
        tmp.write_text(json.dumps(entry.to_dict(), indent=2), encoding="utf-8")
        tmp.replace(path)
        # Also add to the boot camp legends list
        legends_path = _boot_camp_legends_path()
        legends = self._load_json_list(legends_path)
        legends.append({
            "card_id":  entry.card_id,
            "callsign": entry.callsign,
            "promoted": time.time(),
        })
        self._atomic_write(legends_path, legends)

    # -----------------------------------------------------------------------
    # Read
    # -----------------------------------------------------------------------

    def load_entry(self, card_id: str) -> Optional[ArchiveEntry]:
        path = _card_path(card_id)
        if not path.exists():
            return None
        return ArchiveEntry.from_dict(json.loads(path.read_text()))

    def boot_camp_legends(self) -> list[dict]:
        return self._load_json_list(_boot_camp_legends_path())

    def sacrifice_log(self) -> list[dict]:
        return self._load_json_list(_sacrifice_log_path())

    def index(self) -> list[dict]:
        return self._load_json_list(_index_path())

    # -----------------------------------------------------------------------
    # Internal
    # -----------------------------------------------------------------------

    def _update_index(self, entry: ArchiveEntry) -> None:
        idx_path = _index_path()
        idx = self._load_json_list(idx_path)
        idx.append({
            "card_id":       entry.card_id,
            "callsign":      entry.callsign,
            "archive_type":  entry.archive_type,
            "archived_ts":   entry.archived_ts,
            "service_days":  round(entry.service_days, 2),
            "legend":        entry.promoted_to_legend,
        })
        self._atomic_write(idx_path, idx)

    def _load_json_list(self, path: Path) -> list:
        if not path.exists():
            return []
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _atomic_write(self, path: Path, data: list) -> None:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(path)


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

_default_archive: Optional[Archive] = None


def _get_archive() -> Archive:
    global _default_archive
    if _default_archive is None:
        _default_archive = Archive()
    return _default_archive


def archive_fallen(
    card: "DraftCard",          # type: ignore[name-defined]  — imported by callers
    cause: str,
    jacket_honour_score: float = 0.0,
    sacrifice_entries: list = None,
    archive: "Optional[Archive]" = None,
) -> ArchiveEntry:
    """
    Convenience function: build and save an ArchiveEntry for a KIA card.
    Marks the draft card as KIA first if not already.
    """
    from .draft_card import CardStatus
    if card.status != CardStatus.KIA:
        card.kill(cause)

    entry = ArchiveEntry(
        card_id           = card.card_id,
        player_id         = card.player_id,
        callsign          = card.callsign,
        enlistment_ts     = card.enlistment_ts,
        death_ts          = card.death_ts,
        cause_of_death    = cause,
        theater           = card.theater,
        mos_code          = card.mos_code,
        rank_code         = card.rank_code,
        archive_type      = "KIA",
        honour_score      = jacket_honour_score,
        sacrifice_entries = sacrifice_entries or [],
    )
    (archive or _get_archive()).save_entry(entry)
    return entry


def load_archive(card_id: str) -> Optional[ArchiveEntry]:
    return _get_archive().load_entry(card_id)
