#!/usr/bin/env bash
# node-up.sh — first boot of a fresh Debian box, run from the Phoenix USB stick
# Phoenix DevOps OS | jwl247 | GPL v3
#
#   sudo bash /media/$USER/PHOENIXUSB/node-up.sh [hostname]      # default hostname: pbmiii
#
# Run from YOUR login with sudo (not a root shell): the SSH key goes to that user.
# What it does, in order (safe to run again):
#   1. hostname
#   2. SSH server + PBMII's key (authorized_keys on the stick — public keys only, no secrets)
#   3. phoenix-box-setup.sh --admin-key: updates, never sleep, Wake-on-LAN, auto security
#      updates, admin by key without a password, SSH passwords off
#   4. PowerShell 7 from the clone pool (.deb on the stick)
#   5. Phoenix tree -> /opt/phoenix
#   6. Helix + paging manager PLACED: built, units installed, NOT enabled or loaded
#   7. node exporter (Prometheus) — the firewall keeps it to the mesh once hardened
# Secrets (mesh cert, samba password) never ride the stick: PBMII pushes them over SSH
# afterwards with scripts/pbmiii-up.ps1. No drive is formatted, no udev/modprobe touched.
set -euo pipefail
HERE=$(dirname "$(readlink -f "$0")")
HOST=${1:-pbmiii}
[[ $EUID -eq 0 ]] || { echo "run with sudo"; exit 1; }
U=${SUDO_USER:-}
[[ -n "$U" && "$U" != root ]] || { echo "run as: sudo bash $0  (from your own login, not a root shell)"; exit 1; }
UH=$(getent passwd "$U" | cut -d: -f6)
LOG=/var/log/phoenix-node-up.log
exec > >(tee -a "$LOG") 2>&1
log() { printf '\n== %s\n' "$*"; }
export DEBIAN_FRONTEND=noninteractive
echo "=== node-up $(date -Is) host=$HOST user=$U ==="

log "1. hostname -> $HOST"
hostnamectl set-hostname "$HOST"
grep -q "127.0.1.1" /etc/hosts && sed -i "s/^127\.0\.1\.1.*/127.0.1.1\t$HOST/" /etc/hosts || echo -e "127.0.1.1\t$HOST" >> /etc/hosts

log "2. SSH + PBMII key for $U"
apt-get update -q
apt-get -y -q install openssh-server
install -d -m 700 -o "$U" -g "$U" "$UH/.ssh"
touch "$UH/.ssh/authorized_keys"
while read -r k; do
  [[ -z "$k" || "$k" == \#* ]] && continue
  grep -qF "$(awk '{print $2}' <<<"$k")" "$UH/.ssh/authorized_keys" || { echo "$k" >> "$UH/.ssh/authorized_keys"; echo "  added: ${k##* }"; }
done < "$HERE/authorized_keys"
chown "$U:$U" "$UH/.ssh/authorized_keys"; chmod 600 "$UH/.ssh/authorized_keys"
systemctl enable --now ssh >/dev/null 2>&1

log "3. box setup (phoenix-box-setup.sh --admin-key)"
SUDO_USER="$U" bash "$HERE/phoenix/scripts/phoenix-box-setup.sh" --admin-key

log "4. PowerShell 7 (clone pool .deb)"
deb=$(ls "$HERE"/pkgs/powershell*.deb 2>/dev/null | head -n1)
if [[ -n "$deb" ]]; then
  cp "$deb" /tmp/ && apt-get -y -q install "/tmp/$(basename "$deb")" && rm -f "/tmp/$(basename "$deb")"
  echo "  $(pwsh -NoLogo -NoProfile -c '$PSVersionTable.PSVersion.ToString()' 2>/dev/null || echo 'pwsh FAILED')"
else echo "  no powershell .deb on the stick — skipped"; fi

log "5. Phoenix tree -> /opt/phoenix"
install -d -m 755 /opt/phoenix
cp -a "$HERE/phoenix/." /opt/phoenix/
chown -R root:root /opt/phoenix
find /opt/phoenix -name '*.sh' -exec chmod 755 {} +
echo "  $(find /opt/phoenix -type f | wc -l) files"

log "6. Helix + paging manager PLACED (not enabled, not loaded)"
apt-get -y -q install build-essential linux-headers-amd64 fio python3
KVER=$(ls /lib/modules | sort -V | tail -n1)     # newest kernel: what boots after the upgrade in step 3
K=/opt/phoenix/sector1/kernels
if make -C $K KVER="$KVER" >/tmp/helix-build.log 2>&1 && make -C $K KVER="$KVER" helix_test >>/tmp/helix-build.log 2>&1; then
  echo "  helix.ko + Frank3 slots built for $KVER ($(grep -ciE 'warning|error' /tmp/helix-build.log) warning/error lines)"
else echo "  Helix build FAILED for $KVER — see /tmp/helix-build.log (rerun after reboot: make -C $K)"; fi
( cd $K/libhelix && cc -O2 -Wall -Wextra -fPIC -shared -o libhelix.so libhelix.c ) && echo "  libhelix.so built"
mkdir -p /var/lib/helix /var/lib/phoenix-swap && chmod 700 /var/lib/helix /var/lib/phoenix-swap
[[ -f /etc/default/helix ]] || cat > /etc/default/helix <<'EOF'
# Helix boot settings (read by /opt/phoenix/sector1/kernels/helix_boot.sh)
# Helix needs her own origin partition, partlabel helix-origin. Jerry picks the disk.
HELIX_ORIGIN=/dev/disk/by-partlabel/helix-origin
HELIX_RAM=auto
HELIX_B_IMG=/var/lib/helix/strandB.img
HELIX_B_MB=65536
HELIX_MOUNT=/srv/helix
EOF
ram=$(awk '/MemTotal/{printf "%d", $2/1048576}' /proc/meminfo)
free=$(df -BG --output=avail /var/lib | tail -n1 | tr -dc 0-9)
[[ -f /etc/default/phoenix-paging ]] || cat > /etc/default/phoenix-paging <<EOF
# sized to this box by node-up.sh (unit defaults are for a 15 GB / big-SSD machine)
PHOENIX_PAGING_TOTAL_RAM_GB=$ram
PHOENIX_PAGING_MAX_SWAP_GB=$(( free / 4 > 4 ? free / 4 : 4 ))
EOF
install -m 644 /opt/phoenix/sector3/services/helix.service /opt/phoenix/sector3/services/phoenix-paging.service /etc/systemd/system/
systemctl daemon-reload
echo "  units installed, disabled. Turn on later: sudo systemctl enable --now phoenix-paging"
echo "  (Helix: give her a partition labelled helix-origin first, then: sudo systemctl enable --now helix)"

log "7. node exporter"
apt-get -y -q install prometheus-node-exporter >/dev/null && echo "  node exporter on :9100"

log "report"
ip4=$(ip -4 -o route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src") print $(i+1)}')
echo "  host $HOST   user $U   LAN $ip4"
echo "  reboot needed: $([[ -f /var/run/reboot-required ]] && echo yes || echo no)"
echo
echo "  NEXT, on PBMII in PS7:"
echo "    cd F:\\Phoenix\\Phoenix-DevOps-oS"
echo "    pwsh scripts\\pbmiii-up.ps1 -Ip $ip4"
echo "  log: $LOG"
