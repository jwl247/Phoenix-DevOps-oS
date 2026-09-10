"""
CoPES guardian / honeypot security layer — sector 1.

The moving-target-defense rotator and its four sector guardians. Resurrected
2026-09-09 from an archived SECTOR4 fossil (security audit T1 #4): moved into
the live tree, given a dispatch/escalation seam, wired into the kernel boot
and phoenix_auth.

Public surface is copes_runtime:

    from security import copes_runtime
    copes_runtime.boot(on_escalate=sink)                     # arm (boot entrypoint)
    copes_runtime.dispatch({"type": "auth_failure", ...})    # event sources
    copes_runtime.status()

`honeypot.py` (the standalone Honeypot wrapper class) is kept for reference
but is NOT on the live path — honeypot behavior for an inactive guardian lives
in GuardianBase.go_honeypot() / handle_contact(), which the rotator drives.
"""

from . import copes_runtime  # noqa: F401

__all__ = ["copes_runtime"]
