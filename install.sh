#!/usr/bin/env zsh
# install.sh — full Phoenix kernel sideload install
# Run inside WSL Debian as root
# Phoenix DevOps LLC — jwl247

set -e
SCRIPT_DIR="${0:A:h}"

echo "[phoenix] Starting dual-slot kernel sideload install...\n"

# ─── Build kernel modules ─────────────────────────────────────────
echo "[1/5] Installing kernel headers..."
apt-get install -y linux-headers-$(uname -r) build-essential

echo "[2/5] Building Frank3 slot modules..."
cd "$SCRIPT_DIR"
make all
make install

# ─── Install systemd units ────────────────────────────────────────
echo "[3/5] Installing systemd units..."
cp frank3-slot-a.service /etc/systemd/system/
cp frank3-slot-b.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable frank3-slot-a.service
systemctl enable frank3-slot-b.service
echo "[OK] Slot A (10s) and Slot B (15s failover) enabled"

# ─── Run saddle block ─────────────────────────────────────────────
echo "[4/5] Running saddle block..."
chmod +x "$SCRIPT_DIR/saddle_block.sh"
"$SCRIPT_DIR/saddle_block.sh"

# ─── Jupyter kernel registration ─────────────────────────────────
echo "[5/5] Registering Frank3 in Jupyter..."
python3 -m ipykernel install --user --name frank3_slot_a --display-name "Frank3 Slot A"
python3 -m ipykernel install --user --name frank3_slot_b --display-name "Frank3 Slot B"

echo "\n[phoenix] Install complete."
echo "[phoenix] Run: wsl --shutdown"
echo "[phoenix] Then restart WSL — Frank3 loads 10s after boot."
echo "[phoenix] Check status: systemctl status frank3-slot-a frank3-slot-b"
echo "[phoenix] Check kernel log: dmesg | grep frank3"
