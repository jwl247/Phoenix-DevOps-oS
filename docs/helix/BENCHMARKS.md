# Helix — benchmark record

Every Helix benchmark we have run output for, each with its source, method and
fine print. This is the evidence behind Helix's performance claims. If a number
isn't in here with a source, don't quote it.

Raw logs that contain personal machine details are kept in the vault, not in
this public repo: `F:\Phoenix\Vault\helix-benchmarks\` (with `SHA256SUMS`).

---

## 1. AWS EC2, 1 GB RAM — 2025-11-17

- **Source:** GitHub repo `helix_ai_serverSSP`, file `11-17-25 BENCH .txt`
  (commit `b3864cd`, 2025-11-21). Raw copy in the vault:
  `helix-benchmarks/2025-11-17-aws-ec2-1gb/`, sha256 `ce2f5815…692bf`.
- **Machine:** Ubuntu 24.04 EC2 instance, AWS us-east-1, 18 GB disk.
  `free -h` in the log shows **914 MiB RAM total**, a 1 GB class instance.
- **Method:** Python Helix AI system (`extreme_benchmark.py` and an "insane"
  benchmark), with S3 as the persistent store behind Helix's in-memory cache.

| Test | Result |
|---|---|
| Read (cached) | **346,465 ops/s**, avg 0.002 ms |
| Random access | **376,340 ops/s** (1,000 ops) |
| Sustained burst | **461,862 ops/s** (10,000 ops) |
| Read (second run, "insane" suite) | 47,799 ops/s, avg 0.0045 ms |
| Random (second run) | 1,902 ops/s |
| Stress | 2,686 ops/s (20,000 ops) |
| Cache hit rate | 100% |
| Write (to S3 over the network) | 28.7 ops/s, avg 34.7 ms, p95 60.2 ms, p99 88.2 ms |

**Fine print:** reads measure packets already in Helix's in-memory cache, in
Python. Writes are bound by S3 network latency, not Helix.

## 2. Helix cache in front of AWS S3 — 2025-11-16

- **Source:** `helix_ai_serverSSP` (`benchmark cache backend1.txt`,
  `benchmark s3.txt`); copy also at
  `archive/root-stale-consolidation-20260822-114018/Benchmarks4helixandCO`.
- Cached retrieve **98,597 ops/s** (92,007x faster than S3) and 49,897
  packets/s. S3 store ~1.1 packets/s (685–1,024 ms each). Hit rate 100%.
- **Fine print:** one line reports "1,000,000 packets/sec". That is an
  artifact of a timer reading ~0 s and is not counted.

## 3. Phoronix, minimum thermal tier — before 2026-03-03

- **Source:** `archive/fossil-consolidation-20260819-210541/SECTOR4/SECTOR4-coms`
  (first committed `e9d73ee`, 2026-03-03): "Helix in this configuration has
  benched between **600-687k ops/s** phoronix while zlib 6 and ... L1 L2 L3 all
  set to the minimum thermal tier."
- This is the source of the "700k" figure in CLAUDE.md and the README.
- **Note:** measured while governed: zlib 6 instead of her format (zlib 5),
  and the smallest tier sizes (see §6).
- Older header numbers in `HELIFRANKEN5.PY`: 30,595 insert, 887,251 retrieve,
  1,685,814 at scale (method not recorded).

## 4. Kernel Helix (dm-helix) on pbm3 — 2026-09-25

pbm3: AMD Athlon II X2 250 (2010), 7.5 GB RAM, spinning HDD origin, SSD for
Strand B. Block I/O through the real Linux block layer, direct I/O (page cache
bypassed). Script: `sector1/kernels/dm_helix_test.sh`.

| Configuration | Test | Result |
|---|---|---|
| Raw HDD | 4k random reads | 535–544 IOPS, ~1.85 ms |
| Single strand, headless (pre-Dandelion) | same, fully warm | 194,694 IOPS, 4.4 µs |
| Single strand + Dandelion | same, fully warm | 177,699 IOPS, 4.9 µs |
| Double helix, 32 MiB A + 512 MiB B | working set 6x RAM | 3,246 IOPS, 0.30 ms (raw 106 / 9.4 ms under load) |

Free drive (hands-off real work, 1.1 GB of system files, page cache dropped
between passes), Strand A capped at 512 MiB, fixed heat scale: six
search/checksum passes 581 s vs 639 s raw (9% faster; repeat searches 17%).
**Unbridled free drive (2026-09-25, same work, same machine):** her real size
(`auto`: 3,848 MiB Strand A = half the RAM), 8 GiB Strand B on the SSD,
self-calibrating heat, 8 parallel Strand B readers, all defaults, hands off.

| Pass | Raw disk | Helix unbridled | Speedup |
|---|---|---|---|
| Copy-in | 148.6 s | 149.9 s | 1.0x (writes pass through) |
| Search 1 | 106.2 s | 110.8 s | first read |
| Checksum 1 | 109.3 s | 31.8 s | 3.4x |
| Search 2 | 105.7 s | 3.6 s | 29x |
| Checksum 2 | 102.8 s | 5.5 s | 19x |
| Search 3 | 104.3 s | 2.7 s | 39x |
| Checksum 3 | 103.3 s | 5.6 s | 18x |
| **Six passes** | **632 s** | **160 s** | **4.0x** |
| **Passes 2-3 (learned)** | **416 s** | **17.4 s** | **24x** |

She self-calibrated to heat 1.0 under the work and was cooling (0.387) at the end.
She moved 28,630 blocks to Strand B on her own and served 28,089 reads from it;
28,087 blocks were on both strands. The integrity suite with 8 parallel readers
ran first: 0 failures.
**Fine print:** 1.1 GB fits in her 3.8 GB Strand A, so passes 2-3 run at RAM
speed. Linux's page cache was dropped between passes to measure her alone; on
this machine Linux's own cache could also hold 1.1 GB. Her edge over Linux
must be shown with working sets larger than RAM and under memory pressure
(the Compaq run is §5b).

**vs Linux, page cache LEFT ON (2026-09-25, same work, same machine):**
raw 0.6-0.8 s search / 2.9-3.1 s checksum per pass; Helix identical within
noise. Linux's page cache held all 1.1 GB and answered every read before it
reached the block layer. Helix saw 45 hits / 233 misses the whole run and
stayed cold. **A tie. When the data fits in RAM, Linux's own cache already
does the job and Helix adds nothing.** (The copy-in 121 s vs 29 s is a test
artifact: the raw run went first and left the source files cached. Not
counted.) Her advantage has to be shown where Linux's cache runs out: working
sets larger than RAM (Strand B: ~30x the raw disk, section 4), memory pressure
(the "page cache dropped" runs simulate that case), and persistence and sharing
beyond one kernel's cache.

## 5. Python Helix via FUSE on pbm3 — 2026-09-25

The headless Python stack as a FUSE filesystem was **slower than plain Linux**
(warm random reads 10.9 vs 13.6 MiB/s). That is the evidence for moving Helix
into the kernel and restoring her Dandelion.

## 5b. Kernel Helix (dm-helix) on pbm-compaq, Phoronix raw vs Helix — 2026-09-27

**Run:** `sector1/kernels/helix_verdict_lean.sh` on pbm-compaq, 2026-09-27 13:15–17:32 CDT, detached, with Jerry off the machine.
**Box:** i5-2400 (4 cores), 15 GB RAM, Debian 13 (kernel 6.12.107).
**Origin:** Seagate ST1000LM035, 1 TB at 5400 rpm (serial WQ992JYZ).
**Helix setup:** double strand, Strand A `auto` (half the RAM), Strand B a 64 GB image on the Samsung SSD. Table: `0 1953521664 helix 8:17 7943 7:0 65536`.
**Method:** same filesystem, no reformat; 3 passes per test (`FORCE_TIMES_TO_RUN=3`). The raw fio figures come from the 2026-09-26 fresh run. fs-mark was dropped: it is uninformative for a write-through cache and never finished. PTS result file `helix-compaq`, identifiers `raw` and `helix`. Filed 2026-09-29; the run had finished but was never written up here.

| Test | Unit | Raw disk | Helix | Helix vs raw |
|---|---|---|---|---|
| fio sequential read, 1 MB, 2 jobs | MB/s | 127 | **4,716** | **37.1× faster** |
| fio random read, 4 KB, 2 jobs | MB/s | 1.052 | 1.039 | 0.99× (same) |
| fio sequential write, 1 MB | MB/s | 119 | 123 | 1.03× (same) |
| fio random write, 4 KB | MB/s | 1.335 | 1.290 | 0.97× (same) |
| postmark (small-file transactions) | TPS | 3,457 | 3,947 | 1.14× faster |
| sqlite-speedtest, size 1,000 | s (lower is better) | 110.99 | 112.77 | 0.98× (same) |
| dbench, 6 clients | MB/s | 9.95 | 9.29 | 0.93× |
| dbench, 12 clients | MB/s | 18.57 | 15.25 | **0.82× slower** |
| dbench, 48 clients | MB/s | 32.51 | 8.61 | **0.26× slower (about 4× worse)** |

**What it says:**
- **Repeat big reads are her strength: 37× on sequential read.** This is the ingress shape: pulling assets and model weights that get read again.
- **Writes tie the raw disk,** as designed: she is write-through, so the origin always holds the data.
- **4 KB random reads over fio's cold, spread-out working set gain nothing.** Nothing was hot yet.
- **Heavy concurrent mixed load is a real regression.** dbench at 48 clients runs at 26% of the raw disk. That is the shape of many game clients or workers hitting one box at once, and it has to be solved or routed around before Helix fronts a multi-client server. It is not yet diagnosed. Candidates: per-I/O Dandelion and lane locking, compression on the write path, or Strand B relief I/O competing with origin I/O on the same controller.

**Consequence for the Compaq road test** (`docs/plans/compaq-road-test-plan.md`), which Jerry set 2026-09-29: "if it's slow as shit we change helix's strands to unmanaged the ingress and egress." These numbers argue for ingress on Helix (bulk repeat reads) and for measuring egress (writes, concurrent pushes) both Helix-managed and unmanaged from the first run.

## 5c. Opened up: dm-helix on pbmIII (pbm3), 2 GiB Strand A, CPU governor performance (2026-10-05)

Same box for every run (AMD Athlon II X2 250, 7 GB, HDD, 4 GiB loop image, direct I/O), dbench 60 s.
Tool: `sector1/kernels/helix_tune.sh`. New governor knob `relief_enabled` (module param) isolates relief.

| Clients | Raw MB/s | Helix MB/s | Helix, relief off | Helix ÷ raw |
|---|---|---|---|---|
| 6  | 163.98 | 67.33  | 66.76  | 0.41× |
| 12 | 158.44 | 117.52 | 120.54 | 0.74× |
| 48 | 492.79 | 430.23 | 381.43 | **0.87×** (was 0.26× at 256 MiB on the Compaq) |

What it shows:
- **Starved, not broken.** With room, 48 clients went from 0.26× to 0.87×.
- **The governor's relief (compression, Strand B moves) costs nothing measurable.** Off vs on is within noise.
- **Helix's own code is not CPU-hot.** dbench took 65% of the CPU; no Helix symbol is near the top.
- **dbench barely re-reads:** Helix counted 47 hits vs 368 misses. It is a write-new-data workload, not
  Helix's job (re-reads: 37× in §5b). The remaining gap is pass-through cost on writes. The standard fix is
  write-around for new writes; that is the next tuning step.
- The desktop (Xorg/Thunar/XFCE) used about 15% of the CPU during the run. Servers should boot without it.
- Lesson: `kptr_restrict=2` (hardening) hides kernel symbols from `perf`. Profile with it lowered, then restore.

## 6. Why older numbers understate her

Her real configuration is L1 256 MB / L2 1024 MB / L3 3072 MB (about half the
machine's RAM, "4 GB of 8 GB") with zlib level 5. Most code ran with the
constructor defaults (128/512/1024, zlib 6): half or less of her real size.
The 600–687k Phoronix figure (§3) was measured in that governed state.

## Measuring her: precision rule

Jerry, 2026-09-25: "we tried to measure her .01 or something and all her
numbers came out the exact same ... we changed that parameter 4 times
eventually ending up at .00001 and she was cooking." When the instrument's
resolution is coarser than her operations, every run reads identical, or reads
~0 and turns into nonsense (the "1,000,000 packets/sec" line in section 2 came
from a timer printed at 0.01 s resolution). The trail is in the AWS scripts
(`extreme_benchmark.py`: `time.time()` totals printed `.2f`, later `.4f`). The
final 0.00001 setting isn't in any committed version.
**Rule:** time with nanosecond clocks (`time.perf_counter_ns()`, fio's
`clat_ns`, `ktime`), report at microsecond precision or finer, and treat any
result at or near a timer's resolution floor as invalid. The kernel benchmarks
in section 4 use fio's nanosecond latencies.

## Open

- The 2026-09-25 stress test under forced memory pressure measured a 41.7%
  hit rate (Round 2 functionality S1-F17). "100% hit rate" holds only when the
  working set fits her tiers; say so wherever it's quoted.
- An end-to-end repeat of §1 and §3 with the kernel Helix at her real size.
- **dbench concurrency regression (§5b): 48 clients at 0.26× raw.** Diagnose before Helix fronts any multi-client server.
- The working-set-bigger-than-RAM run on the Compaq (15 GB RAM) is still owed.
