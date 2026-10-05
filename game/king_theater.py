#!/usr/bin/env python3
"""
king_theater.py — The King of Theater System
Sacrifice | Phoenix DevOps OS | jwl247 | GPL v3

The King of Theater holds an Area of Operations.
Holding the AO earns the King control over that AO's spawn rules.
Any player may challenge the King — Frank auto-generates a KING_THEATER accord.
A King who BOUGHT the crown automatically owes the world one free disruptor
(GDD §7.2 — "every dollar spent spawns a counter"); the purchase is disclosed
in every KING_THEATER accord's pay_advantages.
The disruptor token can break any accord in the AO — once, permanently consumed;
the same player never holds it twice in one reign.
Frank witnesses every crowning, challenge, and disruptor activation.
World history records everything.

GDD §7.2 — King of the Theater
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
    Accord, AccordTerms, AccordType, AccordOutcome, AccordStatus,
    propose_accord, countersign_by_authority,
    activate_accord, conclude_accord,
)

log = logging.getLogger("king_theater")


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class KingEvent(Enum):
    CROWNED       = "crowned"
    DETHRONED     = "dethroned"
    CHALLENGED    = "challenged"
    CHALLENGE_WON = "challenge_won"       # King defended
    CHALLENGE_LOST = "challenge_lost"     # King lost; challenger crowned
    DISRUPTOR_GRANTED  = "disruptor_granted"
    DISRUPTOR_USED     = "disruptor_used"
    DISRUPTOR_EXPIRED  = "disruptor_expired"
    SPAWN_RULES        = "spawn_rules"


# ---------------------------------------------------------------------------
# KingTheaterState — one per AO
# ---------------------------------------------------------------------------

@dataclass
class KingTheaterState:
    """
    Live state for one Area of Operations.
    One King, one optional pending Challenger, one optional Disruptor.
    Frank witnesses all transitions.
    """
    ao_id:          str
    theater:        str

    # Current King
    king_id:        Optional[str]  = None
    king_card:      Optional[str]  = None   # card_id
    king_callsign:  Optional[str]  = None
    crowned_ts:     Optional[float] = None
    paid_crown:     bool            = False   # bought the crown — disclosed, owes a disruptor

    # Active challenge
    challenger_id:     Optional[str]  = None
    challenger_card:   Optional[str]  = None
    challenger_callsign: Optional[str] = None
    challenge_accord_id: Optional[str] = None
    challenge_ts:      Optional[float] = None

    # Disruptor
    disruptor_id:          Optional[str]  = None
    disruptor_card:        Optional[str]  = None
    disruptor_callsign:    Optional[str]  = None
    disruptor_granted_ts:  Optional[float] = None
    disruptor_token_used:  bool           = False
    disruptor_used_ts:     Optional[float] = None
    disruptor_broke_accord: Optional[str] = None   # accord_id that was broken
    disruptor_owed:        bool           = False  # paid crown → one free disruptor due
    reign_disruptors:      list           = field(default_factory=list)  # player_ids this reign

    # AO spawn rules — King sets these; None = defaults apply
    spawn_rules:    dict = field(default_factory=dict)

    # Frank seal for the last state transition
    frank_witness_hash: Optional[str] = None
    sealed_ts:          Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "ao_id":                  self.ao_id,
            "theater":                self.theater,
            "king_id":                self.king_id,
            "king_card":              self.king_card,
            "king_callsign":          self.king_callsign,
            "crowned_ts":             self.crowned_ts,
            "paid_crown":             self.paid_crown,
            "challenger_id":          self.challenger_id,
            "challenger_card":        self.challenger_card,
            "challenger_callsign":    self.challenger_callsign,
            "challenge_accord_id":    self.challenge_accord_id,
            "challenge_ts":           self.challenge_ts,
            "disruptor_id":           self.disruptor_id,
            "disruptor_card":         self.disruptor_card,
            "disruptor_callsign":     self.disruptor_callsign,
            "disruptor_granted_ts":   self.disruptor_granted_ts,
            "disruptor_token_used":   self.disruptor_token_used,
            "disruptor_used_ts":      self.disruptor_used_ts,
            "disruptor_broke_accord": self.disruptor_broke_accord,
            "disruptor_owed":         self.disruptor_owed,
            "reign_disruptors":       self.reign_disruptors,
            "spawn_rules":            self.spawn_rules,
            "frank_witness_hash":     self.frank_witness_hash,
            "sealed_ts":              self.sealed_ts,
        }


# ---------------------------------------------------------------------------
# Frank seal
# ---------------------------------------------------------------------------

def _frank_seal(state: KingTheaterState, event: KingEvent) -> str:
    """
    SHA3-512 over the whole AO state + event. The seal time is stored on the
    state, so anyone can recompute the seal from the published record.
    """
    state.sealed_ts = time.time()
    return seal_of(state, event)


def seal_of(state: KingTheaterState, event: KingEvent) -> str:
    """Recompute the seal for a published state (verification)."""
    body = state.to_dict()
    body.pop("frank_witness_hash")
    blob = json.dumps({"event": event.value, **body}, sort_keys=True).encode()
    return hashlib.sha3_512(blob).hexdigest()


def _broadcast(frank, event: KingEvent, state: KingTheaterState) -> None:
    if frank is None:
        return
    try:
        msg = json.dumps({"event": event.value, **state.to_dict()}).encode()
        frank.bus.write_stage(4, msg)
    except Exception as e:
        log.warning(f"Frank broadcast failed ({event.value} {state.ao_id}): {e}")


# ---------------------------------------------------------------------------
# Core operations
# ---------------------------------------------------------------------------

def crown_king(
    ao_id:      str,
    theater:    str,
    player_id:  str,
    card_id:    str,
    callsign:   str,
    spawn_rules: Optional[dict] = None,
    paid:       bool = False,
    frank=None,
) -> KingTheaterState:
    """
    Crown a player as King of this AO (first claim).
    paid=True: the crown was bought — the world is owed one free disruptor.
    Frank witnesses.
    """
    state = KingTheaterState(
        ao_id         = ao_id,
        theater       = theater,
        king_id       = player_id,
        king_card     = card_id,
        king_callsign = callsign,
        crowned_ts    = time.time(),
        spawn_rules   = spawn_rules or {},
        paid_crown    = paid,
        disruptor_owed = paid,
    )
    state.frank_witness_hash = _frank_seal(state, KingEvent.CROWNED)

    log.info(f"King crowned: {callsign} holds AO={ao_id} paid={paid} "
             f"seal={state.frank_witness_hash[:16]}")
    _broadcast(frank, KingEvent.CROWNED, state)
    return state


def challenge_king(
    state:              KingTheaterState,
    challenger_id:      str,
    challenger_card:    str,
    challenger_callsign: str,
    challenger_key:     bytes,
    frank_key:          bytes,
    territory_stake:    Optional[str] = None,
    frank=None,
) -> tuple[KingTheaterState, Accord]:
    """
    A player challenges the King of the AO.
    Frank auto-generates a KING_THEATER accord between challenger and King.
    The accord is PROPOSED by the challenger and immediately countersigned
    by Frank under his own authority (the King cannot refuse a challenge —
    that is the law). Frank never holds the King's key.

    Returns the updated state and the generated accord (ACTIVE status).
    """
    if state.king_id is None:
        raise ValueError(f"AO {state.ao_id} has no King to challenge — use crown_king first")
    if state.challenge_accord_id is not None:
        raise ValueError(
            f"AO {state.ao_id} already has an active challenge "
            f"(accord {state.challenge_accord_id[:8]})"
        )
    if challenger_id == state.king_id:
        raise ValueError("The King cannot challenge themselves")

    terms = AccordTerms(
        accord_name     = (
            f"{challenger_callsign} challenges {state.king_callsign} "
            f"for King of {state.ao_id}"
        ),
        accord_type     = AccordType.KING_THEATER,
        territory_stake = territory_stake or state.ao_id,
        honor_stake     = True,
        time_limit_hours = 48.0,
        theater         = state.theater,
        observer_allowed = True,
        pay_advantages_disclosed = (
            {"king_of_theater": "crown purchased — free disruptor owed"}
            if state.paid_crown else {}
        ),
    )

    # Challenger proposes
    accord = propose_accord(
        challenger_id   = challenger_id,
        challenger_card = challenger_card,
        challenger_key  = challenger_key,
        defender_id     = state.king_id,
        defender_card   = state.king_card,
        terms           = terms,
    )

    # King cannot refuse — Frank countersigns under his own authority
    accord = countersign_by_authority(accord, frank_key, f"King of {state.ao_id} challenged")

    # Activate immediately — the battle is live
    accord = activate_accord(accord)

    state.challenger_id          = challenger_id
    state.challenger_card        = challenger_card
    state.challenger_callsign    = challenger_callsign
    state.challenge_accord_id    = accord.accord_id
    state.challenge_ts           = time.time()
    state.frank_witness_hash     = _frank_seal(state, KingEvent.CHALLENGED)

    log.info(
        f"Challenge issued: {challenger_callsign} vs {state.king_callsign} "
        f"AO={state.ao_id} accord={accord.accord_id[:8]}"
    )
    _broadcast(frank, KingEvent.CHALLENGED, state)

    return state, accord


def conclude_challenge(
    state:           KingTheaterState,
    accord:          Accord,
    outcome:         AccordOutcome,
    detail:          str = "",
    new_spawn_rules: Optional[dict] = None,
    frank=None,
) -> KingTheaterState:
    """
    Conclude a King of Theater challenge.

    CHALLENGER_VICTORY → challenger becomes King
    DEFENDER_VICTORY   → King retains; challenger loses honour stake
    Any forfeit        → forfeiting party loses; other retains/gains King
    DRAW / DISRUPTED   → King retains (the challenger did not take the AO)
    """
    if accord.accord_id != state.challenge_accord_id:
        raise ValueError(f"Accord {accord.accord_id[:8]} is not the open challenge for AO {state.ao_id}")
    if accord.status != AccordStatus.CONCLUDED:
        accord = conclude_accord(accord, outcome, detail, frank)
    outcome = accord.outcome   # expiry may have converted it

    challenger_won = outcome in (
        AccordOutcome.CHALLENGER_VICTORY,
        AccordOutcome.FORFEIT_DEFENDER,
    )

    old_king = state.king_callsign

    if challenger_won:
        # Challenger is now King
        state.king_id           = state.challenger_id
        state.king_card         = state.challenger_card
        state.king_callsign     = state.challenger_callsign
        state.crowned_ts        = time.time()
        state.spawn_rules       = new_spawn_rules or {}
        state.paid_crown        = False      # won by arms, not bought
        state.reign_disruptors  = []         # new reign, new disruptor cycle
        event = KingEvent.CHALLENGE_LOST
        log.info(
            f"King dethroned: {old_king} → new King: {state.king_callsign} "
            f"AO={state.ao_id}"
        )
    else:
        event = KingEvent.CHALLENGE_WON
        log.info(
            f"King defended: {state.king_callsign} holds AO={state.ao_id}"
        )

    # Clear challenge
    state.challenger_id          = None
    state.challenger_card        = None
    state.challenger_callsign    = None
    state.challenge_accord_id    = None
    state.challenge_ts           = None
    state.frank_witness_hash     = _frank_seal(state, event)
    _broadcast(frank, event, state)
    return state


def grant_disruptor(
    state:       KingTheaterState,
    player_id:   str,
    card_id:     str,
    callsign:    str,
    frank=None,
) -> KingTheaterState:
    """
    Grant the disruptor token to a player.
    The disruptor earns this — the server layer validates eligibility.
    Only one disruptor per AO at a time.
    Token is consumed on use and never reissued to the same player in this AO cycle.
    """
    if state.disruptor_id is not None and not state.disruptor_token_used:
        raise ValueError(
            f"AO {state.ao_id} already has an active disruptor: {state.disruptor_callsign}"
        )
    if player_id == state.king_id:
        raise ValueError("The King cannot hold the disruptor token in their own AO")
    if player_id in state.reign_disruptors:
        raise ValueError(f"Player {player_id[:8]} already held the disruptor token this reign")

    state.disruptor_id         = player_id
    state.disruptor_card       = card_id
    state.disruptor_callsign   = callsign
    state.disruptor_granted_ts = time.time()
    state.disruptor_token_used = False
    state.disruptor_used_ts    = None
    state.disruptor_broke_accord = None
    state.disruptor_owed       = False
    state.reign_disruptors.append(player_id)
    state.frank_witness_hash   = _frank_seal(state, KingEvent.DISRUPTOR_GRANTED)

    log.info(f"Disruptor granted: {callsign} in AO={state.ao_id}")
    _broadcast(frank, KingEvent.DISRUPTOR_GRANTED, state)
    return state


def use_disruptor(
    state:            KingTheaterState,
    player_id:        str,
    target:           Accord,
    frank=None,
) -> KingTheaterState:
    """
    The disruptor breaks a SIGNED or ACTIVE accord fought in this AO.
    One use only — token is permanently consumed.
    The accord concludes DISRUPTED (no victor); the disruptor is named in
    world history. Breaking the King's open challenge leaves the King standing.
    """
    if state.disruptor_id != player_id:
        raise ValueError(
            f"Player {player_id[:8]} does not hold the disruptor token for AO {state.ao_id}"
        )
    if state.disruptor_token_used:
        raise ValueError(
            f"Disruptor token for AO {state.ao_id} has already been used"
        )
    if target.status not in (AccordStatus.SIGNED, AccordStatus.ACTIVE):
        raise ValueError(f"Accord {target.accord_id[:8]} is not live — nothing to break")
    if state.ao_id != target.terms.territory_stake and state.theater != target.terms.theater:
        raise ValueError(f"Accord {target.accord_id[:8]} is not fought in AO {state.ao_id}")

    conclude_accord(
        target, AccordOutcome.DISRUPTED,
        f"Broken by disruptor {state.disruptor_callsign}", frank,
    )
    if target.accord_id == state.challenge_accord_id:
        state.challenger_id = state.challenger_card = state.challenger_callsign = None
        state.challenge_accord_id = None
        state.challenge_ts = None

    state.disruptor_token_used   = True
    state.disruptor_used_ts      = time.time()
    state.disruptor_broke_accord = target.accord_id
    state.frank_witness_hash     = _frank_seal(state, KingEvent.DISRUPTOR_USED)

    log.info(
        f"Disruptor used: {state.disruptor_callsign} broke accord={target.accord_id[:8]} "
        f"in AO={state.ao_id}"
    )
    _broadcast(frank, KingEvent.DISRUPTOR_USED, state)
    return state


def dethrone(
    state:  KingTheaterState,
    reason: str,
    frank=None,
) -> KingTheaterState:
    """
    The King falls without a challenger taking the AO (KIA, tribunal execution).
    The throne stands empty until the next crown_king. An open challenge must
    be concluded first — the challenger's claim is decided by that accord.
    """
    if state.king_id is None:
        raise ValueError(f"AO {state.ao_id} has no King to dethrone")
    if state.challenge_accord_id is not None:
        raise ValueError(f"AO {state.ao_id} has an open challenge — conclude it first")
    log.info(f"King dethroned: {state.king_callsign} AO={state.ao_id} — {reason}")
    state.king_id = state.king_card = state.king_callsign = None
    state.crowned_ts = None
    state.paid_crown = False
    state.disruptor_owed = False
    state.spawn_rules = {}
    state.reign_disruptors = []
    state.frank_witness_hash = _frank_seal(state, KingEvent.DETHRONED)
    _broadcast(frank, KingEvent.DETHRONED, state)
    return state


def expire_disruptor(state: KingTheaterState, reason: str, frank=None) -> KingTheaterState:
    """An unused disruptor token dies with its holder — consumed, never used."""
    if state.disruptor_id is None or state.disruptor_token_used:
        raise ValueError(f"AO {state.ao_id} has no live disruptor token")
    state.disruptor_token_used = True
    state.disruptor_used_ts    = time.time()
    state.frank_witness_hash   = _frank_seal(state, KingEvent.DISRUPTOR_EXPIRED)
    log.info(f"Disruptor expired: {state.disruptor_callsign} AO={state.ao_id} — {reason}")
    _broadcast(frank, KingEvent.DISRUPTOR_EXPIRED, state)
    return state


def set_spawn_rules(
    state:       KingTheaterState,
    player_id:   str,
    spawn_rules: dict,
) -> KingTheaterState:
    """
    The King sets spawn rules for their AO.
    Only the current King may call this.
    """
    if state.king_id != player_id:
        raise ValueError(
            f"Player {player_id[:8]} is not the King of AO {state.ao_id}"
        )
    state.spawn_rules = dict(spawn_rules)
    state.frank_witness_hash = _frank_seal(state, KingEvent.SPAWN_RULES)
    log.info(f"Spawn rules updated by {state.king_callsign} for AO={state.ao_id}")
    return state


# ---------------------------------------------------------------------------
# World history entries
# ---------------------------------------------------------------------------

def world_history_entry(state: KingTheaterState, event: KingEvent) -> dict:
    """
    Permanent world history entry for a King of Theater event.
    """
    return {
        "type":                   "king_theater",
        "event":                  event.value,
        "ao_id":                  state.ao_id,
        "theater":                state.theater,
        "king_id":                state.king_id,
        "king_callsign":          state.king_callsign,
        "crowned_ts":             state.crowned_ts,
        "paid_crown":             state.paid_crown,
        "challenger_id":          state.challenger_id,
        "challenger_callsign":    state.challenger_callsign,
        "disruptor_id":           state.disruptor_id,
        "disruptor_callsign":     state.disruptor_callsign,
        "disruptor_broke_accord": state.disruptor_broke_accord,
        "frank_seal":             state.frank_witness_hash,
    }
