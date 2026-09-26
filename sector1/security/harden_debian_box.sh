#!/usr/bin/env bash
# harden_debian_box.sh — baseline hardening for Phoenix's dedicated Debian boxes
# (Compaq/pbm-compaq, pbm3, the Pavilion). Run as root.
#
#   harden_debian_box.sh <admin-user> [--apply-firewall] [--confirm-firewall]
#
# What it does (idempotent, each step checked):
#   1. SSH: key-only (no passwords), no root login, only <admin-user>, no X11.
#      Refuses to run if <admin-user> has no authorized key: no lockouts.
#   2. Firewall (nftables): inbound default DROP; allow loopback, replies,
#      ICMP/ICMPv6 (IPv6 needs it), DHCPv6 client, and SSH only from the LAN
#      (IPv4 private ranges, IPv6 link-local + ULA). Public IPv6 gets nothing.
#      --apply-firewall loads it with a 120 s dead-man switch that flushes it
#      again unless --confirm-firewall is run from a NEW ssh session in time.
#   3. Removes the installer's web-server task (apache2) — nothing listens
#      that we didn't put there.
#   4. Locks the root password (sudo is the way in).
#   5. unattended-upgrades for Debian security updates.
#   6. A few safe sysctls (no ICMP redirects, syncookies, dmesg/kptr restrict).
# Never touches /etc/udev or /etc/modprobe.d (CLAUDE.md AI SAFETY RULES), never
# changes drive state.
set -euo pipefail
U=${1:?usage: harden_debian_box.sh <admin-user> [--apply-firewall|--confirm-firewall]}
MODE=${2:-}
[ "$(id -u)" = 0 ] || { echo "run as root"; exit 1; }
log() { echo "harden: $*"; }

if [ "$MODE" = "--confirm-firewall" ]; then
  systemctl stop phoenix-fw-deadman.timer phoenix-fw-deadman.service 2>/dev/null || true
  systemctl enable nftables >/dev/null 2>&1
  log "firewall confirmed: dead-man switch cancelled, nftables enabled at boot"
  exit 0
fi

HOME_U=$(getent passwd "$U" | cut -d: -f6)
[ -s "$HOME_U/.ssh/authorized_keys" ] || { echo "no authorized_keys for $U: refusing (would lock you out)"; exit 1; }

# 1. SSH
cat > /etc/ssh/sshd_config.d/10-phoenix-hardening.conf <<EOF
# Phoenix hardening (sector1/security/harden_debian_box.sh)
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
AllowUsers $U
X11Forwarding no
MaxAuthTries 3
LoginGraceTime 30
EOF
sshd -t && systemctl reload ssh && log "ssh: key-only, root off, AllowUsers $U"

# 3. web server the installer added
if dpkg -l apache2 2>/dev/null | grep -q '^ii'; then
  DEBIAN_FRONTEND=noninteractive apt-get purge -y -qq apache2 apache2-bin apache2-data apache2-doc apache2-utils task-web-server >/dev/null
  DEBIAN_FRONTEND=noninteractive apt-get autoremove -y -qq >/dev/null
  log "apache2 removed"
fi

# 4. root password
passwd -S root | grep -q ' L ' || { passwd -l root >/dev/null && log "root password locked"; }

# 5. security updates
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq unattended-upgrades nftables >/dev/null
echo 'APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";' > /etc/apt/apt.conf.d/20auto-upgrades
log "unattended security upgrades on"

# 6. sysctls
cat > /etc/sysctl.d/90-phoenix-hardening.conf <<'EOF'
net.ipv4.conf.all.accept_redirects = 0
net.ipv4.conf.default.accept_redirects = 0
net.ipv6.conf.all.accept_redirects = 0
net.ipv6.conf.default.accept_redirects = 0
net.ipv4.conf.all.send_redirects = 0
net.ipv4.tcp_syncookies = 1
net.ipv4.conf.all.rp_filter = 1
kernel.dmesg_restrict = 1
kernel.kptr_restrict = 1
EOF
sysctl -q --system && log "sysctls applied"

# 2. firewall
cat > /etc/nftables.conf <<'EOF'
#!/usr/sbin/nft -f
# Phoenix firewall (sector1/security/harden_debian_box.sh)
flush ruleset
table inet phoenix {
  set lan4 { type ipv4_addr; flags interval; elements = { 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16 } }
  set lan6 { type ipv6_addr; flags interval; elements = { fe80::/10, fc00::/7 } }
  chain input {
    type filter hook input priority 0; policy drop;
    iif lo accept
    ct state established,related accept
    ct state invalid drop
    ip protocol icmp accept
    ip6 nexthdr icmpv6 accept
    udp dport 546 accept                      # DHCPv6 client
    udp dport 68 accept                       # DHCPv4 client
    tcp dport 22 ip saddr @lan4 accept
    tcp dport 22 ip6 saddr @lan6 accept
  }
  chain forward { type filter hook forward priority 0; policy drop; }
  chain output  { type filter hook output priority 0; policy accept; }
}
EOF
nft -c -f /etc/nftables.conf && log "firewall rules valid"

if [ "$MODE" = "--apply-firewall" ]; then
  systemd-run --unit=phoenix-fw-deadman --on-active=120 /usr/sbin/nft flush ruleset >/dev/null
  nft -f /etc/nftables.conf
  log "firewall LOADED. Dead-man flush in 120 s unless: $0 $U --confirm-firewall (from a new ssh session)"
fi
