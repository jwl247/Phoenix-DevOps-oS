# Ring build plan — the Conductor, the journal motor, one ring per machine

**Status: PLAN ONLY. Not being built (Jerry 2026-10-07: "make a build plan its not getting built yet,
prefetch needs worked out").** Prefetch (§6) is the open piece and gates step 3 onward.

Sources: Jerry's ring sketch + talk (`docs/plans/ring-topology-sketch-2026-10-07.md`), his four
configuration pages (`press-room/1.jpg`-`4.jpg`), the Music ring (a guide only), `sector4/ring/`
(built + tested 10/7 morning, parked), the kernel's `SharedMemoryBus` (`sector1/helix-lightning/franken5.py`).

## 1. The rules this plan keeps (Jerry's)
- **The spine stays:** user input → the door (Helix-I) → custody + pool + versions + glossary →
  out (Helix-E) → translate ONLY at the exit (sector3). Already real; build on it, don't redesign it.
- **Who talks to whom:** members talk ONLY to their ring's propcoms; propcoms talks ONLY to Cpt
  Conductor; the Conductor is the ONLY comms in and out. That is why coms is built the way it is: one
  propcoms → one Conductor, so rings add without rewiring (J, 10/7).
- **Cpt Conductor is Frank's promotion, but not where Frank5 / the Genie kernel lives (J).**
- **The audit file is the motor: "everything written to it runs" (press-room/4.jpg).**
- **`helix_api.py` is different per machine; everything else in the ring is typical.**
- **SMB = shared memory bus**, inside one machine. Between machines: the mesh.
- **Ring 4 (Helix) only "provided Helix is fast enough" (press-room/2.jpg)** — decided by measurement.
- Speed is the goal: every step measured before/after (`docs/helix/BENCHMARKS.md` precision rule).
- Validate once at the door. No redundant re-checks in the hot path.

## 2. The shape
```
            outside: other machines (signed, over the mesh) · Helix-I in · Helix-E out
                                         │
                                  CPT CONDUCTOR            one per machine; the only door
                         journal (the motor) · bus owner · ring loader
                                         │  shared memory bus (this machine only)
                                     propcoms              the ring's hub
              ┌──────────┬──────────┬────┴─────┬──────────┬──────────┐
           franken  freewheeling  quadengine  new_horizon  guardian   ...   (+ helix_api for THIS box)
           members = JSON declarations the Conductor side-loads IN-PROCESS (press-room/4.jpg)
```
The mesh is the ring of rings: PBMII, pbmIII, awslh (+ R2 as the vault). The 4-way spread that the
breach_coms1-4 drives used to give is now across machines; the pool (R2 + D1 custody + versions)
carries the safety the 4 drive rings used to.

## 3. The journal (the motor)
- One append-only journal per machine, in the Conductor's home.
- An entry = a job: `{seq, at, who, kind, args, prev_hash}`. Writing it IS the request; the Conductor
  runs it and appends the result entry (`{seq, result, ms, hash}`), chained by hash (tamper shows).
- One file, three jobs: **run** (the motor), **audit** ("what did you just do" is always answerable),
  **heal** (replay on a fresh box rebuilds it; a peer reads it to see what a box should be doing).
- Who may write which kinds: the permission tiers in CLAUDE.md (base runs, deviation asks, never-auto
  refused). Sensitive = rule 10, a terminal yes, never a journal entry from an agent.
- Same idea as a Genie stage; the journal is where stages are written down, not a second system.

## 4. One ring per machine, in-process
- The Conductor loads `team` + member declarations (JSON) and runs members as threads/tasks in his
  process — not 8 processes, not folders, not polling.
- Members get work from propcoms through bus slots and are WOKEN by a signal (event/semaphore), never
  a timer. Status lives in the bus header, not status files.
- Disk only for custody and the cold store, written in background batches, never in the hop path.
- One Helix per machine, shared on the bus (not one per member).
- `helix_api.py` per machine behind a **contract** (route, broadcast, heartbeat, cold store, bus
  attach); one pool row per machine (`pbmii/helix_api.py`, `pbmiii/helix_api.py` — folder-aware names
  work since 5196ff2); each tested against the contract before it is intaked.
- New Horizon is Linux-only + root for swap by its own header: Windows needs its own body or it reports
  idle (never fakes work).

## 5. The bus
- Owned by the Conductor (not the kernel's `frank5.shm`; that one is the kernel's).
- Only the door writes into it from outside; the bus file is locked to Phoenix's own user.
- Fix first: the kernel bus holds ONE stage per slot (`helix_ring.py` notes it) — a ring needs a real
  ring buffer (many slots, head/tail, wake signal).
- Cross-ring/cross-machine traffic never touches another machine's bus: Conductor → mesh → Conductor.

## 6. PREFETCH — OPEN, must be worked out before step 3 (Jerry)
What exists: New Horizon's "prefetch horizon σ" (predicted next access from mean ± stddev of past
intervals; `PrefetchCompressor` adaptive poll 50 ms / 200 ms / 500 ms / 2 s; `hint_prefetch` into T3),
and the sketch calls Prefetch "typical" on every ring. Questions to settle with Jerry:
1. **What gets prefetched?** Pool objects (code/suits), game assets/quadpacks, model weights for the
   local engine, user files, Helix pages — one of these or all, and which first?
2. **Who owns it?** One owner per box (the Conductor, or New Horizon as his member) so two ends of a
   link never fetch the same thing twice.
3. **What predicts the need?** Past access timing (New Horizon's σ), the journal (an entry written is a
   job about to run — its inputs can be fetched before it runs), the game's own state (where a player is
   heading), or a mix.
4. **Where does it land?** RAM (Helix hot tier), the bus, local SSD/NVMe cache, or the 4 TB / coming
   20 TB drive — and what gets evicted to make room.
5. **Across machines:** does pbmIII (storage manager) push to PBMII ahead of time, or does PBMII pull?
   (Windows primary, Linux = data delivery suggests the HP pushes.)
6. **Its adaptive poll** (50 ms-2 s) is a timer; on the bus it should wake on events instead — does
   that keep New Horizon's behaviour?
7. **How we measure it:** hit rate, bytes wasted (fetched, never used), latency saved — and the
   Helix-vs-standard caching test (road-test plan §6) with a working set larger than RAM.

## 7. Build order (when Jerry says build), each step measured
| Step | What | Done when | Touches |
|---|---|---|---|
| 0 | Baseline today's `sector4/ring/` | per-ball in→done ms, balls/s, idle CPU, disk writes/s recorded | PBMII only, read/measure |
| 1 | The journal motor | entries run, results chained, replay rebuilds a test home, tamper detected | PBMII |
| 2 | The bus (ring buffer + wake) | many slots, no polling, µs hand-off measured | PBMII |
| 3 | One in-process ring on the bus (needs §6) | all members live, same work as step 0, faster by measurement | PBMII |
| 4 | `helix_api` contract + per-machine bodies | each body passes the contract test, intaked per machine | PBMII, pbmIII |
| 5 | The ring on pbmIII | same test passes there | pbmIII — service install = rule 9, Jerry's yes first |
| 6 | Conductor ↔ Conductor over the mesh, signed | a ball crosses boxes through both doors only | both + mesh |
| 7 | Healing through the journal + per-box reference | break a node, a PEER fixes it (Jerry's test) | both |
| 8 | Ring 4 = Helix, only if the Helix-vs-standard test says she is fast enough | decided by numbers | — |

## 8. Not in this plan (parked)
Windows/Linux Concierges sharing memory on one box (press-room/1.jpg — only applies where both run on
one machine, e.g. the Debian VM). One drive per user folder (press-room/1.jpg) — waits for the 20 TB
drive and the "drives sequential by label" design with Jerry.
