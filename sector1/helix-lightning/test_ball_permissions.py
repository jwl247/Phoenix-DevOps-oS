#!/usr/bin/env python3
"""
Ball permission tests — security audit T3 #8 (authorize wired / honest) + #9
(least privilege by family, not a blanket default).

    python sector1/helix-lightning/test_ball_permissions.py
"""

import os
import sys
import tempfile
from pathlib import Path

# franken5 configures a FileHandler at import time — point it somewhere writable
_tmp = tempfile.mkdtemp(prefix="ball_test_")
os.environ["PHOENIX_AUDIT"] = os.path.join(_tmp, "audit.log")
os.environ["PHOENIX_SHM"] = os.path.join(_tmp, "shm")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from franken5 import Ball, DataFamily, RingRecord, PCS  # noqa: E402

_p = 0
_f = 0


def ok(cond, msg):
    global _p, _f
    if cond:
        _p += 1
        print(f"  ok   {msg}")
    else:
        _f += 1
        print(f"  FAIL {msg}")


NEVER = ("translate", "delete", "kernel")

# ── #9 — least privilege by family ──────────────────────────────────────────
sys_ball = Ball.for_family(DataFamily.SYSTEM)
ok(sys_ball.authorize("read"), "SYSTEM ball can read")
ok(not sys_ball.authorize("write"), "SYSTEM ball cannot write (observer, not author)")
ok(not sys_ball.authorize("clone"), "SYSTEM ball cannot clone")

user_ball = Ball.for_family(DataFamily.USER)
ok(user_ball.authorize("read") and user_ball.authorize("write") and user_ball.authorize("clone"),
   "USER ball can read/write/clone")

ai_ball = Ball.for_family(DataFamily.AI)
ok(ai_ball.authorize("write"), "AI ball can write")

phys_ball = Ball.for_family(DataFamily.PHYSICS)
ok(phys_ball.authorize("read") and phys_ball.authorize("clone") and not phys_ball.authorize("write"),
   "PHYSICS ball: read+clone, no write")

for fam, b in [("SYSTEM", sys_ball), ("USER", user_ball), ("AI", ai_ball), ("PHYSICS", phys_ball)]:
    ok(all(not b.authorize(a) for a in NEVER),
       f"{fam} ball denies translate/delete/kernel by default")

unknown = Ball.for_family("nonsense-family")
ok(unknown.authorize("read") and not unknown.authorize("write") and not unknown.authorize("clone"),
   "unknown family falls back to most-restrictive (read only)")
ok(all(not unknown.authorize(a) for a in NEVER), "unknown family denies the never-set")

# explicit override still wins — this is how the sector-3 translator ring is born
xlator = Ball.for_family(DataFamily.SYSTEM, sector=3,
                         permissions={"read": True, "translate": True})
ok(xlator.authorize("translate"), "explicit permissions override grants translate")
ok(not xlator.authorize("write"), "override is exact — nothing it didn't list")

# ── #8 — authorize() is real + assert_authorized enforces ──────────────────
ok(isinstance(user_ball.authorize("read"), bool), "authorize() returns a bool")

raised = False
try:
    sys_ball.assert_authorized("write", actor="test")
except PermissionError as e:
    raised = "system" in str(e)
ok(raised, "assert_authorized raises PermissionError on a denied action")

try:
    user_ball.assert_authorized("write")
    ok(True, "assert_authorized passes silently on a granted action")
except PermissionError:
    ok(False, "assert_authorized wrongly raised on a granted action")

# ── #8 — franken5's one real enforcement point: call3 snap-clone ───────────
def _definitive_ring(ball):
    r = RingRecord(ring_id=1, process="p", channel=0, ball=ball,
                   pcs=PCS.born(b"seed", ball.zipcode))
    # RingRecord.call3 calls self.pcs.call3(data) internally, which recomputes
    # `definitive` from the probability math — stub it so this test controls it
    def _force(_data):
        r.pcs.definitive = True
        return r.pcs
    r.pcs.call3 = _force
    return r

r_user = _definitive_ring(Ball.for_family(DataFamily.USER))
ok(r_user.call3(b"final") is True, "definitive ring with clone permission -> snap-clone fires")

r_sys = _definitive_ring(Ball.for_family(DataFamily.SYSTEM))
ok(r_sys.call3(b"final") is False, "definitive ring WITHOUT clone permission -> snap-clone suppressed")

# custody chain still recorded even when the clone is suppressed
ok(any(h["to"] == "D1" for h in r_sys.ball.custody), "custody hand-off to D1 recorded regardless")

print(f"\n{_p} passed, {_f} failed")
sys.exit(1 if _f else 0)
