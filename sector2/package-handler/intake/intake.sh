#!/usr/bin/env bash
# ============================================================
# intake.sh — Phoenix DevOps / UnitedSys
# Location:  /store/scripts/intake
# Project:   Phoenix DevOps / UnitedSys
# Author:    jwl247 / Phoenix DevOps LLC
# License:   GPL-3.0
# Version:   1.2.0
# ============================================================
# PURPOSE:
#   Universal intake pipeline for Phoenix clonepool.
#   Accepts any file, package, config, api def, service unit.
#   Self-registers on first run.
#   Reports all operations to D1 via packages-worker.
#   Companion-aware — .service, .conf, .env, .yaml travel
#   with their parent file as one versioned unit.
# ============================================================
# PIPELINE:
#   1. detect filetype + companions
#   2. generate hex from name + path
#   3. write basic sidecar first (always succeeds)
#   4. enrich sidecar with Python (full metadata)
#   5. version and store in clonepool
#   6. write custody receipt locally
#   7. POST to packages-worker → D1
# ============================================================

set -euo pipefail

# ── Python path (Windows Git Bash) ───────────────────────────
export PATH="/c/Users/jwlef/AppData/Local/Programs/Python/Python313:${PATH}"

# ── Version ───────────────────────────────────────────────────
VERSION="1.2.0"
SCRIPT_NAME="intake"
SCRIPT_HEX="737363726970747332f696e74616b65"

# ── Config ────────────────────────────────────────────────────
CLONEPOOL_DIR="${CLONEPOOL_DIR:-${HOME}/Phoenix/clonepool}"
CATALOG_DB="${HOME}/.catalog/catalog.db"
LOG_DIR="${HOME}/.unitedsys/logs"
LOG_FILE="${LOG_DIR}/intake.log"

# ── Packages Worker ───────────────────────────────────────────
WORKER_URL="${PHOENIX_WORKER_URL:-https://packages-worker.phoenix-jwl.workers.dev}"
PHOENIX_AUTH="${PHOENIX_AUTH:-}"

# ── Bootstrap ─────────────────────────────────────────────────
mkdir -p "${LOG_DIR}"
mkdir -p "${CLONEPOOL_DIR}"
mkdir -p "$(dirname "${CATALOG_DB}")"

# ── Logging ───────────────────────────────────────────────────
log() {
    local level="$1"; shift
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [intake:${level}] $*" | tee -a "${LOG_FILE}"
}

# ── Hex helpers ───────────────────────────────────────────────
to_hex() {
    echo -n "$1" | xxd -p | tr -d '\n'
}

from_hex() {
    echo -n "$1" | xxd -r -p 2>/dev/null
}

# ── File size (cross platform) ────────────────────────────────
get_size() {
    local f="$1"
    wc -c < "${f}" 2>/dev/null | tr -d ' ' || echo "0"
}

# ── Filetype detection ────────────────────────────────────────
detect_filetype() {
    local file="$1"
    local ext="${file##*.}"
    case "${ext,,}" in
        sh|bash|zsh)     echo "script:shell" ;;
        py)              echo "script:python" ;;
        js|mjs|cjs)      echo "script:javascript" ;;
        ts)              echo "script:typescript" ;;
        json)            echo "config:json" ;;
        yaml|yml)        echo "config:yaml" ;;
        toml)            echo "config:toml" ;;
        env)             echo "config:env" ;;
        conf|cfg|ini)    echo "config:conf" ;;
        service)         echo "systemd:service" ;;
        timer)           echo "systemd:timer" ;;
        socket)          echo "systemd:socket" ;;
        sql)             echo "database:sql" ;;
        md|markdown)     echo "docs:markdown" ;;
        txt)             echo "docs:text" ;;
        xml)             echo "config:xml" ;;
        html|htm)        echo "web:html" ;;
        css)             echo "web:css" ;;
        c|h)             echo "source:c" ;;
        cpp|hpp)         echo "source:cpp" ;;
        rs)              echo "source:rust" ;;
        go)              echo "source:go" ;;
        *)               echo "unknown:unknown" ;;
    esac
}

# ── Category from filetype ────────────────────────────────────
filetype_to_category() {
    local filetype="$1"
    case "${filetype}" in
        script:*)        echo "73637269707473" ;;   # scripts
        config:*)        echo "6461746162617365" ;; # database
        systemd:*)       echo "73797374656d" ;;     # system
        database:*)      echo "6461746162617365" ;; # database
        docs:*)          echo "6d65646961" ;;       # media
        web:*)           echo "776f726b657273" ;;   # workers
        source:c)        echo "737562737973" ;;     # subsystem
        binary:*)        echo "7061636b61676573" ;; # packages
        *)               echo "756e6b6e6f776e" ;;   # unknown
    esac
}

# ── Companion detection ───────────────────────────────────────
detect_companions() {
    local filepath="$1"
    local dir
    dir=$(dirname "${filepath}")
    local base
    base=$(basename "${filepath}")
    local name="${base%.*}"
    local companion_exts=("service" "timer" "socket" "conf" "env" "yaml" "yml" "toml" "json" "md")
    for ext in "${companion_exts[@]}"; do
        local candidate="${dir}/${name}.${ext}"
        if [[ -f "${candidate}" && "${candidate}" != "${filepath}" ]]; then
            echo "${candidate}"
            log "INFO" "companion found: ${candidate}"
        fi
    done
}

# ── Version bump ──────────────────────────────────────────────
get_next_version() {
    local dir="$1"
    if [[ ! -d "${dir}" ]]; then
        echo "v1"
        return
    fi
    local files
    files=$(ls "${dir}"/v*_* 2>/dev/null || true)
    if [[ -z "${files}" ]]; then
        echo "v1"
        return
    fi
    local last_num
    last_num=$(echo "${files}" \
        | xargs -I{} basename {} \
        | grep -oP '(?<=v)\d+' \
        | sort -n \
        | tail -1 || echo "0")
    echo "v$((last_num + 1))"
}

# ── Write basic sidecar (always succeeds — no Python needed) ──
write_sidecar_basic() {
    local sidecar="$1"
    local hex="$2"
    local orig="$3"
    local version="$4"
    local filetype="$5"
    local category_hex="$6"
    local size="$7"
    local backend="${8:-direct}"
    local notes="${9:-}"
    local now
    now=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

    mkdir -p "$(dirname "${sidecar}")"

    cat > "${sidecar}" <<SIDECAR
{
  "usys_intake": "1.2",
  "hex_name": "${hex}",
  "original_name": "${orig}",
  "state": "white",
  "version": "${version}",
  "filetype": "${filetype}",
  "category_hex": "${category_hex}",
  "size_bytes": ${size},
  "backend": "${backend}",
  "notes": "${notes}",
  "pool_path": "${CLONEPOOL_DIR}/${hex}",
  "companions": [],
  "qr": {
    "header": {"role": "state", "state": "white"},
    "footer": {"role": "location", "tier": 1}
  },
  "auto_hotswap": false,
  "registered_at": "${now}",
  "updated_at": "${now}",
  "clone_history": [{"version": "${version}", "at": "${now}"}]
}
SIDECAR
    log "INFO" "sidecar written: ${sidecar}"
}

# ── Enrich sidecar with companions (Python optional) ──────────
enrich_sidecar_companions() {
    local sidecar="$1"
    local companions_str="$2"

    command -v python3 &>/dev/null || command -v python &>/dev/null || return 0

    local py_cmd
    py_cmd=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)

    "${py_cmd}" - "${sidecar}" "${companions_str}" <<'PYEOF'
import json, sys, os

sidecar_path = sys.argv[1]
companions_str = sys.argv[2] if len(sys.argv) > 2 else ""

with open(sidecar_path) as f:
    d = json.load(f)

companions = []
if companions_str.strip():
    for line in companions_str.strip().split('\n'):
        line = line.strip()
        if not line:
            continue
        ext  = line.rsplit('.', 1)[-1] if '.' in line else 'unknown'
        name = os.path.basename(line)
        companions.append({
            'file':     name,
            'path':     line,
            'type':     ext,
            'editable': ext in ('service','timer','socket','conf','env','yaml','yml','toml','json')
        })

d['companions'] = companions

with open(sidecar_path, 'w') as f:
    json.dump(d, f, indent=2)
PYEOF
}

# ── Local custody log ─────────────────────────────────────────
custody_log_local() {
    local hex="$1" name="$2" action="$3" version="$4" \
          src="$5" dst="$6" state="$7" actor="$8"

    command -v sqlite3 &>/dev/null || return 0

    sqlite3 "${CATALOG_DB}" 2>/dev/null <<SQL
CREATE TABLE IF NOT EXISTS custody (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    hex_id      TEXT    NOT NULL,
    name        TEXT    NOT NULL,
    action      TEXT    NOT NULL,
    version     TEXT,
    source      TEXT,
    destination TEXT,
    state       TEXT    DEFAULT 'white',
    actor       TEXT    DEFAULT 'usys',
    validated   INTEGER DEFAULT 0,
    intaked_at  TEXT    DEFAULT (datetime('now'))
);
INSERT INTO custody (hex_id, name, action, version, source, destination, state, actor)
VALUES ('${hex}', '${name}', '${action}', '${version}', '${src}', '${dst}', '${state}', '${actor}');
SQL
}

# ── D1 reporter ───────────────────────────────────────────────
post_to_d1() {
    local endpoint="$1"
    local payload="$2"

    [[ -z "${PHOENIX_AUTH}" ]] && log "WARN" "PHOENIX_AUTH not set — skipping D1 report" && return 0

    local response http_code body
    response=$(curl -s -w "\n%{http_code}" \
        -X POST \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer ${PHOENIX_AUTH}" \
        -d "${payload}" \
        "${WORKER_URL}${endpoint}" 2>/dev/null)

    http_code=$(echo "${response}" | tail -1)
    body=$(echo "${response}" | head -1)

    if [[ "${http_code}" == "200" ]]; then
        log "INFO" "D1 OK → ${endpoint}"
    else
        log "WARN" "D1 failed (${http_code}) → ${endpoint}: ${body}"
    fi
}

report_clonepool() {
    local hex="$1" name="$2" version="$3" state="$4" \
          pool_path="$5" sidecar_path="$6" tier="$7" size="$8"
    post_to_d1 "/clonepool" "{\"hex_id\":\"${hex}\",\"b58\":\"${hex}\",\"name\":\"${name}\",\"version\":\"${version}\",\"state\":\"${state}\",\"pool_path\":\"${pool_path}\",\"sidecar_path\":\"${sidecar_path}\",\"tier\":${tier},\"size\":${size}}"
}

report_custody() {
    local hex="$1" name="$2" action="$3" state="$4" actor="$5"
    post_to_d1 "/custody" "{\"hex_id\":\"${hex}\",\"name\":\"${name}\",\"action\":\"${action}\",\"state\":\"${state}\",\"actor\":\"${actor}\"}"
}

report_glossary() {
    local hex="$1" name="$2" description="$3" \
          category_hex="$4" version="$5" size="$6" pool_path="$7"
    post_to_d1 "/glossary" "{\"hex\":\"${hex}\",\"name\":\"${name}\",\"description\":\"${description}\",\"category_hex\":\"${category_hex}\",\"version\":\"${version}\",\"size\":${size},\"pool_path\":\"${pool_path}\",\"state\":\"white\"}"
}

# ── Self registration ─────────────────────────────────────────
self_register() {
    local dir="${CLONEPOOL_DIR}/${SCRIPT_HEX}"
    local sidecar="${dir}/${SCRIPT_HEX}.sidecar.json"

    if [[ -f "${sidecar}" ]]; then
        log "INFO" "self: already registered"
        return 0
    fi

    log "INFO" "self: first run — registering intake into clonepool"
    mkdir -p "${dir}"

    local self_path
    self_path=$(realpath "${BASH_SOURCE[0]}" 2>/dev/null || echo "${0}")
    local size
    size=$(get_size "${self_path}")
    local version="v1"
    local now
    now=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

    # Copy self
    cp "${self_path}" "${dir}/${version}_${SCRIPT_NAME}"

    # Write sidecar — basic first, always succeeds
    write_sidecar_basic \
        "${sidecar}" \
        "${SCRIPT_HEX}" \
        "${SCRIPT_NAME}" \
        "${version}" \
        "script:shell" \
        "73637269707473" \
        "${size}" \
        "self" \
        "intake script — self registered on first run"

    # Local custody
    custody_log_local \
        "${SCRIPT_HEX}" "${SCRIPT_NAME}" \
        "self_register" "${version}" \
        "${self_path}" "${dir}/${version}_${SCRIPT_NAME}" \
        "white" "intake"

    # D1 reports
    report_clonepool \
        "${SCRIPT_HEX}" "${SCRIPT_NAME}" "${version}" "white" \
        "${dir}" "${sidecar}" "1" "${size}"

    report_custody \
        "${SCRIPT_HEX}" "${SCRIPT_NAME}" "self_register" "white" "intake"

    report_glossary \
        "${SCRIPT_HEX}" "${SCRIPT_NAME}" \
        "Intake script: registers new software into the glossary and clonepool" \
        "73637269707473" "${VERSION}" "${size}" "${dir}"

    log "INFO" "self: registration complete"
    echo "[intake:OK] Self registered: ${SCRIPT_NAME} → clonepool"
}

# ══════════════════════════════════════════════════════════════
# CORE INTAKE FUNCTION
# ══════════════════════════════════════════════════════════════
intake_file() {
    local filepath="${1:-}"
    local backend="${2:-direct}"
    local notes="${3:-}"

    if [[ -z "${filepath}" ]]; then
        echo "[intake] Usage: intake <filepath> [backend] [notes]"
        return 1
    fi

    if [[ ! -f "${filepath}" ]]; then
        echo "[intake:MISS] File not found: ${filepath}"
        return 1
    fi

    local orig
    orig=$(basename "${filepath}")
    local hex
    hex=$(to_hex "${orig}")
    local pool_dir="${CLONEPOOL_DIR}/${hex}"
    local sidecar="${pool_dir}/${hex}.sidecar.json"

    mkdir -p "${pool_dir}"

    local version
    version=$(get_next_version "${pool_dir}")

    local filetype
    filetype=$(detect_filetype "${orig}")
    local category_hex
    category_hex=$(filetype_to_category "${filetype}")

    local size
    size=$(get_size "${filepath}")

    log "INFO" "intaking: ${orig} (${filetype}) as ${version}"

    # ── Companions ──────────────────────────────────────────
    local companion_list=""
    companion_list=$(detect_companions "${filepath}" || true)

    # Copy companions
    if [[ -n "${companion_list}" ]]; then
        while IFS= read -r companion; do
            [[ -z "${companion}" ]] && continue
            local comp_name
            comp_name=$(basename "${companion}")
            cp "${companion}" "${pool_dir}/${version}_${comp_name}"
            log "INFO" "companion intaked: ${comp_name}"
        done <<< "${companion_list}"
    fi

    # ── Copy main file ───────────────────────────────────────
    cp "${filepath}" "${pool_dir}/${version}_${orig}"
    log "INFO" "stored: ${pool_dir}/${version}_${orig}"

    # ── Write basic sidecar first — always succeeds ──────────
    write_sidecar_basic \
        "${sidecar}" "${hex}" "${orig}" "${version}" \
        "${filetype}" "${category_hex}" "${size}" \
        "${backend}" "${notes}"

    # ── Enrich with companions (Python optional) ─────────────
    enrich_sidecar_companions "${sidecar}" "${companion_list}"

    # ── Local custody ────────────────────────────────────────
    custody_log_local \
        "${hex}" "${orig}" "intake" "${version}" \
        "${filepath}" "${pool_dir}/${version}_${orig}" \
        "white" "${backend}"

    # ── D1 reports ───────────────────────────────────────────
    report_clonepool \
        "${hex}" "${orig}" "${version}" "white" \
        "${pool_dir}" "${sidecar}" "1" "${size}"

    report_custody \
        "${hex}" "${orig}" "intake" "white" "${backend}"

    report_glossary \
        "${hex}" "${orig}" \
        "Intaked via ${backend}: ${filetype}" \
        "${category_hex}" "${version}" "${size}" "${pool_dir}"

    echo "[intake:OK] ${orig} → clonepool ${version}"
    echo "[intake:OK] hex:  ${hex}"
    echo "[intake:OK] type: ${filetype}"
    [[ -n "${companion_list}" ]] && \
        echo "[intake:OK] companions: $(echo "${companion_list}" | wc -l | tr -d ' ')"
    return 0
}

# ── Intake from backend install ───────────────────────────────
intake_from_backend() {
    local pkg_name="${1:-}"
    local backend="${2:-unknown}"
    local version="${3:-unknown}"
    local install_path="${4:-}"

    if [[ -z "${pkg_name}" ]]; then
        echo "[intake] Usage: intake backend <pkg_name> <backend> <version> [install_path]"
        return 1
    fi

    log "INFO" "backend intake: ${pkg_name} from ${backend} ${version}"

    if [[ -n "${install_path}" && -f "${install_path}" ]]; then
        intake_file "${install_path}" "${backend}" "installed from ${backend} ${version}"
        return $?
    fi

    local hex
    hex=$(to_hex "${pkg_name}")
    local pool_dir="${CLONEPOOL_DIR}/${hex}"
    local sidecar="${pool_dir}/${hex}.sidecar.json"
    mkdir -p "${pool_dir}"

    write_sidecar_basic \
        "${sidecar}" "${hex}" "${pkg_name}" "${version}" \
        "package:${backend}" "7061636b61676573" "0" \
        "${backend}" "installed from ${backend}"

    custody_log_local \
        "${hex}" "${pkg_name}" "backend_install" "${version}" \
        "${backend}" "${pool_dir}" "white" "${backend}"

    report_clonepool \
        "${hex}" "${pkg_name}" "${version}" "white" \
        "${pool_dir}" "${sidecar}" "1" "0"
		grep -n "report_clonepool()" intake.sh

    report_custody \
        "${hex}" "${pkg_name}" "backend_install" "white" "${backend}"

    report_glossary \
        "${hex}" "${pkg_name}" \
        "Package installed from ${backend} v${version}" \
        "7061636b61676573" "${version}" "0" "${pool_dir}"

    echo "[intake:OK] ${pkg_name} (${backend} ${version}) → D1"
}

# ── Status ────────────────────────────────────────────────────
intake_status() {
    local total
    total=$(find "${CLONEPOOL_DIR}" -name "*.sidecar.json" 2>/dev/null | wc -l | tr -d ' ')
    local white grey black
    white=$(find "${CLONEPOOL_DIR}" -name "*.sidecar.json" -exec grep -l '"state": "white"' {} \; 2>/dev/null | wc -l | tr -d ' ')
    grey=$(find  "${CLONEPOOL_DIR}" -name "*.sidecar.json" -exec grep -l '"state": "grey"'  {} \; 2>/dev/null | wc -l | tr -d ' ')
    black=$(find "${CLONEPOOL_DIR}" -name "*.sidecar.json" -exec grep -l '"state": "black"' {} \; 2>/dev/null | wc -l | tr -d ' ')

    echo ""
    echo "  ╔══════════════════════════════════════╗"
    echo "  ║         INTAKE / CLONEPOOL           ║"
    echo "  ╚══════════════════════════════════════╝"
    echo "  Worker : ${WORKER_URL}"
    echo "  Pool   : ${CLONEPOOL_DIR}"
    echo "  Total  : ${total}"
    echo "  White  : ${white} (active)"
    echo "  Grey   : ${grey} (deprecated)"
    echo "  Black  : ${black} (retired)"
    echo ""
}

# ── Help ──────────────────────────────────────────────────────
show_help() {
    cat <<EOF

  ██╗███╗   ██╗████████╗ █████╗ ██╗  ██╗███████╗
  ██║████╗  ██║╚══██╔══╝██╔══██╗██║ ██╔╝██╔════╝
  ██║██╔██╗ ██║   ██║   ███████║█████╔╝ █████╗
  ██║██║╚██╗██║   ██║   ██╔══██║██╔═██╗ ██╔══╝
  ██║██║ ╚████║   ██║   ██║  ██║██║  ██╗███████╗
  ╚═╝╚═╝  ╚═══╝   ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝
  Phoenix DevOps — intake v${VERSION}

  Usage:
    intake <file> [backend] [notes]    Intake a file into clonepool
    intake backend <pkg> <be> <ver>    Register a backend-installed package
    intake status                      Show clonepool status
    intake help                        This screen

  Examples:
    intake ./nginx.conf                         Direct file intake
    intake ./franken.py scripts "Frank v2"      With backend + notes
    intake ./nginx.sh                           Auto-detects companions
    intake backend nodejs winget 20.11.0        Backend package registration

  Pipeline:
    file → hex → sidecar → clonepool → custody → D1

  Worker : ${WORKER_URL}
  Pool   : ${CLONEPOOL_DIR}
  Log    : ${LOG_FILE}

EOF
}

# ── Self register on every run ────────────────────────────────
self_register

# ── Entry ─────────────────────────────────────────────────────
case "${1:-help}" in
    help|--help|-h) show_help ;;
    status)         intake_status ;;
    backend)        shift; intake_from_backend "$@" ;;
    *)              intake_file "$@" ;;
esac