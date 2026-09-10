#!/usr/bin/env python3
"""
CoPES Security Runtime — the one thing the rest of Phoenix imports.
jwl247 / Jerry Leftwich / GPL v3

Moving-target defense: four guardians (Alpha/Beta/Gamma/Delta), exactly one
active at a time, the other three sitting as honeypots. Rotation is randomized
(180-600s) so a prober can't know who's watching. Hit an inactive guardian and
you've fingerprinted yourself — it force-rotates and logs the incident.

Usage from a boot entrypoint:

    from security import copes_runtime
    copes_runtime.boot(on_escalate=my_sink)      # arms the rotator, starts the thread

Usage from an event source (phoenix_auth, usys bridge, watchers):

    from security import copes_runtime
    copes_runtime.dispatch({"type": "auth_failure", "source": "10.0.0.5"})

`dispatch` is safe to call before `boot()` (it no-ops with a debug log) and
never raises — an event source must never be broken by the guardian layer.

History: written months ago, sat in an archived SECTOR4 dir with zero call
sites (its own docstring claimed it was "called at CoPES boot" — it wasn't).
Resurrected 2026-09-09 per the security audit (docs/sec audit doc..., T1 #4):
moved into the live tree, given this dispatch/escalation seam, wired into
sector1/kernel/main_kernel.py and sector1/auth/phoenix_auth.py.
"""

import json
import logging
import os
import threading
from datetime import datetime, timezone

from .guardian_rotator import GuardianRotator, GuardianID
from .guardian_alpha import GuardianAlpha
from .guardian_beta import GuardianBeta
from .guardian_gamma import GuardianGamma
from .guardian_delta import GuardianDelta

log = logging.getLogger("copes_runtime")

# ── Which guardian owns which event type ─────────────────────────────────────
# Every event a guardian's _detect() knows how to handle is routed to it here.
# An event type not in this map is dropped with a debug log (not an error).
_ROUTE = {
    # Alpha — auth / boot / kernel (sector 1)
    "auth_failure":      GuardianID.ALPHA,
    "auth_success":      GuardianID.ALPHA,
    "kernel_tamper":     GuardianID.ALPHA,
    # Beta — process / intake / clone pool (sector 2)
    "process_spawn":     GuardianID.BETA,
    "clone_pool_tamper": GuardianID.BETA,
    "suite_unrecognized": GuardianID.BETA,   # usys.ps1 running an unknown/undeclared suite
    # Gamma — network / file / translator (sector 3)
    "file_motion":       GuardianID.GAMMA,
    "network_connection": GuardianID.GAMMA,
    "translator_breach": GuardianID.GAMMA,
    # Delta — custody / integrity / vault (sector 4)
    "integrity_check":   GuardianID.DELTA,
    "vault_write":       GuardianID.DELTA,
    "helix_tamper":      GuardianID.DELTA,
}

_DEFAULT_INCIDENT_LOG = os.path.expanduser("~/.unitedsys/logs/guardian_incidents.jsonl")


def _incident_log_path() -> str:
    """Resolved at write time so PHOENIX_GUARDIAN_LOG (and $HOME in tests) can
    steer it. The kernel sets PHOENIX_GUARDIAN_LOG to a deliberate location."""
    return os.environ.get("PHOENIX_GUARDIAN_LOG") or \
        os.path.expanduser("~/.unitedsys/logs/guardian_incidents.jsonl")


class _Runtime:
    """Holds the single live rotator + the escalation sink. Not a singleton
    class by ceremony — just one module-level instance below."""

    def __init__(self):
        self.rotator = None
        self._on_escalate = None
        self._lock = threading.Lock()

    def build(self, min_interval=180, max_interval=600):
        r = GuardianRotator(min_interval=min_interval, max_interval=max_interval)
        r.register(GuardianID.ALPHA, GuardianAlpha(r))
        r.register(GuardianID.BETA, GuardianBeta(r))
        r.register(GuardianID.GAMMA, GuardianGamma(r))
        r.register(GuardianID.DELTA, GuardianDelta(r))
        # The rotator calls this when a honeypot is probed (forced rotation
        # already happened inside honeypot_triggered by the time we see it).
        r.escalation_sink = self._escalate
        self.rotator = r
        return r

    def _escalate(self, incident: dict):
        """Single choke point for every escalation — honeypot probes and
        active-guardian threshold hits both land here."""
        incident = dict(incident)
        incident.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        log.critical("GUARDIAN ESCALATION: %s", incident)
        try:
            path = _incident_log_path()
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(incident) + "\n")
        except Exception as e:  # noqa: BLE001 — logging must not break the caller
            log.warning("could not persist incident: %s", e)
        if self._on_escalate:
            try:
                self._on_escalate(incident)
            except Exception as e:  # noqa: BLE001
                log.warning("on_escalate sink raised (ignored): %s", e)


_RT = _Runtime()


def boot(on_escalate=None, min_interval=180, max_interval=600):
    """Arm the guardian rotation. Call once, from the boot entrypoint.

    on_escalate: optional callable(incident: dict) — your upstream handler
                 (page a phone, flip a switch, whatever). Always also written
                 to ~/.unitedsys/logs/guardian_incidents.jsonl.
    Returns the live rotator (also at copes_runtime.rotator()).
    """
    with _RT._lock:
        if _RT.rotator and _RT.rotator.running:
            log.info("guardian rotation already armed — ignoring second boot()")
            return _RT.rotator
        _RT._on_escalate = on_escalate
        r = _RT.build(min_interval=min_interval, max_interval=max_interval)
        r.start()
    st = r.status()
    log.info(
        "CoPES Guardian Rotation ARMED — active=%s interval=%d-%ds honeypots=3",
        st["active_guardian"], r.min_interval, r.max_interval,
    )
    return r


def stop():
    with _RT._lock:
        if _RT.rotator:
            _RT.rotator.stop()


def rotator():
    return _RT.rotator


def status() -> dict:
    if not _RT.rotator:
        return {"armed": False}
    return {"armed": True, **_RT.rotator.status()}


def dispatch(event: dict) -> dict:
    """Route a security event to its guardian. Safe before boot(), never raises.

    Returns the guardian's response dict (or a {"status": ...} stub). If the
    routed guardian is currently a honeypot, the contact is reported to the
    rotator (forced rotation + escalation) by GuardianBase itself. If it is
    active and its _detect() returns status == 'escalate', we forward that to
    the escalation sink here.
    """
    try:
        etype = (event or {}).get("type", "")
        gid = _ROUTE.get(etype)
        if gid is None:
            log.debug("dispatch: no route for event type %r — dropped", etype)
            return {"status": "unrouted", "type": etype}
        if not _RT.rotator:
            log.debug("dispatch: guardian layer not armed — event %r dropped", etype)
            return {"status": "disarmed", "type": etype}

        guardian = _RT.rotator.guardians.get(gid)
        if guardian is None:
            return {"status": "no_guardian", "type": etype}

        result = guardian.handle_contact(event) or {}
        if result.get("status") == "escalate":
            _RT._escalate({
                "type": "active_detection",
                "guardian": gid.value,
                "event_type": etype,
                "detail": result,
            })
        return result
    except Exception as e:  # noqa: BLE001 — an event source must never break here
        log.warning("dispatch swallowed error for %r: %s", (event or {}).get("type"), e)
        return {"status": "error", "message": str(e)}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(name)s] %(levelname)s %(message)s")
    boot()
    import time
    try:
        while True:
            time.sleep(30)
            log.info("status: %s", status())
    except KeyboardInterrupt:
        stop()
