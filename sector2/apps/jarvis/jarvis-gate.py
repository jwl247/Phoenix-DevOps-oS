#!/usr/bin/env python3
"""jarvis-gate — the only door to Jarvis from off the box.
Phoenix DevOps OS | jwl247 | GPL v3

Runs as the SSH forced command for user jarvis-call on pbmIII:
  restrict,from="10.42.0.0/16",command="/opt/openjarvis/jarvis-gate" ssh-ed25519 ...
The caller never gets a shell. It sends ONE JSON object on stdin:
  {"text": "what's on Laurie's list today?"}
and gets ONE JSON object back:
  {"ok": true, "answer": "...", "model": "llama3.2:3b", "ms": 4210}
The gate only talks to Jarvis on 127.0.0.1:8000. Every call is journaled: journalctl -t jarvis-gate
"""
import json, os, subprocess, sys, time, urllib.error, urllib.request

URL = "http://127.0.0.1:8000/v1/chat/completions"
MODEL = "llama3.2:3b"
IDENTITY = "/opt/openjarvis/jarvis_identity.md"  # sent as the system message on EVERY ask (rail: he can't drift from it)
MAX_TEXT = 4000
TIMEOUT = 120


def log(msg):
    subprocess.run(["logger", "-t", "jarvis-gate", msg], check=False)


def identity():
    try:
        with open(IDENTITY, encoding="utf-8") as f:
            return [{"role": "system", "content": f.read()}]
    except OSError:
        log("identity file missing - answering without it")
        return []


def reply(obj, code=0):
    print(json.dumps(obj), flush=True)
    sys.exit(code)


def main():
    who = (os.environ.get("SSH_CLIENT") or "local").split()[0]
    if os.environ.get("SSH_ORIGINAL_COMMAND", "") not in ("", "ask"):
        log(f"refused command from {who}")
        reply({"ok": False, "error": "only 'ask' with JSON on stdin"}, 2)
    try:
        msg = json.loads(sys.stdin.read(MAX_TEXT * 2 + 1024) or "{}")
    except ValueError:
        reply({"ok": False, "error": "stdin is not JSON"}, 2)
    text = msg.get("text") if isinstance(msg, dict) else None
    if not isinstance(text, str) or not text.strip():
        reply({"ok": False, "error": "need {\"text\": \"...\"}"}, 2)
    if len(text) > MAX_TEXT:
        reply({"ok": False, "error": f"text over {MAX_TEXT} chars"}, 2)
    log(f"ask from {who}: {len(text)} chars")
    body = json.dumps({"model": MODEL, "stream": False,
                       "messages": identity() + [{"role": "user", "content": text}]}).encode()
    t0 = time.time()
    try:
        req = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            out = json.loads(r.read())
        answer = out["choices"][0]["message"]["content"]
    except (urllib.error.URLError, OSError, KeyError, IndexError, ValueError) as e:
        log(f"jarvis did not answer: {e}")
        reply({"ok": False, "error": f"jarvis did not answer: {e}"}, 1)
    ms = int((time.time() - t0) * 1000)
    log(f"answered {who} in {ms} ms")
    reply({"ok": True, "answer": answer, "model": out.get("model", MODEL), "ms": ms})


if __name__ == "__main__":
    main()
