#!/usr/bin/env bash
# =============================================================================
# intake_repos.sh — Intake all source files from all 5 Phoenix repos into D1
#
# Repos:
#   1. ~/phoenix-devops/           (Phoenix-DevOps-oS + submodules)
#   2. ~/CoPES/                    (CoPES substrate)
#
# Files intaked one by one — every file gets its own hex ID, sidecar.json,
# clonepool slot, and D1 custody receipt.
#
# Usage:
#   bash ~/phoenix-devops/scripts/intake_repos.sh            # dry run
#   bash ~/phoenix-devops/scripts/intake_repos.sh --run      # real intake
# =============================================================================

set -euo pipefail

REPOS=(
    "/home/jwlef/phoenix-devops"
    "/home/jwlef/CoPES"
)

INTAKE_PY="${PHOENIX_INSTALL_DIR:-${HOME}/phoenix-devops}/unitedsys/core/intake.py"

# Skip dirs — clonepool already in Phoenix, rest are non-source
SKIP_DIRS=".git|__pycache__|node_modules|venv|dist|build|clonepool|.pyc"

# Skip compiled/binary artifacts
SKIP_EXT="pyc|class|o|so|dll|exe|msi|jar|lnk|tmp|crdownload|part|DS_Store|ico|lock"

DRY_RUN=true

for arg in "${@:-}"; do
    case "$arg" in
        --run)      DRY_RUN=false ;;
        --dry-run)  DRY_RUN=true ;;
    esac
done

G="\033[0;32m"; Y="\033[0;33m"; R="\033[0;31m"; C="\033[0;36m"
B="\033[1m"; N="\033[0m"

echo ""
if [[ "$DRY_RUN" == true ]]; then
    echo -e "${B}${Y}DRY RUN — nothing will be intaked. Pass --run to execute.${N}"
else
    echo -e "${B}${G}LIVE RUN — all 5 repos → Phoenix clonepool + D1${N}"
fi
echo -e "${B}Phoenix Repo Intake${N}  $(date '+%Y-%m-%d %H:%M')"
echo ""

[[ -f "${HOME}/.phoenix_env" ]] && source "${HOME}/.phoenix_env" 2>/dev/null

if [[ ! -f "$INTAKE_PY" ]]; then
    echo -e "  ${R}[FAIL]${N}  intake.py not found at $INTAKE_PY"
    exit 1
fi

# ── Build file list ───────────────────────────────────────────────────────────

FILES=()

for repo in "${REPOS[@]}"; do
    if [[ ! -d "$repo" ]]; then
        echo -e "  ${Y}[SKIP]${N}  $repo (not found)"
        continue
    fi

    BEFORE=${#FILES[@]}
    while IFS= read -r f; do
        FILES+=("$f")
    done < <(
        find "$repo" -type f 2>/dev/null \
            | grep -vE "/($SKIP_DIRS)/" \
            | grep -vE "\.($SKIP_EXT)$" \
            | sort
    )
    ADDED=$(( ${#FILES[@]} - BEFORE ))
    echo -e "  ${C}$(basename "$repo")${N}  —  ${ADDED} files"
done

TOTAL=${#FILES[@]}
echo ""
echo -e "${B}Total: ${TOTAL} files across all repos${N}"
echo ""

if [[ "$DRY_RUN" == true ]]; then
    echo -e "${Y}All files that would be intaked:${N}"
    for f in "${FILES[@]}"; do
        # Show path relative to home
        echo "  ${f/#$HOME/~}"
    done
    echo ""
    echo -e "Run with ${B}--run${N} to execute."
    exit 0
fi

# ── Intake one by one ─────────────────────────────────────────────────────────

PASS=0
FAIL=0
LOG="/tmp/phoenix_intake_repos_$$.log"

for (( i=0; i<TOTAL; i++ )); do
    f="${FILES[$i]}"
    NUM=$(( i + 1 ))
    RELPATH="${f/#$HOME/~}"
    printf "\r  [%d/%d] %-70s" "$NUM" "$TOTAL" "$RELPATH"

    if python3 "$INTAKE_PY" "$f" >> "$LOG" 2>&1; then
        PASS=$(( PASS + 1 ))
    else
        FAIL=$(( FAIL + 1 ))
        echo ""
        echo -e "  ${R}[FAIL]${N}  $f"
    fi
done

echo ""
echo ""
echo -e "  ${G}${PASS} intaked${N}  /  ${R}${FAIL} failed${N}"
[[ $FAIL -gt 0 ]] && echo -e "  Full log: ${LOG}"
echo ""
echo -e "  Check pool:    ${C}intake status${N}"
echo -e "  View Glossary: ${C}http://192.168.1.133/glossary/${N}"
echo ""
