# Helix, whole again: plan for JW's review

2026-10-05. JW: "make helix whole again or the thing comes crashing down with 3 players."

## Already done today (fix, not design)

The game's events no longer get lost. Every game event used to go into one 4 KiB slot of the shared
bus, and the last writer won. With three events written before one read, only `KIA` survived. Now
they go through `sector1/helix-lightning/helix_ring.py`: append-only, sequence-numbered, per-reader
cursors, a lock that holds across threads and processes, and readers told exactly how many events they
missed if they fall behind. Proven with 8 threads × 500 events and 4 processes × 300 events, with no
loss. Commit `5a6bb8a`.

## Where Helix stands (survey, 2026-10-05)

| Layer | What's canonical | What's duplicated |
|---|---|---|
| Storage engine | `sector1/kernels/dm_helix.c` (helix.ko, live on the Compaq). `helix_vram.py` is its userspace mirror, and `main_kernel.py` already calls it "the canonical double Helix" | `helix_complete_stack.py` is a **second userspace Helix** with its own Dandelion (and 661 uncommitted lines from 10/3: DandelionController, HelixHostProfile) |
| I/O and bus | `helixi.py` / `helixe.py` / `franken5.py` / `helix_gate.py`, and now `helix_ring.py` for events | `tools/poc/true_double_helix.py` (a copy of helixi); `frank_ring-1.py` (byte-identical copy); `helix-lightning/main_kernel.py` (an old copy) |
| Director | `sector3/hlk/hlk.py` (H.L.K, the peer between ingress and egress) | none |
| Legacy | none | `helix_complete_package.py`, `helix_slim.py`, `phoenix-core/src/helix_*.c`, `sector2/frank/frank_helix.py`, `sector2/ring0/frankenhelix.py` (their systemd units point at dead paths), and `Claude outputs/double_helix*.py` |

The known performance wound (BENCHMARKS.md §5b, the Compaq, dbench MB/s, raw vs Helix):

| Clients | Raw | Helix | Ratio |
|---|---|---|---|
| 6 | 9.95 | 9.29 | 0.93× |
| 12 | 18.57 | 15.25 | 0.82× |
| 48 | 32.51 | 8.61 | **0.26×** |

Not diagnosed yet. The candidates: per-I/O Dandelion and lane locking (`b_lock` nested inside the lane locks), compression on the write path, and Strand B relief I/O competing with clients.

## Proposed: one Helix, three layers

1. **One storage Helix.** dm-helix (kernel) plus **one** userspace mirror, `helix_vram.py`. Fold the useful
   parts of `helix_complete_stack.py` (HostProfile sizing tiers to the machine's RAM, DandelionController)
   into `helix_vram.py`. The second userspace Helix then becomes a thin wrapper or retires.
2. **One I/O layer.** Helix-I and Helix-E for sockets, `helix_ring` for events, `helix_gate` for admission. The slot
   bus stays for the stage hand-offs Genie uses. Anything that is a *stream of events* moves to the ring.
3. **H.L.K directs.** No change.
4. **Duplicates move to `archive/`** (never deleted, with a note saying where the canonical piece lives).
5. **Fix the 48-client wound with evidence, not guesses**, on the Compaq:
   - a. Measure lock contention under dbench-48 (`perf lock` / lockstat).
   - b. Run the same test with write-path compression off.
   - c. Run it with Strand B relief paused.
   - d. Fix what (a)–(c) point to. Likely lane-sharded locking, so the shared `b_lock` isn't taken on every I/O.
   - **Target: ≥ 0.9× raw at 48 clients.** If Helix can't beat standard caching there, the standard wins that job (JW's rule, road-test plan §6).
6. **Versioning, healing, compliance, the same as the mesh:**
   - a version stamp per Helix instance
   - a heal check: Helix up, the ring writable, readers not lapped (lapped readers raise an alarm), Dandelion pressure sane
   - every repair logged
   - compliance notes for availability (A1.2), integrity (SI), audit (AU)

## What the game actually needs from Helix, and when

- **Now (slice):** the event ring. Done. The game server's state is the world-history chain plus D1, so it
  does **not** sit on dm-helix. 48-client dm-helix performance doesn't block the first playable slice.
- **Before real player counts:** the H.L.K + ingress/egress triplet delivering game content packs, warm on the
  player's drive. That's where dm-helix performance matters, so step 5 runs before that.

## Needs JW

- Go or no-go on steps 1–4 (consolidation; touches the 10/3 uncommitted Helix work, which should be committed or
  reviewed first).
- **The Compaq on the network** for step 5. dm-helix lives there.
