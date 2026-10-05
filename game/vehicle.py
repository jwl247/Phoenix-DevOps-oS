#!/usr/bin/env python3
"""
vehicle.py — Vehicle Registry, Upgrades and Art Slots
Sacrifice | Phoenix DevOps OS | jwl247 | GPL v3

GDD §4 — Vehicle System:
  Every vehicle is player-operated. Classes: Armor, Air, Naval, Artillery,
  Logistics. Vehicle loss is equipment loss — real, permanent, felt.

Upgrades follow GDD §4.3 (quality vs power, enforced by structure):
  - POWER upgrades (armor, firepower, speed, capacity) are EARNED only — the
    owner's jacket must meet the service requirement. They cannot be bought.
  - QUALITY upgrades (reliability, durability, repair rate) may be earned or
    paid; paid ones are disclosed in every accord.
  - One upgrade per slot; tiers climb in order (tier 2 needs tier 1).
  - Upgrades live on the vehicle. Lose the vehicle, lose the upgrades.

Art is upgradeable too: every model has an AssetSlot. It starts as a
placeholder; each real photo JW shoots is intaked and added as a new
version (raw photo → cutout → LIVE). Old versions are kept, never deleted.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Optional

from .rank import Rank
from .equipment import Provenance, ServiceRequirement


# ---------------------------------------------------------------------------
# Classes and MOS gates (GDD §4.1)
# ---------------------------------------------------------------------------

class VehicleClass(str, Enum):
    ARMOR     = "armor"       # tanks, APCs, IFVs — crew MOS required
    AIR       = "air"         # fixed wing, rotary, drones
    NAVAL     = "naval"       # own theater, own command structure
    ARTILLERY = "artillery"   # fire support — assigned to field commanders
    LOGISTICS = "logistics"   # supply vehicles — engineering and logistics MOS


# Who may OPERATE (drive, fly, gun). Anyone may ride.
OPERATOR_MOS: dict[VehicleClass, frozenset] = {
    VehicleClass.ARMOR:     frozenset({"19K"}),
    VehicleClass.AIR:       frozenset({"19K"}),
    VehicleClass.NAVAL:     frozenset({"19K"}),
    VehicleClass.ARTILLERY: frozenset({"19K", "11A"}),
    VehicleClass.LOGISTICS: frozenset({"92A", "19K"}),
}
REPAIR_MOS = frozenset({"92A"})    # engineers repair and install upgrades


class UpgradeSlot(str, Enum):
    ARMOR   = "armor"
    ENGINE  = "engine"
    WEAPONS = "weapons"
    OPTICS  = "optics"
    COMMS   = "comms"
    CARGO   = "cargo"


class UpgradeKind(str, Enum):
    POWER   = "power"     # earned only
    QUALITY = "quality"   # earned or paid


POWER_STATS   = ("firepower", "armor", "speed", "capacity")
QUALITY_STATS = ("reliability", "max_condition", "repair_rate")


# ---------------------------------------------------------------------------
# Art slot — upgradeable, versioned, never deleted
# ---------------------------------------------------------------------------

class AssetStatus(str, Enum):
    PLACEHOLDER    = "placeholder"      # no photo yet
    PENDING_CUTOUT = "pending_cutout"   # photo intaked, background not removed yet
    LIVE           = "live"             # what the client draws
    SUPERSEDED     = "superseded"       # an older live version — kept, not drawn


@dataclass
class AssetVersion:
    version:      int
    status:       AssetStatus
    source:       str                     # "placeholder" | "photo" | "cutout"
    tav:          Optional[str] = None    # USYS short address (base58)
    hex_id:       Optional[str] = None    # intake hex identity
    sha3_512:     Optional[str] = None
    filename:     Optional[str] = None
    derived_from: Optional[int] = None    # cutout → the photo version it came from
    ts:           float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "AssetVersion":
        return cls(**{**d, "status": AssetStatus(d["status"])})


@dataclass
class AssetSlot:
    versions: list[AssetVersion] = field(default_factory=lambda: [
        AssetVersion(version=1, status=AssetStatus.PLACEHOLDER, source="placeholder")])

    def live(self) -> AssetVersion:
        """The version the client draws: the newest LIVE, else the placeholder."""
        for v in reversed(self.versions):
            if v.status == AssetStatus.LIVE:
                return v
        return self.versions[0]

    def add(self, status: AssetStatus, source: str, **kw) -> AssetVersion:
        if status == AssetStatus.LIVE:
            self._supersede()
        v = AssetVersion(version=self.versions[-1].version + 1, status=status, source=source, **kw)
        self.versions.append(v)
        return v

    def promote(self, version: int) -> AssetVersion:
        """Make an intaked (pending) version the live art."""
        v = self.get(version)
        if v.status != AssetStatus.PENDING_CUTOUT:
            raise ValueError(f"Version {version} is {v.status.value}, not pending")
        self._supersede()
        v.status = AssetStatus.LIVE
        return v

    def get(self, version: int) -> AssetVersion:
        for v in self.versions:
            if v.version == version:
                return v
        raise ValueError(f"No asset version {version}")

    def _supersede(self) -> None:
        for v in self.versions:
            if v.status == AssetStatus.LIVE:
                v.status = AssetStatus.SUPERSEDED

    def to_dict(self) -> dict:
        return {"versions": [v.to_dict() for v in self.versions]}

    @classmethod
    def from_dict(cls, d: dict) -> "AssetSlot":
        return cls(versions=[AssetVersion.from_dict(v) for v in d["versions"]])


# ---------------------------------------------------------------------------
# Specs
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PowerStats:
    firepower: int
    armor:     int
    speed:     int
    capacity:  int     # passengers, or supply units for LOGISTICS


@dataclass(frozen=True)
class QualityStats:
    reliability:   float   # 0..1 — chance a sortie has no breakdown
    max_condition: int
    repair_rate:   float   # condition restored per supply unit


@dataclass
class VehicleModel:
    model_id:      str
    name:          str
    vclass:        VehicleClass
    crew_slots:    int          # operator seats (MOS-locked)
    power:         PowerStats
    quality:       QualityStats
    supply_cost:   int          # supply drawn from the theater depot to field it
    min_rank_to_command: Rank = Rank.SERGEANT
    upgrade_slots: tuple = ()
    asset:         AssetSlot = field(default_factory=AssetSlot)

    def to_dict(self) -> dict:
        return {
            "model_id": self.model_id, "name": self.name, "vclass": self.vclass.value,
            "crew_slots": self.crew_slots, "power": asdict(self.power),
            "quality": asdict(self.quality), "supply_cost": self.supply_cost,
            "min_rank_to_command": self.min_rank_to_command.name,
            "upgrade_slots": [s.value for s in self.upgrade_slots],
            "asset": self.asset.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "VehicleModel":
        return cls(
            d["model_id"], d["name"], VehicleClass(d["vclass"]), d["crew_slots"],
            PowerStats(**d["power"]), QualityStats(**d["quality"]), d["supply_cost"],
            Rank[d["min_rank_to_command"]], tuple(UpgradeSlot(s) for s in d["upgrade_slots"]),
            AssetSlot.from_dict(d["asset"]),
        )


@dataclass(frozen=True)
class UpgradeSpec:
    upgrade_id:  str
    name:        str
    slot:        UpgradeSlot
    kind:        UpgradeKind
    tier:        int
    classes:     frozenset             # VehicleClass values it fits
    delta:       dict                  # stat → change; POWER_STATS or QUALITY_STATS only
    supply_cost: int
    requirement: ServiceRequirement = ServiceRequirement()   # to EARN it

    def validate(self) -> None:
        allowed = POWER_STATS if self.kind == UpgradeKind.POWER else QUALITY_STATS
        bad = [k for k in self.delta if k not in allowed]
        if bad:
            raise ValueError(f"{self.upgrade_id}: {self.kind.value} upgrade may not change {bad} "
                             f"(GDD §4.3 — quality and power never mix)")
        if self.tier < 1:
            raise ValueError(f"{self.upgrade_id}: tier must be ≥ 1")

    def to_dict(self) -> dict:
        return {
            "upgrade_id": self.upgrade_id, "name": self.name, "slot": self.slot.value,
            "kind": self.kind.value, "tier": self.tier,
            "classes": sorted(c.value for c in self.classes), "delta": dict(self.delta),
            "supply_cost": self.supply_cost, "requirement": self.requirement.to_dict(),
        }


# ---------------------------------------------------------------------------
# Vehicle instance
# ---------------------------------------------------------------------------

class VehicleStatus(str, Enum):
    READY     = "ready"
    DAMAGED   = "damaged"     # below max condition, still operable
    DISABLED  = "disabled"    # ≤ 25 % — cannot move or fight; capturable
    DESTROYED = "destroyed"   # permanent loss


DISABLED_AT = 0.25


@dataclass
class InstalledUpgrade:
    upgrade_id:   str
    slot:         UpgradeSlot
    tier:         int
    provenance:   Provenance
    installed_by: str                 # engineer player_id
    paid_by:      Optional[str] = None
    receipt_ref:  Optional[str] = None
    ts:           float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["slot"], d["provenance"] = self.slot.value, self.provenance.value
        return d


@dataclass
class Vehicle:
    vehicle_id:  str
    model_id:    str
    theater:     str
    owner_id:    Optional[str]        # commanding player; None = abandoned (capturable)
    condition:   int
    status:      VehicleStatus = VehicleStatus.READY
    operators:   list[str] = field(default_factory=list)
    passengers:  list[str] = field(default_factory=list)
    upgrades:    dict[str, InstalledUpgrade] = field(default_factory=dict)   # slot → upgrade
    cargo:       int = 0              # supply units aboard (LOGISTICS)
    spawned_ts:  float = field(default_factory=time.time)

    @property
    def aboard(self) -> list[str]:
        return self.operators + self.passengers

    def to_dict(self) -> dict:
        return {
            "vehicle_id": self.vehicle_id, "model_id": self.model_id, "theater": self.theater,
            "owner_id": self.owner_id, "condition": self.condition, "status": self.status.value,
            "operators": list(self.operators), "passengers": list(self.passengers),
            "upgrades": {k: u.to_dict() for k, u in self.upgrades.items()},
            "cargo": self.cargo, "spawned_ts": self.spawned_ts,
        }


def new_vehicle_id() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class VehicleRegistry:
    """Models + upgrades. Art versions live on the models and persist with save()."""

    def __init__(self):
        self.models:   dict[str, VehicleModel] = {}
        self.upgrades: dict[str, UpgradeSpec]  = {}

    def add_model(self, m: VehicleModel) -> VehicleModel:
        if m.model_id in self.models:
            raise ValueError(f"Model {m.model_id} already registered")
        if m.crew_slots < 1:
            raise ValueError(f"{m.model_id}: needs at least one operator seat")
        self.models[m.model_id] = m
        return m

    def add_upgrade(self, u: UpgradeSpec) -> UpgradeSpec:
        u.validate()
        if u.upgrade_id in self.upgrades:
            raise ValueError(f"Upgrade {u.upgrade_id} already registered")
        self.upgrades[u.upgrade_id] = u
        return u

    def model(self, model_id: str) -> VehicleModel:
        m = self.models.get(model_id)
        if m is None:
            raise ValueError(f"Unknown vehicle model: {model_id}")
        return m

    def upgrade(self, upgrade_id: str) -> UpgradeSpec:
        u = self.upgrades.get(upgrade_id)
        if u is None:
            raise ValueError(f"Unknown upgrade: {upgrade_id}")
        return u

    def effective(self, v: Vehicle) -> tuple[PowerStats, QualityStats]:
        """Model stats plus every installed upgrade."""
        m = self.model(v.model_id)
        p, q = asdict(m.power), asdict(m.quality)
        for inst in v.upgrades.values():
            for stat, d in self.upgrade(inst.upgrade_id).delta.items():
                (p if stat in POWER_STATS else q)[stat] += d
        q["reliability"] = min(0.999, q["reliability"])
        return PowerStats(**p), QualityStats(**q)

    # -- persistence (art versions must survive restarts) --------------------

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps({
            "models": [m.to_dict() for m in self.models.values()],
        }, indent=2), encoding="utf-8")
        tmp.replace(path)

    def load_assets(self, path: Path) -> None:
        """Restore art versions saved earlier onto the models registered here."""
        path = Path(path)
        if not path.exists():
            return
        data = json.loads(path.read_text(encoding="utf-8"))
        for md in data.get("models", []):
            if md["model_id"] in self.models:
                self.models[md["model_id"]].asset = AssetSlot.from_dict(md["asset"])
            else:
                self.models[md["model_id"]] = VehicleModel.from_dict(md)


def default_registry() -> VehicleRegistry:
    """
    The starting motor pool — one or more models per GDD class. Names are
    generic on purpose; JW's photos give each its real face (AssetSlot).
    """
    r = VehicleRegistry()
    S = UpgradeSlot
    for m in [
        VehicleModel("mbt",        "Main Battle Tank",          VehicleClass.ARMOR, 3,
                     PowerStats(90, 90, 40, 0),  QualityStats(0.85, 1000, 6.0), 40, Rank.SERGEANT,
                     (S.ARMOR, S.ENGINE, S.WEAPONS, S.OPTICS, S.COMMS)),
        VehicleModel("ifv",        "Infantry Fighting Vehicle", VehicleClass.ARMOR, 2,
                     PowerStats(55, 60, 60, 6),  QualityStats(0.88, 700, 7.0), 25, Rank.SERGEANT,
                     (S.ARMOR, S.ENGINE, S.WEAPONS, S.OPTICS, S.COMMS)),
        VehicleModel("apc",        "Armored Personnel Carrier", VehicleClass.ARMOR, 1,
                     PowerStats(20, 45, 65, 10), QualityStats(0.90, 600, 8.0), 15, Rank.CORPORAL,
                     (S.ARMOR, S.ENGINE, S.COMMS)),
        VehicleModel("attack_helo", "Attack Helicopter",        VehicleClass.AIR,   2,
                     PowerStats(80, 25, 85, 0),  QualityStats(0.80, 500, 4.0), 45, Rank.STAFF_SERGEANT,
                     (S.ARMOR, S.ENGINE, S.WEAPONS, S.OPTICS, S.COMMS)),
        VehicleModel("lift_helo",  "Transport Helicopter",      VehicleClass.AIR,   2,
                     PowerStats(10, 20, 80, 12), QualityStats(0.82, 450, 4.0), 30, Rank.SERGEANT,
                     (S.ARMOR, S.ENGINE, S.COMMS, S.CARGO)),
        VehicleModel("recon_drone", "Recon Drone",              VehicleClass.AIR,   1,
                     PowerStats(0, 5, 70, 0),    QualityStats(0.90, 120, 10.0), 8, Rank.SPECIALIST,
                     (S.ENGINE, S.OPTICS, S.COMMS)),
        VehicleModel("patrol_boat", "Patrol Boat",              VehicleClass.NAVAL, 2,
                     PowerStats(40, 30, 70, 6),  QualityStats(0.86, 550, 5.0), 25, Rank.SERGEANT,
                     (S.ARMOR, S.ENGINE, S.WEAPONS, S.COMMS)),
        VehicleModel("howitzer",   "Self-Propelled Howitzer",   VehicleClass.ARTILLERY, 3,
                     PowerStats(100, 50, 30, 0), QualityStats(0.84, 800, 5.0), 40, Rank.STAFF_SERGEANT,
                     (S.ARMOR, S.ENGINE, S.WEAPONS, S.OPTICS, S.COMMS)),
        VehicleModel("supply_truck", "Supply Truck",            VehicleClass.LOGISTICS, 1,
                     PowerStats(0, 15, 55, 60),  QualityStats(0.92, 400, 10.0), 10, Rank.PFC,
                     (S.ARMOR, S.ENGINE, S.CARGO)),
        VehicleModel("recovery",   "Armored Recovery Vehicle",  VehicleClass.LOGISTICS, 2,
                     PowerStats(5, 60, 40, 20),  QualityStats(0.90, 800, 12.0), 20, Rank.SERGEANT,
                     (S.ARMOR, S.ENGINE, S.CARGO)),
    ]:
        r.add_model(m)

    ALL = frozenset(VehicleClass)
    GROUND_AIR_SEA = frozenset({VehicleClass.ARMOR, VehicleClass.AIR, VehicleClass.NAVAL,
                                VehicleClass.ARTILLERY})
    vet  = ServiceRequirement(min_rank=Rank.SERGEANT, min_battles=5,  min_honour=0.5)
    q1   = ServiceRequirement(min_battles=3,  min_honour=0.4)
    q2   = ServiceRequirement(min_battles=10, min_honour=0.55)
    hard = ServiceRequirement(min_rank=Rank.STAFF_SERGEANT, min_battles=15, min_commendations=2, min_honour=0.6)
    elite = ServiceRequirement(min_rank=Rank.SERGEANT_FIRST, min_battles=30, min_commendations=5, min_honour=0.75)
    for u in [
        # POWER — earned by service only
        UpgradeSpec("armor_1",   "Applique Armor",       S.ARMOR,   UpgradeKind.POWER, 1, ALL, {"armor": 10}, 15, vet),
        UpgradeSpec("armor_2",   "Reactive Armor",       S.ARMOR,   UpgradeKind.POWER, 2, ALL, {"armor": 15}, 25, hard),
        UpgradeSpec("armor_3",   "Composite Armor Pack", S.ARMOR,   UpgradeKind.POWER, 3, ALL, {"armor": 20, "speed": -5}, 40, elite),
        UpgradeSpec("engine_1",  "Tuned Powerpack",      S.ENGINE,  UpgradeKind.POWER, 1, ALL, {"speed": 8}, 12, vet),
        UpgradeSpec("engine_2",  "Uprated Powerpack",    S.ENGINE,  UpgradeKind.POWER, 2, ALL, {"speed": 12}, 22, hard),
        UpgradeSpec("weapons_1", "Improved Fire Control", S.WEAPONS, UpgradeKind.POWER, 1, GROUND_AIR_SEA, {"firepower": 8}, 15, vet),
        UpgradeSpec("weapons_2", "Upgunned Mount",       S.WEAPONS, UpgradeKind.POWER, 2, GROUND_AIR_SEA, {"firepower": 14}, 30, hard),
        UpgradeSpec("weapons_3", "Veteran Gun System",   S.WEAPONS, UpgradeKind.POWER, 3, GROUND_AIR_SEA, {"firepower": 20}, 45, elite),
        UpgradeSpec("cargo_1",   "Extended Bed",         S.CARGO,   UpgradeKind.POWER, 1,
                    frozenset({VehicleClass.LOGISTICS, VehicleClass.AIR}), {"capacity": 20}, 10, vet),
        # QUALITY — earned (by the requirement) or paid (receipt); never changes power
        UpgradeSpec("optics_q1", "Clear Optics",         S.OPTICS,  UpgradeKind.QUALITY, 1, ALL, {"reliability": 0.03}, 8, q1),
        UpgradeSpec("optics_q2", "Sealed Optics",        S.OPTICS,  UpgradeKind.QUALITY, 2, ALL, {"reliability": 0.04}, 12, q2),
        UpgradeSpec("comms_q1",  "Hardened Comms",       S.COMMS,   UpgradeKind.QUALITY, 1, ALL, {"reliability": 0.03}, 6, q1),
        UpgradeSpec("comms_q2",  "Encrypted Mesh Comms", S.COMMS,   UpgradeKind.QUALITY, 2, ALL, {"reliability": 0.03, "repair_rate": 1.0}, 10, q2),
    ]:
        r.add_upgrade(u)
    return r
