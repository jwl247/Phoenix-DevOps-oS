#!/usr/bin/env bash
# setup_breach_coms.sh — Initialize breach_coms 4-tier vault on phoenix-ext
# Run: sudo bash ~/phoenix-devops/deploy/setup_breach_coms.sh
#
# Tier map:
#   breach_coms4 → T1 PRIMARY    (sdc1, label: breach-coms4)  master vault
#   breach_coms3 → T2 SECONDARY  (sdb1, label: breach-coms3)  day-1 mirror
#   breach_coms2 → T3 TERTIARY   (sdc2, label: breach-coms2)  day-2 mirror
#   breach_coms1 → T4 TERTIARY   (internal dir)               day-3 mirror
#   clonepool    → /breach_coms4/clonepool                     callable face

set -euo pipefail

REAL_USER="${SUDO_USER:-$USER}"
REAL_HOME="$(eval echo ~${REAL_USER})"

echo "[breach_coms] User: $REAL_USER"
echo ""

# ── Step 1: Format sdb → breach-coms3 ────────────────────────────────────────
echo "[1/6] Formatting sdb → breach-coms3 (T2 SECONDARY)..."
umount /dev/sdb1 2>/dev/null || true
umount /dev/sdb2 2>/dev/null || true
parted /dev/sdb --script mklabel gpt mkpart primary ext4 0% 100%
sleep 1
mkfs.ext4 -F -L breach-coms3 /dev/sdb1
echo "      sdb → breach-coms3 ready"

# ── Step 2: Relabel sdc1 → breach-coms4 ──────────────────────────────────────
echo "[2/6] Relabeling sdc1 → breach-coms4 (T1 PRIMARY)..."
umount /dev/sdc1 2>/dev/null || true
e2label /dev/sdc1 breach-coms4
echo "      sdc1 → breach-coms4 ready"

# ── Step 3: Relabel sdc2 → breach-coms2 ──────────────────────────────────────
echo "[3/6] Relabeling sdc2 → breach-coms2 (T3 TERTIARY)..."
umount /dev/sdc2 2>/dev/null || true
e2label /dev/sdc2 breach-coms2
echo "      sdc2 → breach-coms2 ready"

# ── Step 4: Create mount points ───────────────────────────────────────────────
echo "[4/6] Creating mount points..."
mkdir -p /breach_coms4 /breach_coms3 /breach_coms2 /breach_coms1
chown "${REAL_USER}:${REAL_USER}" /breach_coms4 /breach_coms3 /breach_coms2 /breach_coms1
echo "      /breach_coms1-4 created"

# ── Step 5: Wire fstab ────────────────────────────────────────────────────────
echo "[5/6] Wiring /etc/fstab..."
# Remove any old breach_coms entries first
sed -i '/breach.coms/d' /etc/fstab
cat >> /etc/fstab << 'EOF'

# Phoenix breach_coms vault — 4-tier versioning
LABEL=breach-coms4  /breach_coms4  ext4  defaults,nofail  0  2
LABEL=breach-coms3  /breach_coms3  ext4  defaults,nofail  0  2
LABEL=breach-coms2  /breach_coms2  ext4  defaults,nofail  0  2
EOF
echo "      fstab updated"

# ── Step 6: Mount and initialize ─────────────────────────────────────────────
echo "[6/6] Mounting and initializing vault structure..."
mount /breach_coms4
mount /breach_coms3
mount /breach_coms2

# T4 is internal — just a directory, already exists
# breach_coms1 stays on internal sda2

# Vault directory structure on each tier
for TIER in /breach_coms4 /breach_coms3 /breach_coms2 /breach_coms1; do
    mkdir -p "${TIER}/vault" "${TIER}/sidecar" "${TIER}/custody"
    chown -R "${REAL_USER}:${REAL_USER}" "${TIER}"
done

# Clonepool lives on T1 (callable face of the vault)
mkdir -p /breach_coms4/clonepool
chown "${REAL_USER}:${REAL_USER}" /breach_coms4/clonepool

# Symlink clonepool to user home for lol + intake
CLONEPOOL_LINK="${REAL_HOME}/Phoenix/clonepool"
mkdir -p "${REAL_HOME}/Phoenix"
ln -sfn /breach_coms4/clonepool "${CLONEPOOL_LINK}"
chown -h "${REAL_USER}:${REAL_USER}" "${CLONEPOOL_LINK}"
echo "      clonepool → /breach_coms4/clonepool (symlinked from ${CLONEPOOL_LINK})"

echo ""
echo "=== breach_coms vault READY ==="
echo ""
df -h /breach_coms4 /breach_coms3 /breach_coms2 /breach_coms1
echo ""
echo "  T1 PRIMARY:    /breach_coms4  (sdc1 — breach-coms4)"
echo "  T2 SECONDARY:  /breach_coms3  (sdb1 — breach-coms3)"
echo "  T3 TERTIARY:   /breach_coms2  (sdc2 — breach-coms2)"
echo "  T4 TERTIARY:   /breach_coms1  (internal — sda2)"
echo "  Clonepool:     /breach_coms4/clonepool → ~/Phoenix/clonepool"
echo ""
echo "  Next: ssh phoenix-ext, test: lol <file>.lol"
