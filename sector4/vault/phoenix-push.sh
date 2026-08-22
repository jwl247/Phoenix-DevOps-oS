#!/usr/bin/env zsh
# =============================================================================
# phoenix-push.sh -- Phoenix DevOps Vault Push
# Author:  jwl247 / Phoenix DevOps LLC
# Sector:  4 (breach_coms4 / master vault)
# Role:    Pushes files or directories INTO breach_coms4 CLONEPOOL via rsync.
#          Never overwrites existing vault objects (append-only).
#          RULE: breach_coms4 is the master vault -- never delete from it.
# =============================================================================

set -uo pipefail

VAULT="/mnt/g"
CLONEPOOL="${VAULT}/CLONEPOOL"
CATALOG_DB="${HOME}/.catalog/catalog.db"
LOG_DIR="${HOME}/.unitedsys/logs"
LOG_FILE="${LOG_DIR}/phoenix-push.log"
VERSION="0.1.0"

mkdir -p "${LOG_DIR}"

log()  { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "${LOG_FILE}" }
die()  { log "ERROR: $*"; exit 1 }
ok()   { log "OK: $*" }
warn() { log "WARN: $*" }

check_vault() {
    [[ -d "${VAULT}" ]] || die "breach_coms4 not mounted at ${VAULT} -- run: sudo mount -a"
    mkdir -p "${CLONEPOOL}"
    ok "vault: ${VAULT}"
}

catalog_push() {
    local src="$1" dst="$2"
    sqlite3 "${CATALOG_DB}" 2>/dev/null <<SQL || warn "catalog log failed"
CREATE TABLE IF NOT EXISTS vault_pushes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT, source TEXT, dest TEXT
);
INSERT INTO vault_pushes (timestamp, source, dest)
VALUES ('$(date -u +"%Y-%m-%dT%H:%M:%SZ")', '${src}', '${dst}');
SQL
}

push_target() {
    local src="$1"
    local dst="${CLONEPOOL}/$(basename ${src})"
    if [[ -e "${dst}" ]]; then
        warn "already in vault: ${dst} -- skipping (vault is append-only)"
        return
    fi
    log "pushing: ${src} -> ${dst}"
    rsync -a --progress "${src}" "${dst}" \
        && ok "pushed: $(basename ${src})" \
        && catalog_push "${src}" "${dst}" \
        || die "rsync failed: ${src}"
}

cmd_push() {
    check_vault
    for target in "$@"; do
        if [[ -f "${target}" || -d "${target}" ]]; then
            push_target "${target}"
        else
            warn "not found: ${target}"
        fi
    done
}

cmd_status() {
    echo "phoenix-push.sh v${VERSION}"
    echo ""
    echo "-- Vault --"
    [[ -d "${VAULT}" ]] && echo "  [OK] ${VAULT} (breach_coms4)" || echo "  [!!] NOT MOUNTED: ${VAULT}"
    [[ -d "${CLONEPOOL}" ]] && {
        local count
        count=$(find "${CLONEPOOL}" -maxdepth 1 -mindepth 1 | wc -l)
        echo "  CLONEPOOL: ${count} objects"
    }
    echo ""
    echo "-- Recent pushes --"
    sqlite3 "${CATALOG_DB}" 2>/dev/null \
        "SELECT timestamp, source FROM vault_pushes ORDER BY id DESC LIMIT 5;" \
        || echo "  catalog not available"
}

cmd_help() {
    echo "phoenix-push.sh v${VERSION} -- push files to breach_coms4 vault"
    echo ""
    echo "Usage:"
    echo "  phoenix-push.sh push <file|dir> [...]   push to CLONEPOOL (never overwrites)"
    echo "  phoenix-push.sh status                  vault mount + recent pushes"
    echo "  phoenix-push.sh help                    this message"
    echo ""
    echo "Vault:     ${VAULT} (breach_coms4)"
    echo "Clonepool: ${CLONEPOOL}"
    echo "Log:       ${LOG_FILE}"
    echo ""
    echo "RULE: breach_coms4 is the master vault. Nothing is ever deleted from it."
}

case "${1:-help}" in
    push)
        shift
        [[ $# -ge 1 ]] || die "Usage: phoenix-push.sh push <file|dir> [...]"
        cmd_push "$@"
        ;;
    status) cmd_status ;;
    help)   cmd_help ;;
    *)      die "Unknown command: $1 -- run: phoenix-push.sh help" ;;
esac
