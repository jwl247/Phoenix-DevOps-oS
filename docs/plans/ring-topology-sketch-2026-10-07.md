# Ring topology sketch (Jerry, 2026-10-07) — CAPTURED, talked through, NOT BUILT

Jerry: "here is something i have envisioned for later." Hand sketch (photo in the 10/7 evening chat).
Talked through the same evening; corrections from Jerry are marked (J). Architecture stays a talk WITH
Jerry as it develops — do not build ahead of him.

## What the sketch shows
- **Center: PRECISION = Phoenix primary** (PBMII). Ports: socket, phone, and arcs out to each node.
- **COMPAQ = router**, **STORE / HP = storage**. Two circles unlabeled (ask).
- **Every circle is a RING, not an engine stack (J).** "Typical" = the same ring on every node.
- **Typical ring members (J):** QuadEngine, Prefetch (New Horizon's prefetch horizon), New Horizon,
  **SMB = Shared Memory Bus (J)** — not Windows file sharing, not Syncthing.
- **Outer arcs** join rings to each other, not only to the center.
- **`helix_api.py` is different per machine (J)**: the one non-typical piece, the ring's fit to that box.
- **The PCs all work together (J).**

## Where it stands in the code (checked 10/7)
- A shared memory bus already exists in the kernel: `SharedMemoryBus` in
  `sector1/helix-lightning/franken5.py` (256 MB mmap `frank5.shm`; Frank, Helix-I, Helix-E use it).
  The ring members do not use it today ("it dont", J).
- `C:\Users\jwlef\Music` ring = **a guide only (J): "we know more now and things are different."**
  `helixaudit.sh` and rebound are old architecture, not installed. The audit was (or should have been)
  the motor that starts and stops everything in the ring folder (J); the Music copy has no motor; `sector4/ring/rebound.py` is today's start/stop.
- `sector4/ring/` = built + tested on PBMII the morning of 10/7 (rebound.py runs team.json through
  member.py: all 8 alive 35 s, balls validated and escalated coms4->3->2->1, kill -> restart, clean stop;
  bug fixes to `helix_api.py`: cold store, RESPONSIBILITY_PATH, `ket`->`key`, memory_bank role).
  Uncommitted; PARKED by Jerry ("the rest of this has to run correctly and the easy put in first").
- Jerry's standing call: ONE ring in the pool, imported 4x (coms1-4) by each machine.

## Design notes from the talk (Claude's, for Jerry to accept or change)
- Make the center a ROLE any node can take (Jerry travels; PBMII may be off).
- Shared memory works inside one machine only: one bus per ring; ring-to-ring over signed mesh doors.
- Only Helix-I (the door) writes to a bus; the bus file locked to Phoenix's own user (validate once at
  the door). The kernel bus's one-stage-per-slot limit (`helix_ring.py`) needs fixing before a team uses it.
- New Horizon is Linux-only + root for swap: on Windows it needs a Windows body or reports idle.
- `helix_api.py` per machine needs a contract (route, broadcast, heartbeat, cold store, bus attach),
  one pool row per machine (`pbmii/helix_api.py` ...), pinned in each box's healing reference.
- Healing: each box keeps a reference (path, pool name, version, SHA3) pulled from the master at
  deploy time; the reference lives in the pool with custody; peers read it to heal each other.

## Open questions for Jerry
The two unlabeled circles · the motor: what it starts, in what order, what stops it · which box is
"Store HP" (pbmIII is the HP Compaq 6200) · the ring's doors (ring.json "doors" is empty).
