#!/usr/bin/env bash
# ============================================================
#  UnitedSys  —  install.sh
#  Drop this on any machine and run it.
#  That's it. That's the whole install.
#
#  curl -sL https://raw.githubusercontent.com/jwl247/unitedsys/main/install.sh | bash
#  — or —
#  ./install.sh
# ============================================================

set -euo pipefail

USYS_VERSION="0.1.0"
USYS_HOME="$HOME/.usys"
USYS_BIN="$USYS_HOME/bin"
REPO="https://raw.githubusercontent.com/jwl247/unitedsys/main"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info() { echo -e "${CYAN}[usys]${RESET} $*"; }
ok()   { echo -e "${GREEN}[usys]${RESET} $*"; }
warn() { echo -e "${YELLOW}[usys]${RESET} $*"; }
die()  { echo -e "${RED}[usys]${RESET} $*" >&2; exit 1; }

echo -e "${BOLD}"
echo "  ██╗   ██╗███████╗██╗   ██╗███████╗"
echo "  ██║   ██║██╔════╝╚██╗ ██╔╝██╔════╝"
echo "  ██║   ██║███████╗ ╚████╔╝ ███████╗"
echo "  ██║   ██║╚════██║  ╚██╔╝  ╚════██║"
echo "  ╚██████╔╝███████║   ██║   ███████║"
echo "   ╚═════╝ ╚══════╝   ╚═╝   ╚══════╝"
echo -e "${RESET}"
echo -e "  UnitedSys v${USYS_VERSION} installer"
echo -e "  Universal file registration, versioning, hotswap"
echo -e "  GPL v3  —  zero dependencies  —  no sudo required"
echo

# ── Check sqlite3 ─────────────────────────────────────────────
if ! command -v sqlite3 &>/dev/null; then
    warn "sqlite3 not found. Attempting to install..."
    if command -v apt &>/dev/null; then
        sudo apt install -y sqlite3
    elif command -v dnf &>/dev/null; then
        sudo dnf install -y sqlite
    elif command -v pacman &>/dev/null; then
        sudo pacman -S --noconfirm sqlite
    elif command -v brew &>/dev/null; then
        brew install sqlite3
    else
        die "Could not install sqlite3. Please install it manually and re-run."
    fi
fi

ok "sqlite3 found: $(sqlite3 --version | head -1)"

# ── Create directories ────────────────────────────────────────
mkdir -p "$USYS_HOME" "$USYS_BIN" \
         "$USYS_HOME/versions" \
         "$USYS_HOME/log"

# ── Get usys.sh ───────────────────────────────────────────────
if [[ -f "$(dirname "$0")/usys.sh" ]]; then
    # Running from local copy
    cp "$(dirname "$0")/usys.sh" "$USYS_HOME/usys.sh"
    info "Installed from local copy"
elif command -v curl &>/dev/null; then
    info "Downloading usys.sh..."
    curl -sL "$REPO/usys.sh" -o "$USYS_HOME/usys.sh"
elif command -v wget &>/dev/null; then
    info "Downloading usys.sh..."
    wget -q "$REPO/usys.sh" -O "$USYS_HOME/usys.sh"
else
    die "No curl or wget found and no local usys.sh. Cannot install."
fi

chmod +x "$USYS_HOME/usys.sh"

# ── Create bin symlink ────────────────────────────────────────
ln -sf "$USYS_HOME/usys.sh" "$USYS_BIN/usys"
chmod +x "$USYS_BIN/usys"

ok "usys installed: $USYS_HOME/usys.sh"

# ── Init the database ─────────────────────────────────────────
"$USYS_HOME/usys.sh" init

# ── Wire up PATH in shell rc ──────────────────────────────────
PATH_LINE='export PATH="$HOME/.usys/bin:$PATH"'

for rc in "$HOME/.bashrc" "$HOME/.zshrc" "$HOME/.profile"; do
    [[ -f "$rc" ]] || continue
    if ! grep -q "\.usys/bin" "$rc" 2>/dev/null; then
        echo "" >> "$rc"
        echo "# UnitedSys" >> "$rc"
        echo "$PATH_LINE" >> "$rc"
        ok "PATH added to $rc"
    fi
done

echo
echo -e "${BOLD}══════════════════════════════════════════${RESET}"
echo -e "  ${GREEN}UnitedSys installed successfully${RESET}"
echo
echo -e "  ${CYAN}Activate:${RESET}"
echo -e "    source ~/.bashrc"
echo
echo -e "  ${CYAN}First use:${RESET}"
echo -e "    usys register <yourfile> <name>"
echo -e "    usys call <name>"
echo -e "    usys list"
echo
echo -e "  ${CYAN}Hotswap:${RESET}"
echo -e "    usys swap <name> <newfile>"
echo -e "    usys rollback <name>"
echo -e "${BOLD}══════════════════════════════════════════${RESET}"
echo
