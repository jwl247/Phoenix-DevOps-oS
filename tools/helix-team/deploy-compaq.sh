#!/usr/bin/env bash
# deploy-compaq.sh — put this checkout's Helix team on a Linux box at
# /opt/phoenix, install the services, verify, and bring the box's
# verification ledger back into the repo. The scripted form of the
# "git archive to /opt/phoenix" pattern that was only prose in the session log.
#
#   tools/helix-team/deploy-compaq.sh [ssh-alias]      default: pbm-compaq
#   HELIX_PROFILE=drive tools/helix-team/deploy-compaq.sh helix-vm
#
# Sends exactly the committed tree (git archive HEAD), never the working
# copy, so what runs on the box is a commit you can name. Old copies are
# left in place (tar overwrites file by file; nothing is deleted).
set -euo pipefail
HOST=${1:-pbm-compaq}
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
COMMIT=$(git rev-parse --short HEAD)
if [ -n "$(git status --porcelain sector1 sector3 sector4 tools/helix-team scripts/verify.sh)" ]; then
  echo "uncommitted changes in the team paths: commit first, so the box runs a nameable commit" >&2
  exit 1
fi
PATHS="sector1/kernels sector1/helix sector1/security sector1/helix-lightning sector3/services sector3/translator sector3/romeo_juliet sector3/quadengine sector4 tools/helix-team scripts/verify.sh"

echo "== $HOST: ship commit $COMMIT"
git archive --format=tar HEAD $PATHS \
  | ssh "$HOST" 'sudo mkdir -p /opt/phoenix && sudo tar -x -C /opt/phoenix && echo "'"$COMMIT"'" | sudo tee /opt/phoenix/.deployed-commit >/dev/null'

echo "== $HOST: install the team"
ssh "$HOST" "sudo HELIX_PROFILE='${HELIX_PROFILE:-}' bash /opt/phoenix/tools/helix-team/install-team.sh"

echo "== $HOST: verify"
set +e
ssh "$HOST" "sudo bash /opt/phoenix/tools/helix-team/verify-team.sh"
VRC=$?
set -e

echo "== $HOST: pull the ledger back"
DATE_UTC=$(date -u +%Y-%m-%d)
mkdir -p "verification/$DATE_UTC"
# box logs are prefixed with the host so they never collide with the runner's
ssh "$HOST" "cd /opt/phoenix/verification/$DATE_UTC 2>/dev/null && tar -c team-*.log summary.json" \
  | tar -x -C "verification/$DATE_UTC" --transform "s/^/$HOST-/" 2>/dev/null || echo "no ledger on $HOST yet"
ls "verification/$DATE_UTC" | grep "^$HOST-" | sed 's/^/  /'
echo "== done: verify-team exit $VRC (0 = every check passed)"
exit "$VRC"
