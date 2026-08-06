#!/usr/bin/env bash
# ============================================================
# intake.sh — Phoenix DevOps / UnitedSys
# Author: jwl247 / Phoenix DevOps LLC
# License: GPL-3.0
# Version: 1.5.0
# ============================================================
# PIPELINE IN:
#   file → dup check → hex → sidecar → clonepool → custody → D1
# PIPELINE OUT:
#   name → hex → clonepool latest → working directory → custody → D1
# PRUNE:
#   walk clonepool → evict old non-latest versions > 3 days
# ============================================================

set -euo pipefail

VERSION="1.6.0"
SCRIPT_NAME="intake"
SCRIPT_HEX="737363726970747332f696e74616b65"
EVICT_DAYS=3

# ── Config ────────────────────────────────────────────────────
CLONEPOOL_DIR="${CLONEPOOL_DIR:-${HOME}/Phoenix/clonepool}"
CATALOG_DB="${HOME}/.catalog/catalog.db"
LOG_DIR="${HOME}/.unitedsys/logs"
LOG_FILE="${LOG_DIR}/intake.log"
WORKER_URL="${PHOENIX_WORKER_URL:-https://packages-worker.phoenix-jwl.workers.dev}"
PHOENIX_AUTH="${PHOENIX_AUTH:-}"

# ── Python detection ──────────────────────────────────────────
_find_python() {
  for cmd in python3 python python3.13 python3.12 python3.11 python3.10; do
    command -v "${cmd}" &>/dev/null && { echo "${cmd}"; return 0; }
  done
  if [[ "$(uname -s)" == MINGW* ]] || [[ "$(uname -s)" == MSYS* ]]; then
    local win_user
    win_user=$(cmd.exe /c "echo %USERPROFILE%" 2>/dev/null \
      | tr -d '\r\n' | sed 's|\\|/|g' | sed 's|C:|/c|' || true)
    for pydir in \
      "${win_user}/AppData/Local/Programs/Python/Python313" \
      "${win_user}/AppData/Local/Programs/Python/Python312" \
      "${win_user}/AppData/Local/Programs/Python/Python311" \
      "/c/Python313" "/c/Python312" "/c/Python311"; do
      [[ -x "${pydir}/python.exe" ]] && { echo "${pydir}/python.exe"; return 0; }
    done
  fi
  echo ""
}
PYTHON_CMD="${PHOENIX_PYTHON:-$(_find_python)}"

# ── Bootstrap ─────────────────────────────────────────────────
mkdir -p "${LOG_DIR}" "${CLONEPOOL_DIR}" "$(dirname "${CATALOG_DB}")"

# ── Logging ───────────────────────────────────────────────────
log() {
  local level="$1"; shift
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] [intake:${level}] $*" | tee -a "${LOG_FILE}"
}

# ── Hex ───────────────────────────────────────────────────────
to_hex() { echo -n "$1" | xxd -p | tr -d '\n'; }

# ── File size ─────────────────────────────────────────────────
get_size() { wc -c < "${1}" 2>/dev/null | tr -d ' ' || echo "0"; }

# ── SHA256 checksum (cross platform) ─────────────────────────
get_checksum() {
  local file="$1"
  if command -v sha256sum &>/dev/null; then
    sha256sum "${file}" | cut -d' ' -f1
  elif command -v shasum &>/dev/null; then
    shasum -a 256 "${file}" | cut -d' ' -f1
  else
    # fallback — md5 if nothing else available
    if command -v md5sum &>/dev/null; then
      md5sum "${file}" | cut -d' ' -f1
    else
      echo "no-checksum"
    fi
  fi
}

# ── Filetype detection ────────────────────────────────────────
detect_filetype() {
  local ext="${1##*.}"
  case "${ext,,}" in
    sh|bash|zsh)   echo "script:shell" ;;
    py)            echo "script:python" ;;
    js|mjs|cjs)    echo "script:javascript" ;;
    ts)            echo "script:typescript" ;;
    json)          echo "config:json" ;;
    yaml|yml)      echo "config:yaml" ;;
    toml)          echo "config:toml" ;;
    env)           echo "config:env" ;;
    conf|cfg|ini)  echo "config:conf" ;;
    service)       echo "systemd:service" ;;
    timer)         echo "systemd:timer" ;;
    socket)        echo "systemd:socket" ;;
    sql)           echo "database:sql" ;;
    md|markdown)   echo "docs:markdown" ;;
    txt)           echo "docs:text" ;;
    xml)           echo "config:xml" ;;
    html|htm)      echo "web:html" ;;
    css)           echo "web:css" ;;
    c|h)           echo "source:c" ;;
    cpp|hpp)       echo "source:cpp" ;;
    rs)            echo "source:rust" ;;
    go)            echo "source:go" ;;
    ps1)           echo "script:powershell" ;;
    *)             echo "unknown:unknown" ;;
  esac
}

filetype_to_category() {
  case "${1}" in
    script:*)   echo "73637269707473" ;;
    config:*)   echo "6461746162617365" ;;
    systemd:*)  echo "73797374656d" ;;
    database:*) echo "6461746162617365" ;;
    docs:*)     echo "6d65646961" ;;
    web:*)      echo "776f726b657273" ;;
    source:c)   echo "737562737973" ;;
    binary:*)   echo "7061636b61676573" ;;
    *)          echo "756e6b6e6f776e" ;;
  esac
}

# ── Companion detection ───────────────────────────────────────
detect_companions() {
  local filepath="$1"
  local dir; dir=$(dirname "${filepath}")
  local name; name=$(basename "${filepath}"); name="${name%.*}"
  local companion_exts=("service" "timer" "socket" "conf" "env" "yaml" "yml" "toml" "json" "md")
  for ext in "${companion_exts[@]}"; do
    local candidate="${dir}/${name}.${ext}"
    if [[ -f "${candidate}" && "$(realpath "${candidate}" 2>/dev/null || echo "${candidate}")" != "$(realpath "${filepath}" 2>/dev/null || echo "${filepath}")" ]]; then
      echo "${candidate}"
      log "INFO" "companion found: ${candidate}"
    fi
  done
}

# ── Version helpers ───────────────────────────────────────────
get_next_version() {
  local dir="$1"
  [[ ! -d "${dir}" ]] && { echo "v1"; return; }
  local files; files=$(ls "${dir}"/v*_* 2>/dev/null || true)
  [[ -z "${files}" ]] && { echo "v1"; return; }
  local last_num
  last_num=$(echo "${files}" \
    | xargs -I{} basename {} \
    | grep -o 'v[0-9]*' | grep -o '[0-9]*' \
    | sort -n | tail -1 || echo "0")
  echo "v$((last_num + 1))"
}

get_latest_file() {
  local pool_dir="$1"
  local name="$2"
  ls "${pool_dir}"/v*_"${name}" 2>/dev/null \
    | while read -r f; do
        num=$(basename "${f}" | grep -o 'v[0-9]*' | grep -o '[0-9]*')
        echo "${num} ${f}"
      done \
    | sort -n \
    | tail -1 \
    | cut -d' ' -f2-
}

# ── Age of file in days ───────────────────────────────────────
file_age_days() {
  local file="$1"
  local now; now=$(date +%s)
  local modified
  if stat -c %Y "${file}" &>/dev/null; then
    modified=$(stat -c %Y "${file}")          # Linux
  else
    modified=$(stat -f %m "${file}" 2>/dev/null || echo "${now}")  # macOS/Git bash
  fi
  echo $(( (now - modified) / 86400 ))
}

# ── Duplicate check ───────────────────────────────────────────
check_duplicate() {
  local filepath="$1"
  local pool_dir="$2"
  local name="$3"

  local latest
  latest=$(get_latest_file "${pool_dir}" "${name}" || true)
  [[ -z "${latest}" ]] && { echo "none"; return; }

  local new_sum; new_sum=$(get_checksum "${filepath}")
  local old_sum; old_sum=$(get_checksum "${latest}")

  if [[ "${new_sum}" == "${old_sum}" ]]; then
    echo "dup:${latest}"
  else
    echo "different"
  fi
}

# ── Evict old versions for one file ──────────────────────────
evict_old_versions() {
  local pool_dir="$1"
  local name="$2"
  local silent="${3:-false}"

  # Get latest file — never evict this one
  local latest
  latest=$(get_latest_file "${pool_dir}" "${name}" || true)
  [[ -z "${latest}" ]] && return 0

  local evicted=0
  while IFS= read -r f; do
    [[ -z "${f}" ]] && continue
    [[ "${f}" == "${latest}" ]] && continue  # never evict latest

    local age; age=$(file_age_days "${f}")
    if (( age > EVICT_DAYS )); then
      rm -f "${f}"
      log "INFO" "evicted: $(basename "${f}") (${age} days old)"
      (( evicted++ )) || true
    fi
  done < <(ls "${pool_dir}"/v*_"${name}" 2>/dev/null || true)

  if [[ "${silent}" != "true" ]] && (( evicted > 0 )); then
    echo "[intake:PRUNE] ${name} — evicted ${evicted} old version(s)"
  fi
}

# ── Write sidecar ─────────────────────────────────────────────
write_sidecar_basic() {
  local sidecar="$1" hex="$2" orig="$3" version="$4"
  local filetype="$5" category_hex="$6" size="$7"
  local backend="${8:-direct}" notes="${9:-}" checksum="${10:-}"
  local now; now=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  mkdir -p "$(dirname "${sidecar}")"
  cat > "${sidecar}" <<SIDECAR
{
  "usys_intake": "1.5",
  "hex_name": "${hex}",
  "original_name": "${orig}",
  "state": "white",
  "version": "${version}",
  "filetype": "${filetype}",
  "category_hex": "${category_hex}",
  "size_bytes": ${size},
  "sha256": "${checksum}",
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

enrich_sidecar_companions() {
  local sidecar="$1" companions_str="$2"
  [[ -z "${PYTHON_CMD}" ]] && return 0
  "${PYTHON_CMD}" - "${sidecar}" "${companions_str}" <<'PYEOF'
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
        ext = line.rsplit('.', 1)[-1] if '.' in line else 'unknown'
        companions.append({
            'file': os.path.basename(line),
            'path': line,
            'type': ext,
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
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  hex_id TEXT NOT NULL, name TEXT NOT NULL, action TEXT NOT NULL,
  version TEXT, source TEXT, destination TEXT,
  state TEXT DEFAULT 'white', actor TEXT DEFAULT 'usys',
  validated INTEGER DEFAULT 0,
  intaked_at TEXT DEFAULT (datetime('now'))
);
INSERT INTO custody (hex_id, name, action, version, source, destination, state, actor)
VALUES ('${hex}','${name}','${action}','${version}','${src}','${dst}','${state}','${actor}');
SQL
}

# ── D1 reporter ───────────────────────────────────────────────
post_to_d1() {
  local endpoint="$1" payload="$2"
  [[ -z "${PHOENIX_AUTH}" ]] && { log "WARN" "PHOENIX_AUTH not set — skipping D1 report"; return 0; }
  local response http_code body
  response=$(curl -s -w "\n%{http_code}" \
    -X POST \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer ${PHOENIX_AUTH}" \
    -d "${payload}" \
    "${WORKER_URL}${endpoint}" 2>/dev/null)
  http_code=$(echo "${response}" | tail -1)
  body=$(echo "${response}" | head -1)
  [[ "${http_code}" == "200" ]] \
    && log "INFO" "D1 OK → ${endpoint}" \
    || log "WARN" "D1 failed (${http_code}) → ${endpoint}: ${body}"
}

report_clonepool() {
  post_to_d1 "/clonepool" \
    "{\"hex_id\":\"${1}\",\"b58\":\"${1}\",\"name\":\"${2}\",\"version\":\"${3}\",\"state\":\"${4}\",\"pool_path\":\"${5}\",\"sidecar_path\":\"${6}\",\"tier\":${7},\"size\":${8}}"
}
report_custody() {
  post_to_d1 "/custody" \
    "{\"hex_id\":\"${1}\",\"name\":\"${2}\",\"action\":\"${3}\",\"state\":\"${4}\",\"actor\":\"${5}\"}"
}
report_glossary() {
  post_to_d1 "/glossary" \
    "{\"hex\":\"${1}\",\"name\":\"${2}\",\"description\":\"${3}\",\"category_hex\":\"${4}\",\"version\":\"${5}\",\"size\":${6},\"pool_path\":\"${7}\",\"state\":\"white\"}"
}

# ── Self registration ─────────────────────────────────────────
self_register() {
  local dir="${CLONEPOOL_DIR}/${SCRIPT_HEX}"
  local sidecar="${dir}/${SCRIPT_HEX}.sidecar.json"
  [[ -f "${sidecar}" ]] && { log "INFO" "self: already registered"; return 0; }
  log "INFO" "self: first run — registering intake into clonepool"
  mkdir -p "${dir}"
  local self_path; self_path=$(realpath "${BASH_SOURCE[0]}" 2>/dev/null || echo "${0}")
  local size; size=$(get_size "${self_path}")
  local checksum; checksum=$(get_checksum "${self_path}")
  cp "${self_path}" "${dir}/v1_${SCRIPT_NAME}"
  write_sidecar_basic "${dir}/${SCRIPT_HEX}.sidecar.json" \
    "${SCRIPT_HEX}" "${SCRIPT_NAME}" "v1" \
    "script:shell" "73637269707473" "${size}" "self" \
    "intake script — self registered on first run" "${checksum}"
  custody_log_local "${SCRIPT_HEX}" "${SCRIPT_NAME}" "self_register" "v1" \
    "${self_path}" "${dir}/v1_${SCRIPT_NAME}" "white" "intake"
  report_clonepool "${SCRIPT_HEX}" "${SCRIPT_NAME}" "v1" "white" "${dir}" \
    "${dir}/${SCRIPT_HEX}.sidecar.json" "1" "${size}"
  report_custody  "${SCRIPT_HEX}" "${SCRIPT_NAME}" "self_register" "white" "intake"
  report_glossary "${SCRIPT_HEX}" "${SCRIPT_NAME}" \
    "Intake script: registers new software into the glossary and clonepool" \
    "73637269707473" "${VERSION}" "${size}" "${dir}"
  echo "[intake:OK] Self registered: ${SCRIPT_NAME} → clonepool"
}

# ══════════════════════════════════════════════════════════════
# IN — intake a file into the clonepool
# ══════════════════════════════════════════════════════════════
intake_file() {
  local filepath="${1:-}" backend="${2:-direct}" notes="${3:-}"

  [[ -z "${filepath}" ]] && { echo "[intake] Usage: intake <file> [backend] [notes]"; return 1; }
  [[ ! -f "${filepath}" ]] && { echo "[intake:MISS] File not found: ${filepath}"; return 1; }

  local orig; orig=$(basename "${filepath}")
  local hex;  hex=$(to_hex "${orig}")
  local pool_dir="${CLONEPOOL_DIR}/${hex}"
  local sidecar="${pool_dir}/${hex}.sidecar.json"

  mkdir -p "${pool_dir}"

  # ── Duplicate check ────────────────────────────────────────
  local dup_result
  dup_result=$(check_duplicate "${filepath}" "${pool_dir}" "${orig}")

  if [[ "${dup_result}" == dup:* ]]; then
    local existing="${dup_result#dup:}"
    local existing_ver; existing_ver=$(basename "${existing}" | grep -o '^v[0-9]*')
    local age; age=$(file_age_days "${existing}")
    echo ""
    echo "[intake:DUP] ${orig} is identical to ${existing_ver} in clonepool (${age} days old)"
    echo "  [1] Keep existing  — discard incoming file"
    echo "  [2] Replace        — evict old, store new"
    echo "  [3] Keep both      — version it anyway"
    echo ""
    read -rp "Choice [1/2/3]: " choice
    case "${choice}" in
      1)
        echo "[intake:OK] Kept existing ${existing_ver} — incoming discarded"
        return 0
        ;;
      2)
        rm -f "${existing}"
        log "INFO" "dup evicted: ${existing}"
        ;;
      3)
        log "INFO" "dup: user chose to version anyway"
        ;;
      *)
        echo "[intake:OK] No action taken"
        return 0
        ;;
    esac
  fi

  local version; version=$(get_next_version "${pool_dir}")
  local filetype; filetype=$(detect_filetype "${orig}")
  local category_hex; category_hex=$(filetype_to_category "${filetype}")
  local size; size=$(get_size "${filepath}")
  local checksum; checksum=$(get_checksum "${filepath}")

  log "INFO" "intaking: ${orig} (${filetype}) as ${version}"

  local companion_list=""
  companion_list=$(detect_companions "${filepath}" || true)

  if [[ -n "${companion_list}" ]]; then
    while IFS= read -r companion; do
      [[ -z "${companion}" ]] && continue
      local comp_name; comp_name=$(basename "${companion}")
      cp "${companion}" "${pool_dir}/${version}_${comp_name}"
      log "INFO" "companion intaked: ${comp_name}"
    done <<< "${companion_list}"
  fi

  cp "${filepath}" "${pool_dir}/${version}_${orig}"
  log "INFO" "stored: ${pool_dir}/${version}_${orig}"

  write_sidecar_basic "${sidecar}" "${hex}" "${orig}" "${version}" \
    "${filetype}" "${category_hex}" "${size}" "${backend}" "${notes}" "${checksum}"
  enrich_sidecar_companions "${sidecar}" "${companion_list}"
  custody_log_local "${hex}" "${orig}" "intake" "${version}" \
    "${filepath}" "${pool_dir}/${version}_${orig}" "white" "${backend}"
  report_clonepool "${hex}" "${orig}" "${version}" "white" \
    "${pool_dir}" "${sidecar}" "1" "${size}"
  report_custody  "${hex}" "${orig}" "intake" "white" "${backend}"
  report_glossary "${hex}" "${orig}" "Intaked via ${backend}: ${filetype}" \
    "${category_hex}" "${version}" "${size}" "${pool_dir}"

  # ── Auto evict old versions for this file ─────────────────
  evict_old_versions "${pool_dir}" "${orig}" "true"

  echo "[intake:OK] ${orig} → clonepool ${version}"
  echo "[intake:OK] hex:      ${hex}"
  echo "[intake:OK] type:     ${filetype}"
  echo "[intake:OK] sha256:   ${checksum:0:16}..."
  [[ -n "${companion_list}" ]] && \
    echo "[intake:OK] companions: $(echo "${companion_list}" | wc -l | tr -d ' ')"
  return 0
}

# ══════════════════════════════════════════════════════════════
# OUT — clone latest version to current working directory
# ══════════════════════════════════════════════════════════════
intake_clone() {
  local name="${1:-}"

  if [[ -z "${name}" ]]; then
    echo "[intake] Usage: intake clone <filename>"
    echo "         e.g.:  intake clone myfile.py"
    return 1
  fi

  [[ "${name}" == *.lol ]] && name="${name%.lol}"

  local hex; hex=$(to_hex "${name}")
  local pool_dir="${CLONEPOOL_DIR}/${hex}"

  if [[ ! -d "${pool_dir}" ]]; then
    echo "[intake:MISS] '${name}' not found in clonepool"
    echo "              Have you intaked it yet? Run: intake ${name}"
    return 1
  fi

  local latest
  latest=$(get_latest_file "${pool_dir}" "${name}")

  if [[ -z "${latest}" ]]; then
    echo "[intake:MISS] No versioned files found for '${name}' in clonepool"
    return 1
  fi

  local version; version=$(basename "${latest}" | grep -o '^v[0-9]*')
  local dest="${PWD}/${name}"

  if [[ -f "${dest}" ]]; then
    echo "[intake:WARN] '${name}' already exists here — overwriting with ${version}"
  fi

  cp "${latest}" "${dest}"

  log "INFO" "clone out: ${name} ${version} → ${dest}"
  custody_log_local "${hex}" "${name}" "clone_out" "${version}" \
    "${latest}" "${dest}" "white" "user"
  report_custody "${hex}" "${name}" "clone_out" "white" "user"

  echo "[intake:OK] ${name} ${version} → ${PWD}/"
  echo "[intake:OK] This is the latest version — ready to use"
  return 0
}

# ══════════════════════════════════════════════════════════════
# PRUNE — manual eviction of old versions across whole pool
# ══════════════════════════════════════════════════════════════
intake_prune() {
  echo ""
  echo " Scanning clonepool for versions older than ${EVICT_DAYS} days..."
  echo ""

  local total_evicted=0
  local files_checked=0

  # Walk every hex directory in the clonepool
  for pool_dir in "${CLONEPOOL_DIR}"/*/; do
    [[ ! -d "${pool_dir}" ]] && continue

    # Find all unique file names in this pool dir
    local names=()
    while IFS= read -r f; do
      local base; base=$(basename "${f}")
      # Strip version prefix to get original name
      local name="${base#v*_}"
      # Add to names if not already there
      local found=false
      for n in "${names[@]:-}"; do [[ "${n}" == "${name}" ]] && found=true && break; done
      [[ "${found}" == "false" ]] && names+=("${name}")
    done < <(ls "${pool_dir}"v*_* 2>/dev/null || true)

    for name in "${names[@]:-}"; do
      [[ -z "${name}" ]] && continue
      (( files_checked++ )) || true

      # Count versions before eviction
      local before; before=$(ls "${pool_dir}"v*_"${name}" 2>/dev/null | wc -l | tr -d ' ')
      [[ "${before}" -le 1 ]] && continue  # only one version — never evict

      evict_old_versions "${pool_dir}" "${name}" "false"

      local after; after=$(ls "${pool_dir}"v*_"${name}" 2>/dev/null | wc -l | tr -d ' ')
      local evicted=$(( before - after ))
      (( total_evicted += evicted )) || true
    done
  done

  echo ""
  echo " ╔══════════════════════════════════════╗"
  echo " ║         PRUNE COMPLETE               ║"
  echo " ╚══════════════════════════════════════╝"
  echo " Files checked : ${files_checked}"
  echo " Versions evicted : ${total_evicted}"
  echo " Retention    : ${EVICT_DAYS} days"
  echo " Latest versions : always kept"
  echo ""
}

# ── Intake from backend ───────────────────────────────────────
intake_from_backend() {
  local pkg_name="${1:-}" backend="${2:-unknown}" \
        version="${3:-unknown}" install_path="${4:-}"

  [[ -z "${pkg_name}" ]] && {
    echo "[intake] Usage: intake backend <pkg_name> <backend> <version> [install_path]"
    return 1
  }

  log "INFO" "backend intake: ${pkg_name} from ${backend} ${version}"

  if [[ -n "${install_path}" && -f "${install_path}" ]]; then
    intake_file "${install_path}" "${backend}" "installed from ${backend} ${version}"
    return $?
  fi

  local hex; hex=$(to_hex "${pkg_name}")
  local pool_dir="${CLONEPOOL_DIR}/${hex}"
  local sidecar="${pool_dir}/${hex}.sidecar.json"

  mkdir -p "${pool_dir}"
  write_sidecar_basic "${sidecar}" "${hex}" "${pkg_name}" "${version}" \
    "package:${backend}" "7061636b61676573" "0" "${backend}" \
    "installed from ${backend}" ""
  custody_log_local "${hex}" "${pkg_name}" "backend_install" "${version}" \
    "${backend}" "${pool_dir}" "white" "${backend}"
  report_clonepool "${hex}" "${pkg_name}" "${version}" "white" \
    "${pool_dir}" "${sidecar}" "1" "0"
  report_custody  "${hex}" "${pkg_name}" "backend_install" "white" "${backend}"
  report_glossary "${hex}" "${pkg_name}" "Package installed from ${backend} v${version}" \
    "7061636b61676573" "${version}" "0" "${pool_dir}"

  echo "[intake:OK] ${pkg_name} (${backend} ${version}) → D1"
}

# ── Status ────────────────────────────────────────────────────
intake_status() {
  local total white grey black
  total=$(find "${CLONEPOOL_DIR}" -name "*.sidecar.json" 2>/dev/null | wc -l | tr -d ' ')
  white=$(find "${CLONEPOOL_DIR}" -name "*.sidecar.json" \
    -exec grep -l '"state": "white"' {} \; 2>/dev/null | wc -l | tr -d ' ')
  grey=$(find  "${CLONEPOOL_DIR}" -name "*.sidecar.json" \
    -exec grep -l '"state": "grey"'  {} \; 2>/dev/null | wc -l | tr -d ' ')
  black=$(find "${CLONEPOOL_DIR}" -name "*.sidecar.json" \
    -exec grep -l '"state": "black"' {} \; 2>/dev/null | wc -l | tr -d ' ')
  echo ""
  echo " ╔══════════════════════════════════════╗"
  echo " ║     INTAKE / CLONEPOOL STATUS        ║"
  echo " ╚══════════════════════════════════════╝"
  echo " Worker  : ${WORKER_URL}"
  echo " Pool    : ${CLONEPOOL_DIR}"
  [[ -n "${PYTHON_CMD}" ]] \
    && echo " Python  : ${PYTHON_CMD}" \
    || echo " Python  : not found (non-critical)"
  echo " Retention: ${EVICT_DAYS} days"
  echo " Total   : ${total}"
  echo " White   : ${white} (active)"
  echo " Grey    : ${grey} (deprecated)"
  echo " Black   : ${black} (retired)"
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
╚═╝╚═╝  ╚═══╝  ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝

  Phoenix DevOps — intake v${VERSION}

  IN  (file → clonepool):
    intake <file>                    Intake a file
    intake <file.ext.lol>            Short syntax — strips .lol
    intake <file> [backend] [notes]  With backend tag and notes
    intake backend <pkg> <be> <ver>  Register a backend-installed package

  IN  (directory → clonepool):
    intake <directory/>              Intake entire directory with preview
    intake <directory/> [backend]    With backend tag

  OUT (clonepool → your current directory):
    intake clone <file>              Pull latest file version here
    intake clone <dir>               Pull latest directory snapshot here
    intake clone <dir> v2            Pull specific version here
    intake clone <file.lol>          Short syntax works too

  MAINTENANCE:
    intake prune                     Evict old versions (>${EVICT_DAYS} days) across pool
    intake status                    Show clonepool status
    intake help                      This screen

  Duplicate handling:
    If you intake a file identical to what's already in the pool,
    intake asks: keep existing / replace / keep both

  Version eviction:
    Old non-latest versions evict automatically after ${EVICT_DAYS} days
    Latest version is always kept — no matter how old
    Single-version files are never evicted

  Pipeline IN:   file → dup check → hex → sidecar → clonepool → custody → D1
  Pipeline OUT:  name → hex → clonepool latest → \$PWD → custody → D1

  Worker  : ${WORKER_URL}
  Pool    : ${CLONEPOOL_DIR}
  Log     : ${LOG_FILE}
  Python  : ${PYTHON_CMD:-not found (non-critical)}

EOF
}

#!/usr/bin/env bash
# This is the intake_directory function + updated entry point
# to be merged into intake.sh v1.5.0 → v1.6.0

# ── Skip patterns for directory intake ───────────────────────
SKIP_DIRS=("node_modules" ".git" "__pycache__" ".svn" "vendor" "dist" "build" ".next" ".nuxt" "venv" ".venv" "env" ".tox" "coverage" ".nyc_output" "target" "out")
SKIP_EXTENSIONS=(".jpg" ".jpeg" ".png" ".gif" ".webp" ".svg" ".ico" ".bmp" ".tiff" ".mp4" ".mp3" ".wav" ".avi" ".mov" ".zip" ".tar" ".gz" ".rar" ".7z" ".exe" ".dll" ".so" ".dylib" ".bin" ".dat" ".db" ".sqlite" ".lock")

is_skip_dir() {
  local dir="$1"
  local base; base=$(basename "${dir}")
  for skip in "${SKIP_DIRS[@]}"; do
    [[ "${base}" == "${skip}" ]] && return 0
  done
  return 1
}

is_skip_ext() {
  local file="$1"
  local ext="${file##*.}"; ext=".${ext,,}"
  for skip in "${SKIP_EXTENSIONS[@]}"; do
    [[ "${ext}" == "${skip}" ]] && return 0
  done
  return 1
}

is_known_type() {
  local file="$1"
  local ext="${file##*.}"; ext="${ext,,}"
  case "${ext}" in
    sh|bash|zsh|py|js|mjs|cjs|ts|json|yaml|yml|toml|env|\
    conf|cfg|ini|service|timer|socket|sql|md|markdown|txt|\
    xml|html|htm|css|c|h|cpp|hpp|rs|go|ps1) return 0 ;;
    *) return 1 ;;
  esac
}

# ── Human readable size ───────────────────────────────────────
human_size() {
  local bytes="$1"
  if (( bytes < 1024 )); then echo "${bytes} B"
  elif (( bytes < 1048576 )); then echo "$(( bytes / 1024 )) KB"
  elif (( bytes < 1073741824 )); then echo "$(( bytes / 1048576 )) MB"
  else echo "$(( bytes / 1073741824 )) GB"
  fi
}

# ══════════════════════════════════════════════════════════════
# DIRECTORY INTAKE
# ══════════════════════════════════════════════════════════════
intake_directory() {
  local dirpath="${1:-}"
  local backend="${2:-direct}"
  local notes="${3:-}"

  # Strip trailing slash
  dirpath="${dirpath%/}"
  dirpath="${dirpath%\\}"

  [[ -z "${dirpath}" ]] && { echo "[intake] Usage: intake <directory/>"; return 1; }
  [[ ! -d "${dirpath}" ]] && { echo "[intake:MISS] Directory not found: ${dirpath}"; return 1; }

  local dirname; dirname=$(basename "${dirpath}")
  local hex;     hex=$(to_hex "${dirname}")
  local pool_dir="${CLONEPOOL_DIR}/${hex}"
  local version; version=$(get_next_version "${pool_dir}")

  echo ""
  echo " [intake:DIR] Scanning directory..."
  echo ""

  # ── Collect files ────────────────────────────────────────
  local all_files=()
  local known_files=()
  local skipped_dirs=()
  local skipped_files=()
  local sensitive_files=()
  local total_size=0
  declare -A ext_counts

  while IFS= read -r -d '' f; do
    local rel="${f#${dirpath}/}"

    # Check if in a skip dir
    local in_skip=false
    for skip in "${SKIP_DIRS[@]}"; do
      if [[ "${rel}" == "${skip}/"* ]] || [[ "${rel}" == *"/${skip}/"* ]]; then
        in_skip=true
        # Record skip dir once
        local skip_base="${rel%%/*}"
        local already=false
        for s in "${skipped_dirs[@]:-}"; do [[ "$s" == "$skip_base" ]] && already=true; done
        [[ "${already}" == "false" ]] && skipped_dirs+=("${skip_base}")
        break
      fi
    done
    [[ "${in_skip}" == "true" ]] && continue

    # Check extension
    if is_skip_ext "${f}"; then
      skipped_files+=("${rel}")
      continue
    fi

    if is_known_type "${f}"; then
      known_files+=("${f}")
      local size; size=$(get_size "${f}")
      (( total_size += size )) || true

      # Count by extension
      local ext="${f##*.}"; ext="${ext,,}"
      ext_counts["${ext}"]=$(( ${ext_counts["${ext}"]:-0} + 1 ))

      # Flag sensitive files
      case "$(basename "${f}")" in
        .env|*.env|*secret*|*password*|*credential*|*token*|*auth*)
          sensitive_files+=("${rel}") ;;
      esac
    else
      skipped_files+=("${rel}")
    fi
  done < <(find "${dirpath}" -type f -print0 2>/dev/null)

  # ── Build type summary ────────────────────────────────────
  local type_summary=""
  for ext in "${!ext_counts[@]}"; do
    type_summary+=".${ext} (${ext_counts[$ext]})  "
  done

  # ── Show warning ──────────────────────────────────────────
  echo " ╔══════════════════════════════════════════════════╗"
  echo " ║         DIRECTORY INTAKE PREVIEW                ║"
  echo " ╚══════════════════════════════════════════════════╝"
  echo ""
  echo "  Path     : ${dirpath}"
  echo "  Version  : ${version} ($([ "${version}" == "v1" ] && echo "new" || echo "update"))"
  echo "  Files    : ${#known_files[@]} files to intake"
  echo "  Types    : ${type_summary}"
  echo "  Size     : $(human_size ${total_size})"
  echo ""

  if (( ${#skipped_dirs[@]} > 0 )); then
    echo "  Skipped  : ${skipped_dirs[*]} (ignored directories)"
  fi
  if (( ${#skipped_files[@]} > 0 )); then
    echo "  Ignored  : ${#skipped_files[@]} binary/media files"
  fi

  echo ""

  if (( ${#sensitive_files[@]} > 0 )); then
    echo " ⚠  WARNING — SENSITIVE FILES DETECTED:"
    for sf in "${sensitive_files[@]}"; do
      echo "    → ${sf}"
    done
    echo " ⚠  These files will be stored in clonepool AND reported to D1"
    echo " ⚠  D1 is a remote store — ensure this is intentional"
    echo ""
  fi

  echo "  [1] Proceed — intake all files"
  echo "  [2] Exclude .env and sensitive files"
  echo "  [3] Cancel"
  echo ""
  read -rp "  Choice [1/2/3]: " choice

  case "${choice}" in
    1) log "INFO" "dir intake: user chose full intake" ;;
    2)
      log "INFO" "dir intake: user excluded sensitive files"
      local filtered=()
      for f in "${known_files[@]}"; do
        local rel="${f#${dirpath}/}"
        local is_sensitive=false
        for sf in "${sensitive_files[@]}"; do
          [[ "${rel}" == "${sf}" ]] && is_sensitive=true && break
        done
        [[ "${is_sensitive}" == "false" ]] && filtered+=("${f}")
      done
      known_files=("${filtered[@]}")
      echo ""
      echo " [intake:OK] Sensitive files excluded — proceeding with ${#known_files[@]} files"
      ;;
    *)
      echo " [intake:CANCEL] Directory intake cancelled"
      return 0
      ;;
  esac

  echo ""
  echo " [intake:DIR] Intaking ${#known_files[@]} files..."
  echo ""

  # ── Create directory snapshot in clonepool ────────────────
  local snapshot_dir="${pool_dir}/${version}_${dirname}"
  mkdir -p "${snapshot_dir}"

  local success=0
  local failed=0
  local dir_manifest="[]"
  local manifest_entries=""

  for f in "${known_files[@]}"; do
    local rel="${f#${dirpath}/}"
    local file_orig; file_orig=$(basename "${f}")
    local file_hex;  file_hex=$(to_hex "${file_orig}")
    local file_pool="${CLONEPOOL_DIR}/${file_hex}"
    local file_version; file_version=$(get_next_version "${file_pool}")
    local filetype;  filetype=$(detect_filetype "${file_orig}")
    local category_hex; category_hex=$(filetype_to_category "${filetype}")
    local size;      size=$(get_size "${f}")
    local checksum;  checksum=$(get_checksum "${f}")

    mkdir -p "${file_pool}"

    # Duplicate check — skip if identical
    local dup_result
    dup_result=$(check_duplicate "${f}" "${file_pool}" "${file_orig}")
    if [[ "${dup_result}" == dup:* ]]; then
      log "INFO" "dir dup skipped: ${rel}"
      (( success++ )) || true
      continue
    fi

    cp "${f}" "${file_pool}/${file_version}_${file_orig}"
    # Also copy into snapshot dir preserving relative path
    mkdir -p "${snapshot_dir}/$(dirname "${rel}")"
    cp "${f}" "${snapshot_dir}/${rel}"

    local sidecar="${file_pool}/${file_hex}.sidecar.json"
    write_sidecar_basic "${sidecar}" "${file_hex}" "${file_orig}" \
      "${file_version}" "${filetype}" "${category_hex}" "${size}" \
      "${backend}" "dir:${dirname}/${rel}" "${checksum}"

    custody_log_local "${file_hex}" "${file_orig}" "dir_intake" \
      "${file_version}" "${f}" "${file_pool}/${file_version}_${file_orig}" \
      "white" "${backend}"
    report_clonepool "${file_hex}" "${file_orig}" "${file_version}" "white" \
      "${file_pool}" "${sidecar}" "1" "${size}"
    report_custody "${file_hex}" "${file_orig}" "dir_intake" "white" "${backend}"

    # Auto evict old versions
    evict_old_versions "${file_pool}" "${file_orig}" "true"

    manifest_entries+="  {\"hex\":\"${file_hex}\",\"name\":\"${file_orig}\",\"path\":\"${rel}\",\"version\":\"${file_version}\",\"checksum\":\"${checksum}\"},"
    (( success++ )) || true
    echo "  [OK] ${rel}"
  done

  # ── Write directory sidecar ───────────────────────────────
  local dir_sidecar="${pool_dir}/${hex}.sidecar.json"
  local now; now=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  local dir_checksum; dir_checksum=$(get_checksum "${dirpath}" 2>/dev/null || echo "dir-no-checksum")

  mkdir -p "${pool_dir}"
  cat > "${dir_sidecar}" <<DIRSIDECAR
{
  "usys_intake": "1.6",
  "type": "directory",
  "hex_name": "${hex}",
  "original_name": "${dirname}",
  "state": "white",
  "version": "${version}",
  "snapshot_path": "${snapshot_dir}",
  "file_count": ${success},
  "size_bytes": ${total_size},
  "backend": "${backend}",
  "notes": "${notes}",
  "pool_path": "${pool_dir}",
  "registered_at": "${now}",
  "updated_at": "${now}",
  "files": [
${manifest_entries%,}
  ],
  "clone_history": [{"version": "${version}", "at": "${now}"}]
}
DIRSIDECAR

  custody_log_local "${hex}" "${dirname}" "dir_intake" "${version}" \
    "${dirpath}" "${snapshot_dir}" "white" "${backend}"
  report_clonepool "${hex}" "${dirname}" "${version}" "white" \
    "${pool_dir}" "${dir_sidecar}" "1" "${total_size}"
  report_custody "${hex}" "${dirname}" "dir_intake" "white" "${backend}"
  report_glossary "${hex}" "${dirname}" \
    "Directory snapshot: ${#known_files[@]} files, ${version}" \
    "6469726563746f7279" "${version}" "${total_size}" "${pool_dir}"

  echo ""
  echo " ╔══════════════════════════════════════════════════╗"
  echo " ║         DIRECTORY INTAKE COMPLETE               ║"
  echo " ╚══════════════════════════════════════════════════╝"
  echo "  Directory : ${dirname}"
  echo "  Version   : ${version}"
  echo "  Files     : ${success} intaked"
  echo "  Size      : $(human_size ${total_size})"
  echo "  Hex       : ${hex}"
  echo "  Snapshot  : ${snapshot_dir}"
  echo ""
  echo "  To restore: intake clone ${dirname}"
  echo ""
}

# ── Directory clone out ───────────────────────────────────────
intake_clone_directory() {
  local name="${1:-}"
  local version="${2:-latest}"

  local hex; hex=$(to_hex "${name}")
  local pool_dir="${CLONEPOOL_DIR}/${hex}"
  local sidecar="${pool_dir}/${hex}.sidecar.json"

  if [[ ! -d "${pool_dir}" ]]; then
    echo "[intake:MISS] '${name}' not found in clonepool"
    return 1
  fi

  # Check if it's a directory type
  local type
  type=$(grep -o '"type": "directory"' "${sidecar}" 2>/dev/null || echo "")
  if [[ -z "${type}" ]]; then
    # Fall through to regular file clone
    return 1
  fi

  # Find snapshot dir for requested version
  local snapshot
  if [[ "${version}" == "latest" ]]; then
    snapshot=$(ls -d "${pool_dir}"/v*_"${name}" 2>/dev/null \
      | while read -r d; do
          num=$(basename "${d}" | grep -o 'v[0-9]*' | grep -o '[0-9]*')
          echo "${num} ${d}"
        done \
      | sort -n | tail -1 | cut -d' ' -f2-)
  else
    snapshot="${pool_dir}/${version}_${name}"
  fi

  if [[ -z "${snapshot}" ]] || [[ ! -d "${snapshot}" ]]; then
    echo "[intake:MISS] No snapshot found for '${name}' ${version}"
    return 1
  fi

  local ver; ver=$(basename "${snapshot}" | grep -o '^v[0-9]*')
  local dest="${PWD}/${name}"

  if [[ -d "${dest}" ]]; then
    echo "[intake:WARN] '${name}' already exists here — overwriting with ${ver}"
  fi

  cp -r "${snapshot}" "${dest}"

  log "INFO" "dir clone out: ${name} ${ver} → ${dest}"
  custody_log_local "${hex}" "${name}" "dir_clone_out" "${ver}" \
    "${snapshot}" "${dest}" "white" "user"
  report_custody "${hex}" "${name}" "dir_clone_out" "white" "user"

  echo "[intake:OK] ${name}/ ${ver} → ${PWD}/"
  echo "[intake:OK] $(ls "${dest}" | wc -l | tr -d ' ') files restored"
  echo "[intake:OK] This is the ${ver} snapshot — ready to use"
}
# ── .lol resolver ─────────────────────────────────────────────
resolve_lol() {
  local arg="${1:-}"
  if [[ "${arg}" == *.lol ]]; then
    local real="${arg%.lol}"
    [[ -f "${real}" ]] && { echo "${real}"; return; }
    [[ -f "${arg}"  ]] && { echo "${arg}";  return; }
    echo "${real}"
  else
    echo "${arg}"
  fi
}

# ── Self register ─────────────────────────────────────────────
self_register

# ── Entry point ───────────────────────────────────────────────
case "${1:-help}" in
  help|--help|-h) show_help ;;
  status)         intake_status ;;
  clone)
    shift
    name="${1:-}"; version="${2:-latest}"
    [[ "${name}" == *.lol ]] && name="${name%.lol}"
    # Try directory clone first, fall back to file clone
    intake_clone_directory "${name}" "${version}" 2>/dev/null \
      || intake_clone "${name}"
    ;;
  prune)          intake_prune ;;
  backend)        shift; intake_from_backend "$@" ;;
  *)
    first_arg=$(resolve_lol "${1:-}")
    shift || true
    # Directory or file?
    if [[ -d "${first_arg}" ]]; then
      intake_directory "${first_arg}" "$@"
    else
      intake_file "${first_arg}" "$@"
    fi
    ;;
esac
