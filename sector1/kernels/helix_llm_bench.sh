#!/usr/bin/env bash
# helix_llm_bench.sh — does Helix help a local LLM? Ollama model load + generation, plain vs Helix.
# Phoenix DevOps OS | jwl247 | GPL v3
#
#   bash helix_llm_bench.sh            # from sector1/kernels (needs helix.ko built), user with sudo
#   HELIX_RAM_MB=6144 RUNS=3 MODEL=llama3 bash helix_llm_bench.sh
#
# Same disk IMAGE both ways (never a real disk): $IMG holds an Ollama models dir.
#   plain : image -> loop (direct I/O) -> ext4 -> Ollama
#   helix : image -> loop (direct I/O) -> dm-helix (RAM) -> ext4 -> Ollama
# Every measured run: sync + drop the page cache, fresh `ollama serve` (model not loaded), one
# short deterministic prompt. Ollama reports load_duration and eval rate. Plus one "page cache
# warm" run: the standard-caching rival (Linux already holding the model in RAM).
set -u
cd "$(dirname "$(readlink -f "$0")")"
IMG=${IMG:-/var/lib/helix-test/models.img}; M=${MNT:-/srv/llm-models}
RAM=${HELIX_RAM_MB:-6144}; RUNS=${RUNS:-3}; MODEL=${MODEL:-llama3}; PORT=11500
export OLLAMA_MODELS=$M OLLAMA_HOST=127.0.0.1:$PORT
[[ -f $IMG && -f helix.ko ]] || { echo "need $IMG and a built helix.ko"; exit 1; }
command -v ollama >/dev/null || { echo "ollama not installed"; exit 1; }

L=""; OP=""
cleanup() {
  [[ -n $OP ]] && kill $OP 2>/dev/null; wait $OP 2>/dev/null
  mountpoint -q $M && sudo umount $M
  sudo dmsetup remove helixm 2>/dev/null; lsmod | grep -q '^helix ' && sudo rmmod helix
  [[ -n $L ]] && sudo losetup -d $L 2>/dev/null; L=""
}
trap cleanup EXIT
mountpoint -q $M && sudo umount $M            # a plain loop mount from setup

dropc() { sync; echo 3 | sudo tee /proc/sys/vm/drop_caches >/dev/null; }
serve() { ollama serve >/tmp/helix-llm-ollama.log 2>&1 & OP=$!
          until curl -sf localhost:$PORT/api/version >/dev/null; do sleep 0.3; done; }
unserve() { kill $OP; wait $OP 2>/dev/null; OP=""; }
measure() {
  local t0 t1 r
  t0=$(date +%s.%N)
  r=$(curl -s localhost:$PORT/api/generate -d "{\"model\":\"$MODEL\",\"prompt\":\"Say hello in five words.\",\"stream\":false,\"options\":{\"num_predict\":16,\"temperature\":0,\"seed\":1}}")
  t1=$(date +%s.%N)
  python3 - "$1" "$t0" "$t1" "$r" <<'PY'
import json, sys
label, t0, t1, raw = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), sys.argv[4]
try:
    r = json.loads(raw)
    tps = r["eval_count"] / (r["eval_duration"] / 1e9)
    print(f"  {label:30} load {r['load_duration']/1e9:7.2f} s   gen {tps:5.2f} tok/s   wall {t1-t0:6.2f} s")
except Exception as e:
    print(f"  {label:30} FAILED: {raw[:160]}")
PY
}
attach() { L=$(sudo losetup --direct-io=on --show -f "$IMG"); }

echo "== host: $(hostname)  kernel $(uname -r)  RAM $(awk '/MemTotal/{printf "%.1f GB",$2/1048576}' /proc/meminfo)  model $MODEL  helix RAM ${RAM} MiB"

echo "== PLAIN (no Helix)"
attach; sudo mount "$L" $M
for i in $(seq 1 $RUNS); do dropc; serve; measure "plain, cold cache #$i"; unserve; done
serve; measure "plain, page cache WARM"; unserve
sudo umount $M; sudo losetup -d "$L"; L=""

echo "== HELIX (dm-helix ${RAM} MiB; run #1 fills her)"
attach; sudo modprobe dm_mod; sudo insmod ./helix.ko
sudo dmsetup create helixm --table "0 $(sudo blockdev --getsz "$L") helix $L $RAM"
sudo mount /dev/mapper/helixm $M
for i in $(seq 1 $RUNS); do dropc; serve; measure "helix, page cache dropped #$i"; unserve; done
st=$(sudo dmsetup status helixm)
echo "  helix: $(grep -oE '(hits|misses|inserts|evictions) [0-9]+' <<<"$st" | tr '\n' ' ')"
echo "  ingress/egress: $(grep -oE '(warm_write|b_writes|invalidations) [0-9]+' <<<"$st" | tr '\n' ' ')"
echo "== kernel: $(sudo dmesg | grep -ciE 'oops|BUG:|call trace') oops/BUG lines"
