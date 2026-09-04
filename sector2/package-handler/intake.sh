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

VERSION="1.7.0"
SCRIPT_NAME="intake"
SCRIPT_HEX="737363726970747332f696e74616b65"
MAX_VERSIONS=7   # keep 7 versions per file — a new intake bumps the oldest out
                 # the 3-day figure is the rollback window (how long you have to
                 # act before a new intake can displace an old version), not a
                 # forced deletion timer. nothing is ever deleted just for being old.

# ── Config ────────────────────────────────────────────────────
CLONEPOOL_DIR="${CLONEPOOL_DIR:-${HOME}/Phoenix/clonepool}"
CATALOG_DB="${HOME}/.catalog/catalog.db"
LOG_DIR="${HOME}/.unitedsys/logs"
LOG_FILE="${LOG_DIR}/intake.log"
WORKER_URL="${PHOENIX_WORKER_URL:-https://packages-worker.phoenix-jwl.workers.dev}"
# Separate worker for the actual R2 bytes (2026-09-04). packages-worker has
# no R2 binding and no PUT handler for the route upload_to_r2() was calling
# — every upload since this pipeline existed has been silently failing
# (confirmed: files from before 2026-08-22 are not in R2 at all). This is a
# brand-new worker, never touches packages-worker.
R2_WORKER_URL="${PHOENIX_R2_WORKER_URL:-https://phoenix-clonepool-r2.phoenix-jwl.workers.dev}"
PHOENIX_AUTH="${PHOENIX_AUTH:-}"

# ── Python detection ──────────────────────────────────────────
_find_python() {
  # `command -v` only proves a name resolves in PATH — on Windows, the
  # Microsoft Store's "python3"/"python" execution-alias stubs satisfy that
  # even when running them does nothing but pop up a Store install prompt.
  # Actually invoking --version (with a timeout, in case a stub hangs
  # instead of erroring) is the only way to tell a real interpreter from
  # one of those. This bit twice already this session before the check
  # existed here.
  for cmd in python3 python python3.13 python3.12 python3.11 python3.10; do
    command -v "${cmd}" &>/dev/null || continue
    timeout 5 "${cmd}" --version &>/dev/null && { echo "${cmd}"; return 0; }
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

# ── Base58 (for QR header/footer strings) ──────────────────────
# Matches phoenix-core/tools/intake.py's _base58() exactly — that Python
# pipeline is the one place this ever actually worked (generates real
# USYS:<b58>:HEADER / :FOOTER:<hex> strings, stored in D1 custody.qr_top/
# qr_bottom). This bash pipeline never had it; reusing the proven
# algorithm via Python rather than reimplementing bignum division in bash.
_base58_from_hex() {
  local hex16="$1"
  [[ -z "${PYTHON_CMD}" ]] && { echo ""; return; }
  "${PYTHON_CMD}" -c "
alphabet = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
data = bytes.fromhex('${hex16}')
n = int.from_bytes(data, 'big')
result = ''
while n:
    n, r = divmod(n, 58)
    result = alphabet[r] + result
for byte in data:
    if byte == 0:
        result = alphabet[0] + result
    else:
        break
print(result)
" 2>/dev/null
}

# ── Bootstrap ─────────────────────────────────────────────────
mkdir -p "${LOG_DIR}" "${CLONEPOOL_DIR}" "$(dirname "${CATALOG_DB}")"

# ── Logging ───────────────────────────────────────────────────
log() {
  local level="$1"; shift
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] [intake:${level}] $*" | tee -a "${LOG_FILE}"
}

# ── Hex ───────────────────────────────────────────────────────
to_hex() { echo -n "$1" | xxd -p | tr -d '\n'; }

# ── Sensitive-name heuristic — shared by single-file and directory intake ──
is_sensitive_name() {
  case "$(basename "$1")" in
    .env|*.env|*secret*|*password*|*credential*|*token*|*auth*) return 0 ;;
    *) return 1 ;;
  esac
}

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
# Rule: keep MAX_VERSIONS most recent versions, evict the rest.
# Latest version is always protected regardless of count.
# A version is never deleted just because it is old — only when
# a new intake pushes the count past MAX_VERSIONS.
evict_old_versions() {
  local pool_dir="$1"
  local name="$2"
  local silent="${3:-false}"

  # Get latest file — never evict this one
  local latest
  latest=$(get_latest_file "${pool_dir}" "${name}" || true)
  [[ -z "${latest}" ]] && return 0

  # Collect all versions sorted by version number ascending
  local all_versions=()
  while IFS= read -r f; do
    [[ -z "${f}" ]] && continue
    all_versions+=("${f}")
  done < <(ls "${pool_dir}"/v*_"${name}" 2>/dev/null \
    | while read -r f; do
        num=$(basename "${f}" | grep -o 'v[0-9]*' | grep -o '[0-9]*')
        echo "${num} ${f}"
      done \
    | sort -n | awk '{print $2}' || true)

  local total="${#all_versions[@]}"
  (( total <= MAX_VERSIONS )) && return 0  # within limit — nothing to do

  local evicted=0
  local keep_from=$(( total - MAX_VERSIONS ))  # evict the oldest beyond the limit
  local idx=0
  for f in "${all_versions[@]}"; do
    if (( idx < keep_from )); then
      [[ "${f}" == "${latest}" ]] && { (( idx++ )) || true; continue; }  # safety: never latest
      rm -f "${f}"
      log "INFO" "evicted: $(basename "${f}") (version count exceeded ${MAX_VERSIONS})"
      (( evicted++ )) || true
    fi
    (( idx++ )) || true
  done

  if [[ "${silent}" != "true" ]] && (( evicted > 0 )); then
    echo "[intake:PRUNE] ${name} — evicted ${evicted} old version(s) (kept ${MAX_VERSIONS})"
  fi
}

# ── Write sidecar ─────────────────────────────────────────────
write_sidecar_basic() {
  local sidecar="$1" hex="$2" orig="$3" version="$4"
  local filetype="$5" category_hex="$6" size="$7"
  local backend="${8:-direct}" notes="${9:-}" checksum="${10:-}"
  local sensitive="${11:-false}"
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
  "sensitive": ${sensitive},
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

# ── R2 uploader — actual file bytes, not just D1 metadata ──────
# R2 was documented as the canonical content store from the start, but
# nothing in this pipeline ever uploaded to it — D1 held pointers to a
# pool_path that only exists on this one machine's disk. This closes that
# gap going forward. Not fatal on failure (same posture as post_to_d1):
# a stalled R2 upload shouldn't abort an otherwise-successful local intake.
R2_MAX_BYTES=$((100 * 1024 * 1024))  # Workers request-body ceiling, conservative
upload_to_r2() {
  local hex="$1" filepath="$2"
  [[ -z "${PHOENIX_AUTH}" ]] && { log "WARN" "PHOENIX_AUTH not set — skipping R2 upload"; return 0; }
  [[ ! -f "${filepath}" ]] && { log "WARN" "R2 upload: file not found: ${filepath}"; return 0; }
  local size; size=$(get_size "${filepath}")
  if (( size > R2_MAX_BYTES )); then
    log "WARN" "R2 upload skipped — ${filepath} is $(( size / 1024 / 1024 ))MB, over the $(( R2_MAX_BYTES / 1024 / 1024 ))MB cap"
    return 0
  fi
  local http_code
  http_code=$(curl -s -o /dev/null -w "%{http_code}" \
    -X PUT \
    -H "Authorization: Bearer ${PHOENIX_AUTH}" \
    --data-binary "@${filepath}" \
    "${R2_WORKER_URL}/object/${hex}" 2>/dev/null)
  [[ "${http_code}" == "200" ]] \
    && log "INFO" "R2 OK → ${hex} (${size} bytes)" \
    || log "WARN" "R2 upload failed (${http_code}) → ${hex}"
}

# stored_filepath (10th, optional) is the actual bytes on disk — content
# hash baseline for the "validated" integrity check (clone-to-workdir and
# hot-swap must never hand out a corrupted/incorrect copy). Package installs
# and directory summaries have no single file to hash, so it's optional;
# omitted, hash_sha3/hash_blake2 stay null and COALESCE on the D1 side
# leaves any prior value alone.
report_clonepool() {
  local hex="${1}"
  local sensitive="${9:-false}"
  local stored_filepath="${10:-}"
  local b58; b58=$(_base58_from_hex "${hex:0:16}")
  local header_qr="" footer_qr=""
  if [[ -n "${b58}" ]]; then
    header_qr="USYS:${b58}:HEADER"
    footer_qr="USYS:${b58}:FOOTER:${hex}"
  fi
  local hash_sha3="" hash_blake2=""
  if [[ -n "${stored_filepath}" && -f "${stored_filepath}" ]]; then
    hash_sha3=$(openssl dgst -sha3-512 -r "${stored_filepath}" 2>/dev/null | awk '{print $1}')
    hash_blake2=$(openssl dgst -blake2b512 -r "${stored_filepath}" 2>/dev/null | awk '{print $1}')
  fi
  post_to_d1 "/clonepool" \
    "{\"hex_id\":\"${hex}\",\"b58\":\"${b58:-${hex}}\",\"name\":\"${2}\",\"version\":\"${3}\",\"state\":\"${4}\",\"pool_path\":\"${5}\",\"sidecar_path\":\"${6}\",\"tier\":${7},\"size\":${8},\"sensitive\":${sensitive},\"header_qr\":\"${header_qr}\",\"footer_qr\":\"${footer_qr}\",\"hash_sha3\":\"${hash_sha3}\",\"hash_blake2\":\"${hash_blake2}\"}"
}
report_custody() {
  local hex="${1}"
  local b58; b58=$(_base58_from_hex "${hex:0:16}")
  local qr_top="" qr_bottom=""
  if [[ -n "${b58}" ]]; then
    qr_top="USYS:${b58}:HEADER"
    qr_bottom="USYS:${b58}:FOOTER:${hex}"
  fi
  post_to_d1 "/custody" \
    "{\"hex_id\":\"${hex}\",\"name\":\"${2}\",\"action\":\"${3}\",\"state\":\"${4}\",\"actor\":\"${5}\",\"qr_top\":\"${qr_top}\",\"qr_bottom\":\"${qr_bottom}\"}"
}
# ── Integrity check — clone-to-workdir / hot-swap gate ────────
# The local clonepool copy is what's actually handed to the working
# directory; the hash recorded in D1 at intake time is the trusted
# baseline. Nothing corrupted or altered should ever come out the other
# end of `intake clone`. Prints one of: valid | CORRUPT | no_baseline
# (older, pre-hash-fix intakes have no baseline yet — allowed through
# with a warning rather than hard-blocked, since refusing every legacy
# file until the backfill runs would just break normal use).
verify_clonepool_copy() {
  local hex="$1" filepath="$2"
  [[ -z "${PHOENIX_AUTH}" || ! -f "${filepath}" ]] && { echo "no_baseline"; return; }
  local meta
  meta=$(curl -s -H "Authorization: Bearer ${PHOENIX_AUTH}" "${WORKER_URL}/clonepool/${hex}?meta=true" 2>/dev/null)
  local baseline_sha3
  baseline_sha3=$(echo "${meta}" | grep -o '"hash_sha3":"[^"]*"' | head -1 | sed -E 's/.*:"([^"]*)"/\1/')
  [[ -z "${baseline_sha3}" ]] && { echo "no_baseline"; return; }

  local actual_sha3
  actual_sha3=$(openssl dgst -sha3-512 -r "${filepath}" 2>/dev/null | awk '{print $1}')
  if [[ -n "${actual_sha3}" && "${actual_sha3}" == "${baseline_sha3}" ]]; then
    curl -s -o /dev/null -X POST -H "Authorization: Bearer ${PHOENIX_AUTH}" -H "Content-Type: application/json" \
      -d "{\"hash_sha3\":\"${actual_sha3}\"}" "${WORKER_URL}/clonepool/${hex}/validate" 2>/dev/null
    echo "valid"
  else
    echo "CORRUPT"
  fi
}
# Same check, looped over every file in a restored directory snapshot — each
# file also has its own independent hex/baseline from dir_intake's per-file
# loop, so this is just verify_clonepool_copy applied per file. Prints
# "corrupt|verified|unverified" counts.
verify_directory_snapshot() {
  local snapshot="$1"
  local corrupt=0 verified=0 unverified=0
  local f fname fhex result
  while IFS= read -r -d '' f; do
    fname=$(basename "${f}")
    fhex=$(to_hex "${fname}")
    result=$(verify_clonepool_copy "${fhex}" "${f}")
    case "${result}" in
      CORRUPT)     corrupt=$((corrupt+1)); echo "  [CORRUPT] ${fname}" >&2 ;;
      valid)       verified=$((verified+1)) ;;
      no_baseline) unverified=$((unverified+1)) ;;
    esac
  done < <(find "${snapshot}" -type f -print0)
  echo "${corrupt}|${verified}|${unverified}"
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
    "${dir}/${SCRIPT_HEX}.sidecar.json" "1" "${size}" "false" "${dir}/v1_${SCRIPT_NAME}"
  upload_to_r2 "${SCRIPT_HEX}" "${dir}/v1_${SCRIPT_NAME}"
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

  # ── Sensitive-name check ──────────────────────────────────────
  local sensitive="false"
  if is_sensitive_name "${orig}"; then
    echo ""
    echo " ⚠  WARNING — SENSITIVE FILE: ${orig}"
    echo " ⚠  This file will be stored in clonepool AND reported to D1,"
    echo " ⚠  flagged sensitive=true so downstream consumers can restrict it."
    echo ""
    echo "  [1] Proceed — intake and flag sensitive"
    echo "  [2] Cancel"
    echo ""
    read -rp "  Choice [1/2]: " sens_choice
    if [[ "${sens_choice}" != "1" ]]; then
      echo " [intake:CANCEL] Sensitive file — intake cancelled"
      return 0
    fi
    sensitive="true"
  fi

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
    "${filetype}" "${category_hex}" "${size}" "${backend}" "${notes}" "${checksum}" "${sensitive}"
  enrich_sidecar_companions "${sidecar}" "${companion_list}"
  custody_log_local "${hex}" "${orig}" "intake" "${version}" \
    "${filepath}" "${pool_dir}/${version}_${orig}" "white" "${backend}"
  report_clonepool "${hex}" "${orig}" "${version}" "white" \
    "${pool_dir}" "${sidecar}" "1" "${size}" "${sensitive}" "${pool_dir}/${version}_${orig}"
  upload_to_r2 "${hex}" "${pool_dir}/${version}_${orig}"
  report_custody  "${hex}" "${orig}" "intake" "white" "${backend}"
  report_glossary "${hex}" "${orig}" "Intaked via ${backend}: ${filetype}" \
    "${category_hex}" "${version}" "${size}" "${pool_dir}"

  # ── Auto evict old versions for this file ─────────────────
  evict_old_versions "${pool_dir}" "${orig}" "true"

  # ── Suite auto-registration ────────────────────────────────
  # If this is a .suite.json manifest, place it at clonepool/<name>/.suite.json
  # so `usys run <name>` can find it immediately. No manual clone step needed.
  if [[ "${orig}" == *.suite.json ]]; then
    local suite_name=""
    if command -v jq &>/dev/null; then
      suite_name=$(jq -r '.name // empty' "${filepath}" 2>/dev/null)
    fi
    if [[ -z "${suite_name}" ]]; then
      suite_name=$(grep -o '"name"[[:space:]]*:[[:space:]]*"[^"]*"' "${filepath}" 2>/dev/null \
        | head -1 | sed 's/.*"name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/')
    fi
    if [[ -n "${suite_name}" && "${suite_name}" != */* && "${suite_name}" != *\\* ]]; then
      local suite_dir="${CLONEPOOL_DIR}/${suite_name}"
      mkdir -p "${suite_dir}"
      # Re-resolve latest after eviction — copy the surviving version
      local suite_latest; suite_latest=$(get_latest_file "${pool_dir}" "${orig}" || true)
      [[ -z "${suite_latest}" ]] && suite_latest="${pool_dir}/${version}_${orig}"
      cp "${suite_latest}" "${suite_dir}/.suite.json"
      echo "[intake:SUITE] ${suite_name} → clonepool/${suite_name}/ — runnable: usys run ${suite_name}"
    fi
  fi

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
  local req_version="${2:-latest}"  # optional: specific version e.g. v2

  if [[ -z "${name}" ]]; then
    echo "[intake] Usage: intake clone <filename> [version]"
    echo "         e.g.:  intake clone myfile.py"
    echo "         e.g.:  intake clone myfile.py v2"
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

  # Resolve the target file — latest or specific version
  local target
  if [[ "${req_version}" == "latest" ]]; then
    target=$(get_latest_file "${pool_dir}" "${name}")
    if [[ -z "${target}" ]]; then
      echo "[intake:MISS] No versioned files found for '${name}' in clonepool"
      return 1
    fi
  else
    target="${pool_dir}/${req_version}_${name}"
    if [[ ! -f "${target}" ]]; then
      echo "[intake:MISS] Version '${req_version}' of '${name}' not found in clonepool"
      echo "  Available versions:"
      ls "${pool_dir}"/v*_"${name}" 2>/dev/null \
        | while read -r f; do
            num=$(basename "${f}" | grep -o '^v[0-9]*')
            echo "    ${num}"
          done || echo "    (none)"
      return 1
    fi
  fi

  local version; version=$(basename "${target}" | grep -o '^v[0-9]*')
  local dest="${PWD}/${name}"

  local verify_result; verify_result=$(verify_clonepool_copy "${hex}" "${target}")
  case "${verify_result}" in
    CORRUPT)
      echo ""
      echo " ⚠  INTEGRITY FAILURE — clonepool copy of '${name}' does not match"
      echo " ⚠  its recorded hash. Refusing to clone a corrupted or altered file."
      echo " ⚠  Re-intake ${name} from a trusted source to fix this."
      echo ""
      log "WARN" "clone out BLOCKED (hash mismatch): ${name} ${version}"
      return 1
      ;;
    no_baseline)
      echo "[intake:WARN] No integrity baseline yet for '${name}' — cloning unverified"
      ;;
    valid)
      echo "[intake:OK] Integrity verified — matches D1 baseline"
      ;;
  esac

  if [[ -f "${dest}" ]]; then
    echo "[intake:WARN] '${name}' already exists here — overwriting with ${version}"
  fi

  cp "${target}" "${dest}"

  log "INFO" "clone out: ${name} ${version} → ${dest}"
  custody_log_local "${hex}" "${name}" "clone_out" "${version}" \
    "${target}" "${dest}" "white" "user"
  report_custody "${hex}" "${name}" "clone_out" "white" "user"

  echo "[intake:OK] ${name} ${version} → ${PWD}/"
  if [[ "${req_version}" == "latest" ]]; then
    echo "[intake:OK] This is the latest version — ready to use"
  else
    echo "[intake:OK] Version ${version} restored"
  fi
  return 0
}

# ══════════════════════════════════════════════════════════════
# PRUNE — manual eviction of old versions across whole pool
# ══════════════════════════════════════════════════════════════
intake_prune() {
  echo ""
  echo " Scanning clonepool — evicting versions beyond ${MAX_VERSIONS} per file..."
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
  echo " Files checked    : ${files_checked}"
  echo " Versions evicted : ${total_evicted}"
  echo " Retention        : ${MAX_VERSIONS} versions per file"
  echo " Latest version   : always kept"
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
  local sensitive="false"
  is_sensitive_name "${pkg_name}" && sensitive="true"

  mkdir -p "${pool_dir}"
  write_sidecar_basic "${sidecar}" "${hex}" "${pkg_name}" "${version}" \
    "package:${backend}" "7061636b61676573" "0" "${backend}" \
    "installed from ${backend}" "" "${sensitive}"
  custody_log_local "${hex}" "${pkg_name}" "backend_install" "${version}" \
    "${backend}" "${pool_dir}" "white" "${backend}"
  report_clonepool "${hex}" "${pkg_name}" "${version}" "white" \
    "${pool_dir}" "${sidecar}" "1" "0" "${sensitive}"
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
  echo " Retention: ${MAX_VERSIONS} versions per file"
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
    intake clone <file> v2           Pull specific file version here
    intake clone <dir> v2            Pull specific directory snapshot here
    intake clone <file.lol>          Short syntax works too

  MAINTENANCE:
    intake prune                     Evict versions beyond ${MAX_VERSIONS} per file across pool
    intake status                    Show clonepool status
    intake help                      This screen

  Duplicate handling:
    If you intake a file identical to what's already in the pool,
    intake asks: keep existing / replace / keep both

  Version eviction:
    Phoenix keeps the ${MAX_VERSIONS} most recent versions of each file
    A version is displaced only when a new intake pushes the count past ${MAX_VERSIONS}
    Latest version is always kept — never evicted
    Files with only one version are never evicted
    3 days is the rollback window — the time you have to roll back before a
    new intake can displace an older version. Not a deletion timer.

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
SKIP_DIRS=("node_modules" ".git" "__pycache__" ".svn" "vendor" "dist" "build" ".next" ".nuxt" "venv" ".venv" "env" ".tox" "coverage" ".nyc_output" "target" "out" ".wrangler" ".idea" ".gradle" "clonepool" "archive")
SKIP_EXTENSIONS=(".jpg" ".jpeg" ".png" ".gif" ".webp" ".svg" ".ico" ".bmp" ".tiff" ".mp4" ".mp3" ".wav" ".avi" ".mov" ".zip" ".tar" ".gz" ".rar" ".7z" ".exe" ".dll" ".so" ".dylib" ".bin" ".dat" ".db" ".sqlite" ".lock" ".qcow2" ".img")

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
    xml|html|htm|css|c|h|cpp|hpp|rs|go|ps1|\
    kt|kts|php|gradle|properties|bat|cmd|jsonc|spec) return 0 ;;
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
        # Record the actual matched skip-pattern name, not the top-level
        # path component — a hit on nested/__pycache__ should report
        # "__pycache__", not "nested".
        local already=false
        for s in "${skipped_dirs[@]:-}"; do [[ "$s" == "$skip" ]] && already=true; done
        [[ "${already}" == "false" ]] && skipped_dirs+=("${skip}")
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
      is_sensitive_name "${f}" && sensitive_files+=("${rel}")
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
    echo "  Ignored  : ${#skipped_files[@]} files (binary/media, or unrecognized extension)"
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

  # INTAKE_YES=1 bypasses the interactive prompt (used by intake_project)
  local choice
  if [[ "${INTAKE_YES:-0}" == "1" ]]; then
    choice="1"
    log "INFO" "dir intake: non-interactive mode (INTAKE_YES=1)"
  else
    echo "  [1] Proceed — intake all files"
    echo "  [2] Exclude .env and sensitive files"
    echo "  [3] Cancel"
    echo ""
    read -rp "  Choice [1/2/3]: " choice
  fi

  case "${choice}" in
    1) log "INFO" "dir intake: proceeding with full intake" ;;
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
  local any_sensitive_included=false

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

    # Was this file flagged sensitive earlier? (already survived the
    # proceed/exclude gate above — if excluded, it's not in known_files)
    local file_sensitive="false"
    for sf in "${sensitive_files[@]}"; do
      [[ "${rel}" == "${sf}" ]] && file_sensitive="true" && break
    done
    [[ "${file_sensitive}" == "true" ]] && any_sensitive_included=true

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
      "${backend}" "dir:${dirname}/${rel}" "${checksum}" "${file_sensitive}"

    custody_log_local "${file_hex}" "${file_orig}" "dir_intake" \
      "${file_version}" "${f}" "${file_pool}/${file_version}_${file_orig}" \
      "white" "${backend}"
    report_clonepool "${file_hex}" "${file_orig}" "${file_version}" "white" \
      "${file_pool}" "${sidecar}" "1" "${size}" "${file_sensitive}" "${file_pool}/${file_version}_${file_orig}"
    upload_to_r2 "${file_hex}" "${file_pool}/${file_version}_${file_orig}"
    report_custody "${file_hex}" "${file_orig}" "dir_intake" "white" "${backend}"

    # Auto evict old versions
    evict_old_versions "${file_pool}" "${file_orig}" "true"

    manifest_entries+="  {\"hex\":\"${file_hex}\",\"name\":\"${file_orig}\",\"path\":\"${rel}\",\"version\":\"${file_version}\",\"checksum\":\"${checksum}\"},"
    (( success++ )) || true
    # Phoenix progress line — single in-place update, no per-file scroll
    printf "\r  Phoenix  %d / %d  %-60s" "${success}" "${#known_files[@]}" "${rel}"
  done
  echo ""  # terminate the progress line

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
  "sensitive": ${any_sensitive_included},
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
    "${pool_dir}" "${dir_sidecar}" "1" "${total_size}" "${any_sensitive_included}"
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

  # Machine-readable output for intake_project() caller
  if [[ "${INTAKE_YES:-0}" == "1" ]]; then
    echo "[intake:DIR:HEX] ${hex}"
    echo "[intake:DIR:VER] ${version}"
  fi
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

  echo "[intake] Verifying snapshot integrity..."
  local vresult; vresult=$(verify_directory_snapshot "${snapshot}")
  local v_corrupt v_verified v_unverified
  IFS='|' read -r v_corrupt v_verified v_unverified <<< "${vresult}"
  if (( v_corrupt > 0 )); then
    echo ""
    echo " ⚠  INTEGRITY FAILURE — ${v_corrupt} file(s) in '${name}' ${ver} do not match"
    echo " ⚠  their recorded hash. Refusing to clone a corrupted or altered snapshot."
    echo " ⚠  Re-intake ${name}/ from a trusted source to fix this."
    echo ""
    log "WARN" "dir clone out BLOCKED (${v_corrupt} hash mismatches): ${name}"
    return 1
  fi
  echo "[intake:OK] Integrity verified — ${v_verified} matched, ${v_unverified} unverified (no baseline yet)"

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
    # project clone takes priority, then directory, then single file
    if [[ "${name}" == "project" ]]; then
      shift
      intake_clone_project "$@"
    else
      intake_clone_directory "${name}" "${version}" 2>/dev/null \
        || intake_clone "${name}" "${version}"
    fi
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
