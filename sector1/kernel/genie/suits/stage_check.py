#!/usr/bin/env python3
"""
stage_check.py — proves the stage path on a machine: Helix-I in -> suit -> Helix-E out.
Phoenix DevOps OS | jwl247 | GPL v3

Also the smallest correct suit, so it doubles as the template for writing one.

    genie import stage_check.py
    genie send stage_check '{"text": "hello"}'

The contract every Python suit keeps:
  run(data, ball=None, pcs=None, **_)
    data  the stage as bytes, exactly what was sent into Helix-I (JSON here)
    ball  Frank's ball for this run (family/slot) — may be None
    pcs   the ring's PCS record — may be None
  return  a JSON string (or bytes). Put "suit": "<this suit's name>" in it —
          that is how `genie send` (and the phone) pick its answer out of the
          Helix-E stream. Never raise: return {"ok": false, "error": ...}.
"""

import json
import platform
import time

NAME = "stage_check"


def run(data, ball=None, pcs=None, **_):
    try:
        msg = json.loads(data)
    except (ValueError, TypeError):
        return json.dumps({"ok": False, "suit": NAME, "error": "stage is not JSON"})
    if not isinstance(msg, dict):
        return json.dumps({"ok": False, "suit": NAME, "error": "stage must be a JSON object"})
    return json.dumps({
        "ok": True,
        "suit": NAME,
        "echo": msg.get("text"),
        "host": platform.node(),
        "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "ball": None if ball is None else str(getattr(ball, "family", ball)),
    })


if __name__ == "__main__":       # local check without the kernel: python stage_check.py '{"text":"hi"}'
    import sys
    print(run(sys.argv[1] if len(sys.argv) > 1 else '{"text": "local"}'))
