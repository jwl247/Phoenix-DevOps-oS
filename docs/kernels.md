# Phoenix Kernel Architecture & Benchmark Guide

## The Quad-Kernel System

Phoenix runs four kernel slots simultaneously. Each slot maps to a storage language and a workload type. This is the quadralingual system — every signal inside Phoenix is expressed in one of four languages depending on which slot handles it.

```
Slot 0  c_pure       → VECTOR      max speed, peak traffic
Slot 1  c_sideload   → NOSQL       balanced, extended calls
Slot 2  python_user  → RELATIONAL  flexible, moderate load
Slot 3  python_full  → TIMESERIES  full flexibility, dev/AI
```

---

## Kernel Slot Detail

### Slot 0 — c_pure / VECTOR
- **Workloads:** physics, system heartbeat, collision, raw signal processing
- **Data form:** float array — `[123.0, 109.0, 11.0, 12.0, ...]`
- **Why:** Zero abstraction overhead. Data is a vector. Math happens directly on it.
- **Benchmark target:** < 1ms ingress → egress per packet at 10,000 packets/sec

### Slot 1 — c_sideload / NOSQL
- **Workloads:** network, asset management, balanced I/O
- **Data form:** flat dict — `{"id": "CPT_000003", "pcs": "...", "data": "..."}`
- **Why:** Flexible key-value for unpredictable payload shapes. No schema enforcement.
- **Benchmark target:** < 2ms ingress → egress per packet at 5,000 packets/sec

### Slot 2 — python_user / RELATIONAL
- **Workloads:** user operations, economy, research tree, building dependencies
- **Data form:** structured dict with typed fields — `{"id": ..., "pcs": ..., "ts": ..., "val": ...}`
- **Why:** Relational structure for data with real schema requirements. Joinable, queryable.
- **Benchmark target:** < 5ms ingress → egress per packet at 1,000 packets/sec

### Slot 3 — python_full / TIMESERIES
- **Workloads:** AI inference, event replay, veterancy log, combat resolution
- **Data form:** list of timestamped events — `[{"ts": ..., "metric": ..., "pcs": ..., "val": ...}]`
- **Why:** Every event is a point in time. Replay, scrub, and audit are native operations.
- **Benchmark target:** < 10ms ingress → egress per packet at 500 packets/sec

---

## Family → Slot Routing

The conductor routes signals by family to their preferred slot:

| Family | Preferred Slot | Language |
|--------|---------------|----------|
| physics | 0 | VECTOR |
| system | 0 | VECTOR |
| network | 1 | NOSQL |
| assets | 1 | NOSQL |
| user | 2 | RELATIONAL |
| ai | 3 | TIMESERIES |

**Overflow rule:** If preferred slot load > 100 in-flight packets, conductor steps down to the least-loaded slot automatically.

---

## PCS — Probabilistic Commit System

Every signal gets a PCS identity at birth. The PCS string is the signal's passport through the entire system.

**PCS string format:**
```
<hash>:<zipcode>:<call1_prob>:<call2_prob>:<call3_prob>:<flags>

Example:
7b6d0b0c80fbcf6c:red:21:27:36:0
│                │   │  │  │  └─ flags
│                │   │  │  └──── call3 probability contribution
│                │   │  └─────── call2 probability contribution
│                │   └────────── call1 probability contribution
│                └────────────── zipcode (zone/flock assignment)
└─────────────────────────────── 16-char hex hash (original, never changes)
```

**3-call lifecycle:**
1. `call1` — PCS born, stage pre-positioned. Hash set. Slot reserved.
2. `call2` — Data accumulates in flock. Probability climbs.
3. `call3` — Definitive check. If probability threshold met → snap-clone fires → ring handles post-stage.

**Key property:** The original hash never changes. It is the signal's identity. All probability and zipcode fields update, but the hash is immutable.

---

## Benchmark Script

Run this to baseline all four kernel slots:

```bash
cd sector4
python3 - << 'EOF'
import time
from freewheeling_stage import FreewheelStage
from conductor import CptConductor, KERNEL_SLOTS

stage = CptConductor()
fwh   = FreewheelStage()

families = [
    ("physics",  b"bench:physics:slot0"),
    ("network",  b"bench:network:slot1"),
    ("user",     b"bench:user:slot2"),
    ("ai",       b"bench:ai:slot3"),
]

ITERATIONS = 1000

print(f"\nPhoenix Kernel Benchmark — {ITERATIONS} packets per slot\n")
print(f"{'FAMILY':<10} {'SLOT':<6} {'LANG':<12} {'TOTAL':>10} {'AVG/PKT':>10} {'PKT/SEC':>10}")
print("-" * 60)

for family, data in families:
    pcs_list = []
    t0 = time.perf_counter()

    for i in range(ITERATIONS):
        pcs = fwh.call1(data + str(i).encode(), family)
        fwh.call2(pcs.hash, b"chunk")
        pcs, _ = fwh.call3(pcs.hash, b"final")
        packet = stage.ingress(pcs, {"i": i})

    elapsed = time.perf_counter() - t0
    avg_ms  = (elapsed / ITERATIONS) * 1000
    pps     = ITERATIONS / elapsed
    slot    = {"physics":0,"system":0,"network":1,"assets":1,"user":2,"ai":3}.get(family,2)
    lang    = KERNEL_SLOTS[slot]["layer"].value

    print(f"{family:<10} {slot:<6} {lang:<12} {elapsed:>9.3f}s {avg_ms:>9.3f}ms {pps:>10.0f}")

print(f"\nStatus: {stage.status()}")
EOF
```

---

## Franken / Helix RAM Benchmark

```bash
# Fix permissions first (one time):
sudo mkdir -p /opt/heix && sudo chmod 777 /opt/heix

cd coms1
python3 franken.py
```

Watch for:
- L1/L2/L3/L4/L5 tier promotion/demotion times
- 1000-block stress test allocation speed
- HelixSync init time once `/opt/heix` is accessible

---

## What to Record Tonight

For each kernel slot:
- Average packet time (ms)
- Packets per second throughput
- Peak load before overflow kicks in
- Slot stepping behavior under load

For Franken:
- malloc/free cycle time
- Tier promotion latency (L1→L2, L2→L3)
- 1000-block stress: total time, avg per block

These numbers become the baseline. Phoenix v4.6 targets will be set against them.
