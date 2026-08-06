#!/usr/bin/env python3
"""
GUARDIAN BETA — Process-based detection
Sector 2: Intake, package handler, clone pool, Frank
jwl247 / Jerry Leftwich / GPL v3
"""

import logging
from guardian_base import GuardianBase
log = logging.getLogger('guardian_beta')

SUSPICIOUS_PROCESSES = ['nc', 'ncat', 'netcat', 'socat', 'proxychains']
SUSPICIOUS_USERS = ['nobody', 'www-data']


class GuardianBeta(GuardianBase):
    def __init__(self, rotator=None):
        super().__init__("beta", rotator)

    def _get_enum_id(self):
        from guardian_rotator import GuardianID
        return GuardianID.BETA

    def _detect(self, data: dict) -> dict:
        event_type = data.get("type", "")

        if event_type == "process_spawn":
            proc_name = data.get("name", "")
            proc_user = data.get("user", "")

            if any(s in proc_name for s in SUSPICIOUS_PROCESSES):
                log.warning(f"[BETA] Suspicious process: {proc_name} by {proc_user}")
                return {
                    "status": "escalate",
                    "guardian": "beta",
                    "reason": "suspicious_process",
                    "data": data
                }

            if proc_user in SUSPICIOUS_USERS and "intake" in data.get("path", ""):
                log.warning(f"[BETA] Suspicious intake access by {proc_user}")
                return {
                    "status": "escalate",
                    "guardian": "beta",
                    "reason": "suspicious_intake_access",
                    "data": data
                }

        elif event_type == "clone_pool_tamper":
            log.critical(f"[BETA] CLONE POOL TAMPER: {data}")
            return {
                "status": "escalate",
                "guardian": "beta",
                "reason": "clone_pool_tamper",
                "data": data
            }

        return {"status": "ok", "guardian": "beta"}

    def _on_activate(self):
        log.info("[BETA] Process monitoring armed")

    def _on_honeypot(self):
        log.info("[BETA] Honeypot mode — faking process responses")
