#!/usr/bin/env bash
# bootstrap.sh — Phoenix DevOps OS
# Drops Phoenix onto the external Ubuntu build target.
# Wires symlinks. Fires Frank. Initializes Helix + clone pool.
# Run once from WSL or directly on the external CoPES machine.
# jwl247 / United Systems / GPL v3
# =============================================================================
# NOTE: No set -euo pipefail — failures warn and continue, never abort.
# Every function is self-contained. A failed init does not kill the run.
# =============================================================================

PHOENIX_VERSION="1.0.0"
PHOENIX_HOME="${PHOENIX_HOME:-$HOME/Phoenix}"
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
cat << 'BANNER'

  ██████╗ ██╗  ██╗ ██████╗ ███████╗███╗   ██╗██╗██╗  ██╗
  ██╔══██╗██║  ██║██╔═══██╗██╔════╝████╗  ██║██║╚██╗██╔╝
  ██████╔╝███████║██║   ██║█████╗  ██╔██╗ ██║██║ ╚███╔╝
  ██╔═══╝ ██╔══██║██║   ██║██╔══╝  ██║╚██╗██║██║ ██╔██╗
  ██║     ██║  ██║╚██████╔╝███████╗██║ ╚████║██║██╔╝ ██╗
  ╚═╝     ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝╚═╝╚═╝  ╚═╝

  DevOps OS — United Systems — jwl247
  Built for Laurie. Built for everyone. 🔥⚡

BANNER
}

# ── Preflight ─────────────────────────────────────────────────────────────────

preflight() {
    ph_log "Running preflight checks..."

    command -v "$PYTHON" >/dev/null 2>&1 \
        || ph_die "Python3 not found. Install python3 first."

    PY_VERSION=$("$PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    ph_log "Python version: $PY_VERSION"

    PY_OK=$("$PYTHON" -c "import sys; print(1 if sys.version_info >= (3,10) else 0)")
    [[ "$PY_OK" == "1" ]] || ph_die "Python 3.10+ required. Found: $PY_VERSION"

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
        "$PHOENIX_HOME/src/kernel" \
        "$PHOENIX_HOME/backup"
    ph_ok "Directory structure created at $PHOENIX_HOME"
}

# ── Python dependencies ───────────────────────────────────────────────────────

install_deps() {
    ph_log "Installing Python dependencies..."

    "$PYTHON" -m venv "$PHOENIX_HOME/.venv"
    if [[ $? -ne 0 ]]; then
        ph_die "Failed to create venv — is python3-venv installed?"
    fi

    PIP="$PHOENIX_HOME/.venv/bin/pip"
    "$PIP" install --upgrade pip --quiet

    # base58 required for TAV hex identity in helix.py
    "$PIP" install base58 --quiet
    if [[ $? -eq 0 ]]; then
        ph_ok "base58 installed — TAV system ready"
    else
        ph_warn "base58 install failed — TAV system will be degraded"
    fi

    ph_ok "Python dependencies installed."
}

# ── Copy Phoenix source files ─────────────────────────────────────────────────

copy_sources() {
    ph_log "Copying Phoenix source files..."

    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    SRC_DIR="$(cd "$SCRIPT_DIR/../src" 2>/dev/null && pwd)"

    if [[ -z "$SRC_DIR" || ! -d "$SRC_DIR" ]]; then
        ph_warn "src/ directory not found relative to install/ — trying SCRIPT_DIR"
        SRC_DIR="$SCRIPT_DIR"
    fi

    ph_log "Source directory: $SRC_DIR"

    for f in helix.py frank.py package_handler.py helix_memory.py \
              distro_handler.py watcher.py; do
        if [[ -f "$SRC_DIR/$f" ]]; then
            cp "$SRC_DIR/$f" "$PHOENIX_HOME/src/$f"
            ph_ok "Copied $f → $PHOENIX_HOME/src/"
        else
            ph_warn "$f not found in $SRC_DIR — skipping"
        fi
    done

    # ── Kernel package — Frank and Helix kernel layer ─────────────────────────
    if [[ -d "$SRC_DIR/kernel" ]]; then
        mkdir -p "$PHOENIX_HOME/src/kernel"
        cp -r "$SRC_DIR/kernel/." "$PHOENIX_HOME/src/kernel/"
        ph_ok "Copied kernel/ → $PHOENIX_HOME/src/kernel/"
    else
        ph_warn "kernel/ not found in $SRC_DIR — kernel layer skipped"
    fi

    # Copy security subdir if present
    if [[ -d "$SRC_DIR/security" ]]; then
        mkdir -p "$PHOENIX_HOME/src/security"
        cp -r "$SRC_DIR/security/." "$PHOENIX_HOME/src/security/"
        ph_ok "Copied security/ → $PHOENIX_HOME/src/security/"
    fi

    if [[ -d "$SCRIPT_DIR/templates" ]]; then
        cp -r "$SCRIPT_DIR/templates/." "$PHOENIX_HOME/templates/"
        ph_ok "Copied templates → $PHOENIX_HOME/templates/"
    fi

    REPO_ROOT="$(cd "$SCRIPT_DIR/.." 2>/dev/null && pwd)"
    if [[ -f "$REPO_ROOT/CLAUDE.md" ]]; then
        cp "$REPO_ROOT/CLAUDE.md" "$PHOENIX_HOME/CLAUDE.md"
        ph_ok "CLAUDE.md placed."
    fi
}

# ── Symlinks ──────────────────────────────────────────────────────────────────

wire_symlinks() {
    ph_log "Wiring egress symlinks..."

    HELIX_SRC="$PHOENIX_HOME/src/helix.py"
    BIN="$PHOENIX_HOME/bin"

    if [[ ! -f "$HELIX_SRC" ]]; then
        ph_warn "helix.py not found in $PHOENIX_HOME/src/ — symlinks skipped"
        return
    fi

    for name in romeo juliet dbl_juliet translator; do
        LINK="$BIN/${name}.py"
        [[ -L "$LINK" ]] && rm "$LINK"
        [[ -f "$LINK" ]] && rm "$LINK"
        ln -s "$HELIX_SRC" "$LINK"
        ph_ok "symlink: $name → helix.py"
    done

    # Shell wrapper: egress_helix
    cat > "$BIN/egress_helix" << SHEOF
#!/usr/bin/env bash
source "$PHOENIX_HOME/.venv/bin/activate"
PYTHONPATH="$PHOENIX_HOME/src" python3 "$HELIX_SRC" "\$@"
SHEOF
    chmod +x "$BIN/egress_helix"
    ph_ok "Shell wrapper: egress_helix"

    # Shell wrapper: ph (package handler)
    cat > "$BIN/ph" << SHEOF
#!/usr/bin/env bash
source "$PHOENIX_HOME/.venv/bin/activate"
PYTHONPATH="$PHOENIX_HOME/src" python3 "$PHOENIX_HOME/src/package_handler.py" "\$@"
SHEOF
    chmod +x "$BIN/ph"
    ph_ok "Shell wrapper: ph"

    # Shell wrapper: frank
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
    [[ -f "$HOME/.bashrc" ]] && PROFILE="$HOME/.bashrc"
    [[ -f "$HOME/.zshrc"  ]] && PROFILE="$HOME/.zshrc"
    [[ -z "$PROFILE"      ]] && PROFILE="$HOME/.profile"

    if ! grep -q "PHOENIX_HOME" "$PROFILE" 2>/dev/null; then
        {
            echo ""
            echo "# Phoenix DevOps OS"
            echo "export PHOENIX_HOME=\"$PHOENIX_HOME\""
            echo "export PATH=\"\$PATH:$PHOENIX_HOME/bin\""
            echo "export PYTHONPATH=\"\$PYTHONPATH:$PHOENIX_HOME/src\""
        } >> "$PROFILE"
        ph_ok "PATH updated in $PROFILE"
    else
        ph_warn "Phoenix already in $PROFILE — skipping PATH update"
    fi
}

# ── Initialize Kernel — Frank-0 comes up first, always ───────────────────────

init_kernel() {
    ph_log "Initializing CoPES kernel — Frank-0 must be sovereign first..."

    ACTIVATE="$PHOENIX_HOME/.venv/bin/activate"
    if [[ ! -f "$ACTIVATE" ]]; then
        ph_warn "venv not found — kernel init skipped"
        return
    fi

    if [[ ! -f "$PHOENIX_HOME/src/kernel/frank.py" ]]; then
        ph_warn "kernel/frank.py not found — kernel layer skipped"
        return
    fi

    source "$ACTIVATE"

    PYTHONPATH="$PHOENIX_HOME/src" python3 - << PYEOF
import sys
sys.path.insert(0, "$PHOENIX_HOME/src")
try:
    from kernel.frank import build_ring_chain
    frank0 = build_ring_chain()
    s = frank0.status()
    print(f"  Kernel ring chain : online")
    print(f"  Frank-0 ring      : {s['ring']}")
    print(f"  Frank below       : Ring {s['frank_below']}")
    print(f"  Active imports    : {s['active_imports']}")
    print(f"  AI instances      : {s['ai_instances']}")
    print(f"  Status            : Stationary. Sovereign.")
except Exception as e:
    print(f"  Kernel init warning: {e}", file=sys.stderr)
PYEOF

    ph_ok "Kernel initialized — Frank-0 sovereign, ring chain established."
}

# ── Initialize Helix ──────────────────────────────────────────────────────────

init_helix() {
    ph_log "Initializing Helix + clone pool..."

    ACTIVATE="$PHOENIX_HOME/.venv/bin/activate"
    if [[ ! -f "$ACTIVATE" ]]; then
        ph_warn "venv not found — Helix init skipped"
        return
    fi

    if [[ ! -f "$PHOENIX_HOME/src/helix.py" ]]; then
        ph_warn "helix.py not in $PHOENIX_HOME/src/ — Helix init skipped"
        return
    fi

    source "$ACTIVATE"

    PYTHONPATH="$PHOENIX_HOME/src" python3 - << PYEOF
import sys
sys.path.insert(0, "$PHOENIX_HOME/src")
try:
    import helix as h
    hx = h.init("$PHOENIX_HOME/clonepool", "$PHOENIX_HOME/db/helix.db")
    import datetime
    hx.store("phoenix.bootstrap", {
        "version":   "$PHOENIX_VERSION",
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "platform":  hx.quad.current,
    })
    stats = hx.stats()
    print(f"  Helix online   — platform: {stats['platform']}")
    print(f"  Clone pool     : {stats['pool_dir']}")
    print(f"  DB             : {stats['db_path']}")
    print(f"  Ops/sec rated  : {stats['ops_per_sec']}")
    print(f"  Hit rate       : {stats['hit_rate_pct']}%")
except Exception as e:
    print(f"  Helix init warning: {e}", file=sys.stderr)
PYEOF

    ph_ok "Helix initialized."
}

# ── Initialize Frank ──────────────────────────────────────────────────────────

init_frank() {
    ph_log "Initializing Frank (operational layer)..."

    ACTIVATE="$PHOENIX_HOME/.venv/bin/activate"
    if [[ ! -f "$ACTIVATE" ]]; then
        ph_warn "venv not found — Frank init skipped"
        return
    fi

    if [[ ! -f "$PHOENIX_HOME/src/frank.py" ]]; then
        ph_warn "frank.py not in $PHOENIX_HOME/src/ — Frank init skipped"
        return
    fi

    source "$ACTIVATE"

    PYTHONPATH="$PHOENIX_HOME/src" python3 "$PHOENIX_HOME/src/frank.py" init 2>&1 \
        | grep -v "^$" \
        || ph_warn "Frank init returned non-zero — check frank.log"

    ph_ok "Frank initialized."
}

# ── Initialize Package Handler ────────────────────────────────────────────────

init_ph() {
    ph_log "Initializing Package Handler..."

    ACTIVATE="$PHOENIX_HOME/.venv/bin/activate"
    if [[ ! -f "$ACTIVATE" ]]; then
        ph_warn "venv not found — Package Handler init skipped"
        return
    fi

    if [[ ! -f "$PHOENIX_HOME/src/package_handler.py" ]]; then
        ph_warn "package_handler.py not in $PHOENIX_HOME/src/ — PH init skipped"
        return
    fi

    source "$ACTIVATE"

    PYTHONPATH="$PHOENIX_HOME/src" python3 - << PYEOF
import sys
sys.path.insert(0, "$PHOENIX_HOME/src")
try:
    import package_handler as ph
    p  = ph.get_ph()
    s  = p.full_status()
    g  = p.glossary()
    print(f"  Package Handler : online")
    print(f"  Version         : {s['ph_version']}")
    print(f"  Helix connected : {s['helix_online']}")
    print(f"  D1 configured   : {s['d1_configured']}")
    print(f"  Packages        : {s['packages_total']} total / {s['packages_active']} active")
    print(f"  Clone pool      : {g['clone_pool']} items")
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
    echo "  Venv            : $([ -d "$PHOENIX_HOME/.venv" ]                    && echo "✔ exists"  || echo "✗ missing")"
    echo "  Kernel          : $([ -d "$PHOENIX_HOME/src/kernel" ]               && echo "✔ present" || echo "✗ missing")"
    echo "  helix.py        : $([ -f "$PHOENIX_HOME/src/helix.py" ]             && echo "✔ exists"  || echo "✗ missing")"
    echo "  frank.py        : $([ -f "$PHOENIX_HOME/src/frank.py" ]             && echo "✔ exists"  || echo "✗ missing")"
    echo "  package_handler : $([ -f "$PHOENIX_HOME/src/package_handler.py" ]   && echo "✔ exists"  || echo "✗ missing")"
    echo "  Helix DB        : $([ -f "$PHOENIX_HOME/db/helix.db" ]              && echo "✔ exists"  || echo "✗ missing")"
    echo "  Frank DB        : $([ -f "$PHOENIX_HOME/db/frank.db" ]              && echo "✔ exists"  || echo "✗ missing")"
    echo "  PH DB           : $([ -f "$PHOENIX_HOME/db/packages.db" ]           && echo "✔ exists"  || echo "✗ missing")"
    echo "  Clone Pool      : $(ls "$PHOENIX_HOME/clonepool" 2>/dev/null | wc -l) items"
    echo "  Bin wrappers    : $(ls "$PHOENIX_HOME/bin" 2>/dev/null | wc -l) entries"
    echo "  Security        : $([ -d "$PHOENIX_HOME/src/security" ]             && echo "✔ present" || echo "✗ missing")"
    echo ""
}

# ── Main ──────────────────────────────────────────────────────────────────────

main() {
    mkdir -p "$(dirname "$LOG")"
    banner
    ph_log "Phoenix DevOps OS Bootstrap v$PHOENIX_VERSION"
    ph_log "Target : $PHOENIX_HOME"
    ph_log "Date   : $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
    echo ""

    preflight
    make_dirs
    install_deps
    copy_sources
    wire_symlinks
    setup_path
    init_kernel      # ← Frank-0 sovereign first, always
    init_helix
    init_frank
    init_ph
    status_check

    echo ""
    ph_ok "Phoenix bootstrap complete. 🔥⚡"
    echo ""
    ph_log "Activate this session:"
    echo "  source $PHOENIX_HOME/.venv/bin/activate"
    echo "  export PATH=\"\$PATH:$PHOENIX_HOME/bin\""
    echo "  export PYTHONPATH=\"\$PYTHONPATH:$PHOENIX_HOME/src\""
    echo ""
    ph_log "Commands available:"
    echo "  frank            — output coordinator + Ring 3"
    echo "  ph               — package handler"
    echo "  egress_helix     — egress + platform translation"
    echo ""
    ph_log "Quick test:"
    echo "  frank status"
    echo "  ph status"
    echo "  egress_helix stats"
    echo "  egress_helix translate 'apt-get install git' --target windows"
    echo ""
    ph_log "Log: $LOG"
}

main "$@"
