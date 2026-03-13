#!/usr/bin/env bash
# ============================================================
#  Phoenix-DevOps-oS — bootstrap_node.sh
#  Run once on any new Debian/WSL2 node.
#  Sets up usys, aliases, SSH keys, and local peer trust.
#
#  Usage:
#    ./bootstrap_node.sh [node_name] [peer_ip]
#
#  Example:
#    ./bootstrap_node.sh allin1 192.168.1.50
#
#  What it does:
#    1. Installs deps (sqlite3, qrencode, python3, openssh)
#    2. Installs usys + intake
#    3. Sources phoenix aliases in .bashrc
#    4. Generates SSH keypair (no passphrase)
#    5. Optionally pushes key to peer (passwordless from here on)
#    6. Drops peer into ~/.ssh/config for easy connect
#
#  No internet required after initial apt install.
#  All coms stay local.
#  GPL v3
# ============================================================

set -euo pipefail

NODE_NAME="${1:-phoenix-node}"
PEER_IP="${2:-}"
PHOENIX_DIR="${PHOENIX_DIR:-$HOME/phoenix}"
REPO_URL="${REPO_URL:-}"   # set if pulling from git

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info() { echo -e "${CYAN}[bootstrap]${RESET} $*"; }
ok()   { echo -e "${GREEN}[bootstrap]${RESET} $*"; }
warn() { echo -e "${YELLOW}[bootstrap]${RESET} $*"; }
die()  { echo -e "${RED}[bootstrap]${RESET} $*" >&2; exit 1; }

echo -e "${BOLD}"
echo "  ██████╗ ██╗  ██╗ ██████╗ ███████╗███╗   ██╗██╗██╗  ██╗"
echo "  ██╔══██╗██║  ██║██╔═══██╗██╔════╝████╗  ██║██║╚██╗██╔╝"
echo "  ██████╔╝███████║██║   ██║█████╗  ██╔██╗ ██║██║ ╚███╔╝ "
echo "  ██╔═══╝ ██╔══██║██║   ██║██╔══╝  ██║╚██╗██║██║ ██╔██╗ "
echo "  ██║     ██║  ██║╚██████╔╝███████╗██║ ╚████║██║██╔╝ ██╗"
echo "  ╚═╝     ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝╚═╝╚═╝  ╚═╝"
echo -e "${RESET}"
echo -e "  Phoenix-DevOps-oS  —  Node Bootstrap"
echo -e "  Node: ${BOLD}$NODE_NAME${RESET}"
[[ -n "$PEER_IP" ]] && echo -e "  Peer: ${BOLD}$PEER_IP${RESET}"
echo

# ── 1. Deps ───────────────────────────────────────────────────
info "Installing dependencies..."
sudo apt-get update -qq
sudo apt-get install -y -qq \
    sqlite3 \
    qrencode \
    python3 \
    python3-pip \
    openssh-client \
    openssh-server \
    xxd \
    imagemagick \
    git \
    curl \
    rsync \
    tmux \
    barrier
ok "Dependencies installed"

# ── 2. SSH server ─────────────────────────────────────────────
info "Configuring SSH server..."
sudo systemctl enable ssh 2>/dev/null || sudo service ssh enable 2>/dev/null || true
sudo systemctl start  ssh 2>/dev/null || sudo service ssh start  2>/dev/null || true

# Lock down to local only — no password auth
sudo tee /etc/ssh/sshd_config.d/phoenix_local.conf > /dev/null << 'SSHCONF'
# Phoenix local node — no password auth
PasswordAuthentication no
PubkeyAuthentication yes
PermitRootLogin no
X11Forwarding no
AllowAgentForwarding no
SSHCONF

sudo systemctl reload ssh 2>/dev/null || sudo service ssh reload 2>/dev/null || true
ok "SSH configured — key auth only, no passwords"

# ── 3. SSH keypair ────────────────────────────────────────────
info "Generating SSH keypair..."
mkdir -p "$HOME/.ssh"
chmod 700 "$HOME/.ssh"

KEY="$HOME/.ssh/phoenix_${NODE_NAME}"

if [[ ! -f "$KEY" ]]; then
    ssh-keygen -t ed25519 \
        -f "$KEY" \
        -N "" \
        -C "phoenix@${NODE_NAME}"
    ok "Keypair: $KEY"
else
    ok "Keypair already exists: $KEY"
fi

# Add to authorized_keys (self-trust for local ops)
cat "${KEY}.pub" >> "$HOME/.ssh/authorized_keys"
chmod 600 "$HOME/.ssh/authorized_keys"
sort -u "$HOME/.ssh/authorized_keys" -o "$HOME/.ssh/authorized_keys"

# ── 4. SSH config — peer shortcut ─────────────────────────────
if [[ -n "$PEER_IP" ]]; then
    info "Configuring peer shortcut: phoenix-peer → $PEER_IP"

    cat >> "$HOME/.ssh/config" << SSHCFG

# Phoenix peer — added by bootstrap_node.sh
Host phoenix-peer
    HostName $PEER_IP
    User $USER
    IdentityFile $KEY
    StrictHostKeyChecking no
    ServerAliveInterval 30
    ServerAliveCountMax 3
SSHCFG

    chmod 600 "$HOME/.ssh/config"
    ok "SSH config: connect with  ssh phoenix-peer"

    # Push our public key to peer (one-time, uses password this time only)
    echo
    warn "One-time key exchange with peer $PEER_IP"
    warn "You'll be asked for the peer's password once — never again after this."
    echo
    if command -v ssh-copy-id &>/dev/null; then
        ssh-copy-id -i "${KEY}.pub" -o StrictHostKeyChecking=no "$USER@$PEER_IP" || \
            warn "Could not push key automatically — copy this to the peer manually:"
    else
        warn "ssh-copy-id not available. Copy this key to the peer manually:"
    fi
    echo
    cat "${KEY}.pub"
    echo
fi

# ── 5. Phoenix dir ────────────────────────────────────────────
info "Setting up Phoenix directory..."
mkdir -p "$PHOENIX_DIR"

if [[ -n "$REPO_URL" ]]; then
    if [[ -d "$PHOENIX_DIR/.git" ]]; then
        git -C "$PHOENIX_DIR" pull --quiet
        ok "Phoenix repo updated"
    else
        git clone "$REPO_URL" "$PHOENIX_DIR"
        ok "Phoenix repo cloned"
    fi
else
    warn "No REPO_URL set — copy PhoenixDevOps files to $PHOENIX_DIR manually"
    warn "Or set: export REPO_URL=<your-repo> and re-run"
fi

# ── 6. usys install ───────────────────────────────────────────
info "Installing usys..."
USYS_SH="$PHOENIX_DIR/sector4/usys.sh"
INTAKE_SH="$PHOENIX_DIR/sector4/intake.sh"

if [[ -f "$USYS_SH" ]]; then
    bash "$PHOENIX_DIR/scripts/install.sh"
    ok "usys installed"

    # Wire intake alongside usys
    if [[ -f "$INTAKE_SH" ]]; then
        cp "$INTAKE_SH" "$HOME/.usys/intake.sh"
        chmod +x "$HOME/.usys/intake.sh"
        ok "intake.sh installed to ~/.usys/"
    fi
else
    warn "usys.sh not found at $USYS_SH — install manually after copying files"
fi

# ── 7. Aliases ────────────────────────────────────────────────
info "Installing phoenix aliases..."
ALIASES_SRC="$PHOENIX_DIR/_kali_import/phoenix/phoenix_aliases.sh"
ALIASES_DST="$HOME/.phoenix_aliases"

if [[ -f "$ALIASES_SRC" ]]; then
    cp "$ALIASES_SRC" "$ALIASES_DST"

    for rc in "$HOME/.bashrc" "$HOME/.zshrc"; do
        [[ -f "$rc" ]] || continue
        if ! grep -q "phoenix_aliases" "$rc" 2>/dev/null; then
            echo "" >> "$rc"
            echo "# Phoenix aliases" >> "$rc"
            echo "[[ -f ~/.phoenix_aliases ]] && source ~/.phoenix_aliases" >> "$rc"
            ok "Aliases sourced in $rc"
        fi
    done
else
    warn "Aliases file not found — will skip"
fi

# ── 8. tmux config ───────────────────────────────────────────
info "Configuring tmux..."
cat > "$HOME/.tmux.conf" << 'TMUXCONF'
# Phoenix tmux config
set -g default-terminal "screen-256color"
set -g history-limit 10000
set -g mouse on

# Status bar
set -g status-style bg=black,fg=cyan
set -g status-left "#[bold]#[fg=green] phoenix:#S #[fg=cyan]| "
set -g status-right "#[fg=yellow]%H:%M #[fg=cyan]| #[fg=green]#h"
set -g status-left-length 30

# Window titles
set -g window-status-current-style fg=white,bold
setw -g window-status-current-format " [#I] #W "

# Pane borders
set -g pane-border-style fg=colour238
set -g pane-active-border-style fg=cyan

# No delay on escape
set -sg escape-time 0

# Share session — allow multiple clients
set -g allow-rename off
TMUXCONF
ok "tmux configured: ~/.tmux.conf"

# Aliases for tmux shared session
cat >> "$HOME/.phoenix_aliases" << 'TMUXALIASES'

# ── tmux shared session ───────────────────────────────────────
alias phoenix-session='tmux new-session -A -s phoenix'   # start or attach
alias join='tmux attach -t phoenix'                       # join from peer
alias sessions='tmux ls 2>/dev/null || echo "no sessions"'
TMUXALIASES
ok "tmux aliases added"

# If this is the main node (no peer IP = likely main), start the session
if [[ -z "$PEER_IP" ]]; then
    info "Main node — run 'phoenix-session' to start the shared session"
else
    info "Peer node — run 'join' after SSHing to main, or 'phoenix-session' for local"
fi

# ── 9. Barrier — shared keyboard/mouse ───────────────────────
info "Configuring Barrier..."

BARRIER_DIR="$HOME/.local/share/barrier"
mkdir -p "$BARRIER_DIR"

if [[ -z "$PEER_IP" ]]; then
    # Main machine = Barrier SERVER (controls the mouse/keyboard)
    info "This node = Barrier SERVER (main keyboard/mouse)"
    cat > "$BARRIER_DIR/barrier.conf" << BCONF
section: screens
    $(hostname):
    phoenix-peer:
end

section: links
    $(hostname):
        right = phoenix-peer
    phoenix-peer:
        left = $(hostname)
end

section: options
    heartbeat = 5000
    switchDelay = 250
end
BCONF

    # Autostart alias
    cat >> "$HOME/.phoenix_aliases" << 'BALIASES'

# ── Barrier ───────────────────────────────────────────────────
alias barrier-start='barriers --no-tray --debug ERROR --name $(hostname) --disable-crypto -c ~/.local/share/barrier/barrier.conf --address :24800 &'
alias barrier-stop='pkill barriers 2>/dev/null; echo "barrier stopped"'
BALIASES
    ok "Barrier server config written"
    info "Start with: barrier-start"
    info "All-in-one mouse lives to the RIGHT of this screen by default"

else
    # Peer machine = Barrier CLIENT
    info "This node = Barrier CLIENT (receives keyboard/mouse from main)"
    cat >> "$HOME/.phoenix_aliases" << BALIASES

# ── Barrier ───────────────────────────────────────────────────
alias barrier-start='barrierc --no-tray --debug ERROR --name $(hostname) --disable-crypto $PEER_IP:24800 &'
alias barrier-stop='pkill barrierc 2>/dev/null; echo "barrier stopped"'
BALIASES
    ok "Barrier client config written"
    info "Start with: barrier-start (after main node runs barrier-start)"
fi

# ── 10. Clonepool mount point ─────────────────────────────────
info "Creating clonepool mount point..."
sudo mkdir -p /mnt/clonepool
ok "/mnt/clonepool ready"
warn "Mount your dedicated drive here when available:"
warn "  sudo mount /dev/sdX1 /mnt/clonepool"
warn "  Or add to /etc/fstab for auto-mount"

# ── 11. Node identity ────────────────────────────────────────
info "Writing node identity..."
mkdir -p "$HOME/.usys"
cat > "$HOME/.usys/node.json" << NODEJSON
{
  "node_name": "$NODE_NAME",
  "user": "$USER",
  "hostname": "$(hostname)",
  "pubkey": "$(cat ${KEY}.pub)",
  "bootstrapped_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "peer_ip": "$PEER_IP",
  "pool_root": "/mnt/clonepool"
}
NODEJSON
ok "Node identity: ~/.usys/node.json"

# ── Done ──────────────────────────────────────────────────────
echo
echo -e "${BOLD}══════════════════════════════════════════${RESET}"
echo -e "  ${GREEN}Node bootstrap complete: $NODE_NAME${RESET}"
echo
echo -e "  ${CYAN}Activate aliases:${RESET}"
echo -e "    source ~/.bashrc"
echo
if [[ -n "$PEER_IP" ]]; then
echo -e "  ${CYAN}Connect to peer:${RESET}"
echo -e "    ssh phoenix-peer"
echo
fi
echo -e "  ${CYAN}First use:${RESET}"
echo -e "    ul          (usys list)"
echo -e "    ur <file> <name>   (register + auto-intake)"
echo
echo -e "  ${CYAN}Clonepool:${RESET}"
echo -e "    cpool       (cd /mnt/clonepool)"
echo -e "    clonepool   (ls /mnt/clonepool)"
echo
echo -e "  ${CYAN}Barrier (shared keyboard/mouse):${RESET}"
if [[ -z "$PEER_IP" ]]; then
echo -e "    barrier-start       start server (main machine)"
echo -e "    Then run barrier-start on the all-in-one"
echo -e "    Move mouse RIGHT to slide onto the all-in-one"
else
echo -e "    barrier-start       connect to main keyboard/mouse"
echo -e "    (run barrier-start on main first)"
fi
echo
echo -e "  ${CYAN}Shared session:${RESET}"
if [[ -z "$PEER_IP" ]]; then
echo -e "    phoenix-session     start shared tmux session"
echo -e "    (peer joins with:   ssh phoenix-peer then join)"
else
echo -e "    ssh phoenix-peer    connect to main"
echo -e "    join                attach to shared session"
fi
echo -e "${BOLD}══════════════════════════════════════════${RESET}"
echo
