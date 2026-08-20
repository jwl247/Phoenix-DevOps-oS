#!/usr/bin/env python3
"""
GUARDIAN GAMMA — Network and file-based detection
Sector 3: Comms, romeo/juliet, quadengine, translator
jwl247 / Jerry Leftwich / GPL v3
Integrates with motion_sensor and buffer_escalation (JS modules via subprocess)
"""

import logging
from guardian_base import GuardianBase
log = logging.getLogger('guardian_gamma')

SOCKS5_PORTS = [1080, 9050, 4444, 31337]
SENSITIVE_PATHS = [
    '/etc/passwd', '/etc/shadow', '/root/.ssh',
    '/var/www/html', '/usr/bin', '/usr/sbin'
]


class GuardianGamma(GuardianBase):
    def __init__(self, rotator=None):
        super().__init__("gamma", rotator)

    def _get_enum_id(self):
        from guardian_rotator import GuardianID
        return GuardianID.GAMMA

    def _detect(self, data: dict) -> dict:
        event_type = data.get("type", "")

        if event_type == "file_motion":
            path = data.get("path", "")
            if any(path.startswith(s) for s in SENSITIVE_PATHS):
                log.warning(f"[GAMMA] Sensitive path motion: {path}")
                return {
                    "status": "escalate",
                    "guardian": "gamma",
                    "reason": "sensitive_path_motion",
                    "data": data
                }

        elif event_type == "network_connection":
            port = data.get("port", 0)
            if port in SOCKS5_PORTS:
                log.critical(f"[GAMMA] SOCKS5/PROXY DETECTED on port {port}")
                return {
                    "status": "escalate",
                    "guardian": "gamma",
                    "reason": "socks5_detected",
                    "severity": "SOCK5",
                    "data": data
                }

        elif event_type == "translator_breach":
            log.critical(f"[GAMMA] TRANSLATOR BREACH — intake rule violated: {data}")
            return {
                "status": "escalate",
                "guardian": "gamma",
                "reason": "translator_breach",
                "data": data
            }

        return {"status": "ok", "guardian": "gamma"}

    def _on_activate(self):
        log.info("[GAMMA] Network/file monitoring armed")

    def _on_honeypot(self):
        log.info("[GAMMA] Honeypot mode — faking network responses")
