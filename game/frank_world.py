#!/usr/bin/env python3
"""
frank_world.py — Frank World Orchestrator Integration
Phoenix DevOps OS | jwl247 | GPL v3

Frank is the world orchestrator and storage kernel.
Frank is not a persistent server. Frank is a kernel, imported on demand,
who witnesses all accords, enforces all laws, records all history,
and disappears when the session ends.

One instance. One pen. Zero movement.
The ring comes to Frank — Frank never moves.

This module wires the Phase 2 game systems into the existing Frank/Helix stack.
It is the only entry point for game state changes.
All game events flow through frank_world. Frank witnesses. Frank archives.

Integration points:
  - franken5.Frank5 / get_frank() for the Frank kernel
  - helix_i.HelixI for world state ingress
  - helix_e.HelixE for world state egress (translated at sector3 boundary)
  - game.draft_card for player identity
  - game.mos for MOS assessment
  - game.rank for rank and unit management
  - game.hospital for wound management
  - game.archive for permadeath
  - game.jacket for service records
  Phase 4: game.vehicle_world (mixin) — vehicles, upgrades, equipment, supply
  Phase 3:
  - game.accord / game.tribunal / game.king_theater / game.footage —
    every accord, verdict, crown and clip passes through this gate, lands in
    the jackets it touches, and is appended to world history.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from .draft_card  import DraftCard, CardStatus, issue_draft_card, derive_player_id
from .mos         import MOS, TrainingSession, MOSAssignment, assess_mos
from .rank        import Rank, RankRecord, promote, issue_unit, rank_display
from .hospital    import WoundSeverity, WoundHistory, admit, discharge, is_protected_by_hospital
from .archive     import Archive, archive_fallen, ArchiveEntry
from .jacket      import Jacket, JacketCategory
from .accord      import (
    Accord, AccordTerms, AccordStatus, AccordOutcome, AccordType, FRANK_AUTHORITY,
    propose_accord, countersign_accord, activate_accord, conclude_accord,
    void_accord, add_observer, check_expiry,
    world_history_entry as accord_history,
)
from .tribunal    import (
    TribunalCharge, TribunalRecord, TribunalStatus, TribunalVerdict, TribunalSentence,
    file_charges, open_tribunal, add_testimony, cast_vote, render_verdict,
    execute_sentence, world_history_entry as tribunal_history,
)
from . import king_theater as kt
from .vehicle_world import VehicleWorldMixin
from .vehicle import VehicleRegistry
from .world_history import WorldHistory, default_history_path
from . import territory as terr
from .territory import AO, AOControl, Battle, BattleStatus
from .named_ground import NamedGroundRegistry, GroundKind
from . import theater_map
from .footage     import (
    FootageClip, FootageType, AOKillBoard, record_footage, set_r2_key,
    try_flag_top_kill, jacket_entry as footage_jacket,
    world_history_entry as footage_history,
)

log = logging.getLogger("frank_world")


# ---------------------------------------------------------------------------
# Frank's signing key — signs compelled accords (King challenge, tribunal duel)
# ---------------------------------------------------------------------------

def _frank_key_path() -> Path:
    explicit = os.environ.get("PHOENIX_FRANK_KEY_FILE")
    if explicit:
        return Path(explicit)
    archive_root = Path(os.environ.get("PHOENIX_ARCHIVE_ROOT", "/var/lib/phoenix/archive"))
    return archive_root.parent / "frank_world.key"


def _load_frank_key() -> bytes:
    """
    Frank's key, in order: PHOENIX_FRANK_KEY (hex), the key file, or a new
    32-byte key written 0600 beside the archive the first time Frank runs.
    The key must outlive the session — compelled accords are verified with it
    later. If no file can be written, Frank runs on a session key and says so.
    """
    env_hex = os.environ.get("PHOENIX_FRANK_KEY")
    if env_hex:
        key = bytes.fromhex(env_hex.strip())
        if len(key) < 32:
            raise ValueError("PHOENIX_FRANK_KEY must be at least 32 bytes (64 hex chars)")
        return key

    path = _frank_key_path()
    if path.exists():
        key = path.read_bytes()
        if len(key) < 32:
            raise ValueError(f"Frank key file {path} is shorter than 32 bytes")
        return key

    import secrets
    key = secrets.token_bytes(32)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(key)
        log.info(f"Frank key created: {path}")
        return key
    except FileExistsError:
        return path.read_bytes()          # another process created it first
    except OSError as e:
        log.warning(f"Frank key not persisted ({path}: {e}) — session key only; "
                    "compelled accords from this session cannot be re-verified later")
        return key


def _side_outcome(outcome: AccordOutcome, role: str) -> str:
    """One party's view of an accord outcome, for their jacket."""
    if outcome in (AccordOutcome.DRAW, AccordOutcome.DISRUPTED):
        return outcome.value
    challenger_won = outcome in (AccordOutcome.CHALLENGER_VICTORY, AccordOutcome.FORFEIT_DEFENDER)
    forfeit = outcome in (AccordOutcome.FORFEIT_CHALLENGER, AccordOutcome.FORFEIT_DEFENDER)
    won = challenger_won if role == "challenger" else not challenger_won
    if won:
        return "won by forfeit" if forfeit else "won"
    return "forfeited" if forfeit else "lost"


# ---------------------------------------------------------------------------
# FrankWorld — the one gate to game state
# ---------------------------------------------------------------------------

class FrankWorld(VehicleWorldMixin):
    """
    The Phoenix world orchestrator.
    All game state changes go through here.
    Frank witnesses. Nothing escapes the jacket.

    Usage:
        fw = FrankWorld()
        card   = fw.enlist("player-key-hex", "Reaper", master_key=b"...")
        # ... training observations ...
        assign = fw.graduate(card, session)
        fw.wound(card, "combat", WoundSeverity.WOUNDED)
        fw.kill(card, "artillery_strike")
    """

    def __init__(
        self,
        frank=None,             # franken5.Frank5 instance (optional — late-bind)
        archive: Optional[Archive] = None,
        frank_key: Optional[bytes] = None,   # Frank's own signing key (compelled accords)
        registry: Optional[VehicleRegistry] = None,   # Phase 4 motor pool
        history:  Optional[WorldHistory] = None,      # Phase 5 permanent record
    ):
        self._frank   = frank
        self._archive = archive or Archive()
        self._frank_key = frank_key or _load_frank_key()

        # In-memory store keyed by card_id (production: backed by D1 / Frank bus)
        self._cards:       dict[str, DraftCard]      = {}
        self._rank_records:dict[str, RankRecord]     = {}
        self._jackets:     dict[str, Jacket]         = {}
        self._wound_history: dict[str, WoundHistory] = {}
        self._training:    dict[str, TrainingSession] = {}

        # Phase 3
        self._player_card: dict[str, str]           = {}   # player_id → current card_id
        self._accords:     dict[str, Accord]         = {}
        self._charges:     dict[str, TribunalCharge] = {}
        self._tribunals:   dict[str, TribunalRecord] = {}
        self._kings:       dict[str, kt.KingTheaterState] = {}   # ao_id → state
        self._clips:       dict[str, FootageClip]    = {}
        self._kill_boards: dict[str, AOKillBoard]    = {}
        self._history:     WorldHistory              = history or WorldHistory(default_history_path())

        # Phase 4
        self._init_vehicle_world(registry)

        # Phase 5
        self._aos:     dict[str, AO]     = {}
        self._battles: dict[str, Battle] = {}
        self._grounds = NamedGroundRegistry()

        log.info("FrankWorld online — Frank witnesses all")

    # -----------------------------------------------------------------------
    # Enlistment
    # -----------------------------------------------------------------------

    def enlist(
        self,
        callsign:   str,
        master_key: bytes,
        theater:    str = "Boot Camp",
    ) -> DraftCard:
        """
        Issue a draft card and open a training session.
        The player is in TRAINING until graduate() is called.
        """
        player_id = derive_player_id(master_key)
        card      = issue_draft_card(player_id, callsign, master_key, theater)

        rank_rec  = RankRecord(player_id=player_id, card_id=card.card_id)
        jacket    = Jacket(
            player_id  = player_id,
            card_id    = card.card_id,
            callsign   = callsign,
            created_ts = time.time(),
        )

        self._cards[card.card_id]        = card
        self._player_card[player_id]     = card.card_id
        self._rank_records[card.card_id] = rank_rec
        self._jackets[card.card_id]      = jacket
        self._wound_history[card.card_id]= WoundHistory(
            player_id = player_id,
            card_id   = card.card_id,
        )

        jacket.record(
            JacketCategory.DRAFT_CARD_REF,
            "Boot Camp",
            f"{callsign} enlisted",
            {"card_id": card.card_id, "player_id": player_id, "theater": theater},
        )

        log.info(f"Enlisted: {callsign} (card={card.card_id[:8]})")
        self._broadcast_event("enlistment", card, {})
        return card

    def open_training(self, card: DraftCard) -> TrainingSession:
        """Open a training session for a card in TRAINING status."""
        if card.status != CardStatus.TRAINING:
            raise ValueError(f"Card {card.card_id[:8]} is not in training")
        session = TrainingSession(
            player_id = card.player_id,
            card_id   = card.card_id,
        )
        self._training[card.card_id] = session
        return session

    # -----------------------------------------------------------------------
    # Graduation
    # -----------------------------------------------------------------------

    def graduate(self, card: DraftCard, session: TrainingSession) -> MOSAssignment:
        """
        Close training, assess MOS, field the card.
        Frank writes MOS to the card and the jacket.
        """
        session.finish()
        assignment = assess_mos(session)

        card.mos_code = assignment.mos_code
        card.field()    # TRAINING → ACTIVE

        rank_rec = self._rank_records[card.card_id]
        jacket   = self._jackets[card.card_id]

        jacket.record(
            JacketCategory.SERVICE_HISTORY,
            "Boot Camp",
            f"Graduated basic training — MOS: {assignment.mos.title}",
            {
                "mos_code":     assignment.mos_code,
                "mos_title":    assignment.mos.title,
                "confidence":   assignment.confidence,
                "observations": assignment.observation_count,
            },
        )

        log.info(
            f"Graduated: {card.callsign} → MOS {assignment.mos_code} "
            f"({assignment.mos.title}) conf={assignment.confidence:.2f}"
        )
        self._broadcast_event("graduated", card, {"mos": assignment.mos_code})
        return assignment

    # -----------------------------------------------------------------------
    # Rank & Unit Management
    # -----------------------------------------------------------------------

    def promote_player(
        self,
        card:        DraftCard,
        to_rank:     Rank,
        reason:      str,
        promoted_by: str = "FRANK",
    ) -> RankRecord:
        """Promote a player. Frank issues a unit if the new rank qualifies."""
        rec  = self._rank_records[card.card_id]
        j    = self._jackets[card.card_id]

        promote(rec, to_rank, reason, promoted_by)
        card.rank_code = to_rank.name

        j.record(
            JacketCategory.SERVICE_HISTORY,
            card.theater,
            f"Promoted to {rank_display(to_rank)} — {reason}",
            {
                "from_rank":    rec.promotions[-1]["from_rank"],
                "to_rank":      to_rank.value,
                "reason":       reason,
                "promoted_by":  promoted_by,
            },
        )
        self._broadcast_event("promoted", card, {"rank": to_rank.value, "reason": reason})
        return rec

    # -----------------------------------------------------------------------
    # Combat: Wounds & Death
    # -----------------------------------------------------------------------

    def wound(
        self,
        card:      DraftCard,
        cause:     str,
        severity:  WoundSeverity = WoundSeverity.WOUNDED,
    ) -> Optional[object]:
        """
        Process a wound.
        Private–Corporal have no hospital protection — critical can mean immediate KIA.
        Sergeant and above get the hospital system (GDD §3.4).
        """
        rank_rec = self._rank_records[card.card_id]
        jacket   = self._jackets[card.card_id]

        protected = is_protected_by_hospital(rank_rec.rank.value)

        if severity == WoundSeverity.KIA or (not protected and severity == WoundSeverity.CRITICAL):
            # Immediate KIA
            return self.kill(card, cause)

        rec, history = admit(
            card.player_id, card.card_id, severity, cause,
            self._wound_history.get(card.card_id),
        )
        self._wound_history[card.card_id] = history

        self._leave_vehicles(card)
        if severity == WoundSeverity.WOUNDED:
            card.wound("wound")
        else:
            card.wound("critical")

        jacket.record(
            JacketCategory.SERVICE_HISTORY,
            card.theater,
            f"Wounded ({severity.value}) — {cause}",
            {"severity": severity.value, "cause": cause, "protected": protected},
        )
        log.info(f"Wounded: {card.callsign} severity={severity.value} protected={protected}")
        self._broadcast_event("wounded", card, {"severity": severity.value, "cause": cause})
        return rec

    def discharge_player(self, card: DraftCard, unit_held: bool = False) -> DraftCard:
        """Discharge a player from hospital back to active duty."""
        history = self._wound_history.get(card.card_id)
        if not history or not history.active_record:
            raise ValueError(f"{card.callsign} is not hospitalised")

        rec = history.active_record
        discharge(rec, unit_held=unit_held)
        card.recover()

        jacket = self._jackets[card.card_id]
        jacket.record(
            JacketCategory.SERVICE_HISTORY,
            card.theater,
            "Discharged from hospital — returned to active duty",
            {"unit_held": unit_held},
        )
        self._broadcast_event("discharged", card, {"unit_held": unit_held})
        return card

    def kill(self, card: DraftCard, cause: str) -> ArchiveEntry:
        """
        Process permadeath. Archive the card. Jacket is permanent.
        Frank witnesses and archives. The world remembers.
        """
        if card.status in (CardStatus.KIA, CardStatus.ARCHIVED):
            raise ValueError(f"{card.callsign} is already {card.status.value} — death is final")
        jacket = self._jackets.get(card.card_id)
        honour = jacket.honour_score if jacket else 0.5
        sacrifices = [e.to_dict() for e in jacket.by_category(JacketCategory.SACRIFICE)] if jacket else []

        entry = archive_fallen(card, cause, honour, sacrifices, archive=self._archive)

        if jacket:
            jacket.record(
                JacketCategory.SERVICE_HISTORY,
                card.theater,
                f"KIA — {cause}",
                {"cause": cause, "honour_score": honour},
            )
            # Exceptional honour → boot camp legend
            if honour >= 0.8 and jacket.commendation_count >= 3:
                self._archive.promote_to_legend(card.card_id)
                log.info(f"Legend: {card.callsign} added to boot camp briefings")

        log.info(f"KIA: {card.callsign} — {cause} (honour={honour:.2f})")
        self._broadcast_event("KIA", card, {"cause": cause, "honour": honour})
        self._fall_from_thrones(card)
        self._vehicle_fallout(card)
        return entry

    # -----------------------------------------------------------------------
    # Jacket / Record Access
    # -----------------------------------------------------------------------

    def jacket(self, card_id: str) -> Optional[Jacket]:
        return self._jackets.get(card_id)

    def reputation(self, card_id: str) -> Optional[dict]:
        j = self._jackets.get(card_id)
        return j.reputation_summary() if j else None

    def card(self, card_id: str) -> Optional[DraftCard]:
        return self._cards.get(card_id)

    def card_of(self, player_id: str) -> Optional[DraftCard]:
        """The player's current card (the newest one Frank issued them)."""
        cid = self._player_card.get(player_id)
        return self._cards.get(cid) if cid else None

    def world_history(self) -> list[dict]:
        """Permanent world history, oldest first. A copy — the record is append-only."""
        return self._history.entries()

    def accord(self, accord_id: str) -> Optional[Accord]:
        return self._accords.get(accord_id)

    def tribunal(self, tribunal_id: str) -> Optional[TribunalRecord]:
        return self._tribunals.get(tribunal_id)

    def king(self, ao_id: str) -> Optional[kt.KingTheaterState]:
        return self._kings.get(ao_id)

    def clip(self, clip_id: str) -> Optional[FootageClip]:
        return self._clips.get(clip_id)

    def top_kills(self, ao_id: str, n: int = 10) -> list[FootageClip]:
        board = self._kill_boards.get(ao_id)
        return board.top(n) if board else []

    # -----------------------------------------------------------------------
    # Phase 3 — internal helpers
    # -----------------------------------------------------------------------

    def _live_card(self, player_id: str, role: str = "Player") -> DraftCard:
        card = self.card_of(player_id)
        if card is None:
            raise ValueError(f"{role} {player_id[:8]} has no draft card — enlist first")
        if card.status in (CardStatus.KIA, CardStatus.ARCHIVED):
            raise ValueError(f"{role} {card.callsign} is {card.status.value} — the dead hold no standing")
        if card.status == CardStatus.TRAINING:
            raise ValueError(f"{role} {card.callsign} is still in basic training")
        return card

    def _get(self, store: dict, key: str, what: str):
        obj = store.get(key)
        if obj is None:
            raise ValueError(f"Unknown {what}: {key}")
        return obj

    def _history_append(self, entry: dict) -> None:
        """Append to world history and fire it down Helix-E. Never rewritten."""
        rec = self._history.append(entry)
        self._emit({"event": f"history:{rec['type']}", **rec})

    def _emit(self, payload: dict) -> None:
        if self._frank is None:
            return
        try:
            self._frank.bus.write_stage(4, json.dumps(payload, default=str).encode())
        except Exception as e:
            log.warning(f"Broadcast failed ({payload.get('event')}): {e}")

    def _jacket_of_player(self, player_id: str) -> Optional[Jacket]:
        cid = self._player_card.get(player_id)
        return self._jackets.get(cid) if cid else None

    def _record_accord_jackets(self, accord: Accord) -> None:
        for role, pid, opp in (("challenger", accord.challenger_id, accord.defender_id),
                               ("defender",   accord.defender_id,   accord.challenger_id)):
            if pid == FRANK_AUTHORITY:
                continue
            j = self._jacket_of_player(pid)
            if j:
                j.record_accord(accord.terms.theater, accord.accord_name, role,
                                _side_outcome(accord.outcome, role), opp)

    def _king_state_for(self, accord_id: str) -> Optional[kt.KingTheaterState]:
        return next((s for s in self._kings.values() if s.challenge_accord_id == accord_id), None)

    # -----------------------------------------------------------------------
    # Phase 3 — Accords (GDD §7)
    # -----------------------------------------------------------------------

    def propose(
        self,
        challenger_key: bytes,
        defender_id:    str,
        terms:          AccordTerms,
    ) -> Accord:
        """The challenger names the accord and sets every rule. Their key signs it."""
        if terms.accord_type in (AccordType.KING_THEATER, AccordType.TRIBUNAL_DUEL):
            raise ValueError(f"{terms.accord_type.value} accords are issued by Frank, not proposed")
        challenger = self._live_card(derive_player_id(challenger_key), "Challenger")
        defender   = self._live_card(defender_id, "Defender")
        # Transparency Covenant (GDD §7.4): Frank writes every paid advantage
        # either side holds into the terms before they are hashed and signed.
        disclosed = dict(terms.pay_advantages_disclosed)
        for role, card in (("challenger", challenger), ("defender", defender)):
            for k, val in self.paid_advantages(card.player_id).items():
                disclosed[f"{role}:{card.callsign}:{k}"] = val
        terms.pay_advantages_disclosed = disclosed
        accord = propose_accord(
            challenger.player_id, challenger.card_id, challenger_key,
            defender.player_id, defender.card_id, terms,
        )
        self._accords[accord.accord_id] = accord
        self._emit({"event": "accord_proposed", **accord.to_dict()})
        return accord

    def countersign(self, accord_id: str, defender_key: bytes) -> Accord:
        accord = self._get(self._accords, accord_id, "accord")
        self._live_card(accord.defender_id, "Defender")
        countersign_accord(accord, defender_key)
        self._emit({"event": "accord_signed", **accord.to_dict()})
        return accord

    def activate(self, accord_id: str) -> Accord:
        accord = self._get(self._accords, accord_id, "accord")
        activate_accord(accord)
        self._emit({"event": "accord_active", **accord.to_dict()})
        return accord

    def observe(self, accord_id: str, player_id: str) -> Accord:
        accord = self._get(self._accords, accord_id, "accord")
        self._live_card(player_id, "Observer")
        add_observer(accord, player_id)
        return accord

    def void(self, accord_id: str, reason: str) -> Accord:
        accord = self._get(self._accords, accord_id, "accord")
        void_accord(accord, reason)
        self._emit({"event": "accord_voided", **accord.to_dict()})
        return accord

    def conclude(
        self,
        accord_id:       str,
        outcome:         AccordOutcome,
        detail:          str = "",
        new_spawn_rules: Optional[dict] = None,
    ) -> Accord:
        """
        Record the outcome. Immutable. Both jackets carry it; world history keeps
        the name forever. A King of Theater challenge also settles the crown.
        """
        accord = self._get(self._accords, accord_id, "accord")
        state  = self._king_state_for(accord_id)
        if state is not None:
            kt.conclude_challenge(state, accord, outcome, detail, new_spawn_rules, self._frank)
            self._history_append(kt.world_history_entry(
                state,
                kt.KingEvent.CHALLENGE_LOST if state.king_id == accord.challenger_id
                else kt.KingEvent.CHALLENGE_WON,
            ))
        else:
            conclude_accord(accord, outcome, detail, self._frank)
        self._record_accord_jackets(accord)
        self._history_append(accord_history(accord))
        self._settle_territory_stake(accord)
        return accord

    def sweep_expired(self) -> list[Accord]:
        """Conclude every accord whose clock ran out. No decisive result → DRAW."""
        done = []
        for accord in list(self._accords.values()):
            if not check_expiry(accord):
                continue
            if accord.status == AccordStatus.PROPOSED:
                self.void(accord.accord_id, "Not countersigned before the time limit")
            else:
                self.conclude(accord.accord_id, AccordOutcome.DRAW, "Time limit expired")
            done.append(accord)
        return done

    # -----------------------------------------------------------------------
    # Phase 3 — Tribunal (GDD §8)
    # -----------------------------------------------------------------------

    def file_charges(
        self,
        accused_id: str,
        charges:    list[str],
        filed_by:   str,
        witnesses:  list[str],
    ) -> TribunalCharge:
        """Any player files charges. Three witnesses, all real players, or nothing."""
        accused = self._live_card(accused_id, "Accused")
        self._live_card(filed_by, "Filer")
        for w in witnesses:
            if w != filed_by:
                self._live_card(w, "Witness")
        charge = file_charges(accused.player_id, accused.card_id, charges,
                              filed_by, accused.theater, witnesses)
        self._charges[charge.charge_id] = charge
        self._emit({"event": "charges_filed", **charge.to_dict()})
        return charge

    def open_tribunal(self, charge_id: str, jurors: list[str]) -> TribunalRecord:
        """
        Seat a jury of peers: active players in the accused's theater. Anyone
        else offered is set aside. Too few → dismissed, and that is recorded too.
        """
        charge = self._get(self._charges, charge_id, "charge")
        if any(t.charge.charge_id == charge_id for t in self._tribunals.values()):
            raise ValueError(f"Charge {charge_id[:8]} already has a tribunal")
        eligible = []
        for pid in jurors:
            card = self.card_of(pid)
            if card and card.status == CardStatus.ACTIVE and card.theater == charge.theater:
                eligible.append(pid)
        record = open_tribunal(charge, eligible)
        self._tribunals[record.tribunal_id] = record
        if record.verdict == TribunalVerdict.DISMISSED:
            self._record_tribunal_jacket(record)
            self._history_append(tribunal_history(record))
        else:
            self._emit({"event": "tribunal_opened", **record.to_dict()})
        return record

    def testify(
        self,
        tribunal_id: str,
        witness_id:  str,
        text:        str,
        footage_id:  Optional[str] = None,
    ) -> TribunalRecord:
        record = self._get(self._tribunals, tribunal_id, "tribunal")
        witness = self._live_card(witness_id, "Witness")
        if footage_id is not None:
            self._get(self._clips, footage_id, "footage clip")
        return add_testimony(record, witness_id, witness.callsign, text, footage_id)

    def vote(self, tribunal_id: str, juror_id: str, verdict: TribunalVerdict) -> TribunalRecord:
        record = self._get(self._tribunals, tribunal_id, "tribunal")
        return cast_vote(record, juror_id, verdict)

    def render_verdict(
        self,
        tribunal_id: str,
        sentence:    TribunalSentence,
        detail:      str = "",
    ) -> TribunalRecord:
        """
        Tally, seal, carry out. Frank presides; the verdict is immutable.
        EXECUTION is permadeath; TRIBUNAL_DUEL is a Frank-issued accord the
        accused cannot refuse; DISHONOUR is a permanent court-martial entry.
        """
        record  = self._get(self._tribunals, tribunal_id, "tribunal")
        accused = self._cards[record.charge.accused_card]
        if accused.status in (CardStatus.KIA, CardStatus.ARCHIVED):
            raise ValueError(f"{accused.callsign} is {accused.status.value} — no sentence can be carried out")
        render_verdict(record, sentence, detail)
        self._record_tribunal_jacket(record)
        execute_sentence(record, self, accused, self._frank_key, self._frank)
        if record.duel_accord is not None:
            self._accords[record.duel_accord.accord_id] = record.duel_accord
            self._emit({"event": "accord_signed", **record.duel_accord.to_dict()})
        self._history_append(tribunal_history(record))
        return record

    def _record_tribunal_jacket(self, record: TribunalRecord) -> None:
        j = self._jackets.get(record.charge.accused_card)
        if j is None:
            return
        j.record_tribunal(
            record.charge.theater, "; ".join(record.charge.charges), record.verdict.value,
            {"tribunal_id": record.tribunal_id, "sentence": record.sentence.value,
             "frank_seal": record.frank_witness_hash},
        )
        if record.sentence == TribunalSentence.DISHONOUR:
            j.record(
                JacketCategory.COURT_MARTIAL, record.charge.theater,
                f"Dishonoured by tribunal — {'; '.join(record.charge.charges)}",
                {"tribunal_id": record.tribunal_id, "verdict_detail": record.verdict_detail},
            )

    # -----------------------------------------------------------------------
    # Phase 3 — King of Theater (GDD §7.2)
    # -----------------------------------------------------------------------

    def crown(
        self,
        ao_id:       str,
        player_id:   str,
        spawn_rules: Optional[dict] = None,
        paid:        bool = False,
    ) -> kt.KingTheaterState:
        """First claim on an empty AO. A held AO is taken only by challenge."""
        card = self._live_card(player_id, "King")
        state = self._kings.get(ao_id)
        if state is not None and state.king_id is not None:
            raise ValueError(f"AO {ao_id} is held by {state.king_callsign} — challenge the King")
        new = kt.crown_king(ao_id, card.theater, card.player_id, card.card_id,
                            card.callsign, spawn_rules, paid, self._frank)
        self._kings[ao_id] = new
        self._jackets[card.card_id].record(
            JacketCategory.SERVICE_HISTORY, card.theater, f"Crowned King of {ao_id}",
            {"ao_id": ao_id, "paid_crown": paid, "frank_seal": new.frank_witness_hash},
        )
        self._history_append(kt.world_history_entry(new, kt.KingEvent.CROWNED))
        return new

    def challenge_king(
        self,
        ao_id:           str,
        challenger_key:  bytes,
        territory_stake: Optional[str] = None,
    ) -> Accord:
        """The King cannot refuse. Frank countersigns by law; the fight is live."""
        state = self._get(self._kings, ao_id, "AO")
        challenger = self._live_card(derive_player_id(challenger_key), "Challenger")
        _, accord = kt.challenge_king(
            state, challenger.player_id, challenger.card_id, challenger.callsign,
            challenger_key, self._frank_key, territory_stake, self._frank,
        )
        self._accords[accord.accord_id] = accord
        self._history_append(kt.world_history_entry(state, kt.KingEvent.CHALLENGED))
        return accord

    def grant_disruptor(self, ao_id: str, player_id: str) -> kt.KingTheaterState:
        state = self._get(self._kings, ao_id, "AO")
        card = self._live_card(player_id, "Disruptor")
        kt.grant_disruptor(state, card.player_id, card.card_id, card.callsign, self._frank)
        self._history_append(kt.world_history_entry(state, kt.KingEvent.DISRUPTOR_GRANTED))
        return state

    def use_disruptor(self, ao_id: str, player_id: str, accord_id: str) -> Accord:
        """Break one live accord in the AO. Token gone. The disruptor is named."""
        state  = self._get(self._kings, ao_id, "AO")
        accord = self._get(self._accords, accord_id, "accord")
        self._live_card(player_id, "Disruptor")
        kt.use_disruptor(state, player_id, accord, self._frank)
        self._record_accord_jackets(accord)
        j = self._jacket_of_player(player_id)
        if j:
            j.record(JacketCategory.ACCORD_HISTORY, state.theater,
                     f"Disrupted accord '{accord.accord_name}'",
                     {"accord_id": accord_id, "ao_id": ao_id})
        self._history_append(accord_history(accord))
        self._history_append(kt.world_history_entry(state, kt.KingEvent.DISRUPTOR_USED))
        return accord

    def owed_disruptors(self) -> list[kt.KingTheaterState]:
        """
        AOs whose crown was bought and whose free disruptor has not spawned yet
        (GDD §7.2 — every dollar spent spawns a counter). Matchmaking picks a
        player of equivalent combat capability and calls grant_disruptor.
        """
        return [s for s in self._kings.values() if s.disruptor_owed and s.king_id]

    def set_spawn_rules(self, ao_id: str, player_id: str, spawn_rules: dict) -> kt.KingTheaterState:
        state = self._get(self._kings, ao_id, "AO")
        kt.set_spawn_rules(state, player_id, spawn_rules)
        self._history_append(kt.world_history_entry(state, kt.KingEvent.SPAWN_RULES))
        return state

    def _fall_from_thrones(self, card: DraftCard) -> None:
        """
        Death is final, for every standing the fallen held: their live accords
        are forfeited, a King's crown goes (to the challenger if one is in the
        field), and an unused disruptor token dies with its holder.
        """
        pid = card.player_id
        for accord in list(self._accords.values()):
            if accord.status not in (AccordStatus.SIGNED, AccordStatus.ACTIVE):
                if accord.status == AccordStatus.PROPOSED and pid in (accord.challenger_id, accord.defender_id):
                    self.void(accord.accord_id, f"{card.callsign} fell before signing")
                continue
            if pid == accord.challenger_id:
                self.conclude(accord.accord_id, AccordOutcome.FORFEIT_CHALLENGER, f"{card.callsign} KIA")
            elif pid == accord.defender_id:
                self.conclude(accord.accord_id, AccordOutcome.FORFEIT_DEFENDER, f"{card.callsign} KIA")

        for ao in self._aos.values():
            if ao.controller_id != pid:
                continue
            if ao.control == AOControl.CONTESTED:     # the contest decides it now
                ao.controller_id = ao.controller_callsign = ao.held_since = None
            else:
                terr.vacate(ao)
            self._history_append({"type": "territory", "event": "holder_fell", **ao.state(),
                                  "fallen": card.callsign})

        for state in self._kings.values():
            if state.king_id == pid:     # no challenge left open — forfeits settled above
                kt.dethrone(state, f"{card.callsign} KIA", self._frank)
                self._history_append({**kt.world_history_entry(state, kt.KingEvent.DETHRONED),
                                      "fallen_king": card.callsign})
            if state.disruptor_id == pid and not state.disruptor_token_used:
                kt.expire_disruptor(state, f"{card.callsign} KIA", self._frank)
                self._history_append(kt.world_history_entry(state, kt.KingEvent.DISRUPTOR_EXPIRED))

    # -----------------------------------------------------------------------
    # Phase 3 — Footage (GDD §6.1)
    # -----------------------------------------------------------------------

    def record_clip(
        self,
        footage_type:       FootageType,
        ao_id:              str,
        player_id:          str,
        event_id:           str,
        kill_count_at_time: int = 0,
        secondary_id:       Optional[str] = None,
        r2_key:             Optional[str] = None,
    ) -> FootageClip:
        """
        Frank captures the moment. It lands in the player's jacket; a KILL clip
        that makes the AO's top board is flagged and enters world history.
        The video itself goes to the clone pool; attach its key with attach_r2.
        """
        card = self.card_of(player_id)
        if card is None:
            raise ValueError(f"Player {player_id[:8]} has no draft card")
        second = self.card_of(secondary_id) if secondary_id else None
        if secondary_id and second is None:
            raise ValueError(f"Player {secondary_id[:8]} has no draft card")

        clip = record_footage(
            footage_type, ao_id, card.theater, card.player_id, card.callsign, event_id,
            r2_key, kill_count_at_time,
            second.player_id if second else None, second.callsign if second else None,
        )
        board = self._kill_boards.setdefault(ao_id, AOKillBoard(ao_id))
        try_flag_top_kill(clip, self._frank, board)
        self._clips[clip.clip_id] = clip

        entry = footage_jacket(clip)
        self._jackets[card.card_id].record(JacketCategory.FOOTAGE, card.theater, entry["label"], entry)
        if clip.flagged_top_kill:
            self._history_append(footage_history(clip))
        return clip

    def attach_r2(self, clip_id: str, r2_key: str) -> FootageClip:
        return set_r2_key(self._get(self._clips, clip_id, "footage clip"), r2_key)

    # -----------------------------------------------------------------------
    # Phase 5 — Territory, battles, named ground (GDD §11), the map
    # -----------------------------------------------------------------------

    OFFICER_MIN_RANK = Rank.LIEUTENANT

    def ao(self, ao_id: str) -> Optional[AO]:
        return self._aos.get(ao_id)

    def battle(self, battle_id: str) -> Optional[Battle]:
        return self._battles.get(battle_id)

    def named_ground(self, theater: Optional[str] = None) -> list:
        return self._grounds.active(theater)

    def define_ao(self, ao_id: str, theater: str, name: str, polygon: list) -> AO:
        """World building: an Area of Operations on real ground."""
        if ao_id in self._aos:
            raise ValueError(f"AO {ao_id} already exists — ground is not redrawn")
        a = AO(ao_id, theater, name, polygon)
        self._aos[ao_id] = a
        self._history_append({"type": "territory", "event": "ao_defined", **a.state(),
                              "polygon": a.polygon})
        return a

    def take_ground(self, ao_id: str, player_id: str) -> AO:
        """Unheld ground goes to whoever holds it first."""
        a = self._get(self._aos, ao_id, "AO")
        card = self._live_card(player_id, "Soldier")
        if card.theater != a.theater:
            raise ValueError(f"{card.callsign} is not in {a.theater}")
        terr.take_neutral(a, card.player_id, card.callsign)
        self._history_append({"type": "territory", "event": "taken", **a.state()})
        return a

    def open_battle(self, ao_id: str, name: str, organizer_id: str, contest: bool = False) -> Battle:
        """
        GDD §8.1 — whoever organizes a battle is its field commander. contest=True
        means the organizer is fighting for held ground: the AO goes CONTESTED.
        """
        a = self._get(self._aos, ao_id, "AO")
        org = self._live_card(organizer_id, "Organizer")
        if org.theater != a.theater:
            raise ValueError(f"{org.callsign} is not in {a.theater}")
        if any(b.ao_id == ao_id and b.status == BattleStatus.OPEN for b in self._battles.values()):
            raise ValueError(f"A battle is already being fought in {ao_id}")
        b = terr.new_battle(a, name, org.player_id)
        if contest:
            terr.contest(a, org.player_id, b.battle_id)
            self._history_append({"type": "territory", "event": "contested", **a.state(),
                                  "battle_id": b.battle_id})
        self._battles[b.battle_id] = b
        self._emit({"event": "battle_opened", **b.to_dict()})
        return b

    def join_battle(self, battle_id: str, player_id: str) -> Battle:
        b = self._get(self._battles, battle_id, "battle")
        if b.status != BattleStatus.OPEN:
            raise ValueError("That battle is over")
        card = self._live_card(player_id, "Soldier")
        if card.theater != b.theater:
            raise ValueError(f"{card.callsign} is not in {b.theater}")
        if player_id not in b.participants:
            b.participants.append(player_id)
        return b

    def battle_casualty(
        self,
        battle_id: str,
        player_id: str,
        cause:     str,
        holding:   bool = False,
        lon:       Optional[float] = None,
        lat:       Optional[float] = None,
    ):
        """
        A soldier falls in battle. An officer who dies holding a field position
        gives that ground their name — automatically, permanently (GDD §11.1).
        """
        b = self._get(self._battles, battle_id, "battle")
        if b.status != BattleStatus.OPEN:
            raise ValueError("That battle is over")
        if player_id not in b.participants:
            raise ValueError("Only those who fought in the battle fall in it")
        card = self.card_of(player_id)
        rank = self._rank_records[card.card_id].rank
        a = self._aos[b.ao_id]
        names_ground = holding and rank >= self.OFFICER_MIN_RANK
        if names_ground:
            if lon is None or lat is None:
                raise ValueError("An officer holding ground needs the ground's position")
            if not a.contains(lon, lat):
                raise ValueError(f"({lon}, {lat}) is not inside {a.name}")
        b.casualties += 1
        b.fallen.append(player_id)
        entry = self.kill(card, cause)
        if names_ground:
            b.officers_fallen_holding.append(player_id)
            g, replaced = self._grounds.name_fallen_officer(
                a.ao_id, a.theater, lon, lat, card.player_id, card.callsign,
                rank_display(rank), b.battle_id, b.casualties)
            self._history_append({"type": "named_ground", **g.to_dict(),
                                  "replaced": [r.ground_id for r in replaced]})
        return entry

    def close_battle(self, battle_id: str, winner_id: Optional[str] = None, outcome: str = "") -> Battle:
        """
        The battle enters every participant's jacket (it counts toward earned
        gear) and world history. A contest is settled: the challenger takes the
        ground only by winning it.
        """
        b = self._get(self._battles, battle_id, "battle")
        if b.status != BattleStatus.OPEN:
            raise ValueError("That battle is already closed")
        if winner_id and winner_id not in b.participants:
            raise ValueError("The winner must have fought in the battle")
        b.status, b.winner_id, b.outcome, b.closed_ts = BattleStatus.CLOSED, winner_id, outcome, time.time()
        for pid in b.participants:
            j = self._jacket_of_player(pid)
            if j:
                result = ("fell" if pid in b.fallen else
                          "won" if pid == winner_id else "fought")
                j.record_battle(b.theater, b.name, result,
                                {"battle_id": b.battle_id, "ao_id": b.ao_id, "casualties": b.casualties})
        a = self._aos[b.ao_id]
        if a.control == AOControl.CONTESTED and a.contest_battle_id == b.battle_id:
            w = self.card_of(winner_id) if winner_id else None
            alive = w is not None and w.status not in (CardStatus.KIA, CardStatus.ARCHIVED)
            terr.resolve(a, winner_id if alive else None, w.callsign if alive else None)
            self._history_append({"type": "territory", "event": "contest_settled", **a.state(),
                                  "battle_id": b.battle_id})
        self._history_append({"type": "battle", **b.to_dict()})
        return b

    def name_ground(self, player_id: str, battle_id: str, name: str, lon: float, lat: float):
        """After a real battle, one who fought in it may name ground in that AO."""
        b = self._get(self._battles, battle_id, "battle")
        if b.status != BattleStatus.CLOSED:
            raise ValueError("Ground is named after the battle, not during it")
        if player_id not in b.participants:
            raise ValueError("Only those who fought there may name the ground")
        card = self._live_card(player_id, "Soldier")
        a = self._aos[b.ao_id]
        if not a.contains(lon, lat):
            raise ValueError(f"({lon}, {lat}) is not inside {a.name}")
        g, replaced = self._grounds.name_by_player(
            a.ao_id, a.theater, lon, lat, card.player_id, card.callsign, name,
            b.battle_id, b.casualties)
        self._history_append({"type": "named_ground", **g.to_dict(),
                              "replaced": [r.ground_id for r in replaced]})
        return g

    def _settle_territory_stake(self, accord: Accord) -> None:
        """An accord that staked an AO moves it — but only what the loser actually held."""
        a = self._aos.get(accord.terms.territory_stake or "")
        if a is None or accord.outcome is None:
            return
        if accord.outcome in (AccordOutcome.CHALLENGER_VICTORY, AccordOutcome.FORFEIT_DEFENDER):
            winner, loser = accord.challenger_id, accord.defender_id
        elif accord.outcome in (AccordOutcome.DEFENDER_VICTORY, AccordOutcome.FORFEIT_CHALLENGER):
            winner, loser = accord.defender_id, accord.challenger_id
        else:
            return
        w = self.card_of(winner)
        if a.controller_id != loser or w is None or w.status in (CardStatus.KIA, CardStatus.ARCHIVED):
            return
        terr.transfer(a, winner, w.callsign)
        self._history_append({"type": "territory", "event": "won_by_accord", **a.state(),
                              "accord_id": accord.accord_id, "accord_name": accord.accord_name})

    def _theater_layers(self, theater: str):
        aos = [a for a in self._aos.values() if a.theater == theater]
        kings = [(s, self._aos[s.ao_id]) for s in self._kings.values()
                 if s.king_id and s.ao_id in self._aos and self._aos[s.ao_id].theater == theater]
        return aos, self._grounds.active(theater), kings

    def map_payload(self, theater: str, worker_url: Optional[str] = None) -> dict:
        """What the Godot client draws for a theater."""
        return theater_map.map_payload(theater, *self._theater_layers(theater), worker_url=worker_url)

    def theater_snapshot(self, theater: str, out, source=None, width: int = 1024, height: int = 768):
        """Frank's strategic overview PNG. Returns (path, sha3-512); intake it to keep it."""
        aos, grounds, kings = self._theater_layers(theater)
        return theater_map.snapshot(aos, grounds, kings, out, source, width, height,
                                    title=f"{theater} — strategic overview")

    # -----------------------------------------------------------------------
    # Events → Helix-E (broadcast to world)
    # -----------------------------------------------------------------------

    def _broadcast_event(self, event_type: str, card: DraftCard, payload: dict) -> None:
        """
        Push world events through Helix-E for distribution.
        Helix-E handles translation at the sector3 boundary.
        Frank fires and forgets.
        """
        if self._frank is None:
            return   # dev mode — no Frank bus attached
        try:
            msg = json.dumps({
                "event":     event_type,
                "card_id":   card.card_id,
                "callsign":  card.callsign,
                "player_id": card.player_id,
                "ts":        time.time(),
                **payload,
            }).encode()
            # Channel 5 = primary egress strand A (helixe.py)
            self._frank.bus.write_stage(4, msg)   # slot 4 = channel 5
            log.debug(f"Broadcast: {event_type} for {card.callsign}")
        except Exception as e:
            log.warning(f"Broadcast failed ({event_type}): {e}")


# ---------------------------------------------------------------------------
# Module-level singleton (opt-in)
# ---------------------------------------------------------------------------

_world: Optional[FrankWorld] = None


def get_world() -> FrankWorld:
    """Return the shared FrankWorld instance, creating it if necessary."""
    global _world
    if _world is None:
        _world = FrankWorld()
    return _world
