#!/usr/bin/env zsh
# saddle_block.sh — neutralize Windows control files
# Run while Debian is stopped, from Windows side
# \\wsl$\Debian\etc\
# Phoenix DevOps LLC — jwl247

set -e

# Guard: this OVERWRITES /etc/fstab, /etc/hosts, /etc/nsswitch.conf and
# /etc/resolv.conf with WSL-only templates. On a real Debian/Ubuntu install
# (bare metal or the QEMU VM) the fstab rewrite drops the root/EFI mounts and
# leaves the machine unbootable. Phoenix no longer uses WSL — refuse unless
# we're genuinely inside WSL, or the operator forces it knowingly.
if ! grep -qi microsoft /proc/version 2>/dev/null && [[ "${SADDLE_FORCE:-}" != "1" ]]; then
    echo "[saddle] Not running inside WSL — refusing to overwrite /etc/fstab et al." >&2
    echo "[saddle] (set SADDLE_FORCE=1 only if you really mean it)" >&2
    exit 1
fi

echo "[saddle] Blocking Windows control points...\n"

# ─── /etc/wsl.conf ───────────────────────────────────────────────
cat > /etc/wsl.conf << 'WSLCONF'
[boot]
systemd=true

[automount]
enabled=false
mountFsTab=false

[network]
generateResolvConf=false
generateHosts=false

[interop]
enabled=false
appendWindowsPath=false
WSLCONF
echo "[OK] /etc/wsl.conf — Windows hooks removed"

# ─── /etc/resolv.conf ────────────────────────────────────────────
# Remove Windows-managed symlink, write static DNS
rm -f /etc/resolv.conf
cat > /etc/resolv.conf << 'RESOLV'
# Phoenix — static DNS, not Windows managed
nameserver 1.1.1.1
nameserver 9.9.9.9
RESOLV
chattr +i /etc/resolv.conf
echo "[OK] /etc/resolv.conf — immutable, Windows DNS blocked"

# ─── /etc/hosts ──────────────────────────────────────────────────
cat > /etc/hosts << 'HOSTS'
127.0.0.1   localhost
127.0.1.1   phoenix
::1         localhost ip6-localhost ip6-loopback
HOSTS
echo "[OK] /etc/hosts — clean, no Windows injections"

# ─── /etc/fstab ──────────────────────────────────────────────────
cat > /etc/fstab << 'FSTAB'
# Phoenix fstab — no Windows automounts
# Add breach_coms drives by LABEL when ready:
# LABEL=breach_coms1  /mnt/d  ext4  defaults  0  2
# LABEL=breach_coms2  /mnt/e  ext4  defaults  0  2
# LABEL=breach_coms3  /mnt/f  ext4  defaults  0  2
# LABEL=breach_coms4  /mnt/g  ext4  defaults  0  2
FSTAB
echo "[OK] /etc/fstab — Windows automounts removed"

# ─── /etc/nsswitch.conf ──────────────────────────────────────────
cat > /etc/nsswitch.conf << 'NSS'
passwd:         files
group:          files
shadow:         files
hosts:          files dns
networks:       files
protocols:      db files
services:       db files
ethers:         db files
rpc:            db files
NSS
echo "[OK] /etc/nsswitch.conf — Windows resolution chain removed"

echo "\n[saddle] All 5 control points blocked."
echo "[saddle] Restart WSL: wsl --shutdown && wsl"
