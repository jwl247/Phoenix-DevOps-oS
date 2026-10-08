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
import fcntl, json, os, re, subprocess, sys, time, urllib.error, urllib.request

URL = "http://127.0.0.1:8000/v1/chat/completions"
MODEL = "llama3.2:3b"
IDENTITY = "/opt/openjarvis/jarvis_identity.md"  # sent as the system message on EVERY ask (rail: he can't drift from it)
MAX_TEXT = 4000
WARM = sys.argv[1:] == ["--warm"]  # root-only, from openjarvis.service at start; SSH callers can't pass argv to a forced command
TIMEOUT = 90  # reins loosened (Jerry 2026-10-08: "guard rail don't mean chained in the basement"): 22 s cut off real answers on a busy CPU. Still ends BEFORE the suit gives up (WAIT 100 s); one ask per caller box still holds (S2APPS-F79/JARVIS-S11)
MAX_TOKENS = 1024     # loosened from 300 (Jerry 10/8); sized to finish inside TIMEOUT on CPU
KEY_FILE = "/etc/openjarvis/gate.key"  # 0640 root:jarvis-call - Jarvis's API refuses calls without it (JARVIS-S03)


def log(msg):
    subprocess.run(["logger", "-t", "jarvis-gate", msg], check=False)


def identity():
    try:
        with open(IDENTITY, encoding="utf-8") as f:
            return [{"role": "system", "content": f.read()}]
    except OSError:
        log("identity file missing - answering without it")
        return []


def api_key():
    try:
        with open(KEY_FILE, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def reply(obj, code=0):
    print(json.dumps(obj), flush=True)
    sys.exit(code)


def main():
    who = (os.environ.get("SSH_CLIENT") or "local").split()[0]
    if os.environ.get("SSH_ORIGINAL_COMMAND", "") not in ("", "ask"):
        log(f"refused command from {who}")
        reply({"ok": False, "error": "only 'ask' with JSON on stdin"}, 2)
    try:
        msg = {"text": "ready?"} if WARM else json.loads(sys.stdin.read(MAX_TEXT * 2 + 1024) or "{}")
    except ValueError:
        reply({"ok": False, "error": "stdin is not JSON"}, 2)
    text = msg.get("text") if isinstance(msg, dict) else None
    if not isinstance(text, str) or not text.strip():
        reply({"ok": False, "error": "need {\"text\": \"...\"}"}, 2)
    if len(text) > MAX_TEXT:
        reply({"ok": False, "error": f"text over {MAX_TEXT} chars"}, 2)
    if not WARM:
        # JARVIS-S11: one ask at a time per calling box (OpenJarvis's own limiter doesn't load);
        # a second ask while the first runs is refused at once instead of queueing behind it.
        locks = os.path.expanduser("~/.gate-locks")
        os.makedirs(locks, mode=0o700, exist_ok=True)
        lock = open(os.path.join(locks, re.sub(r"[^0-9A-Za-z.:-]", "_", who) + ".lock"), "w")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            log(f"busy: {who} already has an ask running")
            reply({"ok": False, "error": "busy: your previous ask is still running"}, 3)
    log(f"ask from {who}: {len(text)} chars")
    body = json.dumps({"model": MODEL, "stream": False, "max_tokens": MAX_TOKENS,
                       "messages": identity() + [{"role": "user", "content": text}]}).encode()
    t0 = time.time()
    try:
        headers = {"Content-Type": "application/json"}
        key = api_key()
        if key:
            headers["Authorization"] = f"Bearer {key}"
        req = urllib.request.Request(URL, data=body, headers=headers)
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
