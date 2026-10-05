#!/usr/bin/env python3
"""
test_phase3.py — Sacrifice Phase 3 through the Frank gate
Phoenix DevOps OS | jwl247 | GPL v3

Accords, tribunal, King of Theater and footage, driven only through
FrankWorld — the way the game server will drive them. Every test runs in
its own temp dir (archive + Frank key); nothing touches real state.

    python game/tests/test_phase3.py
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from game.frank_world import FrankWorld, _load_frank_key
from game.draft_card import CardStatus
from game.jacket import JacketCategory
from game.accord import (
    AccordTerms, AccordType, AccordStatus, AccordOutcome, FRANK_AUTHORITY, verify_party,
)
from game.tribunal import TribunalVerdict, TribunalSentence, TribunalStatus
from game.footage import FootageType


class WorldCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="phoenix_phase3_")
        self._env = {
            "PHOENIX_ARCHIVE_ROOT":   str(Path(self._tmp) / "archive"),
            "PHOENIX_FRANK_KEY_FILE": str(Path(self._tmp) / "frank_world.key"),
        }
        self._saved = {k: os.environ.get(k) for k in [*self._env, "PHOENIX_FRANK_KEY"]}
        os.environ.update(self._env)
        os.environ.pop("PHOENIX_FRANK_KEY", None)
        self.w = FrankWorld()
        self.keys: dict[str, bytes] = {}

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self._tmp, ignore_errors=True)

    def soldier(self, callsign: str, theater: str = "Ardennes"):
        key = (callsign.encode() * 8)[:32]
        card = self.w.enlist(callsign, key, theater)
        card.field()
        self.keys[card.player_id] = key
        return card

    def history_types(self):
        return [(e["type"], e.get("event")) for e in self.w.world_history()]


# ---------------------------------------------------------------------------
# Accords
# ---------------------------------------------------------------------------

class TestAccords(WorldCase):
    def test_full_accord_lands_in_both_jackets_and_history(self):
        a, b = self.soldier("Reaper"), self.soldier("Ghost")
        terms = AccordTerms(accord_name="The Bridge at Dawn", theater="Ardennes",
                            honor_stake=True, pay_advantages_disclosed={"none": "declared"})
        acc = self.w.propose(self.keys[a.player_id], b.player_id, terms)
        self.assertEqual(acc.status, AccordStatus.PROPOSED)
        self.w.countersign(acc.accord_id, self.keys[b.player_id])
        self.assertTrue(verify_party(acc, self.keys[a.player_id], "challenger"))
        self.assertTrue(verify_party(acc, self.keys[b.player_id], "defender"))
        self.assertEqual(len(acc.frank_witness_hash), 128)          # SHA3-512
        self.w.activate(acc.accord_id)
        self.w.conclude(acc.accord_id, AccordOutcome.CHALLENGER_VICTORY, "held the bridge")

        ja = self.w.jacket(a.card_id).by_category(JacketCategory.ACCORD_HISTORY)
        jb = self.w.jacket(b.card_id).by_category(JacketCategory.ACCORD_HISTORY)
        self.assertEqual(ja[-1].detail["outcome"], "won")
        self.assertEqual(jb[-1].detail["outcome"], "lost")
        hist = self.w.world_history()
        self.assertEqual(hist[-1]["name"], "The Bridge at Dawn")
        self.assertEqual(hist[-1]["pay_advantages"], {"none": "declared"})

    def test_wrong_key_cannot_sign(self):
        a, b, c = self.soldier("A1"), self.soldier("B1"), self.soldier("C1")
        acc = self.w.propose(self.keys[a.player_id], b.player_id, AccordTerms(accord_name="x"))
        with self.assertRaises(ValueError):
            self.w.countersign(acc.accord_id, self.keys[c.player_id])

    def test_terms_tampered_after_proposal_refused(self):
        a, b = self.soldier("A2"), self.soldier("B2")
        acc = self.w.propose(self.keys[a.player_id], b.player_id, AccordTerms(accord_name="clean"))
        acc.terms.equipment_stake = "hidden tank"
        with self.assertRaises(ValueError):
            self.w.countersign(acc.accord_id, self.keys[b.player_id])

    def test_rules_challenger_must_name_cannot_self_challenge_cannot_forge_king(self):
        a, b = self.soldier("A3"), self.soldier("B3")
        with self.assertRaises(ValueError):
            self.w.propose(self.keys[a.player_id], b.player_id, AccordTerms(accord_name="  "))
        with self.assertRaises(ValueError):
            self.w.propose(self.keys[a.player_id], a.player_id, AccordTerms(accord_name="me"))
        with self.assertRaises(ValueError):
            self.w.propose(self.keys[a.player_id], b.player_id,
                           AccordTerms(accord_name="k", accord_type=AccordType.KING_THEATER))

    def test_trainee_and_dead_have_no_standing(self):
        a = self.soldier("A4")
        rookie = self.w.enlist("Rookie", b"r" * 32, "Ardennes")       # still TRAINING
        with self.assertRaises(ValueError):
            self.w.propose(self.keys[a.player_id], rookie.player_id, AccordTerms(accord_name="x"))
        b = self.soldier("B4")
        self.w.kill(b, "artillery")
        with self.assertRaises(ValueError):
            self.w.propose(self.keys[a.player_id], b.player_id, AccordTerms(accord_name="x"))

    def test_observers_and_void(self):
        a, b, o = self.soldier("A5"), self.soldier("B5"), self.soldier("Obs")
        acc = self.w.propose(self.keys[a.player_id], b.player_id, AccordTerms(accord_name="watched"))
        self.w.void(acc.accord_id, "changed mind")
        self.assertEqual(acc.status, AccordStatus.VOIDED)
        acc2 = self.w.propose(self.keys[a.player_id], b.player_id, AccordTerms(accord_name="watched 2"))
        self.w.countersign(acc2.accord_id, self.keys[b.player_id])
        self.w.observe(acc2.accord_id, o.player_id)
        self.w.conclude(acc2.accord_id, AccordOutcome.DRAW)
        self.assertEqual(self.w.world_history()[-1]["observer_count"], 1)
        with self.assertRaises(ValueError):
            self.w.void(acc2.accord_id, "too late")

    def test_sweep_expired(self):
        a, b = self.soldier("A6"), self.soldier("B6")
        signed = self.w.propose(self.keys[a.player_id], b.player_id, AccordTerms(accord_name="slow"))
        self.w.countersign(signed.accord_id, self.keys[b.player_id])
        unsigned = self.w.propose(self.keys[a.player_id], b.player_id, AccordTerms(accord_name="never"))
        signed.expires_ts = time.time() - 1
        unsigned.expires_ts = time.time() - 1
        done = self.w.sweep_expired()
        self.assertEqual(len(done), 2)
        self.assertEqual(signed.outcome, AccordOutcome.DRAW)
        self.assertEqual(unsigned.status, AccordStatus.VOIDED)

    def test_death_forfeits_live_accords(self):
        a, b = self.soldier("A7"), self.soldier("B7")
        acc = self.w.propose(self.keys[a.player_id], b.player_id, AccordTerms(accord_name="last stand"))
        self.w.countersign(acc.accord_id, self.keys[b.player_id])
        self.w.kill(b, "sniper")
        self.assertEqual(acc.outcome, AccordOutcome.FORFEIT_DEFENDER)
        ja = self.w.jacket(a.card_id).by_category(JacketCategory.ACCORD_HISTORY)
        self.assertEqual(ja[-1].detail["outcome"], "won by forfeit")


# ---------------------------------------------------------------------------
# Tribunal
# ---------------------------------------------------------------------------

class TestTribunal(WorldCase):
    def court(self, theater="Ardennes", jurors=5):
        accused = self.soldier("Accused", theater)
        filer   = self.soldier("Filer", theater)
        wits    = [self.soldier(f"Wit{i}", theater) for i in range(3)]
        jury    = [self.soldier(f"Jur{i}", theater) for i in range(jurors)]
        charge  = self.w.file_charges(accused.player_id, ["Abandoning formation"],
                                      filer.player_id, [w.player_id for w in wits])
        return accused, filer, wits, jury, charge

    def convict(self, sentence, guilty=5):
        accused, filer, wits, jury, charge = self.court()
        rec = self.w.open_tribunal(charge.charge_id, [j.player_id for j in jury])
        self.w.testify(rec.tribunal_id, wits[0].player_id, "He ran.")
        for i, j in enumerate(jury):
            self.w.vote(rec.tribunal_id, j.player_id,
                        TribunalVerdict.GUILTY if i < guilty else TribunalVerdict.NOT_GUILTY)
        self.w.render_verdict(rec.tribunal_id, sentence, "per the code")
        return accused, rec

    def test_three_real_witnesses_required(self):
        accused, filer = self.soldier("Acc"), self.soldier("Fil")
        w1, w2 = self.soldier("W1"), self.soldier("W2")
        with self.assertRaises(ValueError):
            self.w.file_charges(accused.player_id, ["x"], filer.player_id,
                                [w1.player_id, w2.player_id, filer.player_id])
        with self.assertRaises(ValueError):
            self.w.file_charges(accused.player_id, ["x"], filer.player_id,
                                [w1.player_id, w2.player_id, "nobody-real"])

    def test_jury_only_from_accused_theater_else_dismissed(self):
        accused, filer, wits, jury, charge = self.court(jurors=3)
        outsiders = [self.soldier(f"Far{i}", "Pacific") for i in range(5)]
        rec = self.w.open_tribunal(charge.charge_id,
                                   [j.player_id for j in jury] + [o.player_id for o in outsiders])
        self.assertEqual(rec.verdict, TribunalVerdict.DISMISSED)
        trib = self.w.jacket(accused.card_id).by_category(JacketCategory.TRIBUNAL)
        self.assertEqual(trib[-1].detail["verdict"], "dismissed")
        self.assertEqual(self.w.world_history()[-1]["verdict"], "dismissed")

    def test_execution_is_permadeath_regardless_of_rank(self):
        accused, rec = self.convict(TribunalSentence.EXECUTION)
        self.assertEqual(rec.status, TribunalStatus.EXECUTED)
        self.assertEqual(accused.status, CardStatus.KIA)
        j = self.w.jacket(accused.card_id)
        self.assertTrue(j.by_category(JacketCategory.TRIBUNAL))
        self.assertIn("KIA", j.entries[-1].summary)
        self.assertEqual(len(rec.frank_witness_hash), 128)

    def test_tribunal_duel_is_compelled_frank_accord(self):
        accused, rec = self.convict(TribunalSentence.TRIBUNAL_DUEL)
        duel = self.w.accord(rec.duel_accord_id)
        self.assertIsNotNone(duel)
        self.assertEqual(duel.challenger_id, FRANK_AUTHORITY)
        self.assertTrue(duel.defender_compelled)
        self.assertTrue(verify_party(duel, self.w._frank_key, "defender"))
        self.w.conclude(duel.accord_id, AccordOutcome.DEFENDER_VICTORY, "survived")
        self.assertEqual(self.w.jacket(accused.card_id)
                         .by_category(JacketCategory.ACCORD_HISTORY)[-1].detail["outcome"], "won")

    def test_dishonour_is_permanent_court_martial(self):
        accused, rec = self.convict(TribunalSentence.DISHONOUR)
        j = self.w.jacket(accused.card_id)
        self.assertEqual(len(j.by_category(JacketCategory.COURT_MARTIAL)), 1)
        self.assertLess(j.honour_score, 0.5)
        self.assertEqual(accused.status, CardStatus.ACTIVE)

    def test_not_guilty_acquits(self):
        accused, rec = self.convict(TribunalSentence.EXECUTION, guilty=2)
        self.assertEqual(rec.verdict, TribunalVerdict.NOT_GUILTY)
        self.assertEqual(rec.sentence, TribunalSentence.ACQUITTAL)
        self.assertEqual(accused.status, CardStatus.ACTIVE)

    def test_no_sentence_on_the_dead_and_one_tribunal_per_charge(self):
        accused, filer, wits, jury, charge = self.court()
        rec = self.w.open_tribunal(charge.charge_id, [j.player_id for j in jury])
        with self.assertRaises(ValueError):
            self.w.open_tribunal(charge.charge_id, [j.player_id for j in jury])
        for j in jury:
            self.w.vote(rec.tribunal_id, j.player_id, TribunalVerdict.GUILTY)
        self.w.kill(accused, "fell in battle")
        with self.assertRaises(ValueError):
            self.w.render_verdict(rec.tribunal_id, TribunalSentence.EXECUTION)

    def test_testimony_footage_must_exist(self):
        accused, filer, wits, jury, charge = self.court()
        rec = self.w.open_tribunal(charge.charge_id, [j.player_id for j in jury])
        with self.assertRaises(ValueError):
            self.w.testify(rec.tribunal_id, wits[0].player_id, "see clip", "no-such-clip")
        clip = self.w.record_clip(FootageType.COWARDICE, "AO-1", accused.player_id, charge.charge_id)
        self.w.testify(rec.tribunal_id, wits[0].player_id, "see clip", clip.clip_id)
        self.assertEqual(rec.testimony[-1].footage_id, clip.clip_id)


# ---------------------------------------------------------------------------
# King of Theater
# ---------------------------------------------------------------------------

class TestKingOfTheater(WorldCase):
    def test_crown_once_then_challenge_only(self):
        k, c = self.soldier("King"), self.soldier("Chal")
        self.w.crown("AO-7", k.player_id, {"spawn": "north"})
        with self.assertRaises(ValueError):
            self.w.crown("AO-7", c.player_id)

    def test_challenger_victory_takes_the_crown(self):
        k, c = self.soldier("King"), self.soldier("Chal")
        self.w.crown("AO-7", k.player_id)
        acc = self.w.challenge_king("AO-7", self.keys[c.player_id])
        self.assertEqual(acc.status, AccordStatus.ACTIVE)
        self.assertTrue(acc.defender_compelled)
        self.w.conclude(acc.accord_id, AccordOutcome.CHALLENGER_VICTORY, "AO taken", {"spawn": "east"})
        st = self.w.king("AO-7")
        self.assertEqual(st.king_id, c.player_id)
        self.assertEqual(st.spawn_rules, {"spawn": "east"})
        self.assertIn(("king_theater", "challenge_lost"), self.history_types())
        self.assertEqual(self.w.jacket(k.card_id)
                         .by_category(JacketCategory.ACCORD_HISTORY)[-1].detail["outcome"], "lost")

    def test_paid_crown_owes_disruptor_who_breaks_challenge_once(self):
        k, c, d = self.soldier("King"), self.soldier("Chal"), self.soldier("Disr")
        self.w.crown("AO-9", k.player_id, paid=True)
        self.assertEqual([s.ao_id for s in self.w.owed_disruptors()], ["AO-9"])
        acc = self.w.challenge_king("AO-9", self.keys[c.player_id])
        self.assertEqual(acc.terms.pay_advantages_disclosed,
                         {"king_of_theater": "crown purchased — free disruptor owed"})
        self.w.grant_disruptor("AO-9", d.player_id)
        self.assertEqual(self.w.owed_disruptors(), [])
        self.w.use_disruptor("AO-9", d.player_id, acc.accord_id)
        self.assertEqual(acc.outcome, AccordOutcome.DISRUPTED)
        self.assertEqual(self.w.king("AO-9").king_id, k.player_id)      # King stands
        with self.assertRaises(ValueError):
            self.w.grant_disruptor("AO-9", d.player_id)                 # never twice a reign
        with self.assertRaises(ValueError):
            self.w.grant_disruptor("AO-9", k.player_id)                 # King can't hold it

    def test_only_king_sets_spawn_rules(self):
        k, o = self.soldier("King"), self.soldier("Other")
        self.w.crown("AO-2", k.player_id)
        with self.assertRaises(ValueError):
            self.w.set_spawn_rules("AO-2", o.player_id, {"x": 1})
        self.w.set_spawn_rules("AO-2", k.player_id, {"x": 1})
        self.assertEqual(self.w.king("AO-2").spawn_rules, {"x": 1})

    def test_king_falls_with_challenge_open_challenger_crowned(self):
        k, c = self.soldier("King"), self.soldier("Chal")
        self.w.crown("AO-3", k.player_id)
        acc = self.w.challenge_king("AO-3", self.keys[c.player_id])
        self.w.kill(k, "artillery")
        self.assertEqual(acc.outcome, AccordOutcome.FORFEIT_DEFENDER)
        self.assertEqual(self.w.king("AO-3").king_id, c.player_id)

    def test_king_falls_unchallenged_throne_empties_disruptor_dies(self):
        k, d, n = self.soldier("King"), self.soldier("Disr"), self.soldier("Next")
        self.w.crown("AO-4", k.player_id)
        self.w.grant_disruptor("AO-4", d.player_id)
        self.w.kill(d, "mine")
        self.assertTrue(self.w.king("AO-4").disruptor_token_used)
        self.w.kill(k, "sniper")
        self.assertIsNone(self.w.king("AO-4").king_id)
        self.assertIn(("king_theater", "dethroned"), self.history_types())
        self.w.crown("AO-4", n.player_id)
        self.assertEqual(self.w.king("AO-4").king_id, n.player_id)


# ---------------------------------------------------------------------------
# Footage
# ---------------------------------------------------------------------------

class TestFootage(WorldCase):
    def test_top_kill_flagged_jacketed_and_in_history(self):
        a, b = self.soldier("Ace"), self.soldier("Bee")
        ca = self.w.record_clip(FootageType.KILL, "AO-1", a.player_id, "battle-1", 12)
        cb = self.w.record_clip(FootageType.KILL, "AO-1", b.player_id, "battle-1", 30)
        self.assertEqual(cb.top_kill_rank, 1)
        self.assertEqual(ca.top_kill_rank, 2)
        self.assertEqual([c.clip_id for c in self.w.top_kills("AO-1")], [cb.clip_id, ca.clip_id])
        j = self.w.jacket(b.card_id).by_category(JacketCategory.FOOTAGE)
        self.assertEqual(j[-1].summary, "Top Kill #1 in AO-1")
        self.assertEqual(sum(1 for e in self.w.world_history() if e["type"] == "footage"), 2)

    def test_non_kill_clips_jacket_only(self):
        a = self.soldier("Brave")
        clip = self.w.record_clip(FootageType.HEROISM, "AO-1", a.player_id, "battle-2")
        self.assertFalse(clip.flagged_top_kill)
        self.assertEqual(self.w.world_history(), [])
        self.assertEqual(len(self.w.jacket(a.card_id).by_category(JacketCategory.FOOTAGE)), 1)

    def test_r2_key_set_once(self):
        a = self.soldier("Cam")
        clip = self.w.record_clip(FootageType.KILL, "AO-5", a.player_id, "b", 3)
        self.w.attach_r2(clip.clip_id, "footage/abc.mp4")
        with self.assertRaises(ValueError):
            self.w.attach_r2(clip.clip_id, "footage/other.mp4")

    def test_kill_boards_belong_to_their_world(self):
        a = self.soldier("Solo")
        self.w.record_clip(FootageType.KILL, "AO-X", a.player_id, "b", 5)
        other = FrankWorld()
        self.assertEqual(other.top_kills("AO-X"), [])


# ---------------------------------------------------------------------------
# Frank's key
# ---------------------------------------------------------------------------

class TestFrankKey(WorldCase):
    def test_key_persists_0600_and_reloads(self):
        path = Path(self._env["PHOENIX_FRANK_KEY_FILE"])
        self.assertTrue(path.exists())
        self.assertEqual(len(path.read_bytes()), 32)
        self.assertEqual(_load_frank_key(), self.w._frank_key)
        if os.name == "posix":
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_env_key_wins_and_short_key_refused(self):
        os.environ["PHOENIX_FRANK_KEY"] = "ab" * 32
        self.assertEqual(_load_frank_key(), bytes.fromhex("ab" * 32))
        os.environ["PHOENIX_FRANK_KEY"] = "ab" * 8
        with self.assertRaises(ValueError):
            _load_frank_key()


if __name__ == "__main__":
    unittest.main(verbosity=1)
