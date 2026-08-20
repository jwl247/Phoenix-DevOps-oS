#!/usr/bin/env python3
"""
GUARDIAN DELTA — Custody and integrity detection
Sector 4: Helix, Frank, breach_coms, master vault
jwl247 / Jerry Leftwich / GPL v3
Watches the vault. If Delta fires, something got very far in.
"""

import logging
import hashlib
from guardian_base import GuardianBase
log = logging.getLogger('guardian_delta')


class GuardianDelta(GuardianBase):
    def __init__(self, rotator=None):
        super().__init__("delta", rotator)
        self.integrity_hashes = {}

    def _get_enum_id(self):
        from guardian_rotator import GuardianID
        return GuardianID.DELTA

    def register_file(self, path: str, content: bytes):
        """Register a file's hash for integrity checking"""
        self.integrity_hashes[path] = hashlib.sha3_512(content).hexdigest()
        log.info(f"[DELTA] Registered integrity hash for {path}")

    def _detect(self, data: dict) -> dict:
        event_type = data.get("type", "")

        if event_type == "integrity_check":
            path = data.get("path", "")
            current_hash = data.get("hash", "")
            expected = self.integrity_hashes.get(path)

            if expected and current_hash != expected:
                log.critical(
                    f"[DELTA] INTEGRITY VIOLATION: {path} "
                    f"expected={expected[:16]}... got={current_hash[:16]}..."
                )
                return {
                    "status": "escalate",
                    "guardian": "delta",
                    "reason": "integrity_violation",
                    "severity": "CRITICAL",
                    "data": data
                }

        elif event_type == "vault_write":
            # Anything writing to breach_coms4 (master vault) gets logged
            source = data.get("source", "unknown")
            if source != "frank":
                log.critical(
                    f"[DELTA] UNAUTHORIZED VAULT WRITE from {source}"
                )
                return {
                    "status": "escalate",
                    "guardian": "delta",
                    "reason": "unauthorized_vault_write",
                    "severity": "CRITICAL",
                    "data": data
                }

        elif event_type == "helix_tamper":
            log.critical(f"[DELTA] HELIX TAMPER DETECTED: {data}")
            return {
                "status": "escalate",
                "guardian": "delta",
                "reason": "helix_tamper",
                "severity": "CRITICAL",
                "data": data
            }

        return {"status": "ok", "guardian": "delta"}

    def _on_activate(self):
        log.info("[DELTA] Vault/integrity monitoring armed — full custody watch")

    def _on_honeypot(self):
        log.info("[DELTA] Honeypot mode — watching silently")
