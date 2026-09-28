#!/usr/bin/env bash
# run-team.sh — the Helix team as ONE runnable suite (entry of helix-team-*.suite.json).
#
#   PHOENIX_HELIX_ROLE=ingress  run-team.sh     Helix-I (7701-7704) + Romeo (5580 -> peer Juliet)
#   PHOENIX_HELIX_ROLE=egress   run-team.sh     Helix-E (7805-7808) + Juliet (5581 in / 5582 out, translator on output)
#   PHOENIX_HELIX_ROLE=plain    run-team.sh     memory manager + guardian only
#
# Every role runs the memory manager (helix_vramd) and the ring guardian.
# Members are supervised here (this is the process `usys run` / a unit holds):
# one dies -> everything is stopped and the exit code says which. SIGTERM/INT
# stops the whole team in reverse order. Works unprivileged: state and sockets
# go under $PHOENIX_TEAM_HOME (default ~/.phoenix/helix-team) unless the
# systemd paths (/run/phoenix, /var/lib/...) are writable.
#
# Peering (egress on another box, ingress here):
#   PHOENIX_RJ_PEER=pbm3.phx:5581  PHOENIX_RJ_SECRET=<from the vault>  (ingress box)
#   PHOENIX_RJ_BIND=<this box's mesh IP> PHOENIX_RJ_SECRET=<same>         (egress box)
# The secret never lives in a manifest or the repo: it comes from the
# environment (vault -> /etc/default/helix-team on the box).
set -uo pipefail
ROLE="${PHOENIX_HELIX_ROLE:-plain}"
ROOT="${PHOENIX_TEAM_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
HOME_DIR="${PHOENIX_TEAM_HOME:-$HOME/.phoenix/helix-team}"
mkdir -p "$HOME_DIR"
[ -f /etc/default/helix-team ] && . /etc/default/helix-team

# state locations: system paths when writable, else the team home
if [ -w /run/phoenix ] 2>/dev/null || { [ "$(id -u)" = 0 ] && mkdir -p /run/phoenix 2>/dev/null; }; then
  : "${HELIX_VRAM_SOCK:=/run/phoenix/helix-vram.sock}"
else
  : "${HELIX_VRAM_SOCK:=$HOME_DIR/helix-vram.sock}"
fi
if [ "$(id -u)" = 0 ]; then
  : "${HELIX_VRAM_STRAND_B:=/var/lib/helix/vram}"; : "${PHOENIX_GUARDIAN_HOME:=/var/lib/phoenix/guardian}"
else
  : "${HELIX_VRAM_STRAND_B:=$HOME_DIR/vram}"; : "${PHOENIX_GUARDIAN_HOME:=$HOME_DIR/guardian}"
fi
: "${PHOENIX_SHM:=$HOME_DIR/shm}"
: "${TRANSLATOR_SH:=$ROOT/sector3/translator/translator.sh}"
[ -c /dev/helix_intent ] || export HELIX_VRAM_NO_KERNEL=1        # no helix.ko here: she runs standalone
export HELIX_VRAM_SOCK HELIX_VRAM_STRAND_B PHOENIX_GUARDIAN_HOME PHOENIX_SHM TRANSLATOR_SH
export HELIX_LIBHELIX_DIR="${HELIX_LIBHELIX_DIR:-$ROOT/sector1/kernels/libhelix}"
export PYTHONUNBUFFERED=1

case "$ROLE" in
  ingress|egress|plain) ;;
  *) echo "run-team: PHOENIX_HELIX_ROLE must be ingress|egress|plain (got '$ROLE')" >&2; exit 2 ;;
esac
if [ "$ROLE" = egress ] && [ "${PHOENIX_RJ_BIND:-127.0.0.1}" != 127.0.0.1 ] && [ -z "${PHOENIX_RJ_SECRET:-}" ]; then
  echo "run-team: egress bound off loopback needs PHOENIX_RJ_SECRET" >&2; exit 2
fi

declare -a PIDS NAMES
start() {  # name cmd...
  local name="$1"; shift
  "$@" > "$HOME_DIR/$name.log" 2>&1 &
  PIDS+=($!); NAMES+=("$name")
  echo "run-team[$ROLE]: $name pid $! (log $HOME_DIR/$name.log)"
}
stop_all() {
  local i
  for (( i=${#PIDS[@]}-1; i>=0; i-- )); do
    kill -TERM "${PIDS[$i]}" 2>/dev/null || true
  done
  for (( i=${#PIDS[@]}-1; i>=0; i-- )); do
    for _ in 1 2 3 4 5 6 7 8 9 10; do kill -0 "${PIDS[$i]}" 2>/dev/null || break; sleep 0.5; done
    kill -KILL "${PIDS[$i]}" 2>/dev/null || true
  done
}
trap 'echo "run-team[$ROLE]: stopping"; stop_all; exit 0' TERM INT

start helix-vram python3 "$ROOT/sector1/helix/helix_vramd.py" serve
start helix-guardian python3 "$ROOT/sector4/guardian/integrated_guardian.py" guardian_1 daemon
case "$ROLE" in
  ingress)
    start helix-i python3 "$ROOT/sector1/helix-lightning/helixi.py"
    start romeo   python3 "$ROOT/sector3/romeo_juliet/romeo.py"
    ;;
  egress)
    start helix-e python3 "$ROOT/sector1/helix-lightning/helixe.py"
    start juliet  python3 "$ROOT/sector3/romeo_juliet/juliet.py"
    ;;
esac
echo "run-team[$ROLE]: up (${NAMES[*]}); vram socket $HELIX_VRAM_SOCK"
[ -f "$HOME_DIR/ready" ] || : > "$HOME_DIR/ready"

# supervise: the first member to die takes the team down, with its name in the exit
while true; do
  for i in "${!PIDS[@]}"; do
    if ! kill -0 "${PIDS[$i]}" 2>/dev/null; then
      wait "${PIDS[$i]}" 2>/dev/null; rc=$?
      echo "run-team[$ROLE]: ${NAMES[$i]} exited ($rc); stopping the team" >&2
      stop_all; rm -f "$HOME_DIR/ready"; exit $(( rc == 0 ? 1 : rc ))
    fi
  done
  sleep 1
done
