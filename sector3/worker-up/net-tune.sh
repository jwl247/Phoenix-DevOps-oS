#!/usr/bin/env bash
# net-tune.sh — network settings a Phoenix worker needs. Run as root. Re-runnable.
#
# BBR congestion control + fq. Found on pbm-compaq in the road test
# (2026-09-29): its uplink loses ~4.6% of sent segments, and the default CUBIC
# reads every loss as congestion — upload collapsed to ~1 Mbit/s. BBR, on the
# same link, measured 20-26 Mbit/s; a 16 MiB push to Phoenix went 289 s -> 20.7 s.
# Workers pulling from and pushing to Phoenix over home/Starlink/mobile links
# (the game-client shape) all want this. The kernel loads tcp_bbr by itself
# when the setting asks for it — no module configuration is touched.
#   net-tune.sh          apply (and persist in /etc/sysctl.d/90-phoenix-bbr.conf)
#   net-tune.sh revert   remove the file and go back to cubic
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "run as root"; exit 1; }
F=/etc/sysctl.d/90-phoenix-bbr.conf
if [ "${1:-}" = revert ]; then
  rm -f "$F"; echo cubic > /proc/sys/net/ipv4/tcp_congestion_control
  echo "  net      reverted to $(cat /proc/sys/net/ipv4/tcp_congestion_control)"; exit 0
fi
cat > "$F" <<CONF
# Phoenix worker: BBR congestion control (sector3/worker-up/net-tune.sh).
# Remove this file (or run net-tune.sh revert) to go back to the default.
net.core.default_qdisc = fq
net.ipv4.tcp_congestion_control = bbr
CONF
/usr/sbin/sysctl -q -p "$F"
[ "$(cat /proc/sys/net/ipv4/tcp_congestion_control)" = bbr ] || { echo "  net      FAIL: kernel did not take bbr"; exit 1; }
echo "  net      $(cat /proc/sys/net/ipv4/tcp_congestion_control) / $(cat /proc/sys/net/core/default_qdisc) (persisted in $F)"
