#!/usr/bin/env zsh
# align_dirs.sh
# Run in WSL now to audit, run again on bare metal to create matching structure
# Phoenix DevOps LLC — jwl247

set -e

USER="jwl247"
HOME_DIR="/home/$USER"

# ─── Detect environment ───────────────────────────────────────────
if grep -qi microsoft /proc/version 2>/dev/null; then
    ENV="wsl"
else
    ENV="live"
fi
echo "[align] Running in: $ENV"

# ─── Core dirs to align ───────────────────────────────────────────
DIRS=(
    "$HOME_DIR/projects/phoenix"
    "$HOME_DIR/projects/phoenix/unitedsys"
    "$HOME_DIR/projects/phoenix/repo"
    "$HOME_DIR/.catalog"
    "$HOME_DIR/.config"
    "$HOME_DIR/.local/bin"
    "/etc/systemd/system"
    "/opt2"
)

# Vault mounts — labeled, not UUID-based
VAULT_MOUNTS=(
    "/media/$USER/breach_coms1"
    "/media/$USER/breach_coms2"
    "/media/$USER/breach_coms3"
    "/media/$USER/breach_coms4"
)

# ─── Audit mode (WSL) ─────────────────────────────────────────────
if [[ "$ENV" == "wsl" ]]; then
    echo "\n[audit] Checking dirs in WSL:\n"
    for d in $DIRS $VAULT_MOUNTS; do
        if [[ -d "$d" ]]; then
            echo "  [OK]  $d"
        else
            echo "  [--]  $d  ← MISSING, will be created on live"
        fi
    done

    echo "\n[audit] WSL path to Windows host:"
    echo "  /mnt/c/Users/jwlef/   ← Windows home from WSL"
    echo "  \\\\wsl\$\\Debian\\home\\jwl247\\  ← WSL home from Windows Explorer"
    echo "\n[audit] Done. Run this script on bare metal to create matching structure."
    exit 0
fi

# ─── Create mode (bare metal live Linux) ──────────────────────────
echo "\n[align] Creating directory structure on live Linux:\n"

for d in $DIRS; do
    if [[ -d "$d" ]]; then
        echo "  [skip] $d already exists"
    else
        mkdir -p "$d"
        echo "  [OK]   created $d"
    fi
done

# Vault mount points — create but don't mount (needs fstab/labels)
for d in $VAULT_MOUNTS; do
    if [[ -d "$d" ]]; then
        echo "  [skip] $d already exists"
    else
        mkdir -p "$d"
        echo "  [OK]   created $d (mount point only — label drives and add to fstab)"
    fi
done

# ─── .zshrc PATH alignment ────────────────────────────────────────
ZSHRC="$HOME_DIR/.zshrc"
US_PATH='export PATH="$HOME/projects/phoenix/unitedsys/bin:$PATH"'

if grep -q "unitedsys/bin" "$ZSHRC" 2>/dev/null; then
    echo "\n[skip] PATH already set in .zshrc"
else
    echo "\n$US_PATH" >> "$ZSHRC"
    echo "[OK]  Added unitedsys/bin to PATH in .zshrc"
fi

# ─── Aliases ──────────────────────────────────────────────────────
ALIASES=(
    "alias greyskull='sudo chattr +i'"
    "alias ungreyskull='sudo chattr -i'"
    "alias shazam='sudo chmod -R 777'"
    "alias reveal='xdg-open .'"
    "alias s4='cd /etc/systemd/system'"
    "alias s3='cd /etc/systemd'"
)

for a in $ALIASES; do
    KEY="${a%%=*}"
    if grep -q "$KEY" "$ZSHRC" 2>/dev/null; then
        echo "[skip] $KEY already in .zshrc"
    else
        echo "$a" >> "$ZSHRC"
        echo "[OK]  Added $KEY"
    fi
done

echo "\n[align] Complete. Run: source ~/.zshrc"
