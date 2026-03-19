#!/usr/bin/env python3
# ============================================================
# helix_translator.py — Helix Translation Layer
# Project:   Phoenix DevOps / Full Propagator Framework
# Author:    jwl247 / Phoenix DevOps LLC
# License:   GPL-3.0
# ============================================================
# GNU Mach microkernel port-based resource namespace model.
# Translates between quad native language streams and
# platform-specific formats at the boundary edge.
# Everything stays quadralingual until this fires.
# ============================================================

import os
import sys
import json
import logging
from datetime import datetime

LOG_DIR  = os.path.expanduser("~/.unitedsys/logs")
LOG_FILE = os.path.join(LOG_DIR, "helix_translator.log")
VERSION  = "1.4.0"

os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger("helix_translator")

# ── Resource Namespace (GNU Mach port model) ─────────────────
# Each resource type gets a named port — translation is
# port-to-port, not format-to-format. Clean arbitration.
RESOURCE_PORTS = {
    "memory":   "helix://mem",
    "storage":  "helix://fs",
    "network":  "helix://net",
    "compute":  "helix://cpu",
    "com":      "helix://com",
    "vault":    "helix://vault",
}

# ── Platform Targets ─────────────────────────────────────────
PLATFORM_TARGETS = {
    "linux":    ["apt", "dnf", "pacman", "zypper", "apk"],
    "windows":  ["winget", "choco"],
    "wsl2":     ["apt", "winget"],
    "rhel":     ["dnf"],
    "arch":     ["pacman"],
    "alpine":   ["apk"],
}

class HelixTranslator:
    def __init__(self):
        self.translation_count = 0
        log.info(f"HelixTranslator v{VERSION} initialized")
        log.info(f"Resource ports: {list(RESOURCE_PORTS.keys())}")

    def detect_platform(self):
        """Detect current platform for edge translation"""
        import subprocess
        checks = {
            "apt":    ["which", "apt-get"],
            "dnf":    ["which", "dnf"],
            "pacman": ["which", "pacman"],
            "winget": ["which", "winget"],
            "choco":  ["which", "choco"],
        }
        for name, cmd in checks.items():
            try:
                result = subprocess.run(cmd, capture_output=True)
                if result.returncode == 0:
                    return name
            except Exception:
                continue
        return "unknown"

    def translate(self, payload, target_platform=None):
        """
        Translate quad-native payload to platform-specific format.
        Only called at platform boundary — not during quad-internal routing.
        """
        self.translation_count += 1

        if target_platform is None:
            target_platform = self.detect_platform()

        log.info(f"[TRANSLATE #{self.translation_count}] "
                f"→ platform: {target_platform}")

        result = {
            "original":        payload,
            "platform":        target_platform,
            "helix_port":      RESOURCE_PORTS.get(
                                   payload.get("resource", "compute"),
                                   "helix://unknown"
                               ),
            "translated_ts":   datetime.utcnow().isoformat(),
            "translation_id":  self.translation_count,
        }

        # Apply platform-specific translation rules
        if target_platform in ("winget", "choco", "windows"):
            result["format"] = "windows_native"
            result["encoding"] = "utf-16-le"
        elif target_platform in ("apt", "dnf", "pacman", "zypper", "apk"):
            result["format"] = "linux_native"
            result["encoding"] = "utf-8"
        else:
            result["format"] = "quad_passthrough"
            result["encoding"] = "utf-8"

        log.info(f"[TRANSLATE] format={result['format']} "
                f"port={result['helix_port']}")
        return result

    def status(self):
        return {
            "version":           VERSION,
            "translation_count": self.translation_count,
            "resource_ports":    RESOURCE_PORTS,
            "platform_targets":  PLATFORM_TARGETS,
        }


if __name__ == "__main__":
    translator = HelixTranslator()
    test_payload = {
        "type":     "package_install",
        "resource": "storage",
        "package":  "vim",
        "verb":     "install",
    }
    result = translator.translate(test_payload)
    print(json.dumps(result, indent=2))
