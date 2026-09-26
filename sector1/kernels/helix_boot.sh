#!/usr/bin/env bash
# helix_boot.sh — bring Helix up at boot (helix.service) and down at shutdown.
#
#   helix_boot.sh start | stop | status
#
# Loads helix.ko + both Frank3 slots, builds the double helix over her origin
# disk, and mounts it. Settings come from /etc/default/helix:
#
#   HELIX_ORIGIN   origin block device        (default /dev/disk/by-partlabel/helix-origin)
#   HELIX_RAM      Strand A RAM in MiB, or auto = her real size, half the RAM (default auto)
#   HELIX_B_IMG    Strand B image on the fastest disk (default /var/lib/helix/strandB.img)
#   HELIX_B_MB     Strand B size in MiB       (default 65536)
#   HELIX_MOUNT    where her filesystem goes  (default /srv/helix)
#
# Never formats anything: the filesystem on /dev/mapper/helix is made once, by
# hand. dm-helix is write-through, so the origin disk is always complete;
# stopping or losing her never loses data. After a kernel upgrade the modules
# are rebuilt against the new headers before loading (linux-headers-amd64).
set -euo pipefail
K=$(cd "$(dirname "$0")" && pwd)
[ -f /etc/default/helix ] && . /etc/default/helix
ORIGIN=${HELIX_ORIGIN:-/dev/disk/by-partlabel/helix-origin}
RAM=${HELIX_RAM:-auto}
BIMG=${HELIX_B_IMG:-/var/lib/helix/strandB.img}
BMB=${HELIX_B_MB:-65536}
MNT=${HELIX_MOUNT:-/srv/helix}
NAME=helix

log() { echo "helix_boot: $*"; }

start() {
  if [ "$(modinfo -F vermagic "$K/helix.ko" 2>/dev/null | cut -d' ' -f1)" != "$(uname -r)" ]; then
    log "modules not built for $(uname -r): rebuilding"
    make -C "$K" >/dev/null
  fi
  modprobe dm_mod
  lsmod | grep -q '^helix ' || insmod "$K/helix.ko"
  lsmod | grep -q '^frank3_slot_a ' || insmod "$K/frank3_slot_a.ko"
  lsmod | grep -q '^frank3_slot_b ' || insmod "$K/frank3_slot_b.ko"

  if ! dmsetup status "$NAME" >/dev/null 2>&1; then
    [ -b "$ORIGIN" ] || { log "origin $ORIGIN not found"; exit 1; }
    mkdir -p "$(dirname "$BIMG")"
    [ -f "$BIMG" ] || fallocate -l "${BMB}M" "$BIMG"
    chmod 600 "$BIMG"
    LOOPB=$(losetup -j "$BIMG" | cut -d: -f1)
    [ -n "$LOOPB" ] || LOOPB=$(losetup --direct-io=on --show -f "$BIMG")
    dmsetup create "$NAME" --table "0 $(blockdev --getsz "$ORIGIN") helix $ORIGIN $RAM $LOOPB $BMB"
    log "up: origin $ORIGIN, Strand A $(dmsetup table $NAME | cut -d' ' -f5) MiB RAM, Strand B $BMB MiB on $LOOPB"
  fi
  mkdir -p "$MNT"
  if ! mountpoint -q "$MNT"; then
    if blkid -p /dev/mapper/$NAME >/dev/null 2>&1; then
      mount /dev/mapper/$NAME "$MNT" && log "mounted on $MNT"
    else
      log "no filesystem on /dev/mapper/$NAME yet (make one by hand once); not mounting"
    fi
  fi
}

stop() {
  mountpoint -q "$MNT" && umount "$MNT"
  if dmsetup status "$NAME" >/dev/null 2>&1; then
    dmsetup remove "$NAME"
  fi
  LOOPB=$(losetup -j "$BIMG" 2>/dev/null | cut -d: -f1)
  [ -n "$LOOPB" ] && losetup -d "$LOOPB"
  for m in frank3_slot_b frank3_slot_a helix; do
    lsmod | grep -q "^$m " && rmmod "$m"
  done
  log "down"
}

case "${1:-}" in
  start)  start ;;
  stop)   stop ;;
  status) cat /proc/helix 2>/dev/null; dmsetup status "$NAME" 2>/dev/null || echo "no $NAME target" ;;
  *) echo "usage: $0 start|stop|status"; exit 2 ;;
esac
