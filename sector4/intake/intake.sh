#!/usr/bin/env zsh
# =============================================================================
# intake.sh -- Phoenix DevOps TAV Intake Shell Wrapper
# Author:  jwl247 / Phoenix DevOps LLC
# Sector:  4 (breach_coms4 / master vault)
# Role:    Shell entry point for TAV intake. Calls intake.py for single files
#          or directories. Validates vault mount before touching breach_coms4.
# =============================================================================

set -uo pipefail

VAULT_MOUNT="/mnt/g"
CATALOG_DB="${HOME}/.catalog/catalog.db"
LOG_DIR="${HOME}/.unitedsys/logs"
LOG_FILE="${LOG_DIR}/intake.log"
INTAKE_PY="${PHOENIX_INSTALL_DIR:-${HOME}/phoenix-devops}/unitedsys/core/intake.py"
VERSION="0.1.0"

mkdir -p "${LOG_DIR}"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "${LOG_FILE}" }
die() { log "ERROR: $*"; exit 1 }

check_vault() {
    [[ -d "${VAULT_MOUNT}" ]] || die "breach_coms4 not mounted at ${VAULT_MOUNT} -- run: sudo mount -a"
    log "vault OK: ${VAULT_MOUNT}"
}

check_python() {
    [[ -f "${INTAKE_PY}" ]] || die "intake.py not found at ${INTAKE_PY}"
}

cmd_file() {
    local target="$1"
    [[ -f "${target}" ]] || die "Not a file: ${target}"
    check_vault
    check_python
    log "intake: ${target}"
    python3 "${INTAKE_PY}" "${target}"
}

cmd_dir() {
    local target="$1"
    [[ -d "${target}" ]] || die "Not a directory: ${target}"
    check_vault
    check_python
    log "intake-dir: ${target}"
    local count=0
    for f in "${target}"/**/*(.); do
        python3 "${INTAKE_PY}" "${f}" && (( count++ ))
    done
    log "intake-dir complete: ${count} files processed"
}

cmd_status() {
    echo "intake.sh v${VERSION}"
    echo ""
    echo "-- Vault mount --"
    [[ -d "${VAULT_MOUNT}" ]] && echo "  [OK] ${VAULT_MOUNT}" || echo "  [!!] NOT MOUNTED: ${VAULT_MOUNT}"
    echo ""
    echo "-- Catalog --"
    [[ -f "${CATALOG_DB}" ]] && sqlite3 "${CATALOG_DB}" \
        "SELECT COUNT(*) || ' packages in catalog' FROM packages;" 2>/dev/null \
        || echo "  catalog.db not yet initialized"
    echo ""
    echo "-- intake.py --"
    [[ -f "${INTAKE_PY}" ]] && echo "  [OK] ${INTAKE_PY}" || echo "  [!!] MISSING: ${INTAKE_PY}"
}

cmd_help() {
    echo "intake.sh v${VERSION} -- TAV intake for Phoenix DevOps"
    echo ""
    echo "Usage:"
    echo "  intake.sh file <path>      intake a single file (SHA3-512 + dual QR)"
    echo "  intake.sh dir  <path>      intake all files in a directory"
    echo "  intake.sh status           check vault mount + catalog"
    echo "  intake.sh help             this message"
    echo ""
    echo "Vault: ${VAULT_MOUNT} (breach_coms4)"
    echo "Log:   ${LOG_FILE}"
}

case "${1:-help}" in
    file)   [[ $# -ge 2 ]] || die "Usage: intake.sh file <path>"; cmd_file "$2" ;;
    dir)    [[ $# -ge 2 ]] || die "Usage: intake.sh dir <path>";  cmd_dir  "$2" ;;
    status) cmd_status ;;
    help)   cmd_help ;;
    *)      die "Unknown command: $1 -- run: intake.sh help" ;;
esac
