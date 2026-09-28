#!/usr/bin/env python3
"""test_peer_chain.py — Romeo -> Juliet with signing, ports, rejection and
clean stop, on one box (loopback), the way the two clones run on two boxes.
Exit code = failures.   python3 tools/helix-team/test_peer_chain.py"""
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import uuid

import zmq

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RJ = os.path.join(ROOT, "sector3", "romeo_juliet")
TMP = tempfile.mkdtemp(prefix="peer-chain-")
SECRET = "test-secret-" + uuid.uuid4().hex
failures = 0
procs = []


def t(name, fn):
    global failures
    try:
        fn(); print(f"  ok  {name}")
    except Exception as e:  # noqa: BLE001
        failures += 1; print(f"FAIL  {name}\n      {type(e).__name__}: {e}")


def env(**extra):
    e = dict(os.environ, HOME=TMP, PYTHONUNBUFFERED="1",
             TRANSLATOR_SH=os.path.join(ROOT, "sector3", "translator", "translator.sh"))
    e.update({k: str(v) for k, v in extra.items()})
    return e


def start(script, *args, **extra):
    """Start a romeo/juliet process with a reader thread feeding its stdout
    lines into a queue, so waiting for a line can time out (a TextIOWrapper
    over a pipe holds lines select() cannot see)."""
    import queue, threading
    p = subprocess.Popen([sys.executable, os.path.join(RJ, script), *args], env=env(**extra),
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    p.lines = queue.Queue()
    p.seen = []

    def _reader():
        for line in p.stdout:
            p.lines.put(line)
        p.lines.put(None)

    threading.Thread(target=_reader, daemon=True).start()
    procs.append(p)
    return p


def wait_log(p, needle, timeout=15):
    import queue
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            line = p.lines.get(timeout=0.25)
        except queue.Empty:
            continue
        if line is None:
            break
        p.seen.append(line)
        if needle in line:
            return "".join(p.seen)
    raise AssertionError(f"'{needle}' not seen (rc={p.poll()}); got:\n" + "".join(p.seen)[-1500:])


def push(port, msg):
    ctx = zmq.Context.instance()
    s = ctx.socket(zmq.PUSH); s.setsockopt(zmq.LINGER, 1000); s.connect(f"tcp://127.0.0.1:{port}")
    time.sleep(0.3); s.send_json(msg); s.close()


def pull(port, want_id, timeout=15):
    ctx = zmq.Context.instance()
    s = ctx.socket(zmq.PULL); s.setsockopt(zmq.RCVTIMEO, 500); s.connect(f"tcp://127.0.0.1:{port}")
    deadline = time.time() + timeout
    try:
        while time.time() < deadline:
            try:
                m = s.recv_json()
            except zmq.Again:
                continue
            if m.get("id") == want_id:
                return m
    finally:
        s.close()
    return None


# ---------------------------------------------------------------- tests
def juliet_refuses_offloopback_without_secret():
    p = start("juliet.py", PHOENIX_RJ_BIND="0.0.0.0")
    out = wait_log(p, "refusing to bind", 10)
    p.terminate(); p.wait(10)
    assert "PHOENIX_RJ_SECRET" in out


juliet = romeo = None


def chain_comes_up():
    global juliet, romeo
    juliet = start("juliet.py", PHOENIX_RJ_SECRET=SECRET)
    wait_log(juliet, "signed messages only")
    romeo = start("romeo.py", PHOENIX_RJ_SECRET=SECRET, PHOENIX_RJ_PEER="127.0.0.1:5581")
    wait_log(romeo, "ingress active")
    wait_log(romeo, "signed")


def signed_message_crosses_untranslated():
    mid = "chain-" + uuid.uuid4().hex[:8]
    push(5580, {"id": mid, "type": "status_ping", "source": "test"})
    m = pull(5582, mid)
    assert m and m["translated"] is False and m["platform"] == "quad", m


def package_message_is_translated_on_output():
    mid = "chain-" + uuid.uuid4().hex[:8]
    push(5580, {"id": mid, "type": "package_list", "verb": "list", "package": "", "source": "test"})
    m = pull(5582, mid, timeout=40)
    assert m and m["translated"] is True, m


def unsigned_message_is_rejected_by_juliet():
    mid = "forged-" + uuid.uuid4().hex[:8]
    push(5581, {"id": mid, "type": "package_install", "verb": "install", "package": "evil", "source": "attacker"})
    assert pull(5582, mid, timeout=4) is None, "forged message reached egress"
    out = wait_log(juliet, "REJECTED", 10)
    assert "signature" in out


def replayed_message_is_rejected():
    """Capture a signed message on the wire (a PULL on Romeo's peer port would
    be the attacker) and play it into Juliet again: same sig, same id."""
    import hmac, hashlib
    from datetime import datetime
    mid = "replay-" + uuid.uuid4().hex[:8]
    body = {"id": mid, "type": "status_ping", "source": "test", "romeo_ts": datetime.utcnow().isoformat(), "romeo_count": 1}
    canon = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode()
    body["sig"] = hmac.new(SECRET.encode(), canon, hashlib.sha256).hexdigest()
    push(5581, body)                                   # first delivery, valid
    assert pull(5582, mid), "a freshly signed message was refused"
    push(5581, body)                                   # replay
    assert pull(5582, mid, timeout=4) is None, "replayed message reached egress"
    wait_log(juliet, "REJECTED id=" + mid, 10)
    stale = dict(body); stale["id"] = mid + "-old"; stale["romeo_ts"] = "2020-01-01T00:00:00"
    canon = json.dumps({k: v for k, v in stale.items() if k != "sig"}, sort_keys=True, separators=(",", ":"), default=str).encode()
    stale["sig"] = hmac.new(SECRET.encode(), canon, hashlib.sha256).hexdigest()
    push(5581, stale)
    assert pull(5582, stale["id"], timeout=4) is None, "stale-timestamp message reached egress"


def romeo_rejects_pre_translated():
    mid = "pre-" + uuid.uuid4().hex[:8]
    push(5580, {"id": mid, "type": "package_list", "pre_translated": True})
    wait_log(romeo, "Rejected: pre-translated", 10)


def barrel_two_ports_do_not_collide():
    j2 = start("juliet.py", "--barrel", "2", PHOENIX_RJ_SECRET=SECRET)
    out = wait_log(j2, "Egress", 10)
    assert ":5583" in out and ":5584" in out, out
    j2.terminate(); j2.wait(10)


def sigterm_stops_both():
    romeo.terminate(); juliet.terminate()
    romeo.wait(10); juliet.wait(10)
    assert romeo.returncode == 0 and juliet.returncode == 0, (romeo.returncode, juliet.returncode)


try:
    t("juliet refuses to bind off-loopback without a secret", juliet_refuses_offloopback_without_secret)
    t("romeo + juliet come up, signed hop", chain_comes_up)
    t("a signed message crosses untranslated (non-package)", signed_message_crosses_untranslated)
    t("a package_* message is translated on output", package_message_is_translated_on_output)
    t("an unsigned message straight at juliet is rejected", unsigned_message_is_rejected_by_juliet)
    t("a replayed or stale signed message is rejected", replayed_message_is_rejected)
    t("romeo rejects pre-translated payloads", romeo_rejects_pre_translated)
    t("barrel 2 gets 5583/5584 (no collision with barrel 1)", barrel_two_ports_do_not_collide)
    t("SIGTERM stops both cleanly", sigterm_stops_both)
finally:
    for p in procs:
        if p.poll() is None:
            p.kill()
print(f"\n{9 - failures} passing, {failures} failing")
sys.exit(failures)
