#!/usr/bin/env bash
# bootstrap.sh — Phoenix DevOps OS
# Drops Phoenix onto the external Ubuntu build target.
# Wires symlinks. Fires Frank. Initializes Helix + clone pool.
# Run once from WSL or directly on the external.
# jwl247 / United Systems / GPL v3
# =============================================================================

set -euo pipefail

PHOENIX_VERSION="1.0.0"
PHOENIX_HOME="${PHOENIX_HOME:-$HOME/Phoenix}"
PHOENIX_REPO="${PHOENIX_REPO:-https://github.com/jwl247/Phoenix-DevOps-oS.git}"
PYTHON="${PYTHON:-python3}"
LOG="$PHOENIX_HOME/logs/bootstrap.log"

# ── Colors ────────────────────────────────────────────────────────────────────

RED='\033[0;31m'
GRN='\033[0;32m'
YLW='\033[1;33m'
BLU='\033[0;34m'
NC='\033[0m'

ph_log()  { echo -e "${BLU}[Phoenix]${NC} $*" | tee -a "$LOG"; }
ph_ok()   { echo -e "${GRN}[  OK  ]${NC} $*"  | tee -a "$LOG"; }
ph_warn() { echo -e "${YLW}[ WARN ]${NC} $*"  | tee -a "$LOG"; }
ph_err()  { echo -e "${RED}[ FAIL ]${NC} $*"  | tee -a "$LOG"; }
ph_die()  { ph_err "$*"; exit 1; }

# ── Banner ────────────────────────────────────────────────────────────────────

banner() {
cat << 'EOF'

  ██████╗ ██╗  ██╗ ██████╗ ███████╗███╗   ██╗██╗██╗  ██╗
  ██╔══██╗██║  ██║██╔═══██╗██╔════╝████╗  ██║██║╚██╗██╔╝
  ██████╔╝███████║██║   ██║█████╗  ██╔██╗ ██║██║ ╚███╔╝
  ██╔═══╝ ██╔══██║██║   ██║██╔══╝  ██║╚██╗██║██║ ██╔██╗
  ██║     ██║  ██║╚██████╔╝███████╗██║ ╚████║██║██╔╝ ██╗
  ╚═╝     ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝╚═╝╚═╝  ╚═╝

  DevOps OS — United Systems — jwl247
  Built for Laurie. Built for everyone. 🧬🔥

EOF
}

# ── Preflight ─────────────────────────────────────────────────────────────────

preflight() {
    ph_log "Running preflight checks..."

    command -v "$PYTHON" >/dev/null 2>&1 \
        || ph_die "Python3 not found. Install python3 first."

    PY_VERSION=$("$PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    ph_log "Python version: $PY_VERSION"

    [[ $(echo "$PY_VERSION >= 3.10" | bc -l) -eq 1 ]] \
        || ph_die "Python 3.10+ required. Found: $PY_VERSION"

    command -v git >/dev/null 2>&1 \
        || ph_die "git not found. Install git first."

    ph_ok "Preflight passed."
}

# ── Directory structure ───────────────────────────────────────────────────────

make_dirs() {
    ph_log "Creating Phoenix directory structure..."
    mkdir -p \
        "$PHOENIX_HOME" \
        "$PHOENIX_HOME/logs" \
        "$PHOENIX_HOME/db" \
        "$PHOENIX_HOME/templates" \
        "$PHOENIX_HOME/clonepool" \
        "$PHOENIX_HOME/bin" \
        "$PHOENIX_HOME/src" \
        "$PHOENIX_HOME/backup"
    ph_ok "Directory structure created at $PHOENIX_HOME"
}

# ── Python dependencies ───────────────────────────────────────────────────────

install_deps() {
    ph_log "Installing Python dependencies..."

    "$PYTHON" -m venv "$PHOENIX_HOME/.venv" \
        || ph_die "Failed to create venv"

    PIP="$PHOENIX_HOME/.venv/bin/pip"
    "$PIP" install --upgrade pip --quiet
    "$PIP" install base58 --quiet \
        || ph_warn "base58 install failed — TAV system will be degraded"

    ph_ok "Python dependencies installed."
}

# ── Copy Phoenix source files ─────────────────────────────────────────────────

copy_sources() {
    ph_log "Copying Phoenix source files..."

    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

    for f in helix.py frank.py package_handler.py; do
        if [[ -f "$SCRIPT_DIR/$f" ]]; then
            cp "$SCRIPT_DIR/$f" "$PHOENIX_HOME/src/$f"
            ph_ok "Copied $f → $PHOENIX_HOME/src/"
        else
            ph_warn "$f not found in $SCRIPT_DIR — skipping"
        fi
    done

    if [[ -d "$SCRIPT_DIR/templates" ]]; then
        cp -r "$SCRIPT_DIR/templates/." "$PHOENIX_HOME/templates/"
        ph_ok "Copied templates → $PHOENIX_HOME/templates/"
    fi

    if [[ -f "$SCRIPT_DIR/CLAUDE.md" ]]; then
        cp "$SCRIPT_DIR/CLAUDE.md" "$PHOENIX_HOME/CLAUDE.md"
        ph_ok "CLAUDE.md placed."
    fi
}

# ── Symlinks — egress_helix is the one process ───────────────────────────────

wire_symlinks() {
    ph_log "Wiring egress symlinks..."

    HELIX_SRC="$PHOENIX_HOME/src/helix.py"
    BIN="$PHOENIX_HOME/bin"

    if [[ ! -f "$HELIX_SRC" ]]; then
        ph_warn "helix.py not found — symlinks skipped"
        return
    fi

    for name in romeo juliet dbl_juliet translator egress_helix; do
        LINK="$BIN/${name}.py"
        [[ -L "$LINK" ]] && rm "$LINK"
        ln -s "$HELIX_SRC" "$LINK"
        ph_ok "symlink: $name → helix.py"
    done

    # Shell wrapper for egress_helix
    cat > "$BIN/egress_helix" << SHEOF
#!/usr/bin/env bash
source "$PHOENIX_HOME/.venv/bin/activate"
PYTHONPATH="$PHOENIX_HOME/src" python3 "$HELIX_SRC" "\$@"
SHEOF
    chmod +x "$BIN/egress_helix"
    ph_ok "Shell wrapper: egress_helix"

    # ph (package handler) wrapper
    cat > "$BIN/ph" << SHEOF
#!/usr/bin/env bash
source "$PHOENIX_HOME/.venv/bin/activate"
PYTHONPATH="$PHOENIX_HOME/src" python3 "$PHOENIX_HOME/src/package_handler.py" "\$@"
SHEOF
    chmod +x "$BIN/ph"
    ph_ok "Shell wrapper: ph (package handler)"

    # frank wrapper
    cat > "$BIN/frank" << SHEOF
#!/usr/bin/env bash
source "$PHOENIX_HOME/.venv/bin/activate"
PYTHONPATH="$PHOENIX_HOME/src" python3 "$PHOENIX_HOME/src/frank.py" "\$@"
SHEOF
    chmod +x "$BIN/frank"
    ph_ok "Shell wrapper: frank"
}

# ── PATH setup ────────────────────────────────────────────────────────────────

setup_path() {
    ph_log "Setting up PATH..."

    PROFILE=""
    [[ -f "$HOME/.bashrc" ]]  && PROFILE="$HOME/.bashrc"
    [[ -f "$HOME/.zshrc" ]]   && PROFILE="$HOME/.zshrc"
    [[ -z "$PROFILE" ]]       && PROFILE="$HOME/.profile"

    EXPORT_LINE="export PATH=\"\$PATH:$PHOENIX_HOME/bin\""
    PHOENIX_ENV_LINE="export PHOENIX_HOME=\"$PHOENIX_HOME\""
    PYTHONPATH_LINE="export PYTHONPATH=\"\$PYTHONPATH:$PHOENIX_HOME/src\""

    if ! grep -q "PHOENIX_HOME" "$PROFILE" 2>/dev/null; then
        {
            echo ""
            echo "# Phoenix DevOps OS"
            echo "$PHOENIX_ENV_LINE"
            echo "$EXPORT_LINE"
            echo "$PYTHONPATH_LINE"
        } >> "$PROFILE"
        ph_ok "PATH updated in $PROFILE"
    else
        ph_warn "Phoenix already in $PROFILE — skipping"
    fi
}

# ── Initialize Helix ──────────────────────────────────────────────────────────

init_helix() {
    ph_log "Initializing Helix + clone pool..."

    ACTIVATE="$PHOENIX_HOME/.venv/bin/activate"
    [[ ! -f "$ACTIVATE" ]] && { ph_warn "venv not found — Helix init skipped"; return; }

    source "$ACTIVATE"
    PYTHONPATH="$PHOENIX_HOME/src" python3 - << PYEOF
import sys
sys.path.insert(0, "$PHOENIX_HOME/src")
try:
    import helix as h
    hx = h.init("$PHOENIX_HOME/clonepool", "$PHOENIX_HOME/db/helix.db")
    # Store bootstrap record in clone pool
    hx.store("phoenix.bootstrap", {
        "version": "$PHOENIX_VERSION",
        "timestamp": __import__("datetime").datetime.utcnow().isoformat(),
        "platform": hx.quad.current,
    })
    stats = hx.stats()
    print(f"  Helix online — platform: {stats['platform']}")
    print(f"  Clone pool: {stats['pool_dir']}")
    print(f"  DB: {stats['db_path']}")
except Exception as e:
    print(f"  Helix init warning: {e}", file=sys.stderr)
PYEOF

    ph_ok "Helix initialized."
}

# ── Initialize Frank ──────────────────────────────────────────────────────────

init_frank() {
    ph_log "Initializing Frank..."

    ACTIVATE="$PHOENIX_HOME/.venv/bin/activate"
    [[ ! -f "$ACTIVATE" ]] && { ph_warn "venv not found — Frank init skipped"; return; }

    source "$ACTIVATE"
    PYTHONPATH="$PHOENIX_HOME/src" python3 - << PYEOF
import sys
sys.path.insert(0, "$PHOENIX_HOME/src")
try:
    import frank as fr
    f = fr.get_frank()
    # Frank intakes his own bootstrap record
    f.intake("frank.bootstrap", {
        "name": "frank.bootstrap",
        "type": "service",
        "version": "1.0.0",
        "description": "Frank bootstrap record",
        "platform": "all",
    }, template_name="process")
    s = f.status()
    print(f"  Frank online — anchor: {s['anchor']}")
    print(f"  Audit entries: {s['audit_entries']}")
    print(f"  Templates: {s['templates']}")
except Exception as e:
    print(f"  Frank init warning: {e}", file=sys.stderr)
PYEOF

    ph_ok "Frank initialized."
}

# ── Initialize Package Handler ────────────────────────────────────────────────

init_ph() {
    ph_log "Initializing Package Handler..."

    ACTIVATE="$PHOENIX_HOME/.venv/bin/activate"
    [[ ! -f "$ACTIVATE" ]] && { ph_warn "venv not found — PH init skipped"; return; }

    source "$ACTIVATE"
    PYTHONPATH="$PHOENIX_HOME/src" python3 - << PYEOF
import sys
sys.path.insert(0, "$PHOENIX_HOME/src")
try:
    import package_handler as ph
    p = ph.get_ph()
    s = p.full_status()
    print(f"  Package Handler online")
    print(f"  Helix connected: {s['helix_online']}")
    print(f"  Frank connected: {s['frank_online']}")
    print(f"  D1 configured:   {s['d1_configured']}")
    g = p.glossary()
    print(f"  Clone pool items: {g['clone_pool']}")
except Exception as e:
    print(f"  Package Handler init warning: {e}", file=sys.stderr)
PYEOF

    ph_ok "Package Handler initialized."
}

# ── Status check ──────────────────────────────────────────────────────────────

status_check() {
    ph_log "Running status check..."
    echo ""
    echo "  PHOENIX_HOME    : $PHOENIX_HOME"
    echo "  Python          : $("$PYTHON" --version 2>&1)"
    echo "  Venv            : $([ -d "$PHOENIX_HOME/.venv" ] && echo "✓ exists" || echo "✗ missing")"
    echo "  Helix DB        : $([ -f "$PHOENIX_HOME/db/helix.db" ] && echo "✓ exists" || echo "✗ missing")"
    echo "  Frank DB        : $([ -f "$PHOENIX_HOME/db/frank.db" ] && echo "✓ exists" || echo "✗ missing")"
    echo "  Package Handler : $([ -f "$PHOENIX_HOME/db/packages.db" ] && echo "✓ exists" || echo "✗ missing")"
    echo "  Clone Pool      : $(ls "$PHOENIX_HOME/clonepool" 2>/dev/null | wc -l) items"
    echo "  Templates       : $(ls "$PHOENIX_HOME/templates"/*.json 2>/dev/null | wc -l) templates"
    echo "  Symlinks        : $(ls "$PHOENIX_HOME/bin" 2>/dev/null | wc -l) entries"
    echo ""
}

# ── Main ──────────────────────────────────────────────────────────────────────

main() {
    mkdir -p "$(dirname "$LOG")"
    banner
    ph_log "Phoenix DevOps OS Bootstrap v$PHOENIX_VERSION"
    ph_log "Target: $PHOENIX_HOME"
    ph_log "Date:   $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
    echo ""

    preflight
    make_dirs
    install_deps
    copy_sources
    wire_symlinks
    setup_path
    init_helix
    init_frank
    init_ph
    status_check

    echo ""
    ph_ok "Phoenix bootstrap complete. 🧬🔥"
    echo ""
    ph_log "To activate this session:"
    echo "  source $PHOENIX_HOME/.venv/bin/activate"
    echo "  export PATH=\"\$PATH:$PHOENIX_HOME/bin\""
    echo "  export PYTHONPATH=\"\$PYTHONPATH:$PHOENIX_HOME/src\""
    echo ""
    ph_log "Commands now available:"
    echo "  frank    — intake authority"
    echo "  ph       — package handler"
    echo "  egress_helix — egress + platform translation"
    echo ""
    ph_log "Example:"
    echo "  frank status"
    echo "  ph list"
    echo "  ph install git"
    echo "  egress_helix translate 'apt-get install git' --target windows"
    echo ""
    ph_log "Log: $LOG"
}

main "$@"