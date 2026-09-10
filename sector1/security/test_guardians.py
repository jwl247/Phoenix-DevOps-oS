#!/usr/bin/env python3
"""
Lifecycle test for the resurrected CoPES guardian layer.
Run:  python -m security.test_guardians       (from sector1/)
  or: python sector1/security/test_guardians.py

Proves: boot arms the rotator; dispatch is safe before boot and on unknown
events; an ACTIVE guardian escalates once its threshold is hit; a HONEYPOT
guardian reports the contact -> forced rotation + escalation sink fires;
every escalation is persisted to the incident log.
"""

import os
import sys
import json
import tempfile
from pathlib import Path

# import as a package whether run as -m or as a file
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# isolate the incident log to a temp file (resolved at write time)
_tmp = tempfile.mkdtemp(prefix="guardian_test_")
_LOG = os.path.join(_tmp, "guardian_incidents.jsonl")
os.environ["PHOENIX_GUARDIAN_LOG"] = _LOG

from security import copes_runtime  # noqa: E402
from security.guardian_rotator import GuardianID  # noqa: E402

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


sink_hits = []

# 1. dispatch is safe and inert before boot()
r = copes_runtime.dispatch({"type": "auth_failure", "source": "pre-boot"})
ok(r.get("status") == "disarmed", "dispatch before boot() -> disarmed, no raise")
ok(copes_runtime.status() == {"armed": False}, "status() reports disarmed")

# 2. boot arms the rotator
rot = copes_runtime.boot(on_escalate=lambda inc: sink_hits.append(inc),
                         min_interval=9999, max_interval=9999)  # keep it from auto-rotating mid-test
st = copes_runtime.status()
ok(st["armed"] is True, "boot() -> armed")
ok(st["active_guardian"] in {g.value for g in GuardianID}, "an active guardian is set")
ok(st["running"] is True, "rotation thread running")
ok(copes_runtime.boot() is rot, "second boot() is a no-op, returns same rotator")

# 3. unknown event type is dropped, not raised
r = copes_runtime.dispatch({"type": "nonsense_event"})
ok(r.get("status") == "unrouted", "unknown event type -> unrouted")
r = copes_runtime.dispatch(None)
ok(r.get("status") in {"unrouted", "error"}, "dispatch(None) does not raise")

# 4. ACTIVE guardian: threshold escalation
for gid, g in rot.guardians.items():
    g.go_honeypot()
rot.guardians[GuardianID.ALPHA].go_active()
rot.active_guardian = GuardianID.ALPHA
sink_hits.clear()

r1 = copes_runtime.dispatch({"type": "auth_failure", "source": "10.0.0.9"})
r2 = copes_runtime.dispatch({"type": "auth_failure", "source": "10.0.0.9"})
ok(r1.get("status") == "ok" and r2.get("status") == "ok", "first two auth failures: ok")
ok(len(sink_hits) == 0, "no escalation before threshold")
r3 = copes_runtime.dispatch({"type": "auth_failure", "source": "10.0.0.9"})
ok(r3.get("status") == "escalate", "3rd auth failure -> escalate")
ok(len(sink_hits) == 1 and sink_hits[0]["type"] == "active_detection",
   "escalation sink fired for active-guardian threshold")
ok(sink_hits[0]["guardian"] == "alpha", "escalation attributed to alpha")

# auth_success resets the counter
copes_runtime.dispatch({"type": "auth_success"})
sink_hits.clear()
for _ in range(2):
    copes_runtime.dispatch({"type": "auth_failure", "source": "x"})
ok(len(sink_hits) == 0, "counter reset by auth_success (no escalation at 2)")

# 5. HONEYPOT guardian: any contact reports -> forced rotation + escalation
for gid, g in rot.guardians.items():
    g.go_honeypot()
rot.active_guardian = GuardianID.GAMMA
rot.guardians[GuardianID.GAMMA].go_active()
rc_before = rot.rotation_count
sink_hits.clear()

r = copes_runtime.dispatch({"type": "integrity_check", "path": "/mnt/g/vault/x",
                            "hash": "deadbeef", "source": "probe-42"})
ok(r.get("detected") is True and r.get("status") == "honeypot",
   "probing a honeypot guardian returns the honeypot marker")
ok(rot.rotation_count > rc_before, "honeypot contact forced a rotation")
ok(len(sink_hits) == 1 and sink_hits[0]["type"] == "honeypot_triggered",
   "escalation sink fired for the honeypot probe")

# 6. every escalation persisted to the incident log
ok(os.path.exists(_LOG), "incident log file created")
lines = [json.loads(x) for x in open(_LOG, encoding="utf-8") if x.strip()]
ok(len(lines) >= 2, f"incident log has the escalations ({len(lines)} rows)")
ok(all("timestamp" in x for x in lines), "every incident row is timestamped")

copes_runtime.stop()
print(f"\n{_p} passed, {_f} failed")
sys.exit(1 if _f else 0)
