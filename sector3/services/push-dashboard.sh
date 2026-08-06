#!/usr/bin/env bash
# push-dashboard.sh — Sync dashboard to Ubuntu over WireGuard/SSH and run the installer.
# Run from WSL on your Windows machine.
# Phoenix DevOps OS / jwl247 / GPL v3
#
# Usage:
#   bash push-dashboard.sh                        # defaults to 192.168.1.133
#   bash push-dashboard.sh 10.0.0.1               # WireGuard IP
#   bash push-dashboard.sh 10.0.0.1 jerry         # WireGuard IP + SSH user

set -euo pipefail

BOLD='\033[1m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
ok()  { echo -e "${GREEN}✓${NC} $*"; }
hdr() { echo -e "\n${BOLD}── $* ──${NC}"; }

UBUNTU_HOST="${1:-192.168.1.133}"
UBUNTU_USER="${2:-$(whoami)}"
UBUNTU_DEST="$UBUNTU_USER@$UBUNTU_HOST"

# Locate repo root relative to this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

REMOTE_REPO="~/Phoenix/Phoenix-DevOps-oS"

hdr "Phoenix Dashboard → Ubuntu"
echo "  Host:  $UBUNTU_DEST"
echo "  From:  $REPO_ROOT"
echo "  To:    $REMOTE_REPO"

# ── Confirm SSH works ─────────────────────────────────────────────────────────
hdr "SSH check"
ssh -o ConnectTimeout=8 -o BatchMode=yes "$UBUNTU_DEST" "echo ok" \
  || { echo -e "${RED}✗ Cannot reach $UBUNTU_DEST — check WireGuard / SSH${NC}"; exit 1; }
ok "SSH reachable"

# ── Ensure remote repo dir exists ─────────────────────────────────────────────
ssh "$UBUNTU_DEST" "mkdir -p $REMOTE_REPO/dashboard $REMOTE_REPO/sector3/services"

# ── Rsync dashboard (skip node_modules and build artifacts) ──────────────────
hdr "Syncing dashboard"
rsync -avz --progress \
  --exclude='node_modules/' \
  --exclude='.cache/' \
  --exclude='*.log' \
  "$REPO_ROOT/dashboard/" \
  "$UBUNTU_DEST:$REMOTE_REPO/dashboard/"
ok "dashboard synced"

# ── Rsync sector3/services (deploy script + service template) ────────────────
hdr "Syncing sector3/services"
rsync -avz --progress \
  "$REPO_ROOT/sector3/services/" \
  "$UBUNTU_DEST:$REMOTE_REPO/sector3/services/"
ok "services synced"

# ── Run the installer on Ubuntu ───────────────────────────────────────────────
hdr "Running deploy-dashboard.sh on Ubuntu"
ssh -t "$UBUNTU_DEST" "
  export PHOENIX_ROOT=$REMOTE_REPO
  chmod +x $REMOTE_REPO/sector3/services/deploy-dashboard.sh
  bash $REMOTE_REPO/sector3/services/deploy-dashboard.sh
"

echo ""
echo -e "${BOLD}${GREEN}Done. Dashboard is live on $UBUNTU_HOST.${NC}"
echo "  Watch logs: ssh $UBUNTU_DEST 'journalctl --user -u phoenix-dashboard -f'"
