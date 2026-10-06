#!/usr/bin/env bash
# pbmiii-recover.sh — bring pbmIII back: LAN up, SSH up, Nebula mesh up, SMB shares to Windows up.
# jwl247 / Jerry Leftwich — GPL v3
#
# Run AT III's console (keyboard + screen), from a USB stick or a copy in /root:
#   sudo bash pbmiii-recover.sh              # check + repair, no policy changes
#   sudo bash pbmiii-recover.sh --lan-ssh    # also open SSH from 192.168.1.0/24 until next reboot
#
# Works WITH the hardening (phoenix-harden.sh / phoenix-shares.sh), never around it: it restores
# their known-good copies, it does not loosen sshd or SMB. --lan-ssh is a runtime nft rule only
# (gone at reboot). Touches no drives, no udev, no modprobe. Log: /var/log/phoenix-recover.log
set -uo pipefail

USER_NAME=a
LAN_IP_EXPECTED=192.168.1.192   # hosts.json "lan"
MESH_IP=10.42.0.10
LIGHTHOUSE=10.42.0.2          # awslh
LAN_NET=192.168.1.0/24
PUBKEY='ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAICNIdEFnh+hhXYHcha3HfbSdlo1EpX1wO+xYRGin42SD phoenix-third-debian-machine'
LAN_SSH=false; [[ "${1:-}" == "--lan-ssh" ]] && LAN_SSH=true

[[ $EUID -eq 0 ]] || { echo "run with sudo"; exit 1; }
LOG=/var/log/phoenix-recover.log
exec > >(tee -a "$LOG") 2>&1
echo "=== pbmiii-recover $(date -Is) ==="

declare -A RESULT
ok()   { echo "  [ OK ] $*"; }
bad()  { echo "  [FAIL] $*"; }
info() { echo "  ....  $*"; }

# ---- 1. clock — Nebula certs are refused if the clock is wrong (CMOS reset after power loss) ----
echo "[1] clock"
timedatectl set-ntp true 2>/dev/null || true
yr=$(date +%Y)
if (( yr < 2026 )); then bad "clock says $(date) — Nebula will reject its cert; set it: date -s '2026-10-06 08:00'"; RESULT[clock]=FAIL
else ok "$(date)"; RESULT[clock]=OK; fi

# ---- 2. LAN ----
echo "[2] LAN"
IFACE=$(ip -o link show | awk -F': ' '$2!="lo" && $2!~/^nebula/ && $2!~/^(docker|veth|virbr|br-)/ {print $2}' | cut -d@ -f1 | head -n1)
info "interface: ${IFACE:-none found}"
if [[ -n "$IFACE" ]]; then
  ip link set "$IFACE" up 2>/dev/null
  if ! ip -4 -o addr show "$IFACE" | grep -q inet; then
    info "no IPv4 — asking DHCP"
    if systemctl is-active -q NetworkManager; then nmcli networking on; nmcli device connect "$IFACE" >/dev/null 2>&1
    elif systemctl is-enabled -q systemd-networkd 2>/dev/null; then systemctl restart systemd-networkd
    elif command -v dhclient >/dev/null; then dhclient -1 "$IFACE"
    else ifup "$IFACE" 2>/dev/null; fi
    sleep 5
  fi
fi
LAN_IP=$(ip -4 -o addr show "${IFACE:-lo}" 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | head -n1)
GW=$(ip route show default | awk '{print $3; exit}')
if [[ -n "$LAN_IP" && "$LAN_IP" != 127.* ]]; then
  ok "LAN address $LAN_IP, gateway ${GW:-none}"
  [[ "$LAN_IP" != "$LAN_IP_EXPECTED" ]] && info "NOT $LAN_IP_EXPECTED — tell Claude: hosts.json pbmiii ssh needs a@$LAN_IP"
  RESULT[lan]=OK
else bad "no LAN address — check cable / Starlink router"; RESULT[lan]=FAIL; fi
if ping -c1 -W3 1.1.1.1 >/dev/null 2>&1; then ok "internet reachable"; RESULT[internet]=OK
else bad "no internet (mesh needs it to reach awslh)"; RESULT[internet]=FAIL; fi

# ---- 3. SSH ----
echo "[3] SSH"
if ! command -v sshd >/dev/null; then
  info "openssh-server missing — installing"
  apt-get -y -q install openssh-server >/dev/null || bad "apt install failed (no internet?)"
fi
home=$(getent passwd "$USER_NAME" | cut -d: -f6)
if [[ -n "$home" ]]; then
  install -d -m 700 -o "$USER_NAME" -g "$USER_NAME" "$home/.ssh"
  touch "$home/.ssh/authorized_keys"
  grep -qF "${PUBKEY% *}" "$home/.ssh/authorized_keys" || { echo "$PUBKEY" >> "$home/.ssh/authorized_keys"; info "Windows key re-added"; }
  chown "$USER_NAME:$USER_NAME" "$home/.ssh/authorized_keys"; chmod 600 "$home/.ssh/authorized_keys"
else bad "user $USER_NAME not found"; fi
# hardening's known-good sshd drop-in wins over anything that drifted
[[ -f /etc/phoenix/sshd.known-good ]] && cp /etc/phoenix/sshd.known-good /etc/ssh/sshd_config.d/91-phoenix-harden.conf
if sshd -t; then
  systemctl enable ssh >/dev/null 2>&1; systemctl restart ssh
  systemctl is-active -q ssh && { ok "sshd running"; RESULT[ssh]=OK; } || { bad "sshd won't start: journalctl -u ssh"; RESULT[ssh]=FAIL; }
else bad "sshd config invalid (sshd -t above)"; RESULT[ssh]=FAIL; fi
# firewall: hardening drops LAN ssh unless --ssh-from was given; mesh ssh always passes (nebula1)
if nft list table inet phoenix >/dev/null 2>&1; then
  if nft list chain inet phoenix input | grep -q 'dport 22'; then ok "firewall allows LAN ssh (break-glass rule)"
  elif $LAN_SSH; then
    nft insert rule inet phoenix input ip saddr $LAN_NET tcp dport 22 accept comment '"recover: until reboot"'
    ok "LAN ssh opened from $LAN_NET until reboot"
  else info "LAN ssh blocked by hardening (mesh ssh is fine) — rerun with --lan-ssh if the mesh stays down"; fi
elif [[ -f /etc/phoenix/nftables.known-good ]]; then
  nft -c -f /etc/phoenix/nftables.known-good && nft -f /etc/phoenix/nftables.known-good && info "firewall was missing — restored known-good"
fi

# ---- 4. Nebula mesh ----
echo "[4] mesh"
C=/etc/nebula
if [[ -x /usr/local/bin/nebula && -f $C/config.yml ]]; then
  if ! /usr/local/bin/nebula -test -config $C/config.yml >/dev/null 2>&1 && [[ -f $C/known-good/config.yml ]]; then
    cp $C/known-good/config.yml $C/config.yml; info "config.yml failed its test — restored known-good"
  fi
  systemctl enable nebula >/dev/null 2>&1; systemctl restart nebula
  systemctl enable --now phoenix-mesh-heal.timer >/dev/null 2>&1
  for _ in $(seq 1 15); do ip -4 addr show nebula1 2>/dev/null | grep -q "$MESH_IP" && break; sleep 1; done
  if ip -4 addr show nebula1 2>/dev/null | grep -q "$MESH_IP"; then ok "nebula1 = $MESH_IP"
    if ping -c2 -W3 $LIGHTHOUSE >/dev/null 2>&1; then ok "lighthouse awslh ($LIGHTHOUSE) answers"; RESULT[mesh]=OK
    else bad "nebula up but awslh silent: journalctl -u nebula -n 30"; RESULT[mesh]=FAIL; fi
  else bad "nebula1 never came up: journalctl -u nebula -n 30"; RESULT[mesh]=FAIL
    journalctl -u nebula -n 15 --no-pager; fi
  info "cert expires: $(/usr/local/bin/nebula-cert print -path $C/host.crt 2>/dev/null | grep -i notAfter | head -n1 | xargs)"
else bad "nebula not installed — reinstall from Windows: python sector3\\mesh\\phoenix_net.py install-ssh pbmiii"; RESULT[mesh]=FAIL; fi

# ---- 5. SMB shares to Windows (mesh only, per phoenix-shares.sh) ----
echo "[5] shares"
if command -v smbd >/dev/null; then
  [[ -f /etc/phoenix/smb.known-good ]] && ! cmp -s /etc/samba/smb.conf /etc/phoenix/smb.known-good \
    && cp /etc/phoenix/smb.known-good /etc/samba/smb.conf && info "smb.conf restored known-good"
  systemctl restart smbd; sleep 2   # restart AFTER nebula1 exists: smbd binds the mesh address only
  if ss -ltn | grep -q "$MESH_IP:445"; then ok "SMB listening on $MESH_IP:445"; RESULT[smb]=OK
  else bad "smbd not on the mesh address (mesh down?)"; RESULT[smb]=FAIL; fi
else info "samba not installed — skipped"; RESULT[smb]=SKIP; fi

# ---- summary ----
echo
echo "=== summary ==="
for k in clock lan internet ssh mesh smb; do printf '  %-9s %s\n' "$k" "${RESULT[$k]:-?}"; done
echo
echo "Test from Windows (PBMII, PS7):"
echo "  ssh -i \$env:USERPROFILE\\.ssh\\phoenix_third_debian_ed25519 $USER_NAME@$MESH_IP hostname"
echo "  Test-NetConnection $MESH_IP -Port 445"
echo "Log: $LOG"
