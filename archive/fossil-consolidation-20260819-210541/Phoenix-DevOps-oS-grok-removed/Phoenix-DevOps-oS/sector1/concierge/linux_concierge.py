#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║  Linux Concierge — Phoenix-DevOps-oS                        ║
║  Runs in Debian WSL.                                        ║
║                                                              ║
║  Receives from the bridge kernel via Unix socket.           ║
║  Hands raw data up. Receives native output back.            ║
║  Does not translate input. Does not interpret output.       ║
║  Just the channel.                                          ║
╚══════════════════════════════════════════════════════════════╝
"""

import os
import sys
import json
import socket
import threading
import time

SOCK_PATH  = os.environ.get("PHOENIX_LINUX_SOCK", "/tmp/phoenix_linux.sock")
BRIDGE_HOST = os.environ.get("PHOENIX_BRIDGE_HOST", "127.0.0.1")
BRIDGE_PORT = int(os.environ.get("PHOENIX_BRIDGE_PORT", "9900"))


class LinuxConcierge:
    """
    The Linux side of the bridge.
    Accepts connections from any Linux input source.
    Forwards raw data to the bridge kernel.
    Returns whatever the bridge sends back — no interpretation.
    """

    def __init__(self):
        self._running = False
        self._sock    = None

    def start(self):
        # Clean up stale socket
        if os.path.exists(SOCK_PATH):
            os.unlink(SOCK_PATH)

        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.bind(SOCK_PATH)
        self._sock.listen(64)          # dynamic capacity
        self._running = True

        print(f"[linux-concierge] listening on {SOCK_PATH}", flush=True)

        while self._running:
            try:
                conn, _ = self._sock.accept()
                threading.Thread(
                    target=self._handle,
                    args=(conn,),
                    daemon=True
                ).start()
            except OSError:
                break

    def _handle(self, conn: socket.socket):
        """
        One connection = one signal.
        Receive raw. Send to bridge. Return native output.
        No loops. Connection closes after one exchange.
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

            # Parse source envelope if present, else treat as raw system signal
            try:
                env    = json.loads(raw)
                family = env.get("family", "system")
                source = env.get("source", "linux")
                data   = env.get("data", raw.decode(errors="replace"))
            except Exception:
                family = "system"
                source = "linux"
                data   = raw.decode(errors="replace")

            # Forward to bridge
            result = self._forward_to_bridge({
                "source": source,
                "family": family,
                "data":   data,
            })

            # Return native output — only translation is here at output
            conn.sendall(json.dumps(result).encode())

        except Exception as exc:
            try:
                conn.sendall(json.dumps({"ok": False, "error": str(exc)}).encode())
            except Exception:
                pass
        finally:
            conn.close()

    def _forward_to_bridge(self, envelope: dict) -> dict:
        """
        Send to bridge kernel via TCP.
        Bridge handles the quadralingual lifecycle.
        We just carry the message.
        """
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
        if os.path.exists(SOCK_PATH):
            os.unlink(SOCK_PATH)


if __name__ == "__main__":
    c = LinuxConcierge()
    try:
        c.start()
    except KeyboardInterrupt:
        c.stop()
        print("[linux-concierge] stopped", flush=True)
