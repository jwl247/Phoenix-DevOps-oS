#!/usr/bin/env python3
"""
GUARDIAN BASE CLASS
jwl247 / Jerry Leftwich / GPL v3

All guardians inherit from this.
Active mode: full detection running.
Honeypot mode: looks active, feeds false data, reports contact to rotator.
"""

import logging
from datetime import datetime
from abc import ABC, abstractmethod

log = logging.getLogger('guardian_base')


class GuardianBase(ABC):
    def __init__(self, guardian_id: str, rotator=None):
        self.guardian_id = guardian_id
        self.rotator = rotator
        self.mode = "inactive"
        self.contact_log = []

    def go_active(self):
        self.mode = "active"
        log.info(f"✅ Guardian {self.guardian_id} — ACTIVE")
        self._on_activate()

    def go_honeypot(self):
        self.mode = "honeypot"
        log.info(f"🍯 Guardian {self.guardian_id} — HONEYPOT")
        self._on_honeypot()

    def is_active(self) -> bool:
        return self.mode == "active"

    def handle_contact(self, contact_data: dict):
        """
        Called when something interacts with this guardian.
        If honeypot: report to rotator immediately.
        If active: run detection logic.
        """
        self.contact_log.append({
            "timestamp": datetime.utcnow().isoformat(),
            "mode": self.mode,
            "data": contact_data
        })

        if self.mode == "honeypot":
            log.warning(
                f"🍯 {self.guardian_id} honeypot contact! "
                f"Reporting to rotator."
            )
            if self.rotator:
                self.rotator.honeypot_triggered(
                    self._get_enum_id(),
                    contact_data
                )
            return {"status": "honeypot", "detected": True}

        elif self.mode == "active":
            return self._detect(contact_data)

        return {"status": "inactive"}

    @abstractmethod
    def _detect(self, data: dict) -> dict:
        """Active detection logic — implement in each guardian"""
        pass

    @abstractmethod
    def _get_enum_id(self):
        """Return the GuardianID enum value for this guardian"""
        pass

    def _on_activate(self):
        """Override for activation side effects"""
        pass

    def _on_honeypot(self):
        """Override for honeypot side effects"""
        pass

    def status(self) -> dict:
        return {
            "guardian": self.guardian_id,
            "mode": self.mode,
            "contacts": len(self.contact_log)
        }
