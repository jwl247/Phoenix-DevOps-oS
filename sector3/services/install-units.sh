#!/usr/bin/env zsh
# Phoenix systemd corridor installer
# Run as root: sudo ./install-units.sh

set -e

UNIT_DIR="/etc/systemd/system"
SCRIPT_DIR="${0:A:h}"

echo "Installing Phoenix systemd units..."

# Copy all units and targets
for f in "$SCRIPT_DIR"/*.service "$SCRIPT_DIR"/*.target; do
    fname="${f:t}"
    echo "  -> $fname"
    cp "$f" "$UNIT_DIR/$fname"
    chmod 644 "$UNIT_DIR/$fname"
done

# Reload and enable
systemctl daemon-reload

echo "Enabling targets..."
systemctl enable phoenix-sector1.target
systemctl enable phoenix-sector2.target

echo "Enabling Sector 1 units..."
systemctl enable phoenix-log-setup.service
systemctl enable phoenix-auto-config.service
systemctl enable phoenix-frankenhelix.service
systemctl enable phoenix-frank-helix.service

echo "Enabling Sector 2 units..."
systemctl enable phoenix-intent-parser.service
systemctl enable phoenix-propagator.service
systemctl enable phoenix-mega-security.service
systemctl enable phoenix-unoserver.service
systemctl enable phoenix-doc-worker.service
systemctl enable phoenix-scheduler.service

echo ""
echo "Done. To start the full stack:"
echo "  sudo systemctl start phoenix-sector1.target"
echo "  sudo systemctl start phoenix-sector2.target"
echo ""
echo "To check status:"
echo "  systemctl status 'phoenix-*'"
echo ""
echo "To watch logs:"
echo "  journalctl -u 'phoenix-*' -f"
