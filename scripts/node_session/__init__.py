"""
node_session — Phoenix node session lifecycle
=============================================
Frank-managed importable module for the player login/logout ring.

Import this. Don't run it standalone. Frank manages the lifecycle.

Tunnel architecture (GDD §2.2):
    ingress_url — packages-worker via the node's INGRESS tunnel
                  (read traffic: state pull, sidecar fetch, blob fetch)
    egress_url  — packages-worker via the node's EGRESS tunnel
                  (write traffic: state push, sidecar push, blob push,
                   hardware fingerprint)
    In dev/single-tunnel setups, egress_url defaults to ingress_url.

Environment variables (all optional — can pass directly instead):
    PHOENIX_WORKER_URL      — base packages-worker URL (ingress)
    PHOENIX_EGRESS_URL      — egress tunnel URL (defaults to PHOENIX_WORKER_URL)
    PHOENIX_AUTH            — bearer token
    PHOENIX_NODE_ROOT       — local storage root (default: ~/.phoenix/node)

Usage:
    from node_session import login, logout

    ctx = login(
        uid          = "player-uid-here",
        ingress_url  = "https://packages-worker.phoenix.workers.dev",
        egress_url   = "https://packages-worker.phoenix.workers.dev",  # or separate
        auth_token   = os.environ["PHOENIX_AUTH"],
        host_profile = helix_profile.info(),   # optional HelixHostProfile.info()
    )

    # ... session runs, game state mutates ctx["state"] ...

    ok = logout(ctx, wipe_local=True)

Frank is created internally by login() and stored in ctx["frank"].
He witnesses every operation and disappears on logout.
"""

import os
import logging
from typing import Optional

from .frank   import Frank
from .session import (
    pull,
    push,
    clone_to,
    content_hash,
    verify_hash,
    make_sidecar,
    node_root,
    sidecar_dir,
    blob_dir,
    state_path,
    hardware_path,
)

log = logging.getLogger("phoenix.node_session")

__all__ = [
    "login",
    "logout",
    "clone_to",
    "content_hash",
    "verify_hash",
    "make_sidecar",
    "node_root",
    "Frank",
]


def login(
    uid:          str,
    ingress_url:  Optional[str] = None,
    auth_token:   Optional[str] = None,
    egress_url:   Optional[str] = None,
    host_profile: Optional[dict] = None,
) -> dict:
    """
    Login: mount player state onto this node via the ingress tunnel.

    Creates a Frank instance, runs the mount phase (pull via ingress),
    advances to run phase, and returns the session context dict.

    ctx["frank"]   — the Frank instance (do not replace)
    ctx["state"]   — player game state dict (mutate freely during session)
    ctx["uid"]     — player uid
    ctx["login_ts"] — unix timestamp of login

    Falls back to PHOENIX_WORKER_URL / PHOENIX_AUTH env vars if not passed.
    """
    ingress = (ingress_url or os.environ.get("PHOENIX_WORKER_URL", "")).strip()
    egress  = (egress_url  or os.environ.get("PHOENIX_EGRESS_URL", ingress)).strip()
    token   = (auth_token  or os.environ.get("PHOENIX_AUTH", "")).strip()

    if not ingress:
        raise RuntimeError(
            "login: ingress_url not provided and PHOENIX_WORKER_URL not set"
        )
    if not token:
        raise RuntimeError(
            "login: auth_token not provided and PHOENIX_AUTH not set"
        )

    frank = Frank(
        uid=uid,
        ingress_url=ingress,
        egress_url=egress,
        auth_token=token,
    )

    import node_session.session as _session
    ctx = frank.mount(_session, host_profile=host_profile)

    log.info(
        f"LOGIN  uid={uid}"
        f"  sidecars={ctx.get('pulled_sidecars', 0)}"
        f"  blobs={ctx.get('fetched_blobs', 0)}"
        f"  tunnels={'split' if ingress != egress else 'shared'}"
    )
    return ctx


def logout(ctx: dict, wipe_local: bool = True) -> bool:
    """
    Logout: sync player state back via egress tunnel, wipe node, kill Frank.

    Returns True on clean sync. If sync returns False, local state is NOT
    wiped — inspect before clearing manually.

    wipe_local=False keeps local files for debugging. Default is True —
    node must be clean for the next player.
    """
    frank: Frank = ctx.get("frank")
    if frank is None:
        raise RuntimeError("logout: no Frank in session context")

    uid = ctx["uid"]

    import node_session.session as _session
    ok = frank.sync(ctx, _session)

    if ok or wipe_local:
        frank.die(ctx, wipe_local=(ok and wipe_local))
    else:
        log.warning(
            f"LOGOUT  uid={uid}  sync had errors — local state preserved, Frank kept"
        )
        return False

    log.info(f"LOGOUT  uid={uid}  ok={ok}  wiped={ok and wipe_local}")
    return ok
