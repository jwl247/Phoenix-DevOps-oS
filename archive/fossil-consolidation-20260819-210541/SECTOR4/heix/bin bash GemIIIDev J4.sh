#!/bin/bash
# 💎 GemIIIDev - J4 Approved Artifact
# SHEDDING PROTOCOL v1.0: "THE BOOSTER SEPARATION"
# Removes boot-only artifacts to leave only the Kernel-Driven Runtime.

GREEN='\033[92m'
CYAN='\033[96m'
YELLOW='\033[93m'
RESET='\033[0m'

echo -e "${CYAN}🚀 SHEDDING PROTOCOL: Transitioning to Post-Boot Purity...${RESET}"

# 1. Stop Legacy/Scaffolding Services
echo -e "${YELLOW}Stopping Discovery & Scaffolding Services...${RESET}"
SERVICES=("enco_confD" "enco_tranD" "enco_franD" "enco_guarD")

for s in "${SERVICES[@]}"; do
    sudo systemctl stop "$s" 2>/dev/null
    sudo systemctl disable "$s" 2>/dev/null
    echo -e "   🔻 $s: SHED"
done

# 2. Lockdown the Core Runtime
echo -e "${YELLOW}Locking down the Neural Minimum...${RESET}"
# Only the Agnostic Layer, Propagator, and Telemetry remain.
sudo systemctl restart enco_agnoD
sudo systemctl restart enco_propD
sudo systemctl restart enco_telemetryD

# 3. Clean the /tmp Context
# The Agnostic Worker will immediately republish a clean context.
rm -f /tmp/gemiii_context.json
echo -e "   ✨ Neural Context Refreshed."

# 4. Verify Ring 0 Dictation
if [ -e "/dev/encompass" ]; then
    echo -e "${GREEN}✅ SUCCESS: Kernel is Dictating the Rules.${RESET}"
    echo -e "   System is running on the Native Helix-Whale Link."
else
    echo -e "${RED}❌ WARNING: /dev/encompass not found. Kernel Link Offline.${RESET}"
fi

echo -e "\n${CYAN}The Booster is separated. The Whale is in orbit.${RESET}"
