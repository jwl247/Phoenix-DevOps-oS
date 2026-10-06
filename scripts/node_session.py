"""
node_session.py — Phoenix node session lifecycle
================================================
Login  (top)  : pull player sidecars from R2, verify hashes, boot Frank context
Logout (bottom): push new/modified sidecars back to R2, wipe local, node clean

Architecture:
  - Files never travel. Sidecars travel.
  - Hash IS the filename, the D1 primary key, and the R2 object key.
  - A sidecar is clone-call metadata: hash, sector, depth, intake_ts, location.
  - Blobs live in R2 at players/{user_id}/blobs/{hash}
  - Sidecars live at players/{user_id}/sidecars/{hash}.sidecar.json
  - state.json  : lightweight game state  (inventory, position, flags)
  - hardware.json: last node fingerprint  (HostProfile, tier config)

Dependencies: boto3 (R2 S3-compatible), hashlib (stdlib), json (stdlib)
  pip install boto3 --break-system-packages
"""

import os
import json
import time
import hashlib
import logging
from pathlib import Path
from typing import Optional

import boto3
from botocore.config import Config as BotoConfig

log = logging.getLogger("phoenix.session")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ── R2 client ────────────────────────────────────────────────────────────────

def _r2_client():
    """Return a boto3 S3 client pointed at Cloudflare R2."""
    account_id  = os.environ["PHOENIX_R2_ACCOUNT_ID"]
    access_key  = os.environ["PHOENIX_R2_ACCESS_KEY"]
    secret_key  = os.environ["PHOENIX_R2_SECRET_KEY"]
    return boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=BotoConfig(signature_version="s3v4"),
        region_name="auto",
    )

BUCKET = os.environ.get("PHOENIX_R2_BUCKET", "phoenix-vault")

# ── Hash — the name, the key, the identity ───────────────────────────────────

def content_hash(data: bytes) -> str:
    """
    Dual-hash: SHA3-256 XOR-folded with BLAKE2b-256.
    The result is the canonical name of this content across every layer.
    Same content → same hash → same name, always.
    """
    sha3   = hashlib.sha3_256(data).digest()
    blake  = hashlib.blake2b(data, digest_size=32).digest()
    folded = bytes(a ^ b for a, b in zip(sha3, blake))
    return folded.hex()

def verify_hash(data: bytes, expected_hash: str) -> bool:
    return content_hash(data) == expected_hash

# ── Sidecar schema ───────────────────────────────────────────────────────────

def make_sidecar(hash_id: str, sector: int, depth: int,
                 location: str, description: str = "") -> dict:
    """
    Sidecar = clone-call metadata. Travels instead of the file.
    Hash is the filename, the D1 key, and the R2 object key.
    """
    return {
        "hash":        hash_id,       # identity — sum of the whole
        "sector":      sector,        # 1–4
        "depth":       depth,         # filesystem depth; target ≤ 8
        "location":    location,      # node hostname or sector path
        "intake_ts":   time.time(),
        "description": description,
    }

# ── Local node paths ─────────────────────────────────────────────────────────

def node_root(user_id: str) -> Path:
    base = Path(os.environ.get("PHOENIX_NODE_ROOT", Path.home() / ".phoenix" / "node"))
    return base / user_id

def sidecar_dir(user_id: str) -> Path:
    return node_root(user_id) / "sidecars"

def blob_dir(user_id: str) -> Path:
    return node_root(user_id) / "blobs"

def state_path(user_id: str) -> Path:
    return node_root(user_id) / "state.json"

def hardware_path(user_id: str) -> Path:
    return node_root(user_id) / "hardware.json"

# ─────────────────────────────────────────────────────────────────────────────
# LOGIN — top of the session lifecycle
# ─────────────────────────────────────────────────────────────────────────────

def login(user_id: str, host_profile: Optional[dict] = None) -> dict:
    """
    Pull player sidecars from R2. Verify hashes. Boot Frank context.
    Blobs are NOT pulled unless missing locally — files never travel
    unless a node genuinely doesn't have them.

    Returns a session context dict for Frank.
    """
    log.info(f"LOGIN  user={user_id}")
    r2     = _r2_client()
    prefix = f"players/{user_id}/"

    # ── create local dirs ────────────────────────────────────────────────────
    sidecar_dir(user_id).mkdir(parents=True, exist_ok=True)
    blob_dir(user_id).mkdir(parents=True, exist_ok=True)

    # ── pull state.json ──────────────────────────────────────────────────────
    state = {}
    try:
        obj   = r2.get_object(Bucket=BUCKET, Key=f"{prefix}state.json")
        state = json.loads(obj["Body"].read())
        state_path(user_id).write_text(json.dumps(state, indent=2))
        log.info(f"  state.json pulled — {len(state)} keys")
    except r2.exceptions.NoSuchKey:
        log.info("  state.json not found — new player")
    except Exception as e:
        log.warning(f"  state.json pull failed: {e}")

    # ── pull sidecars ────────────────────────────────────────────────────────
    paginator = r2.get_paginator("list_objects_v2")
    sidecar_prefix = f"{prefix}sidecars/"
    pulled = 0
    verified = 0
    missing_blobs = []

    for page in paginator.paginate(Bucket=BUCKET, Prefix=sidecar_prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if not key.endswith(".sidecar.json"):
                continue

            # pull sidecar (tiny — always transfer)
            body     = r2.get_object(Bucket=BUCKET, Key=key)["Body"].read()
            sidecar  = json.loads(body)
            hash_id  = sidecar.get("hash", "")

            if not hash_id:
                log.warning(f"  sidecar missing hash field: {key}")
                continue

            # write sidecar locally
            local_sc = sidecar_dir(user_id) / f"{hash_id}.sidecar.json"
            local_sc.write_bytes(body)
            pulled += 1

            # check if blob is cached locally
            local_blob = blob_dir(user_id) / hash_id
            if local_blob.exists():
                # verify: hash is the name — it must match
                blob_data = local_blob.read_bytes()
                if verify_hash(blob_data, hash_id):
                    verified += 1
                else:
                    log.warning(f"  HASH MISMATCH local blob {hash_id[:16]}… — will re-fetch")
                    local_blob.unlink()
                    missing_blobs.append(hash_id)
            else:
                missing_blobs.append(hash_id)

    log.info(f"  sidecars pulled={pulled} verified={verified} missing_blobs={len(missing_blobs)}")

    # ── fetch missing blobs ──────────────────────────────────────────────────
    fetched = 0
    for hash_id in missing_blobs:
        blob_key = f"{prefix}blobs/{hash_id}"
        try:
            blob_data = r2.get_object(Bucket=BUCKET, Key=blob_key)["Body"].read()
            if not verify_hash(blob_data, hash_id):
                log.error(f"  R2 blob hash mismatch {hash_id[:16]}… — skipping")
                continue
            (blob_dir(user_id) / hash_id).write_bytes(blob_data)
            fetched += 1
        except Exception as e:
            log.warning(f"  blob fetch failed {hash_id[:16]}…: {e}")

    if fetched:
        log.info(f"  blobs fetched from R2: {fetched}")

    # ── record hardware fingerprint ──────────────────────────────────────────
    if host_profile:
        hardware_path(user_id).write_text(json.dumps({
            "node":       host_profile.get("hostname"),
            "os":         host_profile.get("os"),
            "arch":       host_profile.get("arch"),
            "ram_gb":     host_profile.get("ram_gb"),
            "helix_l1":   host_profile.get("helix_l1_mb"),
            "helix_l2":   host_profile.get("helix_l2_mb"),
            "helix_l3":   host_profile.get("helix_l3_mb"),
            "login_ts":   time.time(),
        }, indent=2))
        log.info(f"  hardware fingerprint written — node={host_profile.get('hostname')}")

    session = {
        "user_id":       user_id,
        "state":         state,
        "sidecars_dir":  str(sidecar_dir(user_id)),
        "blobs_dir":     str(blob_dir(user_id)),
        "login_ts":      time.time(),
        "pulled":        pulled,
        "verified":      verified,
    }
    log.info(f"LOGIN  complete — user={user_id}")
    return session

# ─────────────────────────────────────────────────────────────────────────────
# LOGOUT — bottom of the session lifecycle
# ─────────────────────────────────────────────────────────────────────────────

def logout(user_id: str, session: dict, wipe_local: bool = True) -> bool:
    """
    Push new/modified sidecars and blobs back to R2.
    Verify each blob hash before pushing — hash is the name, must match.
    Wipe local node state so the node is clean for the next player.

    Returns True if push completed cleanly.
    """
    log.info(f"LOGOUT user={user_id}")
    r2     = _r2_client()
    prefix = f"players/{user_id}/"
    ok     = True

    # ── push state.json ──────────────────────────────────────────────────────
    sp = state_path(user_id)
    if sp.exists():
        try:
            r2.put_object(
                Bucket=BUCKET,
                Key=f"{prefix}state.json",
                Body=sp.read_bytes(),
                ContentType="application/json",
            )
            log.info("  state.json pushed")
        except Exception as e:
            log.error(f"  state.json push failed: {e}")
            ok = False

    # ── push sidecars ────────────────────────────────────────────────────────
    sc_dir = sidecar_dir(user_id)
    pushed_sc = 0
    for sc_file in sc_dir.glob("*.sidecar.json"):
        try:
            r2.put_object(
                Bucket=BUCKET,
                Key=f"{prefix}sidecars/{sc_file.name}",
                Body=sc_file.read_bytes(),
                ContentType="application/json",
            )
            pushed_sc += 1
        except Exception as e:
            log.error(f"  sidecar push failed {sc_file.name}: {e}")
            ok = False
    log.info(f"  sidecars pushed: {pushed_sc}")

    # ── push blobs (only new/unverified against R2) ──────────────────────────
    b_dir = blob_dir(user_id)
    pushed_blobs = 0
    for blob_file in b_dir.iterdir():
        hash_id   = blob_file.name
        blob_data = blob_file.read_bytes()

        # verify before pushing — hash is the name, must be a sum of its whole
        if not verify_hash(blob_data, hash_id):
            log.error(f"  HASH MISMATCH on logout blob {hash_id[:16]}… — not pushing")
            ok = False
            continue

        try:
            r2.put_object(
                Bucket=BUCKET,
                Key=f"{prefix}blobs/{hash_id}",
                Body=blob_data,
            )
            pushed_blobs += 1
        except Exception as e:
            log.error(f"  blob push failed {hash_id[:16]}…: {e}")
            ok = False

    log.info(f"  blobs pushed: {pushed_blobs}")

    # ── hardware fingerprint push ────────────────────────────────────────────
    hp = hardware_path(user_id)
    if hp.exists():
        try:
            hw          = json.loads(hp.read_text())
            hw["logout_ts"] = time.time()
            r2.put_object(
                Bucket=BUCKET,
                Key=f"{prefix}hardware.json",
                Body=json.dumps(hw, indent=2).encode(),
                ContentType="application/json",
            )
            log.info(f"  hardware.json pushed")
        except Exception as e:
            log.warning(f"  hardware.json push failed: {e}")

    # ── wipe local node state ────────────────────────────────────────────────
    if wipe_local and ok:
        import shutil
        node_path = node_root(user_id)
        shutil.rmtree(node_path, ignore_errors=True)
        log.info(f"  local state wiped — node clean")
    elif not ok:
        log.warning("  push had errors — local state NOT wiped, inspect before clearing")

    log.info(f"LOGOUT complete — user={user_id} clean={ok}")
    return ok


# ── quick self-test ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    # hash identity test — sum of its whole
    data = b"phoenix test block"
    h    = content_hash(data)
    assert verify_hash(data, h),      "hash verify failed"
    assert not verify_hash(b"x", h),  "hash collision — should not happen"
    print(f"Hash identity OK  {h[:32]}…")

    # sidecar schema test
    sc = make_sidecar(h, sector=1, depth=3, location="pbm-compaq", description="test")
    assert sc["hash"] == h
    assert sc["sector"] == 1
    print(f"Sidecar schema OK  sector={sc['sector']} depth={sc['depth']}")

    print("\nnode_session self-test PASSED")
    print("Set PHOENIX_R2_ACCOUNT_ID / ACCESS_KEY / SECRET_KEY / BUCKET to test live R2.")
