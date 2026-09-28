#!/usr/bin/env python3
"""Tests for the crew: sailor.py (read-only sector watch) and gangway.py (the hook).

The never-list shapes below are assembled from pieces so that the command that
runs this file never contains one (the gangway hook blocks any Bash command
that does, which is exactly the point)."""
import json, os, shutil, subprocess, sys, tempfile, time, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SAILOR = HERE / "sailor.py"
RO = "blockdev --set" + "ro /dev/sdb"
HD = "hdparm -r" + "1 /dev/sdc"
BL = "echo 'blacklist ahci' > /etc/" + "modprobe.d/x.conf"
TEE = "echo 'blacklist nvme' | sudo tee /etc/" + "modprobe.d/no.conf"
RMG = "rm -rf /mnt/" + "g/vault"
SK = "sk_" + "test_51ABCDEFGHIJKLMNOPQRSTUVWXYZ0123"


def make_ship(tmp: Path) -> Path:
    """A fake Phoenix root with a crew.json copy pointing at two small decks, no .git."""
    root = tmp / "ship"; (root / "sector1").mkdir(parents=True); (root / "sector4" / "guardian").mkdir(parents=True)
    (root / "sector1" / "boot.sh").write_text("#!/usr/bin/env bash\necho boot\n")
    (root / "sector1" / "helix.py").write_text("print('helix')\n")
    (root / "sector4" / "frank.py").write_text("print('frank')\n")
    shutil.copy(SAILOR, root / "sector4" / "guardian" / "sailor.py")
    shutil.copy(HERE / "gangway.py", root / "sector4" / "guardian" / "gangway.py")
    (root / "sector4" / "guardian" / "crew.json").write_text(json.dumps({
        "exclude_dirs": [".git", "__pycache__"],
        "rule_exempt": ["sector4/guardian/sailor.py", "sector4/guardian/gangway.py"],
        "sectors": {
            "sector1": {"deck": "boot", "watch": ["sector1"], "services": ["ghost.service"],
                        "heartbeats": [{"path": str(tmp / "hb.json"), "max_age": 60}], "checks": []},
            "sector4": {"deck": "core", "watch": ["sector4"], "services": [], "heartbeats": [], "checks": []},
        }}))
    return root


class Crew(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="crew-"))
        self.root = make_ship(self.tmp)
        self.home = self.tmp / "crewhome"; self.ledger = self.tmp / "ledger"
        self.env = {**os.environ, "PHOENIX_ROOT": str(self.root), "PHOENIX_CREW_HOME": str(self.home),
                    "VERIFY_DIR": str(self.ledger), "VERIFY_HOST": "testbox", "PHOENIX_SAILOR_BOX": "0"}

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def sail(self, *args, box=False):
        env = dict(self.env)
        if box: env["PHOENIX_SAILOR_BOX"] = "1"
        p = subprocess.run([sys.executable, str(self.root / "sector4" / "guardian" / "sailor.py"), *args],
                           capture_output=True, text=True, env=env)
        return p.returncode, p.stdout + p.stderr

    def test_uncommissioned_then_commission_then_clear(self):
        rc, out = self.sail("sector1", "watch")
        self.assertEqual(rc, 1); self.assertIn("uncommissioned", out)
        rc, out = self.sail("sector1", "commission")
        self.assertEqual(rc, 0); self.assertIn("2 files", out)
        rc, out = self.sail("sector1", "watch")
        self.assertEqual(rc, 0, out); self.assertIn("clear", out)
        day = sorted(self.ledger.iterdir())[0]
        self.assertTrue((day / "crew-sector1.log").exists())
        rows = json.loads((day / "summary.json").read_text())
        self.assertEqual([r["check"] for r in rows], ["crew-sector1"])
        self.assertEqual(rows[0]["result"], "0"); self.assertEqual(rows[0]["host"], "testbox")
        self.assertTrue((self.home / "sector1.heartbeat.json").exists())

    def test_drift_modified_new_missing(self):
        self.sail("sector1", "commission")
        (self.root / "sector1" / "helix.py").write_text("print('tampered')\n")
        (self.root / "sector1" / "extra.txt").write_text("x")
        (self.root / "sector1" / "boot.sh").unlink()
        rc, out = self.sail("sector1", "watch")
        self.assertEqual(rc, 3, out)
        self.assertIn("modified sector1/helix.py", out); self.assertIn("new sector1/extra.txt", out)
        self.assertIn("missing sector1/boot.sh", out)

    def test_never_list_flags_command_shapes_with_line(self):
        self.sail("sector4", "commission")
        (self.root / "sector4" / "bad.sh").write_text(f"#!/usr/bin/env bash\necho ok\n{RO}\n{BL}\nSK={SK}\n")
        rc, out = self.sail("sector4", "watch")
        lines = {l.split()[0]: l.split()[1] for l in out.splitlines() if l.strip().startswith("never:")}
        self.assertEqual(lines.get("never:drive-readonly"), "sector4/bad.sh:3", out)
        self.assertEqual(lines.get("never:modprobe-udev-write"), "sector4/bad.sh:4", out)
        self.assertEqual(lines.get("never:secret-stripe"), "sector4/bad.sh:5", out)
        self.assertGreaterEqual(rc, 4)  # 3 never + 1 drift(new)

    def test_prose_about_the_rules_is_not_a_finding(self):
        self.sail("sector4", "commission")
        (self.root / "sector4" / "notes.md").write_text(
            "Never set drives readonly, not via udev rules, not via blockdev, not via hdparm.\nmodprobe.d is off limits.\n")
        rc, out = self.sail("sector4", "watch")
        self.assertNotIn("never:", out); self.assertEqual(rc, 1)  # only the drift(new)

    def test_services_and_heartbeats_only_on_a_box(self):
        self.sail("sector1", "commission")
        rc, out = self.sail("sector1", "watch")
        self.assertEqual(rc, 0, out)                      # container: skipped, recorded as a note
        rc, out = self.sail("sector1", "watch", box=True)
        self.assertIn("heartbeat-missing", out)           # box: the missing heartbeat is a finding
        self.assertIn("ghost.service", out)
        (self.tmp / "hb.json").write_text("{}"); os.utime(self.tmp / "hb.json", (1, 1))
        rc, out = self.sail("sector1", "watch", box=True)
        self.assertIn("heartbeat-stale", out)

    def test_write_guard_refuses_outside_home_and_ledger(self):
        sys.path.insert(0, str(HERE)); os.environ.update(self.env)
        import importlib, sailor; importlib.reload(sailor)
        with self.assertRaises(PermissionError):
            sailor._write(self.root / "sector1" / "helix.py", "owned")
        self.assertEqual((self.root / "sector1" / "helix.py").read_text(), "print('helix')\n")

    def test_muster_reports_every_deck(self):
        self.sail("sector1", "commission"); self.sail("sector4", "commission")
        rc, out = self.sail("muster")
        self.assertEqual(rc, 0, out); self.assertIn("sector1  clear", out); self.assertIn("sector4  clear", out)
        self.assertIn("0 finding(s) across 2 decks", out)

    def test_daemon_stands_down_on_sigterm(self):
        self.sail("sector1", "commission")
        env = {**self.env, "PHOENIX_SAILOR_INTERVAL": "60"}
        p = subprocess.Popen([sys.executable, str(self.root / "sector4" / "guardian" / "sailor.py"), "sector1", "daemon"],
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
        time.sleep(1.5); p.terminate()
        out, _ = p.communicate(timeout=10)
        self.assertEqual(p.returncode, 0, out); self.assertIn("on watch", out); self.assertIn("stood down", out)

    # ── gangway ──
    def gang(self, payload):
        p = subprocess.run([sys.executable, str(HERE / "gangway.py")], input=json.dumps(payload), capture_output=True, text=True)
        return p.returncode, p.stderr

    def test_gangway_blocks_never_list_and_passes_normal_commands(self):
        rc, err = self.gang({"tool_name": "Bash", "tool_input": {"command": "sudo " + HD}})
        self.assertEqual(rc, 2); self.assertIn("drive-readonly", err)
        rc, err = self.gang({"tool_name": "Bash", "tool_input": {"command": TEE}})
        self.assertEqual(rc, 2); self.assertIn("modprobe-udev-write", err)
        rc, err = self.gang({"tool_name": "Bash", "tool_input": {"command": RMG}})
        self.assertEqual(rc, 2); self.assertIn("vault-delete", err)
        rc, _ = self.gang({"tool_name": "Bash", "tool_input": {"command": "git status && bash scripts/verify.sh --only guardian"}})
        self.assertEqual(rc, 0)
        rc, _ = self.gang({"tool_name": "Bash", "tool_input": {"command": "rm -rf /tmp/build && mount | grep /mnt/g"}})
        self.assertEqual(rc, 0)
        rc, _ = self.gang({"tool_name": "Edit", "tool_input": {"file_path": "x"}})
        self.assertEqual(rc, 0)
        p = subprocess.run([sys.executable, str(HERE / "gangway.py")], input="not json", capture_output=True, text=True)
        self.assertEqual(p.returncode, 0)

    def test_gangway_holds_sailors_to_the_allowlist(self):
        rc, err = self.gang({"tool_name": "Bash", "agent_type": "sailor-sector2",
                             "tool_input": {"command": "python3 sector4/guardian/sailor.py sector2 watch --checks"}})
        self.assertEqual(rc, 0, err)
        rc, err = self.gang({"tool_name": "Bash", "agent_type": "sailor-sector2",
                             "tool_input": {"command": "git status && sed -i 's/a/b/' sector2/x.sh"}})
        self.assertEqual(rc, 2); self.assertIn("read-only", err)
        rc, _ = self.gang({"tool_name": "Bash", "agent_type": "sailor-sector2", "tool_input": {"command": "systemctl restart helix"}})
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main(verbosity=1)
