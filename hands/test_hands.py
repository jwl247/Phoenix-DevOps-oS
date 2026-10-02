"""Tests for H.L.K's hands: tiers, the fixed tool list, the audit log. Run: python hands/test_hands.py

Nothing here opens a window, takes a screenshot or restarts anything: the
tool functions are swapped for stand-ins before any call."""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["PHOENIX_HANDS_LOG"] = os.path.join(tempfile.mkdtemp(), "hands.jsonl")
import hands  # noqa: E402

ran = fails = 0
calls = []
for name in hands.TOOLS:                                  # stand-ins: record, never act
    hands.TOOLS[name]["fn"] = (lambda n: (lambda **kw: calls.append((n, kw)) or {"did": n}))(name)


def t(name, fn):
    global ran, fails
    ran += 1
    try:
        fn()
        print(f"  ok  {name}")
    except Exception as e:
        fails += 1
        print(f"FAIL  {name}\n      {e!r}")


def base_runs_without_asking():
    calls.clear()
    code, out = hands.run("status", {}, None, "test")
    assert code == 200 and out["ok"] and calls == [("status", {})], (code, out, calls)


def ask_tier_needs_a_real_yes():
    calls.clear()
    for confirm in (None, False, "yes", 1):               # only the JSON value true counts
        code, out = hands.run("restart_pc", {}, confirm, "test")
        assert code == 409 and out["needs_confirm"] and out["question"].startswith("Restart "), out
    assert calls == [], "nothing ran before the yes"
    code, out = hands.run("restart_pc", {}, True, "test")
    assert code == 200 and calls == [("restart_pc", {})]


def only_declared_tools():
    code, out = hands.run("format_drive", {}, True, "test")
    assert code == 404 and not out["ok"]
    names = {x["name"] for x in hands.public_tools()}
    # Per-platform tool sets (S34OPS-F37: the suite used to assert the Windows
    # set only, so it failed on compaq/pbm3 even though the code was right).
    if hands.IS_WIN:
        expected = {"status", "open_app", "screenshot", "restart_pc", "cancel_restart"}
    else:
        expected = {"status", "services", "restart_service", "restart_pc", "cancel_restart"}
    assert names == expected, names
    assert names == set(hands.TOOLS), "public_tools() must list exactly the declared tools"
    assert all(x["tier"] in ("base", "ask") for x in hands.public_tools()), "no tool may be tier never"


def bad_args_refused():
    code, out = hands.run("status", ["not", "a", "dict"], None, "test")
    assert code == 400


def every_call_is_logged():
    hands.run("status", {}, None, "console from 10.47.0.1")
    last = hands.recent(1)[0]
    assert last["tool"] == "status" and last["ok"] and last["caller"] == "console from 10.47.0.1", last
    hands.run("restart_pc", {}, None, "test")
    last = hands.recent(1)[0]
    assert last["tool"] == "restart_pc" and not last["ok"] and "confirmation" in last["error"], last


def open_app_allowlist():
    real = hands.tool_open_app
    try:
        real("format_c")
        raise AssertionError("unknown app should raise")
    except ValueError:
        pass


def import_from_pool_is_checked():
    import hashlib
    import http.server
    import threading
    served = {}

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            data, claimed = served["data"], served["claim"]
            self.send_response(200)
            self.send_header("X-Phoenix-SHA3", claimed)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}/pool/hands.py"
    d = tempfile.mkdtemp()
    fake_self = os.path.join(d, "hands.py")
    old = b"print('v1')\n"
    open(fake_self, "wb").write(old)
    real_self, real_sha = hands.SELF, hands.SELF_SHA3
    hands.SELF, hands.SELF_SHA3 = fake_self, hashlib.sha3_512(old).hexdigest()
    try:
        sha = lambda b: hashlib.sha3_512(b).hexdigest()
        served.update(data=old, claim=sha(old))
        assert hands.update_once(url, "t") == "current"
        new = b"print('v2')\n"
        served.update(data=new, claim=sha(b"something else"))
        assert hands.update_once(url, "t").startswith("refused: the file doesn't match"), "wrong fingerprint refused"
        assert open(fake_self, "rb").read() == old, "nothing swapped on refusal"
        broken = b"def (\n"
        served.update(data=broken, claim=sha(broken))
        assert hands.update_once(url, "t").startswith("refused: new version doesn't compile")
        assert open(fake_self, "rb").read() == old
        served.update(data=new, claim=sha(new))
        assert hands.update_once(url, "t") == "updated"
        assert open(fake_self, "rb").read() == new, "new version swapped in"
        assert hands.recent(1)[0]["tool"] == "self_update"
    finally:
        hands.SELF, hands.SELF_SHA3 = real_self, real_sha
        srv.shutdown()


def binds_mesh_address_before_it_exists():
    """A2-N6: an address not on any interface yet (the mesh still coming up)."""
    import http.server
    if not (hasattr(os, "uname") and os.uname().sysname == "Linux"):
        return                                            # IP_FREEBIND is Linux-only; Windows binds 127.0.0.1 only
    addr = ("10.47.0.254", 0)
    try:
        http.server.ThreadingHTTPServer(addr, http.server.BaseHTTPRequestHandler).server_close()
        raise AssertionError("10.47.0.254 is local here; the test needs an address that isn't")
    except OSError as e:
        assert e.errno == 99, e                           # what the boxes hit at boot
    hands.MeshServer(addr, http.server.BaseHTTPRequestHandler).server_close()


t("base tier runs without asking", base_runs_without_asking)
t("import from the pool: fingerprint + compile checked, atomic swap", import_from_pool_is_checked)
t("ask tier runs only after a real yes (JSON true)", ask_tier_needs_a_real_yes)
t("only the declared tools exist; none is tier never", only_declared_tools)
t("bad arguments are refused", bad_args_refused)
t("every call lands in the audit log", every_call_is_logged)
t("open_app only opens apps on its list", open_app_allowlist)
t("binds the mesh address before WireGuard has it (A2-N6)", binds_mesh_address_before_it_exists)
print(f"\n{ran - fails} passing, {fails} failing")
sys.exit(1 if fails else 0)
