#!/bin/bash
# start_wsl.sh — start the full WSL2 side of the bridge stack
# Run this inside your WSL2 Debian session
# Usage: bash start_wsl.sh

PHOENIX_HOME="${PHOENIX_HOME:-$HOME/projects/phoenix}"
BRIDGE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log() { echo -e "${GREEN}[phoenix]${NC} $*"; }
warn() { echo -e "${YELLOW}[phoenix]${NC} $*"; }

# ── check bridge.py exists ────────────────────────────────────────────────────
[ -f "$BRIDGE_DIR/bridge.py" ] || { echo "bridge.py not found in $BRIDGE_DIR"; exit 1; }

# ── kill any stale instances ──────────────────────────────────────────────────
pkill -f "bridge.py"          2>/dev/null
pkill -f "linux_concierge.py" 2>/dev/null
pkill -f "frank_http.py"      2>/dev/null
rm -f /tmp/phoenix_linux.sock
sleep 0.3

# ── start Frank3 HTTP bridge ──────────────────────────────────────────────────
if [ -f "$PHOENIX_HOME/frank_http.py" ]; then
    python3 "$PHOENIX_HOME/frank_http.py" >> /tmp/frank3.log 2>&1 &
    FRANK_PID=$!
    log "Frank3 HTTP bridge started (pid $FRANK_PID) → port 7347"
else
    warn "frank_http.py not found at $PHOENIX_HOME — Frank routing disabled"
fi

sleep 0.3

# ── start bridge kernel ───────────────────────────────────────────────────────
python3 "$BRIDGE_DIR/bridge.py" >> /tmp/bridge.log 2>&1 &
BRIDGE_PID=$!
log "Bridge kernel started (pid $BRIDGE_PID) → port 9900"

sleep 0.3

# ── start linux concierge ─────────────────────────────────────────────────────
python3 "$BRIDGE_DIR/linux_concierge.py" >> /tmp/linux_concierge.log 2>&1 &
LC_PID=$!
log "Linux concierge started (pid $LC_PID) → /tmp/phoenix_linux.sock"

sleep 0.5

# ── verify ────────────────────────────────────────────────────────────────────
echo ""
log "Stack status:"

check_port() {
    python3 -c "
import socket
s = socket.socket()
s.settimeout(1)
r = s.connect_ex(('127.0.0.1', $1))
s.close()
print('  port $1 : ' + ('UP' if r==0 else 'DOWN'))
"
}

check_port 9900
check_port 7347
[ -S /tmp/phoenix_linux.sock ] && \
    echo "  unix sock : UP" || \
    echo "  unix sock : DOWN"

echo ""
log "Windows concierge can reach bridge at 127.0.0.1:9900"
log "Logs: /tmp/bridge.log  /tmp/frank3.log  /tmp/linux_concierge.log"
echo ""
log "To test from Windows PowerShell:"
echo "    .\\concierge.exe status"
echo "    .\\concierge.exe send \"hello frank\" doc"
echo ""
log "Press Ctrl+C to stop all"

# wait and tail logs
trap 'log "stopping..."; kill $FRANK_PID $BRIDGE_PID $LC_PID 2>/dev/null; exit 0' INT
tail -f /tmp/bridge.log
