#!/usr/bin/env python3
"""
test_phase4.py — Sacrifice Phase 4: vehicles, upgrades, equipment, supply, art
Phoenix DevOps OS | jwl247 | GPL v3

Driven through FrankWorld. Photo intake uses a recording fake intaker —
these tests never run hsf-intake.sh, never reach D1 or R2 (one test proves
it by patching subprocess and asserting it was not called).

    python game/tests/test_phase4.py
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from game.frank_world import FrankWorld
from game.rank import Rank
from game.jacket import JacketCategory
from game.hospital import WoundSeverity
from game.accord import AccordTerms
from game.equipment import Provenance, Quality, QUALITY_PROFILE
from game.vehicle import VehicleStatus, AssetStatus, UpgradeSpec, UpgradeSlot, UpgradeKind, VehicleClass
from game import asset_intake as ai


class WorldCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="phoenix_phase4_")
        t = Path(self._tmp)
        self._env = {
            "PHOENIX_ARCHIVE_ROOT":     str(t / "archive"),
            "PHOENIX_FRANK_KEY_FILE":   str(t / "frank_world.key"),
            "PHOENIX_ASSET_STAGING":    str(t / "staging"),
            "PHOENIX_VEHICLE_REGISTRY": str(t / "vehicle_registry.json"),
        }
        self._saved = {k: os.environ.get(k) for k in self._env}
        os.environ.update(self._env)
        self.w = FrankWorld()
        self.keys: dict[str, bytes] = {}

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self._tmp, ignore_errors=True)

    def soldier(self, callsign, mos="11B", rank=Rank.PRIVATE, theater="Ardennes",
                battles=0, commendations=0):
        key = (callsign.encode() * 8)[:32]
        card = self.w.enlist(callsign, key, theater)
        card.field()
        card.mos_code = mos
        cur = Rank.PRIVATE
        while cur < rank:                                  # the code allows 2 grades a step
            cur = Rank(min(cur + 2, rank))
            self.w.promote_player(card, cur, "test")
        j = self.w.jacket(card.card_id)
        for i in range(battles):
            j.record_battle(theater, f"Battle {i}", "held", {})
        for i in range(commendations):
            j.record_commendation(theater, "cmd", "Cmd", "steady")
        self.keys[card.player_id] = key
        return card


# ---------------------------------------------------------------------------
# Supply and fielding
# ---------------------------------------------------------------------------

class TestFielding(WorldCase):
    def test_spawn_costs_supply_and_rank(self):
        cmdr = self.soldier("Cmdr", "19K", Rank.SERGEANT)
        with self.assertRaises(ValueError):
            self.w.spawn_vehicle("mbt", cmdr.player_id)            # empty depot
        self.w.add_supply("Ardennes", 100, "world_seed")
        v = self.w.spawn_vehicle("mbt", cmdr.player_id)
        self.assertEqual(self.w.supply("Ardennes"), 60)
        self.assertEqual(v.condition, 1000)
        pvt = self.soldier("Pvt", "19K")
        with self.assertRaises(ValueError):
            self.w.spawn_vehicle("mbt", pvt.player_id)             # rank too low
        self.assertIn("took command", self.w.jacket(cmdr.card_id)
                      .by_category(JacketCategory.VEHICLE_RECORD)[-1].summary)

    def test_operating_is_mos_locked_riding_is_not(self):
        self.w.add_supply("Ardennes", 100, "seed")
        cmdr = self.soldier("Cmdr", "19K", Rank.SERGEANT)
        v = self.w.spawn_vehicle("ifv", cmdr.player_id)
        rifle = self.soldier("Rifle", "11B")
        with self.assertRaises(ValueError):
            self.w.board(v.vehicle_id, rifle.player_id, operate=True)
        self.w.board(v.vehicle_id, rifle.player_id)                # rides fine
        self.w.board(v.vehicle_id, cmdr.player_id, operate=True)
        with self.assertRaises(ValueError):
            self.w.board(v.vehicle_id, rifle.player_id)            # already aboard
        far = self.soldier("Far", "19K", theater="Pacific")
        with self.assertRaises(ValueError):
            self.w.board(v.vehicle_id, far.player_id, operate=True)

    def test_logistics_moves_supply_between_theaters(self):
        self.w.add_supply("Ardennes", 100, "seed")
        eng = self.soldier("Haul", "92A", Rank.PFC)
        truck = self.w.spawn_vehicle("supply_truck", eng.player_id)
        self.w.board(truck.vehicle_id, eng.player_id, operate=True)
        self.w.load_cargo(truck.vehicle_id, eng.player_id, 50)
        with self.assertRaises(ValueError):
            self.w.load_cargo(truck.vehicle_id, eng.player_id, 20)  # over capacity 60
        self.assertEqual(self.w.deliver_supply(truck.vehicle_id, eng.player_id, "Pacific"), 50)
        self.assertEqual(self.w.supply("Pacific"), 50)
        self.assertEqual(self.w.supply("Ardennes"), 40)
        self.assertEqual(eng.theater, "Pacific")


# ---------------------------------------------------------------------------
# Damage, loss, repair, capture
# ---------------------------------------------------------------------------

class TestLossAndCapture(WorldCase):
    def setUp(self):
        super().setUp()
        self.w.add_supply("Ardennes", 500, "seed")
        self.cmdr = self.soldier("Cmdr", "19K", Rank.SERGEANT, battles=6)
        self.eng  = self.soldier("Wrench", "92A")
        self.v    = self.w.spawn_vehicle("mbt", self.cmdr.player_id)

    def test_damage_states_and_repair_by_engineer_only(self):
        self.w.damage_vehicle(self.v.vehicle_id, 300, "AT round")
        self.assertEqual(self.v.status, VehicleStatus.DAMAGED)
        self.w.damage_vehicle(self.v.vehicle_id, 500, "mine")
        self.assertEqual(self.v.status, VehicleStatus.DISABLED)
        with self.assertRaises(ValueError):
            self.w.repair_vehicle(self.v.vehicle_id, self.cmdr.player_id, 10)
        self.w.repair_vehicle(self.v.vehicle_id, self.eng.player_id, 20)   # 20 × 6.0
        self.assertEqual(self.v.condition, 320)
        self.assertEqual(self.v.status, VehicleStatus.DAMAGED)

    def test_destroyed_is_permanent_and_takes_upgrades(self):
        self.w.install_upgrade(self.v.vehicle_id, "armor_1", self.eng.player_id, Provenance.EARNED)
        self.w.board(self.v.vehicle_id, self.cmdr.player_id, operate=True)
        self.w.damage_vehicle(self.v.vehicle_id, 5000, "air strike")
        self.assertEqual(self.v.status, VehicleStatus.DESTROYED)
        self.assertEqual(self.v.aboard, [])
        lost = self.w.world_history()[-1]
        self.assertEqual((lost["type"], lost["upgrades_lost"]), ("vehicle_lost", ["armor"]))
        for call in (lambda: self.w.repair_vehicle(self.v.vehicle_id, self.eng.player_id, 5),
                     lambda: self.w.board(self.v.vehicle_id, self.cmdr.player_id)):
            with self.assertRaises(ValueError):
                call()

    def test_capture_disabled_keeps_upgrades_and_is_history(self):
        self.w.install_upgrade(self.v.vehicle_id, "armor_1", self.eng.player_id, Provenance.EARNED)
        enemy = self.soldier("Enemy", "19K")
        with self.assertRaises(ValueError):
            self.w.capture_vehicle(self.v.vehicle_id, enemy.player_id)   # still healthy
        self.w.damage_vehicle(self.v.vehicle_id, 800, "flank")
        self.w.capture_vehicle(self.v.vehicle_id, enemy.player_id)
        self.assertEqual(self.v.owner_id, enemy.player_id)
        self.assertIn("armor", self.v.upgrades)
        self.assertEqual(self.w.world_history()[-1]["type"], "vehicle_captured")

    def test_disruptor_taking_kings_armor_is_named(self):
        self.w.crown("AO-1", self.cmdr.player_id)
        d = self.soldier("Disr", "19K")
        self.w.grant_disruptor("AO-1", d.player_id)
        self.w.damage_vehicle(self.v.vehicle_id, 800, "ambush")
        self.w.capture_vehicle(self.v.vehicle_id, d.player_id)
        self.assertEqual(self.w.world_history()[-1]["disruptor_took_kings_armor"], ["AO-1"])

    def test_death_abandons_vehicle_and_loses_kit(self):
        self.w.issue_item(self.cmdr.player_id, "rifle")
        self.w.board(self.v.vehicle_id, self.cmdr.player_id, operate=True)
        self.w.kill(self.cmdr, "sniper")
        self.assertIsNone(self.v.owner_id)
        self.assertEqual(self.v.operators, [])
        self.assertNotIn(self.cmdr.card_id, self.w._loadouts)
        scav = self.soldier("Scav", "19K")
        self.w.capture_vehicle(self.v.vehicle_id, scav.player_id)        # abandoned → capturable
        self.assertEqual(self.v.owner_id, scav.player_id)

    def test_wounded_leave_their_seat(self):
        sgt = self.soldier("Sgt", "19K", Rank.SERGEANT)
        self.w.board(self.v.vehicle_id, sgt.player_id, operate=True)
        self.w.wound(sgt, "shrapnel", WoundSeverity.WOUNDED)
        self.assertNotIn(sgt.player_id, self.v.operators)


# ---------------------------------------------------------------------------
# Upgrades — GDD §4.3
# ---------------------------------------------------------------------------

class TestUpgrades(WorldCase):
    def setUp(self):
        super().setUp()
        self.w.add_supply("Ardennes", 1000, "seed")
        self.eng = self.soldier("Wrench", "92A")

    def test_power_upgrades_earned_never_bought(self):
        rookie = self.soldier("Rookie", "19K", Rank.SERGEANT)
        v = self.w.spawn_vehicle("mbt", rookie.player_id)
        with self.assertRaises(ValueError):                       # can't buy power
            self.w.install_upgrade(v.vehicle_id, "armor_1", self.eng.player_id,
                                   Provenance.PAID, receipt_ref="rcpt_1")
        with self.assertRaises(ValueError):                       # hasn't earned it
            self.w.install_upgrade(v.vehicle_id, "armor_1", self.eng.player_id, Provenance.EARNED)
        for i in range(5):
            self.w.jacket(rookie.card_id).record_battle("Ardennes", f"b{i}", "held", {})
        self.w.install_upgrade(v.vehicle_id, "armor_1", self.eng.player_id, Provenance.EARNED)
        p, _ = self.w.registry.effective(v)
        self.assertEqual(p.armor, 100)

    def test_tiers_climb_in_order_one_per_slot(self):
        vet = self.soldier("Vet", "19K", Rank.SERGEANT_FIRST, battles=30, commendations=9)  # honour 0.77
        v = self.w.spawn_vehicle("mbt", vet.player_id)
        with self.assertRaises(ValueError):
            self.w.install_upgrade(v.vehicle_id, "armor_2", self.eng.player_id, Provenance.EARNED)
        for uid in ("armor_1", "armor_2", "armor_3"):
            self.w.install_upgrade(v.vehicle_id, uid, self.eng.player_id, Provenance.EARNED)
        p, _ = self.w.registry.effective(v)
        self.assertEqual((p.armor, p.speed), (90 + 20, 40 - 5))     # only tier 3 counts
        with self.assertRaises(ValueError):
            self.w.install_upgrade(v.vehicle_id, "armor_3", self.eng.player_id, Provenance.EARNED)

    def test_paid_quality_needs_receipt_changes_no_power_and_is_disclosed(self):
        a = self.soldier("Buyer", "19K", Rank.SERGEANT)
        b = self.soldier("Other", "11B")
        v = self.w.spawn_vehicle("mbt", a.player_id)
        before, _ = self.w.registry.effective(v)
        with self.assertRaises(ValueError):
            self.w.install_upgrade(v.vehicle_id, "optics_q1", self.eng.player_id, Provenance.PAID)
        self.w.install_upgrade(v.vehicle_id, "optics_q1", self.eng.player_id,
                               Provenance.PAID, receipt_ref="rcpt_42")
        after, q = self.w.registry.effective(v)
        self.assertEqual(before, after)                            # power untouched
        self.assertAlmostEqual(q.reliability, 0.88)
        entry = self.w.jacket(a.card_id).by_category(JacketCategory.VEHICLE_RECORD)[-1]
        self.assertEqual(entry.detail["provenance"], "paid")       # jacket shows which
        acc = self.w.propose(self.keys[a.player_id], b.player_id, AccordTerms(accord_name="Fair fight"))
        self.assertTrue(any("optics_q1" in k for k in acc.terms.pay_advantages_disclosed))
        self.w.countersign(acc.accord_id, self.keys[b.player_id])   # disclosure is in the signed hash

    def test_upgrade_must_fit_class_and_slot(self):
        c = self.soldier("C", "92A", Rank.SERGEANT, battles=5)
        truck = self.w.spawn_vehicle("supply_truck", c.player_id)
        with self.assertRaises(ValueError):
            self.w.install_upgrade(truck.vehicle_id, "weapons_1", self.eng.player_id, Provenance.EARNED)

    def test_registry_refuses_upgrade_that_mixes_power_and_quality(self):
        bad = UpgradeSpec("cheat", "Gold Plating", UpgradeSlot.ARMOR, UpgradeKind.QUALITY, 1,
                          frozenset({VehicleClass.ARMOR}), {"armor": 50}, 1)
        with self.assertRaises(ValueError):
            self.w.registry.add_upgrade(bad)


# ---------------------------------------------------------------------------
# Equipment — quality vs power
# ---------------------------------------------------------------------------

class TestEquipment(WorldCase):
    def test_standard_issued_to_all_better_is_earned_or_paid(self):
        s = self.soldier("Grunt")
        std = self.w.issue_item(s.player_id, "rifle")
        self.assertEqual(std.provenance, Provenance.ISSUED)
        with self.assertRaises(ValueError):
            self.w.issue_item(s.player_id, "rifle", Quality.IMPROVED, Provenance.EARNED)
        with self.assertRaises(ValueError):
            self.w.issue_item(s.player_id, "rifle", Quality.IMPROVED, Provenance.PAID)    # no receipt
        paid = self.w.issue_item(s.player_id, "pistol", Quality.SUPERIOR, Provenance.PAID, "rcpt_9")
        self.assertEqual(paid.max_condition, 160)
        self.assertIn("pistol", " ".join(self.w.paid_advantages(s.player_id)))

    def test_quality_never_changes_power(self):
        spec = self.w.items["rifle"]
        for q in Quality:
            self.assertIn(q, QUALITY_PROFILE)
        self.assertNotIn("damage", vars(QUALITY_PROFILE[Quality.SUPERIOR]))
        self.assertEqual(spec.power["damage"], 30)

    def test_mos_gate_and_carry_limit(self):
        s = self.soldier("Grunt", "11B")
        with self.assertRaises(ValueError):
            self.w.issue_item(s.player_id, "toolkit")                  # engineers only
        for item in ("plate", "lmg", "rifle", "plate"):       # 8 + 7.5 + 3.6 + 8 = 27.1 kg
            self.w.issue_item(s.player_id, item)
        self.assertAlmostEqual(self.w.loadout(s.player_id).weight(self.w.items), 27.1)
        with self.assertRaises(ValueError):                     # 35.1 kg > 35 kg limit
            self.w.issue_item(s.player_id, "plate")

    def test_wear_and_engineer_repair(self):
        self.w.add_supply("Ardennes", 10, "seed")
        s, e = self.soldier("Grunt"), self.soldier("Fix", "92A")
        item = self.w.issue_item(s.player_id, "rifle")
        self.w.wear_item(s.player_id, item.instance_id, 70)
        self.w.repair_gear(e.player_id, s.player_id, item.instance_id, 3)
        self.assertEqual(item.condition, 60)
        with self.assertRaises(ValueError):
            self.w.repair_gear(s.player_id, s.player_id, item.instance_id, 1)


# ---------------------------------------------------------------------------
# Art — upgradeable photos
# ---------------------------------------------------------------------------

class FakeIntaker:
    def __init__(self):
        self.calls = []

    def intake(self, path):
        path = Path(path)
        self.calls.append(path.name)
        return ai.IntakeReceipt(path.name, ai.intake_hex(path.name), ai.tav_address(path.name),
                                ai._digest(path, "sha3_512"), str(len(self.calls)))


class FakeCutter:
    def cut(self, src, dst):
        dst.write_bytes(b"CUTOUT" + Path(src).read_bytes())
        return dst


class NoCutter:
    def cut(self, src, dst):
        raise ai.CutoutUnavailable("rembg is not installed on this machine")


class TestArt(WorldCase):
    def photo(self, name, data):
        """A real image file; its colour comes from `data`, so different data = different photo."""
        from PIL import Image
        p = Path(self._tmp) / name
        fmt = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG"}.get(p.suffix.lower())
        if fmt is None:
            p.write_bytes(data)
            return p
        h = __import__("hashlib").sha256(data).digest()
        Image.new("RGB", (64, 48), (h[0], h[1], h[2])).save(p, fmt)
        return p

    def test_phone_photo_is_upright_and_carries_no_location(self):
        from PIL import Image
        src = Path(self._tmp) / "IMG_0001.jpg"
        im = Image.new("RGB", (400, 300), (10, 120, 40))
        exif = Image.Exif()
        exif[0x0112] = 6                                    # "rotate 90° to view" — what phones write
        exif[0x0110] = "Phone Model X"
        exif[0x8825] = {1: "N", 2: (49.0, 54.0, 0.0), 3: "E", 4: (6.0, 10.0, 0.0)}   # GPS
        im.save(src, "JPEG", exif=exif)
        self.assertIn(0x8825, Image.open(src).getexif())    # the original really has GPS
        staged, _ = ai.stage_photo(src, "mbt")
        with Image.open(staged) as out:
            self.assertEqual(out.size, (300, 400))           # turned upright
            self.assertEqual(len(out.getexif()), 0)          # no GPS, no model, nothing
            self.assertNotIn("exif", out.info)
        self.assertNotIn(b"Phone Model X", staged.read_bytes())

    def test_burst_folder_first_live_rest_alternates_rerun_skips(self):
        import time as _t
        burst = Path(self._tmp) / "burst"
        burst.mkdir()
        for i, name in enumerate(("IMG_1.jpg", "IMG_2.jpg", "IMG_3.jpg")):
            p = self.photo(f"burst/{name}", f"shot {i}".encode())
            os.utime(p, (1_700_000_000 + i, 1_700_000_000 + i))      # shot order
        (burst / "notes.txt").write_text("not a photo")
        reg = self.w.registry
        results, skipped = ai.add_vehicle_photos(reg, "apc", burst, FakeIntaker(), FakeCutter())
        self.assertEqual(len(results), 3)
        self.assertEqual(results[0].live.source, "cutout")
        statuses = [r.photo.status for r in results[1:]]
        self.assertEqual(statuses, [AssetStatus.PENDING_CUTOUT] * 2)
        self.assertEqual(self.w.vehicle_art("apc")["derived_from"], results[0].photo.version)
        again, skipped = ai.add_vehicle_photos(reg, "apc", burst, FakeIntaker(), FakeCutter())
        self.assertEqual((again, sorted(skipped)), ([], ["IMG_1.jpg", "IMG_2.jpg", "IMG_3.jpg"]))
        reg.model("apc").asset.promote(results[2].photo.version)       # JW picks the best shot
        self.assertEqual(self.w.vehicle_art("apc")["version"], results[2].photo.version)

    def test_heic_without_support_says_what_to_do(self):
        p = Path(self._tmp) / "IMG_0002.heic"
        p.write_bytes(b"\x00\x00\x00\x18ftypheic")
        with self.assertRaises(ValueError) as cm:
            ai.stage_photo(p, "mbt")
        self.assertIn("Most Compatible", str(cm.exception))

    def test_huge_photo_is_capped(self):
        from PIL import Image
        src = Path(self._tmp) / "big.jpg"
        Image.new("RGB", (6000, 4000), (1, 2, 3)).save(src, "JPEG")
        staged, _ = ai.stage_photo(src, "mbt")
        with Image.open(staged) as out:
            self.assertEqual(max(out.size), ai.MAX_EDGE)

    def test_placeholder_until_photo_then_upgrade_keeps_history(self):
        reg = self.w.registry
        self.assertFalse(self.w.vehicle_art("mbt")["has_photo"])
        it = FakeIntaker()
        r1 = ai.add_vehicle_photo(reg, "mbt", self.photo("t1.jpg", b"tank one"), it, FakeCutter())
        self.assertEqual(r1.live.source, "cutout")
        self.assertEqual(r1.cutout.derived_from, r1.photo.version)
        self.assertTrue(self.w.vehicle_art("mbt")["has_photo"])
        r2 = ai.add_vehicle_photo(reg, "mbt", self.photo("t2.jpg", b"tank two"), it, FakeCutter())
        statuses = [v.status for v in reg.model("mbt").asset.versions]
        self.assertEqual(statuses.count(AssetStatus.LIVE), 1)
        self.assertIn(AssetStatus.SUPERSEDED, statuses)
        self.assertEqual(self.w.vehicle_art("mbt")["version"], r2.cutout.version)
        self.assertEqual(len(it.calls), 4)                         # photo + cutout, twice

    def test_no_rembg_waits_pending_then_promote(self):
        reg = self.w.registry
        r = ai.add_vehicle_photo(reg, "ifv", self.photo("i.jpg", b"ifv"), FakeIntaker(), NoCutter())
        self.assertEqual(r.photo.status, AssetStatus.PENDING_CUTOUT)
        self.assertEqual(r.live.status, AssetStatus.PLACEHOLDER)
        reg.model("ifv").asset.promote(r.photo.version)
        self.assertTrue(self.w.vehicle_art("ifv")["has_photo"])

    def test_no_cutout_flag_and_duplicate_refused(self):
        reg = self.w.registry
        p = self.photo("h.png", b"helo")
        r = ai.add_vehicle_photo(reg, "attack_helo", p, FakeIntaker(), NoCutter(), no_cutout=True)
        self.assertEqual(r.live.source, "photo")
        with self.assertRaises(ValueError):
            ai.add_vehicle_photo(reg, "attack_helo", p, FakeIntaker(), NoCutter(), no_cutout=True)

    def test_staged_names_are_content_unique_and_tav_matches_intake(self):
        p1, s1 = ai.stage_photo(self.photo("same.jpg", b"a"), "mbt")
        p2, s2 = ai.stage_photo(self.photo("same2.jpg", b"b"), "mbt")
        self.assertNotEqual(p1.name, p2.name)
        self.assertTrue(p1.name.startswith(s1[:16]))
        self.assertEqual(ai.tav_address("frank_helix.py"),
                         ai.tav_address("frank_helix.py"))
        self.assertEqual(ai.intake_hex("ab"), "6162")
        with self.assertRaises(ValueError):
            ai.stage_photo(self.photo("x.exe", b"nope"), "mbt")

    def test_registry_art_survives_save_and_load(self):
        reg = self.w.registry
        ai.add_vehicle_photo(reg, "mbt", self.photo("s.jpg", b"save me"), FakeIntaker(), FakeCutter())
        path = Path(self._env["PHOENIX_VEHICLE_REGISTRY"])
        reg.save(path)
        fresh = ai._load_registry(path)
        self.assertEqual(fresh.model("mbt").asset.live().sha3_512, reg.model("mbt").asset.live().sha3_512)

    def test_real_intaker_checks_pool_hash_and_tests_never_run_it(self):
        pool = Path(self._tmp) / "pool"
        staged, _ = ai.stage_photo(self.photo("r.jpg", b"real"), "mbt")
        hx = ai.intake_hex(staged.name)
        (pool / "T1" / hx).mkdir(parents=True)
        side = pool / "T1" / hx / f"{hx}.sidecar.json"
        ok = type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
        with patch.dict(os.environ, {"CLONEPOOL_DIR": str(pool), "PHOENIX_BASH": "bash"}), \
             patch("game.asset_intake.subprocess.run", return_value=ok) as run:
            side.write_text(json.dumps({"sha256": ai._digest(staged, "sha256"), "version": "v1"}))
            rec = ai.HsfIntaker().intake(staged)
            self.assertEqual(rec.version, "v1")
            self.assertTrue(run.call_args[0][0][1].endswith("scripts/hsf-intake.sh"))
            side.write_text(json.dumps({"sha256": "0" * 64}))
            with self.assertRaises(RuntimeError):
                ai.HsfIntaker().intake(staged)


if __name__ == "__main__":
    unittest.main(verbosity=1)
