#!/usr/bin/env bash
# ============================================================
# LOL Bootstrap Installer for Linux/macOS
# Ultra-minimal installer that enables: lol install <package>
# ============================================================

set -euo pipefail

echo ""
echo "  🔥 LOL Bootstrap Installer"
echo "  Installing minimal LOL command..."
echo ""

# Create LOL directory
LOL_HOME="$HOME/.lol"
LOL_BIN="$LOL_HOME/bin"
mkdir -p "$LOL_BIN"

# Create lol command
cat > "$LOL_BIN/lol" << 'EOFSCRIPT'
#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat << 'EOF'

  LOL - Live Ops Loader
  Ultra-simple package installer

  Usage:
    lol install <package>
    lol help

  Examples:
    lol install phoenix-devops-os
    lol install phoenix-package-handler

EOF
}

if [[ $# -eq 0 ]] || [[ "${1:-}" == "help" ]] || [[ "${1:-}" == "--help" ]]; then
    usage
    exit 0
fi

if [[ "${1:-}" != "install" ]]; then
    echo "[ERROR] Unknown command: $1"
    usage
    exit 1
fi

if [[ $# -lt 2 ]]; then
    echo "[ERROR] Package name required"
    echo "Usage: lol install <package>"
    exit 1
fi

PACKAGE="$2"
echo ""
echo "  [LOL] Installing: $PACKAGE"
echo ""

# Package registry
case "$PACKAGE" in
    phoenix-devops-os)
        INSTALL_URL="https://raw.githubusercontent.com/jwl247/Phoenix-DevOps-oS/main/install.sh"
        ;;
    phoenix-package-handler)
        INSTALL_URL="https://raw.githubusercontent.com/jwl247/Phoenix-Package_handler/main/install.sh"
        ;;
    *)
        echo "[ERROR] Unknown package: $PACKAGE"
        echo ""
        echo "Available packages:"
        echo "  - phoenix-devops-os"
        echo "  - phoenix-package-handler"
        echo ""
        exit 1
        ;;
esac

# Execute installer
if command -v curl &>/dev/null; then
    curl -fsSL "$INSTALL_URL" | bash
elif command -v wget &>/dev/null; then
    wget -qO- "$INSTALL_URL" | bash
else
    echo "[ERROR] Neither curl nor wget found"
    exit 1
fi

if [[ $? -eq 0 ]]; then
    echo ""
    echo "  [LOL] Installation complete!"
    echo ""
else
    echo ""
    echo "  [LOL] Installation failed"
    echo ""
    exit 1
fi
EOFSCRIPT

chmod +x "$LOL_BIN/lol"
echo "  ✅ Created: lol command"

# Add to PATH in shell configs
update_shell_config() {
    local config_file="$1"
    local shell_name="$2"
    
    if [[ -f "$config_file" ]]; then
        if ! grep -q "\.lol/bin" "$config_file" 2>/dev/null; then
            echo "" >> "$config_file"
            echo "# LOL - Live Ops Loader" >> "$config_file"
            echo 'export PATH="$HOME/.lol/bin:$PATH"' >> "$config_file"
            echo "  ✅ Updated $shell_name config"
        else
            echo "  ℹ️  $shell_name config already updated"
        fi
    fi
}

update_shell_config "$HOME/.bashrc" "bash"
update_shell_config "$HOME/.zshrc" "zsh"

# Add to current session
export PATH="$LOL_BIN:$PATH"

echo ""
echo "  ====================================="
echo "   LOL Bootstrap Complete!"
echo "  ====================================="
echo ""
echo "  Open a NEW terminal and run:"
echo "    lol install phoenix-devops-os"
echo ""

# Made with Bob
