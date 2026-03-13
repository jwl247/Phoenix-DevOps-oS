#!/usr/bin/env bash
# ============================================================
#  Phoenix-DevOps-oS — Benchmark Suite
#
#  4 conditions × 3 runs × 4 sources = 48 data points
#
#  Condition 1 — Baseline    (idle, full resources)
#  Condition 2 — Normal      (realistic daily load)
#  Condition 3 — Stress      (saturated, peak load)
#  Condition 4 — Red Line    (Sacrifice game condition)
#
#  Sources:
#    1. sysbench         — hardware floor
#    2. Phoronix         — standardized cross-platform score
#    3. Phoenix bench    — slot latency + packets/sec
#    4. py-spy           — flame graph, where time goes
#
#  Usage:
#    ./run_benchmark.sh [condition]   — run one condition
#    ./run_benchmark.sh all           — run all 4 (takes a while)
#    ./run_benchmark.sh redline       — red line only
#
#  Results: benchmark/results/<timestamp>/
# ============================================================

set -euo pipefail

BENCH_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$BENCH_DIR")"
RESULTS_DIR="$BENCH_DIR/results/$(date +%Y%m%d_%H%M%S)"
RUNS=3

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info() { echo -e "${CYAN}[bench]${RESET} $*"; }
ok()   { echo -e "${GREEN}[bench]${RESET} $*"; }
warn() { echo -e "${YELLOW}[bench]${RESET} $*"; }
die()  { echo -e "${RED}[bench]${RESET} $*" >&2; exit 1; }

mkdir -p "$RESULTS_DIR"
LOG="$RESULTS_DIR/benchmark.log"
SUMMARY="$RESULTS_DIR/summary.md"

log() { echo "$*" | tee -a "$LOG"; }

# ── Dep check ─────────────────────────────────────────────────
check_deps() {
    local missing=()
    command -v sysbench         &>/dev/null || missing+=("sysbench")
    command -v phoronix-test-suite &>/dev/null || missing+=("phoronix-test-suite")
    command -v py-spy            &>/dev/null || missing+=("py-spy (pip install py-spy)")
    command -v python3           &>/dev/null || missing+=("python3")

    if [[ ${#missing[@]} -gt 0 ]]; then
        warn "Missing deps: ${missing[*]}"
        warn "Install: sudo apt install sysbench phoronix-test-suite && pip3 install py-spy"
    fi
}

# ── Apply load for a condition ─────────────────────────────────
start_load() {
    local condition="$1"
    case "$condition" in
        baseline)
            info "Condition 1 — Baseline: no extra load"
            ;;
        normal)
            info "Condition 2 — Normal load: light background stress"
            sysbench cpu --cpu-max-prime=5000 --threads=2 run \
                > /dev/null 2>&1 &
            echo $! > /tmp/phoenix_bench_load.pid
            ;;
        stress)
            info "Condition 3 — Stress: saturating CPU + memory"
            sysbench cpu --cpu-max-prime=20000 --threads=$(nproc) run \
                > /dev/null 2>&1 &
            echo $! > /tmp/phoenix_bench_load.pid
            sysbench memory --memory-block-size=1M --memory-total-size=10G \
                --threads=$(nproc) run > /dev/null 2>&1 &
            echo "$!" >> /tmp/phoenix_bench_load.pid
            ;;
        redline)
            info "Condition 4 — RED LINE: Sacrifice game condition"
            info "  Simulating: 200-unit company, all 16 rings, spy+economy+combat"
            # Max threads CPU
            sysbench cpu --cpu-max-prime=50000 --threads=$(nproc) run \
                > /dev/null 2>&1 &
            echo $! > /tmp/phoenix_bench_load.pid
            # Memory pressure (game assets)
            sysbench memory --memory-block-size=4M --memory-total-size=50G \
                --threads=$(nproc) run > /dev/null 2>&1 &
            echo "$!" >> /tmp/phoenix_bench_load.pid
            # Thread contention (16 rings)
            sysbench threads --threads=16 --thread-locks=8 run \
                > /dev/null 2>&1 &
            echo "$!" >> /tmp/phoenix_bench_load.pid
            # Mutex contention (propcoms gate under load)
            sysbench mutex --mutex-num=1024 --mutex-locks=50000 \
                --mutex-loops=5000 run > /dev/null 2>&1 &
            echo "$!" >> /tmp/phoenix_bench_load.pid
            ;;
    esac
    sleep 2  # let load settle
}

stop_load() {
    if [[ -f /tmp/phoenix_bench_load.pid ]]; then
        while read -r pid; do
            kill "$pid" 2>/dev/null || true
        done < /tmp/phoenix_bench_load.pid
        rm -f /tmp/phoenix_bench_load.pid
    fi
}

# ── Source 1: sysbench hardware floor ─────────────────────────
run_sysbench() {
    local condition="$1" run="$2" out="$RESULTS_DIR/${condition}_run${run}_sysbench.txt"
    info "  sysbench CPU..."
    sysbench cpu --cpu-max-prime=10000 --threads=$(nproc) run > "$out" 2>&1
    local eps
    eps=$(grep "events per second" "$out" | awk '{print $NF}')
    log "  sysbench  [$condition] run$run : $eps events/sec"
    echo "$eps"
}

# ── Source 2: Phoronix ─────────────────────────────────────────
run_phoronix() {
    local condition="$1" run="$2" out="$RESULTS_DIR/${condition}_run${run}_phoronix.txt"
    if command -v phoronix-test-suite &>/dev/null; then
        info "  Phoronix pts/compress-gzip..."
        DONT_DO_SLEEP=1 phoronix-test-suite batch-benchmark pts/compress-gzip \
            > "$out" 2>&1 || true
        log "  phoronix  [$condition] run$run : see $out"
    else
        warn "  Phoronix not found — skipping"
        echo "N/A" > "$out"
    fi
}

# ── Source 3: Phoenix kernel bench ────────────────────────────
run_phoenix_bench() {
    local condition="$1" run="$2" out="$RESULTS_DIR/${condition}_run${run}_phoenix.txt"
    info "  Phoenix kernel slots..."

    python3 - > "$out" 2>&1 << 'PYEOF'
import sys, time
sys.path.insert(0, 'sector4')

from freewheeling_stage import FreewheelStage
from conductor import CptConductor, KERNEL_SLOTS

stage = CptConductor()
fwh   = FreewheelStage()

families = [
    ("physics",  b"bench:physics:slot0",  0),
    ("network",  b"bench:network:slot1",  1),
    ("user",     b"bench:user:slot2",     2),
    ("ai",       b"bench:ai:slot3",       3),
]

ITERATIONS = 1000

print(f"Phoenix Kernel Benchmark — {ITERATIONS} packets per slot")
print(f"{'FAMILY':<10} {'SLOT':<6} {'LANG':<12} {'TOTAL_MS':>10} {'AVG_MS':>10} {'PKT/SEC':>10}")
print("-" * 62)

results = {}
for family, data, slot in families:
    t0 = time.perf_counter()
    for i in range(ITERATIONS):
        pcs = fwh.call1(data + str(i).encode(), family)
        fwh.call2(pcs.hash, b"chunk")
        pcs, _ = fwh.call3(pcs.hash, b"final")
        packet = stage.ingress(pcs, {"i": i})
    elapsed = time.perf_counter() - t0
    total_ms = elapsed * 1000
    avg_ms   = total_ms / ITERATIONS
    pps      = ITERATIONS / elapsed
    lang     = KERNEL_SLOTS[slot]["layer"].value
    results[family] = {"avg_ms": avg_ms, "pps": pps, "slot": slot}
    print(f"{family:<10} {slot:<6} {lang:<12} {total_ms:>10.1f} {avg_ms:>10.3f} {pps:>10.0f}")

print(f"\nStatus: {stage.status()}")
print(f"\nSLOW_SLOT: {max(results, key=lambda f: results[f]['avg_ms'])}")
print(f"FAST_SLOT: {min(results, key=lambda f: results[f]['avg_ms'])}")
PYEOF

    local avg_slot0 avg_slot3
    avg_slot0=$(grep "^physics" "$out" | awk '{print $5}')
    avg_slot3=$(grep "^ai"      "$out" | awk '{print $5}')
    log "  phoenix   [$condition] run$run : slot0=${avg_slot0}ms slot3=${avg_slot3}ms"
}

# ── Source 4: py-spy flame graph ──────────────────────────────
run_pyspy() {
    local condition="$1" run="$2"
    local svg="$RESULTS_DIR/${condition}_run${run}_flamegraph.svg"
    info "  py-spy flame graph..."

    if ! command -v py-spy &>/dev/null; then
        warn "  py-spy not found — skipping flame graph"
        return
    fi

    python3 - &
    local bench_pid=$!

    sleep 1
    sudo py-spy record \
        --pid "$bench_pid" \
        --output "$svg" \
        --duration 10 \
        --format speedscope \
        2>/dev/null || true

    wait "$bench_pid" 2>/dev/null || true
    [[ -f "$svg" ]] && ok "  Flame graph: $svg" || warn "  py-spy: no output (may need sudo)"
}

# ── Run one condition ──────────────────────────────────────────
run_condition() {
    local condition="$1"
    local label=""
    case "$condition" in
        baseline) label="Condition 1 — Baseline" ;;
        normal)   label="Condition 2 — Normal Load" ;;
        stress)   label="Condition 3 — Stress" ;;
        redline)  label="Condition 4 — RED LINE" ;;
    esac

    echo
    echo -e "${BOLD}══════════════════════════════════════════${RESET}"
    echo -e "  ${RED}$label${RESET}"
    echo -e "${BOLD}══════════════════════════════════════════${RESET}"
    log ""
    log "=== $label ==="

    start_load "$condition"

    for run in 1 2 3; do
        echo
        info "Run $run of 3..."
        log ""
        log "--- Run $run ---"
        run_sysbench "$condition" "$run"
        run_phoronix "$condition" "$run"
        cd "$REPO_DIR" && run_phoenix_bench "$condition" "$run"
        run_pyspy "$condition" "$run"
    done

    stop_load
    ok "$label complete — 3 runs done"
}

# ── Write summary ──────────────────────────────────────────────
write_summary() {
    cat > "$SUMMARY" << EOF
# Phoenix Benchmark Results
**Date:** $(date)
**Host:** $(hostname)
**CPU:** $(grep "model name" /proc/cpuinfo | head -1 | cut -d: -f2 | xargs)
**RAM:** $(free -h | awk '/^Mem:/{print $2}')
**Kernel:** $(uname -r)

## Conditions Run
- Condition 1 — Baseline (idle)
- Condition 2 — Normal load
- Condition 3 — Stress (saturated)
- Condition 4 — Red Line (Sacrifice game condition)

## Sources
1. sysbench — hardware floor (events/sec)
2. Phoronix — standardized score
3. Phoenix bench — slot latency (ms) + packets/sec
4. py-spy — flame graph (see SVG files)

## Results
See individual files in: $RESULTS_DIR

## Log
\`\`\`
$(cat "$LOG")
\`\`\`
EOF
    ok "Summary: $SUMMARY"
}

# ── Main ──────────────────────────────────────────────────────
check_deps

CONDITION="${1:-all}"

case "$CONDITION" in
    baseline) run_condition baseline ;;
    normal)   run_condition normal ;;
    stress)   run_condition stress ;;
    redline)  run_condition redline ;;
    all)
        run_condition baseline
        run_condition normal
        run_condition stress
        run_condition redline
        ;;
    *)
        echo "Usage: $0 [baseline|normal|stress|redline|all]"
        exit 1
        ;;
esac

write_summary

echo
echo -e "${BOLD}══════════════════════════════════════════${RESET}"
ok "Benchmark complete"
echo -e "  Results : $RESULTS_DIR"
echo -e "  Summary : $SUMMARY"
echo -e "${BOLD}══════════════════════════════════════════${RESET}"
echo
