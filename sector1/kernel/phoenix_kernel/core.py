#!/usr/bin/env python3
"""
Phoenix Universal Kernel Core - Production Ready & Cross-Platform
Phoenix DevOps OS | jwl247 | GPL v3
"""

import socket
import threading
import subprocess
import logging
import time
import signal
import sys
import os
from pathlib import Path
from typing import Optional

# Cross-platform log directory
if os.name == 'nt':  # Windows
    LOG_DIR = Path(os.getenv("LOCALAPPDATA", "~/.phoenix")) / "phoenix" / "logs"
else:  # Linux / macOS
    LOG_DIR = Path.home() / ".phoenix" / "logs"

LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "phoenix_kernel.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [PHOENIX] %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE, mode='a', encoding='utf-8')
    ]
)
log = logging.getLogger("phoenix")

class PhoenixKernel:
    def __init__(self, config: dict = None):
        self._alive = True
        self.config = config or {"timeout": 60, "max_output": 200000}
        self._setup_signals()

    def _setup_signals(self):
        signal.signal(signal.SIGTERM, self._shutdown)
        signal.signal(signal.SIGINT, self._shutdown)

    def start(self):
        log.info("🚀 Phoenix Universal Kernel v1.0 (Cross-Platform) Starting...")
        log.info(f"Logs: {LOG_FILE}")
        
        for ch in range(1, 5):
            port = 7700 + ch
            t = threading.Thread(target=self._listener, args=(ch, port), daemon=True)
            t.start()
            log.info(f"✅ Channel {ch} listening on 0.0.0.0:{port}")

        try:
            while self._alive:
                time.sleep(30)
        except Exception as e:
            log.error(f"Main loop error: {e}")

    def _listener(self, channel: int, port: int):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("0.0.0.0", port))
            sock.listen(20)
        except Exception as e:
            log.error(f"Failed to bind port {port}: {e}")
            return

        while self._alive:
            try:
                conn, addr = sock.accept()
                data = conn.recv(65536).decode('utf-8', errors='ignore').strip()
                if data:
                    log.info(f"🚀 INTAKE ch{channel} from {addr[0]}: {data[:200]}")
                    output = self._safe_execute(data)
                    response = f"✅ Phoenix executed:\n{output}\n"
                    conn.sendall(response.encode())
                conn.close()
            except Exception as e:
                if self._alive:
                    log.error(f"ch{channel} error: {e}")

    def _safe_execute(self, cmd: str) -> str:
        """Safe cross-platform execution"""
        dangerous = ['rm -rf /', 'dd if=', '> /dev/sd', 'format', 'mkfs']
        if any(d in cmd.lower() for d in dangerous):
            return "❌ Blocked: Dangerous command detected"

        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=self.config["timeout"]
            )
            output = (result.stdout + result.stderr).strip()[:self.config["max_output"]]
            return f"{output or '(no output)'}\n\n[Return Code: {result.returncode}]"
        except subprocess.TimeoutExpired:
            return "❌ Command timed out (60s)"
        except Exception as e:
            return f"❌ Error: {e}"

    def _shutdown(self, signum=None, frame=None):
        log.info("Phoenix Kernel shutting down gracefully...")
        self._alive = False
        sys.exit(0)

if __name__ == "__main__":
    kernel = PhoenixKernel()
    kernel.start()
