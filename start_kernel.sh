#!/usr/bin/env bash
# start_kernel.sh — Boot Phoenix HLK (dev / WSL)
# Sets PHOENIX_SECTOR* to live repo paths, fires the kernel.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export PHOENIX_SECTOR1="${REPO}/sector1"
export PHOENIX_SECTOR2="${REPO}/sector2"
export PHOENIX_SECTOR3="${REPO}/sector3"
export PHOENIX_SECTOR4="${REPO}/sector4"
export PHOENIX_SUITS="${REPO}"
export PHOENIX_SHM="/tmp/phoenix_shm"
export PHOENIX_AUDIT="/tmp/phoenix_audit.log"
export PHOENIX_CUSTODY="/tmp/phoenix_custody.jsonl"
export CLONEPOOL_DIR="${CLONEPOOL_DIR:-${HOME}/Phoenix/clonepool}"

echo "[Phoenix] Repo:     $REPO"
echo "[Phoenix] Clonepool: $CLONEPOOL_DIR"
echo "[Phoenix] Booting kernel..."

exec python3 "${REPO}/phoenix_universal_kernel/main_kernel.py"
