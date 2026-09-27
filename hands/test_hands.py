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
    assert names == {"status", "open_app", "screenshot", "restart_pc", "cancel_restart"}, names
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


t("base tier runs without asking", base_runs_without_asking)
t("ask tier runs only after a real yes (JSON true)", ask_tier_needs_a_real_yes)
t("only the declared tools exist; none is tier never", only_declared_tools)
t("bad arguments are refused", bad_args_refused)
t("every call lands in the audit log", every_call_is_logged)
t("open_app only opens apps on its list", open_app_allowlist)
print(f"\n{ran - fails} passing, {fails} failing")
sys.exit(1 if fails else 0)
