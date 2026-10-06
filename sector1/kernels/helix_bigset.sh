#!/usr/bin/env bash
# helix_bigset.sh — the owed test (road-test plan §6, BENCHMARKS §5b): a working
# set BIGGER than RAM, Helix vs standard Linux caching, same disk, same file.
#
#   ./helix_bigset.sh helix    [/srv/helix-ingress]   ext4 on dm-helix, page cache on
#   ./helix_bigset.sh standard <dir>                   ext4 on the plain origin, page cache only
#
# Buffered I/O on purpose (direct=0): Linux's page cache IS the standard we're
# measuring against. Working set = 1.5x RAM so neither the page cache nor
# Helix's Strand A can hold all of it. Caches dropped before every pass.
# Precision: fio reports latency in ns, summarised here in µs (BENCHMARKS rule).
#
# Run detached:  setsid nohup bash helix_bigset.sh helix >/dev/null 2>&1 &
# Output: ~/bigset-<label>-<date>/  (run.log, one fio JSON per job, summary.txt)
set -u
LABEL=${1:?usage: helix_bigset.sh helix|standard [dir]}
DIR=${2:-/srv/helix-ingress}
RAM_GB=$(awk '/MemTotal/{printf "%d", $2/1048576}' /proc/meminfo)
SIZE_GB=${BIGSET_GB:-$(( RAM_GB * 3 / 2 ))}
RUNTIME=${BIGSET_RUNTIME:-300}
PASSES=${BIGSET_PASSES:-3}
OUT=$HOME/bigset-$LABEL-$(date +%Y%m%d-%H%M)
mkdir -p "$OUT"
exec > >(tee "$OUT/run.log") 2>&1

mountpoint -q "$DIR" || { echo "$DIR is not a mount point - stopping"; exit 2; }
DEV=$(findmnt -no SOURCE "$DIR")
DM=$(basename "$DEV")
F=$DIR/bigset/data.bin
mkdir -p "$DIR/bigset"
AVAIL_GB=$(df -BG --output=avail "$DIR" | tail -1 | tr -dc 0-9)
[ "$AVAIL_GB" -gt $(( SIZE_GB + 20 )) ] || { echo "only ${AVAIL_GB} GB free on $DIR - stopping"; exit 2; }

drop() { sync; sudo sh -c 'echo 3 > /proc/sys/vm/drop_caches'; }
state() {
  if sudo dmsetup status "$DM" 2>/dev/null | grep -q ' helix '; then
    echo "   her state: $(sudo dmsetup status "$DM" | grep -oE 'hits [0-9]+ zhits [0-9]+ misses [0-9]+|b_hits [0-9]+|used [0-9]+' | tr '\n' ' ')"
  fi
}
job() {   # $1 = name, rest = fio options
  local name=$1; shift
  echo "-- $(date +%T) $name"
  fio --name="$name" --filename="$F" --size="${SIZE_GB}G" --direct=0 \
      --output-format=json --output="$OUT/$name.json" "$@" \
    || echo "   fio failed: $name"
  python3 - "$OUT/$name.json" <<'PY'
import json, sys
j = json.load(open(sys.argv[1]))["jobs"][0]
for k in ("read", "write"):
    s = j[k]
    if s["io_bytes"]:
        p = s["clat_ns"].get("percentile", {})
        print(f"   {k}: {s['bw_bytes']/1048576:9.1f} MiB/s  {s['iops']:10.1f} IOPS  "
              f"lat mean {s['clat_ns']['mean']/1000:9.1f} µs  p99 {p.get('99.000000', 0)/1000:9.1f} µs")
PY
  state
}

echo "== $LABEL  $(date -Is)  $DIR on $DEV  RAM ${RAM_GB} GB  working set ${SIZE_GB} GB  ${PASSES} passes"
state

CUR=$(stat -c %s "$F" 2>/dev/null || echo 0)
if [ "$CUR" -ne $(( SIZE_GB * 1073741824 )) ]; then
  drop
  job layout --rw=write --bs=1M --end_fsync=1
fi

RAND=(--bs=4k --numjobs=4 --group_reporting --time_based --runtime="$RUNTIME" --ioengine=psync)
for P in $(seq 1 "$PASSES"); do
  echo "== pass $P"
  drop
  job "p$P-seqread-first"  --rw=read --bs=1M
  job "p$P-seqread-repeat" --rw=read --bs=1M
  drop
  # zipf: a hot set inside the big set — the shape of game assets and models.
  job "p$P-randread-zipf"    --rw=randread --random_distribution=zipf:1.1 "${RAND[@]}"
  drop
  job "p$P-randread-uniform" --rw=randread --random_distribution=random   "${RAND[@]}"
done

grep -E '^(-- |   (read|write)|== )' "$OUT/run.log" > "$OUT/summary.txt"
echo "== kernel log"
sudo dmesg | grep -iE "oops|bug:|call trace|soft lockup|blocked for" || echo "  clean"
echo "== done $(date -Is)  out: $OUT"
