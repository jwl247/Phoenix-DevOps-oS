#!/usr/bin/env python3
"""
footage.py — The Footage System
Sacrifice | Phoenix DevOps OS | jwl247 | GPL v3

Every significant event is eligible for footage registration.
Top kills per AO are flagged — Frank broadcasts the flag through Helix-E.
Footage clips carry an R2 key (the actual video lives in the clone pool).
Clips appear in jackets and world history.
No footage is ever deleted — the record is permanent.

GDD §6.1 — Footage: Frank-captured moments of heroism and cowardice — both.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

log = logging.getLogger("footage")

# How many top kills we track per AO
TOP_KILL_SLOTS = 10


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class FootageType(Enum):
    KILL                 = "kill"
    HEROISM              = "heroism"       # GDD §6.1 — stayed the five minutes
    COWARDICE            = "cowardice"     # GDD §6.1 — recorded just the same
    ACCORD_CONCLUSION    = "accord_conclusion"
    TRIBUNAL             = "tribunal"
    KING_CROWNED         = "king_crowned"
    DISRUPTOR_ACTIVATION = "disruptor_activation"
    SACRIFICE            = "sacrifice"
    NAMED_GROUND         = "named_ground"


# ---------------------------------------------------------------------------
# FootageClip — one recorded event
# ---------------------------------------------------------------------------

@dataclass
class FootageClip:
    """
    A single footage event. The R2 key points to the actual clip in the clone pool.
    r2_key may be None if the clip has not yet been uploaded (server fills it later).
    """
    clip_id:          str
    footage_type:     FootageType
    ao_id:            str
    theater:          str
    player_id:        str          # primary player in the clip
    callsign:         str
    event_id:         str          # the id of the underlying event (accord_id, tribunal_id, etc.)
    ts:               float = field(default_factory=time.time)

    # R2 storage
    r2_key:           Optional[str]  = None   # clone pool key for the video file
    r2_bucket:        str            = "phoenix-clonepool"   # packages-worker CLONEPOOL_BUCKET

    # Kill-specific
    kill_count_at_time: int          = 0      # confirmed kills in this AO at time of clip
    flagged_top_kill:   bool         = False
    top_kill_rank:      Optional[int] = None  # 1 = highest, up to TOP_KILL_SLOTS

    # Secondary player (victim in a kill clip, etc.)
    secondary_player_id:    Optional[str] = None
    secondary_callsign:     Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "clip_id":               self.clip_id,
            "footage_type":          self.footage_type.value,
            "ao_id":                 self.ao_id,
            "theater":               self.theater,
            "player_id":             self.player_id,
            "callsign":              self.callsign,
            "event_id":              self.event_id,
            "ts":                    self.ts,
            "r2_key":                self.r2_key,
            "r2_bucket":             self.r2_bucket,
            "kill_count_at_time":    self.kill_count_at_time,
            "flagged_top_kill":      self.flagged_top_kill,
            "top_kill_rank":         self.top_kill_rank,
            "secondary_player_id":   self.secondary_player_id,
            "secondary_callsign":    self.secondary_callsign,
        }


# ---------------------------------------------------------------------------
# AO Kill Board — in-memory per AO (production: backed by D1)
# ---------------------------------------------------------------------------

class AOKillBoard:
    """
    Tracks top kill clips per AO. Production version backs this against D1.
    Sorted by kill_count_at_time descending, capped at TOP_KILL_SLOTS.
    """
    def __init__(self, ao_id: str):
        self.ao_id = ao_id
        self._board: list[FootageClip] = []   # sorted, highest first

    def insert(self, clip: FootageClip) -> Optional[int]:
        """
        Try to insert a clip into the top kill board.
        Returns the clip's rank (1-based) if inserted, None if it doesn't make the board.
        """
        if clip.footage_type != FootageType.KILL:
            return None

        # Check if this player already has a higher-kill clip on the board
        existing = next(
            (c for c in self._board if c.player_id == clip.player_id),
            None,
        )
        if existing and existing.kill_count_at_time >= clip.kill_count_at_time:
            return None   # already have a better clip from this player

        # Remove existing lower clip from this player
        if existing:
            existing.flagged_top_kill = False
            existing.top_kill_rank    = None
            self._board = [c for c in self._board if c.player_id != clip.player_id]

        self._board.append(clip)
        # Ties keep the earlier clip ahead — first to reach a count holds the slot.
        self._board.sort(key=lambda c: (-c.kill_count_at_time, c.ts))
        for evicted in self._board[TOP_KILL_SLOTS:]:
            evicted.flagged_top_kill = False
            evicted.top_kill_rank    = None
        self._board = self._board[:TOP_KILL_SLOTS]

        try:
            rank = self._board.index(clip) + 1
        except ValueError:
            return None   # was pushed off the board

        # Update ranks for all clips
        for i, c in enumerate(self._board):
            c.top_kill_rank = i + 1
            c.flagged_top_kill = True

        log.info(
            f"Kill board update: {clip.callsign} rank={rank} "
            f"kills={clip.kill_count_at_time} AO={self.ao_id}"
        )
        return rank

    def top(self, n: int = TOP_KILL_SLOTS) -> list[FootageClip]:
        return self._board[:n]

    def rank_of(self, player_id: str) -> Optional[int]:
        for i, c in enumerate(self._board):
            if c.player_id == player_id:
                return i + 1
        return None


# Module-level kill boards keyed by ao_id (production: backed by D1)
_boards: dict[str, AOKillBoard] = {}


def _get_board(ao_id: str) -> AOKillBoard:
    if ao_id not in _boards:
        _boards[ao_id] = AOKillBoard(ao_id)
    return _boards[ao_id]


# ---------------------------------------------------------------------------
# Core operations
# ---------------------------------------------------------------------------

def record_footage(
    footage_type:        FootageType,
    ao_id:               str,
    theater:             str,
    player_id:           str,
    callsign:            str,
    event_id:            str,
    r2_key:              Optional[str] = None,
    kill_count_at_time:  int           = 0,
    secondary_player_id: Optional[str] = None,
    secondary_callsign:  Optional[str] = None,
) -> FootageClip:
    """
    Register a footage clip. The clip is addressable by clip_id.
    r2_key may be None if the video is not yet uploaded — set it later via set_r2_key().
    """
    if kill_count_at_time < 0:
        raise ValueError("kill_count_at_time cannot be negative")
    clip = FootageClip(
        clip_id             = str(uuid.uuid4()),
        footage_type        = footage_type,
        ao_id               = ao_id,
        theater             = theater,
        player_id           = player_id,
        callsign            = callsign,
        event_id            = event_id,
        r2_key              = r2_key,
        kill_count_at_time  = kill_count_at_time,
        secondary_player_id = secondary_player_id,
        secondary_callsign  = secondary_callsign,
    )
    log.info(
        f"Footage registered: {footage_type.value} clip={clip.clip_id[:8]} "
        f"player={callsign} AO={ao_id}"
    )
    return clip


def set_r2_key(clip: FootageClip, r2_key: str) -> FootageClip:
    """Set the R2 storage key once the video has been uploaded to the clone pool."""
    if clip.r2_key is not None:
        raise ValueError(
            f"Clip {clip.clip_id[:8]} already has an R2 key; use a new clip for a new upload"
        )
    clip.r2_key = r2_key
    log.info(f"R2 key set for clip {clip.clip_id[:8]}: {r2_key}")
    return clip


def try_flag_top_kill(
    clip:  FootageClip,
    frank=None,
    board: Optional[AOKillBoard] = None,
) -> FootageClip:
    """
    Attempt to flag a KILL clip as a top-N kill in the AO.
    If it makes the kill board, clip.flagged_top_kill is set and Frank broadcasts.
    Safe to call on any clip type — non-KILL clips are a no-op.
    board: the caller's own board for this AO (FrankWorld keeps one per world);
    defaults to the module-level board.
    """
    if clip.footage_type != FootageType.KILL:
        return clip
    if board is not None and board.ao_id != clip.ao_id:
        raise ValueError(f"Board is for AO {board.ao_id}, clip is in {clip.ao_id}")

    board = board or _get_board(clip.ao_id)
    rank  = board.insert(clip)

    if rank is not None:
        clip.flagged_top_kill = True
        clip.top_kill_rank    = rank

        log.info(
            f"Top kill flagged: {clip.callsign} rank={rank} "
            f"kills={clip.kill_count_at_time} AO={clip.ao_id}"
        )

        if frank is not None:
            try:
                msg = json.dumps({
                    "event":    "top_kill_flagged",
                    "clip_id":  clip.clip_id,
                    "ao_id":    clip.ao_id,
                    "player_id": clip.player_id,
                    "callsign": clip.callsign,
                    "rank":     rank,
                    "kills":    clip.kill_count_at_time,
                    "ts":       clip.ts,
                }).encode()
                frank.bus.write_stage(4, msg)
            except Exception as e:
                log.warning(f"Frank broadcast failed (top_kill {clip.clip_id[:8]}): {e}")

    return clip


def get_top_kills(ao_id: str, n: int = TOP_KILL_SLOTS) -> list[FootageClip]:
    """Return the top N kill clips for an AO, ranked highest first."""
    return _get_board(ao_id).top(n)


def kill_rank(ao_id: str, player_id: str) -> Optional[int]:
    """Return the current kill board rank for a player in an AO, or None if not on the board."""
    return _get_board(ao_id).rank_of(player_id)


# ---------------------------------------------------------------------------
# Jacket and world history entries
# ---------------------------------------------------------------------------

def jacket_entry(clip: FootageClip) -> dict:
    """
    Format a footage clip for insertion into a player's jacket.
    Used by frank_world when recording events that have footage.
    """
    label = clip.footage_type.value.replace("_", " ").title()
    if clip.flagged_top_kill and clip.top_kill_rank:
        label = f"Top Kill #{clip.top_kill_rank} in {clip.ao_id}"

    return {
        "type":        "footage",
        "clip_id":     clip.clip_id,
        "label":       label,
        "ao_id":       clip.ao_id,
        "theater":     clip.theater,
        "event_id":    clip.event_id,
        "r2_key":      clip.r2_key,
        "r2_bucket":   clip.r2_bucket,
        "ts":          clip.ts,
        "top_kill":    clip.flagged_top_kill,
        "kill_rank":   clip.top_kill_rank,
    }


def world_history_entry(clip: FootageClip) -> dict:
    """
    Permanent world history entry for a flagged footage clip.
    Non-top-kill clips are logged but are not surfaced in public world history.
    """
    return {
        "type":                  "footage",
        "clip_id":               clip.clip_id,
        "footage_type":          clip.footage_type.value,
        "ao_id":                 clip.ao_id,
        "theater":               clip.theater,
        "player_id":             clip.player_id,
        "callsign":              clip.callsign,
        "event_id":              clip.event_id,
        "r2_key":                clip.r2_key,
        "ts":                    clip.ts,
        "flagged_top_kill":      clip.flagged_top_kill,
        "top_kill_rank":         clip.top_kill_rank,
        "kill_count_at_time":    clip.kill_count_at_time,
        "secondary_player_id":   clip.secondary_player_id,
        "secondary_callsign":    clip.secondary_callsign,
    }
