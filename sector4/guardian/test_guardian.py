#!/usr/bin/env python3
"""Tests for the ring guardian as a service. Exit code = failures.
   python3 sector4/guardian/test_guardian.py"""
import json
import os
import subprocess
import sys
import tempfile
import time

TMP = tempfile.mkdtemp(prefix="guardian-test-")
HOME = os.path.join(TMP, "state")
SCAN = os.path.join(TMP, "units")
os.makedirs(SCAN)
os.environ["PHOENIX_GUARDIAN_HOME"] = HOME
os.environ["PHOENIX_GUARDIAN_SCAN_DIRS"] = SCAN
os.environ["PHOENIX_GUARDIAN_INTERVAL"] = "1"
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import integrated_guardian as g  # noqa: E402

failures = 0


def t(name, fn):
    global failures
    try:
        fn(); print(f"  ok  {name}")
    except Exception as e:  # noqa: BLE001
        failures += 1; print(f"FAIL  {name}\n      {type(e).__name__}: {e}")


def w(name, text):
    with open(os.path.join(SCAN, name), "w") as f:
        f.write(text)


w("phoenix-paging.service", "[Service]\nEnvironment=PHOENIX_PAGING_DASH_BIND=127.0.0.1\nExecStart=/usr/bin/python3 /opt/phoenix/sector4/paging.py start\n# dashboard 127.0.0.1:8888\nAfter=helix.service\n")
w("helix-vram.service", "[Service]\nExecStart=/usr/bin/python3 /opt/phoenix/sector1/helix/helix_vramd.py serve\nEnvironmentFile=-/etc/default/helix-vram\n")
w("stranger.service", "[Service]\nExecStart=/usr/local/bin/stranger --listen 0.0.0.0:8888\n# started 2026-09-28 at 10:30\n")
w("clock.env", "START=06:00\nEND=23:00\nDATE=2026-09-28\n")


def state_lives_in_home():
    fg = g.FileGuardian()
    assert os.path.isfile(os.path.join(HOME, "installer_registry.json"))
    assert os.path.isfile(os.path.join(HOME, "file_guardian.json"))
    assert not os.path.exists(os.path.join(HERE, "installer_registry.json")), "wrote into the repo tree"


def times_are_not_ports():
    fg = g.FileGuardian()
    reg = fg.installer.registry
    assert "8888" in reg["ports"], reg["ports"].keys()
    assert "30" not in reg["ports"] and "00" not in reg["ports"] and "2026" not in reg["ports"], reg["ports"].keys()


def real_conflict_found_friends_suppressed():
    fg = g.FileGuardian()
    real = fg.installer.resolve_conflicts(quiet=True)
    kinds = {(c["conflict"]["type"], str(c["conflict"]["value"])) for c in real}
    assert ("port", "8888") in kinds, kinds          # paging vs stranger on 8888
    svcs = {tuple(c["conflict"]["services"]) for c in real}
    assert ("phoenix-paging", "stranger") in svcs, svcs
    fg.installer.make_friends("phoenix-paging", "stranger")
    real2 = fg.installer.resolve_conflicts(quiet=True)
    assert not any(str(c["conflict"]["value"]) == "8888" for c in real2), "friends still reported"


def team_are_friends_by_default():
    fg = g.FileGuardian()
    assert fg.installer.are_friends("helix", "helix-vram") and fg.installer.are_friends("phoenix-paging", "helix-guardian")


def rescan_does_not_stack_claims():
    fg = g.FileGuardian()
    fg.installer.auto_scan(); fg.installer.auto_scan()
    users = fg.installer.registry["ports"]["8888"]
    assert len(users) == 2, users


def heartbeat_and_once():
    fg = g.FileGuardian()
    fg.daemon(once=True)
    hb = json.load(open(os.path.join(HOME, "heartbeat.json")))
    assert hb["configs"] >= 3 and "at" in hb and hb["instance"] == "guardian_1", hb
    assert fg.query("conflicts")["configs"] >= 3


def cli_status_and_sigterm():
    env = dict(os.environ)
    r = subprocess.run([sys.executable, os.path.join(HERE, "integrated_guardian.py"), "status"], env=env,
                       capture_output=True, text=True, timeout=30)
    assert "configs" in r.stdout, r.stdout + r.stderr
    p = subprocess.Popen([sys.executable, os.path.join(HERE, "integrated_guardian.py"), "guardian_2", "daemon"], env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    time.sleep(2.5)
    p.terminate()
    out, _ = p.communicate(timeout=15)
    assert p.returncode == 0 and "down" in out, (p.returncode, out[-300:])
    assert json.load(open(os.path.join(HOME, "heartbeat.json")))["instance"] == "guardian_2"


t("state files live in PHOENIX_GUARDIAN_HOME, not the repo", state_lives_in_home)
t("clock times and dates are not ports", times_are_not_ports)
t("a real port conflict is found; friends suppress it", real_conflict_found_friends_suppressed)
t("the team are friends by default", team_are_friends_by_default)
t("rescanning does not stack claims", rescan_does_not_stack_claims)
t("daemon --once writes the heartbeat", heartbeat_and_once)
t("status CLI + daemon stops on SIGTERM", cli_status_and_sigterm)
print(f"\n{7 - failures} passing, {failures} failing")
sys.exit(failures)
