# 💎 GemIIIDev - System Artifact
"""
HELIX CORE - "THE WHALE"
Orchestrates the 3-Buffer Pipeline and monitors the Jonas Raw Segments.
"""
import os
import sys
import time
import json
import logging
import signal
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [WHALE] - %(message)s')

class JonasMonitor:
    """Monitors the raw LVM segments (Jonas) inside the Whale."""
    def __init__(self):
        self.segments = [f"/dev/gemiii_whale/jonas_data_{i}" for i in range(1, 5)]

    def check_segments(self):
        status = {}
        for seg in self.segments:
            exists = os.path.exists(seg)
            status[seg] = "ONLINE" if exists else "MISSING"
        return status

class HelixSystem:
    def __init__(self):
        self.active = True
        self.jonas = JonasMonitor()
        self.pid_file = "/tmp/helix_whale.pid"
        
        signal.signal(signal.SIGINT, self.handle_exit)
        signal.signal(signal.SIGTERM, self.handle_exit)

    def handle_exit(self, signum, frame):
        logging.info("Whale surfacing. Shutting down...")
        self.active = False

    def run(self):
        logging.info("🐋 HELIX THE WHALE INITIALIZED.")
        with open(self.pid_file, "w") as f:
            f.write(str(os.getpid()))

        while self.active:
            # Monitor the Raw Jonas Segments
            segments = self.jonas.check_segments()
            if all(s == "ONLINE" for s in segments.values()):
                logging.debug("All Jonas segments nominal.")
            else:
                logging.warning(f"Segment Alert: {segments}")
            
            # The heart of the RTS Engine pulses here
            time.sleep(2)

        if os.path.exists(self.pid_file):
            os.remove(self.pid_file)
        logging.info("Whale at rest.")

if __name__ == "__main__":
    system = HelixSystem()
    system.run()
