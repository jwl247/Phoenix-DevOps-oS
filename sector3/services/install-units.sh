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

# Enable a unit only if it exists AND the program its ExecStart names is on
# this box. Most legacy units here still point at /home/jwl247/projects/phoenix
# paths that do not exist (round-2 S34OPS-F04); enabling those just fails at
# boot. The Helix team units are installed by tools/helix-team/install-team.sh.
enable_if_real() {
    local unit="$1" exec_path
    if [[ ! -f "$UNIT_DIR/$unit" ]]; then
        echo "  skip $unit (no such unit file)"; return 0
    fi
    exec_path=$(grep -m1 '^ExecStart=' "$UNIT_DIR/$unit" | sed -E 's/^ExecStart=-?//' | awk '{print $1}')
    if [[ "$exec_path" == /usr/bin/python3 || "$exec_path" == /usr/bin/env ]]; then
        exec_path=$(grep -m1 '^ExecStart=' "$UNIT_DIR/$unit" | sed -E 's/^ExecStart=-?//' | awk '{print $2}')
    fi
    if [[ -n "$exec_path" && "$exec_path" == /* && ! -e "$exec_path" ]]; then
        echo "  skip $unit (ExecStart $exec_path not on this box)"; return 0
    fi
    systemctl enable "$unit" && echo "  enabled $unit"
}

echo "Enabling targets..."
enable_if_real phoenix-sector1.target
enable_if_real phoenix-sector2.target

echo "Enabling Sector 1 units..."
enable_if_real phoenix-auto-config.service
enable_if_real phoenix-frankenhelix.service
enable_if_real phoenix-frank-helix.service

echo "Enabling Sector 2 units..."
enable_if_real phoenix-intent-parser.service
enable_if_real phoenix-propagator.service
enable_if_real phoenix-mega-security.service
enable_if_real phoenix-unoserver.service
enable_if_real phoenix-doc-worker.service
enable_if_real phoenix-scheduler.service

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
