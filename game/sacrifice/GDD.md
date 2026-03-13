# Game Design Document: Sacrifice
**Version:** 0.2 — Phoenix-powered, deterministic architecture
**Engine:** Unity (private repo: "step 1") + Phoenix-DevOps-oS runtime
**License:** GPL v3 / Commercial dual-license

---

## 1.0 Overview

**1.1 Game Title:** Sacrifice

**1.2 Genre:** Real-Time Strategy (RTS) with deep logistical, economic, and political simulation.

**1.3 Elevator Pitch:** A strategic RTS where players command real-world nations, managing populations, complex supply lines, and espionage. Victory depends on industrial might, logistical planning, and maintaining the stability of the home front — not just battlefield tactics.

---

## 2.0 Core Gameplay & Mechanics

### 2.1 Time & Progression
- **Real-Time Core:** The game runs continuously in real-time.
- **"Complete Button" (Fast Forward):** Players can unanimously vote to fast-forward time to the next in-game day. If not unanimous, time continues in real-time.
- **Day/Night Cycle:** Affects visibility and operations (e.g., 9 pm – 7 am is dark).

### 2.2 Core Principles
- **Population is Key:** Population is the source of all military units and the civilian workforce. Its growth and loyalty (morale) are paramount.
- **Logistics is the Foundation:** Victory is impossible without managing supply lines for resources and fuel.
- **Homeland Defense is Critical:** Protecting home territory from raids and espionage is as important as frontline combat.

### 2.3 Map & Terrain
The game uses real-world map data from MapTiler. Terrain effects (movement penalties, defensive bonuses) are defined on a per-unit basis.

---

## 3.0 Win & Loss Conditions

### 3.1 Game Modes
Players vote on the victory condition in the game lobby before the match begins.
- **Strategic Victory:** Each province is assigned a point value. The first player/alliance to control provinces totaling 70% of the map's total points wins.
- **Total Domination:** A "last man standing" mode where victory is achieved only when a single player/alliance controls 100% of the provinces.

### 3.2 Optional Time Limit
Players can vote to set a time limit. If the timer ends, the player/alliance with the highest score wins.

### 3.3 The Surrender Mechanic
- **Surrendering to an Alliance:** All provinces, units, and resources are transferred to the remaining allies.
- **Surrendering to an Enemy:** The recipient only gains control of the provinces and units that are geographically contiguous (touching) their own borders.
- **Fate of Non-Contiguous Territories:** Any of the surrendering player's territories not contiguous to the recipient immediately secede and become neutral.

---

## 4.0 Economy & Resources

### 4.1 Resource Categories
- **Primary (Raw) Resources:** Metal, Wood, Oil, Gas, Food
- **Secondary (Produced) Resource:** Core Mat'l — processed goods/components, produced in Industrial Plants
- **Abstract Resources:** Money (currency), Population (manpower)
- **Fuel Types:** Gas (Tier 1), Biofuel (Tier 2), Wind/Turbine/Solar (Tier 3)

### 4.2 Resource Generation
- **Geographic Sourcing:** Each map region provides a base income of specific raw materials based on real-world geography.
- **Development:** Players augment raw material yield by building development structures (Mines, Farms, etc.).

### 4.3 Trade
A global Trade Market allows players to buy and sell resources. Deals require physical transport, making trade routes vulnerable.

### 4.4 Production & Logistics Bottlenecks
Production buildings (Industrial Plants, Mines, etc.) have an internal storage buffer. When this buffer is full, production halts.

The rate at which this buffer empties is determined by the number of available loading bays and the efficiency of the transport units (trucks, trains) assigned to the building's supply route.

Upgrading a building to a higher tier increases production output significantly but also requires more dedicated transport to prevent the buffer from filling up.

**Factory Loading Bay Scale:**
- Tier 1: 2 loading bays
- Tier 2: 4 loading bays (total)
- Tier 3: 8 loading bays (total) — dedicated logistics wing

---

## 5.0 Research System

**5.1 Research Cost:** Research does not use "Research Points." Each technology costs a specific amount of Money, Metal, Wood, and Core Mat'l.

**5.2 Research Time:** Based on the technology's tier and its combined resource cost.
- Tier 1: Base Time = 9 × "Cost Value" (minutes)
- Tier 2: Base Time = 6 × "Cost Value" (minutes)
- Tier 3+: Base Time = 3 × "Cost Value" (minutes)

**5.3 Morale Influence:** National Morale modifies research time. High morale speeds it up; low morale slows it down.

---

## 6.0 Military Research Tree

**6.1 Unit Deployment:** Tiered unlocks for Infantry, Armor, Air, and Naval units.

**6.2 Unit Enhancements:** Upgrades for Armor, Weapons, Speed, and Sensors.

**6.3 Military Logistics:** Dedicated, high-capacity/high-cost supply units and Forward Bases. Includes research to lower Embark/Disembark times.

**6.4 Military Production:** Unlocks tiered, specialized military production buildings (Barracks → Armor Plants → Aerospace Complexes). Includes research for Carrier capacity.

**6.5 Doctrines & Tactics:** Nation-specific bonuses and special unit abilities.

**6.6 Recruiting Branch:** Manpower mobilization, improved training, and morale management (War Bonds, Hero Branding). Unlocks the Draft.

**6.7 Advanced Weaponry & Missile Systems:** A late-game tree beginning with Anti-Air and Anti-Missile defense, which then unlocks branches for Air-to-Air, Air-to-Ground, Cruise Missiles, and finally Ballistic Missiles (Scud, Chemical, Tactical & Strategic Nukes).

**6.8 Electronic Warfare & C5ISR:** A special high-tier branch for information dominance, including Radar, Satellites, Sonar Buoys, and culminating in a five-tier research path to the EMP.

---

## 7.0 Unit & Fortification Mechanics

### 7.1 Unit Design Principles
Realism & Asymmetry, Logistical Footprint, Combined Arms, Veterancy.

### 7.2 Universal Unit Stats
Health (HP), Armor, Speed, Attack Damage, Rate of Fire, Range, Fuel Capacity, Fuel Consumption, Supply Consumption, Visibility/Stealth, Manpower Cost.

### 7.3 Infantry Branch

#### Base Units (unlocked via research, produced at Military Base):

**Base Infantry**
- Research: Initial Infantry tech
- Strength: Faster movement on clear terrain
- Weakness: Movement penalty when encountering obstacles (forests, hills, water)

**Base Marine** *(Prerequisite: Infantry)*
- Strength: Traverses obstacles (water, forests) quickly and efficiently
- Weakness: Slower movement on clear terrain

**Base Spec-Ops** *(Prerequisites: Infantry + Marine)*
- Role: Elite vanguard / night operations
- Strengths: Superior mobility (faster than Infantry AND Marine), lower energy consumption, higher base attack rating
- Weaknesses: Low baseline defense (glass cannon), penalized during daylight hours
- Note: Spec-Ops depend on certifications to bring defense up to match their attack rating. Fully certified Spec-Ops are deadly — attack and defense ratings balanced.

#### Infantry Certifications (researched independently, stack on unit production cost):
- **LoS Night Vision:** Increased line of sight during nighttime
- **Urban Warfare:** Combat bonus in urban terrain
- **Ranger School:** +10 combat rating (flat bonus)
- **Survival Training:** +10 bonus when unit HP reaches 25% or below
- **Air Raid Survival:** Defensive bonus against helicopter attacks

Certs do not require each other. A fully certified unit takes significantly more time and resources to produce. A fully certified Spec-Ops is the pinnacle of infantry.

### 7.4 Unit Stacking System *(Researchable under Logistics)*

| Tier | Name | Max Units |
|------|------|-----------|
| 1 (Base) | Fire Team | 4 |
| 2 | Squad | 9 |
| 3 | Platoon | 27 |
| 4 | Company | 200 |

**Overstack Penalty:** For each unit over the researched limit: -5% to Movement, Attack, and Defense (cumulative).
- Example: 2 over limit = -10% to all three stats.

**Platoon Rules:**
- Once 27 units form a Platoon, they are administratively bound to that Platoon.
- Splitting a Platoon must produce valid sub-stacks: Squads of 9 or Fire Teams of 4 only.
- Detached sub-stacks are still assigned to the original Platoon and cannot merge with a different Platoon.
- Reason: Platoon integrity requires exactly 27 units. Losses are replaced by fresh production, not by raiding other formations.

### 7.5 Fortification & Siege Mechanics
- Fortifications provide significant damage resistance. Armor and aircraft suffer severe penalties attacking them.
- Special Forces can perform "Detailed Recon" to reduce these penalties, making defensive patrolling essential.

### 7.6 Amphibious & Naval Transport
- Ground units can self-transform into slow water transports or be carried on faster, dedicated transport ships.
- Embark/Disembark Timer: 15-minute base (researchable to 8 min, or 5 min for veterans).

### 7.7 Carrier Operations
Aircraft Carriers must be accompanied by a Supply Ship to function. The Supply Ship has a depleting inventory and is a primary target.

---

## 8.0 Diplomacy, Espionage, & Intelligence

### 8.1 Spy & Counter-Spy Upkeep
Deployed agents require a substantial daily payment in Money.

### 8.2 Spy Mission Cycle
A spy must receive orders at an origin point, travel to the target, complete the objective, and return to the origin point for the mission to succeed.

### 8.3 Issuing Spy Commands
Initiated from the command pop-up on an enemy province, which opens a special spy menu.

### 8.4 Spy Prerequisites (researched once)
Languages, Electronic Surveillance, Evasion, Small Arms, Rifle Cert, Physical Training Elite.

### 8.5 Theatre of Operations Research
Spies can only operate effectively in regions where the player has researched the corresponding Theatre of Operations (e.g., "Western Europe Theatre," "Southeast Asia Theatre"). Home region is included by default.

### 8.6 Spy Stack Abilities *(one ability active at a time per stack)*

| Stack Size | Ability |
|-----------|---------|
| 1 Spy | Reduces local resource production; reveals troop locations after 5-hour presence |
| 2 Spies | Intercepts communications (reading intercepted comms loses troop location intel) |
| 3 Spies | Damages/steals resources; damages infrastructure |
| 4 Spies | False flag communications |
| 5 Spies | False flag attack (simulates attack, attributes it to another player) |

### 8.7 Counter-Spy Stack Abilities

| Stack Size | Ability |
|-----------|---------|
| 1 CS | Wide-area passive spy detection |
| 2 CS | Post-action notification of spy activity in the area |
| 3 CS | Chance to disarm ongoing sabotage (see Trivia Mechanic below) |
| 4 CS | Non-specific alert that a false flag event occurred |
| 5 CS | Spy Hunter: homing beacon leads to target's state/province |

**Trivia Disarm Mechanic (3-CS Stack):**
When a 3-spy counter-spy stack is in the same state/province as active sabotage, a trivia challenge triggers. A game-related question appears with a 30-second timer and audible clock tick. Correct answer = sabotage disarmed, counter-spy survives. Wrong answer = sabotage succeeds, counter-spy is lost. Sabotage location is only revealed after the outcome.

**Spy Hunter Mechanic (5-CS Stack):**
- Homing beacon leads to spy's state/province.
- After 10 hours, if the spy is still in that region, stealth is lost.
- If the spy attempts to leave the region within 10 hours, they are caught at the border.
- On capture: spy is lost + 2 counter-spies from the stack are lost.

**Other Spy Detection Methods:**
- Direct contact with a counter-spy unit
- Running into a Platoon (27+ unit stack)

### 8.8 Economic Aid Treaties
Formal negotiated treaties with minimum value of 25,000 resources. Include payback periods and "forgiveness clauses" tied to diplomatic or military actions.

### 8.9 Alliance Dynamics
Alliances provide bonuses, with larger bonuses for neighboring nations. "Superpower" alliances incur a small penalty. Betraying an alliance has severe, permanent consequences.

---

## 9.0 Building, Development, & Infrastructure

**9.1 Victory Cities & Provincial Development:** Each nation starts with 7 "Victory Cities" with full building capabilities. All other provinces must first be "developed" at great cost and time before upgrading into new functional cities.

**9.2 Building Volume Cap:** Every city has a limit on how many buildings it can support, forcing specialization.

**9.3 Factory & Barracks Specialization:** Production buildings must be specialized at construction (e.g., "Aircraft Factory" or "Ground Vehicle Factory"). Cannot change specialization after construction.

**9.4 Advanced Building Requirements:** High-tier production buildings require support from a nearby Power Plant and Recruiting Office.

**9.5 Infrastructure Queue:** A separate queue in the city panel is used for linear projects like streets, railways, and landing strips.

---

## 10.0 Building Art Direction

### 10.1 Visual Style: Gritty & Utilitarian
Function over form is the absolute priority. Think mid-20th century industrial — concrete, corrugated steel, rust, soot. Every building should look like it was built to work, not to impress.

### 10.2 Factory (Industrial Plant) — Modular Design System

**Tier 1 — Industrial Plant (Core Mat'l production)**
- Foundation: Thick poured-concrete slab with visible cracks and stains
- Walls: Faded soot-stained red brick + corrugated steel panels with rust at ground level
- Roof: Flat tar roof with simple vents and pipes; sawtooth section with grimy glass panes
- Smokestack: Single tall brick-and-steel smokestack, light grey smoke animation
- Loading Bays: 2 roll-up metal garage doors, weathered; pallets/oil drums nearby
- Windows: Small steel-framed, wired safety glass, covered in industrial grime
- Weathering: Rain streaks, soot accumulation, aged surfaces throughout

**Tier 2 Upgrade:**
- Adds external network of pipes and conduits
- Larger storage tanks on the side
- Second larger smokestack comes online; smoke effect thickens
- 2 additional loading bays (4 total)

**Tier 3 Upgrade:**
- Large spinning ventilation turbines on roof (animated)
- Constant steam venting from multiple points
- Gantry crane animating over exterior storage yard
- Dedicated logistics wing addition
- 4 more loading bays (8 total) — the building looks industrial and alive

**Specialization Extensions (added at construction, permanent):**

*Ground Vehicle Factory (Armor Plant):*
- Massive wide garage extension with bay doors tall enough for heavy tanks
- Scattered tank treads, barrels, welding equipment near the new bay

*Aircraft Factory (Aerospace Complex):*
- Very tall vertical assembly building (VAB) — clamshell doors taller than main factory
- Small control tower element on roof

*Naval Production (Naval Yard):*
- Coastal-only specialization
- Drydock structure extending from factory into water
- Large cranes on the dock

---

## 11.0 Combat Command & Resolution

**11.1 Combat Initiation:** Initiated by direct player command (select unit → Attack → select target). Ranged units move into range and fire; ground units advance to make contact.

**11.2 Combat Resolution Cycle (Simultaneous Damage Model):**
- Combat is resolved in 30-minute in-game rounds.
- A "Force Strength" is calculated for each side based on all unit stats and active modifiers.
- Both sides inflict a percentage of their Force Strength as manpower casualties simultaneously. Battles are attritional; reinforcements can turn the tide.

**11.3 Absolute Modifiers:**
- ×2 Force Strength for Numerical Superiority (2-to-1 unit count)
- ×2 Force Strength for holding High Ground

**11.4 Special Action: The Ultimate Sacrifice**
Available to a 5-stack unit in a defensive position against overwhelming odds. Provides a massive temporary combat boost. Upon the unit's destruction: grants a national morale boost and causes a percentage of the surviving enemy force to go AWOL.

---

## 12.0 Factions & National Asymmetry

**12.1 Factional Blocs:**
- Eastern Bloc: Ground unit advantage
- Western Bloc: Air power advantage
- Island Nations: Naval advantage

**12.2 Advantage Scaling:** Bonuses start at 5% and increase with technology. Modified by national morale.

**12.3 Low-Economy Nation Bonuses:** Weaker nations start with free "Militia Guard" units on borders — powerful defensively for the first 5 days, then must be paid for or disbanded.

**12.4 Asymmetrical Alliances:** Alliances between weaker nations = large bonus. Alliances between superpowers = small penalty.

---

## 13.0 Unit Roster

| Category | Units |
|----------|-------|
| Infantry | Infantry, Motorized Infantry, Mechanized Infantry, Commando, Paratroopers |
| Ranged Support | Artillery, SP Artillery, Anti-Air, Mobile Anti-Air |
| Armor | Armored Car, APC, Light Tank, Medium Tank, Heavy Tank, Tank Destroyer |
| Air Force | Interceptor, Tactical Bomber, Strategic Bomber, Naval Bomber |
| Naval Fleet | Frigate, Destroyer, Cruiser, Battleship, Aircraft Carrier, Submarine |
| Special & C5ISR | Radar, AWACS, Sonar Buoy, Satellite |
| Civilian Logistics | Truck, Train, Air Freighter |

---

## 14.0 User Interface (UI) & User Experience (UX)

**14.1 Main HUD:** Top-of-screen bar displaying all resources with current stockpile and color-coded (green/red) net flow rate.

**14.2 Project Management:** Dedicated screen for planning construction, simulating economic impact, and implementing the plan with a 5% tax.

**14.3 Contextual Control Panels:** Side panel displaying relevant info and commands when a unit or city is selected.

---

## 15.0 Strategic Warfare & Consequences

**15.1 Nuclear Warfare:** Using a nuclear weapon is a last resort. The offending player's entire military is grounded and quarantined for 36 hours. All other nations receive a permanent +5% boost to their fortification defenses.

**15.2 EMP Warfare:** End-game weapon that destroys all aircraft and converts all land vehicles into basic infantry in a large radius, with significant friendly-fire penalties.

---

## 16.0 Territorial Defense Systems

**16.1 Shore Defense Perimeters:** Players can designate up to five 150-mile coastal stretches with a massive defensive bonus against naval invasion, which can only be negated by multiple successful spy missions.

**16.2 Coast Guard Reactionary Force:** A dedicated force assigned to a Shore Defense Perimeter.
- +50% Attack bonus while inside the perimeter
- +50% Speed bonus when deployed outside the perimeter

---

---

## 17.0 The Three Pillars — Honoring the Legends

Sacrifice does not try to be something new from scratch. It rewinds three of the greatest RTS games to their peak — the moment before each one fell — and fuses them into one. Every mechanic in this document traces back to one of these three DNA strands.

---

### 17.1 Command & Conquer: Red Alert 2 / Generals
**Peak:** 2001–2003 — before EA gutted the franchise.
**What it did better than anything:**
- Espionage was an actual weapon, not a footnote. Spies, engineers, infiltration — it changed the entire game state.
- Superpower asymmetry felt real. USSR played nothing like the Allies. Every unit had personality.
- Base building was a living economy — power grids, ore trucks, defensive rings. Lose your war factory, lose the war.
- The tension of the Allied vs Soviet standoff was the Cold War you actually wanted to fight.

**What Sacrifice takes from it:**
- The full spy/counter-spy system (Sections 8.0–8.9)
- Factional bloc asymmetry — Eastern, Western, Island (Section 12.0)
- Production building specialization — you build the factory, you pick the weapon (Section 9.3)
- The feeling that every building in your base is a vulnerability

---

### 17.2 StarCraft: Brood War
**Peak:** 1998–2010 — the game that defined competitive RTS. Still played at pro level in Korea.
**What it did better than anything:**
- Three completely different races playing three completely different games on the same map. No unit overlap. Total asymmetry.
- Macro and micro as separate, measurable skills. A better player could feel it in every exchange.
- The fog of war was a genuine strategic layer — scouting had real value, information was a resource.
- It was brutally honest. No hand-holding. No auto-pathing forgiveness. You earned every win.

**What Sacrifice takes from it:**
- Genuine asymmetric factions — no faction is just a reskin (Section 12.0)
- Fog of War as a strategic tool — spies and recon are how you see (Section 8.0)
- The stack/formation system rewards skill — knowing when to platoon vs fire team is micro (Section 7.4)
- Combat resolution rewards preparation — Force Strength model punishes careless engagements (Section 11.2)
- Veterancy — units that survive become harder to replace (Section 7.1)

---

### 17.3 Age of Empires II: The Age of Kings
**Peak:** 1999–2013 — still the most-played game in the series. The HD and DE releases proved it aged better than anything.
**What it did better than anything:**
- Every civilization felt historically grounded. The Mongols played like the Mongols. The Britons played like the Britons. The map shaped the strategy.
- The economy was a full-time job. You could lose a war in your farms and lumber camps before a single sword was drawn.
- Technology ages gave players a shared language — you knew exactly where the game was when someone said "Castle Age."
- It proved that a deep, slow-building strategy game could be both accessible and infinite in depth.

**What Sacrifice takes from it:**
- Real-world geographic economy — your region's terrain determines your starting resources (Section 4.2)
- Provincial development — you can't just build anywhere, you earn your cities (Section 9.1)
- Research tiers as pacing — the Logistics tree gates unit stack sizes just like AoE ages gate units (Sections 5.0, 7.4)
- The feeling that your nation has a personality tied to geography and history (Sections 11.0–12.0)
- The surrender/non-contiguous territory mechanic — territory logic matters (Section 3.3)

---

### 17.4 The Fusion — What Sacrifice Is That None of Them Were
No one game had all three. C&C had the espionage and faction flavor but shallow economy. StarCraft had the depth and asymmetry but no real-world grounding. AoE had the civilization depth and economy but no modern warfare or spy layer.

Sacrifice runs all three simultaneously:
- **C&C's espionage** operating inside **AoE's provincial economy** with **StarCraft's asymmetric faction depth**
- Real-world nations on a real-world map with real geographic resource logic
- Logistics is not optional — it is the game
- You can win or lose before the first shot is fired, in your supply lines and your spy networks

---

## 18.0 Phoenix OS Integration — System Architecture

Sacrifice is not just a Unity game. It is built on top of Phoenix-DevOps-oS, which means every subsystem in the OS is available to the game as a native capability.

---

### 18.1 Why Phoenix Changes What's Possible

Most games fight their OS. They beg for memory, negotiate with drivers, wrap everything in abstraction layers, and hope the scheduler doesn't kill them at the wrong moment.

Sacrifice is running on an OS that exists to serve it. The quad-kernel, the conductor, the sector architecture, the clone pool — all of it was built by the same hands that are building the game. There is no negotiation. The game is a first-class citizen of the OS.

---

### 18.2 Deterministic Simulation Engine

**Target:** Lock-step deterministic simulation at 60 Hz game logic ticks, network-synchronized across all players.

**How Phoenix enables it:**

The Phoenix OS quadralingual system runs four kernel slots simultaneously — VECTOR, NOSQL, RELATIONAL, TIMESERIES. The game maps these directly:

| Kernel Slot | Game Use |
|-------------|----------|
| VECTOR | Unit position, movement, collision, pathfinding |
| NOSQL | Game state snapshots, fog of war, spy intel layer |
| RELATIONAL | Economy, research tree, building dependencies, trade |
| TIMESERIES | Combat resolution log, event replay, veterancy progression |

Each game tick, all four slots commit their state in order. The conductor (`cpt_conductor.py`) sequences the commit. No slot can race ahead. This is the determinism guarantee — every player in the game runs the same tick in the same order on the same input hash.

**Replay and Anti-Cheat:**
Because every tick is logged to the TIMESERIES slot via usys, a complete game replay is a side effect of normal operation — not a separate recording system. The replay file IS the event log. Cheats that modify local state are caught because they break the commit hash.

---

### 18.3 Clone Pool as Asset Management

The usys clone pool (`/mnt/clonepool`) manages all game assets the same way it manages any file in the system:
- Every asset (unit model, texture, sound, map tile) is registered by filename → hex
- Version history is automatic — swap a tank model and the old one is in the pool, not deleted
- Sidecar JSON travels with every asset: resolution, LOD tier, faction, state (white/grey/black)
- Grey-state assets auto-hotswap when a replacement is registered — no manual pipeline maintenance
- QR headers on every asset file = physical inventory possible (print shop floor for the art team)

This means the art pipeline and the game pipeline are the same pipeline.

---

### 18.4 Sector Architecture Mapping

| Phoenix Sector | Game System |
|---------------|-------------|
| Sector 4 (system/core) | Simulation kernel, deterministic tick, conductor |
| Sector 3 (output/systemd corridor) | Renderer output, audio, network I/O, UI |
| Sector 2 | Multiplayer session management, matchmaking, lobby |
| Sector 1 (bridge) | Windows/Linux cross-play layer, save sync |

The engine bus (`bus.py`) carries all inter-system messages. The game renderer is a worker subscribed to the bus. The simulation is a worker publishing to the bus. They never talk directly — the bus is the contract.

---

### 18.5 The Rings — 16-Ring Event System

Phoenix runs 4 sectors × 4 coms rings = 16 rings. Sacrifice maps game events to rings by urgency and type:

**Sector 4 rings (core simulation):**
- Ring 1: Tick lock (deterministic commit gate)
- Ring 2: Unit state delta (move, attack, stack, die)
- Ring 3: Economy delta (resource flow, production, logistics buffer)
- Ring 4: Research/tech state

**Sector 3 rings (output):**
- Ring 5: Renderer command queue (draw calls, LOD decisions)
- Ring 6: Audio events (combat, ambient, UI)
- Ring 7: Network sync (player input hashes, anti-cheat)
- Ring 8: UI state (HUD updates, panel changes)

**Sector 2 rings (session):**
- Ring 9: Lobby/matchmaking
- Ring 10: Chat/comms (spy intercept system hooks here)
- Ring 11: Alliance/diplomacy events
- Ring 12: Victory condition monitor

**Sector 1 rings (platform):**
- Rings 13–16: Save, replay, OS integration, cross-platform bridge

---

### 18.6 Performance Target — What "As Real As Possible" Means

**Resolution & Frame Rate:**
- Target: 4K/60fps on mid-tier hardware (RTX 3060 class), 1440p/144fps on high-tier
- LOD system: 5 tiers managed by usys asset state — the clone pool knows which tier to serve per hardware profile
- Dynamic resolution scaling tied to simulation load, not frame pacing — the sim never drops ticks, only the renderer adapts

**Graphics Rendering Goals:**
- Global Illumination: Real-time GI via Unity's URP/HDRP pipeline — time of day lighting matters because night ops matter
- Unit fidelity: 50,000–100,000 poly models at close range, LOD steps at distance — the detail you need when you zoom in on your Spec-Ops in an urban firefight
- Terrain: MapTiler real-world data rendered as a living surface — elevation, water, forest density all visually represented and mechanically meaningful
- Destruction: Buildings degrade visually through their HP states — a bombed factory looks bombed. Fortifications show shell damage. Fires persist.
- Weather layer: Rain, fog, night — all affect unit visibility stats, not just aesthetics. Night vision certs are visible on units (green lens glow)
- Scale: Company-level engagements (200 units) rendered simultaneously without sim stutter because the renderer is decoupled from the tick via the bus

**The Standard:**
Every rendering decision is in service of the tactical read. If a player can't tell at a glance that those are Marines crossing a river vs Infantry getting penalized, the art has failed. Gritty and utilitarian means function-forward, not low-fidelity.

---

### 18.7 Prefetch & Deterministic Loading

Phoenix OS is deterministic with prefetch — Sacrifice benefits directly:
- Map regions are prefetched based on unit movement vectors — by the time your platoon reaches the next province, its assets are already in memory
- The OS knows your research queue — factory specialization assets are prefetched at research time, not at build time
- Replay scrubbing is instantaneous because the TIMESERIES slot is indexed — the OS already knows where every tick is

---

### 18.8 LifeFirst Integration (Future)

Once the LifeFirst app is complete, Sacrifice can hook into it for the player's partner/support use case:
- Laurie's scheduling/notification worker can send session reminders ("your game partner is online")
- The memory worker can log session outcomes, strategies, notes
- This is personal — the OS serves the people who built it first

---

## Appendix A: Art Asset List

### 3D Unit Models
- **Infantry:** Infantry, Motorized, Mechanized, Commando, Paratroopers
- **Armor:** Armored Car, APC, Light Tank, Medium Tank, Heavy Tank, Tank Destroyer
- **Support:** Towed Artillery, SP Artillery, Mobile Anti-Air
- **Air Force:** Interceptor, Tactical Bomber, Strategic Bomber, Naval Bomber, AWACS, Air Freighter
- **Naval:** Frigate, Destroyer, Cruiser, Battleship, Aircraft Carrier, Submarine, Supply Ship, Transport Ship
- **Civilian:** Logistics Truck, Train

### 3D Building Models
- **Civilian:** Industrial Plant (3 tiers × 3 specializations), Mine, Farm/Food Production, Power Plant, Recruiting Office, Satellite Uplink Center
- **Military:** Barracks (tiered), Armor Plant (tiered), Aerospace Complex (tiered), Naval Yard
- **Defensive:** Bunkers, Fortifications, Anti-Air Emplacements, Radar Station
- **Strategic:** Secret Facility, Missile Silo

### 2D UI & Icons
- **Resource Icons:** Money, Metal, Wood, Oil, Gas, Food, Core Mat'l, Population, Fuel
- **Command Icons:** Attack, Move, Patrol, Stack, Sacrifice, Spy Operations
- **Unit & Building Icons:** Unique 2D icon for every unit and building (queues, management screens)
- **Faction Flags/Symbols:** For each playable nation
- **Technology Icons:** Unique icon for each researchable technology
- **General UI:** Buttons, frames, menu backgrounds, pop-up windows

### Visual Effects (VFX)
- **Combat:** Muzzle flashes, missile trails, torpedo trails, explosions, smoke/fire on damaged units
- **Strategic:** Nuclear detonation (mushroom cloud + shockwave), EMP blast
- **Environmental:** Building destruction animations, dust clouds from vehicle movement
