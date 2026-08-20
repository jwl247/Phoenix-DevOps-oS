#!/bin/bash
# 💎 GemIIIDev - J4 Approved Artifact
# UNIVERSAL SYNC GUN v1.0
# Surgical tool to force a "Case 2" Sync for any data block.

ROOT="/etc/HEix7_3GIII"
STAGING="$ROOT/staging_area"
LIVE="$ROOT/core/live_entry.py"

echo -e "\033[96m🔫 UNIVERSAL SYNC GUN: Ready to Fire.\033[0m"

if [ -z "$1" ]; then
    echo "Usage: ./universal_sync_gun.sh [source_file_or_buffer]"
    echo "Example: ./universal_sync_gun.sh .buf3"
    exit 1
fi

SOURCE="$1"

# If user just typed '.buf3', expand it to the full path
if [[ "$SOURCE" == "."* ]]; then
    SOURCE="$STAGING/$SOURCE"
fi

if [ ! -f "$SOURCE" ]; then
    echo -e "\033[91m❌ Error: Source $SOURCE not found.\033[0m"
    exit 1
fi

echo "🚀 Target: $LIVE"
echo "⚙️  Executing Delta-Sync (--inplace)..."

# The Gun Command
rsync -av --inplace --no-whole-file --progress "$SOURCE" "$LIVE"

if [ $? -eq 0 ]; then
    echo -e "\033[92m✅ HIT: Sync Complete. Live Entry Point is now Updated.\033[0m"
    # Inform the Supervisor to update the state
    echo "{\"manual_sync_trigger\": \"$(date)\", \"source\": \"$SOURCE\"}" > "$ROOT/magnet_index/pcs_manual_sync.json"
else
    echo -e "\033[91m❌ MISFIRE: Sync Failed.\033[0m"
fi
