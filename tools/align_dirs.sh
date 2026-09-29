#!/usr/bin/env bash
# align_dirs.sh — create the Phoenix directory layout on a Linux box
# (Phoenix's Debian VM or bare-metal Debian/Ubuntu). Phoenix DevOps LLC — jwl247
#
# Rewritten in bash 2026-09-29 (S34OPS-F31): the old zsh version branched on
# WSL (not used, not planned), hardcoded USER=jwl247, used the stale
# ~/projects/phoenix layout, iterated arrays zsh-style (under `bash`, which is
# how bin/align_dirs runs it, only the first dir was ever created) and added a
# `chmod -R 777` alias. PATH setup is install.sh's job (~/.usys/bin).
#
# Usage:
#   align_dirs.sh            create what is missing (user dirs; system dirs only if writable)
#   align_dirs.sh --check    audit only — report, change nothing

set -euo pipefail

CHECK_ONLY=0
[[ "${1:-}" == "--check" ]] && CHECK_ONLY=1

PHX_USER="${USER:-$(id -un)}"
HOME_DIR="${HOME:-/home/$PHX_USER}"

# User-level layout (matches install.sh).
USER_DIRS=(
    "$HOME_DIR/Phoenix"
    "$HOME_DIR/Phoenix/clonepool"
    "$HOME_DIR/.catalog"
    "$HOME_DIR/.config"
    "$HOME_DIR/.local/bin"
    "$HOME_DIR/.usys/bin"
    "$HOME_DIR/.unitedsys/logs"
)

# System-level paths — created only when writable, otherwise reported.
SYSTEM_DIRS=(
    "/etc/systemd/system"
    "/opt2"
)

# Vault mount points — labeled, not UUID-based. Create the mount point only;
# never mount, never change drive state. (Which mount convention is canonical,
# /media/<user>/breach_comsN vs the Debian-VM /mnt/{g,f,e,d}, is open with
# Jerry — S34OPS-F22.)
VAULT_MOUNTS=(
    "/media/$PHX_USER/breach_coms1"
    "/media/$PHX_USER/breach_coms2"
    "/media/$PHX_USER/breach_coms3"
    "/media/$PHX_USER/breach_coms4"
)

ensure_dir() {
    local d="$1" note="${2:-}"
    if [[ -d "$d" ]]; then
        echo "  [OK]   $d"
    elif (( CHECK_ONLY )); then
        echo "  [--]   $d  (missing)"
    elif mkdir -p "$d" 2>/dev/null; then
        echo "  [NEW]  created $d${note:+ ($note)}"
    else
        echo "  [SUDO] $d not writable — run: sudo mkdir -p '$d'"
    fi
}

echo "[align] user=$PHX_USER home=$HOME_DIR mode=$([[ $CHECK_ONLY == 1 ]] && echo check || echo create)"
echo ""
echo "[align] user dirs:"
for d in "${USER_DIRS[@]}"; do ensure_dir "$d"; done
echo ""
echo "[align] system dirs:"
for d in "${SYSTEM_DIRS[@]}"; do ensure_dir "$d"; done
echo ""
echo "[align] vault mount points (mount point only — label drives and add to fstab):"
for d in "${VAULT_MOUNTS[@]}"; do ensure_dir "$d" "mount point only"; done

# ─── Aliases (idempotent, per shell rc that exists) ───────────────
ALIASES=(
    "alias greyskull='sudo chattr +i'"
    "alias ungreyskull='sudo chattr -i'"
    "alias reveal='xdg-open .'"
    "alias s4='cd /etc/systemd/system'"
    "alias s3='cd /etc/systemd'"
)

if (( ! CHECK_ONLY )); then
    echo ""
    for rc in "$HOME_DIR/.bashrc" "$HOME_DIR/.zshrc"; do
        [[ -f "$rc" ]] || continue
        for a in "${ALIASES[@]}"; do
            key="${a%%=*}"
            if grep -qF "$key=" "$rc" 2>/dev/null; then
                echo "[skip] $key already in $rc"
            else
                echo "$a" >> "$rc"
                echo "[OK]   added $key to $rc"
            fi
        done
    done
fi

echo ""
echo "[align] Complete."
