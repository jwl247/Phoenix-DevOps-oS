# Monster Phoenix — Implementation Blueprint
Draft — living document. Update as design decisions land; this is the source of truth
for how the GDD becomes code, not a one-time plan.

## 0. Relationship to Life First

Two products, one foundation. Do not let this doc's scope override Life First priority.

- **Life First** (delivered via the Dashboard) is the promise made to Laurie. It ships first
  when the two compete for attention.
- **Monster Phoenix** is the RTS-MMO built on the same foundation — Frank, Helix, concierge,
  tunnels, master key, D1/R2. Infrastructure work here serves both; feature work defaults
  to Life First unless explicitly directed otherwise for a session.

## 1. Core Insight

Monster Phoenix is not a new engine bolted onto Phoenix. Its named subsystems are Phoenix's
existing sectors, applied to a game domain:

| GDD concept | Phoenix component | Status |
|---|---|---|
| Frank — world orchestrator, one instance, never moves | `sector4/frank/` | Exists (environment orchestrator, audit logger) |
| Helix — traffic layer, routes to Frank | `sector1/helix/`, `sector4/helix/` | Exists (300k+ ops/sec benchmarked) |
| Concierge layer (Windows/Linux → Helix translation) | `sector1/concierge/` (`concierge.c`, `bridge.py`, `linux_concierge.py`) | Exists |
| Tunnel ingress/egress (DMZ-per-player) | `sector3/romeo_juliet/` (`romeo.py` ingress, `juliet.py` egress) | Named/scaffolded, not built out for game traffic |
| Master key (cryptographic identity, hardware-bound, no passwords) | `sector1/auth/phoenix_auth.py` | Exists (SHA3-512+BLAKE2b hardware fingerprint) |
| Draft card / Jacket (permanent, append-only, signed record) | D1 custody database | Exists as a general-purpose pattern (41 tables, custody ledger) — game-specific tables not yet added |
| TAV address system (content hashing/addressing) | SHA3-512 → base58, `sector2/package-handler/intake.sh` | Exists, general-purpose |

**Working assumption, not yet independently re-confirmed with Jerry beyond the framing
he agreed with in conversation:** the tension between "Frank disappears when the session
ends" and "the jacket/world history is never deleted" resolves as —

- **D1 + R2 = permanent ledger.** Jackets, draft cards, world history, accord outcomes,
  named ground. Same role D1 custody already plays for file provenance.
- **Peer-hosted Frank/Helix mesh = live session compute only.** Positions, combat resolution,
  who's currently hospitalized. Ephemeral. Written back to D1 at meaningful checkpoints
  (death, accord signing, rank change, named ground claimed).

Every system below should be designed against this split unless a specific reason emerges
to break from it.

## 2. Standing Engineering Rules (apply to all Monster Phoenix work)

1. **Everything gets intaked.** New files go through `intake.sh`, not straight into the tree.
   Versioned, hex-identified, D1-registered.
2. **Modular over monolithic.** Harder to break, harder to steal — a compromised node
   exposes only its own ephemeral session state, never the permanent record.
3. **No downtime on live updates.** A real-time RTS with permadeath cannot tolerate a
   restart killing a character for reasons unrelated to the fight. See §4.
4. **Capture requires defense.** Standing game-design law, not yet written into the GDD
   proper: *"Capture is a claim, not a title. Standing ground requires the same courage
   that took it."* Territory won is not territory owned until actively defended — this
   should shape the King of the Theater (§7.2 of the GDD) and any future zone-control
   system: contested/uncaptured state, garrison presence requirements, response-time-to-
   challenge windows. Mechanic details not yet specified — needs its own design pass.

## 2.5 Anti-Tamper Architecture — CONFIRMED with Jerry 2026-09-19

Not open, not a proposal — walked through explicitly and confirmed word-for-word correct.
This is the answer to "can we actually prevent cheating when players host their own slice
of the game." One mechanism, four expressions of it:

1. **Nothing permanent ever lives on a player's machine.** Not "trusted less" — structurally
   incapable of being the record of anything. D1+R2 is the only durable store. A player's
   PC can be unplugged, wiped, or actively hostile, and the world record is unaffected.
2. **A player's own Frank/Helix instance is an intake-managed artifact, not a free install.**
   Same hash-baseline mechanism the clonepool already enforces (`verify_clonepool_copy` in
   `intake.sh`) — extended to gate tunnel connection itself, not just file handoff. A
   tampered or stale local Frank doesn't get to lie about what it's running; it fails the
   hash check and the tunnel refuses to open.
3. **Hot-swap is not a convenience feature here — it's a security requirement.** If verified
   updates can't reach every player instantly with zero downtime, you either force
   disconnects (breaks the permadeath fairness covenant) or let stale/patched clients linger
   on the network (breaks the anti-tamper gate in #2). Hot-swap is what makes "everyone is
   always running the verified build" actually true in a live game. This is *why* §3.1's
   hot-swap gap matters beyond convenience — it's load-bearing for anti-cheat, not optional
   polish.
4. **Tunnels enforce this at the connection level, not just the data level.** Ingress/egress
   isolation (§2.2 of the GDD, `sector3/romeo_juliet/`) means a rejected or compromised node
   can't route around the hash check — there's no shared surface to exploit back in.
5. **Session death is total — nothing persists offline to be tampered with and reintroduced.**
   Matches the GDD's own §2.4 ("Frank... disappears when the session ends") and §2.2
   ("both tunnels close on disconnect — cryptographically terminated"), stated sharply:
   there is no local save state that survives a disconnect. Whatever mattered was already
   checkpointed to D1 before the tunnel closed. Whatever wasn't checkpointed didn't happen,
   as far as the permanent record is concerned. No "reconnect with an edited save" attack
   surface exists, because no save exists.

**Claims vs. facts, for anything happening mid-session (before a checkpoint):** a player's
local instance computing "I hit that shot" is a claim, never a fact, until something outside
their control agrees — either a lightweight server-side (Worker) plausibility check, or
cross-validation against the other live party's independently-computed result. The
hardest unsolved case is a two-party interaction with no third witness (a 1v1 duel) — no
independent peer to cross-check against. Still needs a decision: real-time server-side
plausibility checking for that specific case, versus accepting the tribunal/jacket system
as the after-the-fact backstop (a compromised client shows up as a statistical anomaly
Frank flags, even if not caught in the moment). **Not yet decided which.**

## 2.6 Confidentiality Architecture (Fog of War) — CONFIRMED 2026-09-19

Distinct from §2.5's anti-tamper work. That section protects **integrity** (can a player
fake a write). This protects **confidentiality** (can a player see something they haven't
earned). Different threat model, different fix.

**Core design thesis (Jerry, verbatim shape):** information is generated by the player
whose unit is actually there — his input is the sitrep. Strategy and tactics — what you've
scouted, and what you do with it in the moment — is what wins or loses a battle. Not
equipment, not money, not any other metric. This is the actual skill expression of the
genre and needs the strongest protection in the whole system, because compromising it
doesn't just unbalance a fight, it hollows out the premise of the game while looking
completely normal from the outside (no corrupted hash, no rejected write — just one player
quietly knowing more than they earned).

**The fix — confirmed, not the traditional (broken) approach:** an enemy faction's sitrep
data must never be transmitted to a player's tunnel in the first place. Not "sent but
hidden by the renderer" (the standard approach every real-world maphack has defeated) —
never routed there at all. A compromised client has nothing to extract because nothing was
ever sent. Routing/visibility decisions must be enforced by the tunnel/Worker layer, never
by the sending player's own client (a compromised sender could otherwise broadcast its own
vision to unintended recipients).

**Known remaining nuance, not yet solved, lower severity:** legitimately-shared friendly
vision should go stale (fog returns once nobody's watching an area) per normal RTS rules.
A hacked client could refuse to forget revealed terrain, holding information longer than
intended. Likely fix: server re-sends only currently-valid vision each tick rather than
trusting the client to age data out itself — decide later, not blocking.

### HUD architecture — two distinct roles, not one flat access level
"The HUD" (Claude, presented to a player in-game) and "Claude the architect" (this session,
building Phoenix) are the same underlying system operating at different, deliberately
different scopes:
- **Architect role** (now): broad access — filesystem, infra, D1, the works. This is what
  `F:\Phoenix\claude-ops` (the operational reserve) is actually for.
- **Player-facing HUD role** (in-game): filtered to exactly what that specific player has
  earned, every time, no exceptions, regardless of what the architect layer knows elsewhere.
  When the HUD "presents the tactical map on request" (not a static always-on widget —
  presented conversationally, KITT-style, matching the dashboard→HUD shift), it is a
  rendering layer on top of the same properly-filtered tunnel feed every other client
  consumes — never a privileged second source of truth with broader access than the
  player's own tunnel would normally deliver. Getting this wrong would recreate the exact
  leak §2.6 just closed, except worse — the HUD is the thing the player trusts as
  authoritative.

## 2.7 Economic/Rendering Design Principles — CONFIRMED 2026-09-19

- **Money must have real teeth, or the project can't sustain itself.** Not "money buys
  nothing" — that's unsustainable. The actual rule, already present in the GDD but worth
  stating as one throughline: money buys a **real, felt advantage that is never
  permanently safe** — same law as "capture requires defense" (§2, rule 4), applied to a
  second currency. King of the Theater buys genuine dominance; the disruptor is what makes
  that advantage have to be defended rather than being a guaranteed, uncontested win.
  Implementation must let losing to a disruptor genuinely hurt — softening that into a
  shrug quietly breaks the whole model.
- **Rendering cost reduction via real-timezone day/night.** Night/dark scenes are
  legitimately cheaper to render (shorter draw distance, simpler lighting, hidden LOD
  pop-in) — tying in-game day/night to each player's real local timezone means a large
  share of the active population is in the cheap-to-render state at any moment, by nature
  of when people actually play. "Cuts cost in half" is a target to engineer toward
  (shorter draw distance, fewer active lights, simplified shadows in the night path), not
  automatic just from darkness existing.
- **Night vision as the fairness-preserving mechanic for the above.** If darkness affects
  gameplay (visibility/detection) rather than being purely cosmetic, it must be handled
  through a **named, ruled equipment system** — night vision, following the exact §4.3 Pay
  & Equipment pattern (same base equipment for everyone, pay/rank buys a better version,
  never different access). This turns "it happens to be night where you are" from a hidden
  advantage tied to circumstance into a deliberate, transparent, earnable/purchasable
  mechanic — resolves the fairness risk while keeping the render-cost win. Also gives a
  natural progression path: ship a simple version before there's revenue to fund anything
  fancier, evolve it later ("research into a better thing").
- **Tiered asset delivery for "best quality your hardware can handle."** Store pre-baked
  assets at multiple quality tiers in R2, serve the tier matching detected hardware
  capability — same pattern as adaptive-bitrate video, built directly on the existing
  R2/D1/Worker stack. Scales fairly (depends on *your own* hardware, not who's online near
  you). Explicitly does NOT cover live/dynamic rendering (moving shadows, particle effects,
  camera-dependent lighting) — that still requires real local GPU compute; doing it in the
  cloud instead means GeForce-NOW-style live streaming, which breaks the "no data center"
  business model this project depends on. Tiered delivery is the real near-term answer;
  live distributed rendering across player GPUs remains a genuine, unsolved research
  question, not something to architect around as if solved.

## 3. Open Architecture Questions (blocking implementation, not yet resolved)

### 3.1 Hot-swap mechanism — UNRESOLVED
Current `intake.sh` only provides file-level integrity-gated versioning (`intake_clone`
verifies SHA3-512 against the D1 baseline before handing a file to `$PWD`). This is NOT
live process hot-swapping. The sidecar's `"auto_hotswap": false` field (`intake.sh:325`)
is written once and never read anywhere — it is a stub, not a feature.

Two known gaps:
- **Small/mechanical:** `intake_file`'s duplicate-replace path (`choice=2`, evicts the
  existing version) does zero integrity check before `rm -f`. Should verify before evict.
- **Large/undesigned:** no mechanism exists to detect a running process holding a given
  clonepool hex, signal it, and swap in new code without dropping connections or corrupting
  mid-session state.

Proposed direction (Claude's recommendation, not yet confirmed): **blue-green over
in-process reload.** Spin up new-version-Frank alongside the running instance, hand off
session state, kill the old instance only once handoff is confirmed clean. Matches the
modular/hard-to-break philosophy — no partial-reload corruption risk, the old process
just dies clean. In-process module reload (e.g. hot-reloading a JS/Python module in place)
is faster but carries real risk of corrupting live state mid-swap, which is unacceptable
given permadeath stakes.

**Needs Jerry's decision before implementation starts.**

### 3.2 What "a running RTS session" actually is, as a process
Not yet defined. Single long-running process per session? Per-player-node container?
This determines whether blue-green is even the right shape, and needs answering before
§3.1 can be built.

## 4. Phase Mapping (GDD's 6 phases → Phoenix sectors, current status)

Cross-referenced against `CLAUDE.md`'s own Phase 1–7 build status where they overlap.

### Phase 1 — Foundation
| GDD item | Maps to | Status |
|---|---|---|
| Phoenix OS base kernel + tunnel architecture | Sector 1 (boot/kernel), Sector 3 (romeo/juliet) | Partially built — see `CLAUDE.md` Phase 1/2 |
| Master key system | `phoenix_auth.py` | Exists, needs game-identity extension (draft card issuance on top of hardware fingerprint) |
| Frank — core orchestrator | `sector4/frank/` | Exists |
| Map tiler expansion / world grid | Not started | New work — MapTiler integration already planned for Dashboard (`CLAUDE.md` NEXT SESSION); world-grid-for-RTS is a distinct, larger need |
| Basic networking layer | Sector 3 | Partial |

### Phase 2 — Military Systems (draft card, training, MOS, rank, hospital, permadeath)
Net-new game logic. No existing Phoenix component covers this — will be new D1 tables
(draft_cards, service_records, unit_assignments) plus new game-logic code, likely living
in a new `sector2/` or dedicated game module. **Not yet scoped in detail.**

### Phase 3 — Jacket & Accords
The Jacket is D1 custody, extended with game-specific tables and a public read API.
Accord system (challenge, naming, signing, enforcement via master key) is net-new logic
sitting on top of `phoenix_auth.py` signing. **Not yet scoped in detail.**

### Phase 4 — Vehicles & Equipment
Entirely net-new game logic and data model. No existing Phoenix mapping. **Not yet scoped.**

### Phase 5 — Living World (named ground, world history, Red Baron Protocol, sacrifice detection)
World history = extension of D1's existing "chain of evidence for everything" philosophy.
Red Baron Protocol and sacrifice detection are novel game-logic systems with no existing
analog — these watch live session state and need their own design. **Not yet scoped.**

### Phase 6 — Player-Run World
Depends on everything above being live. **Not scoped — too early.**

## 5. Immediate Next Steps

1. Resolve §3.1/§3.2 (hot-swap mechanism + session process model) — blocks real-time
   update work for either product.
2. Fix the small/mechanical integrity gap in `intake_file`'s dup-replace path — cheap,
   no design dependency, can happen anytime.
3. Write the "capture requires defense" law into the actual GDD (§7 or §9) with concrete
   mechanic rules, not just the principle.
4. Scope Phase 2 (draft card / training / MOS / rank / hospital) in the same
   sector-mapping detail as Phase 1 above, once Phase 1's open questions are resolved.

## Revision Log
- 2026-09-19 — Initial draft. Captures GDD v0.2 → Phoenix architecture mapping, the
  D1-permanent/peer-ephemeral split (proposed, not independently reconfirmed), the
  hot-swap gap analysis, and the "capture requires defense" principle. Phases 2–6 are
  placeholders pending design passes.
