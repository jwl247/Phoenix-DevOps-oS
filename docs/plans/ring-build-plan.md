# Ring build plan — 1 Cpt Conductor, 4 rings, the journal motor

**Status: PLAN ONLY. Not being built (Jerry 2026-10-07: "make a build plan its not getting built yet,
prefetch needs worked out").** Prefetch (§6) is the open piece and gates step 3 onward.

**The general idea (J, 10/7): "basically we build Helix into 3 PCs" — not written in stone.** One Helix
across the three sisters (PBMII, the Compaq, the HP), with everything below as the working draft of how.

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

**Placement (J, 10/7): each machine has its corresponding ring, with its own ingress and egress;
all roads lead to the HP for final storage.** Open, the big one (J): **how deep the Phoenix universe
delves into R2 and D1** — today CLAUDE.md says R2 is the source of truth for content and D1 the custody
ledger; "final storage on the HP" moves the truth home. Decide before step 5.
**The principle (J, 10/7): "we are the universe but the cloud will be our satellites that the rest of
the world marvels at."** Home (the HP, the machines, the mesh, Jerry's phone as a mesh node) holds the
truth; the cloud (R2, D1, workers) is the satellites: offsite copy, game edge, Radar, the public face.
Remote access goes phone → mesh → HP, not through the cloud. Proposed (Claude, awaiting Jerry's yes,
changes CLAUDE.md "R2 primary — source of truth"): the HP holds final bytes + its own custody ledger;
R2/D1 mirrored in the background; if the cloud vanished, home keeps running.
**Roles (J, 10/7): the Compaq (pbmIII) is the ROUTER — to be built. Final storage = the other HP.**
CLAUDE.md "R2 primary" stays until this is built ("not yet, we haven't built any of this").
**End game (J, 10/7, referencing the ring sketch):** the Compaq RECEIVES everything, sorts, organizes,
prioritizes, and sends it on to "dad" (ask: PBMII?) or the HP. Same for egress. **Prefetch calls and all
of that come from PBMII.** **Everything in this system clones to destination** (the clone pool is the
installer; see the sector-kernels / clone-to-destination note).
**The three sisters (J, 10/7): "we are going to make all three pcs sisters — think as 1, act as 1;
everything else is 1 — socket together, symlink, whatever is called for."** PBMII (the brain: decisions,
prefetch calls), the Compaq (the router: receives, sorts, prioritizes, in and out), the HP (final storage).
One system across three bodies: one Conductor, one journal, one namespace (the same path means the same
thing on every sister — builds on the slash-insensitive paths and "drives sequential by label"), joined by
sockets over the mesh, symlinks where a local path must point at a sister's.
**Desktops (J, 10/7): the Compaq and the HP lose their desktops at some point** — they end up headless
(router, storage). Creative apps live on PBMII only, where Jerry sits; their HEAVY work (renders, encodes,
transcription) is movable work the load balancer may send to a free sister. The Compaq's LightDM /
Chrome / TV-sound setup (10/7) is temporary, for while it is still used as a desktop.

**What Franken really is (worked through with Jerry 10/7, confirmed "correct"):** `Music\franken.py`
was built by Jerry in Meld from separate parts — the Helix VRAM/cache (from the old
`helix_complete_package.py`, a zlib-6 stand-in, not her), the translator (apps speak Linux:
malloc/open/read/write with pointers and fds → Helix's language and back; `heix/kernel/core/helix_translator.py`),
the AgnosticLayer (its own file, `heix/kernel/core/agnostic_layer.py`), and HelixSync (Syncthing, ported
from `heix_syncthing_module.js`) — all in `archive/fossil-consolidation-20260819-210541/SECTOR4/heix/`.
The only Helix part in his "Helix" block is her **tiered eviction** — and that block is really
**the STORAGE SYSTEM (J, 10/7)**: tiers + eviction ladder + compression + virtual RAM + file cache. Keep the
names apart: **Helix** = two strands side by side, the Dandelion, rungs, quad; **the storage system** = the
tiers (T1/T2/T3, color coded), eviction down, prefetch up.
Take those out and what is left is **the assembler**: start the parts, wire them, give apps one door
(5 calls). That is the Conductor's job. Two false claims in what is left, not to carry forward: it prints
"Core 3, Real-time priority" but sets neither; it prints "ALL TESTS PASSED" without checking anything.

**Captured, not designed (J, 10/7): "we can make the helix kernel pure C, a namespace kernel, and go with
it — I'm not being sarcastic."** Talk it through with Jerry before anything is built.

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
**Decided (J, 10/7): FREEWHEELING IS THE RING'S SHARED MEMORY BUS — "freewheeling is supposed to be the core of
the mem group, we should use it as ring SMB."** It already has what a bus needs: QuadralingualPackets
(every ball held in all 4 languages — quad-native, the "QuadEngine in the shared memory"), a Dandelion with
64 lanes and per-lane locks, store / retrieve / query_language, compress / expand under load. It is plain
in-process memory, which fits §4 (members side-loaded in ONE process): members share it directly, no
copies, no files. Flow: members -> propcoms only; propcoms puts the ball on Freewheeling; the next member
is woken and takes it from Freewheeling. Kills the step-0 polling (511 ms/ball). **The ring's data handlers (J, 10/7): "always Frank sorting to Freewheeling and Helix pushing or pulling."**
Frank (franken) SORTS — decides where each ball goes and puts it into Freewheeling; Freewheeling HOLDS (the
bank = the bus); Helix (New Horizon) MOVES — pushes out of Freewheeling (eviction down the tiers) and pulls in
ahead of need (prefetch up the tiers), i.e. the paging manager's "clears and feeds her". Today's
`member.py` gets this wrong: franken hands to freewheeling through a folder, and new_horizon only archives
balls already done (never pushes/pulls).
If members ever had to be
separate processes, Freewheeling would move onto a memory-mapped region (not needed in this design).

- Owned by the Conductor (not the kernel's `frank5.shm`; that one is the kernel's, reached over the
  bee line).
- Only the door writes into it from outside; the bus file is locked to Phoenix's own user.
- Fix first: the kernel bus holds ONE stage per slot (`helix_ring.py` notes it) — the rings need a real
  ring buffer (many slots, head/tail, wake signal), one region per ring.
- A ring on another machine never shares memory across the wire: its propcoms ↔ the Conductor go over
  the mesh, signed.

## 5b. Sockets between the sisters (talked 10/7)
Measured 10/7: PBMII → Compaq over the mesh 1.3 ms avg (max 2 ms, 10/10); the Compaq's eno1 links at
**1000 Mb/s** (older notes said 100), 4 cores, 16 GB RAM.
- **Everything on the wire is QUADRALINGUAL (J: "everything turns quadralingual").** No translation
  sister-to-sister; translator.sh only at the sector3 exit (CLAUDE.md rules 1-3). A message whose four
  strands disagree is refused at the door: validation is a property of the data, not a step.
  Measure the size/CPU cost of four strands on the real link (quadpack note: MEASURE it).
- **Jerry's hypothesis (10/7): Helix has a connection with the quad — she translates quad into her own
  language, and "the results were different when it was quad, so we'll see."** Test it as an A/B on the
  same data and the same box: plain vs quad into Helix — store/fetch time, compression, hit rate,
  prefetch accuracy, CPU. Keep whichever wins by the numbers (BENCHMARKS precision rule). Fits the
  original intent: quadralingual = room for her to interpret the data, not a fixed 4-format scheme.
- **One persistent connection per sister pair**, reused (the ~7 s/file intake was mostly fresh HTTPS
  calls to Cloudflare; an open mesh socket is ~1-2 ms). **Priority lanes:** rings 1-3, ring 4 (system),
  bulk files — a big copy never blocks a small message.
- Files stream at wire speed (gigabit ≈ 110 MB/s; zero-copy send on Linux, HP → Compaq → PBMII).
- Inside one sister: the shared memory bus + local sockets/named pipes. Never shared memory across the wire.
- Nebula proves the MACHINE, not the program: every socket keeps its own key (the Helix `HXT` token
  handshake) + signed requests (what one sister may ask another).
- A sister that is off: messages wait in the journal and go when she is back; nothing lost.
- Bind exclusively, mesh address + loopback only, refuse loudly when a port is taken (10/7: a stray PoC
  held 7701-7704 and stages went to it silently).
- Symlinks to a sister's folder need a mounted share (SMB/NFS); Windows symlinks need Developer Mode/admin.
  Shares only where a program needs a path; the main road is sockets.
- Off-mesh (Jerry's phone away from home): 30-80 ms through the lighthouse; control yes, bulk stays home.

## 6. PREFETCH — OPEN, must be worked out before step 3 (Jerry)

**Decided (J, 10/7):** not one monolith prefetch — **three**, with **the same tiered system as Helix**
("right exactly the prefetch has the same tiered system as helixes"): hot (RAM / Helix hot tier,
ms-s, from what is being touched now), warm (local SSD/NVMe, s-min, from the journal: a written job's
inputs fetched before it runs), cold (4 TB / 20 TB drive from the pool and other machines, min-h, from
patterns). Each hands up to the tier above, so nothing is fetched twice.
**Why the tiers match (J, 10/7): "her eviction is tiered."** Helix HOLDS data on two strands side by side
(the wider hallway, deterministic placement); her EVICTION steps down tiers (hot → warm → cold → out).
Prefetch is the same ladder in reverse (cold → warm → hot, ahead of demand). Compared 10/7: Franken2's
HelixCache (Music/franken.py) is a plain 3-tier LRU with no Dandelion and one lock — not Helix;
dm-helix is closest in body; New Horizon is the newest and the only one with quad.
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

**The tiers live on the three sisters (J, 10/7, confirmed):**
| Tier | Sister | Prefetch role |
|---|---|---|
| T1 hot (primary colors) | PBMII | what is in use now, RAM; PBMII makes the prefetch calls |
| T2 warm (secondary colors) | the Compaq | **the holding area**: staged ahead of PBMII asking; the router decides what waits there and how long |
| T3 cold (tertiary colors) | the HP | final storage, everything |
Compaq <-> HP talk prefetch (the HP pushes what is likely needed into the Compaq's warm holding area);
the Compaq hands from the holding area into PBMII's hot tier (1.3 ms link). Eviction is the same ladder in
reverse (PBMII -> Compaq warm -> HP). The "bus between each machine and the other" is figurative: one
conversation per pair, each with its own job; under it, a mirrored bus (each side writes its own copy at
memory speed, the socket keeps the copies in step, the reader wakes on arrival).
**A QuadEngine in the shared memory (J): "to help it along."** Data stays quad on every bus and in the
holding area; the QuadEngine on each bus keeps it quad (encode on the way in, strands checked as they land,
so a bad message never reaches a ring) — and, per Jerry's hypothesis, quad may be what Helix runs fastest
on (measure it: the New Horizon A/B).

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

## Step 0 RESULT — baseline of today's ring (run 2026-10-07 21:15 on PBMII, `sector4/ring/bench_ring.py`, scratch home)
- Start: all 8 members up in 2.5 s (conductor_sync + syncthing idle by design). **17 processes.**
- **Idle: CPU 2.6% of one core, 18.2 file writes/s with no work at all.**
- **One ball at a time: in -> done p50 511 ms, max 633 ms** (20/20 done) — ~0.5 s per ball is almost all
  polling waits (3 hops x 0.25 s sleeps), not work.
- **Burst of 500: 40 done, 460 escalated to coms3** (freewheeling escalates past 60 balls/min on one system);
  all 500 accounted for in 6.32 s = 79 balls/s. Nothing missing, nothing in breach.
- Raw: `sector4/ring/bench_ring-20261007-211510.json`. This is the "before" every later step is measured against.

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
