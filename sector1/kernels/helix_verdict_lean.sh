#!/usr/bin/env bash
# helix_verdict_lean.sh — finish the raw-vs-Helix Phoronix comparison on the
# Compaq without redoing what's already measured ("let her eat", Jerry).
#
# Why lean (2026-09-26): fs-mark (1000 x 1 MB files, fsync each) ran ~6 files/s
# on the 5400 rpm origin and PTS kept re-running it (9th pass after 8 h); it is
# also uninformative for Helix, which is write-through (forced-flush writes tie
# the raw disk by design). So: no fs-mark, 3 passes per test, no reformat, and
# the raw fio results already in result file `helix-compaq` stay.
#
#   raw   : dbench 1/12/48, postmark, sqlite-speedtest   (fio already done)
#   helix : fio x4, dbench 1/12/48, postmark, sqlite     (same filesystem, dm-helix over it)
#
# Run detached:  setsid nohup bash helix_verdict_lean.sh >/dev/null 2>&1 &
# Log: ~/verdict-lean-<date>.log   Result file: helix-compaq (identifiers raw, helix)
set -u
K=/opt/phoenix/sector1/kernels
exec > >(tee "$HOME/verdict-lean-$(date +%Y%m%d-%H%M).log") 2>&1
export FORCE_TIMES_TO_RUN=3
P=/dev/disk/by-partlabel/helix-origin
[ "$(lsblk -dno SERIAL /dev/sdb)" = WQ992JYZ ] || { echo "origin drive not WQ992JYZ - stopping"; exit 1; }

echo "== $(date -Is) start. /srv/bench on: $(findmnt -no SOURCE /srv/bench || echo nothing)"
if [ "$(findmnt -no SOURCE /srv/bench)" = /dev/mapper/helix ]; then
  echo "already on Helix - this script starts from the plain disk; stopping"; exit 1
fi
mountpoint -q /srv/bench || { sudo mkdir -p /srv/bench && sudo mount $P /srv/bench && sudo chown a:a /srv/bench; } || exit 1

echo "== $(date -Is) RAW: the tests not yet measured on the plain disk"
HELIX_PTS_SKIP="fio fsmark" bash $K/helix_phoronix.sh raw

echo "== $(date -Is) switching the origin disk to Helix (same filesystem, no reformat)"
sync; sudo umount /srv/bench || { echo "umount failed - stopping"; exit 1; }
sudo bash $K/install_helix_boot.sh || { echo "install failed - stopping"; exit 1; }
sudo systemctl start helix.service phoenix-paging.service
sleep 5
[ "$(findmnt -no SOURCE /srv/bench)" = /dev/mapper/helix ] || { echo "not on Helix - stopping"; exit 1; }
echo "   her table: $(sudo dmsetup table helix)"

echo "== $(date -Is) HELIX: the identical set (fio included)"
HELIX_PTS_SKIP="fsmark" bash $K/helix_phoronix.sh helix

echo "== $(date -Is) VERDICT"
phoronix-test-suite result-file-to-text helix-compaq 2>&1 | grep -v deprecated | sed -n '/Flexible IO/,$p'
sudo dmsetup status helix | tr ' ' '\n' | paste -sd' ' | fold -w 160
sudo dmesg | grep -iE "oops|bug:|call trace|soft lockup|blocked for|I/O error" || echo "kernel log clean"
echo "== done $(date -Is)"
