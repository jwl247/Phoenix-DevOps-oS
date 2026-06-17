#!/usr/bin/env bash
# setup_conversion_agent.sh — Install LibreOffice headless + conversion agent service
# Run: sudo bash ~/phoenix-devops/deploy/setup_conversion_agent.sh

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REAL_USER="${SUDO_USER:-$USER}"
AGENT_SRC="$REPO/sector2/documents-worker/conversion_agent.py"
AGENT_DEST="/opt/phoenix/conversion_agent.py"
SERVICE_FILE="/etc/systemd/system/phoenix-conversion-agent.service"

echo "[Conversion Agent] Installing..."

# 1. LibreOffice headless
echo "[1/4] Installing LibreOffice headless..."
apt-get install -y libreoffice-nogui > /dev/null 2>&1
echo "      LibreOffice: $(libreoffice --version 2>/dev/null | head -1)"

# 2. Copy agent
echo "[2/4] Installing conversion_agent.py..."
mkdir -p /opt/phoenix
cp "$AGENT_SRC" "$AGENT_DEST"
chmod +x "$AGENT_DEST"

# 3. Audit log dir
mkdir -p /var/log/phoenix
chown "$REAL_USER:$REAL_USER" /var/log/phoenix

# 4. Systemd service
echo "[3/4] Installing systemd service..."
cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Phoenix Conversion Agent (LibreOffice headless)
After=network.target

[Service]
Type=simple
User=$REAL_USER
EnvironmentFile=/etc/phoenix/secrets.env
ExecStart=/usr/bin/python3 $AGENT_DEST
Restart=always
RestartSec=15
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable phoenix-conversion-agent

echo "[4/4] Service installed."
echo ""
echo "=== Conversion Agent ready ==="
echo "  Set PHOENIX_AUTH and DOCS_WORKER_URL in /etc/phoenix/secrets.env then:"
echo "  sudo systemctl start phoenix-conversion-agent"
echo "  sudo systemctl status phoenix-conversion-agent"
