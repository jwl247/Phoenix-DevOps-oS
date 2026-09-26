#!/usr/bin/env bash
# helix_phoronix.sh — the same Phoronix Test Suite set, raw disk vs Helix.
#
#   ./helix_phoronix.sh raw     # /srv/bench = plain ext4 on the origin disk
#   ./helix_phoronix.sh helix   # /srv/bench = ext4 on /dev/mapper/helix (dm-helix over it)
#
# Both runs land in ONE result file (TEST_RESULTS_NAME), one identifier each,
# so `phoronix-test-suite result-file-to-text helix-compaq` shows them side by
# side. Needs PTS batch mode configured (UploadResults FALSE: results stay
# local) and EnvironmentDirectory=/srv/bench/pts-env/ in user-config.xml.
# Linux caches are dropped before every test so we measure the disk path,
# not Linux's RAM. Timing precision: PTS/fio report at microsecond or finer.
set -u
LABEL=${1:?usage: helix_phoronix.sh raw|helix}
NAME=${HELIX_PTS_NAME:-helix-compaq}
LOG=${HELIX_PTS_LOG:-$HOME/helix-phoronix-$LABEL-$(date +%Y%m%d-%H%M%S).log}
exec > >(tee "$LOG") 2>&1
export TEST_RESULTS_NAME="$NAME" TEST_RESULTS_IDENTIFIER="$LABEL"
export TEST_RESULTS_DESCRIPTION="Compaq i5-2400 / 15 GB / ST1000LM035 origin, Samsung SSD Strand B. raw = plain disk, helix = dm-helix double strand (Strand A auto = half RAM, zlib 5, self-calibrating heat)."

mountpoint -q /srv/bench || { echo "/srv/bench not mounted"; exit 2; }
echo "== $LABEL on $(findmnt -no SOURCE /srv/bench)  $(date -Is)"
mkdir -p /srv/bench/pts-env

drop() { sync; sudo sh -c 'echo 3 > /proc/sys/vm/drop_caches'; }

# Debian 13 notes (found 2026-09-26): dbench needs libpopt-dev, sqlite-speedtest
# needs tcl, postmark is 1990s C that GCC 14 rejects (built with -std=gnu89 via
# CFLAGS, which its install.sh passes through). compilebench needs python2,
# which Debian 13 no longer ships: fs-mark (small-file create/sync) replaces it.
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq libpopt-dev tcl >/dev/null
TESTS=(pts/fio pts/fs-mark pts/dbench pts/postmark pts/sqlite-speedtest)
phoronix-test-suite batch-install pts/fio pts/fs-mark pts/dbench pts/sqlite-speedtest 2>&1 | grep -v deprecated | tail -5
# gnu89 for postmark ONLY: fio needs C99+ and fails under it.
CFLAGS="-std=gnu89 -O2" phoronix-test-suite batch-install pts/postmark 2>&1 | grep -v deprecated | tail -3
ONLY=${HELIX_PTS_ONLY:-all}   # all | nofio (resume a run whose fio tests already landed)

run() {   # $1 = test, $2 = PRESET_OPTIONS
  drop
  echo "-- $1 [$2]"
  PRESET_OPTIONS="$2" phoronix-test-suite batch-run "$1" 2>&1 | grep -vE "deprecated|^\s*$" | tail -12
  if [ "$LABEL" = helix ] && sudo dmsetup status helix >/dev/null 2>&1; then
    echo "   her state: $(sudo dmsetup status helix | grep -oE 'heat [0-9.]+ state [a-z]+ compression [0-9.]+|hits [0-9]+ zhits [0-9]+ misses [0-9]+|b_hits [0-9]+' | tr '\n' ' ')"
  fi
}

DT="fio.auto-disk-mount-points=Default Test Directory"
if [ "$ONLY" != nofio ]; then
  for T in "Random Read" "Random Write" "Sequential Read" "Sequential Write"; do
    BS=4KB; case "$T" in Seq*) BS=1MB;; esac
    run pts/fio "fio.type=$T;fio.engine=IO_uring;fio.direct=Yes;fio.size=$BS;fio.cpu-threads=1;$DT"
  done
fi
for F in "1000 Files, 1MB Size" "5000 Files, 1MB Size, 4 Threads" "4000 Files, 32 Sub Dirs, 1MB Size"; do
  run pts/fs-mark "fs-mark.test=$F"
done
for N in 1 12 48; do
  run pts/dbench "dbench.client-count=$N"
done
run pts/postmark ""
run pts/sqlite-speedtest ""

echo "== results so far"
phoronix-test-suite result-file-to-text "$NAME" 2>&1 | grep -v deprecated
echo "== kernel log"
sudo dmesg | grep -iE "oops|bug:|call trace|soft lockup|blocked for" || echo "  clean"
echo "== done $(date -Is)  log: $LOG"
