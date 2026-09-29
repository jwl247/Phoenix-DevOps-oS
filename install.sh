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
# The standalone Phoenix-Package_handler repo is no longer cloned: the
# canonical Sector 2 pipeline is in-repo (sector2/package-handler/intake.sh)
# and the standalone copy was archived 2026-09-13 (S34OPS-F21).
INSTALL_ROOT="$HOME/Phoenix"
OS_DIR="$INSTALL_ROOT/Phoenix-DevOps-oS"
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
mkdir -p "$INSTALL_ROOT" "$OS_DIR" "$CLONEPOOL_DIR" "$USYS_DIR" "$USYS_BIN" "$HOME/.catalog"
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

# Canonical Sector 2 intake is the in-repo pipeline (R2 + integrity +
# Cloudflare Access headers). The standalone package-handler clone keeps
# intake.sh at its root (no intake/ subdir) and lacks the Access fix.
INTAKE_SH="$OS_DIR/sector2/package-handler/intake.sh"
if [[ -f "$INTAKE_SH" ]]; then
    phx_ok "Sector 2 intake.sh ready."
else
    phx_warn "sector2/package-handler/intake.sh not found — clone/intake will fail until fixed."
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
export PHOENIX_INTAKE="$INTAKE_SH"
export PHOENIX_INTAKE_SECTOR4="$OS_DIR/sector4/intake/intake.sh"
EOF
chmod 600 "$ENV_SH"
phx_ok "Environment file written: $ENV_SH"

# Source environment
source "$ENV_SH"

# Install global commands
# The real wrappers live in bin/ (S34OPS-F21). They were previously generated
# here as stubs (a 3-command usys, a python-only run), so a Linux install
# never had usys clone/run/pull/search/open. bin/usys and bin/run delegate to
# scripts/usys.ps1 and therefore need PowerShell 7 (pwsh) on this box.
phx_info "Installing global Phoenix commands from $OS_DIR/bin ..."

install_cmd() {
    local name="$1"
    local src="$OS_DIR/bin/$name"
    local dst="$USYS_BIN/$name"
    if [[ -f "$src" ]]; then
        # Strip CR in case the repo was copied from a Windows checkout.
        tr -d '\r' < "$src" > "$dst"
        chmod +x "$dst"
        phx_ok "Installed: $name"
    else
        phx_warn "Source not found: $name (expected: $src)"
    fi
}

for cmd in usys run clone intake status align_dirs get_distros; do
    install_cmd "$cmd"
done

if ! command -v pwsh &>/dev/null; then
    phx_warn "PowerShell 7 (pwsh) not found — 'usys' and 'run' need it (they delegate to scripts/usys.ps1)."
    phx_warn "Install: https://aka.ms/install-powershell  (clone/intake/status work without it)"
fi

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
echo "    usys status          <- system health (needs pwsh)"
echo "    clone <file>         <- Sector 2 clonepool intake"
echo "    intake <file>        <- Sector 2 clonepool intake (same pipeline as clone)"
echo "    status               <- Phoenix status check (status.sh)"
echo ""
echo "  Repo: $OS_DIR"
echo ""

# Made with Bob
