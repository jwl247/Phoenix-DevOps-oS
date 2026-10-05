#!/usr/bin/env python3
"""
tribunal.py — The Tribunal System
Sacrifice | Phoenix DevOps OS | jwl247 | GPL v3

Players run the tribunal. Frank presides. The verdict is immutable.
Charges require 3 witnesses to proceed.
A jury of 5 active players in the same theater renders the verdict.
Sentence: EXECUTION (permadeath via frank_world.kill), TRIBUNAL_DUEL
(auto-generates an accord of type TRIBUNAL_DUEL), or DISHONOUR (permanent
jacket entry, no permadeath).

GDD §8 — The Tribunal System
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .accord import (
    Accord, AccordTerms, AccordType, FRANK_AUTHORITY,
    propose_accord, countersign_by_authority,
)

log = logging.getLogger("tribunal")


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class TribunalStatus(Enum):
    OPEN          = "open"           # Charges filed, awaiting jury assembly
    DELIBERATING  = "deliberating"   # Jury seated, testimony collected, voting
    VERDICT       = "verdict"        # Verdict rendered — immutable from here
    EXECUTED      = "executed"       # Sentence carried out by Frank


class TribunalVerdict(Enum):
    GUILTY     = "guilty"
    NOT_GUILTY = "not_guilty"
    DISMISSED  = "dismissed"        # Insufficient witnesses or jurors


class TribunalSentence(Enum):
    EXECUTION      = "execution"      # Permadeath — frank_world.kill()
    TRIBUNAL_DUEL  = "tribunal_duel"  # Auto-issued accord: TRIBUNAL_DUEL type
    DISHONOUR      = "dishonour"      # Jacket entry, dishonour score, no death
    ACQUITTAL      = "acquittal"      # Not guilty — no sentence


MIN_WITNESSES = 3
MIN_JURORS    = 5


# ---------------------------------------------------------------------------
# Charge — what the accused is being tried for
# ---------------------------------------------------------------------------

@dataclass
class TribunalCharge:
    """
    Filed charges. Requires MIN_WITNESSES to proceed to tribunal.
    """
    charge_id:   str
    accused_id:  str
    accused_card: str                       # card_id of the accused
    charges:     list[str]                  # list of charge descriptions
    filed_by:    str                        # player_id of the filer
    theater:     str                        # AO where the tribunal is held
    witnesses:   list[str] = field(default_factory=list)   # player_ids
    filed_ts:    float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "charge_id":   self.charge_id,
            "accused_id":  self.accused_id,
            "accused_card": self.accused_card,
            "charges":     self.charges,
            "filed_by":    self.filed_by,
            "theater":     self.theater,
            "witnesses":   self.witnesses,
            "filed_ts":    self.filed_ts,
        }


# ---------------------------------------------------------------------------
# Testimony — witness statement, optionally linked to footage
# ---------------------------------------------------------------------------

@dataclass
class Testimony:
    witness_id:  str
    callsign:    str
    text:        str
    footage_id:  Optional[str] = None   # clip_id from footage.py, if provided
    ts:          float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "witness_id": self.witness_id,
            "callsign":   self.callsign,
            "text":       self.text,
            "footage_id": self.footage_id,
            "ts":         self.ts,
        }


# ---------------------------------------------------------------------------
# Jury vote
# ---------------------------------------------------------------------------

@dataclass
class JuryVote:
    juror_id:  str
    vote:      TribunalVerdict   # GUILTY or NOT_GUILTY only (DISMISSED is automatic)
    ts:        float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "juror_id": self.juror_id,
            "vote":     self.vote.value,
            "ts":       self.ts,
        }


# ---------------------------------------------------------------------------
# TribunalRecord — the binding record
# ---------------------------------------------------------------------------

@dataclass
class TribunalRecord:
    """
    The full tribunal. Frank presides. Verdict is immutable once rendered.
    Both jackets carry this. World history records it.
    """
    tribunal_id:        str
    charge:             TribunalCharge

    status:             TribunalStatus = TribunalStatus.OPEN

    # Jury
    jurors:             list[str]     = field(default_factory=list)   # player_ids
    votes:              list[JuryVote] = field(default_factory=list)
    testimony:          list[Testimony] = field(default_factory=list)

    # Verdict — set once, immutable
    verdict:            Optional[TribunalVerdict] = None
    sentence:           Optional[TribunalSentence] = None
    verdict_detail:     Optional[str]              = None

    # Timestamps
    opened_ts:          float  = field(default_factory=time.time)
    verdict_ts:         Optional[float] = None
    executed_ts:        Optional[float] = None

    # If sentence is TRIBUNAL_DUEL — the accord auto-generated
    duel_accord_id:     Optional[str] = None
    duel_accord:        Optional[Accord] = field(default=None, repr=False)  # live object, not serialised

    # Frank's immutable seal over the verdict
    frank_witness_hash: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "tribunal_id":        self.tribunal_id,
            "charge":             self.charge.to_dict(),
            "status":             self.status.value,
            "jurors":             self.jurors,
            "votes":              [v.to_dict() for v in self.votes],
            "testimony":          [t.to_dict() for t in self.testimony],
            "verdict":            self.verdict.value if self.verdict else None,
            "sentence":           self.sentence.value if self.sentence else None,
            "verdict_detail":     self.verdict_detail,
            "opened_ts":          self.opened_ts,
            "verdict_ts":         self.verdict_ts,
            "executed_ts":        self.executed_ts,
            "duel_accord_id":     self.duel_accord_id,
            "frank_witness_hash": self.frank_witness_hash,
        }


# ---------------------------------------------------------------------------
# Frank's seal
# ---------------------------------------------------------------------------

def _frank_seal(record: TribunalRecord) -> str:
    """SHA3-512 of the verdict, sentence, votes, and charge hash."""
    blob = json.dumps({
        "tribunal_id":   record.tribunal_id,
        "accused_id":    record.charge.accused_id,
        "charges":       record.charge.charges,
        "verdict":       record.verdict.value if record.verdict else None,
        "sentence":      record.sentence.value if record.sentence else None,
        "verdict_detail": record.verdict_detail,
        "verdict_ts":    record.verdict_ts,
        "jurors":        sorted(record.jurors),
        "votes":         sorted((v.juror_id, v.vote.value) for v in record.votes),
        "witnesses":     sorted(record.charge.witnesses),
    }, sort_keys=True).encode()
    return hashlib.sha3_512(blob).hexdigest()


# ---------------------------------------------------------------------------
# Core operations
# ---------------------------------------------------------------------------

def file_charges(
    accused_id:   str,
    accused_card: str,
    charges:      list[str],
    filed_by:     str,
    theater:      str,
    witnesses:    list[str],
) -> TribunalCharge:
    """
    File charges. Requires at least MIN_WITNESSES witnesses to proceed.
    The filer cannot be listed as a witness (conflict of interest).
    """
    if not charges:
        raise ValueError("Charges list cannot be empty")

    witnesses = [w for w in witnesses if w != filed_by]   # filer cannot witness

    if len(witnesses) < MIN_WITNESSES:
        raise ValueError(
            f"At least {MIN_WITNESSES} witnesses required; "
            f"got {len(witnesses)} (excluding filer)"
        )

    if accused_id == filed_by:
        raise ValueError("A player cannot file charges against themselves")

    charge = TribunalCharge(
        charge_id   = str(uuid.uuid4()),
        accused_id  = accused_id,
        accused_card = accused_card,
        charges     = charges,
        filed_by    = filed_by,
        theater     = theater,
        witnesses   = witnesses,
    )
    log.info(
        f"Charges filed: {accused_id[:8]} accused by {filed_by[:8]} "
        f"({len(charges)} charge(s), {len(witnesses)} witness(es))"
    )
    return charge


def open_tribunal(
    charge:  TribunalCharge,
    jurors:  list[str],
) -> TribunalRecord:
    """
    Seat the jury and open the tribunal.
    Requires MIN_JURORS active players in the same theater.
    Accused, filer, and witnesses cannot serve as jurors.
    """
    excluded = {charge.accused_id, charge.filed_by, *charge.witnesses}
    jurors = list(dict.fromkeys(j for j in jurors if j not in excluded))

    if len(jurors) < MIN_JURORS:
        # Auto-dismiss — insufficient jurors
        record = TribunalRecord(
            tribunal_id = str(uuid.uuid4()),
            charge      = charge,
            status      = TribunalStatus.VERDICT,
            verdict     = TribunalVerdict.DISMISSED,
            sentence    = TribunalSentence.ACQUITTAL,
            verdict_detail = (
                f"Dismissed: only {len(jurors)} eligible juror(s) "
                f"available (need {MIN_JURORS})"
            ),
            verdict_ts  = time.time(),
        )
        record.frank_witness_hash = _frank_seal(record)
        log.warning(
            f"Tribunal dismissed for {charge.accused_id[:8]}: "
            f"insufficient jurors ({len(jurors)}/{MIN_JURORS})"
        )
        return record

    record = TribunalRecord(
        tribunal_id = str(uuid.uuid4()),
        charge      = charge,
        status      = TribunalStatus.DELIBERATING,
        jurors      = jurors[:],
    )
    log.info(
        f"Tribunal opened: {record.tribunal_id[:8]} — "
        f"accused={charge.accused_id[:8]}, jurors={len(record.jurors)}"
    )
    return record


def add_testimony(
    record:      TribunalRecord,
    witness_id:  str,
    callsign:    str,
    text:        str,
    footage_id:  Optional[str] = None,
) -> TribunalRecord:
    """
    Add witness testimony. Only listed witnesses may testify.
    Testimony is locked once the verdict is rendered.
    """
    if record.status != TribunalStatus.DELIBERATING:
        raise ValueError(
            f"Tribunal {record.tribunal_id[:8]} is not in deliberation "
            f"(status: {record.status.value})"
        )
    if witness_id not in record.charge.witnesses:
        raise ValueError(
            f"Player {witness_id[:8]} is not a listed witness for this tribunal"
        )

    record.testimony.append(Testimony(
        witness_id = witness_id,
        callsign   = callsign,
        text       = text,
        footage_id = footage_id,
    ))
    log.info(f"Testimony added: {callsign} for tribunal {record.tribunal_id[:8]}")
    return record


def cast_vote(
    record:   TribunalRecord,
    juror_id: str,
    vote:     TribunalVerdict,
) -> TribunalRecord:
    """
    Cast a jury vote. Each juror votes once.
    Only GUILTY and NOT_GUILTY are valid votes — DISMISSED is automatic.
    """
    if record.status != TribunalStatus.DELIBERATING:
        raise ValueError(
            f"Tribunal {record.tribunal_id[:8]} is not accepting votes"
        )
    if juror_id not in record.jurors:
        raise ValueError(f"Player {juror_id[:8]} is not a seated juror")
    if any(v.juror_id == juror_id for v in record.votes):
        raise ValueError(f"Juror {juror_id[:8]} has already voted")
    if vote == TribunalVerdict.DISMISSED:
        raise ValueError("Jurors cannot vote DISMISSED — that is automatic")

    record.votes.append(JuryVote(juror_id=juror_id, vote=vote))
    log.info(
        f"Vote cast: {juror_id[:8]} voted {vote.value} "
        f"for tribunal {record.tribunal_id[:8]} "
        f"({len(record.votes)}/{len(record.jurors)} votes in)"
    )
    return record


def render_verdict(
    record:         TribunalRecord,
    sentence:       TribunalSentence,
    verdict_detail: str = "",
) -> TribunalRecord:
    """
    Tally votes and render the verdict. Requires all jurors to have voted.
    Simple majority: more GUILTY than NOT_GUILTY = GUILTY.
    Frank seals the verdict. Immutable from this point.

    The caller is responsible for collecting all votes before calling this.
    """
    if record.status != TribunalStatus.DELIBERATING:
        raise ValueError(
            f"Tribunal {record.tribunal_id[:8]} is not in deliberation"
        )
    if len(record.votes) < len(record.jurors):
        raise ValueError(
            f"Not all jurors have voted: "
            f"{len(record.votes)}/{len(record.jurors)}"
        )

    guilty_count    = sum(1 for v in record.votes if v.vote == TribunalVerdict.GUILTY)
    not_guilty_count = len(record.votes) - guilty_count

    if guilty_count > not_guilty_count:
        verdict = TribunalVerdict.GUILTY
        if sentence == TribunalSentence.ACQUITTAL:
            raise ValueError("A guilty verdict needs a sentence: EXECUTION, TRIBUNAL_DUEL or DISHONOUR")
    else:
        verdict = TribunalVerdict.NOT_GUILTY
        sentence = TribunalSentence.ACQUITTAL   # override — acquittal is automatic on not guilty

    record.verdict        = verdict
    record.sentence       = sentence
    record.verdict_detail = verdict_detail
    record.verdict_ts     = time.time()
    record.status         = TribunalStatus.VERDICT
    record.frank_witness_hash = _frank_seal(record)

    log.info(
        f"Verdict rendered: tribunal={record.tribunal_id[:8]} "
        f"verdict={verdict.value} sentence={sentence.value} "
        f"({guilty_count}G/{not_guilty_count}NG) "
        f"frank_seal={record.frank_witness_hash[:16]}"
    )
    return record


def execute_sentence(
    record:             TribunalRecord,
    frank_world,                            # FrankWorld instance
    accused_card,                           # DraftCard of the accused
    frank_key:          Optional[bytes] = None,  # Frank's own key — needed only for TRIBUNAL_DUEL
    frank=None,
) -> TribunalRecord:
    """
    Execute the sentence Frank has sealed.

    EXECUTION  → frank_world.kill(card, cause="tribunal_execution")
    TRIBUNAL_DUEL → auto-generate an accord of type TRIBUNAL_DUEL;
                    Frank issues it and signs for both sides — the accused
                    cannot refuse a sentence. SIGNED on return.
    DISHONOUR  → jacket dishonour entry (FrankWorld writes it)
    ACQUITTAL  → no action
    """
    if record.status != TribunalStatus.VERDICT:
        raise ValueError(
            f"Tribunal {record.tribunal_id[:8]} has no rendered verdict to execute"
        )
    if record.sentence is None:
        raise ValueError(f"Tribunal {record.tribunal_id[:8]} has no sentence")

    cause = f"tribunal_execution:{record.tribunal_id}"

    if record.sentence == TribunalSentence.EXECUTION:
        frank_world.kill(accused_card, cause=cause)
        log.info(
            f"Sentence executed: EXECUTION — {accused_card.callsign} "
            f"KIA by tribunal {record.tribunal_id[:8]}"
        )

    elif record.sentence == TribunalSentence.TRIBUNAL_DUEL:
        if frank_key is None:
            raise ValueError("TRIBUNAL_DUEL sentence requires Frank's key to issue the accord")
        terms = AccordTerms(
            accord_name   = f"Tribunal Duel — {accused_card.callsign} "
                            f"[tribunal:{record.tribunal_id[:8]}]",
            accord_type   = AccordType.TRIBUNAL_DUEL,
            honor_stake   = True,
            time_limit_hours = 48.0,
            theater       = record.charge.theater,
            observer_allowed = True,
        )
        accord = propose_accord(
            challenger_id   = FRANK_AUTHORITY,
            challenger_card = record.tribunal_id,
            challenger_key  = frank_key,
            defender_id     = record.charge.accused_id,
            defender_card   = record.charge.accused_card,
            terms           = terms,
        )
        accord = countersign_by_authority(
            accord, frank_key, f"tribunal {record.tribunal_id[:8]} sentence",
        )
        record.duel_accord_id = accord.accord_id
        record.duel_accord    = accord
        log.info(
            f"Sentence executed: TRIBUNAL_DUEL accord={accord.accord_id[:8]} "
            f"issued against {accused_card.callsign}"
        )

    elif record.sentence == TribunalSentence.DISHONOUR:
        # Jacket entry is the caller's responsibility via frank_world.jacket()
        log.info(
            f"Sentence executed: DISHONOUR — {accused_card.callsign} "
            f"tribunal {record.tribunal_id[:8]}"
        )

    elif record.sentence == TribunalSentence.ACQUITTAL:
        log.info(
            f"Sentence: ACQUITTAL — {accused_card.callsign} "
            f"tribunal {record.tribunal_id[:8]}"
        )

    record.executed_ts = time.time()
    record.status      = TribunalStatus.EXECUTED

    # Broadcast to Frank bus
    if frank is not None:
        try:
            msg = json.dumps(record.to_dict()).encode()
            frank.bus.write_stage(4, msg)
        except Exception as e:
            log.warning(f"Frank broadcast failed for tribunal {record.tribunal_id[:8]}: {e}")

    return record


# ---------------------------------------------------------------------------
# World history entry
# ---------------------------------------------------------------------------

def world_history_entry(record: TribunalRecord) -> dict:
    """
    Permanent world history entry for a concluded tribunal.
    """
    return {
        "type":           "tribunal",
        "tribunal_id":    record.tribunal_id,
        "accused_id":     record.charge.accused_id,
        "filed_by":       record.charge.filed_by,
        "theater":        record.charge.theater,
        "charges":        record.charge.charges,
        "verdict":        record.verdict.value if record.verdict else None,
        "sentence":       record.sentence.value if record.sentence else None,
        "verdict_detail": record.verdict_detail,
        "duel_accord_id": record.duel_accord_id,
        "frank_seal":     record.frank_witness_hash,
        "verdict_ts":     record.verdict_ts,
        "juror_count":    len(record.jurors),
        "witness_count":  len(record.testimony),
    }
