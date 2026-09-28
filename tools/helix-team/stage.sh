#!/usr/bin/env bash
# stage.sh — build the two clone directories of the Helix team from git HEAD:
#
#   helix-team-ingress/   .suite.json with PHOENIX_HELIX_ROLE=ingress
#   helix-team-egress/    .suite.json with PHOENIX_HELIX_ROLE=egress
#
# Both hold exactly the same files (the committed team paths); only the
# manifest differs. Distinct directory names give distinct hex identities in
# the clone pool (hex = name), so both clones keep their own history. Intake
# them with scripts/hsf-intake.sh <dir>/ — the directory-intake suite hook
# lands each in clonepool/<name>/ ready for `usys run helix-team-ingress`.
#
#   tools/helix-team/stage.sh [out-dir]     default: ./staging
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT="${1:-$ROOT/staging}"
cd "$ROOT"
COMMIT=$(git rev-parse --short HEAD)
PATHS="sector1/kernels/libhelix sector1/helix sector1/helix-lightning sector3/translator sector3/romeo_juliet sector4/guardian tools/helix-team"

for role in ingress egress; do
  dir="$OUT/helix-team-$role"
  rm -rf "$dir"; mkdir -p "$dir"
  git archive --format=tar HEAD $PATHS | tar -x -C "$dir"
  echo "$COMMIT" > "$dir/.team-commit"
  cat > "$dir/.suite.json" <<EOF
{
  "name": "helix-team-$role",
  "version": "1.0.0",
  "description": "The Helix team as the $role half: $( [ $role = ingress ] && echo 'Helix-I + Romeo' || echo 'Helix-E + Juliet (translator fires on output only)' ), plus the memory manager and the ring guardian. Peer with the other half over the Phoenix Mesh.",
  "author": "jwl247",
  "type": "service",
  "entry": "tools/helix-team/run-team.sh",
  "runtime": "bash",
  "dependencies": ["py-3", "pyzmq"],
  "environment": {
    "PHOENIX_HELIX_ROLE": "$role",
    "PHOENIX_TEAM_ROOT": "auto:suite-root"
  },
  "permissions": ["filesystem:read", "filesystem:write", "network:loopback", "network:mesh"],
  "metadata": {
    "category": "helix-team",
    "tags": ["helix", "$role", "romeo-juliet", "vram", "guardian", "team"],
    "commit": "$COMMIT",
    "ports": $( [ $role = ingress ] && echo '{"helix_i": "7701-7704", "romeo_in": 5580}' || echo '{"helix_e": "7805-7808", "juliet_in": 5581, "juliet_out": 5582}' ),
    "peer_env": "PHOENIX_RJ_PEER / PHOENIX_RJ_BIND / PHOENIX_RJ_SECRET (secret from the vault, never here)",
    "license": "GPL-3.0"
  }
}
EOF
  n=$(find "$dir" -type f | wc -l)
  echo "staged $dir ($n files, commit $COMMIT)"
done
