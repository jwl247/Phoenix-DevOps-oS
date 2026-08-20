#!/usr/bin/env bash
# ============================================================
# deploy.sh — Phoenix DevOps Sector3/2 Deployment
# Promotes translator.sh into /etc/systemd/system (sector3)
# and /etc/systemd (sector2 backup). Requires sudo.
# ============================================================
set -euo pipefail

SECTOR3="/etc/systemd/system/translator.sh"
SECTOR2="/etc/systemd/translator.sh"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/translator/translator.sh"

echo "[PHOENIX] Deploying translator to sector3 and sector2..."

sudo cp "${SRC}" "${SECTOR3}"
sudo cp "${SRC}" "${SECTOR2}"
sudo chmod +x "${SECTOR3}" "${SECTOR2}"

echo "[PHOENIX] Verifying..."
[[ -x "${SECTOR3}" ]] && echo "  ✓ sector3: ${SECTOR3}"
[[ -x "${SECTOR2}" ]] && echo "  ✓ sector2: ${SECTOR2}"

echo ""
echo "[PHOENIX] Ready or not — here we come."
