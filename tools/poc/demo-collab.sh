#!/usr/bin/env bash
# =============================================================================
# demo-collab.sh — Phoenix Collaboration Demo (Debian side)
#
# This is the Debian half of the collaboration demo.
# Run this inside Debian (SSH or console) FIRST, then run demo-collab.ps1
# on Windows to watch Phoenix intake and promote the result.
#
# What this does:
#   1. Writes hello-phoenix.py to /phoenix/Projects/  (shared FS)
#   2. Runs it — produces output.txt in the same dir
#   3. Writes a manifest so Windows knows what to intake
#   4. Prints a signal line Windows watches for
#
# Prerequisites:
#   - Debian booted via: usys run debian
#   - Shared FS mounted: sudo mount -t cifs //10.0.2.2/Phoenix /phoenix \
#       -o username=jwlef,password=...,uid=1000,gid=1000,vers=3.0
#   - /phoenix/Projects/ exists and is writable
#
# Usage (inside Debian):
#   bash /phoenix/Projects/demo-collab.sh
#   -- or copy it in manually and run it --
# =============================================================================

set -euo pipefail

SHARE="/phoenix/Projects"
SCRIPT_NAME="hello-phoenix.py"
OUTPUT_NAME="output.txt"
MANIFEST_NAME="demo-collab.ready"

# ── Colors ───────────────────────────────────────────────────────────────────
G='\033[0;32m'; Y='\033[1;33m'; C='\033[0;36m'; W='\033[1;37m'; R='\033[0m'

echo ""
printf "${C}  Phoenix Collaboration Demo — Debian side${R}\n"
printf "${W}  Writing to shared FS → Windows intakes via Phoenix${R}\n"
echo ""

# ── Step 1: verify the share is mounted and writable ─────────────────────────
if ! mountpoint -q /phoenix 2>/dev/null && ! mount | grep -q '/phoenix'; then
    printf "${Y}  /phoenix is not mounted. Mount it first:${R}\n"
    printf "  sudo mount -t cifs //10.0.2.2/Phoenix /phoenix \\\\\n"
    printf "    -o username=jwlef,password=YOUR_PASS,uid=1000,gid=1000,vers=3.0\n\n"
    exit 1
fi

if [[ ! -d "$SHARE" ]]; then
    printf "${Y}  $SHARE not found — creating it${R}\n"
    mkdir -p "$SHARE"
fi

if [[ ! -w "$SHARE" ]]; then
    printf "\033[0;31m  ERROR: $SHARE is not writable. Check mount options (uid=1000).${R}\n"
    exit 1
fi

printf "${G}  ✓ Share mounted and writable: $SHARE${R}\n"
echo ""

# ── Step 2: write hello-phoenix.py ───────────────────────────────────────────
SCRIPT_PATH="$SHARE/$SCRIPT_NAME"
HOSTNAME_DEB=$(hostname)
DATE_NOW=$(date -u '+%Y-%m-%dT%H:%M:%SZ')

cat > "$SCRIPT_PATH" << PYEOF
#!/usr/bin/env python3
"""
hello-phoenix.py
Written on Debian ($HOSTNAME_DEB) at $DATE_NOW via shared FS.
Intaked by Phoenix on Windows. Runs anywhere Phoenix runs.
"""

import platform, datetime, socket

def main():
    print("=" * 56)
    print("  Phoenix Collaboration Demo")
    print("=" * 56)
    print(f"  Written on : Debian ($HOSTNAME_DEB)")
    print(f"  Ran on     : {platform.system()} {platform.release()}")
    print(f"  Host       : {socket.gethostname()}")
    print(f"  Time       : {datetime.datetime.utcnow().isoformat()}Z")
    print(f"  Python     : {platform.python_version()}")
    print("=" * 56)
    print("  No install. No wizard. Phoenix brought this here.")
    print("  Written in Debian. Intaked on Windows.")
    print("  Runs anywhere Phoenix runs.")
    print("=" * 56)

if __name__ == "__main__":
    main()
PYEOF

chmod +x "$SCRIPT_PATH"
printf "${G}  ✓ Written: $SCRIPT_PATH${R}\n"

# ── Step 3: run it — output goes to the shared dir ───────────────────────────
OUTPUT_PATH="$SHARE/$OUTPUT_NAME"
python3 "$SCRIPT_PATH" | tee "$OUTPUT_PATH"
echo ""
printf "${G}  ✓ Output written: $OUTPUT_PATH${R}\n"

# ── Step 4: write the ready manifest ─────────────────────────────────────────
MANIFEST_PATH="$SHARE/$MANIFEST_NAME"
cat > "$MANIFEST_PATH" << MEOF
script=$SCRIPT_NAME
output=$OUTPUT_NAME
written_by=$HOSTNAME_DEB
written_at=$DATE_NOW
platform=debian
ready=true
MEOF

printf "${G}  ✓ Manifest written: $MANIFEST_PATH${R}\n"
echo ""

# ── Step 5: signal ────────────────────────────────────────────────────────────
printf "${C}  ============================================================${R}\n"
printf "${W}  DEBIAN SIDE COMPLETE.${R}\n"
printf "${C}  Now run on Windows (PS7):${R}\n"
printf "${W}    pwsh -NoProfile -ExecutionPolicy Bypass -File tools\\poc\\demo-collab.ps1${R}\n"
printf "${C}  Or via usys:${R}\n"
printf "${W}    . scripts\\usys.ps1; usys run demo-collab${R}\n"
printf "${C}  ============================================================${R}\n"
echo ""
