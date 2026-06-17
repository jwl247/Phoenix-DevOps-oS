#!/usr/bin/env bash
# setup_telemetry.sh — Install Phoenix Telemetry Server on phoenix-ext
# Run: sudo bash ~/phoenix-devops/deploy/setup_telemetry.sh

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REAL_USER="${SUDO_USER:-$USER}"

echo "[telemetry] Installing dependencies..."
pip install --break-system-packages websockets psutil 2>/dev/null || \
  pip install websockets psutil

mkdir -p /tmp/phoenix_run

echo "[telemetry] Installing systemd service..."
sed \
  -e "s|PHOENIX_USER|${REAL_USER}|g" \
  -e "s|PHOENIX_REPO|${REPO}|g" \
  "${REPO}/sector3/services/phoenix-telemetry.service" \
  > /etc/systemd/system/phoenix-telemetry.service

systemctl daemon-reload
systemctl enable phoenix-telemetry
systemctl restart phoenix-telemetry
sleep 2

if systemctl is-active --quiet phoenix-telemetry; then
  echo ""
  echo "=== Telemetry Server LIVE ==="
  echo "  WebSocket: ws://$(hostname -I | awk '{print $1}'):7899"
  echo "  Test page: sector4/telemetry/hud_test.html"
  echo "  Logs:      journalctl -u phoenix-telemetry -f"
else
  echo "FAILED — check: journalctl -u phoenix-telemetry -n 30"
fi
