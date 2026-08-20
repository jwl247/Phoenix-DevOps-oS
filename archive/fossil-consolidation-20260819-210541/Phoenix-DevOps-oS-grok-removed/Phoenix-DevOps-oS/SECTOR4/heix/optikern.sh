#!/bin/bash
# 💎 GemIIIDev - J4 Approved Artifact
# FEDORA FORGE v2.1: "LAPTOP SOVEREIGNTY"
# Optimized for Fedora 40/41+ and Kernel 6.x.

GREEN='\033[92m'
CYAN='\033[96m'
YELLOW='\033[93m'
BOLD='\033[1m'
RESET='\033[0m'

ROOT="/opt/HEix7_3GIII"

echo -e "${CYAN}${BOLD}🌌 GEMIII FEDORA FORGE: IGNITING NATIVE HARDWARE...${RESET}"

# 1. Arming Fedora Toolchain
echo -e "${YELLOW}[1/5] Arming dnf toolchain...${RESET}"
sudo dnf install -y kernel-devel-$(uname -r) kernel-headers gcc make lvm2 rsync python3-devel bc
sudo dnf groupinstall -y "Development Tools"

# 2. Establishing Sovereign Hub
echo -e "${YELLOW}[2/5] Creating /opt Hub and Staging area...${RESET}"
sudo mkdir -p $ROOT/{core,network,elements,interface,magnet_index,staging_area}
sudo chown -R $USER:$USER $ROOT/

# 3. Initializing 3-Buffer Pipeline (The End Game)
echo -e "${YELLOW}[3/5] Seeding invisible buffers...${RESET}"
for i in {1..3}; do
    touch "$ROOT/staging_area/.buf$i"
done
echo -e "   ✅ Buffers .buf1, .buf2, .buf3 initialized."

# 4. Persistence setup
echo -e "${YELLOW}[4/5] Setting up udev rules for /dev/encompass...${RESET}"
echo 'KERNEL=="encompass", MODE="0666"' | sudo tee /etc/udev/rules.d/99-encompass.rules
sudo udevadm control --reload-rules

# 5. Environment Cleanup
rm -f /tmp/gemiii_context.json
echo -e "\n${GREEN}${BOLD}✅ FEDORA BASELINE NOMINAL.${RESET}"
echo "------------------------------------------------"
echo "Next Maneuver: [Step 2] Carve 1T Whale"
