#!/usr/bin/env bash
# =============================================================================
# phoenix_boot.sh — Start the full Phoenix stack (WSL dev)
#
# Boot order:
#   1. Frank5          (helix_lightning_kernel/franken5.py) — SHM bus, rings
#   2. Universal Kernel (phoenix_universal_kernel/main_kernel.py)
#      └─ boots Frank5 (if not already), ProcessLibrary, FrankSpawn,
#         HelixI (7701-7704), HelixE (7805-7808)
#
# NOTE: sector4/helix/helix.py is a standalone demo — NOT a daemon.
#       Helix-I and Helix-E are embedded inside main_kernel.py.
#
# Usage:
#   bash ~/phoenix-devops/phoenix_boot.sh
#   bash ~/phoenix-devops/phoenix_boot.sh --stop
#   bash ~/phoenix-devops/phoenix_boot.sh --status
#   bash ~/phoenix-devops/phoenix_boot.sh --restart
#
# PID file: /tmp/phoenix_pids
# Logs:     /tmp/phoenix_frank5.log  /tmp/phoenix_kernel.log
# =============================================================================

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="/tmp/phoenix_pids"
LOG_DIR="/tmp"

G="\033[0;32m"; R="\033[0;31m"; Y="\033[0;33m"; C="\033[0;36m"
B="\033[1m"; N="\033[0m"

ok()  { echo -e "  ${G}[UP]${N}    $1"; }
bad() { echo -e "  ${R}[FAIL]${N}  $1"; }
inf() { echo -e "  ${C}→${N}       $1"; }

# ── Environment ───────────────────────────────────────────────────────────────
[[ -f "$HOME/.phoenix_env" ]] && source "$HOME/.phoenix_env" 2>/dev/null

export PHOENIX_SECTOR1="${REPO}/sector1"
export PHOENIX_SECTOR2="${REPO}/sector2"
export PHOENIX_SECTOR3="${REPO}/sector3"
export PHOENIX_SECTOR4="${REPO}/sector4"
export PHOENIX_SUITS="${REPO}"
export PHOENIX_SHM="/tmp/phoenix_shm"
export PHOENIX_AUDIT="/tmp/phoenix_audit.log"
export PHOENIX_CUSTODY="/tmp/phoenix_custody.jsonl"
export CLONEPOOL_DIR="${CLONEPOOL_DIR:-${HOME}/Phoenix/clonepool}"

# ── Stop ──────────────────────────────────────────────────────────────────────
stop_stack() {
    echo -e "\n${B}Phoenix — Stopping stack${N}"
    if [[ -f "$PID_FILE" ]]; then
        while IFS='=' read -r name pid; do
            if kill -0 "$pid" 2>/dev/null; then
                kill "$pid" 2>/dev/null && echo -e "  ${Y}[DOWN]${N}  $name (PID $pid)"
            fi
        done < "$PID_FILE"
        rm -f "$PID_FILE"
    else
        echo "  No PID file found — nothing to stop"
    fi
    echo ""
}

# ── Status ────────────────────────────────────────────────────────────────────
status_stack() {
    echo -e "\n${B}Phoenix — Stack status${N}"
    if [[ ! -f "$PID_FILE" ]]; then
        echo "  No PID file — stack not started via phoenix_boot.sh"
        return
    fi
    while IFS='=' read -r name pid; do
        if kill -0 "$pid" 2>/dev/null; then
            ok "$name (PID $pid)"
        else
            bad "$name (PID $pid) — not running"
        fi
    done < "$PID_FILE"
    echo ""
    echo -e "  ${C}Channel check:${N}"
    for port in 7701 7702 7703 7704; do
        RESP=$(echo '{"op":"health"}' | nc -w1 localhost "$port" 2>/dev/null || echo "")
        if [[ -n "$RESP" ]]; then
            inf "Port $port — responding"
        else
            inf "Port $port — silent"
        fi
    done
    echo ""
}

# ── Handle flags ──────────────────────────────────────────────────────────────
case "${1:-}" in
    --stop)   stop_stack; exit 0 ;;
    --status) status_stack; exit 0 ;;
    --restart) stop_stack; sleep 1 ;;
esac

# ── Boot ──────────────────────────────────────────────────────────────────────
echo ""
echo -e "${B}${C}Phoenix DevOps OS — Booting${N}  $(date '+%H:%M:%S')"
echo -e "  Repo: $REPO"
echo -e "  Clonepool: $CLONEPOOL_DIR"
echo ""

[[ -f "$PID_FILE" ]] && stop_stack && sleep 1

> "$PID_FILE"

# ── Step 1: Frank5 ───────────────────────────────────────────────────────────
FRANK5="${REPO}/helix_lightning_kernel/franken5.py"
if [[ ! -f "$FRANK5" ]]; then
    bad "Frank5 not found: $FRANK5"
    exit 1
fi

echo -e "${B}1/2  Frank5${N} — SHM bus + rings"
python3 "$FRANK5" > "$LOG_DIR/phoenix_frank5.log" 2>&1 &
FRANK5_PID=$!
echo "frank5=$FRANK5_PID" >> "$PID_FILE"
inf "PID $FRANK5_PID → $LOG_DIR/phoenix_frank5.log"

sleep 2

if kill -0 "$FRANK5_PID" 2>/dev/null; then
    ok "Frank5 running (PID $FRANK5_PID)"
else
    bad "Frank5 died — check $LOG_DIR/phoenix_frank5.log"
    tail -5 "$LOG_DIR/phoenix_frank5.log"
    exit 1
fi

# ── Step 2: Universal Kernel (boots HelixI + HelixE internally) ──────────────
KERNEL="${REPO}/phoenix_universal_kernel/main_kernel.py"
if [[ ! -f "$KERNEL" ]]; then
    bad "Universal Kernel not found: $KERNEL"
    exit 1
fi

echo -e "${B}2/2  Universal Kernel${N} — HelixI (7701-7704) + HelixE (7805-7808)"
python3 "$KERNEL" > "$LOG_DIR/phoenix_kernel.log" 2>&1 &
KERNEL_PID=$!
echo "kernel=$KERNEL_PID" >> "$PID_FILE"
inf "PID $KERNEL_PID → $LOG_DIR/phoenix_kernel.log"

sleep 3

if kill -0 "$KERNEL_PID" 2>/dev/null; then
    ok "Universal Kernel running (PID $KERNEL_PID)"
else
    bad "Universal Kernel died — check $LOG_DIR/phoenix_kernel.log"
    tail -5 "$LOG_DIR/phoenix_kernel.log"
    exit 1
fi

# ── Intake check ─────────────────────────────────────────────────────────────
echo ""
echo -e "${B}Intake check${N}"
sleep 1
INTAKE=$(echo '{"op":"health"}' | nc -w2 localhost 7701 2>/dev/null || echo "")
if [[ -n "$INTAKE" ]]; then
    ok "Channel 7701 responding: $INTAKE"
else
    inf "Channel 7701 silent — kernel may still be warming up"
    inf "Check: echo '{\"op\":\"health\"}' | nc localhost 7701"
fi


# ── Step 3: llama3.1 pre-warm ─────────────────────────────────────────────────
echo -e "${B}3/4  llama3.1${N} — pre-warm via ollama"
if command -v ollama &>/dev/null; then
    ollama run llama3.1 "ping" &>/dev/null &
    LLAMA_PID=$!
    echo "llama3.1=$LLAMA_PID" >> "$PID_FILE"
    sleep 2
    if kill -0 "$LLAMA_PID" 2>/dev/null; then
        ok "llama3.1 warming (PID $LLAMA_PID)"
    else
        inf "llama3.1 pre-warm completed (model loaded into memory)"
    fi
else
    inf "ollama not found — skipping llama3.1 pre-warm"
fi

# ── Step 4: Cpt_conductor ─────────────────────────────────────────────────────
CONDUCTOR="${REPO}/SECTOR4/Cpt_conductor.py"
if [[ ! -f "$CONDUCTOR" ]]; then
    bad "Cpt_conductor not found: $CONDUCTOR"
else
    echo -e "${B}4/4  Cpt_conductor${N} — SECTOR4 ring coordination (coms1-4)"
    python3 "$CONDUCTOR" start > "$LOG_DIR/phoenix_conductor.log" 2>&1 &
    CONDUCTOR_PID=$!
    echo "conductor=$CONDUCTOR_PID" >> "$PID_FILE"
    inf "PID $CONDUCTOR_PID → $LOG_DIR/phoenix_conductor.log"
    sleep 2
    if kill -0 "$CONDUCTOR_PID" 2>/dev/null; then
        ok "Cpt_conductor running (PID $CONDUCTOR_PID)"
    else
        bad "Cpt_conductor died — check $LOG_DIR/phoenix_conductor.log"
        tail -5 "$LOG_DIR/phoenix_conductor.log"
    fi
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo -e "${B}${G}Phoenix stack is up.${N}"
echo ""
echo -e "  ${C}Commands:${N}"
echo -e "    Status:  bash ~/phoenix-devops/phoenix_boot.sh --status"
echo -e "    Stop:    bash ~/phoenix-devops/phoenix_boot.sh --stop"
echo -e "    Logs:    tail -f /tmp/phoenix_frank5.log"
echo -e "             tail -f /tmp/phoenix_kernel.log"
echo -e "    Health:  bash ~/phoenix-devops/status.sh"
echo -e "    Intake:  echo '{\"op\":\"health\"}' | nc localhost 7701"
echo ""
