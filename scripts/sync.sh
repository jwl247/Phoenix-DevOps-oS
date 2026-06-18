#!/usr/bin/env bash
# =============================================================================
# sync.sh — Phoenix DevOps global sync
# WSL → GitHub → phoenix-ext, one command.
#
# Usage:
#   bash ~/phoenix-devops/scripts/sync.sh           # full sync
#   bash ~/phoenix-devops/scripts/sync.sh --push    # WSL → GitHub only
#   bash ~/phoenix-devops/scripts/sync.sh --pull    # phoenix-ext pull only
#   bash ~/phoenix-devops/scripts/sync.sh --no-restart  # skip service restart
# =============================================================================

set -euo pipefail

REPO="${PHOENIX_INSTALL_DIR:-${HOME}/phoenix-devops}"
EXT_HOST="phoenix-lan"
EXT_REPO="~/phoenix-devops"

G="\033[0;32m"; Y="\033[0;33m"; R="\033[0;31m"; C="\033[0;36m"
B="\033[1m"; N="\033[0m"

ok()   { echo -e "  ${G}[OK]${N}    $1"; }
bad()  { echo -e "  ${R}[FAIL]${N}  $1"; }
warn() { echo -e "  ${Y}[WARN]${N}  $1"; }
hdr()  { echo -e "\n${B}${C}── $1 ──${N}"; }
step() { echo -e "  ${C}→${N}  $1"; }

PUSH=true
PULL=true
RESTART=true

for arg in "${@:-}"; do
    case "$arg" in
        --push)       PULL=false  ; RESTART=false ;;
        --pull)       PUSH=false ;;
        --no-restart) RESTART=false ;;
    esac
done

echo ""
echo -e "${B}Phoenix DevOps — Global Sync${N}  $(date '+%Y-%m-%d %H:%M')"

# ── 1. WSL → GitHub ──────────────────────────────────────────────────────────
if [[ "$PUSH" == true ]]; then
    hdr "WSL → GitHub"

    cd "$REPO"

    # Stage any unstaged tracked changes
    DIRTY=$(git status --porcelain 2>/dev/null | grep -v "^??" | wc -l | tr -d ' ')
    UNTRACKED=$(git status --porcelain 2>/dev/null | grep "^??" | wc -l | tr -d ' ')

    if [[ "$DIRTY" -gt 0 ]]; then
        warn "$DIRTY modified/staged file(s) — commit them before syncing or they won't push"
        git status --short
    fi

    [[ "$UNTRACKED" -gt 0 ]] && warn "$UNTRACKED untracked file(s) (not staged, skipping)"

    AHEAD=$(git rev-list @{u}..HEAD 2>/dev/null | wc -l | tr -d ' ')

    if [[ "$AHEAD" -eq 0 ]]; then
        ok "WSL already up to date with origin — nothing to push"
    else
        step "Pushing $AHEAD commit(s) to origin..."
        git push origin HEAD
        ok "Pushed to github.com/jwl247/Phoenix-DevOps-oS"
    fi

    # Push any submodules that have commits ahead of origin
    step "Checking submodules..."
    git submodule foreach --quiet '
        ahead=$(git rev-list @{u}..HEAD 2>/dev/null | wc -l | tr -d " ")
        if [[ "$ahead" -gt 0 ]]; then
            echo "  [sub] $name — pushing $ahead commit(s)"
            git push origin HEAD 2>/dev/null || echo "  [sub] $name — push skipped (private or no remote)"
        fi
    ' 2>/dev/null || true
    ok "Submodules checked"
fi

# ── 2. phoenix-ext pull ───────────────────────────────────────────────────────
if [[ "$PULL" == true ]]; then
    hdr "GitHub → phoenix-ext"

    SSH_OK=$(ssh -o ConnectTimeout=6 -o BatchMode=yes "$EXT_HOST" "echo ok" 2>/dev/null || echo FAIL)

    if [[ "$SSH_OK" != "ok" ]]; then
        bad "Cannot reach $EXT_HOST — skipping ext pull"
        echo -e "       Check: is phoenix-ext on? Is SSH key working?"
        echo -e "       Manual: ssh $EXT_HOST 'git -C $EXT_REPO pull --recurse-submodules'"
    else
        step "Pulling on phoenix-ext..."
        EXT_OUT=$(ssh -o BatchMode=yes "$EXT_HOST" "
            cd $EXT_REPO
            git fetch --quiet origin
            BEHIND=\$(git rev-list HEAD..@{u} | wc -l | tr -d ' ')
            if [[ \"\$BEHIND\" -gt 0 ]]; then
                git pull --ff-only --recurse-submodules 2>&1
                echo \"PULLED:\$BEHIND\"
            else
                echo \"UPTODATE\"
            fi
        " 2>&1)

        if echo "$EXT_OUT" | grep -q "UPTODATE"; then
            ok "phoenix-ext already up to date"
        elif echo "$EXT_OUT" | grep -q "PULLED:"; then
            COUNT=$(echo "$EXT_OUT" | grep "PULLED:" | cut -d: -f2)
            ok "phoenix-ext pulled $COUNT commit(s)"
        else
            warn "phoenix-ext pull output:"
            echo "$EXT_OUT" | sed 's/^/         /'
        fi

        # ── 3. Restart phoenix-kernel on ext ─────────────────────────────────
        if [[ "$RESTART" == true ]]; then
            hdr "Restart phoenix-kernel on ext"
            step "Restarting phoenix-kernel.service..."
            RST=$(ssh -o BatchMode=yes "$EXT_HOST" \
                "sudo systemctl restart phoenix-kernel 2>&1 && echo OK || echo FAIL")
            if echo "$RST" | grep -q "OK"; then
                ok "phoenix-kernel.service restarted"
            else
                warn "Restart returned: $RST"
                warn "Manual: ssh $EXT_HOST 'sudo systemctl restart phoenix-kernel'"
            fi
        fi
    fi
fi

# ── Summary ───────────────────────────────────────────────────────────────────
hdr "Done"

LOCAL=$(git -C "$REPO" rev-parse --short HEAD 2>/dev/null)
echo -e "  WSL commit:  ${C}${LOCAL}${N}"

if [[ "$PULL" == true ]]; then
    EXT_SHA=$(ssh -o ConnectTimeout=4 -o BatchMode=yes "$EXT_HOST" \
        "git -C $EXT_REPO rev-parse --short HEAD 2>/dev/null" 2>/dev/null || echo "unreachable")
    echo -e "  ext commit:  ${C}${EXT_SHA}${N}"
    [[ "$LOCAL" == "$EXT_SHA" ]] && ok "Both nodes on same commit" \
                                  || warn "Commits differ — check above"
fi

echo ""
