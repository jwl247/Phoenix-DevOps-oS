#!/usr/bin/env python3
"""
territory.py — Areas of Operation, control, and battles
Sacrifice | Phoenix DevOps OS | jwl247 | GPL v3

An AO is real ground: a polygon of [lon, lat] points the theater map draws
(MapTiler, via theater_map.py). It is NEUTRAL, HELD by a player, or
CONTESTED while a challenger fights for it. Control changes hands only by
battle or by an accord that staked the AO (territory_stake = ao_id).

A Battle is the unit the living world is built from: who fought, where, how
many fell, which officers died holding ground. Named ground, accord stakes
and every soldier's battle count (which earns upgrades) all come from here.
"""

from __future__ import annotations

import math
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AOControl(str, Enum):
    NEUTRAL   = "neutral"
    HELD      = "held"
    CONTESTED = "contested"


def _check_point(lon: float, lat: float) -> None:
    if not (-180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0):
        raise ValueError(f"Not a point on Earth: ({lon}, {lat})")


@dataclass
class AO:
    ao_id:    str
    theater:  str
    name:     str
    polygon:  list                    # [[lon, lat], ...] closed ring
    control:  AOControl = AOControl.NEUTRAL
    controller_id:       Optional[str] = None
    controller_callsign: Optional[str] = None
    held_since:          Optional[float] = None
    contested_by:        Optional[str] = None
    contest_battle_id:   Optional[str] = None

    def __post_init__(self):
        ring = [list(map(float, p)) for p in self.polygon]
        if len(ring) >= 3 and ring[0] != ring[-1]:
            ring.append(list(ring[0]))
        if len(ring) < 4:
            raise ValueError(f"AO {self.ao_id}: a polygon needs at least 3 distinct points")
        for lon, lat in ring:
            _check_point(lon, lat)
        self.polygon = ring

    def contains(self, lon: float, lat: float) -> bool:
        """Ray casting on the ring (fine at AO scale)."""
        inside, ring = False, self.polygon
        for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
            if (y1 > lat) != (y2 > lat):
                x = x1 + (lat - y1) * (x2 - x1) / (y2 - y1)
                if lon < x:
                    inside = not inside
        return inside

    def centroid(self) -> tuple[float, float]:
        pts = self.polygon[:-1]
        return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))

    def to_feature(self, extra: Optional[dict] = None) -> dict:
        return {
            "type": "Feature",
            "id": self.ao_id,
            "geometry": {"type": "Polygon", "coordinates": [self.polygon]},
            "properties": {
                "kind": "ao", "ao_id": self.ao_id, "theater": self.theater, "name": self.name,
                "control": self.control.value, "controller_id": self.controller_id,
                "controller_callsign": self.controller_callsign, "held_since": self.held_since,
                "contested_by": self.contested_by, **(extra or {}),
            },
        }

    def state(self) -> dict:
        return {k: v for k, v in self.to_feature()["properties"].items() if k != "kind"}


class BattleStatus(str, Enum):
    OPEN   = "open"
    CLOSED = "closed"


@dataclass
class Battle:
    battle_id:    str
    ao_id:        str
    theater:      str
    name:         str
    organizer_id: str                         # GDD §8.1 — the organizer is field commander
    participants: list = field(default_factory=list)
    casualties:   int = 0
    fallen:       list = field(default_factory=list)          # player_ids
    officers_fallen_holding: list = field(default_factory=list)
    status:       BattleStatus = BattleStatus.OPEN
    winner_id:    Optional[str] = None
    outcome:      Optional[str] = None
    opened_ts:    float = field(default_factory=time.time)
    closed_ts:    Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "battle_id": self.battle_id, "ao_id": self.ao_id, "theater": self.theater,
            "name": self.name, "organizer_id": self.organizer_id,
            "participants": list(self.participants), "casualties": self.casualties,
            "fallen": list(self.fallen), "officers_fallen_holding": list(self.officers_fallen_holding),
            "status": self.status.value, "winner_id": self.winner_id, "outcome": self.outcome,
            "opened_ts": self.opened_ts, "closed_ts": self.closed_ts,
        }


def new_battle(ao: AO, name: str, organizer_id: str) -> Battle:
    if not name or not name.strip():
        raise ValueError("A battle needs a name")
    return Battle(str(uuid.uuid4()), ao.ao_id, ao.theater, name.strip(), organizer_id,
                  participants=[organizer_id])


# ---------------------------------------------------------------------------
# Control
# ---------------------------------------------------------------------------

def take_neutral(ao: AO, player_id: str, callsign: str) -> AO:
    """Unheld ground is taken by whoever holds it first."""
    if ao.control != AOControl.NEUTRAL:
        raise ValueError(f"AO {ao.ao_id} is {ao.control.value} — it must be fought for")
    return _set_holder(ao, player_id, callsign)


def contest(ao: AO, challenger_id: str, battle_id: str) -> AO:
    if ao.control != AOControl.HELD:
        raise ValueError(f"AO {ao.ao_id} is {ao.control.value} — only held ground is contested")
    if challenger_id == ao.controller_id:
        raise ValueError("The holder cannot contest their own ground")
    ao.control, ao.contested_by, ao.contest_battle_id = AOControl.CONTESTED, challenger_id, battle_id
    return ao


def resolve(ao: AO, winner_id: Optional[str], winner_callsign: Optional[str]) -> AO:
    """End a contest. The challenger takes it only by winning; anything else, the holder keeps it."""
    if ao.control != AOControl.CONTESTED:
        raise ValueError(f"AO {ao.ao_id} is not contested")
    challenger = ao.contested_by
    ao.contested_by = ao.contest_battle_id = None
    if winner_id and winner_id == challenger:
        return _set_holder(ao, winner_id, winner_callsign)
    ao.control = AOControl.HELD if ao.controller_id else AOControl.NEUTRAL
    return ao


def transfer(ao: AO, player_id: str, callsign: str) -> AO:
    """An accord that staked this AO was won — the ground changes hands by law."""
    ao.contested_by = ao.contest_battle_id = None
    return _set_holder(ao, player_id, callsign)


def vacate(ao: AO) -> AO:
    """The holder fell and nobody was contesting: the ground goes neutral."""
    ao.control = AOControl.NEUTRAL
    ao.controller_id = ao.controller_callsign = ao.held_since = None
    return ao


def _set_holder(ao: AO, player_id: str, callsign: str) -> AO:
    ao.control, ao.controller_id, ao.controller_callsign = AOControl.HELD, player_id, callsign
    ao.held_since = time.time()
    return ao


def distance_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Great-circle distance in metres (haversine)."""
    r = 6_371_008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))
