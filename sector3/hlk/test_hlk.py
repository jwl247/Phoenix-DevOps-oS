#!/usr/bin/env python3
"""test_hlk.py — H.L.K's own logic, with intake/dmsetup/worker stood in:
tiers (push asks, no = nothing ran), pull swap-in safety, name safety, the
shared index, status parsing + hit-rate deltas, HTTP token gate.
Run: python3 test_hlk.py   (exit 0 = all passing). The live test is on the box."""
import json
import os
import sys
import tempfile
import threading
import urllib.error
import urllib.request

T = tempfile.mkdtemp(prefix="hlk-test-")
os.environ.update(HLK_STATE=os.path.join(T, "state"), HLK_CRED=os.path.join(T, "cred"),
                  HLK_WORKDIR=os.path.join(T, "work"), HLK_EGRESS=os.path.join(T, "egress"))
for d in ("state", "cred", "work/ops", "work/bin"):
    os.makedirs(os.path.join(T, d), exist_ok=True)
for n, v in (("url", "http://phoenix.invalid"), ("auth", "k")):
    open(os.path.join(T, "cred", n), "w").write(v)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hlk  # noqa: E402

passed = failed = 0


def check(name, cond):
    global passed, failed
    print(("  ok    " if cond else "  FAIL  ") + name)
    passed, failed = passed + (1 if cond else 0), failed + (0 if cond else 1)


# ── stand-ins ────────────────────────────────────────────────────────────
intake_calls = []
META = {}


def fake_intake(args, cwd):
    intake_calls.append(args)
    if args[0] == "clone":
        name = args[1]
        if name == "broken":
            return 1, "MISS"
        if name == "tree":
            os.makedirs(os.path.join(cwd, "tree", "sub"))
            open(os.path.join(cwd, "tree", "a.py"), "w").write("a")
            open(os.path.join(cwd, "tree", "sub", "b.sh"), "w").write("bb")
        else:
            open(os.path.join(cwd, name), "w").write("content of " + name)
        return 0, "ok"
    path = args[0]                                  # a push: intake <file>
    META[os.path.basename(path)] = {"hash_sha3": hlk.sha3_file(path)}
    return 0, "ok"


hlk.run_intake = fake_intake
hlk.worker_meta = lambda name: META.get(name, {})
LINE = ("0 1953521664 helix double dandelion heat 0.021 state cooling compression 0.810 lanes 64 strandA raw 3791 "
        "zlib5 127 zbytes 56816 pending_bytes 0 strandB slots 16777216 used 1312 bonly 1311 rungs 0 b_hits {b} "
        "b_writes 1320 entries 5229 temps frozen 5229 cold 0 warm 0 hot 0 blazing 0 hits {h} zhits 0 misses {m} bypass 1")
counters = {"ingress": (100, 0, 100), "egress": (0, 0, 10)}


class P:
    def __init__(self, out):
        self.stdout = out


real_run = hlk.subprocess.run


def fake_run(cmd, *a, **k):
    if cmd[:3] == ["sudo", "-n", "dmsetup"]:
        inst = cmd[-1].split("-", 1)[1]
        h, b, m = counters[inst]
        return P("helix-x: " + LINE.format(h=h, b=b, m=m))
    return real_run(cmd, *a, **k)


hlk.subprocess.run = fake_run
os.makedirs(hlk.STATE, exist_ok=True)

# ── pull + index ─────────────────────────────────────────────────────────
code, r = hlk.call("pull", {"name": "frank_save.py"}, "127.0.0.1", "test")
check("pull a file: ok, lands in ops, indexed warm", code == 200 and r["ok"]
      and os.path.isfile(os.path.join(hlk.WORKDIR, "ops", "frank_save.py"))
      and hlk.tool_warm({"name": "frank_save.py"})["warm"])
code, r = hlk.call("pull", {"name": "tree"}, "127.0.0.1", "test")
check("pull a directory: 2 files, 3 bytes, indexed", r["ok"] and r["kind"] == "dir" and r["files"] == 2 and r["bytes"] == 3)
open(os.path.join(hlk.WORKDIR, "ops", "keep.txt"), "w").write("GOOD")
hlk.run_intake = lambda args, cwd: (1, "network down")
code, r = hlk.call("pull", {"name": "keep.txt"}, "127.0.0.1", "test")
check("a failed pull leaves the good copy untouched", not r["ok"]
      and open(os.path.join(hlk.WORKDIR, "ops", "keep.txt")).read() == "GOOD")
check("no temp pull dirs left behind", not [d for d in os.listdir(os.path.join(hlk.WORKDIR, "ops")) if d.startswith(".pull-")])
hlk.run_intake = fake_intake
for bad in ("../etc", "a/b", "..", "", "x" * 200, None):
    code, r = hlk.call("pull", {"name": bad}, "127.0.0.1", "test")
    check(f"unsafe name refused: {bad!r:.20}", code == 400)
check("warm: unknown item is not warm", not hlk.tool_warm({"name": "nope.txt"})["warm"])

# ── tiers: stage is auto, push asks ──────────────────────────────────────
code, r = hlk.call("stage", {"name": "result.txt", "text": "the answer"}, "127.0.0.1", "test")
check("stage runs without asking, lands on egress", code == 200 and os.path.isfile(os.path.join(hlk.EGRESS, "result.txt")))
code, r = hlk.call("stage", {"name": "x.txt", "from_pulled": "../../etc/passwd"}, "127.0.0.1", "test")
check("stage from_pulled refuses a path outside ingress", code == 400)
n_before = len(intake_calls)
code, r = hlk.call("push", {"name": "result.txt"}, "127.0.0.1", "test")
check("push asks first (202 + pending id), nothing sent yet", code == 202 and r["pending"] in hlk._pending
      and len(intake_calls) == n_before)
code, r = hlk.confirm(r["pending"], "no", "127.0.0.1")
check("answer no: nothing was done", r.get("done") is False and len(intake_calls) == n_before)
code, r = hlk.call("push", {"name": "result.txt"}, "127.0.0.1", "test")
code, r = hlk.confirm(r["pending"], "yes", "127.0.0.1")
check("answer yes: pushed, D1 receipt matches the local SHA3", r["ok"] and r["d1_receipt"] == r["local"])
check("a used confirmation id can't be replayed", hlk.confirm("whatever", "yes", "127.0.0.1")[0] == 404)
audit = [json.loads(x) for x in open(os.path.join(hlk.STATE, "audit.jsonl"))]
check("audit has asked / declined / ran-with-confirmation", {"asked", "declined", "ran"} <= {a["event"] for a in audit}
      and any(a.get("confirmed") for a in audit))

# ── status: her own counters, hit rate since the last look ───────────────
s1 = hlk.tool_status({})
check("status parses both instances", s1["ingress"]["up"] and s1["ingress"]["state"] == "cooling" and s1["egress"]["up"])
check("total hit rate from hits+b_hits vs misses", s1["ingress"]["hit_rate_total"] == 50.0)
counters["ingress"] = (190, 0, 110)                  # +90 served, +10 missed since last look
s2 = hlk.tool_status({})
check("hit_rate_now is since the last status (90/100 = 90%)", s2["ingress"]["hit_rate_now"] == 90.0)
check("index summary counts warm items", s2["index"]["warm_items"] >= 2)

# ── HTTP gate ─────────────────────────────────────────────────────────────
srv = hlk.http.server.ThreadingHTTPServer(("127.0.0.1", 0), hlk.make_handler("TOKEN123", ()))
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{srv.server_address[1]}"


def get(path, tok=None):
    req = urllib.request.Request(base + path, headers={"Authorization": f"Bearer {tok}"} if tok else {})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


check("/health open", get("/health") == 200)
check("/tools without token -> 401", get("/tools") == 401)
check("/tools with a wrong token -> 401", get("/tools", "nope") == 401)
check("/tools with the token -> 200", get("/tools", "TOKEN123") == 200)
srv.shutdown()

print(f"\n{passed} passing, {failed} failing")
sys.exit(1 if failed else 0)
