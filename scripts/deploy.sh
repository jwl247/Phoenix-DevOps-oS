#!/usr/bin/env bash
# ============================================================
#  Phoenix-DevOps-oS — Deploy Script
#
#  Clones the base stack across all 16 rings.
#  Drops ring configs in place.
#  Injects drive UUIDs into SECTOR4.
#  Symlinks propcoms.
#  Data goes where it's told. Original form preserved.
#
#  Usage:
#    sudo bash deploy.sh
# ============================================================

set -euo pipefail

SYSTEMD="/etc/systemd/system"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BASE_STACK="$SYSTEMD/SECTOR4/coms4"

RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'
BOLD='\033[1m'; RESET='\033[0m'

info() { echo -e "${CYAN}[deploy]${RESET} $*"; }
ok()   { echo -e "${GREEN}[deploy]${RESET} $*"; }
die()  { echo -e "${RED}[deploy]${RESET} $*" >&2; exit 1; }

[[ $EUID -ne 0 ]] && die "Run as root: sudo bash deploy.sh"
[[ -d "$BASE_STACK" ]] || die "Base stack not found at $BASE_STACK"

# ── Sector 4 drive UUIDs ──────────────────────────────────────
declare -A S4_UUIDS=(
    ["coms1"]="9ce1c4ff-599a-482b-8b32-97fd53099ca4"
    ["coms2"]="44c72008-e269-4d96-b7a7-00a981da2ad1"
    ["coms3"]="a67ef4fb-bb2e-4e98-b60b-48e42c49e6a2"
    ["coms4"]="a339483b-3453-4c69-a4c8-1954088dbf4a"
)

# ── All sectors and their rings ───────────────────────────────
SECTORS=("SECTOR1" "SECTOR2" "SECTOR3" "SECTOR4")
RINGS=("coms1" "coms2" "coms3" "coms4")

echo
echo -e "${BOLD}════════════════════════════════════════════${RESET}"
echo -e "  Phoenix Deploy — 16 rings"
echo -e "${BOLD}════════════════════════════════════════════${RESET}"
echo

# ── Step 1: Clone base stack into all rings ───────────────────
info "Step 1 — Cloning base stack across all sectors..."

for SECTOR in "${SECTORS[@]}"; do
    mkdir -p "$SYSTEMD/$SECTOR"
    for COMS in "${RINGS[@]}"; do
        DEST="$SYSTEMD/$SECTOR/$COMS"
        if [[ "$SECTOR" == "SECTOR4" && "$COMS" == "coms4" ]]; then
            ok "  $SECTOR/$COMS — origin, skipping clone"
            continue
        fi
        mkdir -p "$DEST"
        cp -r "$BASE_STACK/." "$DEST/"
        ok "  $SECTOR/$COMS — cloned"
    done
done

# ── Step 2: Inject drive UUIDs into SECTOR4 freewheeling ──────
info "Step 2 — Injecting drive UUIDs into SECTOR4..."

for COMS in "${RINGS[@]}"; do
    UUID="${S4_UUIDS[$COMS]}"
    FW="$SYSTEMD/SECTOR4/$COMS/freewheeling.py"
    if [[ -f "$FW" ]]; then
        # Inject drive_uuid into DoubleHelixStorage.__init__
        sed -i "s/def __init__(self, base_size: float = 1\.0, spiral_radius: float = 10\.0):/def __init__(self, base_size: float = 1.0, spiral_radius: float = 10.0, drive_uuid: str = \"$UUID\"):/" "$FW" 2>/dev/null || true
        sed -i "s/def __init__(self, initial_levels: int = 5):/def __init__(self, initial_levels: int = 5, drive_uuid: str = \"$UUID\"):/" "$FW" 2>/dev/null || true
        ok "  SECTOR4/$COMS — UUID $UUID"
    else
        info "  SECTOR4/$COMS — freewheeling.py not found, skipping UUID inject"
    fi
done

# ── Step 3: Drop ring_config.json into each ring ──────────────
info "Step 3 — Dropping ring configs..."

for SECTOR in "${SECTORS[@]}"; do
    SECTOR_LOWER=$(echo "$SECTOR" | tr '[:upper:]' '[:lower:]')
    for COMS in "${RINGS[@]}"; do
        CONFIG="$REPO_DIR/$SECTOR_LOWER/$COMS/ring_config.json"
        DEST="$SYSTEMD/$SECTOR/$COMS/ring_config.json"
        if [[ -f "$CONFIG" ]]; then
            cp "$CONFIG" "$DEST"
            ok "  $SECTOR/$COMS — ring_config.json dropped"
        else
            info "  $SECTOR/$COMS — no ring_config.json in repo, skipping"
        fi
    done
done

# ── Step 4: Symlink propcoms ──────────────────────────────────
info "Step 4 — Symlinking propcoms..."

PROPCOMS_SRC="$SYSTEMD/SECTOR4/coms4/propcoms.py"

for SECTOR in "${SECTORS[@]}"; do
    for COMS in "${RINGS[@]}"; do
        DEST="$SYSTEMD/$SECTOR/$COMS/propcoms.py"
        if [[ "$SECTOR" == "SECTOR4" && "$COMS" == "coms4" ]]; then
            continue
        fi
        ln -sf "$PROPCOMS_SRC" "$DEST"
        ok "  $SECTOR/$COMS — propcoms symlinked"
    done
done

# ── Step 5: Reload systemd ────────────────────────────────────
info "Step 5 — Reloading systemd..."
systemctl daemon-reload
ok "  systemd reloaded"

# ── Done ──────────────────────────────────────────────────────
echo
echo -e "${BOLD}════════════════════════════════════════════${RESET}"
ok "Deploy complete — 16 rings populated"
echo -e "  Base stack : $BASE_STACK"
echo -e "  Sectors    : ${SECTORS[*]}"
echo -e "${BOLD}════════════════════════════════════════════${RESET}"
echo
