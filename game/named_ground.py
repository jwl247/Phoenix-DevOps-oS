#!/usr/bin/env python3
"""
named_ground.py — Ground that carries a name
Sacrifice | Phoenix DevOps OS | jwl247 | GPL v3

Two ways ground gets a name (JW, 2026-10-05: GDD on top, player naming under it):

1. OFFICER_FALLEN — GDD §11.1 / §8.2: "When an officer dies holding a field
   position, that ground takes their name. Permanently." Automatic. Never
   overwritten, never blocked; it outranks any player-given name there.

2. PLAYER_NAMED — build sheet: after a real battle, a player who fought in it
   may name ground inside that AO. Allowed only where no officer's name
   stands. A later, bigger battle (more casualties) at the same ground may
   rename a player-given name. One name per battle.

Nothing is deleted. A renamed entry is marked superseded and stays in the
registry and in world history.
"""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass, asdict
from enum import Enum
from typing import Optional

from .territory import distance_m

SAME_GROUND_M = 250.0            # two names this close are the same ground
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 '\-\.]{1,46}[A-Za-z0-9\.']$")


class GroundKind(str, Enum):
    OFFICER_FALLEN = "officer_fallen"
    PLAYER_NAMED   = "player_named"


@dataclass
class NamedGround:
    ground_id:  str
    ao_id:      str
    theater:    str
    name:       str
    lon:        float
    lat:        float
    kind:       GroundKind
    player_id:  str            # the fallen officer, or the player who named it
    callsign:   str
    battle_id:  str
    casualties: int            # the battle's toll when the name was given
    ts:         float
    superseded_by: Optional[str] = None

    @property
    def active(self) -> bool:
        return self.superseded_by is None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["kind"] = self.kind.value
        d["active"] = self.active
        return d

    def to_feature(self) -> dict:
        return {
            "type": "Feature", "id": self.ground_id,
            "geometry": {"type": "Point", "coordinates": [self.lon, self.lat]},
            "properties": {**{k: v for k, v in self.to_dict().items() if k not in ("lon", "lat", "kind")},
                           "kind": "named_ground", "ground_kind": self.kind.value},
        }


def clean_name(name: str) -> str:
    name = " ".join((name or "").split())
    if not NAME_RE.match(name):
        raise ValueError("A ground name is 3–48 letters, digits, spaces, ' - . "
                         "and starts and ends with a letter or digit")
    return name


class NamedGroundRegistry:
    def __init__(self):
        self.entries: list[NamedGround] = []

    def active(self, theater: Optional[str] = None, ao_id: Optional[str] = None) -> list[NamedGround]:
        return [g for g in self.entries if g.active
                and (theater is None or g.theater == theater) and (ao_id is None or g.ao_id == ao_id)]

    def near(self, lon: float, lat: float, kind: Optional[GroundKind] = None) -> list[NamedGround]:
        return [g for g in self.entries if g.active and (kind is None or g.kind == kind)
                and distance_m(lon, lat, g.lon, g.lat) <= SAME_GROUND_M]

    def name_fallen_officer(
        self, ao_id: str, theater: str, lon: float, lat: float,
        player_id: str, callsign: str, rank_title: str, battle_id: str, casualties: int,
    ) -> tuple[NamedGround, list[NamedGround]]:
        """The officer's ground. Supersedes any player-given name there. Returns (new, superseded)."""
        g = NamedGround(str(uuid.uuid4()), ao_id, theater, f"{rank_title} {callsign}",
                        lon, lat, GroundKind.OFFICER_FALLEN, player_id, callsign,
                        battle_id, casualties, time.time())
        replaced = self.near(lon, lat, GroundKind.PLAYER_NAMED)
        for old in replaced:
            old.superseded_by = g.ground_id
        self.entries.append(g)
        return g, replaced

    def name_by_player(
        self, ao_id: str, theater: str, lon: float, lat: float,
        player_id: str, callsign: str, name: str, battle_id: str, casualties: int,
    ) -> tuple[NamedGround, list[NamedGround]]:
        name = clean_name(name)
        if any(g.battle_id == battle_id and g.kind == GroundKind.PLAYER_NAMED for g in self.entries):
            raise ValueError("That battle has already named its ground")
        if self.near(lon, lat, GroundKind.OFFICER_FALLEN):
            officer = self.near(lon, lat, GroundKind.OFFICER_FALLEN)[0]
            raise ValueError(f"This ground carries {officer.name}'s name — it is never renamed")
        existing = self.near(lon, lat, GroundKind.PLAYER_NAMED)
        for old in existing:
            if casualties <= old.casualties:
                raise ValueError(f"'{old.name}' was named after a battle of {old.casualties} fallen; "
                                 f"only a larger battle renames it")
        g = NamedGround(str(uuid.uuid4()), ao_id, theater, name, lon, lat,
                        GroundKind.PLAYER_NAMED, player_id, callsign, battle_id, casualties, time.time())
        for old in existing:
            old.superseded_by = g.ground_id
        self.entries.append(g)
        return g, existing
