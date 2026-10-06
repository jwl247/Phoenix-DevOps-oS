"""
node_session smoke test — runs against live packages-worker
Usage:
    python test_node_session.py

Reads PHOENIX_AUTH from env. Worker URL is hardcoded to the live endpoint.
Logs every operation with timing. Prints a summary at the end.
"""

import os
import sys
import time
import json
import logging

# ── logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)-22s  %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("smoke")

# ── config ────────────────────────────────────────────────────────────────────
WORKER_URL = "https://packages-worker.phoenix-jwl.workers.dev"
AUTH_TOKEN  = os.environ.get("PHOENIX_AUTH", "").strip()
TEST_UID    = "smoke-test-player-001"

if not AUTH_TOKEN:
    log.error("PHOENIX_AUTH env var not set — set it and rerun")
    sys.exit(1)

# ── import node_session ───────────────────────────────────────────────────────
# Must be run from the scripts/ directory, or scripts/ must be on sys.path
SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "scripts")
sys.path.insert(0, os.path.abspath(SCRIPTS_DIR))

try:
    from node_session import login, logout, clone_to, content_hash, make_sidecar
except ImportError as e:
    log.error(f"Cannot import node_session: {e}")
    log.error("Run this script from Phoenix-DevOps-oS/scripts/ or adjust the path above")
    sys.exit(1)

# ── test ─────────────────────────────────────────────────────────────────────
results = {}

log.info("=" * 60)
log.info(f"TARGET  {WORKER_URL}")
log.info(f"UID     {TEST_UID}")
log.info("=" * 60)

# ── 1. login ──────────────────────────────────────────────────────────────────
t0 = time.perf_counter()
try:
    ctx = login(
        uid         = TEST_UID,
        ingress_url = WORKER_URL,
        egress_url  = WORKER_URL,   # single tunnel for smoke test
        auth_token  = AUTH_TOKEN,
    )
    login_ms = int((time.perf_counter() - t0) * 1000)
    results["login_ms"]        = login_ms
    results["pulled_sidecars"] = ctx.get("pulled_sidecars", 0)
    results["fetched_blobs"]   = ctx.get("fetched_blobs", 0)
    results["state_keys"]      = len(ctx.get("state", {}))
    log.info(f"LOGIN OK  {login_ms}ms  sidecars={results['pulled_sidecars']}  blobs={results['fetched_blobs']}  state_keys={results['state_keys']}")
except Exception as e:
    log.error(f"LOGIN FAILED: {e}")
    sys.exit(1)

# ── 2. write some state ───────────────────────────────────────────────────────
ctx["state"]["smoke_test"] = True
ctx["state"]["ts"]         = time.time()
ctx["state"]["node"]       = "compaq-smoke"
log.info("STATE mutated  keys=" + str(len(ctx["state"])))

# ── 3. make a test blob + sidecar ─────────────────────────────────────────────
blob_data = b"Phoenix smoke test blob - hash is the name, a sum of its whole."
h = content_hash(blob_data)

from node_session.session import blob_dir, sidecar_dir
blob_dir(TEST_UID).mkdir(parents=True, exist_ok=True)
sidecar_dir(TEST_UID).mkdir(parents=True, exist_ok=True)

(blob_dir(TEST_UID) / h).write_bytes(blob_data)
sc = make_sidecar(h, sector=1, depth=4, location="compaq-smoke", description="smoke test blob")
import json as _json
(sidecar_dir(TEST_UID) / f"{h}.sidecar.json").write_text(_json.dumps(sc))
log.info(f"BLOB+SIDECAR created  hash={h[:16]}…")
results["test_hash"] = h

# ── 4. logout (push) ──────────────────────────────────────────────────────────
t1 = time.perf_counter()
try:
    ok = logout(ctx, wipe_local=True)
    logout_ms = int((time.perf_counter() - t1) * 1000)
    results["logout_ms"] = logout_ms
    results["logout_ok"] = ok
    log.info(f"LOGOUT {'OK' if ok else 'ERRORS'}  {logout_ms}ms")
except Exception as e:
    log.error(f"LOGOUT FAILED: {e}")
    results["logout_ok"] = False

# ── 5. verify blob made it to R2 via a fresh login ───────────────────────────
log.info("VERIFY — fresh login to confirm R2 round-trip…")
t2 = time.perf_counter()
try:
    ctx2 = login(
        uid         = TEST_UID,
        ingress_url = WORKER_URL,
        egress_url  = WORKER_URL,
        auth_token  = AUTH_TOKEN,
    )
    verify_ms = int((time.perf_counter() - t2) * 1000)
    results["verify_ms"]          = verify_ms
    results["verify_sidecars"]    = ctx2.get("pulled_sidecars", 0)
    results["verify_blobs"]       = ctx2.get("fetched_blobs", 0)
    results["verify_state_smoke"] = ctx2.get("state", {}).get("smoke_test", False)
    log.info(
        f"VERIFY LOGIN  {verify_ms}ms"
        f"  sidecars={results['verify_sidecars']}"
        f"  blobs={results['verify_blobs']}"
        f"  state.smoke_test={results['verify_state_smoke']}"
    )
    # clean up
    logout(ctx2, wipe_local=True)
except Exception as e:
    log.error(f"VERIFY FAILED: {e}")
    results["verify_ok"] = False

# ── summary ───────────────────────────────────────────────────────────────────
log.info("")
log.info("=" * 60)
log.info("SMOKE TEST SUMMARY")
log.info("=" * 60)
log.info(f"  login          {results.get('login_ms', '?')} ms")
log.info(f"  logout/push    {results.get('logout_ms', '?')} ms")
log.info(f"  verify login   {results.get('verify_ms', '?')} ms")
log.info(f"  state round-trip  {'PASS' if results.get('verify_state_smoke') else 'FAIL'}")
log.info(f"  blob round-trip   {'PASS' if results.get('verify_blobs', 0) > 0 else 'FAIL'}")
log.info(f"  sidecar count     {results.get('verify_sidecars', 0)}")
log.info(f"  test hash         {results.get('test_hash', '?')[:32]}…")
log.info("=" * 60)

all_pass = (
    results.get("logout_ok", False) and
    results.get("verify_state_smoke", False) and
    results.get("verify_blobs", 0) > 0
)
log.info(f"RESULT: {'ALL PASS' if all_pass else 'CHECK LOGS ABOVE'}")
sys.exit(0 if all_pass else 1)
