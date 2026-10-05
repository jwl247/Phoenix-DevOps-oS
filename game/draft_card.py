#!/usr/bin/env python3
"""
draft_card.py — Sacrifice Draft Card System
Phoenix DevOps OS | jwl247 | GPL v3

The draft card is the foundation of a player's identity in Phoenix.
  - Cryptographically signed by their master key.
  - Cannot be faked, bought, or transferred.
  - Issued on enlistment — signed by master key.
  - Contains service record, MOS, rank, and theater assignments.
  - Permanently archived on character death — never deleted.
  - Re-enlistment starts a new card — old card remains public record.

Frank witnesses every issuance. Frank archives every death.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

class CardStatus(str, Enum):
    ACTIVE      = "ACTIVE"       # Enlisted, alive, full access
    WOUNDED     = "WOUNDED"      # Hospital — limited field action
    CRITICAL    = "CRITICAL"     # Extended hospital stay
    KIA         = "KIA"          # Permadeath — card archived forever
    ARCHIVED    = "ARCHIVED"     # Re-enlisted — old card stands, new card issued
    TRAINING    = "TRAINING"     # Still in basic — not yet fielded


# ---------------------------------------------------------------------------
# Draft Card
# ---------------------------------------------------------------------------

@dataclass
class DraftCard:
    """
    A player's cryptographically signed military identity.

    Issued once per enlistment. Archived on death. Public forever.
    """
    card_id:        str                    # UUID4 — globally unique
    player_id:      str                    # master-key derived player identifier
    callsign:       str                    # name the soldier goes by
    enlistment_ts:  float                  # epoch seconds — when issued
    theater:        str                    # starting theater assignment
    status:         CardStatus             = CardStatus.TRAINING

    # MOS and rank are written by the MOS/rank systems after training
    mos_code:       Optional[str]          = None
    rank_code:      Optional[str]          = None

    # Signature over the immutable fields — set at issue time
    signature:      Optional[str]          = None

    # Timestamps for state changes
    fielded_ts:     Optional[float]        = None   # left training
    death_ts:       Optional[float]        = None   # KIA

    # Chain: list of (system, action) that touched this card
    chain:          list                   = field(default_factory=list)

    # -----------------------------------------------------------------------
    # Signing / verification
    # -----------------------------------------------------------------------

    def sign(self, master_key: bytes) -> "DraftCard":
        """
        Sign the card's immutable fields with the player's master key.
        Must be called exactly once at issuance.
        Raises if already signed.
        """
        if self.signature is not None:
            raise ValueError(f"DraftCard {self.card_id} already signed — cannot re-sign")
        payload = self._signable_payload()
        self.signature = hmac.new(master_key, payload, hashlib.sha3_256).hexdigest()
        return self

    def verify(self, master_key: bytes) -> bool:
        """Verify the card's signature. Returns True if untampered."""
        if self.signature is None:
            return False
        payload = self._signable_payload()
        expected = hmac.new(master_key, payload, hashlib.sha3_256).hexdigest()
        return hmac.compare_digest(expected, self.signature)

    def _signable_payload(self) -> bytes:
        """Canonical bytes covering immutable card fields."""
        blob = json.dumps({
            "card_id":       self.card_id,
            "player_id":     self.player_id,
            "callsign":      self.callsign,
            "enlistment_ts": self.enlistment_ts,
            "theater":       self.theater,
        }, sort_keys=True, separators=(",", ":"))
        return blob.encode()

    # -----------------------------------------------------------------------
    # State transitions — each one appends to chain
    # -----------------------------------------------------------------------

    def field(self) -> "DraftCard":
        """Graduate from training to active duty."""
        if self.status != CardStatus.TRAINING:
            raise StateError(f"Cannot field a card in status {self.status}")
        self.status     = CardStatus.ACTIVE
        self.fielded_ts = time.time()
        self._touch("frank_world", "fielded")
        return self

    def wound(self, severity: str) -> "DraftCard":
        """Record a wound. Transitions to WOUNDED or CRITICAL."""
        if self.status not in (CardStatus.ACTIVE, CardStatus.WOUNDED):
            raise StateError(f"Cannot wound a card in status {self.status}")
        self.status = CardStatus.WOUNDED if severity == "wound" else CardStatus.CRITICAL
        self._touch("hospital", f"wounded:{severity}")
        return self

    def recover(self) -> "DraftCard":
        """Discharge from hospital back to active."""
        if self.status not in (CardStatus.WOUNDED, CardStatus.CRITICAL):
            raise StateError(f"Cannot recover from status {self.status}")
        self.status = CardStatus.ACTIVE
        self._touch("hospital", "recovered")
        return self

    def kill(self, cause: str = "combat") -> "DraftCard":
        """
        Permanent death. Once KIA, nothing changes this card again.
        Frank witnesses. Archive must be called to preserve it.
        """
        if self.status == CardStatus.KIA:
            raise StateError("Card already KIA — death is final")
        self.status   = CardStatus.KIA
        self.death_ts = time.time()
        self._touch("frank_world", f"KIA:{cause}")
        return self

    def archive(self) -> "DraftCard":
        """Mark as archived (re-enlistment path). Old card stands."""
        if self.status not in (CardStatus.KIA, CardStatus.ACTIVE):
            raise StateError(f"Cannot archive from status {self.status}")
        prev = self.status.value
        self.status = CardStatus.ARCHIVED
        self._touch("archive", f"archived:was_{prev}")
        return self

    # -----------------------------------------------------------------------
    # Serialisation
    # -----------------------------------------------------------------------

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "DraftCard":
        d = dict(d)
        d["status"] = CardStatus(d["status"])
        return cls(**d)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_json(cls, s: str) -> "DraftCard":
        return cls.from_dict(json.loads(s))

    # -----------------------------------------------------------------------
    # Internal
    # -----------------------------------------------------------------------

    def _touch(self, system: str, action: str) -> None:
        self.chain.append({"ts": time.time(), "system": system, "action": action})


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class StateError(RuntimeError):
    """Illegal state transition on a draft card."""


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def issue_draft_card(
    player_id:  str,
    callsign:   str,
    master_key: bytes,
    theater:    str = "Boot Camp",
) -> DraftCard:
    """
    Issue a new draft card for a player.
    Signs it with their master key. Logs the issuance chain entry.
    Returns the signed card ready to be handed to Frank for witnessing.
    """
    card = DraftCard(
        card_id       = str(uuid.uuid4()),
        player_id     = player_id,
        callsign      = callsign,
        enlistment_ts = time.time(),
        theater       = theater,
        status        = CardStatus.TRAINING,
        chain         = [],
    )
    card.sign(master_key)
    card._touch("enlistment", "issued")
    return card


def load_draft_card(path: Path) -> DraftCard:
    """Load a draft card from disk (JSON)."""
    return DraftCard.from_json(path.read_text(encoding="utf-8"))


def save_draft_card(card: DraftCard, path: Path) -> None:
    """Persist a draft card to disk (atomic write)."""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(card.to_json(), encoding="utf-8")
    tmp.replace(path)


def derive_player_id(master_key: bytes) -> str:
    """
    Derive the player ID from the master key using SHA3-256.
    The player ID is a hex string — 64 chars.
    It does NOT expose the key itself.
    """
    return hashlib.sha3_256(master_key).hexdigest()
