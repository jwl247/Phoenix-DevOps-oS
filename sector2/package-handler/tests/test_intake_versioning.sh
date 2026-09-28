#!/usr/bin/env bash
# Versioning tests for sector2/package-handler/intake.sh — real intake.sh, a
# temporary clone pool, and tests/fake_worker.py standing in for packages-worker.
# Every assertion is a file on disk or a request the fake worker recorded.
#
#   bash sector2/package-handler/tests/test_intake_versioning.sh
#
# Exit code = number of failed assertions. Needs: bash, python3, curl, openssl.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INTAKE="${HERE}/../intake.sh"
WORK="$(mktemp -d)"
export HOME="${WORK}/home"; mkdir -p "${HOME}"
export CLONEPOOL_DIR="${WORK}/pool"
export PHOENIX_AUTH="test-token"
export FAKE_PHOENIX_AUTH="test-token"
export INTAKE_YES=1
STATE="${WORK}/worker"; mkdir -p "${STATE}"
PORT=$(( 20000 + RANDOM % 20000 ))
export PHOENIX_WORKER_URL="http://127.0.0.1:${PORT}"

python3 "${HERE}/fake_worker.py" "${PORT}" "${STATE}" &
WPID=$!
trap 'kill ${WPID} 2>/dev/null; rm -rf "${WORK}"' EXIT
for _ in $(seq 1 50); do
  curl -s -o /dev/null -H "Authorization: Bearer ${PHOENIX_AUTH}" "${PHOENIX_WORKER_URL}/whoami" && break
  sleep 0.1
done

pass=0; fail=0
ok()   { if eval "$1"; then pass=$((pass+1)); echo "  ok   $2"; else fail=$((fail+1)); echo "  FAIL $2"; fi; }
hexof() { python3 -c 'import sys;print(sys.argv[1].encode().hex())' "$1"; }
sha3p() { openssl dgst -sha3-512 -r "$1" | awk '{print substr($1,1,16)}'; }
reqs() { grep -c "\"method\": \"$1\", \"path\": \"$2\"" "${STATE}/requests.jsonl" 2>/dev/null || echo 0; }
run_intake() { bash "${INTAKE}" "$@" >"${WORK}/last.out" 2>&1; echo $? >"${WORK}/last.rc"; }

SRC="${WORK}/src"; mkdir -p "${SRC}"

echo "== to_hex without xxd matches python"
h_a=$(cd "${WORK}" && PATH="/usr/bin:/bin" bash -c 'source <(sed -n "/^to_hex()/,/^}/p" "$1"); to_hex "alpha.txt"' _ "${INTAKE}")
ok "[[ '${h_a}' == '$(hexof alpha.txt)' ]]" "to_hex(alpha.txt) = $(hexof alpha.txt) (od fallback)"

echo "== single file: v1, current bytes + version bytes reach R2"
printf 'one\n' > "${SRC}/alpha.txt"
run_intake "${SRC}/alpha.txt"
HEX=$(hexof alpha.txt)
ok "[[ -f '${CLONEPOOL_DIR}/T1/${HEX}/v1_alpha.txt' ]]" "v1_alpha.txt stored in T1"
ok "[[ $(reqs PUT /clonepool/${HEX}) -eq 1 ]]" "PUT current bytes once"
P1=$(sha3p "${SRC}/alpha.txt")
ok "[[ $(reqs PUT /clonepool/${HEX}/versions/${P1}) -eq 1 ]]" "PUT version bytes at ${HEX}/versions/${P1}"
ok "cmp -s '${STATE}/objects/${HEX}__versions__${P1}' '${SRC}/alpha.txt'" "version object bytes == file bytes"

echo "== changed content: v2, second version object, first one untouched"
printf 'two\n' > "${SRC}/alpha.txt"
run_intake "${SRC}/alpha.txt"
P2=$(sha3p "${SRC}/alpha.txt")
ok "[[ -f '${CLONEPOOL_DIR}/T1/${HEX}/v2_alpha.txt' ]]" "v2_alpha.txt stored"
ok "[[ $(reqs PUT /clonepool/${HEX}/versions/${P2}) -eq 1 ]]" "PUT version bytes for v2"
ok "cmp -s '${STATE}/objects/${HEX}__versions__${P1}' <(printf 'one\n')" "v1 object still holds 'one'"
ok "[[ $(python3 -c "import json;print(len([v for v in json.load(open('${STATE}/versions.json')) if v['package']=='alpha.txt']))") -eq 2 ]]" "two versions rows for alpha.txt"

echo "== identical re-intake, choice 1: no new version, no new upload"
before_puts=$(reqs PUT /clonepool/${HEX})
echo 1 | INTAKE_YES=0 bash "${INTAKE}" "${SRC}/alpha.txt" >"${WORK}/last.out" 2>&1
ok "[[ ! -f '${CLONEPOOL_DIR}/T1/${HEX}/v3_alpha.txt' ]]" "no v3 on identical bytes"
ok "[[ $(reqs PUT /clonepool/${HEX}) -eq ${before_puts} ]]" "no extra current-bytes PUT"

echo "== rotated bucket (T3) continues history back in T1 (S2CORE-F07)"
mkdir -p "${CLONEPOOL_DIR}/T3" && mv "${CLONEPOOL_DIR}/T1/${HEX}" "${CLONEPOOL_DIR}/T3/${HEX}"
printf 'three\n' > "${SRC}/alpha.txt"
run_intake "${SRC}/alpha.txt"
ok "[[ -f '${CLONEPOOL_DIR}/T1/${HEX}/v3_alpha.txt' ]]" "v3 written to the T1 bucket"
ok "[[ -f '${CLONEPOOL_DIR}/T1/${HEX}/v1_alpha.txt' && ! -d '${CLONEPOOL_DIR}/T3/${HEX}' ]]" "one bucket: history v1..v3 together, T3 copy gone"

echo "== directory: second identical intake keeps every file in the snapshot"
D="${SRC}/teamdir"; mkdir -p "${D}/sub"
printf 'a\n' > "${D}/a.py"; printf 'b\n' > "${D}/sub/b.sh"
run_intake "${D}"
DHEX=$(hexof teamdir)
ok "[[ -f '${CLONEPOOL_DIR}/T1/${DHEX}/v1_teamdir/a.py' && -f '${CLONEPOOL_DIR}/T1/${DHEX}/v1_teamdir/sub/b.sh' ]]" "v1 snapshot complete"
run_intake "${D}"
ok "[[ -f '${CLONEPOOL_DIR}/T1/${DHEX}/v2_teamdir/a.py' && -f '${CLONEPOOL_DIR}/T1/${DHEX}/v2_teamdir/sub/b.sh' ]]" "v2 snapshot complete (dup-skip no longer drops files)"
ok "[[ ! -f '${CLONEPOOL_DIR}/T1/$(hexof a.py)/v2_a.py' ]]" "unchanged a.py did not get a per-file v2"
ok "grep -q '\"path\": *\"sub/b.sh\"\\|\"path\":\"sub/b.sh\"' '${CLONEPOOL_DIR}/T1/${DHEX}/${DHEX}.sidecar.json'" "v2 sidecar lists sub/b.sh"

echo "== directory with a suite manifest becomes runnable in clonepool/<name>/"
S="${SRC}/suitedir"; mkdir -p "${S}"
printf 'echo hi\n' > "${S}/run.sh"
cat > "${S}/team.suite.json" <<'J'
{ "name": "team-x", "version": "1.0.0", "type": "service", "entry": "run.sh", "runtime": "bash" }
J
run_intake "${S}"
ok "[[ -f '${CLONEPOOL_DIR}/team-x/.suite.json' && -f '${CLONEPOOL_DIR}/team-x/run.sh' ]]" "clonepool/team-x/ has .suite.json + entry"
ok "grep -q 'runnable: usys run team-x' '${WORK}/last.out'" "intake announces the runnable suite"

echo "== tier rotation moves an aged bucket and PATCHes D1"
python3 - "${CLONEPOOL_DIR}/T1/${DHEX}/${DHEX}.sidecar.json" <<'PY'
import sys, re, datetime
p = sys.argv[1]; s = open(p).read()
old = (datetime.datetime.utcnow() - datetime.timedelta(days=2)).strftime('%Y-%m-%dT%H:%M:%SZ')
s = re.sub(r'"registered_at": "[^"]*"', f'"registered_at": "{old}"', s, count=1)
open(p, 'w').write(s)
PY
run_intake prune
ok "[[ -d '${CLONEPOOL_DIR}/T2/${DHEX}' && ! -d '${CLONEPOOL_DIR}/T1/${DHEX}' ]]" "2-day-old bucket rotated T1 -> T2"
ok "[[ $(reqs PATCH /clonepool/${DHEX}/tier) -ge 1 ]]" "PATCH /clonepool/<hex>/tier sent"
run_intake "${D}"
ok "[[ -d '${CLONEPOOL_DIR}/T1/${DHEX}/v3_teamdir' && ! -d '${CLONEPOOL_DIR}/T2/${DHEX}' ]]" "re-intake after rotation: v3 in T1, T2 bucket gone"

echo "== clone-out restores a specific version"
( cd "${WORK}" && bash "${INTAKE}" clone alpha.txt v1 >/dev/null 2>&1 )
ok "[[ \"\$(cat '${WORK}/alpha.txt')\" == 'one' ]]" "intake clone alpha.txt v1 -> 'one'"

echo "== wrong token is refused before any file is touched"
rm -rf "${CLONEPOOL_DIR}/T1/$(hexof zeta.txt)"
printf 'z\n' > "${SRC}/zeta.txt"
PHOENIX_AUTH=wrong bash "${INTAKE}" "${SRC}/zeta.txt" >"${WORK}/last.out" 2>&1
ok "[[ ! -d '${CLONEPOOL_DIR}/T1/$(hexof zeta.txt)' ]]" "nothing written with a rejected token"

echo
echo "passed ${pass}, failed ${fail}"
exit "${fail}"
