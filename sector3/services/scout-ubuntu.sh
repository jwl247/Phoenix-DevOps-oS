#!/usr/bin/env bash
# scout-ubuntu.sh — Inventory all git repos and Phoenix-related files on this machine.
# Run on Ubuntu: bash scout-ubuntu.sh
# Phoenix DevOps OS / jwl247 / GPL v3

BOLD='\033[1m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; RED='\033[0;31m'; NC='\033[0m'
hdr() { echo -e "\n${BOLD}${CYAN}── $* ──${NC}"; }
ok()  { echo -e "  ${GREEN}✓${NC} $*"; }
warn(){ echo -e "  ${YELLOW}⚠${NC}  $*"; }

echo -e "${BOLD}Phoenix Ubuntu Scout — $(hostname) — $(date)${NC}"

# ── All git repos on this machine ─────────────────────────────────────────────
hdr "Git repos found on this machine"
find "$HOME" /opt /srv 2>/dev/null -name ".git" -maxdepth 6 -type d | while read gitdir; do
    repo=$(dirname "$gitdir")
    name=$(basename "$repo")
    branch=$(git -C "$repo" branch --show-current 2>/dev/null || echo "?")
    remote=$(git -C "$repo" remote get-url origin 2>/dev/null || echo "no remote")
    size=$(du -sh "$repo" 2>/dev/null | cut -f1)
    echo -e "  ${BOLD}$name${NC}"
    echo "    path:   $repo"
    echo "    branch: $branch"
    echo "    remote: $remote"
    echo "    size:   $size"
done

# ── Phoenix-DevOps-oS specifically ───────────────────────────────────────────
hdr "Phoenix-DevOps-oS repo state"
PHOENIX_REPO=""
for candidate in \
    "$HOME/Phoenix/Phoenix-DevOps-oS" \
    "$HOME/phoenix-devops-os" \
    "$HOME/Phoenix-DevOps-oS" \
    "/opt/phoenix" \
    "/srv/phoenix"; do
    if [ -d "$candidate/.git" ]; then
        PHOENIX_REPO="$candidate"
        break
    fi
done

if [ -n "$PHOENIX_REPO" ]; then
    ok "Found at: $PHOENIX_REPO"
    git -C "$PHOENIX_REPO" log --oneline -5
    echo ""
    echo "  Sector structure:"
    for s in sector1 sector2 sector3 SECTOR4 phoenix-core dashboard; do
        if [ -d "$PHOENIX_REPO/$s" ]; then
            count=$(find "$PHOENIX_REPO/$s" -type f 2>/dev/null | wc -l)
            echo "    $s/ — $count files"
        else
            echo "    $s/ — MISSING"
        fi
    done
else
    warn "Phoenix-DevOps-oS NOT found — needs to be cloned or pushed"
fi

# ── Node / npm / Electron ─────────────────────────────────────────────────────
hdr "Runtime check"
for cmd in node npm electron claude python3; do
    if command -v $cmd &>/dev/null; then
        ok "$cmd — $(${cmd} --version 2>/dev/null | head -1)"
    else
        warn "$cmd — NOT installed"
    fi
done

# ── Disk ──────────────────────────────────────────────────────────────────────
hdr "Disk"
df -h / | tail -1 | awk '{printf "  / — used: %s of %s (%s free)\n", $3, $2, $4}'

# ── What to consolidate ───────────────────────────────────────────────────────
hdr "Repos that can likely be retired (already integrated into Phoenix)"
KNOWN="Phoenix-DevOps-oS\|Phoenix-Package_handler\|phoenix-package\|CoPES\|copes\|helix\|frank\|sector"
find "$HOME" 2>/dev/null -name ".git" -maxdepth 5 -type d | while read gitdir; do
    repo=$(dirname "$gitdir")
    name=$(basename "$repo")
    if echo "$name" | grep -qi "copes\|package.handler\|helix\|frank\|sector\|quadengine\|romeo\|juliet\|breach"; then
        remote=$(git -C "$repo" remote get-url origin 2>/dev/null || echo "no remote")
        warn "$name ($repo) — integrated into Phoenix, candidate for removal"
        echo "    remote was: $remote"
    fi
done

echo ""
echo -e "${BOLD}Paste this output to Claude before running push-dashboard.ps1.${NC}"
echo "Claude will map what needs to stay vs what can be retired."
