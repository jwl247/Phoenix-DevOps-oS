#!/usr/bin/env zsh
# Phoenix systemd unit installer
# Run as root: sudo ./install-units.sh
# Installs all Phoenix service and target units, enables by sector

set -e

UNIT_DIR="/etc/systemd/system"
SCRIPT_DIR="${0:A:h}"

echo "Installing Phoenix systemd units..."

for f in "$SCRIPT_DIR"/*.service "$SCRIPT_DIR"/*.target; do
    fname="${f:t}"
    echo "  -> $fname"
    cp "$f" "$UNIT_DIR/$fname"
    chmod 644 "$UNIT_DIR/$fname"
done

systemctl daemon-reload

echo ""
echo "Enabling foundation..."
systemctl enable phoenix-log-setup.service

echo ""
echo "Enabling Sector 1 target + units..."
systemctl enable phoenix-sector1.target
systemctl enable phoenix-log-setup.service
systemctl enable phoenix-auto-config.service
systemctl enable phoenix-frankenhelix.service
systemctl enable phoenix-frank-helix.service

echo ""
echo "Enabling Sector 2 target + units..."
systemctl enable phoenix-sector2.target
systemctl enable phoenix-intent-parser.service
systemctl enable phoenix-propagator.service
systemctl enable phoenix-mega-security.service
systemctl enable phoenix-unoserver.service
systemctl enable phoenix-doc-worker.service
systemctl enable phoenix-scheduler.service

echo ""
echo "Enabling Sector 3 target + units..."
systemctl enable phoenix-sector3.target
systemctl enable phoenix-romeo.service
systemctl enable phoenix-juliet.service
systemctl enable phoenix-dbl-juliet.service
systemctl enable phoenix-quadengine.service

echo ""
echo "Enabling Sector 4 target + units..."
systemctl enable phoenix-sector4.target
systemctl enable phoenix-helix.service
systemctl enable phoenix-frank.service

echo ""
echo "Enabling kernel slots..."
systemctl enable frank3-slot-a.service
systemctl enable frank3-slot-b.service

echo ""
echo "Done."
echo ""
echo "Start order:"
echo "  sudo systemctl start phoenix-sector1.target"
echo "  sudo systemctl start phoenix-sector2.target"
echo "  sudo systemctl start phoenix-sector3.target"
echo "  sudo systemctl start phoenix-sector4.target"
echo ""
echo "Status:"
echo "  systemctl status 'phoenix-*'"
echo ""
echo "Logs:"
echo "  journalctl -u 'phoenix-*' -f"
