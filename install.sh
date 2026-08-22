#!/usr/bin/env bash
# ============================================================
# install.sh — Phoenix DevOps OS Linux/macOS Installer
# USys — United Systems | jwl247 | GPL-3.0
#
# Installs: Phoenix DevOps OS, global commands, environment setup
#
# Usage:
#   bash install.sh
#   curl -fsSL https://raw.githubusercontent.com/jwl247/Phoenix-DevOps-oS/main/install.sh | bash
# ============================================================

set -euo pipefail

# ── Config ────────────────────────────────────────────────────
WORKER_URL='https://packages-worker.phoenix-jwl.workers.dev'
OS_REPO_URL='https://github.com/jwl247/Phoenix-DevOps-oS.git'
PKG_REPO_URL='https://github.com/jwl247/Phoenix-Package_handler.git'
INSTALL_ROOT="$HOME/Phoenix"
OS_DIR="$INSTALL_ROOT/Phoenix-DevOps-oS"
PKG_DIR="$INSTALL_ROOT/package-handler"
CLONEPOOL_DIR="$INSTALL_ROOT/clonepool"
ENV_SH="$HOME/.phoenix_env.sh"
USYS_DIR="$HOME/.usys"
USYS_BIN="$USYS_DIR/bin"

# ── Helpers ───────────────────────────────────────────────────
phx_info()  { echo -e "\033[36m[PHX]\033[0m $1"; }
phx_ok()    { echo -e "\033[32m[OK]\033[0m  $1"; }
phx_warn()  { echo -e "\033[33m[WARN]\033[0m $1"; }
phx_error() { echo -e "\033[31m[ERR]\033[0m $1"; exit 1; }

phx_banner() {
    echo ""
    echo "  ======================================"
    echo "   Phoenix DevOps OS Installer"
    echo "   UnitedSys / USys v0.1"
    echo "  ======================================"
    echo ""
}

# ── Main ──────────────────────────────────────────────────────
phx_banner

# Check for required tools
if ! command -v git &>/dev/null; then
    phx_error "git not found. Install: sudo apt install git (Debian/Ubuntu) or brew install git (macOS)"
fi

# Create directory structure
phx_info "Creating Phoenix directory structure..."
mkdir -p "$INSTALL_ROOT" "$OS_DIR" "$PKG_DIR" "$CLONEPOOL_DIR" "$USYS_DIR" "$USYS_BIN" "$HOME/.catalog"
phx_ok "Directories ready."

# Clone or update OS repo
if [[ -d "$OS_DIR/.git" ]]; then
    phx_info "OS repo exists — pulling latest..."
    git -C "$OS_DIR" pull --ff-only 2>/dev/null || phx_warn "Pull failed, continuing..."
    phx_ok "OS repo updated at $OS_DIR"
else
    phx_info "Cloning Phoenix-DevOps-oS to $OS_DIR ..."
    git clone "$OS_REPO_URL" "$OS_DIR"
    [[ -d "$OS_DIR/.git" ]] || phx_error "OS repo clone failed."
    phx_ok "OS repo cloned."
fi

# Clone or update package-handler
if [[ -d "$PKG_DIR/.git" ]]; then
    phx_info "package-handler exists — pulling..."
    git -C "$PKG_DIR" pull --ff-only 2>/dev/null || phx_warn "Pull failed, continuing..."
else
    phx_info "Cloning package-handler to $PKG_DIR ..."
    git clone "$PKG_REPO_URL" "$PKG_DIR"
fi

if [[ -f "$PKG_DIR/intake/intake.sh" ]]; then
    phx_ok "Sector 2 intake.sh ready."
else
    phx_warn "package-handler intake.sh not found — clone/intake will fail until fixed."
fi

# PHOENIX_AUTH prompt
if [[ -z "${PHOENIX_AUTH:-}" ]]; then
    if [[ -t 0 ]]; then
        echo ""
        echo "  Enter PHOENIX_AUTH token (Enter to skip — D1 sync disabled):"
        echo "  Cloudflare -> packages-worker -> Settings -> Variables"
        echo ""
        read -r -p "  PHOENIX_AUTH: " PHOENIX_AUTH
    else
        phx_warn "PHOENIX_AUTH not set — D1 sync disabled (non-interactive install)."
    fi
fi

# Write environment file
phx_info "Writing environment file..."
cat > "$ENV_SH" << EOF
# Phoenix DevOps OS environment — generated $(date -u +"%Y-%m-%dT%H:%M:%SZ")
export PHOENIX_ROOT="$OS_DIR"
export PHOENIX_AUTH="${PHOENIX_AUTH:-}"
export PHOENIX_WORKER_URL="$WORKER_URL"
export CLONEPOOL_DIR="$CLONEPOOL_DIR"
export PHOENIX_INTAKE="$PKG_DIR/intake/intake.sh"
export PHOENIX_INTAKE_SECTOR4="$OS_DIR/SECTOR4/intake/intake.sh"
EOF
chmod 600 "$ENV_SH"
phx_ok "Environment file written: $ENV_SH"

# Source environment
source "$ENV_SH"

# Install global commands
phx_info "Installing global Phoenix commands..."

install_cmd() {
    local name="$1"
    local src="$2"
    local dst="$USYS_BIN/$name"
    if [[ -f "$src" ]]; then
        cp "$src" "$dst"
        sed -i 's/\r//' "$dst"
        chmod +x "$dst"
        phx_ok "Installed: $name"
    else
        phx_warn "Source not found: $name (expected: $src)"
    fi
}

install_cmd "clone"      "$OS_DIR/tools/clone.sh"
install_cmd "align_dirs" "$OS_DIR/tools/align_dirs.sh"
install_cmd "get_distros" "$OS_DIR/tools/get_distros.sh"
install_cmd "intake"     "$OS_DIR/SECTOR4/intake/intake.sh"

# Generate usys command
cat > "$USYS_BIN/usys" << 'USYS'
#!/usr/bin/env bash
# Phoenix USys — United Systems global command
[[ -f "$HOME/.phoenix_env.sh" ]] && source "$HOME/.phoenix_env.sh"

PHX_ROOT="${PHOENIX_ROOT:-$HOME/Phoenix/Phoenix-DevOps-oS}"

case "${1:-help}" in
    status)
        echo ""
        echo "  Phoenix DevOps OS — System Status"
        echo "  $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
        echo ""
        for s in sector1 sector2 sector3 SECTOR4; do
            count=$(find "$PHX_ROOT/$s" -type f 2>/dev/null | wc -l)
            echo "  $s: $count files"
        done
        echo ""
        echo "  PHOENIX_ROOT: $PHX_ROOT"
        echo "  PHOENIX_AUTH: ${PHOENIX_AUTH:+set}"
        echo "  CLONEPOOL:    ${CLONEPOOL_DIR:-not set}"
        echo ""
        ;;
    init)
        echo "  [usys init] Phoenix already installed at $PHX_ROOT"
        ;;
    help|--help|-h|"")
        echo ""
        echo "  usys — Phoenix DevOps OS command layer"
        echo ""
        echo "  usys status       system health"
        echo "  usys init         (re)initialize Phoenix"
        echo "  usys help         this message"
        echo ""
        ;;
    *)
        echo "  usys: unknown command '$1' — try: usys help"
        exit 1
        ;;
esac
USYS
chmod +x "$USYS_BIN/usys"
sed -i 's/\r//' "$USYS_BIN/usys"
phx_ok "Installed: usys"

# Generate status command
cat > "$USYS_BIN/status" << 'STATUSCMD'
#!/usr/bin/env bash
# Phoenix status — quick health check
[[ -f "$HOME/.phoenix_env.sh" ]] && source "$HOME/.phoenix_env.sh"
PHX_ROOT="${PHOENIX_ROOT:-$HOME/Phoenix/Phoenix-DevOps-oS}"
echo ""
echo "  Phoenix Status — $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
echo ""
[[ -d "$PHX_ROOT" ]] && echo "  [OK] Root: $PHX_ROOT" || echo "  [!!] Root missing: $PHX_ROOT"
[[ -n "${PHOENIX_AUTH:-}" ]] && echo "  [OK] PHOENIX_AUTH set" || echo "  [--] PHOENIX_AUTH not set"
[[ -n "${CLONEPOOL_DIR:-}" && -d "${CLONEPOOL_DIR:-}" ]] && echo "  [OK] Clonepool: $CLONEPOOL_DIR" || echo "  [--] Clonepool: ${CLONEPOOL_DIR:-not set}"
echo ""
STATUSCMD
chmod +x "$USYS_BIN/status"
sed -i 's/\r//' "$USYS_BIN/status"
phx_ok "Installed: status"

# Generate run command stub
cat > "$USYS_BIN/run" << 'RUNCMD'
#!/usr/bin/env bash
# Phoenix run — execute a suit via franken5
[[ -f "$HOME/.phoenix_env.sh" ]] && source "$HOME/.phoenix_env.sh"
PHX_ROOT="${PHOENIX_ROOT:-$HOME/Phoenix/Phoenix-DevOps-oS}"

if [[ $# -eq 0 ]]; then
    echo "  Usage: run <suit.py> [args...]"
    echo "  Executes a franken5 suit in Phoenix context."
    exit 1
fi

SUIT="$1"; shift
if [[ ! -f "$SUIT" ]]; then
    echo "  run: suit not found: $SUIT"
    exit 1
fi

python3 "$SUIT" "$@"
RUNCMD
chmod +x "$USYS_BIN/run"
sed -i 's/\r//' "$USYS_BIN/run"
phx_ok "Installed: run"

phx_ok "Global commands installed to $USYS_BIN"

# Update PATH in shell configs
phx_info "Updating shell configuration..."

update_shell_config() {
    local config_file="$1"
    local shell_name="$2"
    
    if [[ -f "$config_file" ]]; then
        if ! grep -q "Phoenix DevOps OS" "$config_file" 2>/dev/null; then
            cat >> "$config_file" << 'EOF'

# Phoenix DevOps OS — added by install.sh
[[ -f "$HOME/.phoenix_env.sh" ]] && source "$HOME/.phoenix_env.sh"
export PATH="$HOME/.usys/bin:$PATH"
EOF
            phx_ok "Updated $shell_name config: $config_file"
        else
            phx_warn "$shell_name config already has Phoenix block — skipped."
        fi
    fi
}

update_shell_config "$HOME/.bashrc" "bash"
update_shell_config "$HOME/.zshrc" "zsh"

# Add to current session PATH
export PATH="$USYS_BIN:$PATH"

# Register machine with D1 (non-fatal)
if [[ -n "${PHOENIX_AUTH:-}" ]]; then
    phx_info "Registering machine with D1..."
    
    hostname=$(hostname)
    os_info=$(uname -s)
    version=$(uname -r)
    
    reg_body=$(cat <<EOF
{
  "package_name": "phoenix-devops-os",
  "hostname": "$hostname",
  "os": "$os_info",
  "version": "$version",
  "installed_by": "install.sh",
  "install_dir": "$OS_DIR"
}
EOF
)
    
    if command -v curl &>/dev/null; then
        response=$(curl -s -w "\n%{http_code}" -X POST "$WORKER_URL/installed/register" \
            -H "Authorization: Bearer $PHOENIX_AUTH" \
            -H "Content-Type: application/json" \
            -d "$reg_body" 2>/dev/null || echo "000")
        
        http_code=$(echo "$response" | tail -n1)
        if [[ "$http_code" =~ ^(200|201)$ ]]; then
            phx_ok "Machine registered."
        else
            phx_warn "D1 registration failed (HTTP $http_code)"
        fi
    else
        phx_warn "curl not found — D1 registration skipped."
    fi
fi

# Done
echo ""
echo "  ======================================"
echo "   Phoenix DevOps OS installed."
echo "  ======================================"
echo ""
echo "  Open a NEW terminal, then:"
echo "    usys status          <- system health"
echo "    clone <file>         <- Sector 2 clonepool intake"
echo "    intake <file>        <- Sector 4 vault intake"
echo "    status               <- Phoenix status check"
echo ""
echo "  Repo: $OS_DIR"
echo ""

# Made with Bob
