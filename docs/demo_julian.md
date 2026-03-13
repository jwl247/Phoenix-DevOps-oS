# Phoenix Demo — Julian
**Tonight's goal:** Show the engine under Sacrifice. Get Julian's machine running.

---

## The Hook (say this before you touch the keyboard)

> "You know how every RTS game — Red Alert, StarCraft, AoE — eventually just slows down when the map gets big and the battles get large? Units start rubber-banding, the AI cheats because it can't actually compute, late game becomes a slideshow. That's not a graphics problem. It's an architecture problem. The engine can't keep up with its own simulation.
>
> What we built is the engine that doesn't do that. Four separate kernels, each one owns a different class of work. Physics in one. Network in another. Economy in another. AI in another. All running simultaneously. The game is built on top of the OS, not on top of Unity or Unreal. There's no middleman taking a cut of every frame."

Then open a terminal.

---

## Act 1 — The Kernel Pipeline (5 min)
*This is the engine. Show him what's underneath the game.*

```bash
cd /mnt/c/users/jwlef/PhoenixDevOps/sector4
python3 conductor.py
```

**What he'll see:** All 4 kernel slots processing packets. Physics → slot 0 (VECTOR). Network → slot 1 (NOSQL). Economy → slot 2 (RELATIONAL). AI → slot 3 (TIMESERIES).

**Say:** "Every unit action in Sacrifice goes through this. A spy infiltrating a factory — that's a TIMESERIES event hitting slot 3, a RELATIONAL update hitting slot 2 for the economy hit, and a VECTOR update for the physics of the infiltration animation. Three kernels, one action, zero waiting on each other."

---

## Act 2 — The Signal (3 min)
*Show him a packet being born and dying.*

```bash
python3 freewheeling_stage.py
```

**What he'll see:** PCS hash generated, 3-call lifecycle, snap-clone fires.

**Say:** "This is a PCS — Probabilistic Commit System. Every signal in the game gets one at birth. That hash never changes. It's the signal's identity from the moment a unit gets an order to the moment it's resolved and logged. We can replay any moment in the game from these. That's how the audit trail works. That's how replays work. It's not bolted on — it's structural."

---

## Act 3 — Benchmark (20 min)
*Let the machine prove itself.*

```bash
cd /mnt/c/users/jwlef/PhoenixDevOps
bash benchmark/run_benchmark.sh baseline
```

While it runs, explain the 4 conditions:
- **Baseline** — idle machine, what's the floor?
- **Normal** — realistic background load
- **Stress** — saturated, every core pegged
- **Red Line** — the Sacrifice game condition. 200-unit company. All 16 rings active. Spy + economy + combat simultaneous. This is what the engine has to survive at launch.

When baseline finishes:
```bash
bash benchmark/run_benchmark.sh redline
```

**Say:** "Red Line is our name for the condition where someone's running the biggest possible Sacrifice game. 200 units, full economy, active spy network, active combat on multiple fronts. If the kernel latency stays under target under Red Line, the game ships. That's the pass/fail line."

**Benchmark targets to watch:**
| Slot | Should be under |
|------|----------------|
| physics (slot 0) | 1ms avg |
| network (slot 1) | 2ms avg |
| economy (slot 2) | 5ms avg |
| ai (slot 3) | 10ms avg |

---

## Act 4 — The File System (5 min)
*Show him usys — the part that makes this a real OS layer.*

```bash
usys list
usys register sector4/conductor.py conductor
usys info conductor
```

**Say:** "usys is like apt but for any file, any type, any language. You register a file, it gets a hex identity, a version history, and you can hotswap it live — no restart. The game uses this for asset management. A texture, a unit behavior script, a balance patch — they all go through the same pipeline. You can roll back any of them independently."

Show the clone pool intake:
```bash
usys intake sector4/pcs.py pcs white "PCS core — probabilistic commit system"
ls /mnt/clonepool/
```

**Say:** "Every file that enters Phoenix custody gets a QR code. Two of them — one for state (white/black/grey), one for location in the tier system. The game's asset pipeline runs on this. When we patch a unit's stats, the old version goes grey and auto-hotswaps. Zero downtime. The game doesn't restart."

---

## Act 5 — The Game (5 min)
*Paint the picture. You don't have to show code for this part.*

Pull up `game/sacrifice/GDD.md` and flip to the three pillars section.

**Say:** "Three games. Red Alert 2 at its peak — the espionage layer, the spy game inside the war game. StarCraft Brood War at its peak — asymmetric factions, units that reward mastery, micro that actually matters. Age of Empires II at its peak — geographic economy, you win or lose on logistics before the first battle. We're not making a clone of any of them. We're taking the one thing each one got absolutely right, and building a single game that has all three."

Then:
> "The difference is the engine underneath. Those games ran on 2001 hardware with 2001 architecture. We're running on Phoenix. The simulation doesn't cheat. The AI doesn't get free resources. The replay is lossless. The late game doesn't slow down. That's the pitch."

---

## If Julian Wants to Run It on His Machine

```bash
# On Julian's PC — WSL2 setup (if needed, one reboot)
wsl --install

# After reboot, in WSL:
sudo apt-get update
sudo apt-get install -y sysbench php-cli python3-pip git sqlite3
pip3 install py-spy --break-system-packages

# Get the repo
cd /mnt/c/users/<julian>/
git clone <repo>
# or: copy PhoenixDevOps folder via USB

# Bootstrap his node
cd PhoenixDevOps
bash scripts/bootstrap_node.sh julian <your_ip>

# Run the benchmark
bash benchmark/run_benchmark.sh all
```

His numbers vs your numbers = the first cross-node comparison. If his machine beats yours on slot 0 but yours beats his on slot 3, that tells you something about workload distribution across nodes.

---

## The Close

> "What we're building is the infrastructure for a game that couldn't exist before. Not because the ideas are new — the ideas are 25 years old and proven. Because the engine to run it didn't exist. Now it does."

If he's in, the next conversation is: what does he want to build on it?
