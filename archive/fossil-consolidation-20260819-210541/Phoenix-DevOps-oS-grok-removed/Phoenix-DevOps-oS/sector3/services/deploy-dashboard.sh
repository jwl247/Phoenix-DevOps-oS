#!/usr/bin/env bash
# deploy-dashboard.sh — Install and autostart the Phoenix desktop on Ubuntu
# Wires: ollama (Help Desk) → dashboard (Electron shell) → graphical login
# Phoenix DevOps OS / jwl247 / GPL v3

set -euo pipefail

BOLD='\033[1m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'

ok()   { echo -e "${GREEN}✓${NC} $*"; }
warn() { echo -e "${YELLOW}⚠${NC}  $*"; }
die()  { echo -e "${RED}✗${NC} $*"; exit 1; }
hdr()  { echo -e "\n${BOLD}── $* ──${NC}"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DASHBOARD_SRC="$REPO_ROOT/dashboard"
PHOENIX_ROOT="${PHOENIX_ROOT:-$REPO_ROOT}"
DASHBOARD_DIR="${DASHBOARD_DIR:-$PHOENIX_ROOT/dashboard}"
SERVICE_DIR="$HOME/.config/systemd/user"
PHOENIX_CONF="$HOME/.phoenix"
ENV_FILE="$PHOENIX_CONF/phoenix.env"
START_SCRIPT="$DASHBOARD_DIR/start-desktop.sh"
DASHBOARD_UNIT="$SERVICE_DIR/phoenix-dashboard.service"
OLLAMA_UNIT="$SERVICE_DIR/phoenix-ollama.service"
DESKTOP_TARGET="$SERVICE_DIR/phoenix-desktop.target"

hdr "Phoenix Desktop Deploy"
echo "  Repo:      $REPO_ROOT"
echo "  Dashboard: $DASHBOARD_DIR"
echo "  Units:     $SERVICE_DIR"

# ── Node.js ───────────────────────────────────────────────────────────────────
hdr "Node.js"
if ! command -v node &>/dev/null; then
    warn "Node.js not found — installing via NodeSource..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
    sudo apt-get install -y nodejs
fi
ok "Node $(node --version)"

# ── Dashboard dependencies (local electron via npm) ───────────────────────────
hdr "Dashboard npm install"
if [ "$DASHBOARD_DIR" != "$DASHBOARD_SRC" ] && [ ! -d "$DASHBOARD_DIR" ]; then
    cp -r "$DASHBOARD_SRC" "$DASHBOARD_DIR"
    ok "Copied dashboard → $DASHBOARD_DIR"
fi
cd "$DASHBOARD_DIR"
npm install 2>&1 | tail -5
if [ -x "node_modules/.bin/electron" ] || [ -f "node_modules/.bin/electron" ]; then
    ok "local electron binary present"
else
    npx --yes electron --version &>/dev/null || true
fi
chmod +x "$START_SCRIPT" 2>/dev/null || true
ok "npm install done"

# ── Ollama (Help Desk primary) ────────────────────────────────────────────────
hdr "Ollama"
OLLAMA_BIN=""
if command -v ollama &>/dev/null; then
    OLLAMA_BIN="$(command -v ollama)"
    ok "Ollama at $OLLAMA_BIN"
else
    warn "Ollama not installed — Help Desk will use Claude fallback"
    warn "Install: curl -fsSL https://ollama.com/install.sh | sh"
    OLLAMA_BIN="/usr/local/bin/ollama"
fi

# ── ~/.phoenix/ config ────────────────────────────────────────────────────────
hdr "Phoenix config"
mkdir -p "$PHOENIX_CONF"
chmod 700 "$PHOENIX_CONF"

if [ ! -f "$ENV_FILE" ]; then
    cat > "$ENV_FILE" <<ENV
# Phoenix environment — loaded by phoenix-dashboard.service + start-desktop.sh
PHOENIX_ROOT=$PHOENIX_ROOT
PHOENIX_WORKER_URL=https://packages-worker.phoenix-jwl.workers.dev
PHOENIX_AI_PROVIDER=helpdesk
PHOENIX_OLLAMA_URL=http://localhost:11434
PHOENIX_SKIP_AUTH_MODAL=1
# PHOENIX_AUTH=                # Worker auth token
# CLONEPOOL_DIR=$HOME/Phoenix/clonepool
ENV
    chmod 600 "$ENV_FILE"
    ok "Created $ENV_FILE"
else
    ok "$ENV_FILE already exists — not overwritten"
fi

# ── systemd user units ────────────────────────────────────────────────────────
hdr "systemd user units"
mkdir -p "$SERVICE_DIR"

if command -v ollama &>/dev/null; then
    cat > "$OLLAMA_UNIT" <<OLLAMA
[Unit]
Description=Ollama local LLM for Phoenix Help Desk
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=$OLLAMA_BIN serve
Restart=on-failure
RestartSec=5
Environment=OLLAMA_HOST=127.0.0.1:11434

[Install]
WantedBy=default.target
OLLAMA
    ok "phoenix-ollama.service written"
else
    warn "Skipping phoenix-ollama.service (ollama not installed)"
fi

cat > "$DASHBOARD_UNIT" <<SERVICE
[Unit]
Description=Phoenix DevOps OS Desktop (Electron shell + Help Desk)
After=network-online.target graphical-session.target phoenix-ollama.service
Wants=network-online.target
Wants=phoenix-ollama.service

[Service]
Type=simple
ExecStart=$START_SCRIPT
WorkingDirectory=$DASHBOARD_DIR
Restart=on-failure
RestartSec=5
StartLimitBurst=5
StartLimitIntervalSec=120
EnvironmentFile=-$ENV_FILE
Environment=DISPLAY=:0
Environment=XAUTHORITY=$HOME/.Xauthority
StandardOutput=journal
StandardError=journal
SyslogIdentifier=phoenix-dashboard

[Install]
WantedBy=phoenix-desktop.target
SERVICE
ok "phoenix-dashboard.service written"

cp "$SCRIPT_DIR/phoenix-desktop.target" "$DESKTOP_TARGET"
ok "phoenix-desktop.target installed"

# ── linger (user systemd survives logout / boots at login) ────────────────────
hdr "loginctl linger"
if loginctl enable-linger "$USER" 2>/dev/null; then
    ok "linger enabled for $USER"
else
    warn "Could not enable linger — desktop may not start until next graphical login"
fi

# ── Enable and start ──────────────────────────────────────────────────────────
hdr "Enable desktop target"
systemctl --user daemon-reload
systemctl --user enable phoenix-desktop.target
if [ -f "$OLLAMA_UNIT" ]; then
    systemctl --user enable phoenix-ollama.service
    systemctl --user start  phoenix-ollama.service || warn "ollama start failed — may need install"
fi
systemctl --user enable phoenix-dashboard.service
systemctl --user start  phoenix-dashboard.service

sleep 4
if systemctl --user is-active --quiet phoenix-dashboard; then
    ok "phoenix-dashboard.service is RUNNING"
else
    STATUS=$(systemctl --user status phoenix-dashboard --no-pager 2>&1 | tail -10)
    warn "Dashboard may need an active graphical session. Status:"
    echo "$STATUS"
    echo ""
    warn "Ensure you are logged into a desktop session, or set DISPLAY in $ENV_FILE"
fi

echo ""
echo -e "${BOLD}${GREEN}Phoenix desktop deployed.${NC}"
echo "  Target:  systemctl --user status phoenix-desktop.target"
echo "  Logs:    journalctl --user -u phoenix-dashboard -f"
echo "  Ollama:  journalctl --user -u phoenix-ollama -f"
echo "  Stop:    systemctl --user stop phoenix-desktop.target"
echo "  Config:  $ENV_FILE"