#!/usr/bin/env bash
# phoenix-box-setup.sh — bring a Debian box up to Phoenix standard
# Phoenix DevOps OS | jwl247 | GPL v3
#
#   sudo bash phoenix-box-setup.sh                 # updates, packages, never sleep, Wake-on-LAN, auto security updates
#   sudo bash phoenix-box-setup.sh --admin-key     # ALSO: this user's SSH key may run admin without a password,
#                                                  #       and SSH password logins are switched OFF (keys only)
# Safe to run again. Prints a short report at the end.
set -euo pipefail

[[ $EUID -eq 0 ]] || { echo "run with sudo"; exit 1; }
ADMIN_KEY=false
[[ "${1:-}" == "--admin-key" ]] && ADMIN_KEY=true
USER_NAME="${SUDO_USER:-}"
log() { printf '\n== %s\n' "$*"; }

log "packages: update + upgrade"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get -y -q full-upgrade
apt-get -y -q install python3-cryptography curl git ethtool unattended-upgrades apt-listchanges

log "never sleep"
systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target >/dev/null
mkdir -p /etc/systemd/logind.conf.d
cat > /etc/systemd/logind.conf.d/phoenix-no-sleep.conf <<'EOF'
[Login]
HandleLidSwitch=ignore
HandleLidSwitchExternalPower=ignore
HandleSuspendKey=ignore
HandleHibernateKey=ignore
IdleAction=ignore
EOF
# GNOME's own idle suspend, for every user (dconf system default)
if [[ -d /etc/dconf ]]; then
  mkdir -p /etc/dconf/db/local.d /etc/dconf/profile
  printf 'user-db:user\nsystem-db:local\n' > /etc/dconf/profile/user
  cat > /etc/dconf/db/local.d/00-phoenix-no-sleep <<'EOF'
[org/gnome/settings-daemon/plugins/power]
sleep-inactive-ac-type='nothing'
sleep-inactive-battery-type='nothing'
EOF
  dconf update 2>/dev/null || true
fi

log "Wake-on-LAN (magic packet) on wired ports"
for dev in $(nmcli -t -f DEVICE,TYPE dev status | awk -F: '$2=="ethernet"{print $1}'); do
  con=$(nmcli -t -f GENERAL.CONNECTION dev show "$dev" | cut -d: -f2-)
  [[ -n "$con" && "$con" != "--" ]] && nmcli con mod "$con" 802-3-ethernet.wake-on-lan magic
  ethtool -s "$dev" wol g 2>/dev/null || true
  echo "  $dev: $(ethtool "$dev" 2>/dev/null | awk '/Wake-on:/{w=$2} END{print "wake-on=" w}') mac=$(cat /sys/class/net/$dev/address)"
done

log "automatic security updates"
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
EOF
systemctl enable --now unattended-upgrades >/dev/null 2>&1 || true

if $ADMIN_KEY; then
  log "admin by key only"
  [[ -n "$USER_NAME" && -s "/home/$USER_NAME/.ssh/authorized_keys" ]] \
    || { echo "  refusing: $USER_NAME has no SSH key installed — password logins stay on"; exit 1; }
  echo "$USER_NAME ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/90-phoenix-admin
  chmod 440 /etc/sudoers.d/90-phoenix-admin
  visudo -cf /etc/sudoers.d/90-phoenix-admin >/dev/null
  cat > /etc/ssh/sshd_config.d/90-phoenix-keys-only.conf <<'EOF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
EOF
  sshd -t && systemctl reload ssh
  echo "  $USER_NAME: admin without password (key holders only); SSH passwords OFF"
fi

log "report"
echo "  $(. /etc/os-release; echo "$PRETTY_NAME"), kernel $(uname -r)"
echo "  sleep: $(systemctl is-enabled sleep.target 2>&1)   upgrades left: $(apt list --upgradable 2>/dev/null | tail -n +2 | wc -l)"
echo "  failed units: $(systemctl --failed --no-legend | wc -l)   reboot needed: $([[ -f /var/run/reboot-required ]] && echo yes || echo no)"
echo "done."
