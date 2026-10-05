#!/usr/bin/env bash
# helix_pair_test.sh — Helix alone vs Helix + her paging manager (he clears and feeds her)
# Phoenix DevOps OS | jwl247 | GPL v3
#
#   ./helix_pair_test.sh            from the dir holding helix.ko; needs fio, python3, the repo's
#                                   sector4/paging_kernel_helix.py at $PAGER. Disk-image files only.
#
# MODEL of her real job (ingress Helix): the origin is FAR (each read delayed like a network
# fetch — dm-delay, ORIGIN_DELAY_MS), Strand B is LOCAL (SSD image). Two workloads, three ways:
#   origin   — reading the far origin directly
#   helix    — dm-helix in front (double strand), alone
#   paired   — dm-helix + the paging manager (Doppelgangers + predictive fetch)
# Workloads (fio, direct I/O so no page cache helps anyone):
#   stream   — STREAMS parallel readers, each reading its own region front to back (asset streaming)
#   reuse    — random reads, zipf-skewed, over a working set bigger than Strand A (her re-reads)
set -u
DELAY=${ORIGIN_DELAY_MS:-10}
SECS=${SECS:-40}
STREAMS=${STREAMS:-8}
RAM_MB=${RAM_MB:-256}
B_MB=${B_MB:-512}
PAGER=${PAGER:-$HOME/pager/paging_kernel_helix.py}
DIR=${HELIX_PAIR_DIR:-$HOME/helixpair}
OUT=${HELIX_PAIR_OUT:-$DIR/results-$(date +%Y%m%d-%H%M%S)}
mkdir -p "$DIR" "$OUT"
[ -f "$DIR/origin.img" ] || { fallocate -l 4G "$DIR/origin.img"; dd if=/dev/urandom of="$DIR/origin.img" bs=4M count=1024 conv=notrunc status=none; }
[ -f "$DIR/strandB.img" ] || fallocate -l 4G "$DIR/strandB.img"

cleanup() { [ -n "${PPID_PAGER:-}" ] && sudo pkill -TERM -f paging_kernel_helix.py 2>/dev/null; sudo dmsetup remove helix0 2>/dev/null; sudo dmsetup remove far0 2>/dev/null
            sudo /sbin/rmmod helix 2>/dev/null; sudo losetup -d ${LO:-} ${LB:-} 2>/dev/null; }
trap cleanup EXIT
sudo /sbin/modprobe dm_mod; sudo /sbin/modprobe dm-delay
LO=$(sudo losetup --direct-io=on --show -f "$DIR/origin.img")
LB=$(sudo losetup --direct-io=on --show -f "$DIR/strandB.img")
SZ=$(sudo blockdev --getsz "$LO")
sudo dmsetup create far0 --table "0 $SZ delay $LO 0 $DELAY"          # the far origin
FAR=/dev/mapper/far0

fio_run() {   # $1 device $2 label $3 workload
  local args
  if [ "$3" = stream ]; then
    args="--rw=read --bs=64k --numjobs=$STREAMS --size=$((4096/STREAMS))M --offset_increment=$((4096/STREAMS))M"
  else
    args="--rw=randread --bs=4k --numjobs=$STREAMS --random_distribution=zipf:1.1 --size=3G"
  fi
  sync; echo 3 | sudo tee /proc/sys/vm/drop_caches >/dev/null
  sudo fio --name="$2-$3" --filename="$1" --direct=1 --ioengine=psync --iodepth=1 --time_based --runtime="$SECS" \
       --group_reporting $args --output-format=terse --terse-version=3 2>/dev/null \
    | awk -F';' -v L="$2" -v W="$3" '{printf "%s %s MB/s=%.1f iops=%d lat_ms=%.2f\n", W, L, $7/1024, $8, $40/1000}' | tee -a "$OUT/summary.txt"
}

helix_up() {
  sudo /sbin/insmod ./helix.ko
  sudo dmsetup create helix0 --table "0 $SZ helix $FAR $RAM_MB $LB $B_MB"
}
helix_down() { sudo dmsetup status helix0 > "$OUT/status-$1.txt"; sudo dmsetup remove helix0; sudo /sbin/rmmod helix; }

echo "host $(hostname); origin delay ${DELAY} ms/IO (model of a far origin); Strand A ${RAM_MB} MiB; Strand B ${B_MB} MiB base on SSD (4 GiB device)" | tee "$OUT/summary.txt"
for W in stream reuse; do
  fio_run "$FAR" origin "$W"
  helix_up; fio_run /dev/mapper/helix0 helix "$W"; helix_down "helix-$W"
  helix_up
  sudo python3 "$PAGER" --dm helix0 --b-file "$DIR/strandB.img" --interval 0.25 --pager-interval 2 \
       --seconds $((SECS + 3)) > "$OUT/pager-$W.log" 2>&1 &
  PPID_PAGER=$!
  sleep 1
  fio_run /dev/mapper/helix0 paired "$W"
  wait "$PPID_PAGER" 2>/dev/null; PPID_PAGER=                 # he stops himself after --seconds
  helix_down "paired-$W"
done
echo "results: $OUT"
