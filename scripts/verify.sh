#!/usr/bin/env bash
# verify.sh — verification to disk. Runs every check the repo has and writes
# the result of each one to verification/<UTC date>/<check>.log plus one line
# in verification/<date>/summary.json. Nothing is "verified" in Phoenix
# without a line here (Jerry, 2026-09-28: "i want verification of everything
# to disk from now on").
#
#   scripts/verify.sh                 run everything
#   scripts/verify.sh --only intake   run checks whose name contains "intake"
#   scripts/verify.sh --list          print check names
#   VERIFY_DIR=/opt/phoenix/verification scripts/verify.sh   (box-side ledger)
#
# Exit code: number of failed checks. Same script on this repo's CI runner,
# the Precision (Git Bash), the Compaq and pbm3: the summary records the host,
# so a line from a box that could load the kernel is distinguishable from one
# that could not. Checks that cannot run where they are invoked (no pwsh, no
# node, no kernel) are recorded as "skipped" with the reason — a skip is not
# a pass and is not a fail; it is a fact.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"
DATE_UTC="$(date -u +%Y-%m-%d)"
OUT="${VERIFY_DIR:-${ROOT}/verification}/${DATE_UTC}"
mkdir -p "${OUT}"
SUMMARY="${OUT}/summary.json"
HOST="${VERIFY_HOST:-$(hostname 2>/dev/null || echo unknown)}"
COMMIT="$(git rev-parse --short HEAD 2>/dev/null || echo nogit)"
DIRTY="$(git status --porcelain 2>/dev/null | grep -q . && echo true || echo false)"
ONLY=""; LIST=0
while (( $# )); do
  case "$1" in
    --only) ONLY="$2"; shift 2 ;;
    --list) LIST=1; shift ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

pass=0; fail=0; skip=0
[[ -f "${SUMMARY}" ]] || echo "[]" > "${SUMMARY}"

# record <name> <exit|skipped> <seconds> <command> <reason>
record() {
  local name="$1" result="$2" secs="$3" cmd="$4" reason="${5:-}"
  python3 - "${SUMMARY}" "${name}" "${result}" "${secs}" "${cmd}" "${reason}" "${COMMIT}" "${DIRTY}" "${HOST}" <<'PY'
import json, sys, datetime
path, name, result, secs, cmd, reason, commit, dirty, host = sys.argv[1:]
rows = json.load(open(path))
rows = [r for r in rows if r["check"] != name]           # one line per check per day: latest wins
rows.append({"check": name, "result": result, "seconds": float(secs), "command": cmd,
             "reason": reason, "commit": commit, "dirty": dirty == "true", "host": host,
             "utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")})
json.dump(sorted(rows, key=lambda r: r["check"]), open(path, "w"), indent=1)
PY
}

# check <name> <needs-cmd|-> <command...>
check() {
  local name="$1" needs="$2"; shift 2
  if [[ -n "${ONLY}" && "${name}" != *"${ONLY}"* ]]; then return; fi
  if (( LIST )); then echo "${name}"; return; fi
  local log="${OUT}/${name}.log"
  # needs: "-" (nothing), a command name, or "file:/abs/path" (a header, a device…)
  local missing=""
  if [[ "${needs}" == file:* ]]; then
    [[ -e "${needs#file:}" ]] || missing="${needs#file:}"
  elif [[ "${needs}" != "-" ]] && ! command -v "${needs}" &>/dev/null; then
    missing="${needs}"
  fi
  if [[ -n "${missing}" ]]; then
    printf 'SKIPPED: %s not present on %s\n' "${missing}" "${HOST}" > "${log}"
    record "${name}" "skipped" 0 "$*" "${missing} not present"
    skip=$((skip+1)); printf '  skip  %-40s (%s missing)\n' "${name}" "${missing}"; return
  fi
  local t0 t1 rc
  t0=$(date +%s.%N)
  { echo "# ${name}"; echo "# host=${HOST} commit=${COMMIT} dirty=${DIRTY} utc=$(date -u +%FT%TZ)"; echo "# \$ $*"; echo; } > "${log}"
  ( eval "$*" ) >> "${log}" 2>&1; rc=$?
  t1=$(date +%s.%N)
  local secs; secs=$(python3 -c "print(round(${t1}-${t0},3))")
  echo "# exit=${rc}" >> "${log}"
  record "${name}" "${rc}" "${secs}" "$*"
  if (( rc == 0 )); then pass=$((pass+1)); printf '  ok    %-40s %ss\n' "${name}" "${secs}"
  else fail=$((fail+1)); printf '  FAIL  %-40s exit %s  -> %s\n' "${name}" "${rc}" "${log#${ROOT}/}"; fi
}

# ── Syntax: every script in the tree (archive/ and node_modules excluded) ──
check syntax-bash - 'rc=0; while IFS= read -r -d "" f; do bash -n "$f" || { echo "FAIL $f"; rc=1; }; done < <(find . -path ./archive -prune -o -path "*/node_modules" -prune -o -path ./verification -prune -o -name "*.sh" -print0); exit $rc'
check syntax-python python3 'python3 -m compileall -q $(find . -path ./archive -prune -o -path "*/node_modules" -prune -o -path "*/.venv" -prune -o -name "*.py" -print) && echo compiled'
check syntax-node node 'rc=0; while IFS= read -r -d "" f; do node --check "$f" 2>/dev/null || { echo "FAIL $f"; rc=1; }; done < <(find . -path ./archive -prune -o -path "*/node_modules" -prune -o \( -name "*.js" -o -name "*.mjs" -o -name "*.cjs" \) -print0); exit $rc'
check syntax-powershell pwsh 'pwsh -NoProfile -Command "\$e=0; Get-ChildItem -Recurse -Filter *.ps1 | Where-Object FullName -notmatch \"\\\\archive\\\\|/archive/\" | ForEach-Object { \$t=\$null; \$err=\$null; [System.Management.Automation.Language.Parser]::ParseFile(\$_.FullName,[ref]\$t,[ref]\$err) | Out-Null; if (\$err) { \$e++; Write-Output (\"FAIL \" + \$_.FullName); \$err | ForEach-Object { Write-Output (\"  \" + \$_.Message) } } }; exit \$e"'

# ── Unit / integration tests ──
check test-intake-versioning python3 'bash sector2/package-handler/tests/test_intake_versioning.sh'
check test-hands python3 'python3 hands/test_hands.py'
check test-portal python3 'python3 portal/test_server.py'
check test-meshd python3 'python3 sector3/phoenix-net/meshd/test_meshd.py'
check test-helix-vram python3 'HELIX_VRAM_NO_KERNEL=1 python3 sector1/helix/test_helix_vram.py'
check test-helix-vramd python3 'HELIX_VRAM_NO_KERNEL=1 python3 sector1/helix/test_helix_vramd.py'
check test-guardian python3 'python3 sector4/guardian/test_guardian.py'
check test-copes-guardians python3 'python3 sector1/security/test_guardians.py'
check test-ball-permissions python3 'python3 sector1/helix-lightning/test_ball_permissions.py'
check test-radar-worker node 'cd pbm-consulting-website/radar-worker && node --test test.mjs'
check test-leads-worker node 'cd pbm-consulting-website/worker && node --test test.mjs'
check test-office-worker node 'cd phoenix-office/worker && node --test test.mjs'
check test-meds-worker node 'cd sector2/apps/lifefirst/meds-worker && node --test test.mjs'
check test-mesh-worker node 'cd sector3/phoenix-net/mesh-worker && node --test test.mjs'
check test-config-centralizer node 'cd dashboard && node --test config-centralizer.test.js'
check test-usys-suite-gate pwsh 'pwsh -NoProfile -File scripts/usys-suite-gate.Tests.ps1'
check test-usys-vm-args pwsh '[ -f scripts/usys-vm-args.Tests.ps1 ] && pwsh -NoProfile -File scripts/usys-vm-args.Tests.ps1 || echo "no such test yet"'

# ── Workers: does each one at least build? (no account needed for --dry-run) ──
for w in sector2/package-handler/worker pbm-consulting-website/radar-worker pbm-consulting-website/worker phoenix-office/worker sector2/apps/office/notify-worker sector2/apps/lifefirst/meds-worker sector3/phoenix-net/mesh-worker; do
  n="wrangler-dry-run-$(basename "$(dirname "$w")")-$(basename "$w")"
  check "${n}" npx "cd ${w} && npx --yes wrangler@latest deploy --dry-run --outdir /tmp/wrangler-dry-\$\$ 2>&1 | tail -5"
done

# ── C: userspace pieces compile (kernel modules need a kernel tree: box-side) ──
check build-libhelix gcc 'cd sector1/kernels/libhelix && gcc -O2 -shared -fPIC -o /tmp/libhelix-verify.so libhelix.c && echo built'
check build-phoenix-core curl-config 'cd phoenix-core && make -n >/dev/null && make -s clean >/dev/null 2>&1; make -s 2>&1 | tail -20'

if (( LIST )); then exit 0; fi
echo
echo "verification/${DATE_UTC}: ${pass} passed, ${fail} failed, ${skip} skipped  (host ${HOST}, commit ${COMMIT}, dirty ${DIRTY})"
echo "ledger: ${SUMMARY#${ROOT}/}"
exit "${fail}"
