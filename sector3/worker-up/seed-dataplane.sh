#!/usr/bin/env bash
# seed-dataplane.sh — put the Phoenix operations set into a data plane stood up
# by dataplane-up.sh, through the import method (intake.sh), so every file
# lands with a hex identity, a SHA3-512, a D1 custody row and its R2 bytes.
# Step 2 of "Phoenix from the cloud, a worker on the ground"
# (docs/plans/compaq-road-test-plan.md, Phase 1).
#
#   seed-dataplane.sh <name> [list-file]     default list: operations-set.txt
#
# Isolation (the road test's hard rule: our system stays unaffected):
#   intake.sh keeps a catalog in ~/.catalog, logs in ~/.unitedsys and a local
#   pool in CLONEPOOL_DIR. All three are pointed INSIDE this data plane's state
#   dir, and every Phoenix variable is set explicitly, so nothing from the
#   caller's environment (our worker URL, our PHOENIX_AUTH) can leak in.
# Re-runnable: intake keeps an identical existing version instead of adding one.
# Unattended: INTAKE_YES=1 answers intake's "proceed?" menu with "intake all".
# That would include files intake flags as sensitive (.env, *secret*, *token*,
# *auth*…), so keep the operations set free of them — checked 2026-09-29.
set -euo pipefail

NAME=${1:?usage: seed-dataplane.sh <name> [list-file]}
HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/../.." && pwd)
LIST=${2:-$HERE/operations-set.txt}
STATE="$HOME/.phoenix/worker-up/$NAME"
[[ -s "$STATE/auth" && -s "$STATE/url" ]] || { echo "no data plane state in $STATE — run dataplane-up.sh $NAME first"; exit 1; }

SEED_HOME="$STATE/seed-home"
mkdir -p "$SEED_HOME/pool"
COMMIT=$(git -C "$REPO" rev-parse --short HEAD)
DIRTY=$(git -C "$REPO" status --porcelain -- $(grep -vE '^\s*(#|$)' "$LIST") | head -1)
[[ -z "$DIRTY" ]] || { echo "uncommitted changes under the operations set — commit first so every seeded file maps to one commit"; exit 1; }

run_intake() {
  env -i PATH="$PATH" HOME="$SEED_HOME" USERPROFILE="$SEED_HOME" \
    PHOENIX_WORKER_URL="$(cat "$STATE/url")" PHOENIX_AUTH="$(cat "$STATE/auth")" \
    CF_ACCESS_CLIENT_ID="" CF_ACCESS_CLIENT_SECRET="" \
    CLONEPOOL_DIR="$SEED_HOME/pool" PHOENIX_INTAKE="" INTAKE_YES=1 \
    bash "$REPO/sector2/package-handler/intake.sh" "$@" </dev/null
}

echo "== seeding $NAME from commit $COMMIT"
start=$(date +%s)
ok=0; bad=0
while IFS= read -r rel; do
  [[ -z "$rel" || "$rel" == \#* ]] && continue
  src="$REPO/$rel"
  [[ -e "$src" ]] || { echo "  MISSING  $rel"; bad=$((bad+1)); continue; }
  if run_intake "$src" "roadtest" "seed $COMMIT" >"$STATE/seed-$(echo "$rel" | tr '/' '_').log" 2>&1; then
    echo "  ok       $rel"; ok=$((ok+1))
  else
    echo "  FAIL     $rel   (log: $STATE/seed-$(echo "$rel" | tr '/' '_').log)"; bad=$((bad+1))
  fi
done < "$LIST"
echo "$COMMIT" > "$STATE/seeded.commit"
echo "== seeded $ok ok, $bad failed, $(( $(date +%s) - start ))s"
[[ $bad -eq 0 ]]
