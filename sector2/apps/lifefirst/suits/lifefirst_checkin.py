#!/usr/bin/env python3
"""
lifefirst_checkin.py — Life First's first suit.
Phoenix DevOps OS | jwl247 | GPL v3

The phone is Life First's eyes, ears and screen; this suit is the first thing
the brain does with what it hears. A stage addressed to it:

    {"suit": "lifefirst_checkin", "who": "laurie", "type": "checkin",
     "text": "took my morning meds", "lat": 35.87, "lon": -97.42}

What it does, in order:
  1. Validates (who + text required; text <= 4000 chars; type from a fixed set).
  2. Records it — append-only JSONL, every record carrying the SHA3-512 of the
     previous one, so the log is tamper-evident (same idea as the custody
     chain). And stores it in Helix (phoenix_ctx.helix) — her tiers' first real
     data — when the kernel has her running.
  3. Replies through Ollama-local (CLAUDE.md rule 14: local is a real path, not
     a checkbox). If Ollama is down or the model is missing, it still logs and
     says plainly that the reply is not from the AI ("ai": false). Never fakes.

Return value goes out through Helix-E (the spawner's egress bridge) to the phone.

Env:
  LIFEFIRST_HOME   default ~/.phoenix/lifefirst
  LIFEFIRST_MODEL  default llama3.2:3b (the model the road test imported)
  OLLAMA_HOST      default http://127.0.0.1:11434
"""

import hashlib
import json
import os
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

LIFEFIRST_HOME = Path(os.environ.get("LIFEFIRST_HOME", Path.home() / ".phoenix" / "lifefirst"))
LOG_PATH = LIFEFIRST_HOME / "checkins.jsonl"
MODEL = os.environ.get("LIFEFIRST_MODEL", "llama3.2:3b")
OLLAMA = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_TIMEOUT_S = float(os.environ.get("LIFEFIRST_AI_TIMEOUT", "25"))
TYPES = ("checkin", "voice", "note", "location", "photo")
MAX_TEXT = 4000

SYSTEM = (
    "You are Life First, a calm, kind assistant on a phone. The person just checked in. "
    "Reply in one or two short, warm, plain sentences. Acknowledge what they said. "
    "Do not give medical advice, do not invent facts about them, do not ask more than one question."
)

_log_lock = threading.Lock()


def _last_hash() -> str:
    if not LOG_PATH.exists():
        return "0" * 128
    with open(LOG_PATH, "rb") as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        f.seek(max(0, size - 8192))
        tail = f.read().splitlines()
    for line in reversed(tail):
        try:
            return json.loads(line)["hash"]
        except (ValueError, KeyError):
            continue
    return "0" * 128


def _append(record: dict) -> dict:
    """Append with a hash chain: hash = sha3_512(prev_hash + canonical record)."""
    LIFEFIRST_HOME.mkdir(parents=True, exist_ok=True)
    with _log_lock:
        prev = _last_hash()
        body = json.dumps(record, sort_keys=True, separators=(",", ":"))
        h = hashlib.sha3_512((prev + body).encode("utf-8")).hexdigest()
        line = dict(record, prev=prev, hash=h)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(line, sort_keys=True) + "\n")
            f.flush()
            os.fsync(f.fileno())
    return line


def verify_log() -> dict:
    """Walk the chain. Returns {"ok", "records", "broken_at"}."""
    prev, n = "0" * 128, 0
    if not LOG_PATH.exists():
        return {"ok": True, "records": 0, "broken_at": None}
    with open(LOG_PATH, encoding="utf-8") as f:
        for n, raw in enumerate(f, 1):
            rec = json.loads(raw)
            h, p = rec.pop("hash"), rec.pop("prev")
            body = json.dumps(rec, sort_keys=True, separators=(",", ":"))
            if p != prev or hashlib.sha3_512((p + body).encode("utf-8")).hexdigest() != h:
                return {"ok": False, "records": n, "broken_at": n}
            prev = h
    return {"ok": True, "records": n, "broken_at": None}


def _ask_ollama(who: str, kind: str, text: str):
    prompt = f"{who} sent a {kind}: \"{text}\""
    body = json.dumps({"model": MODEL, "system": SYSTEM, "prompt": prompt, "stream": False,
                       "options": {"num_predict": 80, "temperature": 0.4}}).encode()
    req = urllib.request.Request(f"{OLLAMA}/api/generate", data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT_S) as r:
            out = json.loads(r.read())
        reply = (out.get("response") or "").strip()
        return (reply, None) if reply else (None, "empty reply from model")
    except urllib.error.HTTPError as e:
        return None, f"ollama HTTP {e.code} (model {MODEL} missing?)"
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        return None, f"ollama unreachable: {e}"


def run(data, ball=None, pcs=None, **_):
    try:
        msg = json.loads(data)
    except (ValueError, TypeError):
        return json.dumps({"ok": False, "error": "stage is not JSON"})
    if not isinstance(msg, dict):
        return json.dumps({"ok": False, "error": "stage must be a JSON object"})

    who = str(msg.get("who", "")).strip()[:64]
    text = str(msg.get("text", "")).strip()
    kind = str(msg.get("type", "checkin")).strip().lower()
    if not who or not text:
        return json.dumps({"ok": False, "error": "who and text are required"})
    if len(text) > MAX_TEXT:
        return json.dumps({"ok": False, "error": f"text over {MAX_TEXT} chars"})
    if kind not in TYPES:
        return json.dumps({"ok": False, "error": f"type must be one of {', '.join(TYPES)}"})

    now = time.time()
    record = {"ts": round(now, 3), "who": who, "type": kind, "text": text}
    for k in ("lat", "lon"):
        if isinstance(msg.get(k), (int, float)):
            record[k] = msg[k]
    line = _append(record)

    in_helix = False
    try:
        import phoenix_ctx  # set by main_kernel when Helix is running
        if getattr(phoenix_ctx, "helix", None) is not None:
            in_helix = bool(phoenix_ctx.helix.allocate(f"lifefirst:{who}:{line['hash'][:16]}", record))
    except Exception:
        in_helix = False

    reply, why = _ask_ollama(who, kind, text)
    ai = reply is not None
    if not ai:
        reply = f"Got it, {who} — your {kind} is logged at {time.strftime('%H:%M', time.localtime(now))}."

    return json.dumps({"ok": True, "suit": "lifefirst_checkin", "who": who, "type": kind,
                       "reply": reply, "ai": ai, "model": MODEL if ai else None,
                       "ai_error": None if ai else why,
                       "logged": line["hash"][:16], "in_helix": in_helix})


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "verify":
        print(json.dumps(verify_log(), indent=2))
    else:
        print("usage: python lifefirst_checkin.py verify   (walk the check-in hash chain)")
