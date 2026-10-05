#!/usr/bin/env python3
"""
world_history.py — The permanent world record
Sacrifice | Phoenix DevOps OS | jwl247 | GPL v3

GDD §11.2 — "Frank maintains a permanent, public, chronological record of
world events ... accessible to any player at any time."
GDD §11.4 — nothing is ever deleted, nothing is ever erased.

Built like Phoenix's custody chain:
  - append-only, numbered (seq 1, 2, 3 …)
  - each entry carries the previous entry's hash; its own hash is
    SHA3-512 over its exact canonical bytes — alter, drop or reorder one
    entry and every later hash stops matching
  - written to a local JSONL file first (flushed + fsynced), so the world
    survives restarts and works offline; then synced to D1 through the
    sacrifice-worker, which re-checks the chain before accepting a row.

The canonical bytes travel with the hash, so the worker never has to
re-serialise JSON in another language to check it.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
import urllib.request
from pathlib import Path
from typing import Iterable, Optional

log = logging.getLogger("world_history")

GENESIS = "0" * 128
USER_AGENT = "phoenix-sacrifice/1.0"   # Cloudflare 403s Python's default UA


def canonical(body: dict) -> str:
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def entry_hash(canon: str) -> str:
    return hashlib.sha3_512(canon.encode("utf-8")).hexdigest()


class ChainBroken(RuntimeError):
    pass


class WorldHistory:
    """
    The record. `path=None` keeps it in memory only (tests, tools); a path
    makes it durable — the file is re-read and re-verified on open.
    """

    def __init__(self, path: Optional[Path] = None, fsync: bool = True):
        self.path  = Path(path) if path else None
        self.fsync = fsync
        self._rows: list[tuple[str, str]] = []     # (canonical, hash)
        self._bodies: list[dict] = []
        if self.path and self.path.exists():
            self._load()

    # -- write ---------------------------------------------------------------

    def append(self, entry: dict) -> dict:
        if "type" not in entry:
            raise ValueError("Every history entry needs a type")
        body = {**entry,
                "seq": len(self._rows) + 1,
                "prev_hash": self.head,
                "recorded_ts": entry.get("recorded_ts", time.time())}
        canon = canonical(body)
        h = entry_hash(canon)
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8", newline="\n") as f:
                f.write(json.dumps({"c": canon, "h": h}, ensure_ascii=False) + "\n")
                f.flush()
                if self.fsync:
                    os.fsync(f.fileno())
        self._rows.append((canon, h))
        parsed = json.loads(canon)
        parsed["entry_hash"] = h
        self._bodies.append(parsed)
        return dict(parsed)

    # -- read ----------------------------------------------------------------

    @property
    def head(self) -> str:
        return self._rows[-1][1] if self._rows else GENESIS

    def __len__(self) -> int:
        return len(self._rows)

    def entries(self) -> list[dict]:
        return [dict(b) for b in self._bodies]

    def query(
        self,
        type:      Optional[str] = None,
        theater:   Optional[str] = None,
        player_id: Optional[str] = None,
        since_seq: int = 0,
        limit:     Optional[int] = None,
    ) -> list[dict]:
        out = []
        for b in self._bodies:
            if b["seq"] <= since_seq:
                continue
            if type and b.get("type") != type:
                continue
            if theater and b.get("theater") != theater:
                continue
            if player_id and player_id not in json.dumps(b):
                continue
            out.append(dict(b))
            if limit and len(out) >= limit:
                break
        return out

    def rows(self, since_seq: int = 0) -> list[dict]:
        """Wire form for D1 sync: the exact bytes plus their hash."""
        return [{"seq": i + 1, "canonical": c, "entry_hash": h}
                for i, (c, h) in enumerate(self._rows) if i + 1 > since_seq]

    # -- verify --------------------------------------------------------------

    def verify(self) -> int:
        """Walk the chain. Returns the length; raises ChainBroken at the first bad link."""
        prev = GENESIS
        for i, (canon, h) in enumerate(self._rows, start=1):
            if entry_hash(canon) != h:
                raise ChainBroken(f"Entry {i}: hash does not match its bytes")
            body = json.loads(canon)
            if body.get("seq") != i:
                raise ChainBroken(f"Entry {i}: out of order (seq {body.get('seq')})")
            if body.get("prev_hash") != prev:
                raise ChainBroken(f"Entry {i}: does not follow entry {i - 1}")
            prev = h
        return len(self._rows)

    def _load(self) -> None:
        with open(self.path, encoding="utf-8") as f:
            for n, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    self._rows.append((rec["c"], rec["h"]))
                except (ValueError, KeyError) as e:
                    raise ChainBroken(f"{self.path} line {n} is not a history row: {e}") from e
        self.verify()
        for canon, h in self._rows:
            b = json.loads(canon)
            b["entry_hash"] = h
            self._bodies.append(b)
        log.info(f"World history loaded: {len(self._rows)} entries, chain verified")

    # -- D1 sync -------------------------------------------------------------

    def _cursor_path(self) -> Optional[Path]:
        return self.path.with_suffix(self.path.suffix + ".d1cursor") if self.path else None

    def synced_through(self) -> int:
        p = self._cursor_path()
        return int(p.read_text().strip() or 0) if p and p.exists() else 0

    def sync(self, client: "HistoryClient", batch: int = 100) -> int:
        """Push everything D1 has not acknowledged. Returns the acknowledged seq."""
        acked = self.synced_through()
        while acked < len(self._rows):
            chunk = self.rows(acked)[:batch]
            acked = client.push(chunk)
            p = self._cursor_path()
            if p:
                p.write_text(str(acked))
            if acked < chunk[-1]["seq"]:
                raise RuntimeError(f"Worker acknowledged only through seq {acked}")
        return acked


class HistoryClient:
    """POSTs history rows to the sacrifice-worker. Credentials from the environment only."""

    def __init__(self, base_url: Optional[str] = None, token: Optional[str] = None, timeout: int = 30):
        self.base_url = (base_url or os.environ.get("SACRIFICE_WORKER_URL", "")).rstrip("/")
        self.token    = token or os.environ.get("SACRIFICE_FRANK_TOKEN", "")
        self.timeout  = timeout
        if not self.base_url or not self.token:
            raise RuntimeError("SACRIFICE_WORKER_URL and SACRIFICE_FRANK_TOKEN must be set")

    def push(self, rows: Iterable[dict]) -> int:
        data = json.dumps({"entries": list(rows)}).encode("utf-8")
        req = urllib.request.Request(self.base_url + "/history", data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {self.token}")
        req.add_header("User-Agent", USER_AGENT)
        cid, csec = os.environ.get("CF_ACCESS_CLIENT_ID"), os.environ.get("CF_ACCESS_CLIENT_SECRET")
        if cid and csec:
            req.add_header("CF-Access-Client-Id", cid)
            req.add_header("CF-Access-Client-Secret", csec)
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return int(json.loads(r.read())["accepted_through"])


def default_history_path() -> Path:
    explicit = os.environ.get("PHOENIX_WORLD_HISTORY")
    if explicit:
        return Path(explicit)
    archive = Path(os.environ.get("PHOENIX_ARCHIVE_ROOT", "/var/lib/phoenix/archive"))
    return archive.parent / "world_history.jsonl"
