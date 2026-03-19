#!/usr/bin/env bash
# ============================================================
#  UnitedSys  —  usys
#  Universal file registration, versioning, and hotswap
#
#  GPL v3 — use it, share it, build on it
#  https://github.com/jwl247/unitedsys
#
#  Standalone — no external scripts required
#  Core deps : bash + sqlite3
#  Clone pool: + qrencode + python3  (optional — auto-detected)
#
#  Commands:
#    usys init                        — first time setup
#    usys register <file> <name>      — register a file
#    usys call <name> [args...]       — call a registered file
#    usys swap <name> <newfile>       — hotswap to new version
#    usys rollback <name> [version]   — roll back to previous
#    usys list                        — list all registered
#    usys info <name>                 — show version history
#    usys remove <name>               — unregister
#    usys where <name>                — show file location
#    usys sync <name> <dest>          — sync to destination
#    usys clone <name> <dest>         — clone with full history
#    usys search <query>              — search registry
#    usys install <pkg> [--mgr]       — install via system pkg mgr + register
#    usys intake <file> <pool> [state] [desc]  — intake into clone pool
#    usys deprecate <name>            — mark grey, queue hotswap
#    usys hotswap-check               — scan deprecated files
#    usys version                     — show usys version
# ============================================================

set -euo pipefail

# ── Version ───────────────────────────────────────────────────
USYS_VERSION="0.3.0"

# ── Paths ─────────────────────────────────────────────────────
USYS_HOME="${USYS_HOME:-$HOME/.usys}"
USYS_DB="$USYS_HOME/usys.db"
USYS_BIN="$USYS_HOME/bin"
USYS_VERSIONS="$USYS_HOME/versions"
USYS_ROOT="/mnt/d/usys"
CLONEPOOL_ROOT="/mnt/d/clonepool"
POOL_ROOT="${POOL_ROOT:-/mnt/clonepool}"
USYS_LOG="$USYS_HOME/log"

# ── Colors ────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

# ── Helpers ───────────────────────────────────────────────────
info()  { echo -e "${CYAN}[usys]${RESET} $*"; }
ok()    { echo -e "${GREEN}[usys]${RESET} $*"; }
warn()  { echo -e "${YELLOW}[usys]${RESET} $*"; }
err()   { echo -e "${RED}[usys]${RESET} $*" >&2; }
die()   { err "$*"; exit 1; }

# ── Root warning ──────────────────────────────────────────────
check_sudo() {
    if [[ $EUID -eq 0 ]]; then
        echo -e "${YELLOW}"
        echo "  ⚠  WARNING: You are running usys as root."
        echo "     Packages will register to root's index,"
        echo "     not your user index. Most operations"
        echo "     do not require sudo."
        echo -e "${RESET}"
        if [[ -t 0 ]]; then
            read -rp "  Continue as root? [y/N] " confirm
            [[ "$confirm" =~ ^[Yy]$ ]] || exit 0
        fi
    fi
}

# ── Require sqlite3 ───────────────────────────────────────────
require_sqlite() {
    command -v sqlite3 &>/dev/null || \
        die "sqlite3 not found. Install it:\n  Ubuntu/Debian: sudo apt install sqlite3\n  Fedora: sudo dnf install sqlite\n  RHEL: sudo dnf install sqlite"
}

# ── DB query helpers ──────────────────────────────────────────
db() {
    sqlite3 "$USYS_DB" "$@"
}

db_exec() {
    sqlite3 "$USYS_DB" << SQL
$*
SQL
}

# ── Init DB schema ────────────────────────────────────────────
init_db() {
    db << 'SQL'
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS packages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    UNIQUE NOT NULL,
    current_ver TEXT    NOT NULL,
    source_path TEXT,
    bin_path    TEXT,
    filetype    TEXT,
    executable  INTEGER DEFAULT 1,
    registered  TEXT    DEFAULT (datetime('now')),
    updated     TEXT    DEFAULT (datetime('now')),
    tags        TEXT    DEFAULT '',
    description TEXT    DEFAULT ''
);

CREATE TABLE IF NOT EXISTS versions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    package     TEXT    NOT NULL,
    version     TEXT    NOT NULL,
    store_path  TEXT    NOT NULL,
    hash        TEXT    NOT NULL,
    size        INTEGER,
    created     TEXT    DEFAULT (datetime('now')),
    note        TEXT    DEFAULT '',
    FOREIGN KEY (package) REFERENCES packages(name) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS swaplog (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    package     TEXT    NOT NULL,
    from_ver    TEXT,
    to_ver      TEXT,
    action      TEXT    NOT NULL,
    ts          TEXT    DEFAULT (datetime('now')),
    note        TEXT    DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_versions_package ON versions(package);
CREATE INDEX IF NOT EXISTS idx_swaplog_package  ON swaplog(package);
SQL
}

# ── Generate version string ───────────────────────────────────
next_version() {
    local name="$1"
    local count
    count=$(db "SELECT COUNT(*) FROM versions WHERE package='$name';")
    echo "v$((count + 1))"
}

# ── File hash ─────────────────────────────────────────────────
file_hash() {
    sha256sum "$1" | awk '{print $1}'
}

# ── Detect filetype ───────────────────────────────────────────
detect_type() {
    local file="$1"
    local ext="${file##*.}"
    local shebang
    shebang=$(head -c 50 "$file" 2>/dev/null | grep -oE '^#![^\n]+' || echo "")

    if [[ -n "$shebang" ]]; then
        echo "$shebang" | grep -qE 'python' && echo "python" && return
        echo "$shebang" | grep -qE 'bash|sh'   && echo "shell"  && return
        echo "$shebang" | grep -qE 'node'   && echo "node"   && return
        echo "$shebang" | grep -qE 'ruby'   && echo "ruby"   && return
        echo "$shebang" | grep -qE 'perl'   && echo "perl"   && return
    fi

    case "$ext" in
        py|pyw)         echo "python" ;;
        sh|bash|zsh)    echo "shell"  ;;
        js|mjs)         echo "node"   ;;
        rb)             echo "ruby"   ;;
        pl)             echo "perl"   ;;
        php)            echo "php"    ;;
        go)             echo "go"     ;;
        *)
            file "$file" 2>/dev/null | grep -qi "executable" && echo "binary" || echo "file"
            ;;
    esac
}

# ── Create callable wrapper in ~/.usys/bin ────────────────────
make_callable() {
    local name="$1"
    local store_path="$2"
    local filetype="$3"
    local wrapper="$USYS_BIN/$name"

    cat > "$wrapper" << WRAPPER
#!/usr/bin/env bash
# UnitedSys callable wrapper — $name
# Auto-generated by usys — do not edit manually
# Edit via: usys swap $name <newfile>

USYS_TARGET=\$(sqlite3 "\$HOME/.usys/usys.db" \
    "SELECT v.store_path FROM packages p \
     JOIN versions v ON v.package=p.name AND v.version=p.current_ver \
     WHERE p.name='$name' LIMIT 1;" 2>/dev/null)

[[ -z "\$USYS_TARGET" ]] && {
    echo "[usys] ERROR: '$name' not found in registry" >&2
    exit 1
}

[[ -x "\$USYS_TARGET" ]] || chmod +x "\$USYS_TARGET" 2>/dev/null || true

exec "\$USYS_TARGET" "\$@"
WRAPPER

    chmod +x "$wrapper"
}
# ── Kernel wrapper generator ──────────────────────────────────
make_kernel_wrapper() {
    ...
}

# ── Jupyter kernel.json installer ─────────────────────────────
install_kernel_json() {
    ...
}
status() {
    echo "UnitedSys Status"
    echo "----------------"
    echo "USYS_ROOT:        $USYS_ROOT"
    echo "CLONEPOOL_ROOT:   $CLONEPOOL_ROOT"
    echo

    echo "Paths:"
    [ -d "$USYS_ROOT" ] && echo "  ✔ $USYS_ROOT exists" || echo "  ✘ $USYS_ROOT missing"
    [ -d "$CLONEPOOL_ROOT" ] && echo "  ✔ $CLONEPOOL_ROOT exists" || echo "  ✘ $CLONEPOOL_ROOT missing"
    [ -f "$USYS_ROOT/registry/registry.json" ] && echo "  ✔ registry.json present" || echo "  ✘ registry.json missing"
    echo

    echo "Dispatcher:"
    which_usys=$(which usys)
    echo "  Using: $which_usys"
    if [ "$which_usys" = "/usr/local/bin/usys" ]; then
        echo "  ✔ Global dispatcher active"
    else
        echo "  ✘ Not using global dispatcher"
    fi
    echo

    echo "Working Directory:"
    echo "  $(pwd)"
    echo

    echo "Status complete."
}


# ============================================================
#  INTAKE PIPELINE — clone pool, QR codes, sidecars
#  Deps: qrencode + python3  (auto-checked before use)
# ============================================================

# ── Require intake deps ───────────────────────────────────────
require_intake_deps() {
    command -v qrencode &>/dev/null || \
        die "qrencode not found — apt install qrencode"
    command -v python3  &>/dev/null || \
        die "python3 not found"
}

# ── Check intake deps silently (returns 0/1) ─────────────────
have_intake_deps() {
    command -v qrencode &>/dev/null && command -v python3 &>/dev/null
}

# ── Filename → hex ───────────────────────────────────────────
to_hex() {
    printf '%s' "$1" | xxd -p | tr -d '\n'
}

# ── Clone pool depth → tier (1-4) ────────────────────────────
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

# ── Tier + index → location color ────────────────────────────
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

# ── State → QR fg/bg colors ──────────────────────────────────
state_colors() {
    case "$1" in
        white) echo "000000 FFFFFF" ;;
        black) echo "FFFFFF 000000" ;;
        grey)  echo "444444 AAAAAA" ;;
        *)     echo "000000 FFFFFF" ;;
    esac
}

# ── Generate QR PNG ──────────────────────────────────────────
gen_qr() {
    local content="$1" out="$2" fg="$3" bg="$4"
    qrencode \
        --foreground="$fg" \
        --background="$bg" \
        --size=6 --margin=2 --level=M \
        --type=PNG --output="$out" \
        "$content"
}

# ── Sidecar JSON ─────────────────────────────────────────────
write_sidecar() {
    local out="$1"
    python3 - <<PYEOF
import json, time

s = {
    "usys_intake":    "1.0",
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

# ── Append to clone history in sidecar ───────────────────────
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

# ── Register/update pool entry in usys DB ────────────────────
_pool_register() {
    local name="$1" hex="$2" src="$3" state="$4"
    local pool="$5" ver="$6" size="$7" sidecar="$8"

    local exists
    exists=$(db "SELECT COUNT(*) FROM packages WHERE name='$name';")

    if [[ "$exists" -gt 0 ]]; then
        db << SQL
INSERT INTO versions (package, version, store_path, hash, size, note)
VALUES ('$name', '$ver', '$pool/$hex', '', $size, 'intake state=$state');

UPDATE packages
SET current_ver='$ver', source_path='$src',
    updated=datetime('now'),
    tags='sidecar=$sidecar',
    description='state=$state'
WHERE name='$name';

INSERT INTO swaplog (package, from_ver, to_ver, action, note)
VALUES ('$name',
    (SELECT current_ver FROM packages WHERE name='$name'),
    '$ver', 'intake', 'state=$state');
SQL
    else
        db << SQL
INSERT INTO packages (name, current_ver, source_path, bin_path, filetype, tags, description)
VALUES ('$name', '$ver', '$src', '$USYS_BIN/$name', 'intake', 'sidecar=$sidecar', 'state=$state');

INSERT INTO versions (package, version, store_path, hash, size, note)
VALUES ('$name', '$ver', '$pool/$hex', '', $size, 'intake: initial');

INSERT INTO swaplog (package, from_ver, to_ver, action, note)
VALUES ('$name', NULL, '$ver', 'intake', 'initial state=$state');
SQL
    fi
}

# ── Internal intake pipeline (used by register/install) ──────
_run_intake() {
    local src="${1:-}" pool="${2:-}" state="${3:-white}" desc="${4:-}"

    [[ -z "$src"  ]] && return 1
    [[ -z "$pool" ]] && return 1
    [[ -f "$src"  ]] || return 1

    src="$(realpath "$src")"

    local fname size tier tier_idx color ver hex name
    fname="$(basename "$src")"
    size="$(wc -c < "$src")"
    hex="$(to_hex "$fname")"
    name="${fname%.*}"
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

    cp "$src" "$stored"
    chmod +x "$stored" 2>/dev/null || true

    write_sidecar "$sidecar" \
        "$hex" "$fname" "$state" "$ver" "$size" "$desc" \
        "$pool" "$tier" "$color" "$qr_hdr" "$qr_ftr"

    local colors fg bg
    colors="$(state_colors "$state")"
    fg="$(echo "$colors" | awk '{print $1}')"
    bg="$(echo "$colors" | awk '{print $2}')"

    gen_qr "{\"hex\":\"$hex\",\"state\":\"$state\",\"ver\":\"$ver\",\"sidecar\":\"$sidecar\"}" \
        "$qr_hdr" "$fg" "$bg"
    gen_qr "{\"hex\":\"$hex\",\"pool\":\"$pool\",\"tier\":$tier,\"color\":\"#$color\",\"sidecar\":\"$sidecar\"}" \
        "$qr_ftr" "$color" "FFFFFF"

    if command -v convert &>/dev/null; then
        convert -append "$qr_hdr" "$qr_ftr" "$qr_sheet" 2>/dev/null || true
    fi

    _pool_register "$name" "$hex" "$src" "$state" "$pool" "$ver" "$size" "$sidecar"
    append_history "$sidecar" "$ver" "$src"
}


# ============================================================
#  COMMANDS
# ============================================================

# ── usys init ────────────────────────────────────────────────
cmd_init() {
    echo -e "${BOLD}"
    echo "  ██╗   ██╗███████╗██╗   ██╗███████╗"
    echo "  ██║   ██║██╔════╝╚██╗ ██╔╝██╔════╝"
    echo "  ██║   ██║███████╗ ╚████╔╝ ███████╗"
    echo "  ██║   ██║╚════██║  ╚██╔╝  ╚════██║"
    echo "  ╚██████╔╝███████║   ██║   ███████║"
    echo "   ╚═════╝ ╚══════╝   ╚═╝   ╚══════╝"
    echo "  UnitedSys v${USYS_VERSION} — universal hotswap registry"
    echo -e "${RESET}"

    require_sqlite

    mkdir -p "$USYS_HOME" "$USYS_BIN" "$USYS_VERSIONS" "$USYS_LOG"
    init_db
    ok "Database initialized: $USYS_DB"

    local shell_rc=""
    if [[ -f "$HOME/.bashrc" ]];  then shell_rc="$HOME/.bashrc"; fi
    if [[ -f "$HOME/.zshrc" ]];   then shell_rc="$HOME/.zshrc";  fi

    local path_line="export PATH=\"\$HOME/.usys/bin:\$PATH\""

    if [[ -n "$shell_rc" ]]; then
        if ! grep -q "\.usys/bin" "$shell_rc" 2>/dev/null; then
            echo "" >> "$shell_rc"
            echo "# UnitedSys" >> "$shell_rc"
            echo "$path_line"  >> "$shell_rc"
            ok "Added ~/.usys/bin to PATH in $shell_rc"
        else
            info "PATH already configured in $shell_rc"
        fi
    fi

    cp "$0" "$USYS_HOME/usys.sh" 2>/dev/null || true
    chmod +x "$USYS_HOME/usys.sh"

    ln -sf "$USYS_HOME/usys.sh" "$USYS_BIN/usys" 2>/dev/null || \
        cp "$USYS_HOME/usys.sh" "$USYS_BIN/usys"
    chmod +x "$USYS_BIN/usys"

    echo
    ok "UnitedSys ready."
    echo
    info "Run:  source ~/.bashrc   (or open a new terminal)"
    info "Then: usys register <file> <name>"
    echo
}

# ── usys register <file> <name> [description] ────────────────
cmd_register() {
    local src="${1:-}"
    local name="${2:-}"
    local desc="${3:-}"

    [[ -z "$src"  ]] && die "Usage: usys register <file> <name>"
    [[ -z "$name" ]] && die "Usage: usys register <file> <name>"
    [[ -f "$src"  ]] || die "File not found: $src"

    require_sqlite
    init_db 2>/dev/null || true

    src="$(realpath "$src")"

    local filetype version hash size store_path

    filetype=$(detect_type "$src")
    version=$(next_version "$name")
    hash=$(file_hash "$src")
    size=$(wc -c < "$src")

    local pkg_ver_dir="$USYS_VERSIONS/$name"
    mkdir -p "$pkg_ver_dir"
    store_path="$pkg_ver_dir/${version}_$(basename "$src")"
    cp "$src" "$store_path"
    chmod +x "$store_path" 2>/dev/null || true

    local exists
    exists=$(db "SELECT COUNT(*) FROM packages WHERE name='$name';")

    if [[ "$exists" -gt 0 ]]; then
        warn "'$name' already registered — use 'usys swap $name $src' to update"
        return 1
    fi

    db << SQL
INSERT INTO packages (name, current_ver, source_path, bin_path, filetype, description)
VALUES ('$name', '$version', '$src', '$USYS_BIN/$name', '$filetype', '$desc');

INSERT INTO versions (package, version, store_path, hash, size)
VALUES ('$name', '$version', '$store_path', '$hash', $size);

INSERT INTO swaplog (package, from_ver, to_ver, action, note)
VALUES ('$name', NULL, '$version', 'register', 'initial registration');
SQL

    make_callable "$name" "$store_path" "$filetype"

    # Auto-intake into clone pool (silent, skipped if deps absent)
    if have_intake_deps; then
        local pool_path="$POOL_ROOT/$(basename "$(dirname "$src")")"
        _run_intake "$src" "$pool_path" "white" "$desc" > /dev/null 2>&1 || true
    fi

    echo
    ok "Registered: ${BOLD}$name${RESET}"
    info "  Version  : $version"
    info "  Type     : $filetype"
    info "  Source   : $src"
    info "  Callable : usys call $name"
    info "  Direct   : $name  (once PATH is set)"
    echo
}

# ── usys call <name> [args...] ────────────────────────────────
cmd_call() {
    local name="${1:-}"
    [[ -z "$name" ]] && die "Usage: usys call <name> [args...]"
    shift || true

    require_sqlite

    local store_path
    store_path=$(db "
        SELECT v.store_path
        FROM packages p
        JOIN versions v ON v.package=p.name AND v.version=p.current_ver
        WHERE p.name='$name'
        LIMIT 1;
    ")

    [[ -z "$store_path" ]] && die "'$name' not found in registry. Run: usys list"
    [[ -f "$store_path" ]] || die "Stored file missing: $store_path"

    chmod +x "$store_path" 2>/dev/null || true
    exec "$store_path" "$@"
}

# ── usys swap <name> <newfile> [note] ─────────────────────────
cmd_swap() {
    local name="${1:-}"
    local src="${2:-}"
    local note="${3:-manual swap}"

    [[ -z "$name" ]] && die "Usage: usys swap <name> <newfile>"
    [[ -z "$src"  ]] && die "Usage: usys swap <name> <newfile>"
    [[ -f "$src"  ]] || die "File not found: $src"

    require_sqlite

    local exists
    exists=$(db "SELECT COUNT(*) FROM packages WHERE name='$name';")
    [[ "$exists" -eq 0 ]] && die "'$name' not registered. Run: usys register $src $name"

    src="$(realpath "$src")"

    local old_ver filetype version hash size store_path

    old_ver=$(db "SELECT current_ver FROM packages WHERE name='$name';")
    filetype=$(detect_type "$src")
    version=$(next_version "$name")
    hash=$(file_hash "$src")
    size=$(wc -c < "$src")

    local pkg_ver_dir="$USYS_VERSIONS/$name"
    mkdir -p "$pkg_ver_dir"
    store_path="$pkg_ver_dir/${version}_$(basename "$src")"
    cp "$src" "$store_path"
    chmod +x "$store_path" 2>/dev/null || true

    db << SQL
INSERT INTO versions (package, version, store_path, hash, size, note)
VALUES ('$name', '$version', '$store_path', '$hash', $size, '$note');

UPDATE packages
SET current_ver='$version',
    source_path='$src',
    filetype='$filetype',
    updated=datetime('now')
WHERE name='$name';

INSERT INTO swaplog (package, from_ver, to_ver, action, note)
VALUES ('$name', '$old_ver', '$version', 'swap', '$note');
SQL

    make_callable "$name" "$store_path" "$filetype"

    echo
    ok "Hotswapped: ${BOLD}$name${RESET}"
    info "  $old_ver  →  $version"
    info "  Source : $src"
    info "  Note   : $note"
    echo
    ok "Live. No restart needed."
    echo
}

# ── usys rollback <name> [version] ───────────────────────────
cmd_rollback() {
    local name="${1:-}"
    local target_ver="${2:-}"

    [[ -z "$name" ]] && die "Usage: usys rollback <name> [version]"

    require_sqlite

    local exists
    exists=$(db "SELECT COUNT(*) FROM packages WHERE name='$name';")
    [[ "$exists" -eq 0 ]] && die "'$name' not registered"

    local current_ver
    current_ver=$(db "SELECT current_ver FROM packages WHERE name='$name';")

    if [[ -z "$target_ver" ]]; then
        target_ver=$(db "
            SELECT version FROM versions
            WHERE package='$name' AND version != '$current_ver'
            ORDER BY id DESC LIMIT 1;
        ")
        [[ -z "$target_ver" ]] && die "No previous version to roll back to"
    fi

    local store_path
    store_path=$(db "
        SELECT store_path FROM versions
        WHERE package='$name' AND version='$target_ver'
        LIMIT 1;
    ")

    [[ -z "$store_path" ]] && die "Version '$target_ver' not found for '$name'"
    [[ -f "$store_path" ]] || die "Stored file missing: $store_path"

    db << SQL
UPDATE packages
SET current_ver='$target_ver', updated=datetime('now')
WHERE name='$name';

INSERT INTO swaplog (package, from_ver, to_ver, action, note)
VALUES ('$name', '$current_ver', '$target_ver', 'rollback', 'manual rollback');
SQL

    make_callable "$name" "$store_path" ""

    echo
    ok "Rolled back: ${BOLD}$name${RESET}"
    info "  $current_ver  →  $target_ver"
    echo
    ok "Live. No restart needed."
    echo
}

# ── usys list ────────────────────────────────────────────────
cmd_list() {
    require_sqlite

    local count
    count=$(db "SELECT COUNT(*) FROM packages;")

    echo
    echo -e "${BOLD}  UnitedSys Registry  —  $count package(s)${RESET}"
    echo "  ─────────────────────────────────────────────────"
    printf "  %-20s %-8s %-10s  %s\n" "NAME" "VERSION" "TYPE" "UPDATED"
    echo "  ─────────────────────────────────────────────────"

    db -separator "|" \
       "SELECT name, current_ver, filetype, updated FROM packages ORDER BY name;" \
    | while IFS="|" read -r name ver ftype updated; do
        printf "  ${GREEN}%-20s${RESET} %-8s %-10s  %s\n" \
            "$name" "$ver" "$ftype" "$updated"
    done

    echo "  ─────────────────────────────────────────────────"
    echo
}

# ── usys info <name> ─────────────────────────────────────────
cmd_info() {
    local name="${1:-}"
    [[ -z "$name" ]] && die "Usage: usys info <name>"

    require_sqlite

    local exists
    exists=$(db "SELECT COUNT(*) FROM packages WHERE name='$name';")
    [[ "$exists" -eq 0 ]] && die "'$name' not in registry"

    echo
    echo -e "${BOLD}  $name${RESET}"
    echo "  ─────────────────────────────────────────────"

    db -separator "|" \
       "SELECT current_ver, filetype, source_path, registered, updated, description
        FROM packages WHERE name='$name';" \
    | while IFS="|" read -r ver ftype src reg upd desc; do
        echo -e "  ${CYAN}Current version${RESET}  : $ver"
        echo -e "  ${CYAN}Type${RESET}             : $ftype"
        echo -e "  ${CYAN}Original source${RESET}  : $src"
        echo -e "  ${CYAN}Registered${RESET}       : $reg"
        echo -e "  ${CYAN}Last updated${RESET}     : $upd"
        [[ -n "$desc" ]] && echo -e "  ${CYAN}Description${RESET}      : $desc"
    done

    echo
    echo -e "  ${BOLD}Version history:${RESET}"
    echo "  ─────────────────────────────────────────────"
    printf "  %-8s  %-12s  %-8s  %s\n" "VERSION" "CREATED" "SIZE" "HASH"
    echo "  ─────────────────────────────────────────────"

    db -separator "|" \
       "SELECT version, created, size, hash, note
        FROM versions WHERE package='$name' ORDER BY id DESC;" \
    | while IFS="|" read -r ver created size hash note; do
        local current
        current=$(db "SELECT current_ver FROM packages WHERE name='$name';")
        local marker=""
        [[ "$ver" == "$current" ]] && marker="${GREEN} ◄ current${RESET}"
        printf "  %-8s  %-12s  %-8s  %s\n" \
            "$ver" "${created:0:10}" "${size}b" "${hash:0:12}..."
        echo -e "           ${marker}${note:+  note: $note}"
    done

    echo
    echo -e "  ${BOLD}Swap log:${RESET}"
    echo "  ─────────────────────────────────────────────"

    db -separator "|" \
       "SELECT ts, action, from_ver, to_ver, note
        FROM swaplog WHERE package='$name' ORDER BY id DESC LIMIT 10;" \
    | while IFS="|" read -r ts action from to note; do
        printf "  %-12s  %-10s  %s → %s\n" \
            "${ts:0:10}" "$action" "${from:----}" "${to:----}"
    done

    echo
}

# ── usys remove <name> ───────────────────────────────────────
cmd_remove() {
    local name="${1:-}"
    [[ -z "$name" ]] && die "Usage: usys remove <name>"

    require_sqlite

    local exists
    exists=$(db "SELECT COUNT(*) FROM packages WHERE name='$name';")
    [[ "$exists" -eq 0 ]] && die "'$name' not in registry"

    echo
    warn "This will remove '$name' from the registry."
    warn "Stored versions in $USYS_VERSIONS/$name will be kept."
    read -rp "  Continue? [y/N] " confirm
    [[ "$confirm" =~ ^[Yy]$ ]] || { info "Cancelled."; exit 0; }

    db "DELETE FROM packages WHERE name='$name';"
    rm -f "$USYS_BIN/$name"

    ok "Removed: $name"
    info "Version history kept at: $USYS_VERSIONS/$name"
    echo
}

# ── usys where <name> ────────────────────────────────────────
cmd_where() {
    local name="${1:-}"
    [[ -z "$name" ]] && die "Usage: usys where <name>"

    require_sqlite

    local store_path source_path
    store_path=$(db "
        SELECT v.store_path
        FROM packages p
        JOIN versions v ON v.package=p.name AND v.version=p.current_ver
        WHERE p.name='$name' LIMIT 1;
    ")
    source_path=$(db "SELECT source_path FROM packages WHERE name='$name';")

    [[ -z "$store_path" ]] && die "'$name' not in registry"

    echo
    info "  Name          : $name"
    info "  Callable      : $USYS_BIN/$name"
    info "  Stored version: $store_path"
    info "  Original source: $source_path"
    echo
}

# ── usys sync <name> <dest> ───────────────────────────────────
cmd_sync() {
    local name="${1:-}"
    local dest="${2:-}"

    [[ -z "$name" ]] && die "Usage: usys sync <name> <dest>"
    [[ -z "$dest" ]] && die "Usage: usys sync <name> <dest>"

    require_sqlite

    local store_path
    store_path=$(db "
        SELECT v.store_path
        FROM packages p
        JOIN versions v ON v.package=p.name AND v.version=p.current_ver
        WHERE p.name='$name' LIMIT 1;
    ")

    [[ -z "$store_path" ]] && die "'$name' not in registry"

    mkdir -p "$(dirname "$dest")"
    rsync -av "$store_path" "$dest" 2>/dev/null || \
        cp -v "$store_path" "$dest"

    ok "Synced: $name → $dest"
}
# ── usys install-kernel <name> ────────────────────────────────
cmd_install_kernel() {
    ...
}

# ── usys clone <name> <dest> ──────────────────────────────────
cmd_clone() {
    local name="${1:-}"
    local dest="${2:-}"

    [[ -z "$name" ]] && die "Usage: usys clone <name> <dest>"
    [[ -z "$dest" ]] && die "Usage: usys clone <name> <dest>"

    require_sqlite

    local exists
    exists=$(db "SELECT COUNT(*) FROM packages WHERE name='$name';")
    [[ "$exists" -eq 0 ]] && die "'$name' not in registry"

    local src_dir="$USYS_VERSIONS/$name"
    local dest_dir="$dest/$name"

    mkdir -p "$dest_dir"
    cp -r "$src_dir/." "$dest_dir/"

    db << SQL > "$dest_dir/usys_export.sql"
SELECT '-- UnitedSys export: $name';
SELECT '-- Generated: ' || datetime('now');
SELECT '-- usys import to restore';
SQL

    db -separator "|" \
       "SELECT * FROM packages WHERE name='$name';" \
       >> "$dest_dir/usys_export.sql"

    db -separator "|" \
       "SELECT * FROM versions WHERE package='$name';" \
       >> "$dest_dir/usys_export.sql"

    ok "Cloned: $name → $dest_dir"
    info "Full version history included"
    info "To restore: usys import $dest_dir/usys_export.sql"
}

# ── usys search <query> ───────────────────────────────────────
cmd_search() {
    local query="${1:-}"
    [[ -z "$query" ]] && die "Usage: usys search <query>"

    require_sqlite

    echo
    echo -e "${BOLD}  Search results for: $query${RESET}"
    echo "  ────────────────────────────────────────────"

    db -separator "|" \
       "SELECT name, current_ver, filetype, description
        FROM packages
        WHERE name LIKE '%$query%'
           OR description LIKE '%$query%'
           OR filetype LIKE '%$query%'
        ORDER BY name;" \
    | while IFS="|" read -r name ver ftype desc; do
        printf "  ${GREEN}%-20s${RESET} %-8s %-10s  %s\n" \
            "$name" "$ver" "$ftype" "$desc"
    done

    echo
}

# ── usys install <package> [--pip|--npm|--cargo|--apt|...] ───
cmd_install() {
    local pkg="${1:-}"
    local force_mgr="${2:-}"

    [[ -z "$pkg" ]] && die "Usage: usys install <package> [--apt|--pip|--npm|--cargo|--pacman|--dnf]"

    require_sqlite
    init_db 2>/dev/null || true

    local mgr=""

    if [[ -n "$force_mgr" ]]; then
        mgr="${force_mgr/--/}"
    else
        if   command -v apt-get  &>/dev/null; then mgr="apt"
        elif command -v pacman   &>/dev/null; then mgr="pacman"
        elif command -v dnf      &>/dev/null; then mgr="dnf"
        elif command -v yum      &>/dev/null; then mgr="yum"
        elif command -v brew     &>/dev/null; then mgr="brew"
        elif command -v pip3     &>/dev/null; then mgr="pip"
        elif command -v pip      &>/dev/null; then mgr="pip"
        elif command -v npm      &>/dev/null; then mgr="npm"
        elif command -v cargo    &>/dev/null; then mgr="cargo"
        else
            die "No supported package manager found. Install one of: apt, pacman, dnf, brew, pip, npm, cargo"
        fi
    fi

    info "Package manager : $mgr"
    info "Installing      : $pkg"
    echo

    case "$mgr" in
        apt)    sudo apt-get install -y "$pkg" || die "apt install failed: $pkg" ;;
        pacman) sudo pacman -S --noconfirm "$pkg" || die "pacman install failed: $pkg" ;;
        dnf)    sudo dnf install -y "$pkg" || die "dnf install failed: $pkg" ;;
        yum)    sudo yum install -y "$pkg" || die "yum install failed: $pkg" ;;
        brew)   brew install "$pkg" || die "brew install failed: $pkg" ;;
        pip)
            local pip_bin
            pip_bin=$(command -v pip3 || command -v pip)
            "$pip_bin" install --user "$pkg" || die "pip install failed: $pkg"
            ;;
        npm)    npm install -g "$pkg" || die "npm install failed: $pkg" ;;
        cargo)  cargo install "$pkg" || die "cargo install failed: $pkg" ;;
        *)      die "Unknown package manager: $mgr" ;;
    esac

    echo
    ok "Installed: $pkg  (via $mgr)"

    local bin_path=""
    bin_path=$(command -v "$pkg" 2>/dev/null || true)

    if [[ -z "$bin_path" ]]; then
        local candidates=(
            "$HOME/.local/bin/$pkg"
            "$HOME/.cargo/bin/$pkg"
            "$(npm bin -g 2>/dev/null)/$pkg"
            "/usr/bin/$pkg"
            "/usr/local/bin/$pkg"
        )
        for c in "${candidates[@]}"; do
            [[ -f "$c" ]] && { bin_path="$c"; break; }
        done
    fi

    if [[ -n "$bin_path" ]]; then
        local exists
        exists=$(db "SELECT COUNT(*) FROM packages WHERE name='$pkg';")

        if [[ "$exists" -gt 0 ]]; then
            local old_ver version hash size store_path
            old_ver=$(db "SELECT current_ver FROM packages WHERE name='$pkg';")
            version=$(next_version "$pkg")
            hash=$(file_hash "$bin_path")
            size=$(wc -c < "$bin_path")
            local pkg_ver_dir="$USYS_VERSIONS/$pkg"
            mkdir -p "$pkg_ver_dir"
            store_path="$pkg_ver_dir/${version}_$pkg"
            cp "$bin_path" "$store_path"
            chmod +x "$store_path"

            db << SQL
INSERT INTO versions (package, version, store_path, hash, size, note)
VALUES ('$pkg', '$version', '$store_path', '$hash', $size, 'install via $mgr');

UPDATE packages
SET current_ver='$version', source_path='$bin_path', updated=datetime('now')
WHERE name='$pkg';

INSERT INTO swaplog (package, from_ver, to_ver, action, note)
VALUES ('$pkg', '$old_ver', '$version', 'install', 'reinstalled via $mgr');
SQL
            make_callable "$pkg" "$store_path" "binary"
            ok "Updated registry: $pkg  ($old_ver → $version)"
        else
            local version hash size store_path filetype
            version=$(next_version "$pkg")
            hash=$(file_hash "$bin_path")
            size=$(wc -c < "$bin_path")
            filetype=$(detect_type "$bin_path")
            local pkg_ver_dir="$USYS_VERSIONS/$pkg"
            mkdir -p "$pkg_ver_dir"
            store_path="$pkg_ver_dir/${version}_$pkg"
            cp "$bin_path" "$store_path"
            chmod +x "$store_path"

            db << SQL
INSERT INTO packages (name, current_ver, source_path, bin_path, filetype, description)
VALUES ('$pkg', '$version', '$bin_path', '$USYS_BIN/$pkg', '$filetype', 'installed via $mgr');

INSERT INTO versions (package, version, store_path, hash, size, note)
VALUES ('$pkg', '$version', '$store_path', '$hash', $size, 'install via $mgr');

INSERT INTO swaplog (package, from_ver, to_ver, action, note)
VALUES ('$pkg', NULL, '$version', 'install', 'initial install via $mgr');
SQL
            make_callable "$pkg" "$store_path" "$filetype"
            ok "Registered : $pkg  ($version)"
            info "Callable   : usys call $pkg  or just: $pkg"
        fi

        # Silent auto-intake into clone pool
        if have_intake_deps; then
            _run_intake "$bin_path" "$POOL_ROOT/system" "white" \
                "installed via $mgr" > /dev/null 2>&1 || true
        fi
    else
        warn "Binary not found in PATH after install — skipping usys registration"
        warn "If it installed to a custom location, register manually:"
        warn "  usys register <path-to-binary> $pkg"
    fi

    echo
}

# ── usys intake <file> <pool_path> [state] [desc] ────────────
cmd_intake() {
    local src="${1:-}" pool="${2:-}" state="${3:-white}" desc="${4:-}"

    [[ -z "$src"  ]] && die "Usage: usys intake <file> <pool_path> [state] [description]"
    [[ -z "$pool" ]] && die "Usage: usys intake <file> <pool_path> [state] [description]"
    [[ -f "$src"  ]] || die "File not found: $src"
    [[ "$state" == "white" || "$state" == "black" || "$state" == "grey" ]] || \
        die "State must be: white | black | grey"

    require_sqlite
    require_intake_deps

    src="$(realpath "$src")"

    local fname size tier tier_idx color ver hex name
    fname="$(basename "$src")"
    size="$(wc -c < "$src")"
    hex="$(to_hex "$fname")"
    name="${fname%.*}"
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

    cp "$src" "$stored"
    chmod +x "$stored" 2>/dev/null || true
    info "File    : $fname → $stored"
    info "Hex     : $hex"
    info "State   : $state"
    info "Tier    : $tier  (#$color)"
    info "Version : $ver"

    info "Writing sidecar..."
    write_sidecar "$sidecar" \
        "$hex" "$fname" "$state" "$ver" "$size" "$desc" \
        "$pool" "$tier" "$color" "$qr_hdr" "$qr_ftr"

    info "QR header (state)..."
    local colors fg bg
    colors="$(state_colors "$state")"
    fg="$(echo "$colors" | awk '{print $1}')"
    bg="$(echo "$colors" | awk '{print $2}')"
    gen_qr "{\"hex\":\"$hex\",\"state\":\"$state\",\"ver\":\"$ver\",\"sidecar\":\"$sidecar\"}" \
        "$qr_hdr" "$fg" "$bg"

    info "QR footer (location)..."
    gen_qr "{\"hex\":\"$hex\",\"pool\":\"$pool\",\"tier\":$tier,\"color\":\"#$color\",\"sidecar\":\"$sidecar\"}" \
        "$qr_ftr" "$color" "FFFFFF"

    if command -v convert &>/dev/null; then
        convert -append "$qr_hdr" "$qr_ftr" "$qr_sheet" 2>/dev/null && \
            ok "Sheet   : $qr_sheet" || true
    fi

    info "Registering in usys..."
    _pool_register "$name" "$hex" "$src" "$state" "$pool" "$ver" "$size" "$sidecar"
    append_history "$sidecar" "$ver" "$src"

    echo
    ok "Sidecar : $sidecar"
    ok "Header  : $qr_hdr"
    ok "Footer  : $qr_ftr"
    echo

    [[ "$state" == "grey" ]] && \
        echo -e "${YELLOW}  ⚠  Deprecated — will auto-hotswap when opportunity presents${RESET}" && echo
}
status)
    status
    ;;
# ── usys deprecate <name> ────────────────────────────────────
cmd_deprecate() {
    local name="${1:-}"
    [[ -z "$name" ]] && die "Usage: usys deprecate <name>"

    require_sqlite

    local exists
    exists=$(db "SELECT COUNT(*) FROM packages WHERE name='$name';")
    [[ "$exists" -eq 0 ]] && die "'$name' not in registry"

    db << SQL
UPDATE packages SET description='state=grey', updated=datetime('now') WHERE name='$name';
INSERT INTO swaplog (package, from_ver, to_ver, action, note)
VALUES ('$name',
    (SELECT current_ver FROM packages WHERE name='$name'),
    (SELECT current_ver FROM packages WHERE name='$name'),
    'deprecate', 'grey — queued for auto-hotswap');
SQL
    warn "'$name' marked grey — will hotswap when opportunity presents"
}

# ── usys hotswap-check ────────────────────────────────────────
cmd_hotswap_check() {
    require_sqlite
    info "Scanning for deprecated files..."

    local greys
    greys="$(db "SELECT name FROM packages WHERE description LIKE 'state=grey%';" 2>/dev/null || true)"

    [[ -z "$greys" ]] && ok "None pending" && return

    while IFS= read -r pkg; do
        warn "Deprecated: $pkg — register replacement: usys swap $pkg <newfile>"
    done <<< "$greys"
}
install-kernel) cmd_install_kernel "$@" ;;

# ── usys version ─────────────────────────────────────────────
cmd_version() {
    echo "usys $USYS_VERSION — UnitedSys universal hotswap registry"
    echo "GPL v3 — https://github.com/jwl247/unitedsys"
}


# ============================================================
#  DISPATCH
# ============================================================

CMD="${1:-}"
shift 2>/dev/null || true

case "$CMD" in
  
    init)          cmd_init ;;
    register)      check_sudo; cmd_register "$@" ;;
    call)          cmd_call "$@" ;;
    swap)          check_sudo; cmd_swap "$@" ;;
    rollback)      check_sudo; cmd_rollback "$@" ;;
    list|ls)       cmd_list ;;
    info)          cmd_info "$@" ;;
    remove|rm)     check_sudo; cmd_remove "$@" ;;
    where)         cmd_where "$@" ;;
    sync)          cmd_sync "$@" ;;
    clone)         cmd_clone "$@" ;;
    search)        cmd_search "$@" ;;
    version|-v)    cmd_version ;;
    install)       check_sudo; cmd_install "$@" ;;
    intake)        check_sudo; cmd_intake "$@" ;;
    deprecate)     check_sudo; cmd_deprecate "$@" ;;
    hotswap-check) cmd_hotswap_check ;;

    ""|help|--help|-h)
        echo
        echo -e "${BOLD}  UnitedSys (usys) v${USYS_VERSION}${RESET}"
        echo -e "  Universal file registration, versioning, and hotswap"
        echo
        echo -e "  ${CYAN}Usage:${RESET}"
        echo "    usys init                         first time setup"
        echo "    usys register <file> <name>       register a file"
        echo "    usys call <name> [args...]         call by name"
        echo "    usys swap <name> <newfile>         hotswap live"
        echo "    usys rollback <name> [version]     roll back"
        echo "    usys list                          list all"
        echo "    usys info <name>                   version history"
        echo "    usys remove <name>                 unregister"
        echo "    usys where <name>                  show location"
        echo "    usys sync <name> <dest>            sync to dest"
        echo "    usys clone <name> <dest>           clone with history"
        echo "    usys search <query>                search registry"
        echo "    usys version                       show version"
        echo "    usys install <pkg> [--mgr]         install + auto-register"
        echo
        echo -e "  ${CYAN}Clone Pool:${RESET}"
        echo "    usys intake <file> <pool> [state]  intake into clone pool"
        echo "    usys deprecate <name>              mark grey, queue hotswap"
        echo "    usys hotswap-check                 scan deprecated files"
        echo
        echo -e "  ${CYAN}Examples:${RESET}"
        echo "    usys register ./deploy.sh deploy"
        echo "    usys call deploy"
        echo "    usys swap deploy ./deploy_v2.sh"
        echo "    usys rollback deploy v1"
        echo "    usys clone deploy /media/jwl247/breach_coms2/backup"
        echo
        ;;

    *)
        if sqlite3 "$USYS_DB" \
           "SELECT COUNT(*) FROM packages WHERE name='$CMD';" \
           2>/dev/null | grep -q "^1$"; then
            cmd_call "$CMD" "$@"
        else
            err "Unknown command: $CMD"
            echo "Run 'usys help' for usage"
            exit 1
        fi
        ;;
esac
