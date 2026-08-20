#!/usr/bin/env python3
"""
GUARDIAN ROTATOR — CoPES Security Core
jwl247 / Jerry Leftwich / GPL v3

Only one guardian is active at any time.
Inactive guardians run as honeypots — they look active but aren't.
Rotation is randomized so attackers can't predict who's watching.
If you hit an inactive guardian (honeypot), you just told us everything.
"""

import random
import time
import threading
import logging
from datetime import datetime
from enum import Enum

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [ROTATOR] %(message)s'
)
log = logging.getLogger('guardian_rotator')


class GuardianID(Enum):
    ALPHA = "alpha"    # Auth-based — sector1
    BETA  = "beta"     # Process-based — sector2
    GAMMA = "gamma"    # Network/file-based — sector3
    DELTA = "delta"    # Custody/integrity-based — sector4


class GuardianRotator:
    """
    Rotates which guardian is active.
    Inactive guardians become honeypots.
    Rotation interval is randomized — never predictable.
    Event-based triggers can force immediate rotation.
    """

    def __init__(self, min_interval=180, max_interval=600):
        """
        min_interval: minimum seconds before rotation (default 3 min)
        max_interval: maximum seconds before rotation (default 10 min)
        """
        self.min_interval = min_interval
        self.max_interval = max_interval
        self.active_guardian = None
        self.rotation_count = 0
        self.incident_log = []
        self.running = False
        self._lock = threading.Lock()
        self._rotation_thread = None

        # Guardian registry — populated by register()
        self.guardians = {}

    def register(self, guardian_id: GuardianID, guardian_instance):
        """Register a guardian with the rotator"""
        self.guardians[guardian_id] = guardian_instance
        log.info(f"Registered guardian: {guardian_id.value}")

    def _pick_next(self) -> GuardianID:
        """Pick next active guardian — not the current one"""
        choices = [g for g in GuardianID if g != self.active_guardian]
        return random.choice(choices)

    def _next_interval(self) -> int:
        """Randomized rotation interval — unpredictable"""
        return random.randint(self.min_interval, self.max_interval)

    def rotate(self, reason="scheduled"):
        """Execute a guardian rotation"""
        with self._lock:
            previous = self.active_guardian
            next_guardian = self._pick_next()

            # Deactivate current — send to honeypot mode
            if previous and previous in self.guardians:
                self.guardians[previous].go_honeypot()

            # Activate next
            self.active_guardian = next_guardian
            if next_guardian in self.guardians:
                self.guardians[next_guardian].go_active()

            self.rotation_count += 1

            log.info(
                f"🔄 Rotation #{self.rotation_count} [{reason}] "
                f"{previous.value if previous else 'none'} → {next_guardian.value}"
            )

            return {
                "rotation": self.rotation_count,
                "previous": previous.value if previous else None,
                "active": next_guardian.value,
                "reason": reason,
                "timestamp": datetime.utcnow().isoformat()
            }

    def force_rotate(self, reason="incident"):
        """Immediate rotation — triggered by detection event"""
        log.warning(f"⚡ FORCED ROTATION: {reason}")
        return self.rotate(reason=reason)

    def honeypot_triggered(self, guardian_id: GuardianID, incident_data: dict):
        """
        Called when an inactive guardian (honeypot) is triggered.
        This means someone is probing — they hit the wrong guardian.
        We have their fingerprint. Force rotate and escalate.
        """
        log.warning(
            f"🍯 HONEYPOT TRIGGERED: {guardian_id.value} — "
            f"Attacker fingerprinted. Escalating."
        )

        incident = {
            "type": "honeypot_triggered",
            "guardian": guardian_id.value,
            "data": incident_data,
            "timestamp": datetime.utcnow().isoformat()
        }
        self.incident_log.append(incident)

        # Force immediate rotation — they hit the old position, move now
        self.force_rotate(reason=f"honeypot_{guardian_id.value}")

        # Return incident for upstream handling (buffer escalation etc)
        return incident

    def _rotation_loop(self):
        """Background rotation thread"""
        # Initial activation
        self.rotate(reason="startup")

        while self.running:
            interval = self._next_interval()
            log.info(f"⏱  Next rotation in {interval}s")
            time.sleep(interval)
            if self.running:
                self.rotate(reason="scheduled")

    def start(self):
        """Start the rotation engine"""
        if not self.guardians:
            raise RuntimeError("No guardians registered. Register at least one.")
        self.running = True
        self._rotation_thread = threading.Thread(
            target=self._rotation_loop,
            daemon=True,
            name="guardian_rotator"
        )
        self._rotation_thread.start()
        log.info("🔥 Guardian Rotator started")

    def stop(self):
        """Stop the rotation engine"""
        self.running = False
        log.info("Guardian Rotator stopped")

    def status(self) -> dict:
        return {
            "active_guardian": self.active_guardian.value if self.active_guardian else None,
            "rotation_count": self.rotation_count,
            "incident_count": len(self.incident_log),
            "guardians_registered": len(self.guardians),
            "running": self.running
        }
