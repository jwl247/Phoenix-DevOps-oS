#!/usr/bin/env bash
# =============================================================================
# status.sh — Phoenix DevOps OS health check
# Run this between sessions to see what's green, what needs work.
#
# Usage:  bash ~/phoenix-devops/status.sh
# Paste the output at the start of the next Claude Code session.
# =============================================================================

G="\033[0;32m"; Y="\033[0;33m"; R="\033[0;31m"; C="\033[0;36m"
B="\033[1m"; N="\033[0m"

PASS=0; FAIL=0

ok()   { PASS=$((PASS+1)); echo -e "  ${G}[PASS]${N}  $1"; }
bad()  { FAIL=$((FAIL+1)); echo -e "  ${R}[FAIL]${N}  $1"; }
warn() {                   echo -e "  ${Y}[WARN]${N}  $1"; }
info() {                   echo -e "         ${C}→${N}  $1"; }
hdr()  { echo -e "\n${B}${C}── $1 ──${N}"; }

echo ""
echo -e "${B}Phoenix DevOps OS — Status Check${N}  $(date '+%Y-%m-%d %H:%M')"
echo ""

# ── 1. Local environment ──────────────────────────────────────────────────────
hdr "Local environment (WSL)"

[[ -f "$HOME/.phoenix_env" ]] && source "$HOME/.phoenix_env" 2>/dev/null

if [[ -n "${PHOENIX_HOME:-}" ]]; then
    ok "~/.phoenix_env loaded (PHOENIX_HOME=$PHOENIX_HOME)"
else
    bad "~/.phoenix_env missing — run: bash ~/phoenix-devops/bootstrap.sh"
fi

if [[ -d "$HOME/Phoenix/clonepool" ]]; then
    COUNT=$(ls "$HOME/Phoenix/clonepool" 2>/dev/null | wc -l)
    ok "~/Phoenix/clonepool ($COUNT items)"
else
    bad "~/Phoenix/clonepool missing"
fi

if [[ -x "${HOME}/Phoenix/bin/intake" ]] || command -v intake &>/dev/null; then
    ok "intake command available"
else
    bad "intake not available — source ~/.phoenix_env"
fi

# ── 2. Git repo sync ─────────────────────────────────────────────────────────
hdr "Git repo"

REPO="$HOME/phoenix-devops"
if [[ -d "$REPO/.git" ]]; then
    BRANCH=$(git -C "$REPO" rev-parse --abbrev-ref HEAD 2>/dev/null)
    git -C "$REPO" fetch --quiet origin 2>/dev/null || true
    AHEAD=$(git -C "$REPO" rev-list @{u}..HEAD 2>/dev/null | wc -l | tr -d ' ')
    BEHIND=$(git -C "$REPO" rev-list HEAD..@{u} 2>/dev/null | wc -l | tr -d ' ')
    LOCAL=$(git -C "$REPO" rev-parse --short HEAD 2>/dev/null)
    ok "Repo on branch: $BRANCH (commit: $LOCAL)"
    [[ "$AHEAD"  -gt 0 ]] && warn "$AHEAD commits ahead — push: git -C ~/phoenix-devops push"
    [[ "$BEHIND" -gt 0 ]] && warn "$BEHIND commits behind — pull: git -C ~/phoenix-devops pull"
    [[ "$AHEAD"  -eq 0 && "$BEHIND" -eq 0 ]] && ok "In sync with origin"
else
    bad "Repo not found at $REPO"
fi

# ── 3. WireGuard on WSL ──────────────────────────────────────────────────────
hdr "WireGuard (WSL side)"

if ip link show wg0-wsl &>/dev/null; then
    # Interface exists — try handshake info (needs sudo; skip gracefully if unavailable)
    HS=$(sudo wg show wg0-wsl 2>/dev/null | grep "latest handshake" | sed 's/.*latest handshake: //')
    if [[ -z "$HS" ]]; then
        warn "wg0-wsl up — no handshake yet (run 'sudo wg show wg0-wsl' to check)"
        info "On Windows: ensure WireGuard app has wg0 activated"
    else
        ok "wg0-wsl active — handshake: $HS ago"
    fi
else
    bad "wg0-wsl not running"
    info "Fix: sudo wg-quick up /home/jwlef/phoenix-devops/sector3/wireguard/wg0-wsl.conf"
fi

# ── 4. SSH to phoenix-ext (LAN) ──────────────────────────────────────────────
hdr "SSH to phoenix-ext (192.168.1.133)"

if ssh -o ConnectTimeout=5 -o BatchMode=yes phoenix-lan "echo ok" &>/dev/null; then
    ok "SSH phoenix-lan working (key-based)"
else
    bad "SSH phoenix-lan failed"
    info "Check: is phoenix-ext powered on and on the network?"
    info "If key not installed: scp then run install_key.sh manually"
fi

# ── 5. Phoenix install on phoenix-ext ────────────────────────────────────────
hdr "Phoenix install on phoenix-ext"

SSH_OK=$(ssh -o ConnectTimeout=5 -o BatchMode=yes phoenix-lan "echo ok" 2>/dev/null || echo "FAIL")

if [[ "$SSH_OK" == "ok" ]]; then
    EXT_COMMIT=$(ssh -o BatchMode=yes phoenix-lan \
        "git -C ~/phoenix-devops rev-parse --short HEAD 2>/dev/null || echo MISSING")
    LOCAL_COMMIT=$(git -C "$REPO" rev-parse --short HEAD 2>/dev/null)

    if [[ "$EXT_COMMIT" == "MISSING" ]]; then
        bad "phoenix-devops not cloned on ext"
        info "Fix: ssh phoenix-lan 'curl -fsSL https://get.authenticcoder.com | bash'"
    else
        ok "phoenix-devops cloned on ext (commit: $EXT_COMMIT)"
        [[ "$EXT_COMMIT" != "$LOCAL_COMMIT" ]] && \
            warn "Ext repo is stale — pull: ssh phoenix-lan 'git -C ~/phoenix-devops pull'"
    fi

    CLONEPOOL=$(ssh -o BatchMode=yes phoenix-lan \
        "test -d ~/Phoenix/clonepool && echo yes || echo no" 2>/dev/null)
    [[ "$CLONEPOOL" == "yes" ]] && ok "~/Phoenix/clonepool exists on ext" \
                                 || bad "~/Phoenix missing on ext — re-run bootstrap"
else
    warn "Skipping ext checks (SSH not available)"
fi

# ── 6. WireGuard on phoenix-ext ──────────────────────────────────────────────
hdr "WireGuard on phoenix-ext (10.77.0.3)"

if [[ "$SSH_OK" == "ok" ]]; then
    WG_EXT=$(ssh -o BatchMode=yes phoenix-lan \
        "ip link show wg0 2>/dev/null && echo UP || echo DOWN" 2>/dev/null || echo "FAIL")
    if [[ "$WG_EXT" == *"UP"* ]]; then
        ok "wg0 interface up on phoenix-ext"
        info "Run 'ssh -t phoenix-lan sudo wg show' for handshake details"
    elif [[ "$WG_EXT" == "DOWN" ]]; then
        bad "wg0 not running on phoenix-ext"
        info "Fix: ssh -t phoenix-lan 'sudo bash /tmp/wg_setup.sh'"
    else
        warn "Couldn't reach ext to check WireGuard"
    fi
else
    warn "Skipping (SSH not available)"
fi

# ── 7. Full 3-node WireGuard mesh ────────────────────────────────────────────
hdr "Full mesh (ssh phx = 10.77.0.3 via WireGuard)"

if ssh -o ConnectTimeout=5 -o BatchMode=yes phx "echo ok" &>/dev/null; then
    ok "ssh phx (WireGuard path) working — MESH COMPLETE"
else
    warn "ssh phx not reachable yet"
    info "Needs: wg0 up on phoenix-ext AND wg0-wsl up on WSL"
fi

# ── 8. D1 worker ─────────────────────────────────────────────────────────────
hdr "Cloudflare D1 worker"

WORKER="${PHOENIX_WORKER_URL:-https://packages-worker.phoenix-jwl.workers.dev}"
HTTP=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "Authorization: Bearer ${PHOENIX_AUTH:-test}" \
    "$WORKER/health" --connect-timeout 5 2>/dev/null || echo "000")

if [[ "$HTTP" == "200" ]]; then
    ok "D1 worker healthy ($WORKER)"
elif [[ "$HTTP" == "000" ]]; then
    bad "D1 worker unreachable (timeout) — check internet"
else
    bad "D1 worker returned HTTP $HTTP"
    info "Check: Cloudflare dashboard → Workers → packages-worker"
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${B}────────────────────────────────────────${N}"
if [[ $FAIL -eq 0 ]]; then
    echo -e "  ${G}${B}All $PASS checks passed.${N} Phoenix is healthy."
else
    echo -e "  ${G}$PASS passed${N}  /  ${R}$FAIL failed${N}"
    echo ""
    echo -e "  Fix the red items above, then paste this output to Claude."
fi
echo ""
echo -e "  ${C}Paste this output at the start of the next Claude session.${N}"
echo ""
