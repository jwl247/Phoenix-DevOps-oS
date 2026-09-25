#!/usr/bin/env bash
# helix_freedrive.sh — "let her drive": one hands-off run of real work on the
# double helix, compared with the same work on the raw disk.
#
# No steering: every module parameter at its default, no forced heat, no
# starved RAM. She gets reasonable room (Strand A ${HELIX_RAM_MB:-512} MiB RAM,
# Strand B 512 MiB on the SSD) and decides everything herself: what stays hot,
# what compresses, what moves to Strand B, when she heats and cools. Her
# telemetry is sampled every 2 s to show what she chose.
#
# Sizing: she takes her real size by default, half the machine's RAM ("auto"),
# and an 8 GiB Strand B. Her heat calibrates itself to her own peak.
# Fairness: Linux's own page cache is dropped between passes, otherwise we'd
# be measuring Linux's RAM cache sitting on top of her rather than her.
# Runs on image files only, never a real disk. Linux, root via sudo.
set -u
cd "$(dirname "$0")"
LOG=${HELIX_FD_LOG:-./freedrive-$(date +%Y%m%d-%H%M%S).log}
exec > >(tee "$LOG") 2>&1
IMG=${HELIX_TEST_IMG:-$HOME/helixdm/origin.img}
BIMG=${HELIX_B_IMG:-/mnt/helix/helix-strandB-8g.img}
RAM=${HELIX_RAM_MB:-auto}          # auto = her real size: half the machine's RAM
BMB=${HELIX_B_MB:-8192}
SRC=${HELIX_FD_SRC:-/usr/share/doc /usr/share/locale /usr/share/icons /usr/share/man /usr/include /usr/lib/python3 /usr/share/perl /usr/share/perl5}
MNT=/mnt/hxfd

drop(){ sync; sudo sh -c 'echo 3 > /proc/sys/vm/drop_caches'; }
secs(){ local t0=$1; echo "$(( $(date +%s%N) - t0 ))" | awk '{printf "%.1f", $1/1e9}'; }

workload() {   # $1 = label ; runs on whatever is mounted at $MNT
  local t
  drop; t=$(date +%s%N)
  sudo tar -C / -cf - $SRC 2>/dev/null | sudo tar -C $MNT -xf -; sync
  echo "  $1 copy-in:          $(secs $t) s"
  for pass in 1 2 3; do
    drop; t=$(date +%s%N)
    sudo grep -rIl "Copyright" $MNT >/dev/null 2>&1
    echo "  $1 search pass $pass:    $(secs $t) s"
    drop; t=$(date +%s%N)
    sudo find $MNT -type f -exec md5sum {} + >/dev/null 2>&1
    echo "  $1 checksum pass $pass:  $(secs $t) s"
  done
}

echo "== free drive $(date -Is) | work: copy-in, then 3x (search + checksum all files) of: $SRC"
echo "   size: $(sudo du -shc $SRC 2>/dev/null | tail -1 | cut -f1)"

LOOP=$(sudo losetup --direct-io=on --show -f "$IMG")
SZ=$(sudo blockdev --getsz "$LOOP")

echo "== baseline: raw disk, no Helix"
sudo mkfs.ext4 -q -F "$LOOP" && sudo mkdir -p $MNT && sudo mount "$LOOP" $MNT
workload "raw   "
sudo umount $MNT

echo "== Helix double strand, driving herself (A ${RAM} RAM, B ${BMB} MiB SSD, defaults, self-calibrating heat)"
[ -f "$BIMG" ] || fallocate -l ${BMB}M "$BIMG"
LOOPB=$(sudo losetup --direct-io=on --show -f "$BIMG")
sudo modprobe dm_mod
sudo insmod ./helix.ko || { echo "insmod failed"; exit 1; }
sudo dmsetup create hxfd --table "0 $SZ helix $LOOP $RAM $LOOPB $BMB"
echo "   she took: $(sudo dmsetup table hxfd | cut -d' ' -f5) MiB of RAM for Strand A"
D=/dev/mapper/hxfd
# her telemetry, every 2 s, untouched by anything else
( while sudo dmsetup status hxfd >/dev/null 2>&1; do
    echo "   [$(date +%T)] $(sudo dmsetup status hxfd | grep -oE "heat [0-9.]+ state [a-z]+ compression [0-9.]+|strandA raw [0-9]+ zlib5 [0-9]+|used [0-9]+ bonly [0-9]+ rungs [0-9]+ b_hits [0-9]+|hits [0-9]+ zhits [0-9]+ misses [0-9]+" | tr '\n' ' ')"
    sleep 2
  done ) > ./freedrive-telemetry.txt 2>&1 &
TEL=$!
sudo mkfs.ext4 -q -F $D && sudo mount $D $MNT
workload "helix "
sudo umount $MNT
echo "== her final state"
sudo dmsetup status hxfd | tr ' ' '\n' | paste -sd' ' | fold -w 160
sudo dmsetup remove hxfd
wait $TEL 2>/dev/null
sudo rmmod helix
sudo losetup -d "$LOOP" "$LOOPB"
echo "== what she did (telemetry, every 2 s): ./freedrive-telemetry.txt ($(wc -l < ./freedrive-telemetry.txt) samples)"
echo "   first:  $(head -1 ./freedrive-telemetry.txt)"
echo "   hottest: $(grep -oE "heat [0-9.]+" ./freedrive-telemetry.txt | sort -k2 -n | tail -1)"
echo "   last:   $(tail -1 ./freedrive-telemetry.txt)"
echo "== kernel log"
sudo dmesg | grep -iE "oops|bug:|call trace|soft lockup|blocked for" || echo "  clean"
echo "== done"
