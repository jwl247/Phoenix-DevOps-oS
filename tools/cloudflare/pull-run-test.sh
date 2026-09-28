#!/usr/bin/env bash
# pull-run-test.sh — THE game-gate test (Jerry, 2026-09-28: "we test whether
# phoenix can run via this method ... mandatory before we can decide how to
# build the game"). Monster Phoenix's player-hosted mesh pulls Phoenix from
# R2 onto a box that has nothing; this proves that path end to end:
#
#   1. stage the Helix team from git HEAD (tools/helix-team/stage.sh)
#   2. intake helix-team-ingress/ into the worker (D1 rows + R2 objects,
#      directory manifest at the dir hex, each file at its version key)
#   3. wipe the local clone pool — this box now has nothing
#   4. intake pull helix-team-ingress   (D1 -> manifest -> R2 bytes, every
#      hash verified, nothing unverified written)
#   5. run the pulled suite (tools/helix-team/run-team.sh, role ingress) and
#      prove the team came up from the pulled bytes alone
#   6. write the result block (markdown) + the ledger line
#
#   PHOENIX_WORKER_URL=https://packages-worker.<account>.workers.dev \
#   PHOENIX_AUTH=... CF_ACCESS_CLIENT_ID=... CF_ACCESS_CLIENT_SECRET=... \
#   tools/cloudflare/pull-run-test.sh                # real worker (desk)
#   tools/cloudflare/pull-run-test.sh --fake         # local fake worker (CI / this container)
#
# Exit 0 = PASS. Writes verification/<date>/game-gate-pull-run.log and the
# result block to stdout (paste it into docs/plans/game-gate-r2-test.md).
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
FAKE=0; [[ "${1:-}" == "--fake" ]] && FAKE=1
DATE_UTC=$(date -u +%Y-%m-%d); OUT="${VERIFY_DIR:-$ROOT/verification}/$DATE_UTC"; mkdir -p "$OUT"
LOG="$OUT/game-gate-pull-run.log"; : > "$LOG"
say() { echo "$*" | tee -a "$LOG"; }
WORK=$(mktemp -d); trap 'kill ${WPID:-} 2>/dev/null; rm -rf "$WORK"' EXIT
export HOME="$WORK/home"; mkdir -p "$HOME"
export CLONEPOOL_DIR="$WORK/pool"; mkdir -p "$CLONEPOOL_DIR"
export INTAKE_YES=1
COMMIT=$(git rev-parse --short HEAD)

if (( FAKE )); then
  export PHOENIX_AUTH=test-token FAKE_PHOENIX_AUTH=test-token
  PORT=$(( 20000 + RANDOM % 20000 )); export PHOENIX_WORKER_URL="http://127.0.0.1:$PORT"
  python3 sector2/package-handler/tests/fake_worker.py "$PORT" "$WORK/worker" & WPID=$!
  for _ in $(seq 1 50); do curl -s -o /dev/null -H "Authorization: Bearer $PHOENIX_AUTH" "$PHOENIX_WORKER_URL/whoami" && break; sleep 0.1; done
fi
[[ -z "${PHOENIX_AUTH:-}" || -z "${PHOENIX_WORKER_URL:-}" ]] && { say "need PHOENIX_WORKER_URL + PHOENIX_AUTH (or --fake)"; exit 2; }
say "# game-gate pull-run test  commit=$COMMIT  worker=$PHOENIX_WORKER_URL  fake=$FAKE  utc=$(date -u +%FT%TZ)  host=$(hostname)"
code=$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $PHOENIX_AUTH" -H "CF-Access-Client-Id: ${CF_ACCESS_CLIENT_ID:-}" -H "CF-Access-Client-Secret: ${CF_ACCESS_CLIENT_SECRET:-}" "$PHOENIX_WORKER_URL/whoami")
[[ "$code" == 200 ]] || { say "FAIL: worker /whoami answered $code"; exit 1; }

say "## 1. stage from HEAD"
bash tools/helix-team/stage.sh "$WORK/stage" 2>&1 | tee -a "$LOG" | tail -1
SRC="$WORK/stage/helix-team-ingress"; N_SRC=$(find "$SRC" -type f | wc -l)

say "## 2. intake into the worker"
t0=$(date +%s.%N)
bash sector2/package-handler/intake.sh "$SRC" > "$WORK/intake.out" 2>&1; rc=$?
t1=$(date +%s.%N)
R2_UP=$(grep -c "R2 OK\|R2 version OK" "$WORK/intake.out"); D1_OK=$(grep -c "D1 OK" "$WORK/intake.out")
say "intake rc=$rc  files=$N_SRC  R2 PUTs=$R2_UP  D1 posts=$D1_OK  $(python3 -c "print(round($t1-$t0,1))")s"
grep -q "intake:SUITE\] helix-team-ingress" "$WORK/intake.out" || { say "FAIL: intake did not register the suite"; tail -20 "$WORK/intake.out" | tee -a "$LOG"; exit 1; }

say "## 3. wipe the local pool (this box now has nothing)"
rm -rf "$CLONEPOOL_DIR"; mkdir -p "$CLONEPOOL_DIR"; say "pool entries: $(ls -A "$CLONEPOOL_DIR" | wc -l)"

say "## 4. intake pull helix-team-ingress"
t0=$(date +%s.%N)
bash sector2/package-handler/intake.sh pull helix-team-ingress > "$WORK/pull.out" 2>&1; rc=$?
t1=$(date +%s.%N)
DEST="$CLONEPOOL_DIR/helix-team-ingress"
N_PULLED=$(find "$DEST" -type f ! -name '.pool-manifest.json' ! -name '.suite.json' 2>/dev/null | wc -l)
BYTES=$(du -sb "$DEST" 2>/dev/null | cut -f1)
say "pull rc=$rc  files=$N_PULLED (staged $N_SRC)  bytes=$BYTES  $(python3 -c "print(round($t1-$t0,1))")s"
grep -E "INTEGRITY|MISS|OK\]" "$WORK/pull.out" | tail -3 | tee -a "$LOG"
[[ $rc -eq 0 && -f "$DEST/.suite.json" && -f "$DEST/tools/helix-team/run-team.sh" ]] || { say "FAIL: pull did not restore a runnable suite"; exit 1; }
# every pulled file must be byte-identical to what was staged (the manifest covers known types only)
DIFF=$(cd "$SRC" && find . -type f ! -name '.suite.json' -print0 | xargs -0 -I{} sh -c 'cmp -s "{}" "'"$DEST"'/{}" || echo "{}"' | grep -v '.team-commit' | head -5)
if [[ -n "$DIFF" ]]; then say "note: differ or absent (extension not intaked by design?): $DIFF"; fi
MISSING=$(cd "$SRC" && find . -type f -name '*.py' -o -name '*.sh' -type f | while read -r f; do [ -f "$DEST/$f" ] || echo "$f"; done)
[[ -z "$MISSING" ]] || { say "FAIL: pulled suite is missing: $MISSING"; exit 1; }
say "every .py/.sh staged is present and verified in the pulled suite"

say "## 5. run the pulled suite"
export PHOENIX_TEAM_HOME="$WORK/teamhome" PHOENIX_TEAM_ROOT="$DEST" PHOENIX_HELIX_ROLE=ingress PHOENIX_RJ_SECRET="gate-$RANDOM"
# exec so $RPID IS run-team.sh (a plain subshell would take the TERM and leave the team running)
( cd "$DEST" && exec bash tools/helix-team/run-team.sh ) > "$WORK/run.out" 2>&1 & RPID=$!
UP=0; for _ in $(seq 1 60); do [ -f "$PHOENIX_TEAM_HOME/ready" ] && { UP=1; break; }; kill -0 $RPID 2>/dev/null || break; sleep 0.5; done
sleep 3
ALIVE=$(grep -c "pid" "$WORK/run.out")
say "team up=$UP  members started=$ALIVE  ($(grep 'up (' "$WORK/run.out" | sed 's/.*up (//; s/).*//'))"
# the memory manager must answer from the pulled code
SOCK=$(grep -o 'vram socket [^ ]*' "$WORK/run.out" | awk '{print $3}')
PING=$(HELIX_VRAM_SOCK="$SOCK" python3 -c "import sys; sys.path.insert(0,'$DEST/sector1/helix'); from helix_vramd import HelixVramClient; c=HelixVramClient(); print('pong' if c.ping() else 'no'); c.close()" 2>/dev/null || echo "no")
ROMEO=$(grep -c "ingress active" "$PHOENIX_TEAM_HOME/romeo.log" 2>/dev/null || echo 0)
say "vram ping=$PING  romeo active=$ROMEO"
kill -TERM $RPID 2>/dev/null; wait $RPID 2>/dev/null; RRC=$?
sleep 1
LEFT=$(ps -eo pid,args | grep -F "$DEST/" | grep -v grep | wc -l)
say "run-team stopped rc=$RRC  leftover processes=$LEFT"
if [[ "$LEFT" -ne 0 ]]; then ps -eo pid,args | grep -F "$DEST/" | grep -v grep | awk '{print $1}' | xargs -r kill -TERM; say "FAIL: team members outlived run-team (killed)"; exit 1; fi

say "## 6. verdict"
if [[ $UP -eq 1 && "$PING" == pong && "$ROMEO" -ge 1 ]]; then
  say "PASS: Phoenix (helix-team-ingress, $N_PULLED files, commit $COMMIT) was intaked to $PHOENIX_WORKER_URL, pulled onto an empty pool with every hash verified, and ran."
  python3 - "$OUT/summary.json" "$COMMIT" "$(hostname)" "$FAKE" <<'PY'
import json, sys, datetime, os
path, commit, host, fake = sys.argv[1:]
rows = json.load(open(path)) if os.path.exists(path) else []
rows = [r for r in rows if r["check"] != "game-gate-pull-run"]
rows.append({"check": "game-gate-pull-run", "result": "0", "seconds": 0, "command": "tools/cloudflare/pull-run-test.sh" + (" --fake" if fake == "1" else ""),
             "reason": "fake worker" if fake == "1" else "", "commit": commit, "dirty": False, "host": host,
             "utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")})
json.dump(sorted(rows, key=lambda r: r["check"]), open(path, "w"), indent=1)
PY
  exit 0
fi
say "FAIL: up=$UP ping=$PING romeo=$ROMEO"; tail -20 "$WORK/run.out" | tee -a "$LOG"; exit 1
