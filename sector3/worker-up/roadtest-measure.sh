#!/usr/bin/env bash
# roadtest-measure.sh — measurements M2–M6 of the Compaq road test
# (docs/plans/compaq-road-test-plan.md §3), run ON the worker box after
# worker-bootstrap.sh (M1). Precision rule (docs/helix/BENCHMARKS.md):
# nanosecond clocks, results at microsecond resolution or finer.
#
#   roadtest-measure.sh <workdir>        e.g. /srv/helix-ingress/phoenix-roadtest
#
# Uses the box credential in ~/.phoenix-worker and <workdir>/bin/intake.sh.
# Needs sudo for: dropping the page cache, dmsetup status, and the egress
# managed-vs-unmanaged switch (helix@egress stopped, the same partition mounted
# raw, then helix@egress restored — dm-helix maps the partition 1:1, so the
# filesystem is the same either way).
#
#   M4  push: egress -> R2 + D1 receipt, Helix-managed vs unmanaged (same disk)
#   M2  pull: a 64 MiB object R2 -> ingress (network), then re-read from ingress
#       Helix cold (page cache dropped) and warm
#   M3  small-object latency p50/p95, 1 KiB..1 MiB, new connection per request
#       and one kept-alive connection
#   M5  tamper: altered bytes in R2 must be refused by intake clone
#   M6  both Helix instances' counters around each phase
# Results: <workdir>/measure/results.json
set -euo pipefail

WD=${1:?usage: roadtest-measure.sh <workdir>}
URL=$(cat ~/.phoenix-worker/url); AUTH=$(cat ~/.phoenix-worker/auth)
M="$WD/measure"; rm -rf "$M"; mkdir -p "$M/pool" "$M/home" "$M/out"
RES="$M/results.jsonl"; : > "$RES"
INTAKE="$WD/bin/intake.sh"
EG_RAW=/srv/egress-raw
now() { date +%s%N; }
put() { printf '%s\n' "$1" >> "$RES"; }
hx() { sudo dmsetup status "helix-$1" 2>/dev/null | sed 's/^.* helix //' ; }
snap() { put "{\"m\":\"M6\",\"at\":\"$1\",\"ingress\":\"$(hx ingress)\",\"egress\":\"$(hx egress)\"}"; }
drop() { sync; echo 3 | sudo tee /proc/sys/vm/drop_caches >/dev/null; }
intake() { # workdir-local intake, isolated pool/home
  env -i PATH="$PATH" HOME="$M/home" PHOENIX_WORKER_URL="$URL" PHOENIX_AUTH="$AUTH" \
    CF_ACCESS_CLIENT_ID="" CF_ACCESS_CLIENT_SECRET="" CLONEPOOL_DIR="$M/pool" INTAKE_YES=1 \
    bash "$INTAKE" "$@" </dev/null
}
gen() { # <bytes> <file>: random printable data (base64 text); no pipe for pipefail to trip on
  python3 -c "import os,base64,sys; n=int(sys.argv[1]); open(sys.argv[2],'wb').write(base64.b64encode(os.urandom(n))[:n])" "$1" "$2"
}
hexof() { printf '%s' "$1" | od -An -tx1 | tr -d ' \n'; }
say() { printf '  %-6s %s\n' "$1" "$2"; }
echo "== road-test measurements on $(hostname) $(date -Is)"
snap start

# ── M4: push through egress, managed vs unmanaged ────────────────────────
push_set() { # label dir — stage on egress (write + fsync, timed), then push (timed)
  local label=$1 dir=$2 st_total=0 pu_total=0 bytes=0 s e1 e2 f
  mkdir -p "$dir"
  gen 16777216 "$M/payload"
  for kb in 64 1024 16384; do
    f="$dir/rt-$label-${kb}k.bin.txt"          # .txt: a type intake accepts
    drop
    s=$(now); head -c $((kb*1024)) "$M/payload" > "$f"; sync -f "$f"; e1=$(( $(now) - s ))
    drop
    s=$(now); intake "$f" roadtest "M4 $label" >"$M/push-$label-$kb.log" 2>&1; e2=$(( $(now) - s ))
    st_total=$((st_total+e1)); pu_total=$((pu_total+e2)); bytes=$((bytes+kb*1024))
    put "{\"m\":\"M4\",\"mode\":\"$label\",\"bytes\":$((kb*1024)),\"stage_ns\":$e1,\"push_ns\":$e2}"
  done
  say M4 "$label: stage $(awk -v b=$bytes -v n=$st_total 'BEGIN{printf "%.2f MiB/s", (b/1048576)/(n/1e9)}') · push incl. D1 receipt $(awk -v b=$bytes -v n=$pu_total 'BEGIN{printf "%.2f MiB/s (%.2f s)", (b/1048576)/(n/1e9), n/1e9}')"
}
sudo mkdir -p /srv/helix-egress/phoenix-roadtest-push && sudo chown "$(id -u):$(id -g)" /srv/helix-egress/phoenix-roadtest-push
push_set managed /srv/helix-egress/phoenix-roadtest-push
snap after-M4-managed
sudo systemctl stop helix@egress.service
sudo mkdir -p "$EG_RAW"; sudo mount /dev/disk/by-partlabel/helix-egress "$EG_RAW"; sudo chown "$(id -u):$(id -g)" "$EG_RAW"
push_set unmanaged "$EG_RAW/phoenix-roadtest-push"
sudo umount "$EG_RAW"; sudo systemctl start helix@egress.service
[[ -n "$(hx egress)" ]] || { echo "helix@egress did not come back — stopping"; exit 1; }
snap after-M4-unmanaged

# ── M2: a 64 MiB object, pulled then re-read ─────────────────────────────
BIG="$M/src/rt-big-64m.bin.txt"; mkdir -p "$M/src"
gen 67108864 "$BIG"
intake "$BIG" roadtest "M2 source" >"$M/big-up.log" 2>&1
rm -rf "$M/pool"/* "$M/out"/*; drop
s=$(now); (cd "$M/out" && intake clone rt-big-64m.bin.txt >"$M/big-down.log" 2>&1); e=$(( $(now) - s ))
[[ -f "$M/out/rt-big-64m.bin.txt" ]] || { echo "M2 pull failed — see $M/big-down.log"; exit 1; }
put "{\"m\":\"M2\",\"what\":\"pull R2->ingress (verified)\",\"bytes\":67108864,\"ns\":$e}"
say M2 "pull 64 MiB R2 -> ingress, verified: $(awk -v n=$e 'BEGIN{printf "%.3f s = %.3f MiB/s", n/1e9, 64/(n/1e9)}')"
for pass in cold warm; do
  [[ $pass == cold ]] && drop
  s=$(now); cat "$M/out/rt-big-64m.bin.txt" > /dev/null; e=$(( $(now) - s ))
  put "{\"m\":\"M2\",\"what\":\"re-read from ingress Helix ($pass)\",\"bytes\":67108864,\"ns\":$e}"
  say M2 "re-read 64 MiB from ingress ($pass): $(awk -v n=$e 'BEGIN{printf "%.6f s = %.1f MiB/s", n/1e9, 64/(n/1e9)}')"
done
snap after-M2

# ── M3: small objects ─────────────────────────────────────────────────────
for kb in 1 16 256 1024; do
  f="$M/src/rt-small-${kb}k.bin.txt"; gen $((kb*1024)) "$f"
  intake "$f" roadtest "M3 source" >/dev/null 2>&1
  h=$(hexof "rt-small-${kb}k.bin.txt")
  fresh=$(for i in $(seq 1 20); do curl -s -o /dev/null -w '%{time_total}\n' -H "Authorization: Bearer $AUTH" "$URL/clonepool/$h"; done)
  args=(); for i in $(seq 1 20); do args+=(-o /dev/null "$URL/clonepool/$h"); done
  kept=$(curl -s -w '%{time_total}\n' -H "Authorization: Bearer $AUTH" "${args[@]}")
  line=$(python3 - "$kb" "$fresh" "$kept" <<'PY'
import sys,statistics as st
kb=sys.argv[1]
def pct(xs,p): xs=sorted(xs); return xs[min(len(xs)-1,int(round(p/100*(len(xs)-1))))]*1000
f=[float(x) for x in sys.argv[2].split()]; k=[float(x) for x in sys.argv[3].split()]
print(f'{{"m":"M3","kib":{kb},"new_conn_p50_ms":{pct(f,50):.3f},"new_conn_p95_ms":{pct(f,95):.3f},"keepalive_p50_ms":{pct(k,50):.3f},"keepalive_p95_ms":{pct(k,95):.3f},"n":{len(f)}}}')
PY
)
  put "$line"
  say M3 "$(python3 -c "import json,sys;d=json.loads(sys.argv[1]);print(f\"{d['kib']:>5} KiB  new conn p50 {d['new_conn_p50_ms']:.1f} / p95 {d['new_conn_p95_ms']:.1f} ms   kept-alive p50 {d['keepalive_p50_ms']:.1f} / p95 {d['keepalive_p95_ms']:.1f} ms\")" "$line")"
done
snap after-M3

# ── M5: tamper ────────────────────────────────────────────────────────────
h=$(hexof rt-small-16k.bin.txt)
curl -s -H "Authorization: Bearer $AUTH" "$URL/clonepool/$h" -o "$M/tamper.orig"
printf 'altered by roadtest-measure M5\n' > "$M/tamper.bad"
curl -s -X PUT -H "Authorization: Bearer $AUTH" --data-binary "@$M/tamper.bad" "$URL/clonepool/$h" >/dev/null
rm -rf "$M/pool"/* "$M/out"/*
(cd "$M/out" && intake clone rt-small-16k.bin.txt >"$M/tamper.log" 2>&1) || true
if [[ -f "$M/out/rt-small-16k.bin.txt" ]]; then refused=false; else refused=true; fi
curl -s -X PUT -H "Authorization: Bearer $AUTH" --data-binary "@$M/tamper.orig" "$URL/clonepool/$h" >/dev/null
rm -rf "$M/pool"/* "$M/out"/*
(cd "$M/out" && intake clone rt-small-16k.bin.txt >"$M/tamper-restored.log" 2>&1) || true
[[ -f "$M/out/rt-small-16k.bin.txt" ]] && restored=true || restored=false
put "{\"m\":\"M5\",\"tampered_refused\":$refused,\"restored_clones\":$restored}"
say M5 "tampered object refused: $refused   after restore clones: $restored"
snap end

python3 - "$RES" > "$M/results.json" <<'PY'
import json,sys
print(json.dumps([json.loads(l) for l in open(sys.argv[1])], indent=1))
PY
echo "== done: $M/results.json"
