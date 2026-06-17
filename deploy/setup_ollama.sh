#!/usr/bin/env bash
# setup_ollama.sh — Install Ollama + pull models on phoenix-ext
# Run: sudo bash ~/phoenix-devops/deploy/setup_ollama.sh

set -euo pipefail

REAL_USER="${SUDO_USER:-$USER}"
REAL_HOME="$(eval echo ~${REAL_USER})"

echo "[ollama] Installing Ollama..."
curl -fsSL https://ollama.com/install.sh | sh

echo "[ollama] Starting service..."
systemctl enable ollama
systemctl start ollama
sleep 3

echo "[ollama] Pulling models..."
# Primary: qwen2.5:3b — best reasoning per GB on CPU
sudo -u "$REAL_USER" ollama pull qwen2.5:3b
# Backup: phi3.5:mini — Microsoft efficient model, strong at code
sudo -u "$REAL_USER" ollama pull phi3.5:mini

echo ""
echo "=== Ollama LIVE ==="
echo "  API:     http://localhost:11434"
echo "  Models:  $(sudo -u "$REAL_USER" ollama list 2>/dev/null | tail -n +2 | awk '{print $1}' | tr '\n' ' ')"
echo "  Next:    python3 ~/phoenix-devops/sector4/frank/frank_ollama_bridge.py --test"
