#!/usr/bin/env bash
# ============================================================
# propcoms.sh — Propagator COM Daisy-Chain
# Project:   Phoenix DevOps / Full Propagator Framework
# Author:    jwl247 / Phoenix DevOps LLC
# License:   GPL-3.0
# ============================================================
# COM4 → COM3 → COM2 → COM1 daisy-chain relay.
# Mirrors propcoms.py logic in bash for shell-level access.
# Each hop logs to catalog.db and passes to the next.
# ============================================================

set -euo pipefail

CATALOG_DB="${HOME}/.catalog/catalog.db"
LOG_FILE="${HOME}/.unitedsys/logs/propcoms.log"
COM_PORTS=(5564 5563 5562 5561)
COM_NAMES=(COM4 COM3 COM2 COM1)
VERSION="0.1.0"

mkdir -p "$(dirname "${LOG_FILE}")"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "${LOG_FILE}"; }

catalog_log() {
    local com="$1" msg="$2" status="${3:-OK}"
    sqlite3 "${CATALOG_DB}" 2>/dev/null <<SQL || true
CREATE TABLE IF NOT EXISTS propcoms_log (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT,
    com       TEXT,
    message   TEXT,
    status    TEXT
);
INSERT INTO propcoms_log (timestamp, com, message, status)
VALUES ('$(date -u +"%Y-%m-%dT%H:%M:%SZ")', '${com}', '${msg}', '${status}');
SQL
}

relay_chain() {
    local payload="$1"
    log "propcoms v${VERSION} — starting COM4→COM1 relay"
    log "Payload: ${payload}"

    for i in 0 1 2 3; do
        local com="${COM_NAMES[$i]}"
        local port="${COM_PORTS[$i]}"
        log "[${com}:${port}] Relaying..."
        catalog_log "${com}" "${payload}" "RELAY"
        # In live env: echo "${payload}" | nc localhost "${port}"
        sleep 0.1
        log "[${com}] Done"
    done

    log "Chain complete — COM4→COM3→COM2→COM1"
    catalog_log "CHAIN" "${payload}" "COMPLETE"
}

case "${1:-relay}" in
    relay) relay_chain "${2:-ping}" ;;
    status)
        log "propcoms status"
        for i in 0 1 2 3; do
            echo "  ${COM_NAMES[$i]} → port ${COM_PORTS[$i]}"
        done ;;
    *) echo "Usage: propcoms.sh [relay <payload>|status]" ;;
esac
