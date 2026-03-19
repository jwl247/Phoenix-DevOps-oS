#!/usr/bin/env bash
# ============================================================
# deploy.sh — Phoenix DevOps Sector3/2 Deployment
# Promotes translator.sh into /etc/systemd/system (sector3)
# and /etc/systemd (sector2 backup). Requires sudo.
# Global: symlinks to /usr/local/bin/translator (Linux)
#         and %SystemRoot%\System32\translator.cmd (Windows)
# ============================================================
set -euo pipefail

SECTOR3="/etc/systemd/system/translator.sh"
SECTOR2="/etc/systemd/translator.sh"
GLOBAL_BIN="/usr/local/bin/translator"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/translator/translator.sh"

echo "[PHOENIX] Deploying translator to sector3 and sector2..."

sudo cp "${SRC}" "${SECTOR3}"
sudo cp "${SRC}" "${SECTOR2}"
sudo chmod +x "${SECTOR3}" "${SECTOR2}"

echo "[PHOENIX] Installing global symlink → ${GLOBAL_BIN}..."
sudo ln -sf "${SECTOR3}" "${GLOBAL_BIN}"
sudo chmod +x "${GLOBAL_BIN}"

# Windows: drop a .cmd shim if running under WSL or Git Bash with WINDIR set
if [[ -n "${WINDIR:-}" || -n "${SYSTEMROOT:-}" ]]; then
    WIN_ROOT="${SYSTEMROOT:-${WINDIR}}"
    WIN_SHIM="${WIN_ROOT}/System32/translator.cmd"
    # Convert SRC to Windows path for the shim
    WIN_SRC="$(wslpath -w "${SRC}" 2>/dev/null || cygpath -w "${SRC}" 2>/dev/null || echo "${SRC}")"
    echo "[PHOENIX] Writing Windows shim → ${WIN_SHIM}..."
    echo "@echo off" > /tmp/translator.cmd
    echo "bash \"${WIN_SRC}\" %*" >> /tmp/translator.cmd
    cp /tmp/translator.cmd "${WIN_SHIM}" 2>/dev/null \
        || echo "  [WARN] Could not write Windows shim — run as Administrator if needed"
fi

echo "[PHOENIX] Verifying..."
[[ -x "${SECTOR3}" ]]     && echo "  ✓ sector3:    ${SECTOR3}"
[[ -x "${SECTOR2}" ]]     && echo "  ✓ sector2:    ${SECTOR2}"
[[ -L "${GLOBAL_BIN}" ]]  && echo "  ✓ global:     ${GLOBAL_BIN} → $(readlink ${GLOBAL_BIN})"

echo ""
echo "[PHOENIX] Ready or not — here we come."
