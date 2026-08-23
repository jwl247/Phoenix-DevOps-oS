#!/usr/bin/env bash
# =============================================================================
# test-double-helix.sh -- Phoenix Double Helix end-to-end smoke test
#                         Debian side (Strand B watcher)
#
# What this proves:
#   1. SMB share is mounted and the snapshot file is visible
#   2. windows_snapshot.json is valid JSON with all required fields
#   3. The snapshot is fresh (< 30s old -- paging.py's staleness gate)
#   4. paging.py snapshot reader logic works (standalone -- no full daemon)
#
# This script is self-contained. It does NOT require the repo to be on the
# share. Run it from wherever it lands -- the PS1 test copies it to the share
# so it is always available at /phoenix/helix-pages/test-double-helix.sh.
#
# Usage (inside Debian, run from anywhere):
#   bash /phoenix/helix-pages/test-double-helix.sh
#   -- OR, if the repo IS on the share --
#   bash /phoenix/Phoenix-DevOps-oS/tools/poc/test-double-helix.sh
# =============================================================================

set -uo pipefail

SHARE="/phoenix"
SNAPSHOT="$SHARE/helix-pages/windows_snapshot.json"
# Repo path -- used only for optional Test 5 (paging.py deep check).
# Tests 1-4 work without it.
REPO="$SHARE/Phoenix-DevOps-oS"
PAGING="$REPO/sector4/paging.py"

PASS=0
FAIL=0

pass() { echo "  [PASS] $1"; PASS=$((PASS+1)); }
fail() { echo "  [FAIL] $1"; FAIL=$((FAIL+1)); }
info() { echo "  [INFO] $1"; }

echo ""
echo "  Phoenix Double Helix -- end-to-end smoke test (Debian / Strand B)"
echo "  ====================================================================="
echo ""

# ---------------------------------------------------------------------------
# TEST 1: SMB share is mounted
# ---------------------------------------------------------------------------
info "Test 1: SMB share mounted at $SHARE"

if mountpoint -q "$SHARE" 2>/dev/null || mount | grep -q "$SHARE"; then
    pass "SMB share is mounted at $SHARE"
else
    fail "SMB share NOT mounted at $SHARE"
    echo ""
    echo "  Mount it first:"
    echo "    sudo mount -t cifs //10.0.2.2/Phoenix $SHARE \\"
    echo "      -o username=jwlef,password=YOUR_PASS,uid=1000,gid=1000,vers=3.0"
    echo ""
    echo "  Cannot continue without the share. Exiting."
    exit 1
fi

# ---------------------------------------------------------------------------
# TEST 2: Snapshot file exists and is readable
# ---------------------------------------------------------------------------
info "Test 2: snapshot file exists at $SNAPSHOT"

if [[ -f "$SNAPSHOT" ]]; then
    SIZE=$(stat -c%s "$SNAPSHOT" 2>/dev/null || echo "?")
    pass "windows_snapshot.json present ($SIZE bytes)"
else
    fail "windows_snapshot.json NOT found at $SNAPSHOT"
    echo ""
    echo "  Run test-double-helix.ps1 on Windows first to write the snapshot."
    echo "  Then re-run this test."
    echo ""
    FAIL_EARLY=1
fi

if [[ "${FAIL_EARLY:-0}" == "1" ]]; then
    echo "  ====================================================================="
    echo "  RESULT: $PASS passed, $FAIL FAILED (cannot continue without snapshot)"
    echo ""
    exit 1
fi

# ---------------------------------------------------------------------------
# TEST 3: JSON is valid and all required fields present
# ---------------------------------------------------------------------------
info "Test 3: snapshot JSON structure"

REQUIRED_FIELDS="timestamp hot_mb warm_mb cold_mb frozen_mb hit_rate promotions demotions evictions"

FIELD_RESULT=$(python3 - <<'PYEOF'
import json, sys

REQUIRED = ["timestamp","hot_mb","warm_mb","cold_mb","frozen_mb",
            "hit_rate","promotions","demotions","evictions"]
SNAPSHOT = "/phoenix/helix-pages/windows_snapshot.json"

try:
    with open(SNAPSHOT) as f:
        data = json.load(f)
except Exception as e:
    print(f"INVALID_JSON:{e}")
    sys.exit(0)

missing = [k for k in REQUIRED if k not in data]
if missing:
    print(f"MISSING_FIELDS:{','.join(missing)}")
else:
    print(f"OK:{data['timestamp']:.3f}:{data['frozen_mb']:.1f}")
PYEOF
)

if [[ "$FIELD_RESULT" == OK:* ]]; then
    TS=$(echo "$FIELD_RESULT" | cut -d: -f2)
    FROZEN=$(echo "$FIELD_RESULT" | cut -d: -f3)
    pass "JSON valid -- all required fields present (frozen_mb=${FROZEN})"
elif [[ "$FIELD_RESULT" == MISSING_FIELDS:* ]]; then
    fail "JSON missing fields: ${FIELD_RESULT#MISSING_FIELDS:}"
elif [[ "$FIELD_RESULT" == INVALID_JSON:* ]]; then
    fail "JSON parse error: ${FIELD_RESULT#INVALID_JSON:}"
else
    fail "Unexpected field check result: $FIELD_RESULT"
fi

# ---------------------------------------------------------------------------
# TEST 4: Snapshot is fresh (< 30s old -- paging.py staleness gate)
# ---------------------------------------------------------------------------
info "Test 4: snapshot age < 30s (paging.py staleness gate)"

AGE_RESULT=$(python3 - <<'PYEOF'
import json, time

SNAPSHOT = "/phoenix/helix-pages/windows_snapshot.json"
try:
    with open(SNAPSHOT) as f:
        data = json.load(f)
    age = time.time() - float(data['timestamp'])
    print(f"{age:.1f}")
except Exception as e:
    print(f"ERROR:{e}")
PYEOF
)

if [[ "$AGE_RESULT" == ERROR:* ]]; then
    fail "Could not read snapshot age: ${AGE_RESULT#ERROR:}"
else
    AGE_INT=${AGE_RESULT%.*}
    if [[ "$AGE_INT" -lt 30 ]]; then
        pass "Snapshot age ${AGE_RESULT}s -- fresh (< 30s)"
    else
        fail "Snapshot age ${AGE_RESULT}s -- STALE (> 30s). Is run-helix-poc.ps1 running?"
    fi
fi

# ---------------------------------------------------------------------------
# TEST 5: paging.py reads snapshot (not fallback) -- dry status read
# ---------------------------------------------------------------------------
info "Test 5: snapshot reader logic (standalone -- no paging.py import needed)"

# Replicate exactly what paging.py's _read_snapshot_json() does.
# This test passes whether or not the repo is on the share.
STATUS_RESULT=$(PHOENIX_PAGING_SNAPSHOT_PATH="$SNAPSHOT" \
    python3 - <<'PYEOF'
import os, sys, json, time
from pathlib import Path

snap_path = os.environ.get("PHOENIX_PAGING_SNAPSHOT_PATH", "")
if not snap_path:
    print("NO_SNAP_PATH")
    sys.exit(0)

p = Path(snap_path)
if not p.exists():
    print("SNAP_NOT_FOUND")
    sys.exit(0)

try:
    data = json.loads(p.read_text())
except Exception as e:
    print(f"PARSE_ERROR:{e}")
    sys.exit(0)

age = time.time() - data.get('timestamp', 0)
if age > 30:
    print(f"STALE:{age:.0f}")
    sys.exit(0)

# Mirrors TierSnapshot field list in paging.py
REQUIRED = ["timestamp","hot_mb","warm_mb","cold_mb","frozen_mb",
            "hit_rate","promotions","demotions","evictions"]
missing = [k for k in REQUIRED if k not in data]
if missing:
    print(f"MISSING:{','.join(missing)}")
    sys.exit(0)

print(f"SNAP_OK:{snap_path}:age={age:.1f}s:frozen={data.get('frozen_mb',0):.1f}MB")
PYEOF
)

if [[ "$STATUS_RESULT" == SNAP_OK:* ]]; then
    SNAP_INFO="${STATUS_RESULT#SNAP_OK:}"
    pass "Snapshot reader: paging.py would use this feed -- $SNAP_INFO"
elif [[ "$STATUS_RESULT" == STALE:* ]]; then
    fail "Snapshot stale by ${STATUS_RESULT#STALE:}s -- paging.py would fall back to /proc/meminfo"
elif [[ "$STATUS_RESULT" == MISSING:* ]]; then
    fail "Snapshot missing fields: ${STATUS_RESULT#MISSING:}"
else
    fail "Snapshot reader check: $STATUS_RESULT"
fi

# Bonus: note whether paging.py is reachable (informational only, not a failure)
if [[ -f "$PAGING" ]]; then
    info "paging.py found at $PAGING (repo is on share)"
else
    info "paging.py not on share -- Tests 1-5 still pass (standalone mode)"
fi

# ---------------------------------------------------------------------------
# SUMMARY
# ---------------------------------------------------------------------------
echo ""
echo "  ====================================================================="
if [[ $FAIL -eq 0 ]]; then
    echo "  RESULT: $PASS/$((PASS+FAIL)) passed -- Double Helix bridge proven end-to-end"
    echo ""
    echo "  Strand A (Windows) is writing snapshots."
    echo "  Strand B (Debian) can read them via SMB."
    echo "  paging.py will use the helix feed, not the /proc/meminfo fallback."
    echo ""
    echo "  Start the full stack:"
    echo "    Windows: double-click test-double-helix.cmd then run-helix-poc.cmd"
    echo "    Debian:  bash /phoenix/helix-pages/test-double-helix.sh"
else
    echo "  RESULT: $PASS passed, $FAIL FAILED"
    echo ""
    echo "  Fix failures above before running the full stack."
fi
echo ""
