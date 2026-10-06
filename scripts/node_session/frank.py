"""
frank.py — Frank process ledger for node_session
=================================================
Frank witnesses the mount → run → sync → die ring lifecycle for a single
player session on this node. One instance per session. One pen. Zero
movement. The ring comes to Frank — Frank never moves.

Tunnel architecture (GDD §2.2):
    Each node has two dedicated tunnels — ingress and egress — kept
    strictly separated. This is the DMZ-per-player architecture.

    ingress_url  — packages-worker reachable via the INGRESS tunnel.
                   All pull traffic (login, state fetch, blob fetch)
                   comes through here.
    egress_url   — packages-worker reachable via the EGRESS tunnel.
                   All push traffic (logout, state write, blob write,
                   hardware write) goes out through here.

    If egress_url is omitted it defaults to ingress_url — valid for
    single-tunnel dev/test nodes (Compaq, phone, local machine).
    Production nodes get two separate tunnel endpoints.

Frank is imported on demand. He disappears when the session ends.
Never spawned. Never persistent. Always watching.
"""

import time
import logging
from typing import Optional

log = logging.getLogger("phoenix.frank")


class Frank:
    """
    Process ledger and lifecycle orchestrator for a single player session.

    Ring lifecycle:
        frank = Frank(uid, ingress_url, egress_url, auth_token)
        ctx   = frank.mount(session_mod, host_profile)   # pull via ingress
        # ... session runs ...
        ok    = frank.sync(ctx, session_mod)             # push via egress
        frank.die(ctx, wipe_local=True)                  # wipe node, close

    Frank witnesses every operation. The ledger is in-memory only — it
    disappears with Frank when die() is called. No trace left on the node.
    """

    PHASES = ("born", "mount", "run", "sync", "die")

    def __init__(
        self,
        uid:          str,
        ingress_url:  str,
        auth_token:   str,
        egress_url:   Optional[str] = None,
    ):
        if not uid:
            raise ValueError("Frank: uid is required")
        if not ingress_url:
            raise ValueError("Frank: ingress_url is required")
        if not auth_token:
            raise ValueError("Frank: auth_token is required")

        self.uid          = uid
        self.ingress_url  = ingress_url.rstrip("/")
        self.egress_url   = (egress_url or ingress_url).rstrip("/")
        self.auth_token   = auth_token
        self._ledger:     list  = []
        self._phase:      str   = "born"
        self._born_ts:    float = time.time()
        self._died:       bool  = False

        self._witness("born", {
            "uid":     uid,
            "ingress": self.ingress_url,
            "egress":  self.egress_url,
            "split":   self.ingress_url != self.egress_url,
        })
        log.info(
            f"Frank born  uid={uid}"
            f"  tunnels={'split' if self.ingress_url != self.egress_url else 'shared'}"
        )

    # ── ring phase ────────────────────────────────────────────────────────────

    def _advance(self, phase: str):
        assert phase in self.PHASES, f"unknown phase: {phase}"
        self._phase = phase
        self._witness("phase_advance", {"phase": phase})
        log.info(f"Frank phase={phase}  uid={self.uid}")

    # ── ledger ────────────────────────────────────────────────────────────────

    def _witness(self, event: str, data: dict):
        """Record an event to Frank's in-memory ledger."""
        self._ledger.append({
            "ts":    time.time(),
            "event": event,
            "data":  data,
        })

    def ledger(self) -> list:
        """Return a copy of the full witnessed ledger."""
        return list(self._ledger)

    def summary(self) -> dict:
        return {
            "uid":     self.uid,
            "phase":   self._phase,
            "born_ts": self._born_ts,
            "events":  len(self._ledger),
            "died":    self._died,
            "tunnels": "split" if self.ingress_url != self.egress_url else "shared",
        }

    # ── ring: mount ───────────────────────────────────────────────────────────

    def mount(self, session_mod, host_profile: Optional[dict] = None) -> dict:
        """
        Mount phase: pull player state from packages-worker via INGRESS tunnel.
        Returns a session context dict. Advances ring to 'run'.

        session_mod  — node_session.session (passed in to avoid circular import)
        host_profile — optional HelixHostProfile.info() dict written to
                       players/{uid}/hardware.json via the EGRESS tunnel.
        """
        if self._died:
            raise RuntimeError("Frank is dead — create a new instance")
        self._advance("mount")

        ctx = session_mod.pull(
            uid=self.uid,
            worker_url=self.ingress_url,   # ← ingress tunnel for all pull traffic
            auth_token=self.auth_token,
            host_profile=host_profile,
            egress_url=self.egress_url,    # hardware.json is a write — uses egress
        )
        ctx["frank"] = self

        self._witness("mount_complete", {
            "pulled_sidecars": ctx.get("pulled_sidecars", 0),
            "fetched_blobs":   ctx.get("fetched_blobs", 0),
            "state_keys":      len(ctx.get("state", {})),
        })

        self._advance("run")
        log.info(
            f"Frank mount complete  uid={self.uid}"
            f"  sidecars={ctx.get('pulled_sidecars', 0)}"
            f"  blobs={ctx.get('fetched_blobs', 0)}"
        )
        return ctx

    # ── ring: sync ────────────────────────────────────────────────────────────

    def sync(self, ctx: dict, session_mod) -> bool:
        """
        Sync phase: push all local state back via EGRESS tunnel.
        Returns True on clean push.
        """
        if self._died:
            raise RuntimeError("Frank is dead")
        self._advance("sync")

        ok = session_mod.push(
            ctx=ctx,
            worker_url=self.egress_url,    # ← egress tunnel for all push traffic
            auth_token=self.auth_token,
        )

        self._witness("sync_complete", {"ok": ok})
        log.info(f"Frank sync  uid={self.uid}  ok={ok}")
        return ok

    # ── ring: die ─────────────────────────────────────────────────────────────

    def die(self, ctx: dict, wipe_local: bool = True):
        """
        Die phase: optionally wipe local node state, close the ledger.
        Frank disappears after this call — ledger cleared, node clean.
        """
        if self._died:
            return
        self._advance("die")

        if wipe_local:
            import shutil
            from .session import node_root
            node_path = node_root(self.uid)
            shutil.rmtree(node_path, ignore_errors=True)
            self._witness("wipe", {"path": str(node_path)})
            log.info(f"Frank die  uid={self.uid}  local wiped")
        else:
            log.info(f"Frank die  uid={self.uid}  local kept (inspect before clearing)")

        self._died = True
        self._ledger.clear()   # Frank disappears — he never leaves a trace
