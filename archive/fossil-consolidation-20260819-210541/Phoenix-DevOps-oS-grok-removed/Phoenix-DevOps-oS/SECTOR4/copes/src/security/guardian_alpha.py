#!/usr/bin/env python3
"""
GUARDIAN ALPHA — Auth-based detection
Sector 1: Boot, GRUB, kernel, phoenix_auth
jwl247 / Jerry Leftwich / GPL v3
"""

import logging
from guardian_base import GuardianBase
log = logging.getLogger('guardian_alpha')


class GuardianAlpha(GuardianBase):
    def __init__(self, rotator=None):
        super().__init__("alpha", rotator)
        self.failed_auth_count = 0
        self.failed_auth_threshold = 3

    def _get_enum_id(self):
        from guardian_rotator import GuardianID
        return GuardianID.ALPHA

    def _detect(self, data: dict) -> dict:
        event_type = data.get("type", "")

        if event_type == "auth_failure":
            self.failed_auth_count += 1
            log.warning(
                f"[ALPHA] Auth failure #{self.failed_auth_count} "
                f"from {data.get('source', 'unknown')}"
            )
            if self.failed_auth_count >= self.failed_auth_threshold:
                log.warning("[ALPHA] Threshold reached — escalating")
                self.failed_auth_count = 0
                return {
                    "status": "escalate",
                    "guardian": "alpha",
                    "reason": "repeated_auth_failure",
                    "data": data
                }

        elif event_type == "auth_success":
            self.failed_auth_count = 0

        elif event_type == "kernel_tamper":
            log.critical(f"[ALPHA] KERNEL TAMPER DETECTED: {data}")
            return {
                "status": "escalate",
                "guardian": "alpha",
                "reason": "kernel_tamper",
                "data": data
            }

        return {"status": "ok", "guardian": "alpha"}

    def _on_activate(self):
        self.failed_auth_count = 0
        log.info("[ALPHA] Auth monitoring armed")

    def _on_honeypot(self):
        self.failed_auth_count = 0
        log.info("[ALPHA] Honeypot mode — faking auth responses")
