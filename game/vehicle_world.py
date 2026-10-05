#!/usr/bin/env python3
"""
vehicle_world.py — FrankWorld: vehicles, upgrades, equipment, supply
Sacrifice | Phoenix DevOps OS | jwl247 | GPL v3

The Phase 4 half of Frank's gate. FrankWorld inherits this mixin, so there is
still one gate to game state. Frank witnesses every vehicle fielded, lost,
captured, repaired and upgraded; every piece of gear issued, earned or bought.

GDD §4   — every vehicle player-operated; operating is MOS-locked, riding is not.
GDD §4.2 — vehicle loss is permanent: no respawn with full kit; upgrades go
           with it. A disabled or abandoned vehicle can be captured.
GDD §4.3 — pay buys quality, never power; the jacket shows earned vs paid,
           and every accord discloses paid gear (Transparency Covenant §7.4).
GDD Phase 4 — supply chain: fielding, repairing and upgrading draw on the
           theater's supply depot; logistics vehicles move supply between theaters.
"""

from __future__ import annotations

import logging
from typing import Optional

from .draft_card import CardStatus
from .jacket import JacketCategory
from .rank import Rank
from .equipment import (
    Provenance, Quality, ServiceRequirement, EARNED_QUALITY,
    ItemSpec, Item, Loadout, default_items, make_item, wear, repair_item,
)
from .vehicle import (
    VehicleRegistry, Vehicle, VehicleClass, VehicleStatus, InstalledUpgrade,
    UpgradeKind, OPERATOR_MOS, REPAIR_MOS, DISABLED_AT, AssetStatus,
    default_registry, new_vehicle_id,
)

log = logging.getLogger("vehicle_world")


class VehicleWorldMixin:
    """Mixed into FrankWorld. Uses its cards, jackets, rank records and history."""

    def _init_vehicle_world(
        self,
        registry: Optional[VehicleRegistry] = None,
        items:    Optional[dict[str, ItemSpec]] = None,
    ) -> None:
        self.registry = registry or default_registry()
        self.items    = items or default_items()
        self._vehicles: dict[str, Vehicle] = {}
        self._loadouts: dict[str, Loadout] = {}     # card_id → loadout
        self._supply:   dict[str, int]     = {}     # theater → supply units

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    def vehicle(self, vehicle_id: str) -> Optional[Vehicle]:
        return self._vehicles.get(vehicle_id)

    def vehicles_in(self, theater: str) -> list[Vehicle]:
        return [v for v in self._vehicles.values()
                if v.theater == theater and v.status != VehicleStatus.DESTROYED]

    def _veh(self, vehicle_id: str) -> Vehicle:
        v = self._vehicles.get(vehicle_id)
        if v is None:
            raise ValueError(f"Unknown vehicle: {vehicle_id}")
        if v.status == VehicleStatus.DESTROYED:
            raise ValueError(f"Vehicle {vehicle_id[:8]} was destroyed — loss is permanent")
        return v

    def _rank_of(self, card) -> Rank:
        return self._rank_records[card.card_id].rank

    def _service(self, card) -> tuple[Rank, int, int, float]:
        j = self._jackets[card.card_id]
        battles = sum(1 for e in j.by_category(JacketCategory.SERVICE_HISTORY) if "battle" in e.detail)
        return self._rank_of(card), battles, j.commendation_count, j.honour_score

    def _require_service(self, card, req: ServiceRequirement, what: str) -> None:
        short = req.shortfall(*self._service(card))
        if short:
            raise ValueError(f"{card.callsign} has not earned {what}: {', '.join(short)}")

    def _require_in_theater(self, card, v: Vehicle) -> None:
        if card.theater != v.theater:
            raise ValueError(f"{card.callsign} is in {card.theater}, the vehicle is in {v.theater}")

    def _vehicle_jacket(self, player_id: str, theater: str, vclass: str, fate: str) -> None:
        j = self._jacket_of_player(player_id)
        if j:
            j.record_vehicle(theater, vclass, fate)

    def _set_condition(self, v: Vehicle, condition: int) -> None:
        _, q = self.registry.effective(v)
        v.condition = max(0, min(q.max_condition, condition))
        if v.condition == 0:
            v.status = VehicleStatus.DESTROYED
        elif v.condition <= q.max_condition * DISABLED_AT:
            v.status = VehicleStatus.DISABLED
        elif v.condition < q.max_condition:
            v.status = VehicleStatus.DAMAGED
        else:
            v.status = VehicleStatus.READY

    def _aboard_any(self, player_id: str) -> Optional[Vehicle]:
        return next((v for v in self._vehicles.values()
                     if player_id in v.aboard and v.status != VehicleStatus.DESTROYED), None)

    # -----------------------------------------------------------------------
    # Supply chain
    # -----------------------------------------------------------------------

    def supply(self, theater: str) -> int:
        return self._supply.get(theater, 0)

    def add_supply(self, theater: str, amount: int, source: str) -> int:
        """World seeding, captured depots, production. Every unit has a source."""
        if amount <= 0:
            raise ValueError("Supply added must be positive")
        self._supply[theater] = self.supply(theater) + amount
        self._emit({"event": "supply_added", "theater": theater, "amount": amount,
                    "source": source, "depot": self._supply[theater]})
        return self._supply[theater]

    def _draw_supply(self, theater: str, amount: int, why: str) -> None:
        if self.supply(theater) < amount:
            raise ValueError(f"{theater} depot has {self.supply(theater)} supply; {why} needs {amount}")
        self._supply[theater] -= amount

    def load_cargo(self, vehicle_id: str, operator_id: str, amount: int) -> Vehicle:
        """A crewed logistics vehicle loads supply from its theater's depot."""
        v = self._veh(vehicle_id)
        m = self.registry.model(v.model_id)
        if m.vclass != VehicleClass.LOGISTICS:
            raise ValueError(f"{m.name} does not haul supply")
        if operator_id not in v.operators:
            raise ValueError("Only the vehicle's operator can load it")
        if v.status == VehicleStatus.DISABLED:
            raise ValueError("A disabled vehicle cannot be loaded")
        p, _ = self.registry.effective(v)
        if amount <= 0 or v.cargo + amount > p.capacity:
            raise ValueError(f"Cargo {v.cargo}+{amount} exceeds capacity {p.capacity}")
        self._draw_supply(v.theater, amount, "loading")
        v.cargo += amount
        return v

    def deliver_supply(self, vehicle_id: str, operator_id: str, to_theater: str) -> int:
        """Drive the load to another theater and unload it into that depot."""
        v = self._veh(vehicle_id)
        if operator_id not in v.operators:
            raise ValueError("Only the vehicle's operator can drive it")
        if v.status == VehicleStatus.DISABLED:
            raise ValueError("A disabled vehicle cannot move")
        if v.cargo <= 0:
            raise ValueError("Nothing aboard to deliver")
        delivered, from_theater = v.cargo, v.theater
        v.theater, v.cargo = to_theater, 0
        for pid in v.aboard:
            card = self.card_of(pid)
            if card:
                card.theater = to_theater
        self._supply[to_theater] = self.supply(to_theater) + delivered
        j = self._jacket_of_player(operator_id)
        if j:
            j.record(JacketCategory.SERVICE_HISTORY, to_theater,
                     f"Delivered {delivered} supply {from_theater} → {to_theater}",
                     {"vehicle_id": vehicle_id, "amount": delivered, "from": from_theater})
        self._emit({"event": "supply_delivered", "vehicle_id": vehicle_id, "from": from_theater,
                    "to": to_theater, "amount": delivered})
        return delivered

    # -----------------------------------------------------------------------
    # Vehicles — field, crew, damage, repair, capture, transfer
    # -----------------------------------------------------------------------

    def spawn_vehicle(self, model_id: str, commander_id: str) -> Vehicle:
        """Field a vehicle from the commander's theater depot. Costs supply."""
        m = self.registry.model(model_id)
        card = self._live_card(commander_id, "Commander")
        rank = self._rank_of(card)
        if rank < m.min_rank_to_command:
            raise ValueError(f"{m.name} needs a {m.min_rank_to_command.name} or above to command")
        self._draw_supply(card.theater, m.supply_cost, f"fielding a {m.name}")
        v = Vehicle(new_vehicle_id(), model_id, card.theater, card.player_id,
                    condition=m.quality.max_condition)
        self._vehicles[v.vehicle_id] = v
        self._vehicle_jacket(card.player_id, card.theater, m.vclass.value,
                             f"took command of {m.name} {v.vehicle_id[:8]}")
        self._emit({"event": "vehicle_fielded", **v.to_dict()})
        return v

    def board(self, vehicle_id: str, player_id: str, operate: bool = False) -> Vehicle:
        """Anyone may ride. Operating (drive/fly/gun) needs the class's MOS."""
        v = self._veh(vehicle_id)
        m = self.registry.model(v.model_id)
        card = self._live_card(player_id, "Crew")
        if card.status != CardStatus.ACTIVE:
            raise ValueError(f"{card.callsign} is {card.status.value} — not fit for duty")
        self._require_in_theater(card, v)
        if self._aboard_any(player_id):
            raise ValueError(f"{card.callsign} is already aboard a vehicle")
        if operate:
            if card.mos_code not in OPERATOR_MOS[m.vclass]:
                raise ValueError(f"Operating a {m.vclass.value} vehicle needs MOS "
                                 f"{sorted(OPERATOR_MOS[m.vclass])}; {card.callsign} is {card.mos_code}")
            if len(v.operators) >= m.crew_slots:
                raise ValueError(f"{m.name} operator seats are full ({m.crew_slots})")
            v.operators.append(player_id)
            self._vehicle_jacket(player_id, v.theater, m.vclass.value, f"operated {m.name}")
        else:
            p, _ = self.registry.effective(v)
            if m.vclass != VehicleClass.LOGISTICS and len(v.passengers) >= p.capacity:
                raise ValueError(f"{m.name} has no room for passengers")
            if m.vclass == VehicleClass.LOGISTICS and len(v.passengers) >= 2:
                raise ValueError(f"{m.name} carries supply, not troops")
            v.passengers.append(player_id)
        return v

    def disembark(self, vehicle_id: str, player_id: str) -> Vehicle:
        v = self._vehicles.get(vehicle_id)
        if v is None or player_id not in v.aboard:
            raise ValueError("Player is not aboard that vehicle")
        (v.operators if player_id in v.operators else v.passengers).remove(player_id)
        return v

    def damage_vehicle(self, vehicle_id: str, amount: int, cause: str) -> Vehicle:
        """Combat damage. At zero the vehicle — and every upgrade on it — is gone."""
        v = self._veh(vehicle_id)
        if amount <= 0:
            raise ValueError("Damage must be positive")
        m = self.registry.model(v.model_id)
        self._set_condition(v, v.condition - amount)
        if v.status == VehicleStatus.DESTROYED:
            fate = f"{m.name} destroyed — {cause}"
            for pid in {v.owner_id, *v.aboard} - {None}:
                self._vehicle_jacket(pid, v.theater, m.vclass.value, fate)
            v.operators.clear()
            v.passengers.clear()
            v.cargo = 0
            self._history_append({
                "type": "vehicle_lost", "vehicle_id": v.vehicle_id, "model": m.name,
                "vclass": m.vclass.value, "theater": v.theater, "owner_id": v.owner_id,
                "cause": cause, "upgrades_lost": sorted(v.upgrades),
            })
        else:
            self._emit({"event": "vehicle_damaged", "cause": cause, **v.to_dict()})
        return v

    def repair_vehicle(self, vehicle_id: str, engineer_id: str, supply: int) -> Vehicle:
        """An engineer spends theater supply to restore condition."""
        v = self._veh(vehicle_id)
        card = self._live_card(engineer_id, "Engineer")
        if card.mos_code not in REPAIR_MOS:
            raise ValueError(f"Repairs need MOS {sorted(REPAIR_MOS)}; {card.callsign} is {card.mos_code}")
        self._require_in_theater(card, v)
        if supply <= 0:
            raise ValueError("Repair needs supply")
        _, q = self.registry.effective(v)
        self._draw_supply(v.theater, supply, "repairs")
        self._set_condition(v, v.condition + int(supply * q.repair_rate))
        j = self._jacket_of_player(engineer_id)
        if j:
            j.record(JacketCategory.SERVICE_HISTORY, v.theater,
                     f"Repaired {self.registry.model(v.model_id).name}",
                     {"vehicle_id": vehicle_id, "supply": supply, "condition": v.condition})
        return v

    def capture_vehicle(self, vehicle_id: str, captor_id: str) -> Vehicle:
        """
        A disabled or abandoned vehicle with nobody aboard can be taken. It keeps
        its upgrades — "a free disruptor who captures a king's armor just became
        dangerous." The capture is world history.
        """
        v = self._veh(vehicle_id)
        card = self._live_card(captor_id, "Captor")
        self._require_in_theater(card, v)
        if v.owner_id == captor_id:
            raise ValueError("You cannot capture your own vehicle")
        if v.aboard:
            raise ValueError("Crew still aboard — the vehicle is not taken while it is held")
        if v.owner_id is not None and v.status != VehicleStatus.DISABLED:
            raise ValueError("Only a disabled or abandoned vehicle can be captured")
        m = self.registry.model(v.model_id)
        prev = v.owner_id
        v.owner_id = captor_id
        self._vehicle_jacket(captor_id, v.theater, m.vclass.value, f"captured {m.name}")
        if prev:
            self._vehicle_jacket(prev, v.theater, m.vclass.value, f"{m.name} captured by {card.callsign}")
        disruptor_of = [s.ao_id for s in self._kings.values()
                        if s.disruptor_id == captor_id and prev == s.king_id]
        self._history_append({
            "type": "vehicle_captured", "vehicle_id": v.vehicle_id, "model": m.name,
            "theater": v.theater, "from_owner": prev, "captor_id": captor_id,
            "captor_callsign": card.callsign, "upgrades": sorted(v.upgrades),
            "disruptor_took_kings_armor": disruptor_of,
        })
        return v

    def transfer_vehicle(self, vehicle_id: str, from_id: str, to_id: str) -> Vehicle:
        """A commander hands a vehicle to another who can command it."""
        v = self._veh(vehicle_id)
        if v.owner_id != from_id:
            raise ValueError("Only the commanding player can transfer the vehicle")
        to = self._live_card(to_id, "Receiver")
        m = self.registry.model(v.model_id)
        if self._rank_of(to) < m.min_rank_to_command:
            raise ValueError(f"{to.callsign} cannot command a {m.name}")
        self._require_in_theater(to, v)
        v.owner_id = to_id
        self._vehicle_jacket(from_id, v.theater, m.vclass.value, f"handed {m.name} to {to.callsign}")
        self._vehicle_jacket(to_id, v.theater, m.vclass.value, f"took command of {m.name}")
        return v

    # -----------------------------------------------------------------------
    # Vehicle upgrades (GDD §4.3)
    # -----------------------------------------------------------------------

    def install_upgrade(
        self,
        vehicle_id:  str,
        upgrade_id:  str,
        engineer_id: str,
        provenance:  Provenance,
        receipt_ref: Optional[str] = None,
    ) -> InstalledUpgrade:
        """
        An engineer installs an upgrade from theater supply.
        POWER: earned only — the commanding player's jacket must meet it.
        QUALITY: earned (same check) or PAID (receipt; disclosed in accords).
        Tiers climb in order; one upgrade per slot.
        """
        v = self._veh(vehicle_id)
        u = self.registry.upgrade(upgrade_id)
        m = self.registry.model(v.model_id)
        eng = self._live_card(engineer_id, "Engineer")
        if eng.mos_code not in REPAIR_MOS:
            raise ValueError(f"Installing upgrades needs MOS {sorted(REPAIR_MOS)}")
        self._require_in_theater(eng, v)
        if v.owner_id is None:
            raise ValueError("An abandoned vehicle has no commander to upgrade it for")
        if m.vclass not in u.classes:
            raise ValueError(f"{u.name} does not fit a {m.vclass.value} vehicle")
        if u.slot not in m.upgrade_slots:
            raise ValueError(f"{m.name} has no {u.slot.value} slot")
        current = v.upgrades.get(u.slot.value)
        have = current.tier if current else 0
        if u.tier != have + 1:
            raise ValueError(f"{u.slot.value} slot is at tier {have}; {u.name} is tier {u.tier}")
        if current and self.registry.upgrade(current.upgrade_id).kind != u.kind:
            raise ValueError(f"{u.slot.value} slot holds a {self.registry.upgrade(current.upgrade_id).kind.value} line")

        owner = self.card_of(v.owner_id)
        if provenance == Provenance.PAID:
            if u.kind == UpgradeKind.POWER:
                raise ValueError(f"{u.name} is a POWER upgrade — it is earned, never bought (GDD §4.3)")
            if not receipt_ref:
                raise ValueError("A paid upgrade needs a payment receipt reference")
        elif provenance == Provenance.EARNED:
            self._require_service(owner, u.requirement, u.name)
        else:
            raise ValueError("Upgrades are EARNED or PAID")

        self._draw_supply(v.theater, u.supply_cost, f"installing {u.name}")
        inst = InstalledUpgrade(u.upgrade_id, u.slot, u.tier, provenance, engineer_id,
                                paid_by=owner.player_id if provenance == Provenance.PAID else None,
                                receipt_ref=receipt_ref)
        v.upgrades[u.slot.value] = inst
        _, q = self.registry.effective(v)
        if v.condition > q.max_condition:
            v.condition = q.max_condition
        self._jackets[owner.card_id].record(
            JacketCategory.VEHICLE_RECORD, v.theater,
            f"{m.name}: {u.name} ({provenance.value})",
            {"vehicle_id": v.vehicle_id, "upgrade_id": u.upgrade_id, "kind": u.kind.value,
             "tier": u.tier, "provenance": provenance.value, "receipt_ref": receipt_ref},
        )
        self._emit({"event": "vehicle_upgraded", "vehicle_id": v.vehicle_id, **inst.to_dict()})
        return inst

    # -----------------------------------------------------------------------
    # Personal equipment (GDD §4.3)
    # -----------------------------------------------------------------------

    def loadout(self, player_id: str) -> Loadout:
        card = self.card_of(player_id)
        if card is None:
            raise ValueError(f"Player {player_id[:8]} has no draft card")
        lo = self._loadouts.get(card.card_id)
        if lo is None:
            lo = self._loadouts[card.card_id] = Loadout(card.card_id, card.mos_code)
        lo.mos_code = card.mos_code
        return lo

    def issue_item(
        self,
        player_id:   str,
        item_id:     str,
        quality:     Quality = Quality.STANDARD,
        provenance:  Provenance = Provenance.ISSUED,
        receipt_ref: Optional[str] = None,
    ) -> Item:
        """
        Standard kit is issued to anyone. Better quality is earned by the
        jacket or paid for with a receipt — never power, only quality.
        """
        spec = self.items.get(item_id)
        if spec is None:
            raise ValueError(f"Unknown item: {item_id}")
        card = self._live_card(player_id, "Soldier")
        if provenance == Provenance.EARNED:
            self._require_service(card, EARNED_QUALITY[quality], f"{quality.name} {spec.name}")
        item = make_item(spec, quality, provenance, receipt_ref)
        self.loadout(player_id).add(item, self.items, self._rank_of(card))
        if provenance != Provenance.ISSUED:
            self._jackets[card.card_id].record(
                JacketCategory.SERVICE_HISTORY, card.theater,
                f"{quality.name.title()} {spec.name} ({provenance.value})",
                {"item_id": item_id, "quality": quality.name, "provenance": provenance.value,
                 "receipt_ref": receipt_ref},
            )
        return item

    def wear_item(self, player_id: str, instance_id: str, amount: int) -> Item:
        return wear(self.loadout(player_id).get(instance_id), amount)

    def repair_gear(self, engineer_id: str, owner_id: str, instance_id: str, supply: int) -> Item:
        eng = self._live_card(engineer_id, "Engineer")
        if eng.mos_code not in REPAIR_MOS:
            raise ValueError(f"Gear repair needs MOS {sorted(REPAIR_MOS)}")
        item = self.loadout(owner_id).get(instance_id)
        self._draw_supply(eng.theater, supply, "gear repair")
        return repair_item(item, supply * 10)

    # -----------------------------------------------------------------------
    # Transparency (GDD §7.4) and death
    # -----------------------------------------------------------------------

    def paid_advantages(self, player_id: str) -> dict:
        """Everything this player bought that is in play. Empty dict = nothing."""
        out = {}
        card = self.card_of(player_id)
        if card and card.card_id in self._loadouts:
            for i in self._loadouts[card.card_id].paid():
                out[f"gear:{i.item_id}:{i.instance_id[:8]}"] = f"{i.quality.name} quality (paid)"
        for v in self._vehicles.values():
            if v.owner_id != player_id or v.status == VehicleStatus.DESTROYED:
                continue
            for inst in v.upgrades.values():
                if inst.provenance == Provenance.PAID:
                    out[f"vehicle:{v.vehicle_id[:8]}:{inst.upgrade_id}"] = "quality upgrade (paid)"
        return out

    def _vehicle_fallout(self, card) -> None:
        """
        The fallen leave their seats; their vehicles stand abandoned on the
        field (capturable); their personal kit goes with them — no respawn
        with full kit (GDD §4.2).
        """
        pid = card.player_id
        for v in self._vehicles.values():
            if pid in v.operators:
                v.operators.remove(pid)
            if pid in v.passengers:
                v.passengers.remove(pid)
            if v.owner_id == pid and v.status != VehicleStatus.DESTROYED:
                v.owner_id = None
                self._emit({"event": "vehicle_abandoned", **v.to_dict()})
        lo = self._loadouts.pop(card.card_id, None)
        if lo and lo.items:
            self._emit({"event": "kit_lost", "card_id": card.card_id,
                        "items": [i.to_dict() for i in lo.items]})

    def _leave_vehicles(self, card) -> None:
        """Hospitalised soldiers leave their seats; the vehicle stays with the unit."""
        for v in self._vehicles.values():
            if card.player_id in v.operators:
                v.operators.remove(card.player_id)
            if card.player_id in v.passengers:
                v.passengers.remove(card.player_id)

    # -----------------------------------------------------------------------
    # Art (upgradeable photos — see asset_intake.py)
    # -----------------------------------------------------------------------

    def vehicle_art(self, model_id: str) -> dict:
        """What the client should draw for a model: the live version, or placeholder."""
        m = self.registry.model(model_id)
        live = m.asset.live()
        return {"model_id": model_id, "name": m.name, **live.to_dict(),
                "has_photo": live.status == AssetStatus.LIVE}
