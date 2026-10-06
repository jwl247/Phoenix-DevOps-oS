"""
session.py — HTTP session layer for node_session
=================================================
All network calls to packages-worker. Stdlib urllib only.
No external dependencies. Runs on any Python 3.8+ platform —
Linux, Windows, macOS, Android/Termux, whatever the node is.

Pull (ingress):  GET player state, sidecars, blobs from packages-worker → local
Push (egress):   PUT local state, sidecars, blobs → packages-worker → R2

Hash is the filename, the D1 key, and the R2 object key.
Sidecars travel. Files never travel unless a node genuinely lacks them.
"""

import os
import json
import time
import hashlib
import logging
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional

log = logging.getLogger("phoenix.session")


# ── Hash — identity, integrity, name ────────────────────────────────────────

def content_hash(data: bytes) -> str:
    """
    Dual-hash: SHA3-256 XOR-folded with BLAKE2b-256.
    Result is the canonical name of this content across every layer.
    Same content → same hash → same name, always.
    A sum of its whole.
    """
    sha3  = hashlib.sha3_256(data).digest()
    blake = hashlib.blake2b(data, digest_size=32).digest()
    return bytes(a ^ b for a, b in zip(sha3, blake)).hex()


def verify_hash(data: bytes, expected: str) -> bool:
    return content_hash(data) == expected


# ── Sidecar schema ───────────────────────────────────────────────────────────

def make_sidecar(
    hash_id:     str,
    sector:      int,
    depth:       int,
    location:    str,
    description: str = "",
) -> dict:
    """
    Sidecar = clone-call metadata. Travels instead of the file.
    Hash is the filename, the D1 key, and the R2 object key.
    Target filesystem depth: 4-8 levels.
    """
    return {
        "hash":        hash_id,
        "sector":      sector,
        "depth":       depth,
        "location":    location,
        "intake_ts":   time.time(),
        "description": description,
    }


# ── Local node paths ─────────────────────────────────────────────────────────

def node_root(uid: str) -> Path:
    base = Path(os.environ.get("PHOENIX_NODE_ROOT",
                               Path.home() / ".phoenix" / "node"))
    return base / uid


def sidecar_dir(uid: str) -> Path:
    return node_root(uid) / "sidecars"


def blob_dir(uid: str) -> Path:
    return node_root(uid) / "blobs"


def state_path(uid: str) -> Path:
    return node_root(uid) / "state.json"


def hardware_path(uid: str) -> Path:
    return node_root(uid) / "hardware.json"


# ── HTTP layer — stdlib urllib, no external deps ─────────────────────────────

def _call(
    method:     str,
    url:        str,
    auth_token: str,
    body:       Optional[bytes] = None,
    extra_headers: Optional[dict] = None,
    timeout:    int = 30,
) -> tuple[int, bytes]:
    """
    Single HTTP call via urllib. Returns (status_code, body_bytes).
    Raises urllib.error.HTTPError on 4xx/5xx so callers can handle by status.
    """
    headers = {
        "Authorization": f"Bearer {auth_token}",
        "User-Agent":    "phoenix-node/1.0",
    }
    if body is not None and "Content-Type" not in (extra_headers or {}):
        headers["Content-Type"] = "application/json"
    if extra_headers:
        headers.update(extra_headers)

    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def _get(url: str, auth_token: str, timeout: int = 30) -> tuple[int, bytes]:
    return _call("GET", url, auth_token, timeout=timeout)


def _put(
    url:           str,
    auth_token:    str,
    body:          bytes,
    content_type:  str = "application/json",
    extra_headers: Optional[dict] = None,
    timeout:       int = 60,
) -> tuple[int, bytes]:
    h = {"Content-Type": content_type}
    if extra_headers:
        h.update(extra_headers)
    return _call("PUT", url, auth_token, body=body, extra_headers=h, timeout=timeout)


def _delete(url: str, auth_token: str, timeout: int = 30) -> tuple[int, bytes]:
    return _call("DELETE", url, auth_token, timeout=timeout)


# ── Pull (ingress) — login, bring state to this node ────────────────────────

def pull(
    uid:          str,
    worker_url:   str,
    auth_token:   str,
    host_profile: Optional[dict] = None,
    egress_url:   Optional[str]  = None,
) -> dict:
    """
    Pull player state from packages-worker via the ingress tunnel.
    Creates local dirs, fetches state.json + all sidecars + missing blobs.
    hardware.json is written via egress_url (it's a write operation).

    Returns a session context dict.
    """
    base   = worker_url.rstrip("/")
    ebase  = (egress_url or worker_url).rstrip("/")
    prefix = f"{base}/player/{uid}"

    log.info(f"PULL  uid={uid}  ingress={base}")

    sidecar_dir(uid).mkdir(parents=True, exist_ok=True)
    blob_dir(uid).mkdir(parents=True, exist_ok=True)

    # ── state.json ───────────────────────────────────────────────────────────
    state = {}
    status, body = _get(f"{prefix}/state", auth_token)
    if status == 200:
        try:
            payload = json.loads(body)
            state   = payload.get("state", payload)  # handle both {state:{}} and raw
            state_path(uid).write_text(json.dumps(state, indent=2))
            log.info(f"  state.json pulled  keys={len(state)}")
        except Exception as e:
            log.warning(f"  state.json parse error: {e}")
    elif status == 404:
        log.info("  state.json not found — new player")
    else:
        log.warning(f"  state.json fetch returned {status}")

    # ── sidecars list ─────────────────────────────────────────────────────────
    pulled_sidecars = 0
    missing_blobs   = []

    status, body = _get(f"{prefix}/sidecars", auth_token)
    if status == 200:
        try:
            sidecar_list = json.loads(body).get("sidecars", [])
        except Exception:
            sidecar_list = []

        for entry in sidecar_list:
            h = entry.get("hash", "")
            if not h:
                continue

            # fetch individual sidecar
            s2, sb = _get(f"{prefix}/sidecar/{h}", auth_token)
            if s2 != 200:
                log.warning(f"  sidecar fetch failed {h[:16]}…  status={s2}")
                continue

            local_sc = sidecar_dir(uid) / f"{h}.sidecar.json"
            local_sc.write_bytes(sb)
            pulled_sidecars += 1

            # check local blob cache
            local_blob = blob_dir(uid) / h
            if local_blob.exists():
                data = local_blob.read_bytes()
                if verify_hash(data, h):
                    continue    # cached and valid — files never travel needlessly
                else:
                    log.warning(f"  hash mismatch on cached blob {h[:16]}… — re-fetching")
                    local_blob.unlink()

            missing_blobs.append(h)
    else:
        log.warning(f"  sidecars list returned {status}")

    log.info(f"  sidecars pulled={pulled_sidecars}  missing_blobs={len(missing_blobs)}")

    # ── fetch missing blobs ───────────────────────────────────────────────────
    fetched_blobs = 0
    for h in missing_blobs:
        s3, blob_data = _get(f"{prefix}/blob/{h}", auth_token)
        if s3 != 200:
            log.warning(f"  blob fetch failed {h[:16]}…  status={s3}")
            continue
        if not verify_hash(blob_data, h):
            log.error(f"  R2 blob hash mismatch {h[:16]}… — not caching corrupt data")
            continue
        (blob_dir(uid) / h).write_bytes(blob_data)
        fetched_blobs += 1

    if fetched_blobs:
        log.info(f"  blobs fetched from R2: {fetched_blobs}")

    # ── hardware fingerprint (write → egress) ─────────────────────────────────
    if host_profile:
        hw = {
            "node":      host_profile.get("hostname"),
            "os":        host_profile.get("os"),
            "arch":      host_profile.get("arch"),
            "ram_gb":    host_profile.get("ram_gb"),
            "helix_l1":  host_profile.get("helix_l1_mb"),
            "helix_l2":  host_profile.get("helix_l2_mb"),
            "helix_l3":  host_profile.get("helix_l3_mb"),
            "login_ts":  time.time(),
        }
        hardware_path(uid).write_text(json.dumps(hw, indent=2))
        e2, _ = _put(
            f"{ebase}/player/{uid}/hardware",
            auth_token,
            json.dumps(hw).encode(),
        )
        if e2 in (200, 201):
            log.info(f"  hardware.json written  node={hw.get('node')}")
        else:
            log.warning(f"  hardware.json write returned {e2}")

    ctx = {
        "uid":             uid,
        "worker_url":      base,
        "egress_url":      ebase,
        "auth_token":      auth_token,
        "state":           state,
        "sidecars_dir":    str(sidecar_dir(uid)),
        "blobs_dir":       str(blob_dir(uid)),
        "login_ts":        time.time(),
        "pulled_sidecars": pulled_sidecars,
        "fetched_blobs":   fetched_blobs,
    }

    log.info(f"PULL complete  uid={uid}")
    return ctx


# ── Push (egress) — logout, sync state back from this node ──────────────────

def push(ctx: dict, worker_url: Optional[str] = None, auth_token: Optional[str] = None) -> bool:
    """
    Push all local state back to packages-worker via the egress tunnel.
    Verifies blob hashes before pushing — hash is the name, must match.
    Returns True on clean push.
    """
    uid   = ctx["uid"]
    base  = (worker_url or ctx.get("egress_url") or ctx["worker_url"]).rstrip("/")
    token = auth_token or ctx["auth_token"]
    prefix = f"{base}/player/{uid}"

    log.info(f"PUSH  uid={uid}  egress={base}")
    ok = True

    # ── state.json ───────────────────────────────────────────────────────────
    # Always prefer in-memory state — it may have been mutated since pull.
    # Write it to disk first so file and memory stay in sync.
    sp = state_path(uid)
    mem_state = ctx.get("state")
    if mem_state is not None:
        state_data = json.dumps(mem_state).encode()
        sp.write_bytes(state_data)
        s, _ = _put(f"{prefix}/state", token, state_data)
        if s in (200, 201):
            log.info("  state.json pushed")
        else:
            log.error(f"  state.json push returned {s}")
            ok = False
    elif sp.exists():
        s, _ = _put(f"{prefix}/state", token, sp.read_bytes())
        if s in (200, 201):
            log.info("  state.json pushed (from file)")
        else:
            log.error(f"  state.json push (file) returned {s}")
            ok = False

    # ── sidecars ─────────────────────────────────────────────────────────────
    sc_dir = sidecar_dir(uid)
    pushed_sc = 0
    for sc_file in sc_dir.glob("*.sidecar.json"):
        h = sc_file.stem.replace(".sidecar", "")
        s, _ = _put(f"{prefix}/sidecar/{h}", token, sc_file.read_bytes())
        if s in (200, 201):
            pushed_sc += 1
        else:
            log.error(f"  sidecar push failed {h[:16]}…  status={s}")
            ok = False
    log.info(f"  sidecars pushed: {pushed_sc}")

    # ── blobs ─────────────────────────────────────────────────────────────────
    b_dir = blob_dir(uid)
    pushed_blobs = 0
    for blob_file in b_dir.iterdir():
        if not blob_file.is_file():
            continue
        h    = blob_file.name
        data = blob_file.read_bytes()

        # verify before pushing — hash is the name, a sum of its whole
        if not verify_hash(data, h):
            log.error(f"  hash mismatch on blob {h[:16]}… — not pushing corrupt data")
            ok = False
            continue

        s, _ = _put(
            f"{prefix}/blob/{h}",
            token,
            data,
            content_type="application/octet-stream",
            extra_headers={"X-Phoenix-Hash": h},
        )
        if s in (200, 201):
            pushed_blobs += 1
        else:
            log.error(f"  blob push failed {h[:16]}…  status={s}")
            ok = False

    log.info(f"  blobs pushed: {pushed_blobs}")

    # ── hardware logout_ts ────────────────────────────────────────────────────
    hp = hardware_path(uid)
    if hp.exists():
        try:
            hw = json.loads(hp.read_text())
            hw["logout_ts"] = time.time()
            _put(f"{prefix}/hardware", token, json.dumps(hw).encode())
            log.info("  hardware.json logout_ts updated")
        except Exception as e:
            log.warning(f"  hardware.json logout update failed: {e}")

    log.info(f"PUSH complete  uid={uid}  ok={ok}")
    return ok


# ── Clone (mesh replication) — push cached data to a destination node ────────

def clone_to(
    ctx:             dict,
    destination_url: str,
    auth_token:      Optional[str]  = None,
    hashes:          Optional[list] = None,
    include_state:   bool           = False,
    timeout:         int            = 60,
) -> dict:
    """
    Clone cached blobs (and optionally sidecars + state) from this node to
    a destination packages-worker endpoint.

    destination_url  — target packages-worker base URL (egress of destination node)
    auth_token       — bearer token for destination (defaults to ctx["auth_token"])
    hashes           — list of specific blob hashes to clone; None = all cached blobs
    include_state    — also push state.json to destination (default False)

    Returns:
        {
          "blobs_cloned":    int,
          "sidecars_cloned": int,
          "state_cloned":    bool,
          "errors":          list[str],
        }

    Sidecars travel. Only verified blobs are cloned — hash is the name, a sum
    of its whole. Corrupt or hash-mismatched blobs are skipped and logged.
    """
    uid    = ctx["uid"]
    token  = auth_token or ctx["auth_token"]
    dst    = destination_url.rstrip("/")
    prefix = f"{dst}/player/{uid}"

    log.info(f"CLONE  uid={uid}  destination={dst}")

    result = {
        "blobs_cloned":    0,
        "sidecars_cloned": 0,
        "state_cloned":    False,
        "errors":          [],
    }

    # ── blobs ─────────────────────────────────────────────────────────────────
    b_dir = blob_dir(uid)
    target_hashes = set(hashes) if hashes else None

    for blob_file in b_dir.iterdir():
        if not blob_file.is_file():
            continue
        h = blob_file.name
        if target_hashes and h not in target_hashes:
            continue

        data = blob_file.read_bytes()
        if not verify_hash(data, h):
            msg = f"clone: hash mismatch on blob {h[:16]}… — skipped"
            log.error(msg)
            result["errors"].append(msg)
            continue

        s, _ = _put(
            f"{prefix}/blob/{h}",
            token,
            data,
            content_type="application/octet-stream",
            extra_headers={"X-Phoenix-Hash": h},
            timeout=timeout,
        )
        if s in (200, 201):
            result["blobs_cloned"] += 1
            log.info(f"  blob cloned {h[:16]}…")
        else:
            msg = f"clone: blob put {h[:16]}… returned {s}"
            log.error(msg)
            result["errors"].append(msg)

    # ── sidecars ──────────────────────────────────────────────────────────────
    sc_dir = sidecar_dir(uid)
    for sc_file in sc_dir.glob("*.sidecar.json"):
        h = sc_file.stem.replace(".sidecar", "")
        if target_hashes and h not in target_hashes:
            continue

        s, _ = _put(f"{prefix}/sidecar/{h}", token, sc_file.read_bytes(),
                    timeout=timeout)
        if s in (200, 201):
            result["sidecars_cloned"] += 1
            log.info(f"  sidecar cloned {h[:16]}…")
        else:
            msg = f"clone: sidecar put {h[:16]}… returned {s}"
            log.error(msg)
            result["errors"].append(msg)

    # ── state (optional) ──────────────────────────────────────────────────────
    if include_state:
        sp = state_path(uid)
        if sp.exists():
            s, _ = _put(f"{prefix}/state", token, sp.read_bytes(), timeout=timeout)
            if s in (200, 201):
                result["state_cloned"] = True
                log.info("  state.json cloned")
            else:
                msg = f"clone: state put returned {s}"
                log.error(msg)
                result["errors"].append(msg)

    log.info(
        f"CLONE complete  uid={uid}"
        f"  blobs={result['blobs_cloned']}"
        f"  sidecars={result['sidecars_cloned']}"
        f"  errors={len(result['errors'])}"
    )
    return result
