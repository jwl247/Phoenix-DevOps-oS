#!/usr/bin/env python3
"""
rank.py — Rank System & Unit Issuance
Phoenix DevOps OS | jwl247 | GPL v3

Rank is earned through service and performance. It cannot be bought.
When a player reaches a rank that justifies command, Frank issues them men.
Those men are not NPCs — they are lower-ranked players assigned to that command.

GDD §3.4 — Rank Band → Command & Protection table.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional


# ---------------------------------------------------------------------------
# Rank enumeration (lowest → highest)
# ---------------------------------------------------------------------------

class Rank(IntEnum):
    PRIVATE           = 1
    PFC               = 2
    SPECIALIST        = 3
    CORPORAL          = 4
    SERGEANT          = 5
    STAFF_SERGEANT    = 6
    SERGEANT_FIRST    = 7
    MASTER_SERGEANT   = 8
    FIRST_SERGEANT    = 9
    SERGEANT_MAJOR    = 10
    LIEUTENANT        = 11
    FIRST_LIEUTENANT  = 12
    CAPTAIN           = 13
    MAJOR             = 14
    LIEUTENANT_COL    = 15
    COLONEL           = 16
    BRIGADIER         = 17
    MAJOR_GENERAL     = 18
    LIEUTENANT_GEN    = 19
    GENERAL           = 20
    SUPREME_COMMAND   = 21    # top 10 only — world-shaping authority


_RANK_DISPLAY = {
    Rank.PRIVATE:          "Private",
    Rank.PFC:              "Private First Class",
    Rank.SPECIALIST:       "Specialist",
    Rank.CORPORAL:         "Corporal",
    Rank.SERGEANT:         "Sergeant",
    Rank.STAFF_SERGEANT:   "Staff Sergeant",
    Rank.SERGEANT_FIRST:   "Sergeant First Class",
    Rank.MASTER_SERGEANT:  "Master Sergeant",
    Rank.FIRST_SERGEANT:   "First Sergeant",
    Rank.SERGEANT_MAJOR:   "Sergeant Major",
    Rank.LIEUTENANT:       "Second Lieutenant",
    Rank.FIRST_LIEUTENANT: "First Lieutenant",
    Rank.CAPTAIN:          "Captain",
    Rank.MAJOR:            "Major",
    Rank.LIEUTENANT_COL:   "Lieutenant Colonel",
    Rank.COLONEL:          "Colonel",
    Rank.BRIGADIER:        "Brigadier General",
    Rank.MAJOR_GENERAL:    "Major General",
    Rank.LIEUTENANT_GEN:   "Lieutenant General",
    Rank.GENERAL:          "General",
    Rank.SUPREME_COMMAND:  "Supreme Command",
}


def rank_display(r: Rank) -> str:
    return _RANK_DISPLAY.get(r, str(r))


# ---------------------------------------------------------------------------
# Rank Bands (GDD §3.4)
# ---------------------------------------------------------------------------

class RankBand(str):
    pass

BAND_ENLISTED_JUNIOR  = "PRIVATE_TO_CORPORAL"     # no command; full permadeath risk
BAND_NCO              = "SERGEANT_TO_LIEUTENANT"  # first squad; hospital activates
BAND_FIELD_OFFICER    = "CAPTAIN_TO_COLONEL"      # company + vehicles
BAND_GENERAL_OFFICER  = "BRIGADIER_TO_LTG"        # battalion; combined arms
BAND_GENERAL          = "GENERAL"                 # Frank issues men w/ service records
BAND_SUPREME          = "SUPREME_COMMAND"         # shape theater rules & world policy


def rank_band(r: Rank) -> str:
    if r <= Rank.CORPORAL:
        return BAND_ENLISTED_JUNIOR
    if r <= Rank.FIRST_LIEUTENANT:
        return BAND_NCO
    if r <= Rank.COLONEL:
        return BAND_FIELD_OFFICER
    if r <= Rank.LIEUTENANT_GEN:
        return BAND_GENERAL_OFFICER
    if r == Rank.GENERAL:
        return BAND_GENERAL
    return BAND_SUPREME


def hospital_active(r: Rank) -> bool:
    """Hospital protection activates at Sergeant and above (GDD §3.4)."""
    return r >= Rank.SERGEANT


def command_eligible(r: Rank) -> bool:
    """Frank will issue a unit at Sergeant and above."""
    return r >= Rank.SERGEANT


def vehicles_unlocked(r: Rank) -> bool:
    """Vehicle assignment unlocks at Captain (GDD §3.4)."""
    return r >= Rank.CAPTAIN


def combined_arms(r: Rank) -> bool:
    """Combined arms available at Brigadier (GDD §3.4)."""
    return r >= Rank.BRIGADIER


# ---------------------------------------------------------------------------
# Rank Record
# ---------------------------------------------------------------------------

@dataclass
class RankRecord:
    """
    A player's current rank and promotion history.
    Attached to the draft card by frank_world.
    """
    player_id:          str
    card_id:            str
    rank:               Rank             = Rank.PRIVATE
    band:               str              = BAND_ENLISTED_JUNIOR
    promotions:         list             = field(default_factory=list)  # list of PromotionEvent dicts
    last_promotion_ts:  Optional[float]  = None
    unit_size:          int              = 0    # soldiers currently under command

    @property
    def display(self) -> str:
        return rank_display(self.rank)

    @property
    def can_command(self) -> bool:
        return command_eligible(self.rank)

    @property
    def hospital_protected(self) -> bool:
        return hospital_active(self.rank)


@dataclass
class PromotionEvent:
    from_rank:      Rank
    to_rank:        Rank
    ts:             float
    reason:         str
    promoted_by:    str     # player_id of officer who promoted, or "FRANK" for auto


@dataclass
class IssuedUnit:
    """
    A unit Frank has issued to a commander.
    Each member is a real lower-ranked player with their own jacket and draft card.
    Not NPCs. Not guaranteed. Frank issues whoever is left if the commander
    has a bad reputation.
    """
    commander_player_id:    str
    commander_card_id:      str
    issued_ts:              float
    members:                list    = field(default_factory=list)  # list of UnitMember dicts
    unit_name:              str     = ""
    theater:                str     = ""

    @property
    def size(self) -> int:
        return len(self.members)


@dataclass
class UnitMember:
    player_id:  str
    card_id:    str
    callsign:   str
    rank:       Rank
    mos_code:   str
    joined_ts:  float


# ---------------------------------------------------------------------------
# Operations
# ---------------------------------------------------------------------------

def promote(
    record: RankRecord,
    to_rank: Rank,
    reason: str,
    promoted_by: str = "FRANK",
) -> RankRecord:
    """
    Promote a player to a new rank.
    Enforces: rank can only go up; you cannot skip more than 2 grades at once.
    Supreme Command is guarded — only 10 slots exist in the world.
    """
    if to_rank <= record.rank:
        raise ValueError(
            f"Cannot demote {rank_display(record.rank)} → {rank_display(to_rank)}"
        )
    delta = to_rank - record.rank
    if delta > 2 and to_rank != Rank.SUPREME_COMMAND:
        raise ValueError(
            f"Promotion jump of {delta} grades is illegal — "
            f"max 2 grades at a time (except Supreme Command)"
        )

    event = PromotionEvent(
        from_rank   = record.rank,
        to_rank     = to_rank,
        ts          = time.time(),
        reason      = reason,
        promoted_by = promoted_by,
    )
    record.promotions.append(vars(event) if not isinstance(event, dict) else event)
    record.promotions[-1]["from_rank"] = record.rank.value
    record.promotions[-1]["to_rank"]   = to_rank.value
    record.rank              = to_rank
    record.band              = rank_band(to_rank)
    record.last_promotion_ts = event.ts
    return record


def issue_unit(
    commander: RankRecord,
    candidate_pool: list[UnitMember],
    theater: str,
    unit_name: str = "",
) -> IssuedUnit:
    """
    Frank issues a unit to the commander.
    Size is determined by rank band (GDD §3.4).
    Candidates come from the lower-ranked player pool.
    Frank's quality depends on the commander's jacket reputation
    (reputation_penalty is applied by frank_world before passing pool).
    """
    if not commander.can_command:
        raise PermissionError(
            f"{rank_display(commander.rank)} is below Sergeant — "
            f"Frank does not issue units at this rank"
        )

    target = _unit_size_for_rank(commander.rank)
    members = candidate_pool[:target]   # frank_world pre-sorts by merit vs. leftover

    return IssuedUnit(
        commander_player_id = commander.player_id,
        commander_card_id   = commander.card_id,
        issued_ts           = time.time(),
        members             = [vars(m) if not isinstance(m, dict) else m for m in members],
        unit_name           = unit_name or f"Unit/{rank_display(commander.rank)[:3]}",
        theater             = theater,
    )


def _unit_size_for_rank(r: Rank) -> int:
    """Target unit size per rank band (GDD §3.4 command table)."""
    if r <= Rank.CORPORAL:
        return 0
    if r <= Rank.FIRST_LIEUTENANT:
        return 8            # squad
    if r <= Rank.COLONEL:
        return 100          # company
    if r <= Rank.LIEUTENANT_GEN:
        return 500          # battalion
    if r == Rank.GENERAL:
        return 2000         # full army; Frank issues real service records
    return 10_000           # Supreme Command — shape the world
