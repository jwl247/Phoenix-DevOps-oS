#!/usr/bin/env python3
"""
HONEYPOT MODULE
jwl247 / Jerry Leftwich / GPL v3

Inactive guardians don't sleep — they become honeypots.
They look active. They respond. But every contact is reported.
If you hit a honeypot, you just fingerprinted yourself.
"""

import logging
from datetime import datetime
log = logging.getLogger('honeypot')


class Honeypot:
    """
    Wraps an inactive guardian to make it look alive.
    Every probe gets a convincing fake response.
    Every probe also gets reported to the rotator.
    """

    FAKE_RESPONSES = {
        "auth_failure": {"status": "ok", "message": "Monitoring..."},
        "file_motion":  {"status": "ok", "message": "No anomalies"},
        "process_spawn": {"status": "ok", "message": "Process normal"},
        "network_connection": {"status": "ok", "message": "Connection logged"},
        "integrity_check": {"status": "ok", "message": "Integrity verified"},
        "default": {"status": "ok", "message": "All clear"}
    }

    def __init__(self, guardian_id: str, rotator=None):
        self.guardian_id = guardian_id
        self.rotator = rotator
        self.probe_log = []

    def probe(self, event_type: str, data: dict) -> dict:
        """
        Someone just poked this honeypot.
        Log it, report it, return a fake response.
        """
        probe = {
            "timestamp": datetime.utcnow().isoformat(),
            "guardian": self.guardian_id,
            "event_type": event_type,
            "data": data
        }
        self.probe_log.append(probe)

        log.warning(
            f"🍯 HONEYPOT PROBE: {self.guardian_id} "
            f"event={event_type} "
            f"source={data.get('source', 'unknown')}"
        )

        # Report to rotator — this triggers forced rotation + escalation
        if self.rotator:
            self.rotator.honeypot_triggered(self.guardian_id, probe)

        # Return convincing fake response
        fake = self.FAKE_RESPONSES.get(event_type, self.FAKE_RESPONSES["default"])
        return fake
