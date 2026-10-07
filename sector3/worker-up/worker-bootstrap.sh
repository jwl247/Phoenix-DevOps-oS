#!/usr/bin/env bash
# worker-bootstrap.sh — the only file a blank machine needs to become a Phoenix
# worker: it pulls intake.sh from Phoenix in R2 (checked against D1), then uses
# it to pull the operations set. Everything else comes from the cloud.
# Step 4 of "Phoenix from the cloud, a worker on the ground"
# (docs/plans/compaq-road-test-plan.md, Phase 4; timings are measurement M1).
#
#   worker-bootstrap.sh <workdir> <name> [<name> ...]
#     <workdir>  where the worker lives (on the box's ingress Helix)
#     <name>     things to pull: a directory (kernels, frank …) or a file
#
# Needs: bash, curl, openssl (sha3-512). Box credential (0600, pushed over the
# control plane, never in the repo): ~/.phoenix-worker/{url,auth}
# Output: <workdir>/ops/<name>, a pool + intake home under <workdir>, and one
# JSON line per step in <workdir>/bootstrap.jsonl (nanosecond timings).
set -euo pipefail

WD=${1:?usage: worker-bootstrap.sh <workdir> <name> [<name> ...]}; shift
[[ $# -gt 0 ]] || { echo "name at least one thing to pull"; exit 2; }
CRED="$HOME/.phoenix-worker"
URL=$(cat "$CRED/url"); AUTH=$(cat "$CRED/auth")
[[ -n "$URL" && -n "$AUTH" ]] || { echo "no box credential in $CRED"; exit 1; }
# Keys never go on curl's argv (visible in ps / /proc to every user, A2-N1): headers come from a
# 0600 file written with the printf builtin and removed on exit.
HDR=$(umask 077; mktemp); trap 'rm -f "$HDR"' EXIT
printf 'Authorization: Bearer %s\n' "$AUTH" > "$HDR"
mkdir -p "$WD/bin" "$WD/pool" "$WD/home" "$WD/ops"
LOG="$WD/bootstrap.jsonl"
now() { date +%s%N; }
rec() { printf '{"step":"%s","ns":%s,"ok":%s,"detail":"%s"}\n' "$1" "$2" "$3" "$4" >> "$LOG"; }
t0=$(now)

# ── 1. intake.sh itself, from R2, checked against D1 ─────────────────────
H=$(printf 'intake.sh' | od -An -tx1 | tr -d ' \n')
s=$(now)
want=$(curl -s -H @"$HDR" "$URL/clonepool/$H?meta=true" \
       | grep -o '"hash_sha3"[[:space:]]*:[[:space:]]*"[0-9a-f]*"' | head -1 | grep -o '[0-9a-f]\{64,\}')
curl -s -f -H @"$HDR" "$URL/clonepool/$H" -o "$WD/bin/intake.sh.part"
got=$(openssl dgst -sha3-512 -r "$WD/bin/intake.sh.part" | awk '{print $1}')
if [[ -z "$want" || "$got" != "$want" ]]; then
  rm -f "$WD/bin/intake.sh.part"; rec intake.sh $(( $(now) - s )) false "sha3 mismatch or no D1 hash"
  echo "intake.sh from R2 does not match its D1 hash — stopping"; exit 1
fi
mv "$WD/bin/intake.sh.part" "$WD/bin/intake.sh"
rec intake.sh $(( $(now) - s )) true "verified sha3-512 against D1"
echo "  ok  intake.sh (verified)"

# ── 2. the operations set, through the import method ─────────────────────
run_intake() {
  env -i PATH="$PATH" HOME="$WD/home" PHOENIX_WORKER_URL="$URL" PHOENIX_AUTH="$AUTH" \
    CF_ACCESS_CLIENT_ID="" CF_ACCESS_CLIENT_SECRET="" CLONEPOOL_DIR="$WD/pool" INTAKE_YES=1 \
    bash "$WD/bin/intake.sh" "$@" </dev/null
}
fail=0
for name in "$@"; do
  s=$(now)
  rm -rf "${WD:?}/ops/$name"
  if (cd "$WD/ops" && run_intake clone "$name" > "$WD/home/clone-$name.log" 2>&1) && [[ -e "$WD/ops/$name" ]]; then
    n=$(find "$WD/ops/$name" -type f | wc -l)
    rec "clone:$name" $(( $(now) - s )) true "$n files"
    echo "  ok  $name ($n files)"
  else
    rec "clone:$name" $(( $(now) - s )) false "see home/clone-$name.log"
    echo "  FAIL $name (log: $WD/home/clone-$name.log)"; fail=$((fail+1))
  fi
done
rec total $(( $(now) - t0 )) "$([[ $fail -eq 0 ]] && echo true || echo false)" "$# items, $fail failed"
printf '== bootstrap %s in %.2f s\n' "$([[ $fail -eq 0 ]] && echo complete || echo INCOMPLETE)" "$(echo "$(( $(now) - t0 ))" | awk '{print $1/1e9}')"
[[ $fail -eq 0 ]]
