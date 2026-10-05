#!/usr/bin/env python3
"""
jacket.py — Permanent Service Record
Phoenix DevOps OS | jwl247 | GPL v3

Frank does not track statistics. Frank records the truth.
The jacket is a player's complete military record — public, permanent, uneditable.
Anyone can look up anyone before accepting a challenge, following an officer,
or signing an accord. Your reputation is your currency. Frank is the bank.

GDD §6 — The Jacket.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Jacket Categories
# ---------------------------------------------------------------------------

class JacketCategory(str, Enum):
    """GDD §6.1 — Jacket contents table."""
    SERVICE_HISTORY  = "SERVICE_HISTORY"   # Every battle, theater, assignment
    FOOTAGE          = "FOOTAGE"           # Frank-captured moments — heroism & cowardice
    TRIBUNAL         = "TRIBUNAL"          # Every charge, every verdict — permanent
    SACRIFICE        = "SACRIFICE"         # What you gave and for whom — never deleted
    FIVE_MINUTE      = "FIVE_MINUTE"       # Your defining moments; stayed or ran
    COMMENDATION     = "COMMENDATION"      # Named by players, officers, Red Baron Protocol
    DRAFT_CARD_REF   = "DRAFT_CARD"        # Who you were when you enlisted
    ACCORD_HISTORY   = "ACCORD_HISTORY"    # Every challenge named, accepted, won, lost
    VEHICLE_RECORD   = "VEHICLE_RECORD"    # Every vehicle operated, lost, captured
    UNIT_RECORD      = "UNIT_RECORD"       # Every soldier under command and their fate
    COWARDICE        = "COWARDICE"         # Hiding, abandoning formation, recklessness
    COURT_MARTIAL    = "COURT_MARTIAL"     # Court martial record — public and permanent


# ---------------------------------------------------------------------------
# Jacket Entries
# ---------------------------------------------------------------------------

@dataclass
class JacketEntry:
    """
    A single immutable entry in a jacket.
    Written once. Never edited. Never deleted.
    Frank witnesses every write.
    """
    entry_id:       str
    category:       JacketCategory
    ts:             float
    theater:        str
    summary:        str             # one-line public summary
    detail:         dict            # structured detail — schema varies by category
    witnessed_by:   str             # player_id or "FRANK" or "TRIBUNAL"
    public:         bool = True     # all entries are public by default

    def to_dict(self) -> dict:
        d = asdict(self)
        d["category"] = self.category.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "JacketEntry":
        d = dict(d)
        d["category"] = JacketCategory(d["category"])
        return cls(**d)


# ---------------------------------------------------------------------------
# The Jacket
# ---------------------------------------------------------------------------

@dataclass
class Jacket:
    """
    A player's complete, immutable, permanent military record.
    Public. Anyone can read it.
    Written by Frank and the game systems. Never edited after writing.

    The five-minute doctrine (GDD §6.2):
    Every soldier will face their five minutes.
    Frank is watching. The jacket will record which choice was made.
    """
    player_id:          str
    card_id:            str
    callsign:           str
    created_ts:         float               = field(default_factory=time.time)
    entries:            list[JacketEntry]   = field(default_factory=list)
    honour_score:       float               = 0.5       # 0..1 — Frank's running assessment
    cowardice_flags:    int                 = 0         # system-tracked cowardice count
    tribunal_count:     int                 = 0
    commendation_count: int                 = 0

    # -----------------------------------------------------------------------
    # Write (append-only)
    # -----------------------------------------------------------------------

    def record(
        self,
        category:    JacketCategory,
        theater:     str,
        summary:     str,
        detail:      dict,
        witnessed_by: str = "FRANK",
        public:      bool = True,
    ) -> JacketEntry:
        """
        Append an immutable entry to the jacket.
        Returns the entry. Called by all game systems after any notable event.
        """
        import uuid
        entry = JacketEntry(
            entry_id     = str(uuid.uuid4()),
            category     = category,
            ts           = time.time(),
            theater      = theater,
            summary      = summary,
            detail       = detail,
            witnessed_by = witnessed_by,
            public       = public,
        )
        self.entries.append(entry)
        self._update_scores(entry)
        return entry

    # -----------------------------------------------------------------------
    # Convenience recorders (match GDD §6.1 table)
    # -----------------------------------------------------------------------

    def record_battle(self, theater: str, battle_name: str, outcome: str, detail: dict) -> JacketEntry:
        return self.record(
            JacketCategory.SERVICE_HISTORY, theater,
            f"{battle_name} — {outcome}", {"battle": battle_name, "outcome": outcome, **detail},
        )

    def record_footage(self, theater: str, moment: str, moment_type: str) -> JacketEntry:
        """heroism or cowardice — both get recorded."""
        return self.record(
            JacketCategory.FOOTAGE, theater,
            f"Frank-captured: {moment}", {"moment": moment, "type": moment_type},
        )

    def record_tribunal(
        self, theater: str, charge: str, verdict: str, detail: dict
    ) -> JacketEntry:
        self.tribunal_count += 1
        if verdict.lower() in ("guilty", "execution", "court_martial"):
            self.honour_score = max(0.0, self.honour_score - 0.15)
        return self.record(
            JacketCategory.TRIBUNAL, theater,
            f"Tribunal: {charge} → {verdict}",
            {"charge": charge, "verdict": verdict, **detail},
        )

    def record_sacrifice(
        self, theater: str, sacrifice_type: str, for_whom: str, description: str
    ) -> JacketEntry:
        """
        GDD §9.2 — Sacrifice entries are NEVER deleted.
        The advantages granted by sacrifice are never explained to the recipient.
        """
        self.honour_score = min(1.0, self.honour_score + 0.1)
        return self.record(
            JacketCategory.SACRIFICE, theater,
            f"Sacrifice ({sacrifice_type}) — {for_whom}",
            {"type": sacrifice_type, "for": for_whom, "description": description},
        )

    def record_five_minute(
        self, theater: str, choice: str, stayed: bool
    ) -> JacketEntry:
        """
        GDD §6.2 — The five-minute doctrine.
        stayed=True means they held. stayed=False means they ran.
        """
        label = "held their ground" if stayed else "broke and ran"
        if stayed:
            self.honour_score = min(1.0, self.honour_score + 0.05)
        else:
            self.honour_score = max(0.0, self.honour_score - 0.1)
        return self.record(
            JacketCategory.FIVE_MINUTE, theater,
            f"Five minutes: {label}",
            {"choice": choice, "stayed": stayed},
        )

    def record_commendation(
        self, theater: str, from_player_id: str, from_callsign: str, text: str
    ) -> JacketEntry:
        self.commendation_count += 1
        self.honour_score = min(1.0, self.honour_score + 0.03)
        return self.record(
            JacketCategory.COMMENDATION, theater,
            f"Commendation from {from_callsign}: {text[:80]}",
            {"from": from_player_id, "from_callsign": from_callsign, "text": text},
            witnessed_by = from_player_id,
        )

    def record_cowardice(
        self, theater: str, act: str, consequence: str
    ) -> JacketEntry:
        """
        GDD §8.3 — The Cowardice Law.
        Hiding behind troops, abandoning formation, organising without leading.
        """
        self.cowardice_flags += 1
        self.honour_score = max(0.0, self.honour_score - 0.2)
        return self.record(
            JacketCategory.COWARDICE, theater,
            f"Cowardice: {act}",
            {"act": act, "consequence": consequence},
        )

    def record_accord(
        self, theater: str, accord_name: str, role: str,
        outcome: str, opponent_id: str
    ) -> JacketEntry:
        """GDD §7.3 — Accord history. The accord name becomes permanent world history."""
        return self.record(
            JacketCategory.ACCORD_HISTORY, theater,
            f"Accord '{accord_name}': {role} → {outcome}",
            {"accord": accord_name, "role": role, "outcome": outcome, "opponent": opponent_id},
        )

    def record_vehicle(
        self, theater: str, vehicle_class: str, fate: str
    ) -> JacketEntry:
        return self.record(
            JacketCategory.VEHICLE_RECORD, theater,
            f"{vehicle_class} — {fate}",
            {"class": vehicle_class, "fate": fate},
        )

    def record_unit(
        self, theater: str, unit_name: str, member_count: int, casualties: int, outcome: str
    ) -> JacketEntry:
        return self.record(
            JacketCategory.UNIT_RECORD, theater,
            f"Commanded {unit_name} ({member_count} soldiers) — {outcome}",
            {"unit": unit_name, "members": member_count, "casualties": casualties, "outcome": outcome},
        )

    # -----------------------------------------------------------------------
    # Query
    # -----------------------------------------------------------------------

    def by_category(self, cat: JacketCategory) -> list[JacketEntry]:
        return [e for e in self.entries if e.category == cat]

    def reputation_summary(self) -> dict:
        """What any player sees before signing an accord or following this officer."""
        return {
            "callsign":          self.callsign,
            "honour_score":      round(self.honour_score, 3),
            "commendations":     self.commendation_count,
            "cowardice_flags":   self.cowardice_flags,
            "tribunal_count":    self.tribunal_count,
            "sacrifices":        len(self.by_category(JacketCategory.SACRIFICE)),
            "battles":           len(self.by_category(JacketCategory.SERVICE_HISTORY)),
            "five_minute_holds": sum(
                1 for e in self.by_category(JacketCategory.FIVE_MINUTE)
                if e.detail.get("stayed")
            ),
            "five_minute_runs":  sum(
                1 for e in self.by_category(JacketCategory.FIVE_MINUTE)
                if not e.detail.get("stayed")
            ),
        }

    # -----------------------------------------------------------------------
    # Serialisation
    # -----------------------------------------------------------------------

    def to_dict(self) -> dict:
        d = asdict(self)
        for e in d["entries"]:
            e["category"] = e["category"] if isinstance(e["category"], str) else e["category"].value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Jacket":
        d = dict(d)
        raw_entries = d.pop("entries", [])
        j = cls(**d)
        j.entries = [JacketEntry.from_dict(e) for e in raw_entries]
        return j

    # -----------------------------------------------------------------------
    # Internal
    # -----------------------------------------------------------------------

    def _update_scores(self, entry: JacketEntry) -> None:
        # Additional cross-category honour adjustments if needed
        # Category-specific adjustments happen in the record_* helpers above
        pass
