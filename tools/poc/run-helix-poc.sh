#!/usr/bin/env bash
# =============================================================================
# run-helix-poc.sh -- Phoenix Double Helix PoC launcher (Debian / Strand B watcher)
#
# Starts paging.py (Linux paging brain) pointed at the shared snapshot JSON
# written by Strand A (Windows). paging.py watches both strands and controls
# the Linux swapfile as the shared overflow pool.
#
# Run this INSIDE Debian (SSH or console) after run-helix-poc.ps1 is running
# on Windows and F:\Phoenix\helix-pages\ is producing windows_snapshot.json.
#
# Usage (inside Debian):
#   bash /phoenix/Phoenix-DevOps-oS/tools/poc/run-helix-poc.sh
#
# Prerequisites:
#   - Shared FS mounted: /phoenix/ (SMB over QEMU 10.0.2.2)
#   - paging.py requires root: run with sudo or as root
#   - python3 available
# =============================================================================

set -euo pipefail

SHARE="/phoenix"
SNAPSHOT="$SHARE/helix-pages/windows_snapshot.json"
REPO="$SHARE/Phoenix-DevOps-oS"
PAGE_DIR="$SHARE/helix-pages"

# paging.py location: prefer repo copy, fall back to helix-pages/ copy
# (Windows test script copies paging.py to helix-pages/ automatically)
if [[ -f "$REPO/sector4/paging.py" ]]; then
    PAGING="$REPO/sector4/paging.py"
elif [[ -f "$PAGE_DIR/paging.py" ]]; then
    PAGING="$PAGE_DIR/paging.py"
else
    PAGING=""
fi

# -- Banner -------------------------------------------------------------------
echo ""
echo "  +------------------------------------------------------+"
echo "  |  Phoenix Double Helix PoC -- Debian / Strand B       |"
echo "  |  paging.py -- one brain watching both strands        |"
echo "  +------------------------------------------------------+"
echo ""

# -- Verify shared FS is mounted and non-empty --------------------------------
if ! mountpoint -q "$SHARE" 2>/dev/null && ! mount | grep -q "$SHARE"; then
    echo "  [ERROR] $SHARE is not mounted."
    echo ""
    echo "  Mount it first:"
    echo "    sudo mount -t cifs //10.0.2.2/Phoenix $SHARE \\"
    echo "      -o username=jwlef,password=YOUR_PASS,uid=1000,gid=1000,vers=3.0"
    echo ""
    exit 1
fi

echo "  [OK]  Shared FS mounted: $SHARE"

if [[ -z "$PAGING" ]]; then
    echo "  [ERROR] paging.py not found."
    echo "  Expected at: $REPO/sector4/paging.py"
    echo "          or: $PAGE_DIR/paging.py"
    echo ""
    echo "  Run test-double-helix.cmd on Windows to copy paging.py to the share."
    exit 1
fi

echo "  [OK]  paging.py: $PAGING"

# -- Verify snapshot exists (Windows side must be running) --------------------
if [[ ! -f "$SNAPSHOT" ]]; then
    echo "  [WARN] Snapshot not yet present: $SNAPSHOT"
    echo "  Make sure run-helix-poc.ps1 is running on Windows first."
    echo "  paging.py will start in fallback mode until the snapshot appears."
    echo ""
fi

# -- Set environment ----------------------------------------------------------
export PHOENIX_HELIX_PAGE_DIR="$PAGE_DIR"
export PHOENIX_PAGING_SNAPSHOT_PATH="$SNAPSHOT"

echo "  [OK]  PHOENIX_HELIX_PAGE_DIR=$PAGE_DIR"
echo "  [OK]  Snapshot path: $SNAPSHOT"
echo ""

# -- Root check ---------------------------------------------------------------
if [[ $EUID -ne 0 ]]; then
    echo "  [WARN] paging.py requires root to manage the swapfile."
    echo "  Re-running with sudo..."
    echo ""
    exec sudo \
        PHOENIX_HELIX_PAGE_DIR="$PAGE_DIR" \
        PHOENIX_PAGING_SNAPSHOT_PATH="$SNAPSHOT" \
        python3 "$PAGING" start
fi

# -- Launch -------------------------------------------------------------------
echo "  Starting paging.py with snapshot path: $SNAPSHOT"
echo "  Tier source: windows_snapshot.json (Windows Strand A feed)"
echo ""

python3 "$PAGING" start
