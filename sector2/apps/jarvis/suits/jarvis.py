"""jarvis.py — Genie suit: ask Jarvis (OpenJarvis on pbmIII) from anywhere on the Phoenix Mesh.
Phoenix DevOps OS | jwl247 | GPL v3

Stage:   {"suit": "jarvis", "text": "your question"}
Answer:  {"ok": true, "suit": "jarvis", "answer": "...", "ms": 4210}

Path: this suit -> SSH over the mesh as jarvis-call (forced command, no shell) -> jarvis-gate
-> Jarvis on pbmIII 127.0.0.1:8000 -> Ollama llama3.2:3b. Nothing leaves the mesh.
Env (no secrets in this file):
  JARVIS_HOST  default jarvis-call@10.42.0.10
  JARVIS_KEY   default ~/.ssh/phoenix_jarvis_ed25519
"""
import json
import os
import subprocess
from pathlib import Path

NAME = "jarvis"
WAIT = 25  # seconds: genie send waits 30


# JARVIS-S10: pbmIII's host key, pinned (was trust-on-first-use, so a first connection could be
# intercepted). Taken 2026-10-07 from the box over an already-trusted admin session; matches
# PBMII's known_hosts for both 10.42.0.10 and 192.168.1.192. If pbmIII is rebuilt, update this.
PBMIII_HOST_KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIKuW0yBPHUTtwQ3H6/X1LGxmWTMUD9Cai4HrQlWDsicG"


def pinned_known_hosts() -> str:
    """A known_hosts file holding only pbmIII's pinned key (rewritten each call, so it can't drift)."""
    p = Path.home() / ".ssh" / "phoenix_jarvis_known_hosts"
    p.parent.mkdir(mode=0o700, exist_ok=True)
    p.write_text(f"10.42.0.10 {PBMIII_HOST_KEY}\n", encoding="ascii")
    return str(p)


def run(data, ball=None, pcs=None, **_):
    try:
        msg = json.loads(data)
    except (ValueError, TypeError):
        return json.dumps({"ok": False, "suit": NAME, "error": "stage is not JSON"})
    if not isinstance(msg, dict) or not isinstance(msg.get("text"), str) or not msg["text"].strip():
        return json.dumps({"ok": False, "suit": NAME, "error": 'need {"text": "..."}'})
    host = os.environ.get("JARVIS_HOST", "jarvis-call@10.42.0.10")
    key = os.environ.get("JARVIS_KEY", str(Path.home() / ".ssh" / "phoenix_jarvis_ed25519"))
    cmd = ["ssh", "-i", key, "-o", "BatchMode=yes", "-o", "ConnectTimeout=6",
           "-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={pinned_known_hosts()}", host, "ask"]
    try:
        p = subprocess.run(cmd, input=json.dumps({"text": msg["text"]}), capture_output=True,
                           text=True, timeout=WAIT, encoding="utf-8")
        out = json.loads(p.stdout.strip().splitlines()[-1])
    except subprocess.TimeoutExpired:
        return json.dumps({"ok": False, "suit": NAME, "error": f"Jarvis took longer than {WAIT} s"})
    except (OSError, ValueError, IndexError):
        return json.dumps({"ok": False, "suit": NAME, "error": "no answer from pbmIII (mesh down or key missing)"})
    out["suit"] = NAME
    return json.dumps(out)


if __name__ == "__main__":
    import sys
    print(run(sys.argv[1] if len(sys.argv) > 1 else '{"text": "Who are you and where do you run?"}'))
