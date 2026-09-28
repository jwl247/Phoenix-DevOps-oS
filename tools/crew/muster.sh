#!/usr/bin/env bash
# muster.sh — call the crew: every sailor runs one watch (with the deck's checks
# when --checks is given) and the deck report prints. Exit = findings.
#   tools/crew/muster.sh            drift + never-list + services + heartbeats
#   tools/crew/muster.sh --checks   plus each deck's scripts/verify.sh checks
set -uo pipefail
R="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
exec python3 "$R/sector4/guardian/sailor.py" muster "$@"
