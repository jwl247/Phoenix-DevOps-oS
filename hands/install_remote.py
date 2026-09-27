#!/usr/bin/env python3
"""Put H.L.K's hands on a headless Phoenix box over SSH, and give the Console
that box's token. Runs on the Console's PC (the hub).

UnitedSys — United Systems | jwl247 | GPL-3.0

  python hands/install_remote.py NAME --ssh ALIAS      e.g.  compaq --ssh pbm-compaq

The token is made ON the box, travels back over SSH, and is written only to
~/.phoenix/hands-tokens.json here (owner-only). It is never printed.
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOKENS = os.path.join(os.path.expanduser("~"), ".phoenix", "hands-tokens.json")


def ssh(alias, command, stdin=None):
    r = subprocess.run(["ssh", "-o", "ConnectTimeout=10", alias, command], input=stdin,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        sys.exit(f"[{alias}] failed: {r.stderr.strip()[-400:]}")
    return r.stdout


def main():
    ap = argparse.ArgumentParser(prog="install_remote")
    ap.add_argument("name", help="the box's Phoenix name (compaq, pbm3)")
    ap.add_argument("--ssh", required=True, help="SSH alias for the box")
    a = ap.parse_args()

    print(f"[{a.ssh}] copying the hands")
    ssh(a.ssh, "sudo mkdir -p /opt/phoenix-hands")
    for src, dst in (("hands.py", "/opt/phoenix-hands/hands.py"),
                     ("phoenix-hands.service", "/etc/systemd/system/phoenix-hands.service")):
        with open(os.path.join(HERE, src), encoding="utf-8") as f:
            ssh(a.ssh, f"sudo tee {dst} >/dev/null", stdin=f.read().replace("\r\n", "\n"))
    ssh(a.ssh, "sudo systemctl daemon-reload && sudo systemctl enable phoenix-hands >/dev/null 2>&1 "
               "&& sudo systemctl restart phoenix-hands && sleep 3 && systemctl is-active phoenix-hands")
    token = ssh(a.ssh, "sudo cat /root/.phoenix/hands.token").strip()
    if len(token) != 64:
        sys.exit(f"[{a.ssh}] no token made (is the service running?)")

    os.makedirs(os.path.dirname(TOKENS), exist_ok=True)
    tokens = {}
    if os.path.exists(TOKENS):
        with open(TOKENS, encoding="utf-8") as f:
            tokens = json.load(f)
    tokens[a.name] = token
    with open(TOKENS, "w", encoding="utf-8") as f:
        json.dump(tokens, f)
    if os.name == "nt":
        subprocess.run(["icacls", TOKENS, "/inheritance:r", "/grant:r", f"{os.environ.get('USERNAME')}:F"], capture_output=True)
    else:
        os.chmod(TOKENS, 0o600)
    print(f"hands on {a.name}: running; the Console has its token")


if __name__ == "__main__":
    main()
