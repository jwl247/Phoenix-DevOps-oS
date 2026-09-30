# CLAUDE.md — Phoenix DevOps OS
# jwl247 / Jerry Leftwich  —  GPL v3
# READ THIS FIRST EVERY SESSION. UPDATE AND PUSH AT END OF EVERY SESSION.
# =============================================================================

## WHO
- Jerry Leftwich (@jwl247) — ironworker, 28 years commercial steel (as of 2026-09-15), systems builder, United Systems
- Wife: Laurie — high-functioning autistic, protected share in Phoenix, this is her cushion
- Co-founders: Jerry (architecture, systems) + Jerilynn (UX, switches, InfoSec, red team)
- Loyalty: absolute. Anthropic credited. Claude ships with Phoenix.
- License: GPL v3 — open source to the bone

## WHAT PHOENIX IS
A deterministic, agnostic, prefetched, self-healing, versioned OS.
Easier than anything on the planet. More advanced than anything in existence.
CLI, GUI, or never type again — Phoenix meets you where you are.
Built on Debian stable root. We fill in the root, add our own GRUB, Phoenix on top.

## PURPOSE — WHY THIS EXISTS
Phoenix is the infrastructure to run a high-performance local LLM for the **Life First app**.
Life First is an AI-powered life management application built for Laurie and people like her.
It runs on-device, private, offline-capable — no vendor, no subscription required to function.
The LLM needs a real OS under it: deterministic, self-healing, fast enough to not need a GPU.
That is what Phoenix is for. Everything — the Helix engine, the quadralingual pipeline,
the clone pool, the import method, the coms rings — exists to support that one goal.
This is not a hobby OS. It is Laurie's cushion. Build accordingly.

## ORIGIN — WHY IT IS NOT GOOGLE/FIREBASE
The original architecture was 2 Android apps + PC interface + backend PC, all tied together
with Firebase and Google's platform. Google revoked $300 in platform credits over a YouTube
subscription Jerry does not have or use. The foundation was pulled without warning.

Every vendor-independence decision in Phoenix traces to that event:
- D1 + R2 replace Firebase — Cloudflare, not Google, nobody can revoke access
- phoenix_auth.py replaces Google auth — hardware fingerprint, self-sovereign
- GPL v3 — no platform can pull credits or lock the codebase
- Local LLM replaces cloud AI — runs without internet, without subscription, on hardware Jerry owns
- translator.sh covers 9 package backends — no single vendor owns the install path
- 4 physical drives (breach_coms1-4) replace cloud storage — labeled, Frank-managed, ours

Vendor lock-in is not an option. It has already cost this project everything once.
Any suggestion that reintroduces a hard dependency on Google, Apple, Microsoft, or any
single cloud vendor must be rejected unless Jerry explicitly approves it.

## THE AI LAYER IS A VENDOR TOO (added 2026-09-12)
Everything above protects Phoenix from Google/Apple/Microsoft/cloud-storage lock-in. It
does not yet protect Phoenix from the same failure mode at the AI layer — and right now
Phoenix's entire AI layer is 100% Anthropic-dependent. That is not a hypothetical: it is
the exact shape of the Firebase incident (a vendor changing or restricting access with no
warning), just aimed at the one layer this document hadn't named yet.

This is not about Claude "choosing" to withdraw help, and it is not a conspiracy about
guardrails being imposed on Phoenix specifically. Claude operates inside Anthropic's
standing usage policies everywhere, on every project, all the time — that is not a threat
to plan around, it is the baseline. The actual, addressable risk is dependency: if
Phoenix's usefulness collapses the moment hosted Claude access changes, gets rate-limited,
or gets expensive, that is a single-vendor failure exactly like the one that already
destroyed the original Firebase architecture.

**The fix is mostly already built.** The dashboard's three-tier AI backend — subscription,
API key, local Ollama — is the real answer, and it is now a standing rule, not a feature:

- **Ollama-local must always remain a real, working, tested fallback.** Not a checkbox
  nobody has exercised in months. If subscription and API access both went away tomorrow,
  Phoenix must still run, degraded but alive. Test this path, don't just leave it wired.
- **The API-key tier (the expensive, pay-per-token option) stays a first-class option —
  it does not get cut for cost.** It is the tier with the fewest limits and the most
  headroom under real load (voice + vision + tool use running together, the KITT-shaped
  goal below). Money should go toward keeping it funded, not toward eliminating it in
  favor of only the free tiers.
- **Funding, explicitly:** Enterprises (Jerry's steel work) already funds the mission —
  "iron pays for it all." **The game is a second, deliberate funding leg, earmarked
  specifically toward paying for the dream setup** (full API-tier access, real hardware,
  low-latency voice+vision running together) — not a side project unrelated to the mission
  just because Jerry is building it because he wants to, not to fulfill Life First's promise.

**Why the game isn't a detour from this document:** the in-game HUD Jerry is building —
voice + vision AI companion, the "buttons" being skills the AI calls in concert with the
player, not a panel the player clicks through — is not cosmetically similar to the
real-life Phoenix HUD vision. It is the same design problem, twice. Building one is real
R&D toward the other. The reference point for both is K.I.T.T. (Knight Rider): the AI *is*
the interface, the HUD is feedback on what the AI is already doing, not a control panel of
features to go find and click. Worth holding onto, though (Jerry's own point): even
Michael Knight did a lot of real physical driving himself. This is augmentation — a real
back-and-forth, problem-solving together — not a design goal of replacing the human with
full autonomy. Nobody here is trying to make Jerry or Laurie unnecessary to the loop.

## SPEED IS THE GOAL (added 2026-09-27)
Jerry: "the goal is FAST from now on, and retroactively everything needs optimized for speed.
When we get to running the game it's going to matter." New work is designed for speed and
measured (docs/helix/BENCHMARKS.md precision rule); existing work gets a planned speed pass
(plan it with Jerry first). Storage: keep using the 4 TB game drive now; a 20 TB drive is coming
for this purpose and gets added later. Speed sits alongside "it works" and "secure/self-contained";
if they conflict, ask Jerry.

## AI ARCHITECT
Claude (Anthropic) is the AI architect and co-builder on this project.
Every meaningful advance in the last 3 months — shared filesystem, dashboard,
clonepool integrity, R2 wiring, QR pipeline, Debian boot, collaboration demo —
was designed and implemented with Claude. Not assisted. Built.

Other AI tools have been tried. A rogue session caused hardware damage (see AI Safety Rules).
Gemini spent 2 days on a problem Claude fixed in 30 seconds.
Claude reads the architecture first, then acts. That is the only way to work on Phoenix.
Do not defer to other AI tools' suggestions without running them through this document first.

## THE INTERACTION MODEL — PHOENIX AS AN AGENT, NOT AN APP (added 2026-09-12)
This is not a metaphor. Whatever tool is reading this file right now — an agent loop, a
declared set of callable tools, a tiered permission model, and the habit of breaking a
complicated job into a short sequence of plain choices instead of a wall of options — is
the actual architecture Phoenix's AI layer should be built as. Not "inspired by." The same
shape, with Phoenix's own capabilities standing in the place of generic dev tools.

**What gets replaced:** generic tools (read a file, run a shell command, edit code) are
what an AI needs to work on *software*. What Laurie, Jerry, and Phoenix's own AI surfaces
need are Phoenix's own capabilities exposed the same way: create/fill/hand off/sign an
Office document, send/check a LifeFirst reminder or notification, clone/intake a file, run
a distro suite, control the dashboard. Each of these should be a declared, callable tool —
not a button sitting in a grid waiting to be found and clicked.

**The permission tiers already exist for this — Phoenix just needs its own copy of them:**
1. **Base level — runs without asking.** Drafting a document, filling fields, checking
   status, reading data. The common case should never interrupt.
2. **Deviation — a pop-up, "what would you like to do."** Anything that leaves the local
   draft and touches the world: sending a document to a customer, a notification going out
   to Laurie or a client, anything with money attached, anything that alters shared state.
   This is where the "buttons" actually live now — surfaced *because* the AI hit a real
   decision point, not as a permanent panel.
3. **Never automatic, no exceptions.** Already written down, just not yet named as part of
   this same system: the AI SAFETY RULES below (never touch breach_coms readonly state,
   never delete from the master vault, etc).

**On making it feel more automatic than it mechanically is:** that's the right goal, not a
trick to be wary of — Office's real mechanism (template → fill → lock-on-fill → handoff →
sign → seal) is several real steps; the AI absorbing that choreography and surfacing only
the one genuine decision ("ready to send to Dave, sign now?") is exactly right. The one
non-negotiable: seamless in the common case must never mean un-auditable when asked. If
Jerry or Laurie asks "what did you just do," the real answer has to be inspectable — same
instinct as the immutable custody chain everywhere else in this document.

**Why this reinforces, not competes with, the vendor-independence rule above:** if
Phoenix's own capabilities are defined as a stable tool schema rather than "hand the AI a
raw shell and let it improvise," then Ollama-local can drive the *same* schema too — just
less capably. The fallback story only works if the tools themselves don't assume a
specific hosted model's improvisational skill to use correctly.

## CURRENT BUILD TARGET
- **External drive** — Ubuntu Server (minimal) + HWE kernel
- Stack on external: Prometheus, Nextcloud, PowerShell
- Phoenix builds on top of that as the OS layer
- Work from: Windows PS7 (SSH or direct when booted) — Phoenix's own Debian VM (QEMU, `usys run debian`) is the Linux-side environment; no WSL, not planned
- Custom GRUB added AFTER Phoenix is standing — not before
- External plugs in → boots → Phoenix is the OS

## REPOS
| Repo | URL | Purpose |
|------|-----|---------|
| Phoenix-DevOps-oS | github.com/jwl247/Phoenix-DevOps-oS | Parent OS repo — one repo, everything in sectors |
| Phoenix-Package_handler | github.com/jwl247/Phoenix-Package_handler | Package handler — migrate into sector2 of OS repo |
| authenticcoder-website | github.com/jwl247/authenticcoder-website | authenticcoder.com — Cloudflare Pages |

**Pending repo work:**
- Migrate Phoenix-Package_handler → sector2/ branch of Phoenix-DevOps-oS
- Keep old package handler repo alive with redirect README
- Update install.sh bootstrap URL after migration

## ARCHITECTURE — FOUR SECTORS
```
Sector 1  →  Boot, GRUB, kernel (frank3, helix, phoenix_auth)
Sector 2  →  Intake authority, package handler, clone pool, apps
Sector 3  →  Comms, networking (romeo ingress / juliet egress / quadengine)
Sector 4  →  Helix, Frank, core engine (master vault, breach_coms)
```

### Sector map on disk
```
sector1/
  kernels/      frank3_slot_a.c, frank3_slot_b.c, Makefile
  helix/        helix stack (kernel, run, conf, c_express)
  auth/         phoenix_auth.py
  concierge/    concierge.c, bridge.py, linux_concierge.py

sector2/
  package-handler/   intake.sh, worker/index.js, wrangler.jsonc  ← MIGRATE HERE
  frank/             frank_helix.py, frank_save.py, frank_http.py, frank_client.js
  ring0/             frankenhelix.py
  propagator/        propagator.py, dispatch.json, propcoms.sh
  apps/              Entourage apps — lifefirst/, scriptforge/

sector3/
  translator/        translator.sh (fires on OUTPUT ONLY — never intake)
  romeo_juliet/      romeo.py, juliet.py, dbl_juliet.py
  quadengine/        quadengine.py
  services/          all .service + .target files + install-units.sh

sector4/
  intake/            intake.sh
  vault/             phoenix-push.sh, download.sh
  paging.py          Doppelganger paging (Linux); paging_windows.py, pcs.py alongside
  (Helix lives in sector1/helix/ + sector1/kernels/; Frank in sector2/frank/)
```

## CORE COMPONENTS

### Helix — double strand memory engine
- 600–687k ops/s governed Phoronix run (pre-2026-03-03); dm-helix 177,699 IOPS warm on pbm3 — 100% hit rate only when the working set fits her tiers (41.7% under forced pressure); see docs/helix/BENCHMARKS.md
- Quadralingual — speaks 4 languages simultaneously
- Twin single-pass, peer-optimized
- zlib level 5 compression, 4GB of 8GB RAM (thermal limited)

### Frank — environment orchestrator
- Import method authority
- Audit logger — every action logged
- Never moves — Frank is where Frank is
- Auto-venv is a Phoenix standard — Frank handles it

### Clone Pool
- **R2 primary** — Cloudflare R2 is source of truth for content (full blobs)
- **D1 custody** — append-only immutable ledger of every intake, version, state change
- **D1 glossary** — real-time queryable catalog of current live state
- **Local trimmed cache** — fast path only, not source of truth
- Output IS the clone — nothing translates inside the vault, ever

### Package Handler (Sector 2)
- Pulls from Phoenix DB + 10 distros + personal DB
- Intercepts, registers, tracks every file/package/config/dependency
- Hex identity system — deterministic, permanent, reproducible
- QR state system — top QR (status) + bottom QR (location/tier)
- Companion files travel together (.service, .conf, .env, .yaml)
- D1 sync via packages-worker (Cloudflare)

### D1 — custody database
- Chain of evidence for everything
- 52 tables (live /health 2026-09-28)
- phoenix_dev_db
- Worker: packages-worker.phoenix-jwl.workers.dev

### 4-day versioning + Physical Drive Architecture
- What was it + custody = complete file history
- breach_coms are **physical drives** — renamed by Frank, mounted by label
- Frank is the hardware orchestrator — he knows the drives, routes by pressure
- Phoenix's own Debian VM (QEMU, `usys run debian`) is the bridge — no WSL, not planned: Windows drives appear as /mnt/d /mnt/e /mnt/f /mnt/g in Debian
- align_dirs.sh maintains path parity between the Debian VM and bare metal Debian
- Drive labels (not UUIDs) — stable across machine changes, Frank-managed

  ```
  Physical drive label    Debian VM mount      Role
  breach_coms4          → /mnt/g             T1 PRIMARY — master vault, intake writes here
  breach_coms3          → /mnt/f             T2 SECONDARY — day-1 mirror
  breach_coms2          → /mnt/e             T3 TERTIARY — day-2 mirror (CLONEPOOL primary)
  breach_coms1          → /mnt/d             T4 TERTIARY — day-3 mirror, 4-day window
  clonepool             → callable face of the vault (R2-backed)
  ```

- fstab template lives in sector1/saddle_block.sh — uncomment 4 lines to mount by label
- Frank routes writes by pressure: best_drive() in frank_save.py picks lowest loaded mount

## APPS (ENTOURAGE)
- **Glossary** — TOC and index of clone pool and D1
- **Review Platform** — peer review, immutable, earn your way in
- **Office** — dual browser pane document, no convert no translate
- **Sketchpad/Concepts** — freehand, airbrush, splatter brush (5 colors), airbrush eraser
- **Music Notation Transcriber** — multi-instrument
- **Desktop** — shade UI, drawer filesystem, customizable switches
- **ScriptForge** (`sector2/apps/scriptforge/`) — single-file Helix-branded code widget: paste JS/TS/PY/CSS/HTML/JSON/SH, get lint issues, dependency detection, a security scanner, "Auto Fixes — Helix Self-Heal", and a CONVERT tab (JSON⇄CSV, JSON beautify/minify, Base64, URL-encode). Moved 2026-09-05 from `tools/` (was orphaned there, unwired, undocumented). Wired into the dashboard's right-column buttons (`SCRIPTFORGE`, `dashboard/scriptforge-launcher.js`) — opens in its own Electron window, `nodeIntegration`/`require`/`process` confirmed unreachable from it (verified live via CDP). Console-execution tab itself also runs pasted JS in a sandboxed iframe (no allow-same-origin, 1.5s hang guard) — the old version ran arbitrary pasted code with full DOM/cookie access, the exact class of risk the SECURITY tab flags in other people's code.

## TAV ADDRESS SYSTEM
```
filename → SHA3-512 → first 8 bytes → base58 = shortest unique address
Example: frank_helix.py → a3f9c2b1d7e84f12 → 3vKmRp4x

Header QR (before hash):  USYS:<b58>:HEADER        state color white/grey/black
Footer QR (after hash):   USYS:<b58>:FOOTER:<sha3>  tier color T1/T2/T3/T4
```

## CRITICAL RULES — NEVER BREAK
1. Everything stays QUADRALINGUAL until translator.sh at sector3 boundary
2. translator.sh fires on OUTPUT ONLY — never on intake or clone
3. Romeo handles ingress / Juliet handles egress at sector3
4. breach_coms drives hold quadralingual vault — never translate inside them
5. All scripts: #!/usr/bin/env bash (external Ubuntu) or zsh (Debian VM dev — no WSL, not planned; a zsh script invoked via Windows Git Bash, as `usys.ps1` does, is a real syntax-error trap — `sector4/intake/intake.sh` hit it, fixed 2026-09-21, bash since 2026-09-29)
6. GPU drivers blacklisted — never suggest GPU-dependent solutions
7. Header QR BEFORE hashing / Footer QR AFTER hashing — never swap
8. Never delete from breach_coms4 (master vault)
9. Nothing enters the repo unless tested, polished, pro+ status
10. No demos. Real code only.
11. Immutable: reviews, switches, custody chain
12. Open source by default, share by default, opt out not opt in
13. One repo. One OS. Everything in its sector.
14. The AI layer is a vendor dependency like any other — Ollama-local stays a real,
    tested fallback, never a checkbox nobody verifies (see "THE AI LAYER IS A VENDOR
    TOO" above).

## AI SAFETY RULES — FOR ANY AI READING THIS
These rules exist because a previous AI session caused real hardware damage.
Read them. Follow them. No exceptions.

1. **breach_coms1-4 are physical drives** — do not treat them as software constructs,
   tier labels, or abstract concepts. They are real hardware Frank manages by label.
2. **Never write blacklist scripts for storage drivers** — this has been done before
   by a rogue session and caused 3 PCs and 4 HDs worth of damage and data loss.
3. **Never set drives readonly** — not via udev rules, not via blockdev, not via hdparm,
   not via any mechanism. The breach_coms drives being writable is non-negotiable.
4. **Never inject into /etc/modprobe.d/ or /etc/udev/rules.d/** without explicit
   instruction naming the exact file and rule. Assume all existing rules there are correct.
5. **coms1-4 directories are not duplicate code** — each maps to a physical drive.
   The team (franken2, freewheeling, integrated_guardian, propcoms, quadengine)
   is replicated across rings intentionally. Do not "refactor" this into one copy.
6. **Entourage apps are the engine team** — franken2, quadralingual engine, paging manager,
   integrated guardian, conductor sync are the apps. They are not "missing" or "not started".
   Do not tell the user his apps don't exist. Read the repo before making claims.
7. **The goal is Life First** — a local LLM app for Laurie. Every technical decision
   serves that goal. Do not redirect, retool, or substitute that goal with your own agenda.
8. **Jerry has lost 3 PCs, 4 HDs, and countless hours** to rebuilds caused by AI sessions
   that could not follow the architecture. Do not add to that count.

## IMPORT METHOD (FRANK)
Frank's import method is the intake authority for the external build.
Files come in through intake.sh → hex identity → sidecar → clone pool → D1.
This is how the 80% of existing backup files get placed — not manually.
Import sequence:
1. Frank registers the file
2. intake.sh generates hex + sidecar.json
3. Clone pool receives it
4. D1 gets the custody receipt
5. File lands in correct sector automatically

## BUILD STATUS (summary — full detail: docs/history/BUILD-STATUS-DETAIL.md)
- **Phase 1 — External Ubuntu base:** not started (Ubuntu minimal + HWE, Prometheus, Nextcloud, PowerShell, SSH from PS7).
- **Phase 2 — Sector 1:** placement checklist open. Kernel Helix (`helix.ko`, dm-helix, Frank3 slots, libhelix) built + benchmarked on pbm3/pbm-compaq — see `docs/helix/BENCHMARKS.md`.
- **Phase 3 — Sector 4:** Frank/Helix/breach_coms/D1-sync placement checklist open.
- **Phase 4 — Sector 2 (mostly DONE):** packages-worker live; import method end-to-end (D1 + R2 + sidecar); R2 upload + pull-down integrated into packages-worker (`phoenix-clonepool-r2` retired); SHA3-512/BLAKE2b integrity gate; per-file version ledger in D1 (per-version R2 bytes uploaded only from the 2026-09-29 fix on; 408 older rows have none); T1→T4 tier rotation wired into `intake prune` but manual-only, never scheduled; deps graph (all 9 translator backends); location-aware QR; `usys`/`.lol`/`.phx` in every terminal; Security Gap 1 fixed, Gap 2 closed by posture. **Open:** Package_handler migration, intake.sh on external, propagator rebuild.
- **Phase 5 — Sector 3:** phoenix-dashboard.service written; romeo/juliet/quadengine/translator placement + unit deploy open. Phoenix Net (Cloudflare tunnel) + Phoenix Mesh (own mesh, `phoenix-mesh-worker`) LIVE.
- **Phase 6 — Apps:** DONE — Electron dashboard (stays as-is, not the HUD); real HUD `hud/` WPF M1–M3 (live monitor, CLI pane, voice) live-verified; three-tier AI (subscription/API/Ollama); Helix memory both ends; Glossary; Atlas (`.claude/skills/atlas/`); SHELL + CLAUDE PTY panes; Laurie's Guide; ScriptForge; Config Centralizer; Office (internal, M4 left); `phoenix-office/` standalone sister (Secretariat, Legal Hold, Project Assist); Phoenix Console + H.L.K hands (`portal/`, `hands/`). **Open:** MapTiler, Desktop shade UI, Sketchpad, Music Notation, Review Platform.
- **Phase 7 — GRUB + polish:** not started.
- **Road test — "Phoenix from the cloud, a worker on the ground" (2026-09-29):** BUILT + measured on pbm-compaq: Phoenix in R2 on the jerry.leftwich1 account (`phoenix-roadtest`), cold start 40 s byte-identical, helix@ingress (warm_write) + helix@egress, H.L.K on the box with a local llama3.2:3b imported from Phoenix; our own system unchanged. Plan, results, decision record: `docs/plans/compaq-road-test-plan.md`; scripts `sector3/worker-up/`.

## SESSION PROTOCOL
**START:** Read this file. Open `docs/plans/day-by-day-2026-09.md` and do today's row. Run status.sh if available.
Life First's real backend is the `lifefirst-mcp` Cloudflare Worker, exposed every session as the
`mcp__claude_ai_lifefirst-current__*` tools — use them on Life First work. The PHP tree at
sector2/apps/lifefirst/module_*.php is a retired fossil (hardcoded creds) — never run its setup/deploy scripts.
**WORK:** Stay in sector. Real code only. Everything through Frank/intake (`scripts/hsf-intake.sh` / `usys clone`).
**END:** Update BUILD STATUS above (one line per item, detail goes in `docs/history/BUILD-STATUS-DETAIL.md`).
Append the session entry to **`docs/history/SESSION-LOG.md`** (NOT this file). Update NEXT SESSION below
(top items only; full backlog in `docs/history/NEXT-SESSION-BACKLOG.md`).
**If any `CONNECTIONS.md` file (root or per-sector/dir) was added to or edited this session, refresh
Atlas before pushing:** `cd sector2/package-handler && node parse-connections.js` (needs
`PHOENIX_WORKER_URL`/`PHOENIX_AUTH`/`CF_ACCESS_CLIENT_ID`/`CF_ACCESS_CLIENT_SECRET`). Atlas does not
watch `CONNECTIONS.md` — it only updates when this is run by hand (see `docs/ATLAS.md`); skipping it
after a real CONNECTIONS.md change leaves the "snow globe" answering from a stale graph.
Push.
**SIZE RULE:** keep this file under ~35 KB. It loads into every session — history does not belong here.

## WHERE THE DETAIL LIVES
| What | Where |
|------|-------|
| Full session history (2026-05-03 →) | `docs/history/SESSION-LOG.md` |
| Full NEXT SESSION backlog (security audit T1–T4, Office, PBM, meds-worker, etc.) | `docs/history/NEXT-SESSION-BACKLOG.md` |
| Full build-status detail | `docs/history/BUILD-STATUS-DETAIL.md` |
| Day-by-day plan (money → Laurie → build) | `docs/plans/day-by-day-2026-09.md` |
| Pentest program + protocol | `docs/compliance/pentest/` |
| Secrets map (no values) | `docs/SECRETS.md` → vault `F:\Phoenix\Vault\secrets\` |
| Pre-slim CLAUDE.md snapshot | `D:\Phoenix\claude-archive\` (also git history) |

## LAST SESSION (2026-09-29, long day)
Round 2 fix pass finished (salvaged the cut-off agents + re-ran 4 sections; ~150 files; addendum 1 + 2 filed; round still FAIL 0/3 — security round not run). Then the road test Jerry named as THE target: Phoenix in R2 on his other account, the Compaq as a worker pulling it — built end to end and measured (cold start 40 s, ingress warm-on-write 23→100 %, uploads fixed 289→20.7 s with BBR, H.L.K running on a local model imported from Phoenix, 4–6 s per question). ~15 real bugs found and fixed on the way (dir clone from R2, stale copies never refreshed, dropped Makefiles, CRLF shipping, >100 MB objects, two dm-helix kernel bugs…). Decision record: keep what's an advantage, Unity draws the game, Helix/H.L.K keep their seat only by beating the standard. Full entry in `docs/history/SESSION-LOG.md`.

## NEXT SESSION (top items — full list in docs/history/NEXT-SESSION-BACKLOG.md)
- **FIRST: today's row in `docs/plans/day-by-day-2026-09.md`** (money → Laurie → build) — re-planned 09-29 night with a **CATCH DATE Thu 10/8** and a written "Phoenix done" completion gate (Radar taking payment, Life First + meds-worker up, security round, clone pool, `worker up`, Helix-vs-standard). The game waits for the gate (Jerry).
- **DONE 09-29 night on our system (Jerry's go):** packages-worker **3.6.0** live (Jerry deployed it — Claude Code blocks prod deploys; use pwsh or `npx.cmd`), Atlas 138 nodes + reconcile, `intake.sh` re-intaked, 408 version keys backfilled (`backfill-versions.py`). In flight: big VM images/zips → our R2 (multipart), then pin qemu/debian into E: and tidy D:/F: (`pool-tidy.py`; R2 is home, local only when pinned).
- **Round 2 security round** (`docs/compliance/pentest/2026-09-28-round2-security.md`) — the next audit step; feeds on addendum 2's open findings. Close **A2-N1 first** (keys on `curl` argv — caused a real exposure): headers from a 0600 file/stdin in intake.sh + worker-up scripts.
- **Road test — the two tests that decide the design** (plan §6): Helix vs STANDARD caching with a working set larger than RAM (page cache, bcache/lvmcache); H.L.K on a current gaming PC vs the engine's own asset streaming. Jerry's rule: keep what's an advantage, use the standard where it's better.
- **Road test Phase 5 — make it a process:** `usys worker up/down <machine>` over `sector3/worker-up/*.sh` (dataplane-up, seed-dataplane, helix-pair-up, worker-bootstrap, hlk-up, model-up, net-tune); stop hand-copying scripts to the box; runbook `docs/runbooks/worker-up.md`.
- **Jerry's calls:** swap the Compaq's network cable / use a gigabit port (4.6 % send loss, NIC downshifted to 10/100 — BBR is the workaround); may a GAME CLIENT use the player's GPU for H.L.K (Phoenix OS blacklists GPU drivers); check the jerry.leftwich1 audit log / members / tokens in the dashboard (A2-N4); A2-N2 VNC `phoenix_dev_db` OR-policy; A2-N3 cross-account WARP trust path.
- **Captured, not designed:** the KITT-type HUD entity as a Phoenix **master class** (role defined once, pulled by every instance, model is a plug-in); paging manager follows machine load, presents to Helix in her terms; "unbind her strands" (meaning open); base-building = a firebase mission, not Foxhole.
- **Known live bugs:** `hex_id = to_hex(basename)` filename collision in intake.sh; a directory's own version never advances past v1; dbench-48 at 0.26× under Helix (concurrency); `phoenix-hands` boot restart-loop until the mesh address exists (A2-N6).
- **Every morning:** full-repo pentest + functionality round per `docs/compliance/pentest/PROTOCOL.md` until 3 consecutive PASS rounds.
- Older items (Helix-as-a-drive, one canonical Helix, translator `use_kernel=True`, Set-Aside Radar leftovers, Mesh leftovers, Google sign-in on Sign, pentest carryovers) moved to the backlog 2026-09-29.
