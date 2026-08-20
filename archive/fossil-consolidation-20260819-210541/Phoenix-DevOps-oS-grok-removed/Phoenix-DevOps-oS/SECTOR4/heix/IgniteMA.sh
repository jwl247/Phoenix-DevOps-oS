#!/bin/bash
# 💎 GemIIIDev - Sacrifice Game: MASTER IGNITION
# Role: Registers and starts the background daemons for the Magnet-Helix stack.

ROOT="/opt/SacrificeGame"
USER_NAME=$(whoami)
PYTHON_BIN=$(which python3)

echo -e "\033[96m🚀 IGNITING SACRIFICE BACKGROUND STACK...\033[0m"

# 1. Create Sync Engine Service (Buffer Heartbeat)
cat <<EOF | sudo tee /etc/systemd/system/sacrifice-sync.service > /dev/null
[Unit]
Description=Sacrifice Sync Engine: Neural Heartbeat
After=network.target

[Service]
Type=simple
User=${USER_NAME}
WorkingDirectory=${ROOT}/Source
ExecStart=${PYTHON_BIN} -u ${ROOT}/Source/SacrificeSyncEngine.py
Restart=always
RestartSec=2
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

# 2. Create Portal Service (Command Bridge API)
cat <<EOF | sudo tee /etc/systemd/system/sacrifice-portal.service > /dev/null
[Unit]
Description=Sacrifice Portal: Command Bridge Bridge
After=sacrifice-sync.service

[Service]
Type=simple
User=${USER_NAME}
WorkingDirectory=${ROOT}/Source
ExecStart=${PYTHON_BIN} -u ${ROOT}/Source/SacrificePortal.py
Restart=always
RestartSec=3
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

# 3. Reload and Ignite
sudo systemctl daemon-reload
sudo systemctl enable sacrifice-sync sacrifice-portal
sudo systemctl start sacrifice-sync sacrifice-portal

echo -e "\033[92m✅ DAEMONS REGISTERED AND PULSING.\033[0m"
echo "Monitor with: sudo systemctl status sacrifice-sync"
