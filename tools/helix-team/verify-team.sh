#!/usr/bin/env bash
# verify-team.sh — is the Helix team up, linked, and doing its job on this box?
# Every check writes to the verification ledger (same format as scripts/verify.sh):
#   /opt/phoenix/verification/<date>/team-<check>.log + summary.json
# Exit code = failed checks. Run as root (dmsetup, /dev/helix_intent, journal).
#
#   verify-team.sh            all checks
#   VERIFY_DIR=... verify-team.sh
set -uo pipefail
R=${PHOENIX_ROOT:-/opt/phoenix}
export VERIFY_DIR="${VERIFY_DIR:-$R/verification}"
export VERIFY_HOST="${VERIFY_HOST:-$(hostname)}"
DATE_UTC=$(date -u +%Y-%m-%d)
OUT="$VERIFY_DIR/$DATE_UTC"; mkdir -p "$OUT"
SUMMARY="$OUT/summary.json"; [ -f "$SUMMARY" ] || echo "[]" > "$SUMMARY"
COMMIT=$(git -C "$R" rev-parse --short HEAD 2>/dev/null || cat "$R/.deployed-commit" 2>/dev/null || echo unknown)
pass=0; fail=0

record() {  # name exit secs cmd
  python3 - "$SUMMARY" "$1" "$2" "$3" "$4" "$COMMIT" "$VERIFY_HOST" <<'PY'
import json, sys, datetime
path, name, result, secs, cmd, commit, host = sys.argv[1:]
rows = [r for r in json.load(open(path)) if r["check"] != name]
rows.append({"check": name, "result": result, "seconds": float(secs), "command": cmd, "reason": "",
             "commit": commit, "dirty": False, "host": host,
             "utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")})
json.dump(sorted(rows, key=lambda r: r["check"]), open(path, "w"), indent=1)
PY
}
check() {  # name command...
  local name="team-$1"; shift
  local log="$OUT/$name.log" t0 t1 rc
  t0=$(date +%s.%N)
  { echo "# $name"; echo "# host=$VERIFY_HOST commit=$COMMIT utc=$(date -u +%FT%TZ)"; echo "# \$ $*"; echo; } > "$log"
  ( eval "$*" ) >> "$log" 2>&1; rc=$?
  t1=$(date +%s.%N); echo "# exit=$rc" >> "$log"
  record "$name" "$rc" "$(python3 -c "print(round($t1-$t0,3))")" "$*"
  if (( rc == 0 )); then pass=$((pass+1)); printf '  ok    %-34s\n' "$name"
  else fail=$((fail+1)); printf '  FAIL  %-34s -> %s\n' "$name" "$log"; fi
}

check helix-active          'systemctl is-active helix.service'
check helix-dm-status       'dmsetup status helix && dmsetup table helix | grep -q " helix " && cat /proc/helix'
check helix-dm-double       'dmsetup table helix | awk "{print NF}" | grep -qx 7 && echo "double strand (7 fields)"'
check helix-modules         'lsmod | grep -E "^(helix|frank3_slot_a|frank3_slot_b) "'
check helix-dmesg-clean     '! dmesg | grep -iE "helix.*(oops|bug|warn|error)" | tail -5'
check paging-active         'systemctl is-active phoenix-paging.service'
check paging-kernel-fed     'journalctl -u phoenix-paging -b --no-pager | grep -iE "helix.*(kernel|linked|attached)" | tail -3'
check paging-dash-loopback  'ss -ltn | grep ":8888 " | grep -q "127.0.0.1:8888" && echo "8888 on loopback only"'
check vram-active           'systemctl is-active helix-vram.service'
check vram-socket-perms     'stat -c "%a %U:%G %n" /run/phoenix/helix-vram.sock | grep -q "^660 " && stat -c "%a %n" /run/phoenix/helix-vram.sock'
check vram-round-trip       'HELIX_LIBHELIX_DIR=$R/sector1/kernels/libhelix python3 - <<EOF
import sys, os, time
sys.path.insert(0, "$R/sector1/helix")
from helix_vramd import HelixVramClient
with HelixVramClient() as c:
    assert c.ping()
    k = "verify-%d" % int(time.time())
    c.alloc(k, {"n": 1}); assert c.read(k) == {"n": 1}; assert c.free(k)
    s = c.stat(); print("kernel_linked", s["dandelion"]["kernel_linked"], "blocks", s["total_blocks"])
    assert s["dandelion"]["kernel_linked"] is True, "vramd is not linked to helix.ko"
EOF'
check translator-on-vram    'python3 - <<EOF
import sys; sys.path.insert(0, "$R/sector1/helix")
from helix_translator import HelixTranslator, helix_backend_from_daemon
c = helix_backend_from_daemon(); tr = HelixTranslator(c)
p = tr.translate_malloc(16); assert tr.translate_write(p, b"ok"); assert tr.translate_read(p, 2) == b"ok"; assert tr.translate_free(p); c.close(); print("translator ok")
EOF'
check guardian-active       'systemctl is-active helix-guardian.service'
check guardian-heartbeat    'python3 - <<EOF
import json, time, datetime
hb = json.load(open("/var/lib/phoenix/guardian/heartbeat.json"))
age = time.time() - datetime.datetime.strptime(hb["at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc).timestamp()
print(hb, "age_s", round(age)); assert age < 900, "heartbeat older than 15 min"
EOF'
check guardian-no-conflicts 'PHOENIX_GUARDIAN_HOME=/var/lib/phoenix/guardian python3 $R/sector4/guardian/integrated_guardian.py status'
check translator-sh         'bash -n $R/sector3/translator/translator.sh && $R/sector3/translator/translator.sh deps 2>&1 | head -3'

echo
echo "team on $VERIFY_HOST: $pass passed, $fail failed  (ledger $SUMMARY)"
exit "$fail"
