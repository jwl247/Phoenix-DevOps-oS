#!/usr/bin/env python3
"""
test_phase5.py — Sacrifice Phase 5: world history, territory, named ground, map
Phoenix DevOps OS | jwl247 | GPL v3

Everything runs in a temp dir. Map tiles come from a fake tile source; the
worker is exercised locally through node (real SQLite), fed a chain this
file builds with the Python WorldHistory — the cross-language check.

    python game/tests/test_phase5.py
"""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
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
from game.accord import AccordTerms, AccordOutcome
from game.equipment import Provenance
from game.territory import AOControl
from game.named_ground import GroundKind
from game.world_history import WorldHistory, ChainBroken, HistoryClient, GENESIS
from game import theater_map as tm

# A real piece of ground: a box in the Ardennes.
HILL = [[5.90, 49.80], [6.10, 49.80], [6.10, 50.00], [5.90, 50.00]]
RIDGE = [[6.10, 49.80], [6.30, 49.80], [6.30, 50.00], [6.10, 50.00]]
INSIDE = (6.00, 49.90)


class WorldCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="phoenix_phase5_")
        t = Path(self._tmp)
        self._env = {
            "PHOENIX_ARCHIVE_ROOT":   str(t / "archive"),
            "PHOENIX_FRANK_KEY_FILE": str(t / "frank_world.key"),
            "PHOENIX_WORLD_HISTORY":  str(t / "world_history.jsonl"),
            "MAPTILER_API_KEY":       "SENTINEL-KEY-must-never-leak",
        }
        self._saved = {k: os.environ.get(k) for k in self._env}
        os.environ.update(self._env)
        self.w = FrankWorld()
        self.keys = {}

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self._tmp, ignore_errors=True)

    def soldier(self, callsign, rank=Rank.PRIVATE, mos="11B", theater="Ardennes"):
        key = (callsign.encode() * 8)[:32]
        card = self.w.enlist(callsign, key, theater)
        card.field()
        card.mos_code = mos
        cur = Rank.PRIVATE
        while cur < rank:
            cur = Rank(min(cur + 2, rank))
            self.w.promote_player(card, cur, "test")
        self.keys[card.player_id] = key
        return card


# ---------------------------------------------------------------------------
# World history
# ---------------------------------------------------------------------------

class TestWorldHistory(WorldCase):
    def test_chain_persists_and_reverifies(self):
        path = Path(self._tmp) / "h.jsonl"
        h = WorldHistory(path)
        a = h.append({"type": "battle", "name": "first"})
        b = h.append({"type": "battle", "name": "second"})
        self.assertEqual((a["seq"], a["prev_hash"]), (1, GENESIS))
        self.assertEqual(b["prev_hash"], a["entry_hash"])
        again = WorldHistory(path)
        self.assertEqual(len(again), 2)
        self.assertEqual(again.head, b["entry_hash"])
        self.assertEqual(again.append({"type": "battle"})["seq"], 3)

    def test_tampering_is_caught_on_load(self):
        path = Path(self._tmp) / "h.jsonl"
        h = WorldHistory(path)
        for i in range(3):
            h.append({"type": "battle", "name": f"b{i}"})
        lines = path.read_text(encoding="utf-8").splitlines()
        rec = json.loads(lines[1])
        rec["c"] = rec["c"].replace("b1", "bX")
        path.write_text("\n".join([lines[0], json.dumps(rec), lines[2]]) + "\n", encoding="utf-8")
        with self.assertRaises(ChainBroken):
            WorldHistory(path)
        path.write_text("\n".join([lines[0], lines[2]]) + "\n", encoding="utf-8")   # an entry dropped
        with self.assertRaises(ChainBroken):
            WorldHistory(path)

    def test_world_survives_restart(self):
        self.w.define_ao("AO-1", "Ardennes", "Hill 400", HILL)
        n = len(self.w.world_history())
        reborn = FrankWorld()
        self.assertEqual(len(reborn.world_history()), n)
        self.assertEqual(reborn.world_history()[-1]["name"], "Hill 400")

    def test_query(self):
        self.w.define_ao("AO-1", "Ardennes", "Hill 400", HILL)
        self.w.define_ao("AO-9", "Pacific", "Atoll", [[150, -5], [151, -5], [151, -4]])
        self.assertEqual(len(self.w._history.query(type="territory", theater="Pacific")), 1)
        self.assertEqual(len(self.w._history.query(since_seq=1)), 1)

    def test_sync_pushes_only_unacked_and_keeps_cursor(self):
        path = Path(self._tmp) / "h.jsonl"
        h = WorldHistory(path)
        for i in range(5):
            h.append({"type": "battle", "i": i})

        class Client:
            def __init__(self):
                self.pushed = []

            def push(self, rows):
                self.pushed.append([r["seq"] for r in rows])
                return rows[-1]["seq"]

        c = Client()
        self.assertEqual(h.sync(c, batch=2), 5)
        self.assertEqual(c.pushed, [[1, 2], [3, 4], [5]])
        h.append({"type": "battle", "i": 5})
        c2 = Client()
        WorldHistory(path).sync(c2)
        self.assertEqual(c2.pushed, [[6]])

        class Short:
            def push(self, rows):
                return rows[0]["seq"] - 1

        h.append({"type": "battle"})
        with self.assertRaises(RuntimeError):
            h.sync(Short())

    def test_client_sends_auth_and_ua_and_needs_config(self):
        with patch.dict(os.environ, {"SACRIFICE_WORKER_URL": "", "SACRIFICE_FRANK_TOKEN": ""}):
            with self.assertRaises(RuntimeError):
                HistoryClient()
        seen = {}

        class Resp(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def fake_urlopen(req, timeout):
            seen["auth"] = req.get_header("Authorization")
            seen["ua"] = req.get_header("User-agent")
            seen["url"] = req.full_url
            return Resp(b'{"accepted_through": 7}')

        with patch("game.world_history.urllib.request.urlopen", fake_urlopen):
            n = HistoryClient("https://w.example/", "t" * 40).push([{"seq": 7}])
        self.assertEqual(n, 7)
        self.assertEqual(seen["auth"], "Bearer " + "t" * 40)
        self.assertEqual(seen["url"], "https://w.example/history")
        self.assertNotIn("Python-urllib", seen["ua"])


# ---------------------------------------------------------------------------
# Territory and battles
# ---------------------------------------------------------------------------

class TestTerritory(WorldCase):
    def setUp(self):
        super().setUp()
        self.ao = self.w.define_ao("AO-1", "Ardennes", "Hill 400", HILL)

    def test_polygon_rules(self):
        self.assertTrue(self.ao.contains(*INSIDE))
        self.assertFalse(self.ao.contains(6.2, 49.9))
        with self.assertRaises(ValueError):
            self.w.define_ao("AO-1", "Ardennes", "again", HILL)
        with self.assertRaises(ValueError):
            self.w.define_ao("AO-2", "Ardennes", "line", [[1, 1], [2, 2]])
        with self.assertRaises(ValueError):
            self.w.define_ao("AO-3", "Ardennes", "off-planet", [[0, 0], [200, 0], [0, 10]])

    def test_take_contest_and_hold(self):
        holder, chal = self.soldier("Holder"), self.soldier("Chal")
        self.w.take_ground("AO-1", holder.player_id)
        with self.assertRaises(ValueError):
            self.w.take_ground("AO-1", chal.player_id)          # must be fought for
        b = self.w.open_battle("AO-1", "Hill Fight", chal.player_id, contest=True)
        self.assertEqual(self.ao.control, AOControl.CONTESTED)
        self.w.join_battle(b.battle_id, holder.player_id)
        self.w.close_battle(b.battle_id, holder.player_id, "held")
        self.assertEqual((self.ao.control, self.ao.controller_id), (AOControl.HELD, holder.player_id))

    def test_challenger_wins_ground(self):
        holder, chal = self.soldier("Holder"), self.soldier("Chal")
        self.w.take_ground("AO-1", holder.player_id)
        b = self.w.open_battle("AO-1", "Hill Fight", chal.player_id, contest=True)
        self.w.close_battle(b.battle_id, chal.player_id, "taken")
        self.assertEqual(self.ao.controller_id, chal.player_id)
        events = [e.get("event") for e in self.w.world_history() if e["type"] == "territory"]
        self.assertEqual(events, ["ao_defined", "taken", "contested", "contest_settled"])

    def test_battle_counts_toward_earned_gear(self):
        """Phase 5 battles feed Phase 4: five real battles earn a power upgrade."""
        self.w.add_supply("Ardennes", 200, "seed")
        cmdr = self.soldier("Cmdr", Rank.SERGEANT, "19K")
        eng = self.soldier("Eng", mos="92A")
        v = self.w.spawn_vehicle("mbt", cmdr.player_id)
        for i in range(5):
            b = self.w.open_battle("AO-1", f"Patrol {i}", cmdr.player_id)
            self.w.close_battle(b.battle_id, cmdr.player_id)
        self.w.install_upgrade(v.vehicle_id, "armor_1", eng.player_id, Provenance.EARNED)
        self.assertEqual(len(self.w.jacket(cmdr.card_id).by_category(JacketCategory.SERVICE_HISTORY)) >= 5, True)

    def test_battle_rules(self):
        a, b_ = self.soldier("A"), self.soldier("B")
        far = self.soldier("Far", theater="Pacific")
        b = self.w.open_battle("AO-1", "Fight", a.player_id)
        with self.assertRaises(ValueError):
            self.w.open_battle("AO-1", "Second front", b_.player_id)   # one battle per AO at a time
        with self.assertRaises(ValueError):
            self.w.join_battle(b.battle_id, far.player_id)
        with self.assertRaises(ValueError):
            self.w.close_battle(b.battle_id, b_.player_id)             # winner must have fought
        self.w.close_battle(b.battle_id, a.player_id)
        with self.assertRaises(ValueError):
            self.w.close_battle(b.battle_id)

    def test_accord_stake_moves_ground_only_from_its_holder(self):
        holder, chal, other = self.soldier("Holder"), self.soldier("Chal"), self.soldier("Other")
        self.w.take_ground("AO-1", holder.player_id)
        acc = self.w.propose(self.keys[chal.player_id], holder.player_id,
                             AccordTerms(accord_name="For the Hill", territory_stake="AO-1"))
        self.w.countersign(acc.accord_id, self.keys[holder.player_id])
        self.w.conclude(acc.accord_id, AccordOutcome.CHALLENGER_VICTORY)
        self.assertEqual(self.ao.controller_id, chal.player_id)
        acc2 = self.w.propose(self.keys[other.player_id], holder.player_id,
                              AccordTerms(accord_name="Nothing to lose", territory_stake="AO-1"))
        self.w.countersign(acc2.accord_id, self.keys[holder.player_id])
        self.w.conclude(acc2.accord_id, AccordOutcome.CHALLENGER_VICTORY)
        self.assertEqual(self.ao.controller_id, chal.player_id)          # holder held nothing to lose

    def test_holder_falls(self):
        holder = self.soldier("Holder")
        self.w.take_ground("AO-1", holder.player_id)
        self.w.kill(holder, "sniper")
        self.assertEqual(self.ao.control, AOControl.NEUTRAL)


# ---------------------------------------------------------------------------
# Named ground
# ---------------------------------------------------------------------------

class TestNamedGround(WorldCase):
    def setUp(self):
        super().setUp()
        self.ao = self.w.define_ao("AO-1", "Ardennes", "Hill 400", HILL)

    def battle_with(self, *cards, close=True, winner=None):
        b = self.w.open_battle("AO-1", "Hill Fight", cards[0].player_id)
        for c in cards[1:]:
            self.w.join_battle(b.battle_id, c.player_id)
        if close:
            self.w.close_battle(b.battle_id, winner)
        return b

    def test_officer_dies_holding_names_ground_forever(self):
        lt, pvt = self.soldier("Steel", Rank.LIEUTENANT), self.soldier("Grunt")
        b = self.battle_with(lt, pvt, close=False)
        self.w.battle_casualty(b.battle_id, pvt.player_id, "mortar", holding=True, lon=6.0, lat=49.9)
        self.assertEqual(self.w.named_ground(), [])                       # privates don't name ground
        self.w.battle_casualty(b.battle_id, lt.player_id, "held the line", holding=True, lon=6.0, lat=49.9)
        g = self.w.named_ground()[0]
        self.assertEqual((g.kind, g.name), (GroundKind.OFFICER_FALLEN, "Second Lieutenant Steel"))
        self.assertEqual(lt.status.value, "KIA")
        self.assertEqual(self.w.world_history()[-1]["type"], "named_ground")

    def test_officer_must_be_inside_the_ao(self):
        lt = self.soldier("Steel", Rank.LIEUTENANT)
        b = self.battle_with(lt, close=False)
        with self.assertRaises(ValueError):
            self.w.battle_casualty(b.battle_id, lt.player_id, "x", holding=True, lon=7.0, lat=49.9)
        self.assertEqual(lt.status.value, "ACTIVE")                        # nothing happened

    def test_player_naming_rules(self):
        a, b_ = self.soldier("Namer"), self.soldier("Other")
        outsider = self.soldier("Outsider")
        b = self.battle_with(a, b_)
        with self.assertRaises(ValueError):
            self.w.name_ground(outsider.player_id, b.battle_id, "Nope Hill", *INSIDE)
        with self.assertRaises(ValueError):
            self.w.name_ground(a.player_id, b.battle_id, "!!", *INSIDE)
        with self.assertRaises(ValueError):
            self.w.name_ground(a.player_id, b.battle_id, "Far Away", 7.5, 49.9)
        g = self.w.name_ground(a.player_id, b.battle_id, "Namer's Rest", *INSIDE)
        self.assertEqual(g.kind, GroundKind.PLAYER_NAMED)
        with self.assertRaises(ValueError):                                # one name per battle
            self.w.name_ground(b_.player_id, b.battle_id, "Second Name", 5.95, 49.85)
        open_b = self.w.open_battle("AO-1", "Ongoing", a.player_id)
        with self.assertRaises(ValueError):                                # not during the battle
            self.w.name_ground(a.player_id, open_b.battle_id, "Too Soon", 5.95, 49.85)

    def test_only_a_bigger_battle_renames_player_ground(self):
        a, b_, c = self.soldier("A"), self.soldier("B"), self.soldier("C")
        small = self.battle_with(a, b_)
        first = self.w.name_ground(a.player_id, small.battle_id, "First Name", *INSIDE)
        same = self.battle_with(a, c)                                      # 0 casualties again
        with self.assertRaises(ValueError):
            self.w.name_ground(a.player_id, same.battle_id, "Second Name", 6.0005, 49.9005)
        x, y = self.soldier("X"), self.soldier("Y")
        big = self.battle_with(a, c, x, y, close=False)
        self.w.battle_casualty(big.battle_id, x.player_id, "mg")
        self.w.battle_casualty(big.battle_id, y.player_id, "mg")
        self.w.close_battle(big.battle_id, a.player_id)
        renamed = self.w.name_ground(c.player_id, big.battle_id, "Bloody Ground", 6.0005, 49.9005)
        self.assertEqual(first.superseded_by, renamed.ground_id)
        self.assertEqual([g.name for g in self.w.named_ground()], ["Bloody Ground"])
        self.assertEqual(self.w.world_history()[-1]["replaced"], [first.ground_id])

    def test_officer_ground_outranks_and_blocks_players(self):
        a, lt = self.soldier("A"), self.soldier("Steel", Rank.LIEUTENANT)
        b1 = self.battle_with(a, lt)
        mine = self.w.name_ground(a.player_id, b1.battle_id, "Player Hill", *INSIDE)
        b2 = self.battle_with(a, lt, close=False)
        self.w.battle_casualty(b2.battle_id, lt.player_id, "held", holding=True, lon=6.0003, lat=49.9)
        self.assertIsNotNone(mine.superseded_by)                           # officer replaces player
        self.w.close_battle(b2.battle_id)
        p, q = self.soldier("P"), self.soldier("Q")
        b3 = self.battle_with(a, p, q, close=False)
        for c in (p, q):
            self.w.battle_casualty(b3.battle_id, c.player_id, "x")
        self.w.close_battle(b3.battle_id)
        with self.assertRaises(ValueError):                                # never renamed, even by a bigger battle
            self.w.name_ground(a.player_id, b3.battle_id, "Overwrite", *INSIDE)


# ---------------------------------------------------------------------------
# Theater map
# ---------------------------------------------------------------------------

def solid_tile(_url: str) -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (256, 256), (90, 110, 80)).save(buf, "PNG")
    return buf.getvalue()


class TestTheaterMap(WorldCase):
    def setUp(self):
        super().setUp()
        self.w.define_ao("AO-1", "Ardennes", "Hill 400", HILL)
        self.w.define_ao("AO-2", "Ardennes", "Ridge", RIDGE)
        k = self.soldier("King")
        self.w.crown("AO-1", k.player_id)
        lt = self.soldier("Steel", Rank.LIEUTENANT)
        b = self.w.open_battle("AO-1", "Fight", lt.player_id)
        self.w.battle_casualty(b.battle_id, lt.player_id, "held", holding=True, lon=6.0, lat=49.9)

    def test_payload_is_key_free_geojson(self):
        p = self.w.map_payload("Ardennes", worker_url="https://sacrifice.example")
        blob = json.dumps(p)
        self.assertNotIn("SENTINEL-KEY", blob)
        self.assertEqual(p["tiles"], "https://sacrifice.example/tiles/{z}/{x}/{y}.png")
        kinds = sorted(f["properties"]["kind"] for f in p["geojson"]["features"])
        self.assertEqual(kinds, ["ao", "ao", "king", "named_ground"])
        self.assertIn("OpenStreetMap", p["attribution"])
        self.assertEqual(p["bbox"], [5.9, 49.8, 6.3, 50.0])

    def test_snapshot_renders_and_caches_tiles(self):
        calls = []

        def fetch(url):
            calls.append(url)
            return solid_tile(url)

        src = tm.TileSource(cache_dir=Path(self._tmp) / "tiles", fetch=fetch, key="k")
        out, sha3 = self.w.theater_snapshot("Ardennes", Path(self._tmp) / "snap.png", src, 640, 480)
        from PIL import Image
        with Image.open(out) as img:
            self.assertEqual(img.size, (640, 480))
        self.assertEqual(len(sha3), 128)
        first = len(calls)
        self.assertGreater(first, 0)
        self.w.theater_snapshot("Ardennes", Path(self._tmp) / "snap2.png", src, 640, 480)
        self.assertEqual(len(calls), first)                                 # all from the disk cache

    def test_mercator_and_zoom(self):
        x, y = tm.world_px(0, 0, 0)
        self.assertAlmostEqual(x, 128)
        self.assertAlmostEqual(y, 128)
        self.assertGreater(tm.fit_zoom((5.9, 49.8, 6.3, 50.0), 1024, 768), 6)

    def test_key_from_vault_file_when_env_is_empty(self):
        vault = Path(self._tmp) / "vault"
        vault.mkdir()
        (vault / "maptiler.env").write_text("# comment\nMAPTILER_API_KEY=from-vault\n", encoding="utf-8")
        with patch.dict(os.environ, {"MAPTILER_API_KEY": "", "PHOENIX_MAPTILER_KEY": "",
                                     "PHOENIX_VAULT_SECRETS": str(vault)}):
            self.assertEqual(tm.load_maptiler_key(), "from-vault")


# ---------------------------------------------------------------------------
# Python → worker (node, real SQLite)
# ---------------------------------------------------------------------------

class TestWorkerAcceptsPythonChain(WorldCase):
    def test_cross_language_chain(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node not installed")
        self.w.define_ao("AO-1", "Ardennes", "Hill 400", HILL)
        a, lt = self.soldier("Namer"), self.soldier("Steel", Rank.LIEUTENANT)
        b = self.w.open_battle("AO-1", "Fight", a.player_id)
        self.w.join_battle(b.battle_id, lt.player_id)
        self.w.close_battle(b.battle_id, a.player_id)
        self.w.name_ground(a.player_id, b.battle_id, "Namer's Rest", *INSIDE)
        b2 = self.w.open_battle("AO-1", "Last Stand", lt.player_id)
        self.w.battle_casualty(b2.battle_id, lt.player_id, "held", holding=True, lon=6.0002, lat=49.9)
        fixture = Path(self._tmp) / "fixture.json"
        fixture.write_text(json.dumps({
            "rows": self.w._history.rows(),
            "active_grounds": len(self.w.named_ground()),
            "aos": 1,
        }), encoding="utf-8")
        r = subprocess.run([node, str(REPO_ROOT / "game" / "worker" / "test" / "worker.test.mjs"), str(fixture)],
                           capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("0 failed", r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=1)
