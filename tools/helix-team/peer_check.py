#!/usr/bin/env python3
"""peer_check.py — prove the ingress -> egress hop end to end.

  peer_check.py send   --romeo HOST:5580 [--type package_list]   push one message into Romeo
  peer_check.py listen --juliet HOST:5582 [--timeout 20]         pull Juliet's egress, print what arrives
  peer_check.py both   [--romeo ...] [--juliet ...]               listen, then send, then assert (single box or two)

Exit 0 only when the message we sent comes out of Juliet with the same id,
and — for package_* types — with translated=true (translator.sh fired on
output). Romeo signs the hop when PHOENIX_RJ_SECRET is set on its box; this
tool does not need the secret: it talks to Romeo's ingress side, which is
loopback-only, or to Juliet's egress side, which is the translated output.
"""
import argparse
import json
import sys
import threading
import time
import uuid

import zmq


def send(romeo, mtype, verb="list", package=""):
    ctx = zmq.Context.instance()
    s = ctx.socket(zmq.PUSH)
    s.setsockopt(zmq.LINGER, 2000)
    s.connect(f"tcp://{romeo}")
    mid = f"peer-check-{uuid.uuid4().hex[:12]}"
    msg = {"id": mid, "type": mtype, "verb": verb, "package": package, "source": "peer_check",
           "sent_at": time.time()}
    time.sleep(0.3)  # let the connect settle before the first push
    s.send_json(msg)
    s.close()
    return mid


def listen(juliet, want_id=None, timeout=20.0, stop=None):
    ctx = zmq.Context.instance()
    s = ctx.socket(zmq.PULL)
    s.setsockopt(zmq.RCVTIMEO, 500)
    s.connect(f"tcp://{juliet}")
    deadline = time.time() + timeout
    seen = []
    try:
        while time.time() < deadline and not (stop and stop.is_set()):
            try:
                m = s.recv_json()
            except zmq.Again:
                continue
            seen.append(m)
            print(f"  egress: id={m.get('id')} type={m.get('type')} translated={m.get('translated')} "
                  f"platform={m.get('platform')} barrel={m.get('barrel')}", flush=True)
            if want_id is None or m.get("id") == want_id:
                if want_id is not None:
                    return m
    finally:
        s.close()
    return None if want_id else seen


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["send", "listen", "both"])
    ap.add_argument("--romeo", default="127.0.0.1:5580")
    ap.add_argument("--juliet", default="127.0.0.1:5582")
    ap.add_argument("--type", default="package_list")
    ap.add_argument("--timeout", type=float, default=20.0)
    a = ap.parse_args()

    if a.mode == "send":
        print(f"sent {send(a.romeo, a.type)} -> romeo {a.romeo}")
        return 0
    if a.mode == "listen":
        listen(a.juliet, None, a.timeout)
        return 0

    result = {}
    ready = threading.Event()

    def _listen():
        ready.set()
        result["msg"] = listen(a.juliet, result.get("id_holder", [None])[0] if False else None, a.timeout, stop=None) \
            if False else None

    # listen first (PULL connect), then send, then wait for our id
    got = {}
    stop = threading.Event()

    def _l():
        got["msg"] = listen(a.juliet, want["id"], a.timeout, stop)

    want = {"id": None}
    want["id"] = f"pending"
    t = threading.Thread(target=_l, daemon=True)
    # set the id before the thread compares anything
    mid = send(a.romeo, a.type) if False else None
    want["id"] = None
    mid = f"peer-check-{uuid.uuid4().hex[:12]}"
    want["id"] = mid
    t.start()
    time.sleep(0.5)
    ctx = zmq.Context.instance()
    s = ctx.socket(zmq.PUSH); s.setsockopt(zmq.LINGER, 2000); s.connect(f"tcp://{a.romeo}")
    time.sleep(0.3)
    s.send_json({"id": mid, "type": a.type, "verb": "list", "package": "", "source": "peer_check", "sent_at": time.time()})
    s.close()
    print(f"sent {mid} -> romeo {a.romeo}; waiting on juliet {a.juliet}", flush=True)
    t.join(a.timeout + 2)
    m = got.get("msg")
    if not m:
        print("FAIL: nothing with our id came out of Juliet"); return 1
    if a.type.startswith("package_") and not m.get("translated"):
        print("FAIL: package_* message left Juliet untranslated (translator.sh did not fire on output)"); return 2
    if not a.type.startswith("package_") and m.get("translated"):
        print("FAIL: non-package message was translated (translation must be output-only for package types)"); return 3
    print(f"PASS: {mid} crossed ingress -> egress (translated={m.get('translated')}, platform={m.get('platform')})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
