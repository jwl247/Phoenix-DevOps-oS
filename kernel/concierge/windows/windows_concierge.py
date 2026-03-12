#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║  Windows Concierge — Phoenix-DevOps-oS                      ║
║  Runs on Windows side. Peers with Linux concierge            ║
║  through the bridge kernel.                                  ║
║                                                              ║
║  Accepts connections from any Windows input source.         ║
║  Win10, distros via Ventoy, any Windows process.            ║
║  Hands raw data up. Returns native output. No translation.  ║
╚══════════════════════════════════════════════════════════════╝
"""

import os
import sys
import json
import socket
import threading
import time

BRIDGE_HOST = os.environ.get("PHOENIX_BRIDGE_HOST", "127.0.0.1")
BRIDGE_PORT = int(os.environ.get("PHOENIX_BRIDGE_PORT", "9900"))
LISTEN_HOST = os.environ.get("PHOENIX_WIN_HOST", "127.0.0.1")
LISTEN_PORT = int(os.environ.get("PHOENIX_WIN_PORT", "9901"))


class WindowsConcierge:
    """
    The Windows side of the bridge.
    Accepts raw input from any Windows source.
    Forwards to bridge kernel. Returns native output.
    Symmetric to Linux concierge — same protocol, different side.
    """

    def __init__(self):
        self._running = False
        self._sock    = None

    def start(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((LISTEN_HOST, LISTEN_PORT))
        self._sock.listen(64)
        self._running = True

        print(f"[windows-concierge] listening on {LISTEN_HOST}:{LISTEN_PORT}", flush=True)

        while self._running:
            try:
                conn, addr = self._sock.accept()
                threading.Thread(
                    target=self._handle,
                    args=(conn, addr),
                    daemon=True
                ).start()
            except OSError:
                break

    def _handle(self, conn: socket.socket, addr):
        """
        One connection = one signal.
        Receive raw. Send to bridge. Return native output.
        No loops. Closes after one exchange.
        """
        try:
            chunks = []
            while True:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                chunks.append(chunk)

            raw = b"".join(chunks)
            if not raw:
                return

            # Parse source envelope if present, else raw windows signal
            try:
                env    = json.loads(raw)
                family = env.get("family", "system")
                source = env.get("source", "windows")
                data   = env.get("data", raw.decode(errors="replace"))
            except Exception:
                family = "system"
                source = "windows"
                data   = raw.decode(errors="replace")

            result = self._forward_to_bridge({
                "source": source,
                "family": family,
                "data":   data,
            })

            conn.sendall(json.dumps(result).encode())

        except Exception as exc:
            try:
                conn.sendall(json.dumps({"ok": False, "error": str(exc)}).encode())
            except Exception:
                pass
        finally:
            conn.close()

    def _forward_to_bridge(self, envelope: dict) -> dict:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(5.0)
                s.connect((BRIDGE_HOST, BRIDGE_PORT))
                s.sendall(json.dumps(envelope).encode())
                s.shutdown(socket.SHUT_WR)

                chunks = []
                while True:
                    chunk = s.recv(4096)
                    if not chunk:
                        break
                    chunks.append(chunk)

                return json.loads(b"".join(chunks))

        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def stop(self):
        self._running = False
        if self._sock:
            self._sock.close()


if __name__ == "__main__":
    c = WindowsConcierge()
    try:
        c.start()
    except KeyboardInterrupt:
        c.stop()
        print("[windows-concierge] stopped", flush=True)
