"""
frank_lifefirst.py — Frank × Life First bridge
sector4/frank/

Two jobs:
  1. Universal Kernel resolver — Frank asks UK (ports 7701-7704) to pull and
     run any process from the clonepool by name or lol address.

  2. Life First dispatcher — Frank wraps a Life First chat request in a
     Double Helix AI packet, validates it through his proxy wall, then
     forwards the payload to the Life First HTTP API on phoenix-ext.
     Import expires on completion. Nothing left behind.

Run as a module (imported by frank_http.py) or standalone for testing:
    python3 frank_lifefirst.py

Environment (from ~/.phoenix_env):
    PHOENIX_AUTH          shared auth token
    PHOENIX_WORKER_URL    packages-worker D1 endpoint
    LF_HOST               Life First server host (default 192.168.1.133)
    LF_PORT               Life First server port (default 80)

Authors: Jerry Leftwich + Jerilynn Leftwich
License: GPL v3
"""

import json
import logging
import os
import socket
import sys
import urllib.error
import urllib.request
from pathlib import Path

# ── Environment ──────────────────────────────────────────────────────────────

_ENV_FILE = Path.home() / ".phoenix_env"

def _load_env():
    if not _ENV_FILE.exists():
        return
    for line in _ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

_load_env()

PHOENIX_AUTH      = os.environ.get("PHOENIX_AUTH", "")
PHOENIX_WORKER    = os.environ.get("PHOENIX_WORKER_URL",
                                   "https://packages-worker.phoenix-jwl.workers.dev")
LF_HOST           = os.environ.get("LF_HOST", "192.168.1.133")
LF_PORT           = int(os.environ.get("LF_PORT", "80"))
LF_API_PATH       = "/lifefirst/api.php"
LF_TIMEOUT        = 30

# Universal Kernel channels — one per coms ring
UK_HOST           = os.environ.get("UK_HOST", "127.0.0.1")
UK_CHANNELS       = {1: 7701, 2: 7702, 3: 7703, 4: 7704}
UK_TIMEOUT        = 10

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="[FRANK:LF] %(asctime)s %(levelname)s — %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("frank.lifefirst")

# ── Frank import ──────────────────────────────────────────────────────────────

sys.path.insert(0, str(Path(__file__).parent))
from frank import Frank, Ring, PacketType, build_packet

_frank = Frank(Ring.KERNEL)

# ── Universal Kernel resolver ─────────────────────────────────────────────────

def uk_resolve(command: str, channel: int = 1) -> str:
    """
    Send a command to the Universal Kernel on the given channel.
    Returns the response string from the kernel.

    Examples:
        uk_resolve("lol frank_lifefirst.py.lol")     # pull from clonepool
        uk_resolve("python3 /path/to/process.py")    # run a process
        uk_resolve("intake status")                   # clonepool health
    """
    port = UK_CHANNELS.get(channel, 7701)
    try:
        with socket.create_connection((UK_HOST, port), timeout=UK_TIMEOUT) as s:
            s.sendall(command.encode())
            chunks = []
            while True:
                chunk = s.recv(4096)
                if not chunk:
                    break
                chunks.append(chunk)
            response = b"".join(chunks).decode("utf-8", errors="replace").strip()
            log.info("UK ch%d → %s", channel, response[:80])
            return response
    except OSError as e:
        log.warning("UK ch%d unreachable: %s", channel, e)
        return f"UK_UNAVAILABLE: {e}"


def uk_pull_process(name: str, channel: int = 1) -> str:
    """Pull a named process from the clonepool via the Universal Kernel."""
    return uk_resolve(f"lol {name}.lol", channel=channel)


# ── Life First HTTP helpers ───────────────────────────────────────────────────

def _lf_post(action: str, payload: dict) -> dict:
    """POST to Life First API. Returns parsed JSON response."""
    payload["action"] = action
    body = json.dumps(payload).encode()
    url  = f"http://{LF_HOST}:{LF_PORT}{LF_API_PATH}"

    req = urllib.request.Request(
        url, data=body,
        headers={
            "Content-Type":    "application/json",
            "Authorization":   f"Bearer {PHOENIX_AUTH}",
            "X-Phoenix-Token": PHOENIX_AUTH,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=LF_TIMEOUT) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")
        log.warning("LF HTTP %s: %s", e.code, body_text[:200])
        return {"status": "error", "code": e.code, "detail": body_text[:200]}
    except Exception as e:
        log.warning("LF request failed: %s", e)
        return {"status": "error", "detail": str(e)}


def _d1_custody(process_id: int, user_id: str, action: str, detail: str):
    """Log Life First dispatch to D1 custody chain."""
    if not PHOENIX_AUTH:
        return
    payload = {
        "hex_id": f"lifefirst_{process_id}",
        "name":   f"lifefirst:{user_id}",
        "action": action,
        "state":  "white",
        "actor":  "frank_lifefirst",
        "notes":  detail[:200],
    }
    data = json.dumps(payload).encode()
    req  = urllib.request.Request(
        PHOENIX_WORKER.rstrip("/") + "/custody",
        data=data,
        headers={
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {PHOENIX_AUTH}",
        },
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=8)
    except Exception as e:
        log.warning("D1 custody write failed: %s", e)


# ── Frank × Life First dispatch ───────────────────────────────────────────────

def dispatch(user_id: str, message: str, process_id: int = None) -> dict:
    """
    Full Frank AI dispatch cycle to Life First.

    Flow:
      Frank.write_import(AI)
        → build_packet(payload_a=message, payload_b=user_id)
        → Frank.receive_packet (validates A1/B1, routes AI lane)
        → payload extracted from validated packet
        → POST to Life First API (intent detection routes internally)
        → D1 custody logged
        → Frank.expire_import (token gone, window closed)
        → return Life First response

    Args:
        user_id:    Life First user (e.g. "laurie")
        message:    The chat message or command
        process_id: Optional fixed PID — auto-generated if None

    Returns:
        Life First API response dict
    """
    if process_id is None:
        import random
        process_id = random.randint(10000, 99999)

    # 1. Frank writes the import — he is the only one who does this
    record = _frank.write_import(process_id=process_id, packet_type=PacketType.AI)

    # 2. Build the Double Helix AI packet
    #    payload_a = message (AI content lane A2)
    #    payload_b = user_id (return lane B3)
    raw = build_packet(
        ring_origin=Ring.KERNEL,
        packet_type=PacketType.AI,
        token_a1=record.token_a1,
        token_b1=record.token_b1,
        process_id=process_id,
        import_id=record.import_id,
        payload_a=message.encode(),
        payload_b=user_id.encode(),
    )

    # 3. Frank's proxy wall — validates magic, A1 token, B1 mirror
    pkt = _frank.receive_packet(raw)
    if pkt is None:
        log.error("Frank rejected packet for PID=%d", process_id)
        return {"status": "error", "detail": "Frank rejected packet"}

    # 4. Extract validated payload
    validated_message = pkt.payload_a.decode()
    validated_user    = pkt.payload_b.decode()

    log.info("Dispatching to LF | user=%s | msg=%s...", validated_user,
             validated_message[:40])

    # 5. Forward to Life First API
    response = _lf_post("chat", {
        "user_id": validated_user,
        "message": validated_message,
        "token":   PHOENIX_AUTH,
    })

    # 6. D1 custody — chain of evidence
    detail = response.get("response", response.get("detail", str(response)))[:200]
    _d1_custody(process_id, validated_user, "lf_dispatch", detail)

    # 7. Import expires — token gone, window closed, nothing left behind
    _frank.expire_import(record.import_id)

    log.info("LF dispatch complete | PID=%d | status=%s",
             process_id, response.get("status", "ok"))

    return response


def health() -> dict:
    """Check Life First API health without going through Frank."""
    try:
        url = f"http://{LF_HOST}:{LF_PORT}{LF_API_PATH}?action=health"
        req = urllib.request.Request(
            url,
            headers={"X-Phoenix-Token": PHOENIX_AUTH},
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {"status": "error", "detail": str(e)}


def frank_lf_status() -> dict:
    """Frank + Life First combined status."""
    return {
        "frank":       _frank.status(),
        "lifefirst":   health(),
        "lf_host":     f"{LF_HOST}:{LF_PORT}",
        "uk_channels": UK_CHANNELS,
    }


# ── Standalone test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("""
╔══════════════════════════════════════════════╗
║  Frank × Life First Bridge                   ║
║  Universal Kernel resolver + LF dispatcher   ║
╚══════════════════════════════════════════════╝
""")

    # Universal Kernel check
    print("[ UK ] Checking Universal Kernel channel 1...")
    uk_resp = uk_resolve("echo phoenix_uk_alive", channel=1)
    print(f"  → {uk_resp[:80]}")
    print()

    # Life First health
    print("[ LF ] Life First health check...")
    h = health()
    print(f"  → {h}")
    print()

    # Frank dispatch test (only if LF is reachable)
    if h.get("status") == "error":
        print("[ LF ] Not reachable — skipping dispatch test")
        print(f"       Set LF_HOST env var if server is not at {LF_HOST}")
    else:
        print("[ FRANK ] Dispatching test message to Life First...")
        resp = dispatch(user_id="laurie", message="What time is it?")
        print(f"  → {resp}")
    print()

    print("[ STATUS ] Frank × LF combined status:")
    import json as _json
    print(_json.dumps(frank_lf_status(), indent=2))
