#!/usr/bin/env python3
"""
phoenix_phone.py — the phone side of Life First: eyes, ears and screen.
Phoenix DevOps OS | jwl247 | GPL v3

Runs natively in Termux (where the termux-api commands live), standard
library only. Talks to the brain (PBMII's Universal Kernel) over the Phoenix
Mesh: check-ins go into Helix-I, replies come back out of Helix-E.

  python phoenix_phone.py say "took my morning meds"   send a check-in
  python phoenix_phone.py voice                         speak it (termux-speech-to-text)
  python phoenix_phone.py where                         send a location check-in
  python phoenix_phone.py listen                        stay connected; every reply -> notification
  python phoenix_phone.py flush                         retry the outbox now
  python phoenix_phone.py doctor                        config + reachability check

Config: ~/.phoenix/phone.env (chmod 600), KEY=value lines:
  PHOENIX_BRAIN       the brain's Phoenix Mesh (Tailscale) address — never a LAN/public IP
  HELIX_SOCKET_TOKEN  same token the brain's kernel runs with
  PHOENIX_WHO         whose phone this is (e.g. laurie) — replies for others are ignored
  PHOENIX_SUIT        default lifefirst_checkin
  HELIX_I_PORT / HELIX_E_PORT   default 7701 / 7805
  PHOENIX_SPEAK=1     also speak replies (termux-tts-speak)

When the brain is unreachable, check-ins wait in ~/.phoenix/phone/outbox.jsonl
and go out on the next say/voice/where/flush or while `listen` runs. Nothing
is dropped.
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

HOME = Path(os.environ.get("PHOENIX_PHONE_HOME", Path.home() / ".phoenix" / "phone"))
ENV_FILE = Path(os.environ.get("PHOENIX_PHONE_ENV", Path.home() / ".phoenix" / "phone.env"))
OUTBOX = HOME / "outbox.jsonl"
PIDFILE = HOME / "listen.pid"


# ── config ─────────────────────────────────────────────────────────────────
def load_config() -> dict:
    cfg = {"HELIX_I_PORT": "7701", "HELIX_E_PORT": "7805", "PHOENIX_SUIT": "lifefirst_checkin"}
    if ENV_FILE.exists():
        if os.name == "posix" and ENV_FILE.stat().st_mode & 0o077:
            print(f"warning: {ENV_FILE} is readable by others — run: chmod 600 {ENV_FILE}", file=sys.stderr)
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip().strip('"').strip("'")
    for k in ("PHOENIX_BRAIN", "HELIX_SOCKET_TOKEN", "PHOENIX_WHO", "PHOENIX_SUIT",
              "HELIX_I_PORT", "HELIX_E_PORT", "PHOENIX_SPEAK"):
        if os.environ.get(k):
            cfg[k] = os.environ[k]
    return cfg


def require(cfg: dict, *keys):
    missing = [k for k in keys if not cfg.get(k)]
    if missing:
        sys.exit(f"missing in {ENV_FILE}: {', '.join(missing)}")


# ── termux-api ─────────────────────────────────────────────────────────────
def termux(cmd: list, timeout: float = 60) -> str:
    if not shutil.which(cmd[0]):
        raise RuntimeError(f"{cmd[0]} not found — pkg install termux-api, and install the Termux:API app")
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"{cmd[0]} failed: {r.stderr.strip()[:200]}")
    return r.stdout.strip()


def notify(title: str, text: str, speak: bool = False):
    try:
        termux(["termux-notification", "--title", title, "--content", text, "--id", "phoenix-lifefirst"], timeout=15)
    except Exception as e:
        print(f"(notification failed: {e})", file=sys.stderr)
    if speak:
        try:
            termux(["termux-tts-speak", text], timeout=60)
        except Exception as e:
            print(f"(speak failed: {e})", file=sys.stderr)


# ── wire ───────────────────────────────────────────────────────────────────
def _connect(cfg: dict, port_key: str, timeout: float = 10) -> socket.socket:
    s = socket.create_connection((cfg["PHOENIX_BRAIN"], int(cfg[port_key])), timeout=timeout)
    if cfg.get("HELIX_SOCKET_TOKEN"):
        s.sendall(b"HXT " + cfg["HELIX_SOCKET_TOKEN"].encode() + b"\n")
    return s


def _send_stage(cfg: dict, stage: dict):
    s = _connect(cfg, "HELIX_I_PORT")
    try:
        s.sendall(json.dumps(stage).encode())
    finally:
        s.close()


def _queue(stage: dict):
    HOME.mkdir(parents=True, exist_ok=True)
    with open(OUTBOX, "a", encoding="utf-8") as f:
        f.write(json.dumps(stage) + "\n")


def flush_outbox(cfg: dict) -> int:
    if not OUTBOX.exists():
        return 0
    pending = [json.loads(l) for l in OUTBOX.read_text(encoding="utf-8").splitlines() if l.strip()]
    sent = 0
    for st in pending:
        try:
            _send_stage(cfg, st)
            sent += 1
        except OSError:
            break
    rest = pending[sent:]
    tmp = OUTBOX.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(x) + "\n" for x in rest), encoding="utf-8")
    os.replace(tmp, OUTBOX)
    return sent


def split_json_stream(buf: str):
    """Helix-E writes JSON objects back to back on one stream; split them."""
    dec, out, i = json.JSONDecoder(), [], 0
    while True:
        while i < len(buf) and buf[i].isspace():
            i += 1
        if i >= len(buf):
            return out, ""
        try:
            obj, j = dec.raw_decode(buf, i)
        except ValueError:
            return out, buf[i:]
        out.append(obj)
        i = j


def _mine(cfg: dict, msg) -> bool:
    who = cfg.get("PHOENIX_WHO", "").lower()
    return isinstance(msg, dict) and (not who or str(msg.get("who", "")).lower() == who)


def _listener_running() -> bool:
    try:
        pid = int(PIDFILE.read_text())
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        return False


def checkin(cfg: dict, kind: str, text: str, extra: dict = None, wait: float = 40.0):
    require(cfg, "PHOENIX_BRAIN", "PHOENIX_WHO")
    stage = {"suit": cfg["PHOENIX_SUIT"], "who": cfg["PHOENIX_WHO"], "type": kind, "text": text,
             "sent_at": round(time.time(), 3), **(extra or {})}
    # The listener (if running) owns notifications; otherwise wait for our own reply.
    consumer = None
    if not _listener_running():
        try:
            consumer = _connect(cfg, "HELIX_E_PORT")
            consumer.settimeout(wait)
            time.sleep(0.2)
        except OSError:
            consumer = None
    try:
        flushed = flush_outbox(cfg)
        _send_stage(cfg, stage)
    except OSError as e:
        _queue(stage)
        print(f"brain unreachable ({e}) — queued in outbox, will send when it's back")
        return 1
    if flushed:
        print(f"(sent {flushed} queued check-in(s) first)")
    if consumer is None:
        print("sent — the listener will show the reply")
        return 0
    buf, deadline = "", time.time() + wait
    try:
        while time.time() < deadline:
            chunk = consumer.recv(65536)
            if not chunk:
                break
            msgs, buf = split_json_stream(buf + chunk.decode("utf-8", "replace"))
            for m in msgs:
                if _mine(cfg, m):
                    reply = m.get("reply") or m.get("error") or json.dumps(m)
                    print(reply + ("" if m.get("ai", True) else "   [no AI — logged only]"))
                    notify("Life First", reply, speak=cfg.get("PHOENIX_SPEAK") == "1")
                    return 0
    except socket.timeout:
        pass
    finally:
        consumer.close()
    print("sent — no reply within the wait (the brain may still be thinking)")
    return 0


def listen(cfg: dict):
    require(cfg, "PHOENIX_BRAIN")
    HOME.mkdir(parents=True, exist_ok=True)
    PIDFILE.write_text(str(os.getpid()))
    backoff = 2
    try:
        while True:
            try:
                s = _connect(cfg, "HELIX_E_PORT")
                s.settimeout(None)
                print(f"listening on {cfg['PHOENIX_BRAIN']}:{cfg['HELIX_E_PORT']}")
                backoff = 2
                try:
                    n = flush_outbox(cfg)
                    if n:
                        print(f"sent {n} queued check-in(s)")
                except OSError:
                    pass
                buf = ""
                while True:
                    chunk = s.recv(65536)
                    if not chunk:
                        raise ConnectionError("brain closed the stream")
                    msgs, buf = split_json_stream(buf + chunk.decode("utf-8", "replace"))
                    for m in msgs:
                        if _mine(cfg, m):
                            reply = m.get("reply") or m.get("error") or json.dumps(m)
                            print(f"[{time.strftime('%H:%M:%S')}] {reply}")
                            notify("Life First", reply, speak=cfg.get("PHOENIX_SPEAK") == "1")
            except (OSError, ConnectionError) as e:
                print(f"lost the brain ({e}); retrying in {backoff}s")
                time.sleep(backoff)
                backoff = min(backoff * 2, 60)
    finally:
        try:
            PIDFILE.unlink()
        except OSError:
            pass


def doctor(cfg: dict) -> int:
    ok = True
    for k in ("PHOENIX_BRAIN", "HELIX_SOCKET_TOKEN", "PHOENIX_WHO"):
        print(f"  {k:<20} {'set' if cfg.get(k) else 'MISSING'}")
        ok &= bool(cfg.get(k))
    for c in ("termux-speech-to-text", "termux-location", "termux-notification", "termux-tts-speak"):
        print(f"  {c:<22} {'ok' if shutil.which(c) else 'missing (pkg install termux-api)'}")
    if cfg.get("PHOENIX_BRAIN"):
        for key in ("HELIX_I_PORT", "HELIX_E_PORT"):
            try:
                _connect(cfg, key, timeout=5).close()
                print(f"  brain {key:<14} reachable")
            except OSError as e:
                print(f"  brain {key:<14} UNREACHABLE ({e})")
                ok = False
    q = len(OUTBOX.read_text().splitlines()) if OUTBOX.exists() else 0
    print(f"  outbox               {q} queued")
    return 0 if ok else 1


def main(argv) -> int:
    cfg = load_config()
    cmd = argv[1] if len(argv) > 1 else "doctor"
    if cmd == "say":
        text = " ".join(argv[2:]).strip()
        if not text:
            sys.exit('usage: phoenix_phone.py say "text"')
        return checkin(cfg, "checkin", text)
    if cmd == "voice":
        text = termux(["termux-speech-to-text"], timeout=90)
        if not text:
            sys.exit("heard nothing")
        print(f'heard: "{text}"')
        return checkin(cfg, "voice", text)
    if cmd == "where":
        loc = json.loads(termux(["termux-location", "-p", "network", "-r", "once"], timeout=60))
        return checkin(cfg, "location", "location update",
                       {"lat": loc.get("latitude"), "lon": loc.get("longitude")})
    if cmd == "listen":
        listen(cfg)
        return 0
    if cmd == "flush":
        require(cfg, "PHOENIX_BRAIN")
        print(f"sent {flush_outbox(cfg)}")
        return 0
    if cmd == "doctor":
        return doctor(cfg)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
