#!/usr/bin/env python3
"""
test_phoenix_vault.py — the encrypted vault: seal, refuse, pull, place
Phoenix DevOps OS | jwl247 | GPL v3

Throwaway passphrases and a temp "vault" only — never the real one.
    python sector6/test_phoenix_vault.py
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import phoenix_vault as pv  # noqa: E402

PW = "correct horse battery staple ironworker"


class TestCrypto(unittest.TestCase):
    def setUp(self):
        self.files = {"phoenix-secrets.env": b"PHOENIX_AUTH=abc123\nPHOENIX_WORKER_URL=https://w.example\n",
                      "sacrifice.env": b"SACRIFICE_FRANK_TOKEN=" + b"f" * 48 + b"\n"}

    def test_round_trip(self):
        blob = pv.seal(self.files, PW)
        out = pv.unseal(blob, PW)
        self.assertEqual({k: v.encode() for k, v in out["files"].items()}, self.files)

    def test_ciphertext_reveals_nothing(self):
        blob = pv.seal(self.files, PW)
        for needle in (b"PHOENIX_AUTH", b"abc123", b"fffff"):
            self.assertNotIn(needle, blob)
        self.assertNotEqual(pv.seal(self.files, PW), blob)          # fresh salt + nonce every time

    def test_wrong_passphrase_and_tampering_refused(self):
        blob = pv.seal(self.files, PW)
        with self.assertRaises(ValueError):
            pv.unseal(blob, PW + "x")
        flipped = bytearray(blob)
        flipped[-5] ^= 1
        with self.assertRaises(ValueError):
            pv.unseal(bytes(flipped), PW)
        hdr = bytearray(blob)
        hdr[30] ^= 1                                                 # the salt is authenticated too
        with self.assertRaises(ValueError):
            pv.unseal(bytes(hdr), PW)
        with self.assertRaises(ValueError):
            pv.unseal(b"NOTVAULT" + blob[8:], PW)

    def test_fetch_token_is_stable_and_not_the_key(self):
        t = pv.fetch_token(PW)
        self.assertEqual(t, pv.fetch_token(PW))
        self.assertEqual(len(t), 64)
        self.assertNotEqual(t, pv.fetch_token(PW + "!"))
        self.assertEqual(pv.fetch_hash(PW), hashlib.sha256(t.encode()).hexdigest())


class TestBox(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="phoenix_vault_"))
        self.vault_dir = self.tmp / "vault"
        self.vault_dir.mkdir()
        (self.vault_dir / "phoenix-secrets.env").write_text("PHOENIX_AUTH=abc123\nexport STRIPE_SECRET_KEY_LIVE=\"sk_x\"\n")
        (self.vault_dir / "sacrifice.env").write_text("SACRIFICE_FRANK_TOKEN=tok\n")
        (self.vault_dir / "SECRETS.md").write_text("# map")
        (self.vault_dir / "phoenix-secrets.env.template").write_text("PHOENIX_AUTH=\n")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def sealed(self):
        return pv.unseal(pv.seal(pv.read_vault(self.vault_dir), PW), PW)

    def test_docs_and_templates_stay_home(self):
        self.assertEqual(sorted(pv.read_vault(self.vault_dir)), ["phoenix-secrets.env", "sacrifice.env"])

    def test_pull_only_named_files(self):
        dest = self.tmp / "box"
        written = pv.place(self.sealed(), dest, ["sacrifice.env"], None)
        self.assertEqual(written, ["sacrifice.env"])
        self.assertEqual(sorted(os.listdir(dest)), ["sacrifice.env"])
        if os.name == "posix":
            self.assertEqual(os.stat(dest / "sacrifice.env").st_mode & 0o777, 0o600)
            self.assertEqual(os.stat(dest).st_mode & 0o777, 0o700)

    def test_pull_just_some_keys(self):
        dest = self.tmp / "box"
        pv.place(self.sealed(), dest, None, ["PHOENIX_AUTH", "SACRIFICE_FRANK_TOKEN"])
        self.assertEqual((dest / "phoenix.env").read_text(), "PHOENIX_AUTH=abc123\nSACRIFICE_FRANK_TOKEN=tok\n")
        self.assertFalse((dest / "phoenix-secrets.env").exists())   # the live Stripe key did not come along
        with self.assertRaises(SystemExit):
            pv.place(self.sealed(), dest, None, ["NOPE"])

    def test_cli_pull_end_to_end_with_passphrase_from_env(self):
        blob = pv.seal(pv.read_vault(self.vault_dir), PW)
        seen = {}

        def fake_fetch(url, token, name=pv.OBJECT):
            seen["token"] = token
            return blob

        dest = self.tmp / "box"
        with patch.object(pv, "fetch", fake_fetch), patch.dict(os.environ, {"PHOENIX_VAULT_PASSPHRASE": PW}):
            self.assertEqual(pv.main(["pull", "--keys", "PHOENIX_AUTH", "--dest", str(dest)]), 0)
        self.assertEqual(seen["token"], pv.fetch_token(PW))
        self.assertEqual((dest / "phoenix.env").read_text(), "PHOENIX_AUTH=abc123\n")

    def test_worker_accepts_the_python_token(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node not installed")
        test = HERE.parent / "sector4" / "vault" / "worker" / "test" / "vault.test.mjs"
        r = subprocess.run([node, str(test), pv.fetch_token(PW), pv.fetch_hash(PW)],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=1)
