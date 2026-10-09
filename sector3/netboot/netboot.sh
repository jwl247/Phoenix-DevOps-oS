#!/usr/bin/env bash
# netboot.sh — install a box over the network from this one (PXE), only while you ask it to.
# Phoenix DevOps OS | jwl247 | GPL v3
#
# Jerry 2026-10-09: the HP's Debian 13 network driver never saw the switch (r8169, Link down) and it
# had internet on Debian 12, so it goes back to 12 - over the network, from the Compaq. PXE uses
# the network card's own boot code, so a broken OS driver can't stop it.
#
#   netboot.sh fetch                  Debian 12 netboot files, verified against Debian's signing keys
#   netboot.sh start [--for 2h]       open the boot ports (home LAN only) + start the boot server;
#                                     it stops ITSELF after the time limit (default 2h)
#   netboot.sh stop                   stop the server, remove the firewall opening
#   netboot.sh status                 what is running, who asked
#
# Opt-in only: no service, nothing at boot. Proxy mode: it hands out NO addresses (the router keeps
# doing that); it only answers "here is the installer" to a machine that asks to boot from the network.
# DNS off. One tagged rule in the existing firewall (inet phoenix input), removed by `stop`.
# Env: NETBOOT_DIR (~/pxe-bookworm), NETBOOT_IF (eno1), NETBOOT_LAN (192.168.1.0/24), NETBOOT_SUITE (bookworm)
set -euo pipefail

DIR="${NETBOOT_DIR:-$HOME/pxe-bookworm}"
IFACE="${NETBOOT_IF:-eno1}"
LAN="${NETBOOT_LAN:-192.168.1.0/24}"
SUITE="${NETBOOT_SUITE:-bookworm}"
PIDF=/run/phoenix-netboot.pid
SERVE=/run/phoenix-netboot                 # RAM only: dnsmasq drops root and cannot read a home folder
TAG=phoenix-netboot
KEYRING=/usr/share/keyrings/debian-archive-keyring.gpg
LOG="$DIR/dnsmasq.log"

die() { echo "netboot: $*" >&2; exit 1; }

cmd_fetch() {
  mkdir -p "$DIR" && cd "$DIR"
  local B="https://deb.debian.org/debian/dists/$SUITE"
  curl -fsSO "$B/Release" && curl -fsSO "$B/Release.gpg"
  gpgv --keyring "$KEYRING" Release.gpg Release 2>&1 | grep -q "Good signature" || die "Release is NOT signed by Debian - nothing used"
  curl -fsS -o SHA256SUMS "$B/main/installer-amd64/current/images/SHA256SUMS"
  local want got
  want=$(awk -v f="main/installer-amd64/current/images/SHA256SUMS" 'length($1)==64 && $3==f {print $1; exit}' Release)
  got=$(sha256sum SHA256SUMS | cut -d' ' -f1)
  [ -n "$want" ] && [ "$want" = "$got" ] || die "SHA256SUMS does not match the signed Release - nothing used"
  curl -fsS -o netboot.tar.gz "$B/main/installer-amd64/current/images/netboot/netboot.tar.gz"
  want=$(awk '$2=="./netboot/netboot.tar.gz" {print $1}' SHA256SUMS)
  got=$(sha256sum netboot.tar.gz | cut -d' ' -f1)
  [ "$want" = "$got" ] || die "netboot.tar.gz does not match SHA256SUMS - nothing used"
  rm -rf tftp && mkdir tftp && tar -xzf netboot.tar.gz -C tftp
  echo "netboot: Debian $SUITE installer verified (Debian signature -> SHA256SUMS -> netboot.tar.gz)"
  grep -h "Installer build" tftp/version.info 2>/dev/null || true
}

running() { [ -f "$PIDF" ] && sudo kill -0 "$(cat "$PIDF")" 2>/dev/null; }

rule_handles() { sudo nft -a list chain inet phoenix input 2>/dev/null | awk -v t="\"$TAG\"" 'index($0, t) {print $NF}'; }

cmd_start() {
  local dur=2h
  if [ "${1:-}" = "--for" ]; then dur="${2:?--for needs a time like 30m or 2h}"; fi
  [ -f "$DIR/tftp/pxelinux.0" ] || die "no installer in $DIR/tftp (netboot.sh fetch)"
  running && die "already running (netboot.sh status / stop)"
  [ -n "$(rule_handles)" ] || sudo nft insert rule inet phoenix input ip saddr "$LAN" udp dport '{ 67, 69, 4011 }' accept comment "\"$TAG\""
  : > "$LOG"
  sudo rm -rf "$SERVE" && sudo mkdir -p "$SERVE" && sudo cp -r "$DIR/tftp" "$SERVE/" && sudo chmod -R a+rX "$SERVE"
  sudo setsid nohup /usr/sbin/dnsmasq --keep-in-foreground --log-facility=- --port=0 --interface="$IFACE" --bind-interfaces \
      --dhcp-range="${LAN%/*},proxy" --pxe-service=x86PC,"Debian $SUITE install",pxelinux \
      --enable-tftp --tftp-root="$SERVE/tftp" --tftp-single-port --log-dhcp --pid-file="$PIDF" \
      >> "$LOG" 2>&1 < /dev/null &
  sleep 2
  running || { cmd_stop >/dev/null 2>&1 || true; die "the boot server did not start (see $LOG)"; }
  # never left open by accident: it stops itself
  setsid nohup bash -c "sleep $dur; '$0' stop" >/dev/null 2>&1 < /dev/null &
  echo "netboot: serving Debian $SUITE to $LAN on $IFACE (proxy, DNS off) - stops itself in $dur"
}

cmd_stop() {
  if running; then sudo kill "$(cat "$PIDF")" && sleep 1; fi
  sudo pkill -f -- "--pid-file=$PIDF" 2>/dev/null && sleep 1 || true      # backstop: any copy carrying our tag
  sudo rm -f "$PIDF"; sudo rm -rf "$SERVE"
  for h in $(rule_handles); do sudo nft delete rule inet phoenix input handle "$h"; done
  [ -z "$(rule_handles)" ] || die "firewall rule still there - check: sudo nft -a list chain inet phoenix input"
  echo "netboot: stopped, firewall opening removed"
}

cmd_status() {
  if running; then echo "netboot: RUNNING (pid $(cat "$PIDF"))"; else echo "netboot: not running"; fi
  echo "firewall opening: $([ -n "$(rule_handles)" ] && echo OPEN || echo closed)"
  [ -f "$LOG" ] && grep -iE "PXE|sent |error" "$LOG" | tail -8 || true
}

case "${1:-}" in
  fetch)  cmd_fetch ;;
  start)  shift; cmd_start "$@" ;;
  stop)   cmd_stop ;;
  status) cmd_status ;;
  *) sed -n '2,20p' "$0"; exit 2 ;;
esac
