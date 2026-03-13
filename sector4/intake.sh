#!/usr/bin/env bash
# ============================================================
#  UnitedSys — intake.sh
#  File intake pipeline for the clone pool.
#
#  Flow:
#    1. Receive file
#    2. Filename → hex (the system identity)
#    3. Sidecar JSON (source of truth, metadata lives here)
#    4. QR header (top)  — state color: white/black/grey
#    5. QR footer (bottom) — location/tier color
#    6. Register into usys + clone pool
#
#  State (top QR color):
#    white  = good / active
#    black  = corrupt / trash
#    grey   = deprecated → auto-hotswaps when opportunity presents
#
#  Location (bottom QR color, max 4 deep):
#    Tier 1: red #FF0000 | blue #0000FF | yellow #FFFF00
#    Tier 2: green #00CC00 | orange #FF8800 | purple #8800CC
#    Tier 3: cyan #00CCCC | magenta #CC00CC | lime #88CC00
#    Tier 4: brown #884400 | pink #FF88AA | teal #008888 | navy #000088
#
#  Usage:
#    intake.sh <file> <clone_pool_path> [state] [description]
#    intake.sh deprecate <name>
#    intake.sh hotswap-check
#
#  Deps: bash, sqlite3, qrencode, python3
#  Optional: imagemagick (composite sheet)
#  Platform: Debian
#  GPL v3
# ============================================================

set -euo pipefail

INTAKE_VERSION="0.1.0"
USYS_HOME="${USYS_HOME:-$HOME/.usys}"
USYS_DB="$USYS_HOME/usys.db"
POOL_ROOT="${POOL_ROOT:-/mnt/clonepool}"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info() { echo -e "${CYAN}[intake]${RESET} $*"; }
ok()   { echo -e "${GREEN}[intake]${RESET} $*"; }
warn() { echo -e "${YELLOW}[intake]${RESET} $*"; }
err()  { echo -e "${RED}[intake]${RESET} $*" >&2; }
die()  { err "$*"; exit 1; }

# ── Deps ──────────────────────────────────────────────────────
require_deps() {
    command -v sqlite3  &>/dev/null || die "sqlite3 not found"
    command -v qrencode &>/dev/null || die "qrencode not found — apt install qrencode"
    command -v python3  &>/dev/null || die "python3 not found"
}

# ── Filename → hex ────────────────────────────────────────────
to_hex() {
    printf '%s' "$1" | xxd -p | tr -d '\n'
}

# ── Clone pool depth → tier (1-4) ─────────────────────────────
detect_tier() {
    local path="$1"
    local rel="${path#$POOL_ROOT}"
    rel="${rel#/}"
    [[ -z "$rel" ]] && echo 1 && return
    local depth
    depth=$(echo "$rel" | tr -cd '/' | wc -c)
    local tier=$(( depth + 1 ))
    [[ $tier -gt 4 ]] && tier=4
    echo "$tier"
}

# ── Tier + index → location color ─────────────────────────────
tier_color() {
    local tier="$1" idx="$2"
    case "$tier" in
        1) case "$idx" in 0) echo "FF0000";; 1) echo "0000FF";; *) echo "FFFF00";; esac ;;
        2) case "$idx" in 0) echo "00CC00";; 1) echo "FF8800";; *) echo "8800CC";; esac ;;
        3) case "$idx" in 0) echo "00CCCC";; 1) echo "CC00CC";; *) echo "88CC00";; esac ;;
        4) case "$idx" in 0) echo "884400";; 1) echo "FF88AA";; 2) echo "008888";; *) echo "000088";; esac ;;
        *) echo "FF0000" ;;
    esac
}

# ── State → QR fg/bg colors ───────────────────────────────────
state_colors() {
    case "$1" in
        white) echo "000000 FFFFFF" ;;   # good
        black) echo "FFFFFF 000000" ;;   # corrupt
        grey)  echo "444444 AAAAAA" ;;   # deprecated
        *)     echo "000000 FFFFFF" ;;
    esac
}

# ── Generate QR PNG ───────────────────────────────────────────
gen_qr() {
    local content="$1" out="$2" fg="$3" bg="$4"
    qrencode \
        --foreground="$fg" \
        --background="$bg" \
        --size=6 --margin=2 --level=M \
        --type=PNG --output="$out" \
        "$content"
}

# ── Next version number from usys DB ──────────────────────────
next_version() {
    local name="$1"
    [[ ! -f "$USYS_DB" ]] && echo "v1" && return
    local count
    count=$(sqlite3 "$USYS_DB" \
        "SELECT COUNT(*) FROM versions WHERE package='$name';" 2>/dev/null || echo 0)
    echo "v$((count + 1))"
}

# ── Sidecar JSON ──────────────────────────────────────────────
write_sidecar() {
    local out="$1"
    python3 - <<PYEOF
import json, time

s = {
    "usys_intake":    "$INTAKE_VERSION",
    "hex_name":       "$2",
    "original_name":  "$3",
    "state":          "$4",
    "version":        "$5",
    "size_bytes":     $6,
    "description":    "$7",
    "clone_pool": {
        "path":       "$8",
        "tier":       $9,
        "tier_color": "#${10}",
        "max_depth":  4
    },
    "qr": {
        "header": {
            "path":    "$11",
            "role":    "state",
            "state":   "$4"
        },
        "footer": {
            "path":    "$12",
            "role":    "location",
            "tier":    $9,
            "color":   "#${10}"
        }
    },
    "auto_hotswap":   "$4" == "grey",
    "registered_at":  time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "clone_history":  []
}

with open("$out", "w") as f:
    json.dump(s, f, indent=2)
PYEOF
}

# ── Append to clone history in sidecar ────────────────────────
append_history() {
    local sidecar="$1" version="$2" src="$3"
    python3 - <<PYEOF
import json, time
with open("$sidecar") as f:
    s = json.load(f)
s["clone_history"].append({
    "version": "$version",
    "source":  "$src",
    "at":      time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
})
s["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
with open("$sidecar", "w") as f:
    json.dump(s, f, indent=2)
PYEOF
}

# ── Register / update in usys DB ─────────────────────────────
register_usys() {
    local name="$1" hex="$2" src="$3" state="$4"
    local pool="$5" ver="$6" size="$7" sidecar="$8"

    [[ -f "$USYS_DB" ]] || die "usys not initialized — run: usys init"

    local exists
    exists=$(sqlite3 "$USYS_DB" "SELECT COUNT(*) FROM packages WHERE name='$name';")

    if [[ "$exists" -gt 0 ]]; then
        sqlite3 "$USYS_DB" <<SQL
INSERT INTO versions (package, version, store_path, hash, size, note)
VALUES ('$name', '$ver', '$pool/$hex', '', $size, 'intake state=$state');

UPDATE packages
SET current_ver='$ver', source_path='$src',
    updated=datetime('now'),
    tags='sidecar=$sidecar',
    description='state=$state'
WHERE name='$name';

INSERT INTO swaplog (package, from_ver, to_ver, action, note)
VALUES ('$name', (SELECT current_ver FROM packages WHERE name='$name'),
        '$ver', 'intake', 'state=$state');
SQL
    else
        sqlite3 "$USYS_DB" <<SQL
INSERT INTO packages (name, current_ver, source_path, bin_path, filetype, tags, description)
VALUES ('$name', '$ver', '$src', '$USYS_HOME/bin/$name', 'intake', 'sidecar=$sidecar', 'state=$state');

INSERT INTO versions (package, version, store_path, hash, size, note)
VALUES ('$name', '$ver', '$pool/$hex', '', $size, 'intake: initial');

INSERT INTO swaplog (package, from_ver, to_ver, action, note)
VALUES ('$name', NULL, '$ver', 'intake', 'initial state=$state');
SQL
    fi
}

# ============================================================
#  MAIN INTAKE
# ============================================================

cmd_intake() {
    local src="${1:-}" pool="${2:-}" state="${3:-white}" desc="${4:-}"

    [[ -z "$src"  ]] && die "Usage: intake.sh <file> <clone_pool_path> [state] [description]"
    [[ -z "$pool" ]] && die "Usage: intake.sh <file> <clone_pool_path> [state] [description]"
    [[ -f "$src"  ]] || die "File not found: $src"
    [[ "$state" == "white" || "$state" == "black" || "$state" == "grey" ]] || \
        die "State must be: white | black | grey"

    require_deps
    src="$(realpath "$src")"

    local fname size tier tier_idx color ver
    fname="$(basename "$src")"
    size="$(wc -c < "$src")"

    local hex
    hex="$(to_hex "$fname")"

    local name="${fname%.*}"
    ver="$(next_version "$name")"

    mkdir -p "$pool"
    tier="$(detect_tier "$pool")"
    tier_idx=$(( $(printf '%s' "$pool" | cksum | awk '{print $1}') % 3 ))
    color="$(tier_color "$tier" "$tier_idx")"

    local pkg_dir="$pool/$hex"
    mkdir -p "$pkg_dir"

    local stored="$pkg_dir/${ver}_${fname}"
    local sidecar="$pkg_dir/${hex}.sidecar.json"
    local qr_hdr="$pkg_dir/${hex}_header.png"
    local qr_ftr="$pkg_dir/${hex}_footer.png"
    local qr_sheet="$pkg_dir/${hex}_sheet.png"

    echo
    echo -e "${BOLD}  ── UnitedSys Intake ──${RESET}"
    echo

    # Copy into pool
    cp "$src" "$stored"
    chmod +x "$stored" 2>/dev/null || true
    info "File    : $fname → $stored"
    info "Hex     : $hex"
    info "State   : $state"
    info "Tier    : $tier  (#$color)"
    info "Version : $ver"

    # Sidecar
    info "Writing sidecar..."
    write_sidecar "$sidecar" \
        "$hex" "$fname" "$state" "$ver" "$size" "$desc" \
        "$pool" "$tier" "$color" "$qr_hdr" "$qr_ftr"

    # Header QR — state
    info "QR header (state)..."
    local colors fg bg
    colors="$(state_colors "$state")"
    fg="$(echo "$colors" | awk '{print $1}')"
    bg="$(echo "$colors" | awk '{print $2}')"
    gen_qr "{\"hex\":\"$hex\",\"state\":\"$state\",\"ver\":\"$ver\",\"sidecar\":\"$sidecar\"}" \
        "$qr_hdr" "$fg" "$bg"

    # Footer QR — location
    info "QR footer (location)..."
    gen_qr "{\"hex\":\"$hex\",\"pool\":\"$pool\",\"tier\":$tier,\"color\":\"#$color\",\"sidecar\":\"$sidecar\"}" \
        "$qr_ftr" "$color" "FFFFFF"

    # Composite sheet (imagemagick optional)
    if command -v convert &>/dev/null; then
        convert -append "$qr_hdr" "$qr_ftr" "$qr_sheet" 2>/dev/null && \
            ok "Sheet   : $qr_sheet" || true
    fi

    # Register in usys
    info "Registering in usys..."
    register_usys "$name" "$hex" "$src" "$state" "$pool" "$ver" "$size" "$sidecar"

    # Clone history
    append_history "$sidecar" "$ver" "$src"

    echo
    ok "Sidecar : $sidecar"
    ok "Header  : $qr_hdr"
    ok "Footer  : $qr_ftr"
    echo

    [[ "$state" == "grey" ]] && \
        echo -e "${YELLOW}  ⚠  Deprecated — will auto-hotswap when opportunity presents${RESET}" && echo
}

# ============================================================
#  DEPRECATE
# ============================================================

cmd_deprecate() {
    local name="${1:-}"
    [[ -z "$name" ]] && die "Usage: intake.sh deprecate <name>"
    [[ -f "$USYS_DB" ]] || die "usys not initialized"

    sqlite3 "$USYS_DB" <<SQL
UPDATE packages SET description='state=grey', updated=datetime('now') WHERE name='$name';
INSERT INTO swaplog (package, from_ver, to_ver, action, note)
VALUES ('$name',
    (SELECT current_ver FROM packages WHERE name='$name'),
    (SELECT current_ver FROM packages WHERE name='$name'),
    'deprecate', 'grey — queued for auto-hotswap');
SQL
    warn "'$name' marked grey — will hotswap when opportunity presents"
}

# ============================================================
#  HOTSWAP CHECK — scan grey files
# ============================================================

cmd_hotswap_check() {
    [[ -f "$USYS_DB" ]] || die "usys not initialized"
    info "Scanning for deprecated files..."

    local greys
    greys="$(sqlite3 "$USYS_DB" \
        "SELECT name FROM packages WHERE description LIKE 'state=grey%';" 2>/dev/null || true)"

    [[ -z "$greys" ]] && ok "None pending" && return

    while IFS= read -r pkg; do
        warn "Deprecated: $pkg — register replacement: usys swap $pkg <newfile>"
    done <<< "$greys"
}

# ============================================================
#  DISPATCH
# ============================================================

CMD="${1:-help}"
shift 2>/dev/null || true

case "$CMD" in
    deprecate)     cmd_deprecate "$@" ;;
    hotswap-check) cmd_hotswap_check ;;
    help|--help|-h)
        echo
        echo -e "${BOLD}  intake.sh v${INTAKE_VERSION} — UnitedSys clone pool intake${RESET}"
        echo
        echo "  intake.sh <file> <pool_path> [state] [description]"
        echo "  intake.sh deprecate <name>"
        echo "  intake.sh hotswap-check"
        echo
        echo "  States: white (good) | black (corrupt) | grey (deprecated)"
        echo
        echo "  Tier colors — bottom QR:"
        echo "    1: red  blue  yellow"
        echo "    2: green  orange  purple"
        echo "    3: cyan  magenta  lime"
        echo "    4: brown  pink  teal  navy"
        echo
        ;;
    *) cmd_intake "$CMD" "$@" ;;
esac
