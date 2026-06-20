#!/usr/bin/env bash
# =============================================================================
# intake_windows.sh — Intake Windows Documents + Downloads into Phoenix
#
# Intakes all files from both folders. Skips only compiled binary artifacts
# (.pyc .class) and junk temp files — everything else goes in.
# Uses intake.py directly (breach_coms4 is on phoenix-ext, not WSL;
# clonepool + D1 sync work fine from WSL.)
#
# Usage:
#   bash ~/phoenix-devops/scripts/intake_windows.sh            # dry run (safe)
#   bash ~/phoenix-devops/scripts/intake_windows.sh --run      # real intake
#   bash ~/phoenix-devops/scripts/intake_windows.sh --run --days 30
# =============================================================================

set -euo pipefail

DOCS="/mnt/c/Users/jwlef/Documents"
DOWN="/mnt/c/Users/jwlef/Downloads"
INTAKE_PY="${PHOENIX_INSTALL_DIR:-${HOME}/phoenix-devops}/unitedsys/core/intake.py"

# Skip only compiled artifacts and OS junk — not real files
SKIP_EXT="pyc|class|lnk|tmp|crdownload|part|DS_Store|Thumbs.db"
SKIP_DIRS=".git|__pycache__|node_modules"

DRY_RUN=true
DAYS=60

for arg in "${@:-}"; do
    case "$arg" in
        --run)      DRY_RUN=false ;;
        --dry-run)  DRY_RUN=true ;;
        --days=*)   DAYS="${arg#--days=}" ;;
    esac
done

G="\033[0;32m"; Y="\033[0;33m"; R="\033[0;31m"; C="\033[0;36m"
B="\033[1m"; N="\033[0m"

echo ""
if [[ "$DRY_RUN" == true ]]; then
    echo -e "${B}${Y}DRY RUN — nothing will be intaked. Pass --run to execute.${N}"
else
    echo -e "${B}${G}LIVE RUN — intaking files into Phoenix clonepool + D1${N}"
fi
echo -e "${B}Phoenix Windows Intake${N}  (last ${DAYS} days)  $(date '+%Y-%m-%d %H:%M')"
echo ""

# Load env
[[ -f "${HOME}/.phoenix_env" ]] && source "${HOME}/.phoenix_env" 2>/dev/null

if [[ ! -f "$INTAKE_PY" ]]; then
    echo -e "  ${R}[FAIL]${N}  intake.py not found at $INTAKE_PY"
    exit 1
fi

REF_FILE="/tmp/phoenix_intake_ref_$$"
touch -d "${DAYS} days ago" "$REF_FILE" 2>/dev/null \
    || touch -t "$(date -d "${DAYS} days ago" '+%Y%m%d%H%M')" "$REF_FILE" 2>/dev/null
trap "rm -f $REF_FILE" EXIT

collect_files() {
    local base="$1"
    find "$base" -type f -newer "$REF_FILE" 2>/dev/null \
        | grep -vE "/($SKIP_DIRS)/" \
        | grep -vE "\.($SKIP_EXT)$" \
        || true
}

FILES=()

echo -e "${C}Scanning Documents (recursive)...${N}"
while IFS= read -r f; do FILES+=("$f"); done < <(collect_files "$DOCS")
echo -e "  ${#FILES[@]} files"

PREV=${#FILES[@]}
echo -e "${C}Scanning Downloads (recursive — all subdirs)...${N}"
while IFS= read -r f; do FILES+=("$f"); done < <(collect_files "$DOWN")
DOWN_COUNT=$(( ${#FILES[@]} - PREV ))
echo -e "  ${DOWN_COUNT} files"

TOTAL=${#FILES[@]}
echo ""
echo -e "${B}Total: ${TOTAL} files to intake${N}"
echo ""

if [[ "$DRY_RUN" == true ]]; then
    echo -e "${Y}Sample (first 40):${N}"
    for (( i=0; i<40 && i<TOTAL; i++ )); do
        echo "  ${FILES[$i]}"
    done
    [[ $TOTAL -gt 40 ]] && echo "  ... and $(( TOTAL - 40 )) more"
    echo ""
    echo -e "Run with ${B}--run${N} to execute."
    exit 0
fi

# ── Live intake ───────────────────────────────────────────────────────────────

PASS=0
FAIL=0
LOG="/tmp/phoenix_intake_$$.log"

for (( i=0; i<TOTAL; i++ )); do
    f="${FILES[$i]}"
    NUM=$(( i + 1 ))
    printf "\r  [%d/%d] %-60s" "$NUM" "$TOTAL" "$(basename "$f")"

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
