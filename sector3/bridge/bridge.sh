#!/usr/bin/env bash
# =============================================================================
# bridge.sh — Phoenix DevOps SSH bridge
# Sector 3 / comms layer
# Connects WSL → Windows host → Phoenix external drive
#
# Usage:
#   bridge.sh status          check all machines
#   bridge.sh windows         drop into Windows PowerShell
#   bridge.sh ext             drop into Phoenix external machine
#   bridge.sh run-win <cmd>   run command on Windows, return output
#   bridge.sh run-ext <cmd>   run command on external machine, return output
#   bridge.sh install-key     print pubkey install instructions
#   bridge.sh set-ext <ip>    update phoenix-ext IP in SSH config
# =============================================================================

set -uo pipefail

PUBKEY="${HOME}/.ssh/id_ed25519.pub"
SSH_CONF="${HOME}/.ssh/config"
TIMEOUT=5

# ── Colors ────────────────────────────────────────────────────────────────────
G='\033[0;32m'; R='\033[0;31m'; Y='\033[0;33m'; B='\033[0;34m'; N='\033[0m'

ok()   { echo -e "${G}[OK]${N}  $*"; }
fail() { echo -e "${R}[!!]${N}  $*"; }
warn() { echo -e "${Y}[--]${N}  $*"; }
info() { echo -e "${B}[>>]${N}  $*"; }

# ── Reachability check ────────────────────────────────────────────────────────
_ping() {
    ssh -o ConnectTimeout="${TIMEOUT}" \
        -o BatchMode=yes \
        -o StrictHostKeyChecking=no \
        "$1" "echo pong" 2>/dev/null
}

cmd_status() {
    echo ""
    echo "  ╔══════════════════════════════════════════╗"
    echo "  ║      Phoenix DevOps — Bridge Status      ║"
    echo "  ╚══════════════════════════════════════════╝"
    echo ""

    # WSL (this machine — always reachable)
    ok  "WSL (this machine)   $(hostname) — $(whoami)"

    # Windows host
    if result=$(_ping windows-host 2>/dev/null) && [[ "${result}" == "pong" ]]; then
        ok  "windows-host         172.28.160.1 — SSH OK"
    else
        fail "windows-host         172.28.160.1 — unreachable (OpenSSH Server running?)"
    fi

    # Phoenix external
    if result=$(_ping phoenix-ext 2>/dev/null) && [[ "${result}" == "pong" ]]; then
        ok  "phoenix-ext          booted — SSH OK"
        # Check Phoenix services
        svc=$(ssh -o ConnectTimeout="${TIMEOUT}" -o BatchMode=yes phoenix-ext \
            "systemctl is-active phoenix-sector1.target 2>/dev/null || echo inactive")
        [[ "${svc}" == "active" ]] \
            && ok  "  phoenix-sector1.target  active" \
            || warn "  phoenix-sector1.target  ${svc}"
    else
        warn "phoenix-ext          not reachable (drive booted and on network?)"
    fi

    echo ""
}

# ── Windows shell ─────────────────────────────────────────────────────────────
cmd_windows() {
    info "Connecting to Windows host..."
    ssh windows-host
}

# ── External shell ────────────────────────────────────────────────────────────
cmd_ext() {
    info "Connecting to Phoenix external drive..."
    ssh phoenix-ext
}

# ── Remote command runners ────────────────────────────────────────────────────
cmd_run_win() {
    local cmd="${1:-echo hello}"
    ssh -o ConnectTimeout="${TIMEOUT}" -o BatchMode=yes windows-host \
        "powershell -NonInteractive -Command '${cmd}'"
}

cmd_run_ext() {
    local cmd="${1:-echo hello}"
    ssh -o ConnectTimeout="${TIMEOUT}" -o BatchMode=yes phoenix-ext \
        "${cmd}"
}

# ── Key install instructions ──────────────────────────────────────────────────
cmd_install_key() {
    local pubkey
    pubkey=$(cat "${PUBKEY}" 2>/dev/null || echo "key not found — run: ssh-keygen -t ed25519")

    echo ""
    echo "  Public key (paste this into authorized_keys on each machine):"
    echo ""
    echo "  ${pubkey}"
    echo ""
    echo "  ── Windows (run in PowerShell as admin) ──────────────────────"
    echo '  Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0'
    echo '  Start-Service sshd'
    echo '  Set-Service -Name sshd -StartupType Automatic'
    echo "  \$key = '${pubkey}'"
    echo '  $authFile = "$env:ProgramData\ssh\administrators_authorized_keys"'
    echo '  Add-Content -Path $authFile -Value $key'
    echo '  icacls $authFile /inheritance:r /grant "Administrators:F" /grant "SYSTEM:F"'
    echo ""
    echo "  ── Phoenix external (run after first boot + ssh access) ──────"
    echo "  mkdir -p ~/.ssh && chmod 700 ~/.ssh"
    echo "  echo '${pubkey}' >> ~/.ssh/authorized_keys"
    echo "  chmod 600 ~/.ssh/authorized_keys"
    echo ""
    echo "  ── Then test ─────────────────────────────────────────────────"
    echo "  bridge.sh status"
    echo ""
}

# ── Update external IP ────────────────────────────────────────────────────────
cmd_set_ext() {
    local ip="${1:-}"
    [[ -z "${ip}" ]] && { echo "Usage: bridge.sh set-ext <ip>"; exit 1; }
    sed -i "s/HostName phoenix-ext/HostName ${ip}/" "${SSH_CONF}"
    sed -i "s/HostName phx/HostName ${ip}/" "${SSH_CONF}"
    # Update both phoenix-ext and phx blocks
    python3 - "${SSH_CONF}" "${ip}" <<'PYEOF'
import sys, re
path, ip = sys.argv[1], sys.argv[2]
with open(path) as f:
    content = f.read()

# Replace HostName under phoenix-ext and phx blocks only
lines = content.split('\n')
out, in_target = [], False
for line in lines:
    if line.startswith('Host ') and ('phoenix-ext' in line or line.strip() == 'Host phx'):
        in_target = True
    elif line.startswith('Host ') and 'phoenix-ext' not in line and line.strip() != 'Host phx':
        in_target = False
    if in_target and line.strip().startswith('HostName'):
        line = '    HostName ' + ip
    out.append(line)
with open(path, 'w') as f:
    f.write('\n'.join(out))
PYEOF
    ok "phoenix-ext and phx HostName updated to ${ip}"
    info "Run: bridge.sh status"
}

# ── Help ─────────────────────────────────────────────────────────────────────
cmd_help() {
    cat <<EOF

  bridge.sh — Phoenix DevOps SSH bridge

  Commands:
    status              ping all machines, show Phoenix service state
    windows             interactive shell on Windows host
    ext                 interactive shell on Phoenix external drive
    run-win  <cmd>      run PowerShell command on Windows, print output
    run-ext  <cmd>      run bash command on external drive, print output
    install-key         print pubkey + install instructions for each machine
    set-ext  <ip>       update phoenix-ext IP in ~/.ssh/config

  Machines:
    WSL (here)          $(hostname) — always reachable
    windows-host        172.28.160.1 — OpenSSH Server required
    phoenix-ext         external Ubuntu Server — set IP with set-ext

  Pubkey fingerprint:
    $(ssh-keygen -lf "${PUBKEY}" 2>/dev/null || echo "  key not generated yet")

EOF
}

# ── Entry ─────────────────────────────────────────────────────────────────────
case "${1:-status}" in
    status)      cmd_status ;;
    windows|win) cmd_windows ;;
    ext|phx)     cmd_ext ;;
    run-win)     shift; cmd_run_win "$*" ;;
    run-ext)     shift; cmd_run_ext "$*" ;;
    install-key) cmd_install_key ;;
    set-ext)     shift; cmd_set_ext "${1:-}" ;;
    help|--help) cmd_help ;;
    *)           echo "Unknown: $1 — run: bridge.sh help"; exit 1 ;;
esac
