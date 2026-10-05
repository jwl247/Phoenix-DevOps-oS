#!/usr/bin/env python3
"""
hospital.py — Hospital System & Wound Management
Phoenix DevOps OS | jwl247 | GPL v3

Wounds are not inconveniences. They are consequences.
Hospital time is REAL TIME — hours or days depending on severity.
Equipment stays with the unit. Subordinates hold the line or lose everything.

GDD §5 — Life, Death & The Hospital System.

The hospital system activates at Sergeant (GDD §3.4).
Private–Corporal have no hospital protection — wound → KIA is possible.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Wound Severity
# ---------------------------------------------------------------------------

class WoundSeverity(str, Enum):
    """
    GDD §5.1 — Status table.
    """
    ALIVE    = "ALIVE"     # Full access. Active duty. Full consequence.
    WOUNDED  = "WOUNDED"   # Hospital stay. Real-time recovery. Limited field action.
    CRITICAL = "CRITICAL"  # Extended hospital stay. Unit operates without you.
    KIA      = "KIA"       # Permadeath. Draft card archived. Story ends.


# Real-time recovery windows in seconds (per GDD: "hours or days")
_RECOVERY_SECONDS = {
    WoundSeverity.WOUNDED:  4 * 3600,      # 4 hours
    WoundSeverity.CRITICAL: 48 * 3600,     # 48 hours
}

# While wounded, field action is limited to these allowed action types
_LIMITED_ACTIONS_WOUNDED  = {"recon", "intel", "communicate", "plan"}
_LIMITED_ACTIONS_CRITICAL = set()           # nothing — unit operates without you


# ---------------------------------------------------------------------------
# Hospital Record
# ---------------------------------------------------------------------------

@dataclass
class HospitalRecord:
    """
    Tracks a single hospitalisation event.
    Created by admit(); closed by discharge() or by death.
    """
    player_id:          str
    card_id:            str
    severity:           WoundSeverity
    cause:              str                 # what caused the wound
    admit_ts:           float               = field(default_factory=time.time)
    discharge_ts:       Optional[float]     = None
    discharged:         bool                = False
    unit_held:          bool                = False     # did unit hold while player was out?
    equipment_lost:     list                = field(default_factory=list)

    @property
    def recovery_seconds(self) -> float:
        return _RECOVERY_SECONDS.get(self.severity, 0.0)

    @property
    def est_discharge_ts(self) -> float:
        return self.admit_ts + self.recovery_seconds

    @property
    def seconds_remaining(self) -> float:
        if self.discharged:
            return 0.0
        remaining = self.est_discharge_ts - time.time()
        return max(0.0, remaining)

    @property
    def ready_to_discharge(self) -> bool:
        return not self.discharged and time.time() >= self.est_discharge_ts

    @property
    def allowed_actions(self) -> set:
        if self.severity == WoundSeverity.WOUNDED:
            return _LIMITED_ACTIONS_WOUNDED
        return _LIMITED_ACTIONS_CRITICAL

    def can_act(self, action: str) -> bool:
        return action in self.allowed_actions


@dataclass
class WoundHistory:
    """
    Aggregated wound history for a player across their enlistment.
    Attached to the jacket by frank_world.
    """
    player_id:      str
    card_id:        str
    records:        list[HospitalRecord]    = field(default_factory=list)

    @property
    def total_wounds(self) -> int:
        return len(self.records)

    @property
    def critical_count(self) -> int:
        return sum(1 for r in self.records if r.severity == WoundSeverity.CRITICAL)

    @property
    def total_recovery_seconds(self) -> float:
        return sum(
            (r.discharge_ts or 0) - r.admit_ts
            for r in self.records
            if r.discharged and r.discharge_ts
        )

    @property
    def active_record(self) -> Optional[HospitalRecord]:
        for r in self.records:
            if not r.discharged:
                return r
        return None

    @property
    def hospitalised(self) -> bool:
        return self.active_record is not None


# ---------------------------------------------------------------------------
# Hospital Operations
# ---------------------------------------------------------------------------

def admit(
    player_id:      str,
    card_id:        str,
    severity:       WoundSeverity,
    cause:          str,
    history:        Optional[WoundHistory] = None,
) -> tuple[HospitalRecord, WoundHistory]:
    """
    Admit a player to hospital.
    Returns the new record AND an updated WoundHistory.
    Calling code must update the draft card status separately.
    """
    record = HospitalRecord(
        player_id = player_id,
        card_id   = card_id,
        severity  = severity,
        cause     = cause,
    )
    if history is None:
        history = WoundHistory(player_id=player_id, card_id=card_id)
    history.records.append(record)
    return record, history


def discharge(
    record:         HospitalRecord,
    unit_held:      bool = False,
    equipment_lost: list = None,
) -> HospitalRecord:
    """
    Discharge a player from hospital.
    Sets discharge_ts, closes the record.
    Can be called early (manual discharge by admin) or on timer expiry.
    """
    if record.discharged:
        raise ValueError(f"HospitalRecord for {record.card_id} already discharged")
    record.discharged    = True
    record.discharge_ts  = time.time()
    record.unit_held     = unit_held
    record.equipment_lost = equipment_lost or []
    return record


def check_discharge_eligibility(record: HospitalRecord) -> dict:
    """
    Non-mutating readiness check for the game loop to poll.
    Returns status dict the UI can display.
    """
    remaining = record.seconds_remaining
    return {
        "card_id":          record.card_id,
        "severity":         record.severity.value,
        "ready":            record.ready_to_discharge,
        "seconds_remaining":remaining,
        "hours_remaining":  round(remaining / 3600, 2),
        "est_discharge":    record.est_discharge_ts,
        "allowed_actions":  list(record.allowed_actions),
    }


def is_protected_by_hospital(rank_value: int) -> bool:
    """
    Hospital protection activates at Sergeant (rank.value >= 5).
    Private–Corporal (1–4): no hospital — wound can mean KIA.
    """
    return rank_value >= 5
