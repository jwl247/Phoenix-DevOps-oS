#!/bin/bash
set -euo pipefail

KALI="/kali/home/jwl247"
DEST="/mnt/c/Users/jwlef/PhoenixDevOps/_kali_import"

echo "[1] Mounting Kali drive..."
mkdir -p /kali
mount -t ext4 /dev/sdd1 /kali 2>/dev/null || echo "already mounted"

echo "[2] Verifying source..."
ls "$KALI/"

echo "[3] Copying to Windows..."
mkdir -p "$DEST"
cp -r "$KALI/Downloads/phoenix"/. "$DEST/phoenix/"
cp    "$KALI/dblhelix.py"              "$DEST/"
cp    "$KALI/dblhelix1.py"             "$DEST/"
cp    "$KALI/franken2.py"              "$DEST/"
cp    "$KALI/Documents/README_sector4.md" "$DEST/"
cp    "$KALI/Downloads/UNITEDSYS_README.md" "$DEST/"
cp    "$KALI/Downloads/install.sh"     "$DEST/install_kali.sh"
cp -r "$KALI/RECOVERED"               "$DEST/"
cp -r "$KALI/RECOVERED2"              "$DEST/"

echo "[4] Done. Verifying Windows dest:"
ls "$DEST/"
