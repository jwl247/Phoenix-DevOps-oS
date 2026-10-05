# Sacrifice Build Plan

Oct 5, 2026 - @JW

## The Rule

Every phase is finished before the next one opens. No exceptions, no "we'll come back to it." Coming back is how it never gets done.

Done means: all files in the phase are written, tested, wired into Frank, committed to the repo, and passing. When the phase is done, it is done. We move and we do not return.

Current position: Phase 4 DONE (Oct 5). Phase 5 is next — living world (needs the MapTiler key in the vault).

## Vision and Covenant

Sacrifice is an MMO RTS simulation — a funded R&D platform for the Phoenix HUD and a second revenue leg for Life First. Every design decision serves two masters at once: the game has to be real and worth playing, and every system built for it is direct prototype work for the AI companion layer Laurie will depend on.

The reference design is K.I.T.T. from Knight Rider — not a control panel to click through, but an AI that is already acting and surfaces only the decisions that require the human. The in-game HUD, the voice companion, the "buttons" that are skill calls the AI makes in concert with the player — that is the same design problem as the Phoenix HUD, built twice. Building one is paid R&D on the other.

Frank is the world kernel. Frank witnesses every state change. Frank archives everything. Nothing in the game happens without Frank's knowledge — the same Frank that runs Phoenix OS, imported on demand, never moving, never forgetting.

The covenant: this game is GPL v3, open to the bone. No vendor lock. Three-tier AI backend (subscription / API key / Ollama-local) — Ollama stays a tested fallback, not a checkbox. Iron pays for it all. The game earns the second leg.

## Phase 1 — Foundation

Status: **COMPLETE** — game/ directory standing, Frank kernel wired, Helix events live.

| Component | File | Status |
| --- | --- | --- |
| Game package | `game/__init__.py` | Done |
| Frank world gate | `game/frank_world.py` | Done |
| Frank bus slot 4 | `FrankWorld._broadcast_event()` | Done |
| Helix-E egress | `frank.bus.write_stage(4, msg)` | Done |
| D1 custody | schema wired via packages-worker | Done |
| R2 world snapshots | clone pool ready | Done |

All game events emit to Helix-E channel 5 (Frank bus slot 4). Translation happens at the sector3 boundary — the game itself stays quadralingual throughout. Frank witnesses and archives every state change; nothing happens that Frank doesn't log.

## Phase 2 — Military Systems

Status: **COMPLETE** — all 7 modules live in `game/`, all wired into Frank via franken5.

| Module | File | What it does |
| --- | --- | --- |
| Draft Card | `draft_card.py` | Player identity, cryptographic signing, TRAINING → ACTIVE → KIA lifecycle |
| MOS | `mos.py` | Military Occupational Specialty — assessed from training observations, gated on rank |
| Rank | `rank.py` | Rank system, Frank-issued unit commands, promotion chain |
| Hospital | `hospital.py` | Wound management, real-time recovery, permadeath gate for Private–Corporal |
| Archive | `archive.py` | Permadeath — fallen cards archived permanently, honour threshold for legend status |
| Jacket | `jacket.py` | Complete service record, immutable entries, commendation/dishonour tracking |
| Frank World | `frank_world.py` | Single gate for all game state — Frank witnesses everything |

Private through Corporal: no hospital protection — critical wound = immediate KIA. Sergeant and above get the hospital system. Honour ≥ 0.8 with 3+ commendations at KIA → legend status, inserted into Boot Camp briefings permanently.

## Phase 3 — Jacket and Accords

Status: **COMPLETE** (Oct 5) — all four modules approved, wired through the FrankWorld gate, tested (`game/tests/test_phase3.py` 28/28, `test_helix_agnostic.py` 23/23, also against committed Helix).

| File | Status | What it does |
| --- | --- | --- |
| `accord.py` | Done — approved by JW | Accord system: propose, countersign, activate, conclude, void. HMAC-SHA256 signatures, Frank seals both. Immutable once concluded. |
| `tribunal.py` | Done | Player-run tribunal: charges, witnesses, verdict, sentence (execution or tribunal duel). Frank presides, verdict immutable. |
| `king_theater.py` | Done | King of Theater system: who holds the AO, challenges, disruptor mechanics, auto-generated KingTheater accords. |
| `footage.py` | Done | Kill footage system: top-N kills per AO flagged, stored in clone pool, surfaced in Jacket and world history. |

**Accord design rules (GDD §7):**

- Challenger names the accord — that name is permanent world history
- Challenger sets every rule: stakes, theater, time limit, allowed MOS, vehicle rules, observers
- Both parties sign via HMAC-SHA256 over terms hash with master key
- Frank seals both signatures with SHA3-512 — the Frank witness hash
- Outcome is immutable and public in both jackets
- Pay advantages must be disclosed in the terms (no hidden edges)
- Observers can be registered; observer count goes into world history

**Wired into Frank (`frank_world.py`):** `propose / countersign / activate / observe / void / conclude / sweep_expired`; `file_charges / open_tribunal / testify / vote / render_verdict`; `crown / challenge_king / grant_disruptor / use_disruptor / set_spawn_rules / owed_disruptors`; `record_clip / attach_r2 / top_kills`; `world_history()` (append-only, every entry also fired down Helix-E slot 4).

**Rules Frank enforces at the gate:** trainees and the dead hold no standing (can't challenge, witness, sit a jury); jury = ACTIVE players in the accused's theater only, fewer than 5 → dismissed and recorded; footage cited in testimony must exist; KING_THEATER / TRIBUNAL_DUEL accords are issued by Frank only (signed with Frank's own key, never a player's).

**Death is final for every standing (`kill()`):** the fallen's live accords are forfeited (unsigned ones voided); a King with a challenger in the field loses the crown to them; an unchallenged King's throne empties (`dethroned`, next `crown` takes it); an unused disruptor token dies with its holder.

**Frank's key:** `PHOENIX_FRANK_KEY` (hex) → `PHOENIX_FRANK_KEY_FILE` → created 0600 beside the archive on first run. Production: put it in the vault.

**Paid crown → owed disruptor (GDD §7.2):** Frank lists it (`owed_disruptors()`); choosing a player "of equivalent combat capability" is matchmaking in the game server, which then calls `grant_disruptor`.

## Phase 4 — Vehicles and Equipment

Status: **COMPLETE** (Oct 5) — `vehicle.py`, `equipment.py`, `vehicle_world.py` (FrankWorld mixin), `asset_intake.py`; `game/tests/test_phase4.py` 24/24, Phase 3 + Helix suites still green.

**Upgrades (JW: "make them upgradeable") — built to GDD §4.3, quality vs power enforced by structure:**

- POWER upgrades (armor, engine, weapons, cargo — 3 tiers) are **earned only**: the commander's jacket must meet the rank/battles/commendations/honour requirement. Paying for one is refused.
- QUALITY upgrades (optics, comms — reliability, repair rate) are earned **or** paid (receipt required). The registry refuses any upgrade that mixes the two.
- One per slot, tiers climb in order, an engineer (92A) installs from theater supply. The jacket records earned vs paid. Lose the vehicle, lose its upgrades; a captured vehicle keeps them.
- Personal gear works the same way: STANDARD issued to everyone, IMPROVED/SUPERIOR earned or paid, item power identical at every quality.
- Paid gear and paid upgrades are written into every accord's `pay_advantages_disclosed` by Frank before signing (GDD §7.4).

**Art is upgradeable too:** every model starts on a placeholder. `python -m game.asset_intake add <model> <photo>` stages the photo under a content name (avoids intake's basename collision), intakes it, checks the pool's hash, and adds it as a new art version; the local rembg cutout becomes LIVE. No rembg → the photo waits as pending (`promote <model> <v>`) or `--no-cutout` uses it as shot. Old versions are never deleted. `list` shows every model's art.

**Motor pool (generic names until JW's photos):** mbt, ifv, apc, attack_helo, lift_helo, recon_drone, patrol_boat, howitzer, supply_truck, recovery. Supply chain: depots per theater; fielding, repair and upgrades draw supply; logistics vehicles haul it between theaters.

**Vehicle art — real photography:** JW shoots real vehicles. Photos intake through Frank's import method: `intake.sh` → hex identity → sidecar.json → clone pool (R2) → D1 custody receipt. The asset lives at its TAV address. The game engine pulls it by address — no manual asset management. Background removal and edge cleanup as a post-intake step before the asset is marked live.

| File | What it does |
| --- | --- |
| `vehicle.py` | Vehicle registry: type, class, MOS unlock requirements, crew slots, photo asset TAV address |
| `equipment.py` | Equipment and loadout: item registry, MOS gates, weight/carry limits, durability |
| `vehicle_world.py` | FrankWorld extension: spawn, destroy, transfer, crew in/out, damage state |
| `asset_intake.py` | Photo → Frank import pipeline: call intake.sh on the photo, register asset TAV in vehicle registry |

**MOS gates (examples from GDD):**

- Driver MOS required to operate tracked vehicles
- Engineer MOS for vehicle repair
- Aviation MOS for air assets (if added)
- Any player can ride; operating is MOS-locked

**Vehicle classes (from GDD §4):** Light transport, heavy transport, armored, tracked, rotary (if added), watercraft (if added). Each class has a real-world photo asset. Each vehicle entry in D1 carries its TAV address, crew capacity, MOS requirement, and current damage state.

**Photo intake flow:**

1. JW shoots the vehicle
2. `usys clone <photo>` or `intake.sh <photo>` — Frank registers it
3. Hex ID generated, sidecar.json written, R2 upload
4. D1 custody receipt: asset is now addressable
5. `asset_intake.py` links the TAV address to a vehicle type in the registry
6. Background removal pass (local rembg — no vendor) marks asset live

## Phase 5 — Living World

Status: **NOT STARTED** — depends on MapTiler API key (JW getting it) and Phase 3 complete.

The world is persistent and player-shaped. Ground gets named. Events enter the permanent record. MapTiler powers the theater map.

| File | What it does |
| --- | --- |
| `named_ground.py` | Any player can name ground after a battle: the name is permanent world history in D1. Frank registers it. MapTiler renders the label on the theater map. |
| `world_history.py` | Permanent event log: battles, accords concluded, named ground, legends added, kings crowned. Immutable append-only, backed by D1. |
| `theater_map.py` | MapTiler API wrapper: render AO boundaries, named ground labels, King of Theater markers, strategic overview. |
| `territory.py` | AO ownership and control system: capture, hold, contest mechanics. Territory at stake in accords and King of Theater. |

**Named ground rules (GDD §6):**

- Any player can name ground after a significant battle in that AO
- The name is submitted to Frank, Frank registers it in D1
- A named ground entry carries: player\_id, callsign, battle\_id, ground\_name, ts, theater coordinates
- MapTiler renders the name on the map permanently
- Names can never be removed — only overwritten by a larger battle in the same AO (Frank determines significance by casualty count and accord outcomes)

## Phase 6 — Player-Run World

Status: **NOT STARTED** — depends on Phase 3 (accords) and Phase 5 (territory) complete.

Players run the world. The tribunal decides life and death. King of Theater is earned and defended. The sacrifice system costs something real.

| File | What it does |
| --- | --- |
| `tribunal.py` | **Delivered in Phase 3.** Player-run tribunal: charges filed, witnesses called, verdict (guilty/not), sentence (execution, tribunal duel, dishonour). Frank presides. Verdict immutable. Dishonour entry in jacket is permanent. |
| `king_theater.py` | **Delivered in Phase 3.** King of Theater: current holder, challenge mechanics, disruptor role, auto-issued KingTheater accord. King controls territory spawn rules in their AO. |
| `red_baron.py` | Red Baron Protocol: the player with the highest confirmed kill streak in an AO gets the Red Baron flag. Frank tracks, world history records, every player can see. Becomes a target. |
| `sacrifice.py` | Sacrifice system (GDD §9): a player can sacrifice their own rank, territory, or equipment to another player or to the world. Frank records the sacrifice in world history. The giver drops permanently. |

**Tribunal flow:**

1. Any player files charges against another (requires 3 witnesses to proceed)
2. Frank opens the tribunal record in D1
3. Witnesses testify (text, footage clips from `footage.py`)
4. Jury of peers votes (minimum 5 active players in the same theater)
5. Verdict rendered: Frank writes it immutably, jacket updated
6. Sentence executed by Frank — execution = permadeath trigger through `frank_world.kill()`; tribunal duel = auto-generated accord of type TRIBUNAL\_DUEL

**Disruptor role:** A player who holds the disruptor token can break any accord in their AO — once, per accord cycle. The disruptor is named in world history. They lose the token after use.

## MapTiler Integration

Status: **WAITING ON API KEY** — JW is getting it. Integration code ready to write once key is in the vault.

MapTiler powers the theater map, named ground labels, AO boundaries, and strategic overview. The key goes into the Phoenix vault (`F:\Phoenix\Vault\secrets\`) and is pulled by `theater_map.py` at runtime — never hardcoded, never in the repo.

| Feature | MapTiler endpoint | Phoenix hook |
| --- | --- | --- |
| Theater base map | Maps API — GL JS | `theater_map.py` render call |
| AO boundaries | GeoJSON overlay | `territory.py` serializes to GeoJSON |
| Named ground labels | Custom style layer | `named_ground.py` → D1 → MapTiler style |
| King of Theater marker | Point overlay | `king_theater.py` broadcasts via Helix-E |
| Strategic overview | Static map export | Session snapshot, stored in R2 |

**Key storage protocol:**

1. JW puts `MAPTILER_API_KEY` into the vault at `F:\Phoenix\Vault\secrets\maptiler.env`
2. Frank loads it from the vault at runtime — same pattern as `STRIPE_SECRET_KEY_LIVE`
3. `theater_map.py` reads it from the environment, never from a config file in the repo
4. Rotate: update the vault file, Frank picks it up on next load

**Named ground write flow:**

1. Battle ends in an AO, player submits a name
2. Frank validates: was there a real battle here? (checks jacket entries and accord history for the AO)
3. Frank writes to D1: `named_ground` table with coordinates, name, player\_id, battle\_id
4. `theater_map.py` pulls the D1 record and issues a MapTiler style update — the label appears on the map for all players
5. The name is permanent. Frank never deletes it.

## Revenue Model and Funding

The game is the second funding leg — deliberately earmarked toward API-tier AI access, real hardware, and low-latency voice+vision running together for Life First.

**Three revenue streams:**

| Stream | What it is | Phoenix stake |
| --- | --- | --- |
| Iron | Jerry's steel work (Enterprises) | Primary — funds the mission now |
| Game | Sacrifice revenue | Second leg — earmarked for AI hardware + API tier |
| Life First | Eventual SaaS / licensing | Long-term — Laurie's cushion at scale |

**Game monetization (GDD §10) — no pay-to-win, no hidden edges:**

- Cosmetic unlocks: callsign styles, jacket display themes, vehicle liveries (NOT stat changes)
- Accord transparency: any pay advantages must be declared in accord terms (built into `AccordTerms.pay_advantages_disclosed`)
- Supporter tier: access to draft card archive viewer, world history stats, named ground search — no gameplay advantage
- Phoenix OS node hosting: players who run a Phoenix node in the game world get in-game recognition — no stat advantage

**What the game funds specifically:**

- Full API-tier Claude access (the expensive, pay-per-token tier with no limits) — needed for voice + vision + tool use running together
- The dream setup: real hardware, H.L.K on a current gaming PC, low-latency response for Life First
- Ollama-local stays the floor — the game itself must run with Ollama only if API access goes away

**Radar integration:** Stripe is already wired (`STRIPE_SECRET_KEY_LIVE` in the vault, `stripe-setup.sh live` cleared). Game payments route through Radar. The SSI gate is cleared.

## Technical Stack and Architecture

**Backend — Python on Phoenix:**

| Layer | Technology | Role |
| --- | --- | --- |
| Game logic | Python 3.x, dataclasses | All phases: draft card through player-run world |
| World kernel | Frank (franken5) | Witnesses and archives all state; never moves |
| Memory engine | Helix | Double-strand, quadralingual; game events via bus slot 4 |
| Persistence | D1 (Cloudflare) | Custody chain for all game state — append-only immutable ledger |
| Asset storage | R2 (Cloudflare) | Vehicle photos, world snapshots, footage clips |
| Game state API | Cloudflare Worker | Exposes D1 game state to the front end over HTTPS |
| Map layer | MapTiler API | Theater map, named ground, AO boundaries |
| AI layer | Three-tier (subscription / API / Ollama-local) | Companion AI, MOS assessment, tribunal assist |

**Front end — Godot:**

Godot 4 is the game engine. GPL-compatible, no per-seat license, runs on the player's hardware, exports to Windows/Linux/Mac. The player's GPU runs the Godot client — Phoenix OS blacklists GPU drivers server-side, not client-side. Godot calls the Phoenix game state API (Cloudflare Worker) for all world state. Frank/Helix never touch the Godot client directly — they speak through the worker.

**Asset pipeline for vehicle photos:**

```
JW shoots photo
  → intake.sh → hex identity + sidecar.json
  → R2 (clone pool) + D1 custody receipt
  → asset_intake.py registers TAV address in vehicle registry
  → background removal pass (local rembg)
  → asset marked live in D1
  → Godot client loads asset from R2 by TAV address
```

**Multiplayer architecture:**

- Authoritative server: Cloudflare Worker + D1 is the source of truth
- Clients submit actions to the worker; worker validates through Frank logic
- No client-side game state — everything goes through the worker
- Real-time events: Helix-E pushes world events; clients poll or use Cloudflare Durable Objects for live sync

**AI layer (three-tier, from the dashboard):**

- Subscription tier: Claude.ai API, full capability, voice+vision
- API-key tier: direct Anthropic API, pay-per-token, highest headroom
- Ollama-local: must remain a tested fallback, not a checkbox — the game runs degraded but alive without any hosted AI

**Critical rules that apply to the game as they do to Phoenix:**

- Nothing enters the repo unless tested, polished, pro+ status
- No demos, no stubs — real code only
- All assets through Frank's import method — hex identity for everything
- D1 is append-only for game state; no deletes from the custody chain
- GPL v3 — open source to the bone
