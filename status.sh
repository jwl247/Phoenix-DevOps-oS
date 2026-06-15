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

WG_OUT=$(sudo wg show wg0-wsl 2>/dev/null)
if [[ -n "$WG_OUT" ]]; then
    HS=$(echo "$WG_OUT" | grep "latest handshake" | sed 's/.*latest handshake: //')
    HS_SEC=$(echo "$WG_OUT" | grep "latest handshake" | grep -o '[0-9]* second' | awk '{print $1}')
    if [[ -z "$HS" ]]; then
        warn "wg0-wsl up but no handshake yet"
        info "On Windows: open WireGuard app → Activate wg0"
    elif [[ -n "$HS_SEC" && "$HS_SEC" -lt 180 ]]; then
        ok "wg0-wsl active — handshake: $HS ago"
    else
        warn "wg0-wsl up — handshake: $HS (stale?) — check Windows WireGuard app"
    fi
else
    bad "wg0-wsl not running"
    info "Fix: sudo wg-quick up ~/phoenix-devops/sector3/wireguard/wg0-wsl.conf"
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
        "sudo -n wg show wg0 2>/dev/null | grep 'latest handshake' || echo NONE" 2>/dev/null || echo "FAIL")
    if echo "$WG_EXT" | grep -q "latest handshake"; then
        ok "wg0 active on phoenix-ext — handshake: $(echo "$WG_EXT" | sed 's/.*latest handshake: //')"
    elif [[ "$WG_EXT" == "NONE" ]]; then
        bad "wg0 not running on phoenix-ext"
        info "Fix: ssh -t phoenix-lan \"sudo bash -c 'systemctl enable --now wg-quick@wg0'\""
        info "If /etc/wireguard/wg0.conf missing:"
        info "  scp ~/phoenix-devops/sector3/wireguard/wg0-phoenix-ext.conf phoenix-lan:/tmp/wg0.conf"
        info "  ssh -t phoenix-lan \"sudo bash -c 'cp /tmp/wg0.conf /etc/wireguard/wg0.conf && chmod 600 /etc/wireguard/wg0.conf && systemctl enable --now wg-quick@wg0'\""
    else
        warn "Couldn't check wg0 on ext (sudo may need password)"
        info "Run: ssh -t phoenix-lan 'sudo wg show'"
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
