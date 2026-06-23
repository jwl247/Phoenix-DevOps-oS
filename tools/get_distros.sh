#!/bin/bash
# ============================================================
# get_distros.sh — Download top 10 Linux ISOs to Ventoy
# Usage: sudo bash get_distros.sh [destination]
# Default destination: /opt/ventoy
# ============================================================

DEST="${1:-/opt/ventoy}"
LOG="$DEST/download.log"
FAIL=()

mkdir -p "$DEST"
echo "Downloading to: $DEST"
echo "Log: $LOG"
echo ""

download() {
    local name="$1"
    local url="$2"
    local file="$DEST/$(basename "$url")"

    echo "[$name]"
    if [ -f "$file" ] && [ -s "$file" ]; then
        echo "  Already exists, skipping: $(basename "$url")"
        return
    fi

    wget -c --show-progress -O "$file" "$url" 2>&1 | tee -a "$LOG"

    if [ $? -eq 0 ] && [ -s "$file" ]; then
        echo "  Done: $(basename "$url")"
    else
        echo "  FAILED: $name" | tee -a "$LOG"
        rm -f "$file"
        FAIL+=("$name")
    fi
    echo ""
}

# ============================================================
# Top 10 most popular Linux distros (x86_64 live/install ISOs)
# ============================================================

download "Ubuntu 24.04 LTS" \
    "https://releases.ubuntu.com/24.04/ubuntu-24.04.2-desktop-amd64.iso"

download "Linux Mint 22.1 Cinnamon" \
    "https://mirrors.edge.kernel.org/linuxmint/stable/22.1/linuxmint-22.1-cinnamon-64bit.iso"

download "Debian 12.9 Netinst" \
    "https://cdimage.debian.org/debian-cd/current/amd64/iso-cd/debian-12.9.0-amd64-netinst.iso"

download "Fedora 41 Workstation" \
    "https://download.fedoraproject.org/pub/fedora/linux/releases/41/Workstation/x86_64/iso/Fedora-Workstation-Live-x86_64-41-1.4.iso"

download "Kali Linux 2025.1 Live" \
    "https://cdimage.kali.org/kali-2025.1/kali-linux-2025.1-live-amd64.iso"

download "Manjaro 24 GNOME" \
    "https://download.manjaro.org/gnome/24.2.1/manjaro-gnome-24.2.1-241216-linux612.iso"

download "Pop!_OS 22.04 LTS" \
    "https://iso.pop-os.org/22.04/amd64/intel/42/pop-os_22.04_amd64_intel_42.iso"

download "Arch Linux" \
    "https://geo.mirror.pkgbuild.com/iso/latest/archlinux-x86_64.iso"

download "Rocky Linux 9 Minimal" \
    "https://download.rockylinux.org/pub/rocky/9/isos/x86_64/Rocky-9-latest-x86_64-minimal.iso"

download "Zorin OS 17 Core" \
    "https://mirrors.edge.kernel.org/zorinos-isos/17/Zorin-OS-17.2-Core-64-bit.iso"

# ============================================================
echo "============================================================"
echo "All downloads complete."
echo "ISOs saved to: $DEST"
echo ""

if [ ${#FAIL[@]} -gt 0 ]; then
    echo "FAILED downloads (check URLs or retry):"
    for f in "${FAIL[@]}"; do
        echo "  - $f"
    done
else
    echo "All distros downloaded successfully."
fi

sync
echo "Sync complete. Safe to unplug."
