#!/usr/bin/env bash
# setup_phoenix_ext.sh — Run this ON phoenix-ext with sudo
# Installs Phase 1 prerequisites + Phoenix kernel as a service
#
# Usage (from phoenix-ext):
#   cd ~/phoenix-devops
#   sudo bash deploy/setup_phoenix_ext.sh

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
USER_HOME="$(eval echo ~${SUDO_USER:-$USER})"
PHOENIX_USER="${SUDO_USER:-$USER}"

echo "[Phoenix] Repo:  $REPO"
echo "[Phoenix] User:  $PHOENIX_USER"
echo "[Phoenix] Home:  $USER_HOME"
echo ""

# ── Phase 1: Prometheus ───────────────────────────────────────────────────────
echo "[1/4] Installing Prometheus..."
apt-get install -y prometheus > /dev/null 2>&1
systemctl enable prometheus
systemctl start prometheus
echo "      Prometheus: $(prometheus --version 2>&1 | head -1)"

# ── Phase 1: Nextcloud (snap) ─────────────────────────────────────────────────
echo "[2/4] Installing Nextcloud (snap)..."
if ! snap list nextcloud 2>/dev/null | grep -q nextcloud; then
    snap install nextcloud
    echo "      Nextcloud installed via snap"
else
    echo "      Nextcloud already installed"
fi

# ── Phoenix log directory ─────────────────────────────────────────────────────
echo "[3/4] Creating Phoenix log directory..."
mkdir -p /var/log/phoenix
chown "${PHOENIX_USER}:${PHOENIX_USER}" /var/log/phoenix
echo "      /var/log/phoenix ready"

# ── Phoenix kernel systemd service ───────────────────────────────────────────
echo "[4/4] Installing Phoenix kernel service..."

SERVICE_SRC="${REPO}/sector3/services/phoenix-kernel.service"
SERVICE_DST="/etc/systemd/system/phoenix-kernel.service"

sed \
    -e "s|PHOENIX_USER|${PHOENIX_USER}|g" \
    -e "s|PHOENIX_REPO|${REPO}|g" \
    "$SERVICE_SRC" > "$SERVICE_DST"

systemctl daemon-reload
systemctl enable phoenix-kernel
systemctl start phoenix-kernel

sleep 2
if systemctl is-active --quiet phoenix-kernel; then
    echo "      phoenix-kernel.service: RUNNING"
else
    echo "      phoenix-kernel.service: FAILED — check: journalctl -u phoenix-kernel -n 30"
fi

echo ""
echo "=== Phoenix Phase 1 Complete ==="
echo "  Prometheus:      http://localhost:9090"
echo "  Nextcloud:       http://localhost (first-run setup)"
echo "  Phoenix Kernel:  systemctl status phoenix-kernel"
echo "  Helix-I ports:   7701-7704"
echo "  Helix-E ports:   7805-7808"
echo ""
echo "  Next: sudo bash deploy/setup_phoenix_ext.sh  (idempotent — safe to re-run)"
