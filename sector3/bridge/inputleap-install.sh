#!/usr/bin/env bash
# =============================================================================
# inputleap-install.sh — Install and configure Input Leap client on Phoenix
# Run on the Linux/Phoenix machine after booting
#
# Usage:
#   ./inputleap-install.sh <windows-ip>
#   ./inputleap-install.sh 192.168.1.50
# =============================================================================

set -euo pipefail

WINDOWS_IP="${1:-}"

if [[ -z "${WINDOWS_IP}" ]]; then
    echo "Usage: inputleap-install.sh <windows-lan-ip>"
    echo ""
    echo "Find your Windows LAN IP:"
    echo "  Windows: ipconfig | findstr IPv4"
    echo "  Then re-run: inputleap-install.sh 192.168.x.x"
    exit 1
fi

echo "[inputleap] Installing Input Leap client..."

# Install
if ! command -v input-leapc &>/dev/null; then
    sudo apt-get update -q
    sudo apt-get install -y input-leap
    echo "[inputleap] Input Leap installed"
else
    echo "[inputleap] Input Leap already installed"
fi

# Install service with correct IP
SERVICE_SRC="$(dirname "$0")/../services/phoenix-inputleap-client.service"
SERVICE_DEST="/etc/systemd/system/phoenix-inputleap-client.service"

if [[ -f "${SERVICE_SRC}" ]]; then
    sudo cp "${SERVICE_SRC}" "${SERVICE_DEST}"
    # Inject the real Windows IP
    sudo sed -i "s/WINDOWS_HOST_IP=192.168.1.100/WINDOWS_HOST_IP=${WINDOWS_IP}/" "${SERVICE_DEST}"
    sudo chmod 644 "${SERVICE_DEST}"
    echo "[inputleap] Service installed with IP: ${WINDOWS_IP}"
else
    echo "[inputleap] WARN: service file not found at ${SERVICE_SRC}"
fi

sudo systemctl daemon-reload
sudo systemctl enable phoenix-inputleap-client.service
sudo systemctl start  phoenix-inputleap-client.service

echo ""
echo "[inputleap] Done."
echo "[inputleap] Status: systemctl status phoenix-inputleap-client"
echo "[inputleap] Logs:   journalctl -u phoenix-inputleap-client -f"
echo ""
echo "Windows side — run Input Leap as server, use this config:"
echo "  sector3/bridge/inputleap-server.conf"
echo "  Copy to: %USERPROFILE%\\AppData\\Local\\InputLeap\\InputLeap.conf"
echo ""
echo "Friday (Synergy): copy inputleap-server.conf → synergy.conf — same format."
