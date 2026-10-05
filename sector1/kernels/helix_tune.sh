#!/usr/bin/env bash
# helix_tune.sh — where does Helix lose time under many clients? Measured, not guessed.
# Phoenix DevOps OS | jwl247 | GPL v3
#
#   ./helix_tune.sh                 # from the dir holding helix.ko; disk-image files only, never a real disk
#   CLIENTS="6 12 48" SECS=60 RAM_MB=256 ./helix_tune.sh
#
# Runs dbench at each client count on the SAME box, three ways:
#   raw     — the plain disk image (loop, direct I/O)
#   helix   — dm-helix in front of it, governor normal
#   norelief— dm-helix with the governor's relief (compression / Strand B moves) switched off
#   linear  — a do-nothing device-mapper layer (dm-linear): the fair control for "is it Helix,
#             or just being stacked under device-mapper?"   (MODES="raw linear helix norelief")
# and, at the highest client count, a CPU profile of the Helix run (perf), so the hot code shows.
# Absolute numbers on old hardware mean little; the RATIOS on the same box are the evidence.
set -u
CLIENTS=${CLIENTS:-"6 12 48"}
SECS=${SECS:-60}
RAM_MB=${RAM_MB:-256}
DIR=${HELIX_TUNE_DIR:-$HOME/helixtune}
OUT=${HELIX_TUNE_OUT:-$DIR/results-$(date +%Y%m%d-%H%M%S)}
mkdir -p "$DIR" "$OUT"
IMG=$DIR/origin.img
[ -f "$IMG" ] || fallocate -l 4G "$IMG"

cleanup() { sudo umount /mnt/helixtune 2>/dev/null; sudo dmsetup remove helix0 2>/dev/null; sudo rmmod helix 2>/dev/null; [ -n "${LOOP:-}" ] && sudo losetup -d "$LOOP" 2>/dev/null; }
trap cleanup EXIT

LOOP=$(sudo losetup --direct-io=on --show -f "$IMG")
SZ=$(sudo blockdev --getsz "$LOOP")
sudo modprobe dm_mod
sudo mkdir -p /mnt/helixtune

run_dbench() {   # $1=device $2=label $3=clients
  sudo mkfs.ext4 -q -F "$1" >/dev/null
  sudo mount "$1" /mnt/helixtune
  sync; echo 3 | sudo tee /proc/sys/vm/drop_caches >/dev/null
  local mbs
  mbs=$(sudo dbench -D /mnt/helixtune -t "$SECS" "$3" 2>/dev/null | awk '/^Throughput/{print $2}')
  sudo umount /mnt/helixtune
  echo "$2 clients=$3 MB/s=${mbs:-0}" | tee -a "$OUT/summary.txt"
}

helix_up() {   # $1 = relief 1/0
  sudo insmod ./helix.ko relief_enabled="$1" || exit 99
  sudo dmsetup create helix0 --table "0 $SZ helix $LOOP $RAM_MB"
}
helix_down() { sudo dmsetup remove helix0; sudo rmmod helix; }
MODES=${MODES:-"raw helix norelief"}
has() { [[ " $MODES " == *" $1 "* ]]; }

echo "host: $(hostname) cpu: $(nproc)x $(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2 | xargs) ram: $(free -g | awk '/Mem:/{print $2}')G" | tee "$OUT/summary.txt"
TOP=$(echo $CLIENTS | tr ' ' '\n' | sort -n | tail -1)
for c in $CLIENTS; do
  has raw && run_dbench "$LOOP" raw "$c"
  if has linear; then
    sudo dmsetup create linear0 --table "0 $SZ linear $LOOP 0"
    run_dbench /dev/mapper/linear0 linear "$c"
    sudo dmsetup remove linear0
  fi
  has helix || continue
  helix_up 1
  if [ "$c" = "$TOP" ] && command -v perf >/dev/null; then
    ( sleep $((SECS/3)); sudo perf record -a -g -o "$OUT/perf-helix-$c.data" -- sleep 15 >/dev/null 2>&1 ) &
  fi
  run_dbench /dev/mapper/helix0 helix "$c"
  wait
  sudo dmsetup status helix0 > "$OUT/status-helix-$c.txt" 2>&1 || true
  helix_down
  helix_up 0
  run_dbench /dev/mapper/helix0 norelief "$c"
  helix_down
done
if [ -f "$OUT/perf-helix-$TOP.data" ]; then
  sudo perf report -i "$OUT/perf-helix-$TOP.data" --no-children --sort symbol --stdio 2>/dev/null \
    | grep -vE '^#|^$' | head -40 > "$OUT/perf-top-$TOP.txt"
fi
echo "results: $OUT"
