#!/usr/bin/env python3
"""
equipment.py — Personal Equipment, Quality and Loadout
Sacrifice | Phoenix DevOps OS | jwl247 | GPL v3

GDD §4.3 — Pay & Equipment:
  "Pay only affects personal equipment quality. Not power. Not outcome.
   The same equipment is available to everyone — pay buys a better version
   of that equipment. A veteran who earned their gear through service is
   different from someone who bought their way to it — and Frank's jacket
   shows which one you are."

So, structurally:
  - An item's POWER (damage, protection, range) belongs to the item spec and
    is identical at every quality. Quality never touches it.
  - QUALITY (durability, weight, reliability) is what improves.
  - STANDARD quality is issued to everyone. Better quality is EARNED by
    service record or PAID (with a receipt) — and the provenance is kept.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Optional

from .rank import Rank


# ---------------------------------------------------------------------------
# Provenance and service requirements — shared with vehicle.py
# ---------------------------------------------------------------------------

class Provenance(str, Enum):
    ISSUED = "issued"     # standard kit, everyone gets it
    EARNED = "earned"     # service record met the requirement
    PAID   = "paid"       # bought — quality only, disclosed in every accord


@dataclass(frozen=True)
class ServiceRequirement:
    """What a jacket must show before Frank releases earned gear."""
    min_rank:          Rank  = Rank.PRIVATE
    min_battles:       int   = 0
    min_commendations: int   = 0
    min_honour:        float = 0.0

    def to_dict(self) -> dict:
        return {
            "min_rank": self.min_rank.name, "min_battles": self.min_battles,
            "min_commendations": self.min_commendations, "min_honour": self.min_honour,
        }

    def shortfall(self, rank: Rank, battles: int, commendations: int, honour: float) -> list[str]:
        """Empty list = met. Otherwise, each unmet line in plain words."""
        out = []
        if rank < self.min_rank:
            out.append(f"rank {rank.name} < {self.min_rank.name}")
        if battles < self.min_battles:
            out.append(f"battles {battles} < {self.min_battles}")
        if commendations < self.min_commendations:
            out.append(f"commendations {commendations} < {self.min_commendations}")
        if honour < self.min_honour:
            out.append(f"honour {honour:.2f} < {self.min_honour:.2f}")
        return out


# ---------------------------------------------------------------------------
# Quality
# ---------------------------------------------------------------------------

class Quality(IntEnum):
    STANDARD = 1
    IMPROVED = 2
    SUPERIOR = 3


@dataclass(frozen=True)
class QualityProfile:
    durability_mult: float   # max condition multiplier
    weight_mult:     float   # lighter is better
    reliability:     float   # chance a use does not jam / fail


QUALITY_PROFILE: dict[Quality, QualityProfile] = {
    Quality.STANDARD: QualityProfile(1.00, 1.00, 0.90),
    Quality.IMPROVED: QualityProfile(1.30, 0.90, 0.95),
    Quality.SUPERIOR: QualityProfile(1.60, 0.80, 0.98),
}

# What service earns each quality step (pay can buy the same step instead).
EARNED_QUALITY: dict[Quality, ServiceRequirement] = {
    Quality.IMPROVED: ServiceRequirement(min_battles=5,  min_honour=0.5),
    Quality.SUPERIOR: ServiceRequirement(min_battles=20, min_commendations=3, min_honour=0.7),
}


# ---------------------------------------------------------------------------
# Item registry
# ---------------------------------------------------------------------------

class ItemCategory(str, Enum):
    WEAPON  = "weapon"
    ARMOR   = "armor"
    OPTICS  = "optics"
    COMMS   = "comms"
    MEDICAL = "medical"
    TOOLS   = "tools"
    PACK    = "pack"


@dataclass(frozen=True)
class ItemSpec:
    item_id:         str
    name:            str
    category:        ItemCategory
    weight_kg:       float
    power:           dict                     # identical at every quality — GDD §4.3
    base_durability: int = 100
    mos_gate:        frozenset = frozenset()  # MOS codes; empty = anyone
    min_rank:        Rank = Rank.PRIVATE

    def to_dict(self) -> dict:
        return {
            "item_id": self.item_id, "name": self.name, "category": self.category.value,
            "weight_kg": self.weight_kg, "power": dict(self.power),
            "base_durability": self.base_durability, "mos_gate": sorted(self.mos_gate),
            "min_rank": self.min_rank.name,
        }


def default_items() -> dict[str, ItemSpec]:
    """The kit every soldier can be issued. Same list for everyone."""
    specs = [
        ItemSpec("rifle",       "Service Rifle",        ItemCategory.WEAPON,  3.6, {"damage": 30, "range_m": 450}),
        ItemSpec("pistol",      "Sidearm",              ItemCategory.WEAPON,  0.9, {"damage": 18, "range_m": 50}),
        ItemSpec("lmg",         "Light Machine Gun",    ItemCategory.WEAPON,  7.5, {"damage": 28, "range_m": 600},
                 mos_gate=frozenset({"11B", "11C"})),
        ItemSpec("plate",       "Plate Carrier",        ItemCategory.ARMOR,   8.0, {"protection": 40}),
        ItemSpec("helmet",      "Combat Helmet",        ItemCategory.ARMOR,   1.4, {"protection": 15}),
        ItemSpec("scope",       "Rifle Optic",          ItemCategory.OPTICS,  0.6, {"zoom": 4}),
        ItemSpec("binoculars",  "Binoculars",           ItemCategory.OPTICS,  0.9, {"zoom": 10},
                 mos_gate=frozenset({"35F", "11A", "11C"})),
        ItemSpec("radio",       "Squad Radio",          ItemCategory.COMMS,   1.2, {"range_km": 5}),
        ItemSpec("medkit",      "IFAK",                 ItemCategory.MEDICAL, 0.5, {"heal": 25}),
        ItemSpec("toolkit",     "Engineer Toolkit",     ItemCategory.TOOLS,   4.0, {"repair": 20},
                 mos_gate=frozenset({"92A"})),
        ItemSpec("ruck",        "Rucksack",             ItemCategory.PACK,    2.0, {"carry_kg": 15}),
    ]
    return {s.item_id: s for s in specs}


# ---------------------------------------------------------------------------
# Items and loadout
# ---------------------------------------------------------------------------

@dataclass
class Item:
    instance_id:  str
    item_id:      str
    quality:      Quality
    provenance:   Provenance
    max_condition: int
    condition:    int
    receipt_ref:  Optional[str] = None   # payment receipt for PAID quality
    issued_ts:    float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "instance_id": self.instance_id, "item_id": self.item_id,
            "quality": self.quality.name, "provenance": self.provenance.value,
            "condition": self.condition, "max_condition": self.max_condition,
            "receipt_ref": self.receipt_ref, "issued_ts": self.issued_ts,
        }


def make_item(
    spec:        ItemSpec,
    quality:     Quality,
    provenance:  Provenance,
    receipt_ref: Optional[str] = None,
) -> Item:
    if quality == Quality.STANDARD and provenance != Provenance.ISSUED:
        raise ValueError("STANDARD kit is issued to everyone — it is never earned or bought")
    if quality != Quality.STANDARD and provenance == Provenance.ISSUED:
        raise ValueError(f"{quality.name} quality is earned or paid, never simply issued")
    if provenance == Provenance.PAID and not receipt_ref:
        raise ValueError("PAID gear needs a payment receipt reference")
    max_c = int(spec.base_durability * QUALITY_PROFILE[quality].durability_mult)
    return Item(str(uuid.uuid4()), spec.item_id, quality, provenance, max_c, max_c, receipt_ref)


BASE_CARRY_KG = 35.0
MOS_CARRY_BONUS = {"92A": 10.0}   # logistics/engineers haul more


@dataclass
class Loadout:
    card_id:  str
    mos_code: Optional[str]
    items:    list[Item] = field(default_factory=list)

    def carry_limit(self, specs: dict[str, ItemSpec]) -> float:
        bonus = sum(specs[i.item_id].power.get("carry_kg", 0) for i in self.items)
        return BASE_CARRY_KG + MOS_CARRY_BONUS.get(self.mos_code or "", 0.0) + bonus

    def weight(self, specs: dict[str, ItemSpec]) -> float:
        return round(sum(specs[i.item_id].weight_kg * QUALITY_PROFILE[i.quality].weight_mult
                         for i in self.items), 3)

    def add(self, item: Item, specs: dict[str, ItemSpec], rank: Rank) -> Item:
        spec = specs[item.item_id]
        if spec.mos_gate and self.mos_code not in spec.mos_gate:
            raise ValueError(f"{spec.name} requires MOS {sorted(spec.mos_gate)}")
        if rank < spec.min_rank:
            raise ValueError(f"{spec.name} requires rank {spec.min_rank.name}")
        new_weight = self.weight(specs) + spec.weight_kg * QUALITY_PROFILE[item.quality].weight_mult
        limit = self.carry_limit(specs) + spec.power.get("carry_kg", 0)
        if new_weight > limit:
            raise ValueError(f"Over carry limit: {new_weight:.1f} kg > {limit:.1f} kg")
        self.items.append(item)
        return item

    def remove(self, instance_id: str) -> Item:
        item = self.get(instance_id)
        self.items.remove(item)
        return item

    def get(self, instance_id: str) -> Item:
        for i in self.items:
            if i.instance_id == instance_id:
                return i
        raise ValueError(f"No item {instance_id[:8]} in loadout")

    def paid(self) -> list[Item]:
        return [i for i in self.items if i.provenance == Provenance.PAID]

    def to_dict(self) -> dict:
        return {"card_id": self.card_id, "mos_code": self.mos_code,
                "items": [i.to_dict() for i in self.items]}


def wear(item: Item, amount: int) -> Item:
    """Use wears gear down. At 0 it is broken until repaired."""
    if amount < 0:
        raise ValueError("Wear cannot be negative")
    item.condition = max(0, item.condition - amount)
    return item


def repair_item(item: Item, amount: int) -> Item:
    if amount < 0:
        raise ValueError("Repair cannot be negative")
    item.condition = min(item.max_condition, item.condition + amount)
    return item
