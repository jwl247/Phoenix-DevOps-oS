# Ring build plan — 1 Cpt Conductor, 4 rings, the journal motor

**Status: PLAN ONLY. Not being built (Jerry 2026-10-07: "make a build plan its not getting built yet,
prefetch needs worked out").** Prefetch (§6) is the open piece and gates step 3 onward.

Sources: Jerry's ring sketch + talk (`docs/plans/ring-topology-sketch-2026-10-07.md`), his four
configuration pages (`press-room/1.jpg`-`4.jpg`), the Music ring (a guide only), `sector4/ring/`
(built + tested 10/7 morning, parked), the kernel's `SharedMemoryBus` (`sector1/helix-lightning/franken5.py`).

## 1. The rules this plan keeps (Jerry's)
- **The spine stays:** user input → the door (Helix-I) → custody + pool + versions + glossary →
  out (Helix-E) → translate ONLY at the exit (sector3). Already real; build on it, don't redesign it.
- **The structure (J, 10/7, exact):** "there is 1 cpt conductor · there is a propcoms in every ring so
  propcoms has 6-8 members in its circle · 4 rings, 4 propcoms talk to 1 conductor · conductor is bee
  line kernel." Members talk ONLY to their ring's propcoms; each propcoms talks ONLY to the Conductor;
  the Conductor has the direct line to the kernel and is the ONLY comms in and out of the rings. That is
  why coms is built the way it is.
- **Cpt Conductor is Frank's promotion, but not where Frank5 / the Genie kernel lives (J).**
- **The audit file is the motor: "everything written to it runs" (press-room/4.jpg).**
- **`helix_api.py` is different per machine; everything else in a ring is typical.**
- **SMB = shared memory bus**, inside one machine. Between machines: the mesh.
- **Rings 1-3 = red, blue, yellow; ring 4 = system use, so there is no latency problem waiting on
  anything (J, 10/7).** (press-room/2.jpg's "ring 4 provided Helix is fast enough" was an earlier config.)
- Speed is the goal: every step measured before/after (`docs/helix/BENCHMARKS.md` precision rule).
- Validate once at the door. No redundant re-checks in the hot path.

## 2. The shape
```
                        outside (mesh, Helix-I in, Helix-E out)
                                        │
                     KERNEL ═══ bee line ═══ CPT CONDUCTOR     ONE, the only door in/out of the rings
                                        │                       journal (the motor) · bus owner · ring loader
             ┌──────────────┬───────────┴──┬──────────────┐
         propcoms        propcoms        propcoms        propcoms        one hub per ring
          coms4           coms3           coms2           coms1
        6-8 members     6-8 members     6-8 members     6-8 members      talk ONLY to their propcoms
   (franken, freewheeling, quadengine, new_horizon, guardian, ... + helix_api for the box it runs on)
```
**Open (ask Jerry):** which machine the one Conductor lives on; whether the 4 rings all live on that
machine or spread across machines (then a propcoms reaches the Conductor over the mesh, signed); what
runs when the Conductor's machine is off (Jerry travels — a standby Conductor that takes over, or the
rings hold until he is back).

## 3. The journal (the motor)
- One append-only journal, kept by the Conductor.
- An entry = a job: `{seq, at, who, kind, args, prev_hash}`. Writing it IS the request; the Conductor
  runs it (straight down the bee line to the kernel when it is kernel work, or to a ring's propcoms)
  and appends the result entry (`{seq, result, ms, hash}`), chained by hash (tamper shows).
- One file, three jobs: **run** (the motor), **audit** ("what did you just do" is always answerable),
  **heal** (replay rebuilds a box; anyone checking a box reads what it should be doing).
- Who may write which kinds: the permission tiers in CLAUDE.md (base runs, deviation asks, never-auto
  refused). Sensitive = rule 10, a terminal yes, never a journal entry from an agent.
- Same idea as a Genie stage; the journal is where stages are written down, not a second system.

## 4. The 4 rings, members in-process
- Each ring: one propcoms + 6-8 members, declared in JSON (press-room/4.jpg) and side-loaded as
  threads/tasks — not 8 processes, not folders, not polling.
- Members get work from their propcoms through bus slots and are WOKEN by a signal (event/semaphore),
  never a timer. Status lives in the bus header, not status files.
- Disk only for custody and the cold store, written in background batches, never in the hop path.
- One Helix per machine, shared on the bus (not one per member).
- `helix_api.py` per machine behind a **contract** (route, broadcast, heartbeat, cold store, bus
  attach); one pool row per machine (`pbmii/helix_api.py`, `pbmiii/helix_api.py` — folder-aware names
  work since 5196ff2); each tested against the contract before it is intaked.
- New Horizon is Linux-only + root for swap by its own header: Windows needs its own body or it reports
  idle (never fakes work).

## 5. The bus
- Owned by the Conductor (not the kernel's `frank5.shm`; that one is the kernel's, reached over the
  bee line).
- Only the door writes into it from outside; the bus file is locked to Phoenix's own user.
- Fix first: the kernel bus holds ONE stage per slot (`helix_ring.py` notes it) — the rings need a real
  ring buffer (many slots, head/tail, wake signal), one region per ring.
- A ring on another machine never shares memory across the wire: its propcoms ↔ the Conductor go over
  the mesh, signed.

## 6. PREFETCH — OPEN, must be worked out before step 3 (Jerry)

**Decided (J, 10/7):** not one monolith prefetch — **three**, with **the same tiered system as Helix**
("right exactly the prefetch has the same tiered system as helixes"): hot (RAM / Helix hot tier,
ms-s, from what is being touched now), warm (local SSD/NVMe, s-min, from the journal: a written job's
inputs fetched before it runs), cold (4 TB / 20 TB drive from the pool and other machines, min-h, from
patterns). Each hands up to the tier above, so nothing is fetched twice.
**All of it is color coded (J): the color FAMILY is the tier** — "primary colors tier1, secondary colors
tier2, tertiary colors tier3":
| Tier | Family | Colors |
|---|---|---|
| T1 (hot) | primary | red, blue, yellow |
| T2 (warm) | secondary | orange, green, purple |
| T3 (cold) | tertiary | red-orange, yellow-orange, yellow-green, blue-green, blue-violet, red-violet |
The family says the tier at a glance; the hue inside it says which ring/lane.
**The QR codes reference the colors — the BOTTOM QR (footer: location + tier) (J).** Today (checked 10/7)
the footer is text only, `USYS:<b58>:FOOTER:<hex>:<loc_hex>` in D1 (`intake.sh` report_clonepool), with
no color field, and no QR image is ever rendered for pool files (the only qrcode code is
`sector3/phoenix-net/phoenix-net.py`, for something else). To build: a color field in the footer
(family = tier, hue = ring/lane) and the rendered footer QR drawn in that color; header QR keeps its
state colors (white/grey/black). Footer AFTER hashing, header BEFORE (CLAUDE.md rule 7) — unchanged. Rings 1-3 are red, blue,
yellow (J). **Ring 4 is SYSTEM USE (J): kept for the system's own work so nothing waits on anything —
system jobs never queue behind user work.** (Its color: not given yet.) Nothing in the repo records this color code yet — it gets written here first, then into
the ring/tier code and the QR footer tier colors (CLAUDE.md TAV: footer QR = tier color T1-T4).

Still open:
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
| 3 | The 4 rings in-process on the bus, 4 propcoms → 1 Conductor (needs §6) | all members live, same work as step 0, faster by measurement | the Conductor's machine |
| 4 | `helix_api` contract + per-machine bodies | each body passes the contract test, intaked per machine | PBMII, pbmIII |
| 5 | Rings on other machines (if Jerry spreads them) | a propcoms on pbmIII reaches the Conductor over the mesh | pbmIII — service install = rule 9, Jerry's yes first |
| 6 | The Conductor's bee line to the kernel + his standby (per Jerry's answer) | kernel work goes only Conductor → kernel; standby takes over when he stops | both + mesh |
| 7 | Healing through the journal + per-box reference | break a node, a PEER fixes it (Jerry's test) | both |
| 8 | Ring 4 = system use: the Conductor routes system work (healing, journal upkeep, prefetch cold tier?) only there | a heavy system job running never slows a user ball in rings 1-3 (measured) | the Conductor's machine |

## 8. Not in this plan (parked)
Windows/Linux Concierges sharing memory on one box (press-room/1.jpg — only applies where both run on
one machine, e.g. the Debian VM). One drive per user folder (press-room/1.jpg) — waits for the 20 TB
drive and the "drives sequential by label" design with Jerry.
