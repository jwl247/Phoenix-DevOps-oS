#!/usr/bin/env python3
"""
phoenix_core.py — Universal Execution Engine
Phoenix DevOps OS | jwl247 | GPL v3
"""

import socket
import threading
import subprocess
import logging
import time   # ← This was missing
import os
import hmac

logging.basicConfig(level=logging.INFO, format="%(asctime)s [PHOENIX] %(levelname)s %(message)s")
log = logging.getLogger("phoenix")

# This listener runs arbitrary shell commands for whoever connects, so it is
# loopback-only by default and a shared token is REQUIRED for any other bind.
# Client protocol when a token is set: first line "AUTH <token>", then the command.
BIND_HOST = os.environ.get("PHOENIX_KERNEL_BIND", "127.0.0.1")
AUTH_TOKEN = os.environ.get("PHOENIX_KERNEL_TOKEN", "")
if BIND_HOST not in ("127.0.0.1", "localhost", "::1") and not AUTH_TOKEN:
    raise SystemExit("PhoenixUniversal: refusing non-loopback bind without PHOENIX_KERNEL_TOKEN")


def _check_auth(data: str):
    """Return the command if authorized, else None."""
    if not AUTH_TOKEN:
        return data
    first, _, rest = data.partition("\n")
    if first.startswith("AUTH ") and hmac.compare_digest(first[5:].strip(), AUTH_TOKEN):
        return rest.strip()
    return None

class PhoenixUniversal:
    def __init__(self):
        self._alive = True

    def start(self):
        log.info("🌍 Phoenix Universal Kernel Started — Run ANY program from ANY PC")
        for ch in range(1, 5):
            port = 7700 + ch
            t = threading.Thread(target=self._listener, args=(ch, port), daemon=True, name=f"ch{ch}")
            t.start()
            log.info(f"✅ Channel {ch} listening on port {port}")

        try:
            while True:
                time.sleep(30)
        except KeyboardInterrupt:
            self._alive = False
            log.info("Phoenix Kernel shutdown complete")

    def _listener(self, channel: int, port: int):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((BIND_HOST, port))
        sock.listen(10)

        while self._alive:
            try:
                conn, addr = sock.accept()
                data = conn.recv(65536).decode('utf-8', errors='ignore').strip()
                if data and _check_auth(data) is None:
                    log.warning(f"ch{channel} rejected unauthenticated request from {addr[0]}")
                    conn.sendall(b"DENIED\n")
                    conn.close()
                    continue
                data = _check_auth(data) if data else data
                if data:
                    log.info(f"🚀 INTAKE ch{channel} from {addr[0]}: {data[:150]}")
                    output = self._run_command(data)
                    response = f"✅ Phoenix executed:\n{output}\n"
                    conn.sendall(response.encode())
                conn.close()
            except Exception as e:
                if self._alive:
                    log.error(f"ch{channel} error: {e}")

    def _run_command(self, cmd: str) -> str:
        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
            output = (result.stdout + result.stderr).strip() or "(no output)"
            return f"{output}\n\n[Return Code: {result.returncode}]"
        except subprocess.TimeoutExpired:
            return "❌ Command timed out (60 seconds)"
        except Exception as e:
            return f"❌ Execution error: {e}"

if __name__ == "__main__":
    print("Run with: python3 main_kernel.py")
