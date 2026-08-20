#!/bin/bash
# 💎 GemIIIDev - Sacrifice Game: SYSTEMD DOOR ARMORY
# Purpose: Permanently locking the Hub into Fedora's System Rail.

GREEN='\033[92m'
CYAN='\033[96m'
BOLD='\033[1m'
RESET='\033[0m'

ROOT="/opt/SacrificeGame"
USER_NAME=$(whoami)
PYTHON_BIN=$(which python3)

echo -e "${CYAN}${BOLD}🔗 LOCKING DOORS: MAGNET-HELIX PERSISTENCE...${RESET}"

# Helper: Create .service file
create_door() {
    NAME=$1
    FILE=$2
    DESC=$3
    DEPS=$4

    SERVICE_FILE="/etc/systemd/system/sacrifice-${NAME}.service"
    echo "🚪 Forging Door: sacrifice-${NAME}.service"

    cat <<EOF | sudo tee $SERVICE_FILE > /dev/null
[Unit]
Description=Sacrifice Game: ${DESC}
After=network.target ${DEPS}

[Service]
Type=simple
User=${USER_NAME}
WorkingDirectory=${ROOT}/Source
ExecStart=${PYTHON_BIN} -u ${ROOT}/Source/${FILE}
Restart=always
RestartSec=3
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF
}

# --- 1. THE SYNC ENGINE (Buffer Heartbeat) ---
create_door "sync" "SacrificeSyncEngine.py" "Neural Buffer Heartbeat" ""

# --- 2. THE PORTAL (High-Speed API) ---
create_door "portal" "SacrificePortal.py" "Neural Portal Bridge" "sacrifice-sync.service"

# 3. Reload and Enable
echo -e "\n${CYAN}🔄 Reloading Systemd...${RESET}"
sudo systemctl daemon-reload
sudo systemctl enable sacrifice-sync sacrifice-portal

echo -e "\n${GREEN}${BOLD}✅ HUB LOCKED INTO BOOT RAIL.${RESET}"
