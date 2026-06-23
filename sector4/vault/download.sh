#!/usr/bin/env zsh
# =============================================================================
# download.sh -- Phoenix DevOps Package Downloader
# Author:  jwl247 / Phoenix DevOps LLC
# Sector:  4 (breach_coms4 / master vault)
# Role:    Downloads packages/assets into CLONEPOOL via UnitedSys backends or
#          direct curl/wget. All downloads land in CLONEPOOL only.
#          No translation here -- output boundary is sector3.
# =============================================================================

set -uo pipefail

VAULT="/mnt/g"
CLONEPOOL="${VAULT}/CLONEPOOL"
CATALOG_DB="${HOME}/.catalog/catalog.db"
LOG_DIR="${HOME}/.unitedsys/logs"
LOG_FILE="${LOG_DIR}/download.log"
US_CORE="${HOME}/projects/unitedsys/core/us.py"
VERSION="0.1.0"

mkdir -p "${LOG_DIR}"

log()  { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "${LOG_FILE}" }
die()  { log "ERROR: $*"; exit 1 }
ok()   { log "OK: $*" }
warn() { log "WARN: $*" }

check_vault() {
    [[ -d "${VAULT}" ]] || die "breach_coms4 not mounted at ${VAULT} -- run: sudo mount -a"
    mkdir -p "${CLONEPOOL}"
}

check_network() {
    ping -c1 -W2 1.1.1.1 &>/dev/null || die "No network -- check VPN/firewall"
}

catalog_download() {
    local name="$1" src="$2" dst="$3"
    sqlite3 "${CATALOG_DB}" 2>/dev/null <<SQL || warn "catalog log failed"
CREATE TABLE IF NOT EXISTS downloads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT, name TEXT, source TEXT, dest TEXT, status TEXT
);
INSERT INTO downloads (timestamp, name, source, dest, status)
VALUES ('$(date -u +"%Y-%m-%dT%H:%M:%SZ")', '${name}', '${src}', '${dst}', 'OK');
SQL
}

download_url() {
    local url="$1"
    local filename="${2:-$(basename ${url})}"
    local dst="${CLONEPOOL}/${filename}"
    if [[ -f "${dst}" ]]; then
        warn "already in clonepool: ${filename} -- skipping"
        return
    fi
    check_network
    log "downloading: ${url}"
    if command -v curl &>/dev/null; then
        curl -fsSL --retry 3 --retry-delay 2 -o "${dst}" "${url}" \
            && ok "downloaded: ${filename}" \
            && catalog_download "${filename}" "${url}" "${dst}"
    elif command -v wget &>/dev/null; then
        wget -q --tries=3 -O "${dst}" "${url}" \
            && ok "downloaded: ${filename}" \
            && catalog_download "${filename}" "${url}" "${dst}"
    else
        die "Neither curl nor wget available"
    fi
}

download_package() {
    local pkg="$1"
    log "seeding package: ${pkg}"
    if [[ -f "${US_CORE}" ]]; then
        python3 "${US_CORE}" seed "${pkg}" \
            && ok "seeded: ${pkg}" \
            || warn "seed failed for: ${pkg}"
    else
        die "us.py not found at ${US_CORE}"
    fi
}

cmd_url() {
    check_vault
    local url="$1"
    local name="${2:-}"
    [[ -n "${name}" ]] && download_url "${url}" "${name}" || download_url "${url}"
}

cmd_pkg() {
    check_vault
    for pkg in "$@"; do
        download_package "${pkg}"
    done
}

cmd_batch() {
    local listfile="$1"
    [[ -f "${listfile}" ]] || die "File not found: ${listfile}"
    check_vault
    while IFS= read -r line || [[ -n "${line}" ]]; do
        [[ -z "${line}" || "${line}" == \#* ]] && continue
        if [[ "${line}" == http* ]]; then
            download_url "${line}"
        else
            download_package "${line}"
        fi
    done < "${listfile}"
}

cmd_status() {
    echo "download.sh v${VERSION}"
    echo ""
    echo "-- Vault --"
    [[ -d "${VAULT}" ]] && echo "  [OK] ${VAULT} (breach_coms4)" || echo "  [!!] NOT MOUNTED"
    [[ -d "${CLONEPOOL}" ]] && {
        local count
        count=$(find "${CLONEPOOL}" -maxdepth 1 -mindepth 1 | wc -l)
        echo "  CLONEPOOL: ${count} objects"
    }
    echo ""
    echo "-- Network --"
    ping -c1 -W2 1.1.1.1 &>/dev/null && echo "  [OK] network" || echo "  [!!] no network"
    echo ""
    echo "-- Recent downloads --"
    sqlite3 "${CATALOG_DB}" 2>/dev/null \
        "SELECT timestamp, name FROM downloads ORDER BY id DESC LIMIT 5;" \
        || echo "  catalog not available"
}

cmd_help() {
    echo "download.sh v${VERSION} -- download packages/assets to breach_coms4 CLONEPOOL"
    echo ""
    echo "Usage:"
    echo "  download.sh url <url> [filename]     download a URL directly"
    echo "  download.sh pkg <name> [name ...]    seed packages via UnitedSys"
    echo "  download.sh batch <listfile>         download URLs/pkgs from a file"
    echo "  download.sh status                   vault + network + recent downloads"
    echo "  download.sh help                     this message"
    echo ""
    echo "Vault:     ${VAULT} (breach_coms4)"
    echo "Clonepool: ${CLONEPOOL}"
    echo "Log:       ${LOG_FILE}"
}

case "${1:-help}" in
    url)
        [[ $# -ge 2 ]] || die "Usage: download.sh url <url> [filename]"
        shift; cmd_url "$@" ;;
    pkg)
        [[ $# -ge 2 ]] || die "Usage: download.sh pkg <name> [name ...]"
        shift; cmd_pkg "$@" ;;
    batch)
        [[ $# -ge 2 ]] || die "Usage: download.sh batch <listfile>"
        cmd_batch "$2" ;;
    status) cmd_status ;;
    help)   cmd_help ;;
    *)      die "Unknown command: $1 -- run: download.sh help" ;;
esac
