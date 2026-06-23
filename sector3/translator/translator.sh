#!/usr/bin/env bash
# ============================================================
# translator.sh — UnitedSys Translation Layer
# Location:  /etc/systemd/system/translator.sh
# Backup:    /etc/systemd/translator.sh (sector2 failover)
# Project:   Phoenix DevOps / UnitedSys
# Author:    jwl247 / Phoenix DevOps LLC
# License:   GPL-3.0
# ============================================================
# PURPOSE:
#   Acts as the universal glue between UnitedSys commands and
#   native package backends. Windows peers route through here.
#   Output is translated back up the chain on completion.
#   Sector2 (/etc/systemd) backs this up under high traffic.
# ============================================================

set -euo pipefail

# ── Config ──────────────────────────────────────────────────
CATALOG_DB="${HOME}/.catalog/catalog.db"
SECTOR2="/etc/systemd/translator.sh"
SECTOR3="/etc/systemd/system/translator.sh"
LOG_DIR="${HOME}/.unitedsys/logs"
LOG_FILE="${LOG_DIR}/translator.log"
TRAFFIC_THRESHOLD=10   # jobs in queue before sector2 kicks in
VERSION="0.1.0"

# ── Bootstrap ───────────────────────────────────────────────
mkdir -p "${LOG_DIR}"
mkdir -p "$(dirname "${CATALOG_DB}")"

# ── Logging ─────────────────────────────────────────────────
log() {
    local level="$1"; shift
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [${level}] $*" | tee -a "${LOG_FILE}"
}

# ── Sector2 Failover Check ───────────────────────────────────
# If job queue is high, hand off to sector2 backup instance
check_failover() {
    local queue_depth
    queue_depth=$(jobs -p 2>/dev/null | wc -l)
    if [[ "${queue_depth}" -ge "${TRAFFIC_THRESHOLD}" ]]; then
        log "WARN" "Traffic at ${queue_depth} jobs — failing over to sector2"
        if [[ -x "${SECTOR2}" && "${SECTOR2}" != "${BASH_SOURCE[0]}" ]]; then
            exec "${SECTOR2}" "$@"
        else
            log "WARN" "Sector2 unavailable or same instance — continuing in sector3"
        fi
    fi
}

# ── Backend Detection ────────────────────────────────────────
detect_backend() {
    # Linux-native backends (WSL2 or bare metal)
    command -v apt-get  &>/dev/null && echo "apt"    && return 0
    command -v dnf      &>/dev/null && echo "dnf"    && return 0
    command -v pacman   &>/dev/null && echo "pacman" && return 0
    command -v zypper   &>/dev/null && echo "zypper" && return 0
    command -v apk      &>/dev/null && echo "apk"    && return 0
    command -v xbps-install &>/dev/null && echo "xbps" && return 0
    command -v emerge   &>/dev/null && echo "portage" && return 0

    # Windows peer backends (via WSL2 interop or native Win10)
    command -v winget.exe &>/dev/null && echo "winget" && return 0
    command -v choco.exe  &>/dev/null && echo "choco"  && return 0
    command -v winget     &>/dev/null && echo "winget" && return 0
    command -v choco      &>/dev/null && echo "choco"  && return 0

    echo "unknown"
    return 1
}

# ── Command Translation Table ────────────────────────────────
# Translates UnitedSys verbs → native backend commands
# Usage: translate_cmd <backend> <verb> <package>
translate_cmd() {
    local backend="$1"
    local verb="$2"
    local pkg="${3:-}"

    case "${backend}" in
        apt)
            case "${verb}" in
                install)   echo "apt-get install -y ${pkg}" ;;
                remove)    echo "apt-get remove -y ${pkg}" ;;
                update)    echo "apt-get update" ;;
                upgrade)   echo "apt-get upgrade -y" ;;
                search)    echo "apt-cache search ${pkg}" ;;
                info)      echo "apt-cache show ${pkg}" ;;
                list)      echo "dpkg --get-selections" ;;
                clean)     echo "apt-get autoremove -y && apt-get clean" ;;
                *)         echo "UNKNOWN_VERB:${verb}" ; return 1 ;;
            esac ;;
        dnf)
            case "${verb}" in
                install)   echo "dnf install -y ${pkg}" ;;
                remove)    echo "dnf remove -y ${pkg}" ;;
                update)    echo "dnf check-update" ;;
                upgrade)   echo "dnf upgrade -y" ;;
                search)    echo "dnf search ${pkg}" ;;
                info)      echo "dnf info ${pkg}" ;;
                list)      echo "dnf list installed" ;;
                clean)     echo "dnf autoremove -y && dnf clean all" ;;
                *)         echo "UNKNOWN_VERB:${verb}" ; return 1 ;;
            esac ;;
        pacman)
            case "${verb}" in
                install)   echo "pacman -S --noconfirm ${pkg}" ;;
                remove)    echo "pacman -R --noconfirm ${pkg}" ;;
                update)    echo "pacman -Sy" ;;
                upgrade)   echo "pacman -Syu --noconfirm" ;;
                search)    echo "pacman -Ss ${pkg}" ;;
                info)      echo "pacman -Si ${pkg}" ;;
                list)      echo "pacman -Q" ;;
                clean)     echo "pacman -Sc --noconfirm" ;;
                *)         echo "UNKNOWN_VERB:${verb}" ; return 1 ;;
            esac ;;
        zypper)
            case "${verb}" in
                install)   echo "zypper install -y ${pkg}" ;;
                remove)    echo "zypper remove -y ${pkg}" ;;
                update)    echo "zypper refresh" ;;
                upgrade)   echo "zypper update -y" ;;
                search)    echo "zypper search ${pkg}" ;;
                info)      echo "zypper info ${pkg}" ;;
                list)      echo "zypper packages --installed-only" ;;
                clean)     echo "zypper clean" ;;
                *)         echo "UNKNOWN_VERB:${verb}" ; return 1 ;;
            esac ;;
        apk)
            case "${verb}" in
                install)   echo "apk add ${pkg}" ;;
                remove)    echo "apk del ${pkg}" ;;
                update)    echo "apk update" ;;
                upgrade)   echo "apk upgrade" ;;
                search)    echo "apk search ${pkg}" ;;
                info)      echo "apk info ${pkg}" ;;
                list)      echo "apk list --installed" ;;
                clean)     echo "apk cache clean" ;;
                *)         echo "UNKNOWN_VERB:${verb}" ; return 1 ;;
            esac ;;
        xbps)
            case "${verb}" in
                install)   echo "xbps-install -Sy ${pkg}" ;;
                remove)    echo "xbps-remove -Ry ${pkg}" ;;
                update)    echo "xbps-install -Su" ;;
                upgrade)   echo "xbps-install -Su" ;;
                search)    echo "xbps-query -Rs ${pkg}" ;;
                info)      echo "xbps-query -RS ${pkg}" ;;
                list)      echo "xbps-query -l" ;;
                clean)     echo "xbps-remove -Oo" ;;
                *)         echo "UNKNOWN_VERB:${verb}" ; return 1 ;;
            esac ;;
        portage)
            case "${verb}" in
                install)   echo "emerge ${pkg}" ;;
                remove)    echo "emerge --unmerge ${pkg}" ;;
                update)    echo "emerge --sync" ;;
                upgrade)   echo "emerge -uDN @world" ;;
                search)    echo "emerge --search ${pkg}" ;;
                info)      echo "emerge --info ${pkg}" ;;
                list)      echo "qlist -I" ;;
                clean)     echo "emerge --depclean" ;;
                *)         echo "UNKNOWN_VERB:${verb}" ; return 1 ;;
            esac ;;
        winget)
            case "${verb}" in
                install)   echo "winget install ${pkg}" ;;
                remove)    echo "winget uninstall ${pkg}" ;;
                update)    echo "winget upgrade" ;;
                upgrade)   echo "winget upgrade --all" ;;
                search)    echo "winget search ${pkg}" ;;
                info)      echo "winget show ${pkg}" ;;
                list)      echo "winget list" ;;
                clean)     echo "echo 'winget: no clean verb'" ;;
                *)         echo "UNKNOWN_VERB:${verb}" ; return 1 ;;
            esac ;;
        choco)
            case "${verb}" in
                install)   echo "choco install ${pkg} -y" ;;
                remove)    echo "choco uninstall ${pkg} -y" ;;
                update)    echo "choco outdated" ;;
                upgrade)   echo "choco upgrade all -y" ;;
                search)    echo "choco search ${pkg}" ;;
                info)      echo "choco info ${pkg}" ;;
                list)      echo "choco list --local-only" ;;
                clean)     echo "echo 'choco: no clean verb'" ;;
                *)         echo "UNKNOWN_VERB:${verb}" ; return 1 ;;
            esac ;;
        *)
            log "ERROR" "Unknown backend: ${backend}"
            return 1 ;;
    esac
}

# ── Catalog Logger ───────────────────────────────────────────
# Writes every transaction to SQLite catalog.db
catalog_log() {
    local backend="$1"
    local verb="$2"
    local pkg="$3"
    local status="$4"
    local native_cmd="$5"

    sqlite3 "${CATALOG_DB}" 2>/dev/null <<SQL
CREATE TABLE IF NOT EXISTS translations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT    NOT NULL,
    backend     TEXT    NOT NULL,
    verb        TEXT    NOT NULL,
    package     TEXT,
    native_cmd  TEXT,
    status      TEXT,
    host        TEXT
);
INSERT INTO translations (timestamp, backend, verb, package, native_cmd, status, host)
VALUES (
    '$(date -u +"%Y-%m-%dT%H:%M:%SZ")',
    '${backend}',
    '${verb}',
    '${pkg}',
    '${native_cmd}',
    '${status}',
    '$(hostname)'
);
SQL
}

# ── Output Translator ────────────────────────────────────────
# Normalizes native backend output back to UnitedSys format
translate_output() {
    local backend="$1"
    local raw_output="$2"

    # Normalize common patterns across backends
    echo "${raw_output}" \
        | sed 's/^Reading package lists.*$/[US] Refreshing index.../g' \
        | sed 's/^Fetched /[US] Fetched /g' \
        | sed 's/^Setting up /[US] Configuring /g' \
        | sed 's/^error:/[US:ERROR]/g' \
        | sed 's/^warning:/[US:WARN]/g' \
        | sed 's/^Cannot find /[US:MISS] Package not found: /g' \
        | sed "s/^/${backend}> /g"
}

# ── Main Dispatcher ──────────────────────────────────────────
main() {
    local verb="${1:-help}"
    local pkg="${2:-}"

    # Failover check before doing anything
    check_failover "$@"

    log "INFO" "translator.sh v${VERSION} — verb: ${verb} pkg: ${pkg:-none}"

    # Detect backend
    local backend
    backend=$(detect_backend)
    if [[ "${backend}" == "unknown" ]]; then
        log "ERROR" "No supported package backend found on this system"
        exit 1
    fi
    log "INFO" "Backend detected: ${backend}"

    # Translate verb to native command
    local native_cmd
    if ! native_cmd=$(translate_cmd "${backend}" "${verb}" "${pkg}"); then
        log "ERROR" "Cannot translate verb '${verb}' for backend '${backend}'"
        catalog_log "${backend}" "${verb}" "${pkg}" "TRANSLATE_FAIL" ""
        exit 1
    fi
    log "INFO" "Translated: [${verb} ${pkg}] → [${native_cmd}]"

    # Execute
    local raw_output exit_code
    raw_output=$(eval "${native_cmd}" 2>&1) && exit_code=0 || exit_code=$?

    # Translate output back up the chain
    translate_output "${backend}" "${raw_output}"

    # Log to catalog
    local status="OK"
    [[ "${exit_code}" -ne 0 ]] && status="FAIL:${exit_code}"
    catalog_log "${backend}" "${verb}" "${pkg}" "${status}" "${native_cmd}"

    log "INFO" "Done — status: ${status}"
    return "${exit_code}"
}

# ── Help ─────────────────────────────────────────────────────
show_help() {
    cat <<EOF
translator.sh v${VERSION} — UnitedSys Translation Layer
Usage: translator.sh <verb> [package]

Verbs:
  install <pkg>   Install a package
  remove  <pkg>   Remove a package
  update          Refresh package index
  upgrade         Upgrade all packages
  search  <pkg>   Search for a package
  info    <pkg>   Show package info
  list            List installed packages
  clean           Clean package cache

Backends supported:
  apt | dnf | pacman | zypper | apk | xbps | portage | winget | choco

Sector failover: sector2 (/etc/systemd) activates at ${TRAFFIC_THRESHOLD}+ queued jobs
Catalog:         ${CATALOG_DB}
Logs:            ${LOG_FILE}
EOF
}

# ── Entry ────────────────────────────────────────────────────
case "${1:-help}" in
    help|--help|-h) show_help ;;
    *)              main "$@" ;;
esac
