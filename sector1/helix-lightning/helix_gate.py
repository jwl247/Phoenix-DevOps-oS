#!/usr/bin/env python3
"""
helix_gate.py — the gate on Helix-I / Helix-E sockets.
Phoenix DevOps OS | jwl247 | GPL v3

The Helix sockets had no authentication: anything that could reach 7701-7704
could feed Frank, anything reaching 7805-7808 could read his output. Fine on
loopback; not fine on the mesh (the phone node, 2026-10-03).

  HELIX_SOCKET_TOKEN  shared secret. When set, a client's first line must be
                      "HXT <token>\\n" — compared constant-time — or the
                      connection is dropped and logged. Unset = no handshake
                      (loopback-only use, as before).
  Fail closed:        binding a Helix socket to anything but loopback WITHOUT
                      a token is refused — the socket stays on 127.0.0.1 and
                      a CRITICAL line says why.

The token comes from the environment (an EnvironmentFile / phoenix.env, mode
0600), never from a command line.
"""

import hmac
import logging
import os
import socket

log = logging.getLogger("helix_gate")

PREFIX = b"HXT "
MAX_LINE = 256
HANDSHAKE_TIMEOUT_S = 5.0


def token() -> bytes:
    return os.environ.get("HELIX_SOCKET_TOKEN", "").strip().encode()


def safe_bind(addr: str, who: str) -> str:
    """The address to actually bind: refuses non-loopback without a token."""
    if addr in ("127.0.0.1", "localhost", "::1"):
        return addr
    if not token():
        log.critical("%s: refusing to listen on %s without HELIX_SOCKET_TOKEN — staying on 127.0.0.1", who, addr)
        return "127.0.0.1"
    return addr


def check(conn: socket.socket, addr, who: str) -> bytes:
    """Run the handshake on a fresh connection.

    Returns any payload bytes that arrived after the token line (b"" if none),
    or raises PermissionError (caller closes the connection). With no token
    configured it returns b"" immediately and reads nothing.
    """
    tok = token()
    if not tok:
        return b""
    conn.settimeout(HANDSHAKE_TIMEOUT_S)
    buf = b""
    try:
        while b"\n" not in buf and len(buf) <= MAX_LINE:
            got = conn.recv(MAX_LINE + 1 - len(buf))
            if not got:
                break
            buf += got
    except socket.timeout:
        pass
    finally:
        conn.settimeout(None)
    line, _, rest = buf.partition(b"\n")
    if not (line.startswith(PREFIX) and hmac.compare_digest(line[len(PREFIX):].strip(), tok)):
        log.warning("%s: rejected connection from %s (bad or missing token)", who, addr)
        raise PermissionError("bad helix token")
    return rest
