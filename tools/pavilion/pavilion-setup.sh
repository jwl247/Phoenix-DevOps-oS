#!/usr/bin/env bash
# =============================================================================
# pavilion-setup.sh — Phoenix: line out the Pavilion (Debian 13 "trixie")
# jwl247 / Jerry Leftwich — GPL v3
#
# Run ON THE PAVILION, from a local terminal:
#   sudo bash pavilion-setup.sh              # verify install + SSH up (password auth still ON)
#   sudo bash pavilion-setup.sh --harden     # after your Windows key works: key-only SSH
#
# Options:
#   --user NAME      account that will log in over SSH (default: $SUDO_USER)
#   --harden         turn off password auth (refuses unless NAME already has a key)
#   --no-firewall    skip the ufw LAN-only rule for port 22
#   --no-upgrade     skip apt full-upgrade
#
# What it does, in order (stops loud on the first real failure):
#   1. Confirms this really is Debian 13, run as root
#   2. Network + DNS check (the 2026-09-23 "Temporary failure resolving" issue)
#   3. Repairs apt sources left behind by the live installer (cdrom: lines / empty)
#   4. Repairs any half-configured packages, updates, upgrades
#   5. Health report: disk, time sync, missing firmware, failed units
#   6. Installs + enables openssh-server with a hardened drop-in, validated by `sshd -t`
#   7. LAN-only firewall rule for SSH (ufw)
#   8. Makes this box's own key for SSH-ing OUT to the Windows machines
#   9. Prints IP, hostname, and host-key fingerprints to check on first connect
#
# Deliberately never touches /etc/udev/rules.d, /etc/modprobe.d, or any drive state
# (CLAUDE.md AI Safety Rules).
# =============================================================================
set -euo pipefail

TARGET_USER="${SUDO_USER:-}"
HARDEN=0
FIREWALL=1
UPGRADE=1
DROPIN=/etc/ssh/sshd_config.d/10-phoenix.conf

while [[ $# -gt 0 ]]; do
    case "$1" in
        --user)        TARGET_USER="${2:?--user needs a name}"; shift 2 ;;
        --harden)      HARDEN=1; shift ;;
        --no-firewall) FIREWALL=0; shift ;;
        --no-upgrade)  UPGRADE=0; shift ;;
        -h|--help)     sed -n '2,32p' "$0"; exit 0 ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
    esac
done

c_ok()   { printf '\e[32m[ OK ]\e[0m %s\n' "$*"; }
c_warn() { printf '\e[33m[WARN]\e[0m %s\n' "$*"; }
c_fail() { printf '\e[31m[FAIL]\e[0m %s\n' "$*" >&2; exit 1; }
step()   { printf '\n\e[36m== %s ==\e[0m\n' "$*"; }

# --- 1. preflight -----------------------------------------------------------
step "1. Preflight"
[[ $EUID -eq 0 ]] || c_fail "run with sudo:  sudo bash $0"
# shellcheck disable=SC1091
. /etc/os-release
[[ "${ID:-}" == "debian" ]] || c_fail "this is ${PRETTY_NAME:-unknown}, not Debian — wrong machine?"
[[ "${VERSION_ID:-}" == "13" ]] || c_warn "expected Debian 13 (trixie), found ${PRETTY_NAME}"
c_ok "$PRETTY_NAME, kernel $(uname -r)"

[[ -n "$TARGET_USER" && "$TARGET_USER" != "root" ]] \
    || c_fail "can't tell which user logs in over SSH — pass --user <name>"
id "$TARGET_USER" >/dev/null 2>&1 || c_fail "user '$TARGET_USER' does not exist"
TARGET_HOME=$(getent passwd "$TARGET_USER" | cut -d: -f6)
if id -nG "$TARGET_USER" | tr ' ' '\n' | grep -qx sudo; then
    c_ok "user $TARGET_USER is in the sudo group"
else
    c_warn "user $TARGET_USER is NOT in sudo group — adding (root login over SSH stays disabled)"
    usermod -aG sudo "$TARGET_USER"
fi

# --- 2. network + DNS -------------------------------------------------------
step "2. Network + DNS"
ip -br addr | grep -v '^lo ' || true
DEFAULT_IF=$(ip route show default 2>/dev/null | awk '/default/ {print $5; exit}')
if [[ -z "$DEFAULT_IF" ]]; then
    c_warn "no default route — the link is down or has no DHCP lease"
    if command -v nmcli >/dev/null; then
        nmcli -t -f DEVICE,TYPE,STATE device | while IFS=: read -r dev type state; do
            if [[ "$type" == "ethernet" && "$state" != "connected" ]]; then
                echo "  trying: nmcli device connect $dev"
                nmcli device connect "$dev" || true
            fi
        done
        sleep 5
        DEFAULT_IF=$(ip route show default 2>/dev/null | awk '/default/ {print $5; exit}')
    fi
    [[ -n "$DEFAULT_IF" ]] || c_fail "still no network. Check the cable/link light (cable was moved from the Compaq), then re-run."
fi
c_ok "default route via $DEFAULT_IF ($(ip route show default | awk '{print $3; exit}'))"

if getent hosts deb.debian.org >/dev/null; then
    c_ok "DNS resolves deb.debian.org"
else
    c_warn "DNS lookup failed; resolver config:"
    grep -v '^#' /etc/resolv.conf || true
    if ping -c1 -W3 1.1.1.1 >/dev/null 2>&1; then
        c_fail "internet reachable by IP but DNS is broken. Quick fix:  sudo nmcli connection modify \"\$(nmcli -g NAME connection show --active | head -1)\" ipv4.dns '1.1.1.1 9.9.9.9' && sudo nmcli connection up \"\$(nmcli -g NAME connection show --active | head -1)\"  — then re-run."
    else
        c_fail "no internet at all (can't ping 1.1.1.1). Only one box can be online right now — make sure the connection is on the Pavilion."
    fi
fi

# --- 3. apt sources ---------------------------------------------------------
step "3. APT sources"
SRC=/etc/apt/sources.list
DEB822=/etc/apt/sources.list.d/debian.sources
if [[ -f "$SRC" ]] && grep -Eq '^[[:space:]]*deb[[:space:]]+cdrom:' "$SRC"; then
    cp -a "$SRC" "$SRC.phoenix-bak.$(date +%Y%m%d%H%M%S)"
    sed -i -E 's|^([[:space:]]*deb[[:space:]]+cdrom:)|# disabled by pavilion-setup: \1|' "$SRC"
    c_warn "disabled live-installer cdrom: source (backup kept next to $SRC)"
fi
has_network_source() {
    grep -Ehs '^[[:space:]]*(deb|URIs:)[[:space:]]' "$SRC" /etc/apt/sources.list.d/*.list /etc/apt/sources.list.d/*.sources 2>/dev/null \
        | grep -q 'http'
}
if ! has_network_source; then
    cat > "$DEB822" <<'EOF'
Types: deb
URIs: http://deb.debian.org/debian
Suites: trixie trixie-updates
Components: main contrib non-free non-free-firmware
Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg

Types: deb
URIs: http://security.debian.org/debian-security
Suites: trixie-security
Components: main contrib non-free non-free-firmware
Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg
EOF
    c_warn "no network apt source existed — wrote $DEB822 (trixie + updates + security)"
else
    c_ok "network apt source present"
fi
grep -Ehqs 'security' "$SRC" /etc/apt/sources.list.d/* \
    && c_ok "security updates source present" \
    || c_warn "no trixie-security source found — security patches won't arrive"

# --- 4. package health + update --------------------------------------------
step "4. Package health + updates"
export DEBIAN_FRONTEND=noninteractive
AUDIT=$(dpkg --audit || true)
if [[ -n "$AUDIT" ]]; then
    c_warn "dpkg reports half-configured packages — repairing"
    dpkg --configure -a
    apt-get -y -f install
fi
apt-get update
if [[ $UPGRADE -eq 1 ]]; then
    apt-get -y -o Dpkg::Options::=--force-confold full-upgrade
fi
[[ -z "$(dpkg --audit || true)" ]] && c_ok "dpkg database clean" || c_fail "dpkg still reports problems: dpkg --audit"

# --- 5. health report -------------------------------------------------------
step "5. Install health"
df -h / | tail -1 | awk '{printf "  root fs: %s used of %s (%s)\n", $3, $2, $5}'
ROOT_PCT=$(df --output=pcent / | tail -1 | tr -dc '0-9')
(( ROOT_PCT < 90 )) && c_ok "root filesystem has room" || c_warn "root filesystem ${ROOT_PCT}% full"
free -h | awk '/Mem:/ {print "  RAM: "$2" total, "$7" available"}'

if timedatectl show -p NTPSynchronized --value 2>/dev/null | grep -qx yes; then
    c_ok "clock is NTP-synchronized"
else
    c_warn "clock not NTP-synced — enabling systemd-timesyncd"
    apt-get -y install systemd-timesyncd >/dev/null
    timedatectl set-ntp true || true
fi

FW_MISSING=$(journalctl -k -b --no-pager 2>/dev/null | grep -iE 'firmware: failed to load|failed to load firmware' | sort -u || true)
if [[ -n "$FW_MISSING" ]]; then
    c_warn "kernel reported missing firmware this boot:"
    echo "$FW_MISSING" | sed 's/^/    /'
    echo "  → firmware-linux-nonfree / firmware-realtek / firmware-misc-nonfree usually cover it (non-free-firmware is enabled above)."
else
    c_ok "no missing-firmware errors this boot"
fi

FAILED=$(systemctl --failed --no-legend --plain 2>/dev/null | awk '{print $1}' || true)
[[ -z "$FAILED" ]] && c_ok "no failed systemd units" || { c_warn "failed units:"; echo "$FAILED" | sed 's/^/    /'; }

if command -v mokutil >/dev/null; then
    echo "  secure boot: $(mokutil --sb-state 2>/dev/null | head -1)"
fi

# --- 6. OpenSSH server ------------------------------------------------------
step "6. OpenSSH server"
apt-get -y install openssh-server >/dev/null
AUTH_KEYS="$TARGET_HOME/.ssh/authorized_keys"
PASSWORD_AUTH=yes
if [[ $HARDEN -eq 1 ]]; then
    if [[ -s "$AUTH_KEYS" ]] && grep -Eq '^(ssh-ed25519|ecdsa-|ssh-rsa|sk-)' "$AUTH_KEYS"; then
        PASSWORD_AUTH=no
    else
        c_fail "--harden refused: $AUTH_KEYS has no key. Run connect-from-windows.ps1 on Windows first, or you'd lock yourself out."
    fi
fi

cat > "$DROPIN.new" <<EOF
# Managed by tools/pavilion/pavilion-setup.sh — Phoenix
PermitRootLogin no
PubkeyAuthentication yes
PasswordAuthentication $PASSWORD_AUTH
KbdInteractiveAuthentication no
PermitEmptyPasswords no
MaxAuthTries 4
LoginGraceTime 30
X11Forwarding no
AllowUsers $TARGET_USER
ClientAliveInterval 60
ClientAliveCountMax 3
EOF
# Validate the whole config with the new drop-in before it goes live.
install -d -m 755 /run/sshd   # sshd -t needs this even before first start
mv "$DROPIN.new" "$DROPIN"
if ! sshd -t; then
    rm -f "$DROPIN"
    c_fail "sshd rejected the config — drop-in removed, sshd untouched"
fi
systemctl enable ssh >/dev/null 2>&1
systemctl restart ssh
systemctl is-active --quiet ssh && c_ok "ssh is running and enabled at boot" || c_fail "ssh failed to start: journalctl -u ssh"
ss -ltn | grep -q ':22 ' && c_ok "listening on port 22" || c_fail "ssh not listening on 22"
c_ok "password auth: $PASSWORD_AUTH | root login: no | allowed user: $TARGET_USER"

install -d -m 700 -o "$TARGET_USER" -g "$TARGET_USER" "$TARGET_HOME/.ssh"
touch "$AUTH_KEYS"; chown "$TARGET_USER:$TARGET_USER" "$AUTH_KEYS"; chmod 600 "$AUTH_KEYS"

# --- 7. firewall ------------------------------------------------------------
step "7. Firewall"
if [[ $FIREWALL -eq 1 ]]; then
    LAN=$(ip -4 route show dev "$DEFAULT_IF" scope link 2>/dev/null | awk '{print $1; exit}')
    apt-get -y install ufw >/dev/null
    if [[ -n "$LAN" ]]; then
        ufw allow from "$LAN" to any port 22 proto tcp comment 'Phoenix SSH, LAN only' >/dev/null
        c_ok "ufw: SSH allowed from $LAN only"
    else
        ufw allow 22/tcp comment 'Phoenix SSH' >/dev/null
        c_warn "couldn't detect LAN subnet — SSH allowed from anywhere"
    fi
    ufw default deny incoming >/dev/null
    ufw default allow outgoing >/dev/null
    ufw --force enable >/dev/null
    c_ok "ufw enabled (deny incoming, allow outgoing)"
else
    c_warn "firewall skipped (--no-firewall)"
fi

# --- 8. outbound key to Windows --------------------------------------------
step "8. Key for SSH from here to Windows"
OUT_KEY="$TARGET_HOME/.ssh/phoenix_pavilion_to_windows_ed25519"
if [[ ! -f "$OUT_KEY" ]]; then
    sudo -u "$TARGET_USER" ssh-keygen -q -t ed25519 -N '' -C "$TARGET_USER@$(hostname)-to-windows" -f "$OUT_KEY"
    c_ok "created $OUT_KEY"
else
    c_ok "key already exists: $OUT_KEY"
fi

# --- 9. summary -------------------------------------------------------------
step "9. Connect details"
IP=$(ip -4 -br addr show "$DEFAULT_IF" | awk '{print $3}' | cut -d/ -f1)
echo "  hostname : $(hostname)   (also $(hostname).local if avahi-daemon is running: $(systemctl is-active avahi-daemon 2>/dev/null || echo no))"
echo "  IP       : $IP"
echo "  user     : $TARGET_USER"
echo "  host-key fingerprints (Windows should show one of these on first connect):"
for k in /etc/ssh/ssh_host_*_key.pub; do ssh-keygen -lf "$k" | sed 's/^/    /'; done
echo
echo "  This box's public key (for SSH INTO Windows — connect-from-windows.ps1 -AllowReverse copies it for you):"
sed 's/^/    /' "$OUT_KEY.pub"
echo
if [[ $HARDEN -eq 0 ]]; then
    echo "NEXT: on Windows run"
    echo "  pwsh -File tools\\pavilion\\connect-from-windows.ps1 -HostName $IP -User $TARGET_USER"
    echo "then back here:  sudo bash $0 --harden"
else
    c_ok "hardened: key-only SSH"
fi
