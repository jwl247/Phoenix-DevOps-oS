#!/usr/bin/env python3
"""
mos.py — Military Occupational Specialty System
Phoenix DevOps OS | jwl247 | GPL v3

MOS is assigned at the end of basic training based on OBSERVED PLAY STYLE.
It cannot be bought. It cannot be chosen directly.
Training determines MOS based on what you actually do.

MOS codes follow GDD section 3.3.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# MOS Definitions
# ---------------------------------------------------------------------------

class MOS(str, Enum):
    """Military Occupational Specialty codes per GDD §3.3."""
    FIELD_COMMANDER   = "11A"   # Strategic overview, unit orders, theater command
    RECON_INTEL       = "35F"   # Map exploration, enemy tracking, intel
    LOGISTICS_ENG     = "92A"   # Supply lines, equipment, fortification
    COMBAT_SPECIALIST = "11B"   # Direct engagement, battlefield execution
    VEHICLE_CREW      = "19K"   # Armor, air, naval operations
    PARATROOPER_OFF   = "11C"   # First-in assault leadership, high-risk — elite

    @property
    def title(self) -> str:
        return _MOS_TITLES[self]

    @property
    def description(self) -> str:
        return _MOS_DESC[self]

    @property
    def player_type(self) -> str:
        return _MOS_PLAYER_TYPE[self]


_MOS_TITLES = {
    MOS.FIELD_COMMANDER:   "Field Commander",
    MOS.RECON_INTEL:       "Recon / Intelligence",
    MOS.LOGISTICS_ENG:     "Logistics / Engineering",
    MOS.COMBAT_SPECIALIST: "Combat Specialist",
    MOS.VEHICLE_CREW:      "Vehicle Crew",
    MOS.PARATROOPER_OFF:   "Paratrooper Officer",
}

_MOS_DESC = {
    MOS.FIELD_COMMANDER:   "Strategic overview, unit orders, theater command",
    MOS.RECON_INTEL:       "Map exploration, enemy tracking, intel gathering",
    MOS.LOGISTICS_ENG:     "Supply lines, equipment, fortification building",
    MOS.COMBAT_SPECIALIST: "Direct engagement, battlefield execution",
    MOS.VEHICLE_CREW:      "Armor, air, and naval operations",
    MOS.PARATROOPER_OFF:   "First-in assault leadership — high-risk, elite competitive",
}

_MOS_PLAYER_TYPE = {
    MOS.FIELD_COMMANDER:   "RTS / strategic players",
    MOS.RECON_INTEL:       "Explorer players",
    MOS.LOGISTICS_ENG:     "Builder players",
    MOS.COMBAT_SPECIALIST: "Action players",
    MOS.VEHICLE_CREW:      "Vehicle specialists",
    MOS.PARATROOPER_OFF:   "Elite competitive players",
}


# ---------------------------------------------------------------------------
# Training Observation
# ---------------------------------------------------------------------------

@dataclass
class TrainingObservation:
    """
    Record of a single observed action during basic training.
    The MOS assessment engine reads these — not the player.
    """
    ts:         float           # when it happened
    action:     str             # what the player did
    category:   str             # which MOS archetype it points to
    weight:     float = 1.0     # how strongly it points there

    @classmethod
    def record(cls, action: str, category: str, weight: float = 1.0) -> "TrainingObservation":
        return cls(ts=time.time(), action=action, category=category, weight=weight)


@dataclass
class TrainingSession:
    """
    Accumulates observations across a player's basic training.
    assess_mos() reads this and returns the MOSAssignment.
    """
    player_id:      str
    card_id:        str
    started_ts:     float               = field(default_factory=time.time)
    observations:   list[TrainingObservation] = field(default_factory=list)
    complete:       bool                = False
    completed_ts:   Optional[float]     = None

    def observe(self, action: str, category: str, weight: float = 1.0) -> None:
        """Record a player action during training."""
        if self.complete:
            raise RuntimeError("Training session already complete — observations closed")
        self.observations.append(
            TrainingObservation.record(action, category, weight)
        )

    def finish(self) -> None:
        """Mark training as complete and ready for MOS assessment."""
        self.complete     = True
        self.completed_ts = time.time()

    # Convenience helpers for the game engine
    def command(self, sub: str = "issued_order") -> None:
        self.observe(sub, "FIELD_COMMANDER", 1.0)

    def recon(self, sub: str = "scouted_area") -> None:
        self.observe(sub, "RECON_INTEL", 1.0)

    def build(self, sub: str = "built_fortification") -> None:
        self.observe(sub, "LOGISTICS_ENG", 1.0)

    def fight(self, sub: str = "direct_engagement") -> None:
        self.observe(sub, "COMBAT_SPECIALIST", 1.0)

    def drive(self, sub: str = "operated_vehicle") -> None:
        self.observe(sub, "VEHICLE_CREW", 1.0)

    def lead_assault(self, sub: str = "first_in") -> None:
        self.observe(sub, "PARATROOPER_OFF", 2.0)   # elite weight


# ---------------------------------------------------------------------------
# MOS Assignment
# ---------------------------------------------------------------------------

_CATEGORY_TO_MOS = {
    "FIELD_COMMANDER":   MOS.FIELD_COMMANDER,
    "RECON_INTEL":       MOS.RECON_INTEL,
    "LOGISTICS_ENG":     MOS.LOGISTICS_ENG,
    "COMBAT_SPECIALIST": MOS.COMBAT_SPECIALIST,
    "VEHICLE_CREW":      MOS.VEHICLE_CREW,
    "PARATROOPER_OFF":   MOS.PARATROOPER_OFF,
}


@dataclass
class MOSAssignment:
    """
    The result of a completed MOS assessment.
    Written to the draft card by frank_world after training.
    """
    player_id:          str
    card_id:            str
    mos:                MOS
    assigned_ts:        float
    confidence:         float       # 0..1 — how clearly the play style mapped
    observation_count:  int
    scores:             dict        # category → weighted sum

    @property
    def mos_code(self) -> str:
        return self.mos.value

    @property
    def title(self) -> str:
        return self.mos.title


def assess_mos(session: TrainingSession) -> MOSAssignment:
    """
    Assess MOS from a completed training session.
    Tallies weighted observations per category.
    Highest score wins. Ties broken by Paratrooper > Commander > rest.
    """
    if not session.complete:
        raise ValueError("Training session not complete — cannot assess MOS")

    scores: dict[str, float] = {cat: 0.0 for cat in _CATEGORY_TO_MOS}
    for obs in session.observations:
        if obs.category in scores:
            scores[obs.category] += obs.weight

    total = sum(scores.values()) or 1.0
    best_cat = max(scores, key=lambda c: scores[c])
    confidence = scores[best_cat] / total

    # Tie: prefer PARATROOPER_OFF (elite), then FIELD_COMMANDER
    best_score = scores[best_cat]
    tied = [c for c, s in scores.items() if abs(s - best_score) < 0.01]
    if len(tied) > 1:
        for pref in ("PARATROOPER_OFF", "FIELD_COMMANDER"):
            if pref in tied:
                best_cat = pref
                break

    return MOSAssignment(
        player_id         = session.player_id,
        card_id           = session.card_id,
        mos               = _CATEGORY_TO_MOS[best_cat],
        assigned_ts       = time.time(),
        confidence        = round(confidence, 4),
        observation_count = len(session.observations),
        scores            = {k: round(v, 4) for k, v in scores.items()},
    )
