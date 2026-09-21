# CLAUDE.md — Phoenix DevOps OS
# jwl247 / Jerry Leftwich / Phoenix DevOps LLC
# READ THIS FIRST EVERY SESSION. UPDATE AND PUSH AT END OF EVERY SESSION.
# =============================================================================

## WHO
- Jerry Leftwich (@jwl247) — ironworker, 25 years commercial steel, systems builder, United Systems
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

## AI ARCHITECT
Claude (Anthropic) is the AI architect and co-builder on this project.
Every meaningful advance in the last 3 months — shared filesystem, dashboard,
clonepool integrity, R2 wiring, QR pipeline, Debian boot, collaboration demo —
was designed and implemented with Claude. Not assisted. Built.

Other AI tools have been tried. A rogue session caused hardware damage (see AI Safety Rules).
Gemini spent 2 days on a problem Claude fixed in 30 seconds.
Claude reads the architecture first, then acts. That is the only way to work on Phoenix.
Do not defer to other AI tools' suggestions without running them through this document first.

## CURRENT BUILD TARGET
- **External drive** — Ubuntu Server (minimal) + HWE kernel
- Stack on external: Prometheus, Nextcloud, PowerShell
- Phoenix builds on top of that as the OS layer
- Work from: Windows PS7 or WSL (SSH or direct when booted)
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
  clone-pool/        one big JSON, nothing moves until output

sector3/
  translator/        translator.sh (fires on OUTPUT ONLY — never intake)
  romeo_juliet/      romeo.py, juliet.py, dbl_juliet.py
  quadengine/        quadengine.py
  services/          all .service + .target files + install-units.sh

sector4/
  intake/            intake.sh
  vault/             phoenix-push.sh, download.sh
  helix/             Helix engine (double strand, 300k+ ops/sec, 100% hit rate)
  frank/             Frank (environment orchestrator, audit logger, never moves)
```

## CORE COMPONENTS

### Helix — double strand memory engine
- 300k+ ops/sec (benchmarked at 700k), 100% hit rate
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
- 41 tables
- phoenix_dev_db
- Worker: packages-worker.phoenix-jwl.workers.dev

### 4-day versioning + Physical Drive Architecture
- What was it + custody = complete file history
- breach_coms are **physical drives** — renamed by Frank, mounted by label
- Frank is the hardware orchestrator — he knows the drives, routes by pressure
- WSL is the bridge: Windows drives appear as /mnt/d /mnt/e /mnt/f /mnt/g in Debian
- align_dirs.sh maintains path parity between WSL dev and bare metal Debian
- Drive labels (not UUIDs) — stable across machine changes, Frank-managed

  ```
  Physical drive label    WSL/Debian mount    Role
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
5. All scripts: #!/usr/bin/env bash (external Ubuntu) or zsh (WSL dev)
6. GPU drivers blacklisted — never suggest GPU-dependent solutions
7. Header QR BEFORE hashing / Footer QR AFTER hashing — never swap
8. Never delete from breach_coms4 (master vault)
9. Nothing enters the repo unless tested, polished, pro+ status
10. No demos. Real code only.
11. Immutable: reviews, switches, custody chain
12. Open source by default, share by default, opt out not opt in
13. One repo. One OS. Everything in its sector.

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

## BUILD STATUS

### Phase 1 — External Ubuntu base (CURRENT)
- [ ] Ubuntu Server minimal + HWE kernel on external drive
- [ ] Prometheus installed
- [ ] Nextcloud installed
- [ ] PowerShell installed
- [ ] SSH access confirmed from WSL/PS7

### Phase 2 — Sector 1 (Boot/Kernel)
- [ ] frank3_slot_a.c + frank3_slot_b.c placed in sector1/kernels/
- [ ] Makefile placed
- [ ] helix stack placed in sector1/helix/
- [ ] phoenix_auth.py placed in sector1/auth/
- [ ] concierge placed in sector1/concierge/

### Phase 3 — Sector 4 (Helix + Frank engine)
- [ ] Frank placed and confirmed immovable
- [ ] Helix engine running — confirm 300k+ ops/sec
- [ ] breach_coms drive map confirmed on external
- [ ] Clone pool initialized
- [ ] D1 worker URL set and syncing

### Phase 4 — Sector 2 (Package handler + clone pool)
- [ ] Phoenix-Package_handler migrated into sector2/
- [ ] intake.sh operational on external
- [x] packages-worker deployed and healthy (v3.4+ with /stats endpoint)
- [x] Import method tested end-to-end (C core ingress → D1 + R2 + local sidecar.json)
- [x] R2 upload wired into the bash intake.sh pipeline (was documented as canonical, never actually bound/uploaded to before 2026-08-22 — confirmed via byte-identical fetch-back)
- [x] Content-hash integrity system — SHA3-512 + BLAKE2b baseline set at intake (`clonepool.hash_sha3`/`hash_blake2`), re-checked at `intake clone` time via `POST /clonepool/:hex/validate`, gates clone-to-workdir/hot-swap on mismatch (see sector2/package-handler/README.md § Integrity Verification) — **was silently broken since introduction**, fixed 2026-09-20 (see SESSION LOG)
- [x] Real per-file version history — `versions` table + immutable per-content R2 keys (`/clonepool/:hex/versions/:hashPrefix`), auto-logged on every genuine content change via `POST /clonepool`. NOT time-windowed/auto-evicting yet — see `project_versioning_true_state` memory for the honest scope line
- [x] Tier placement + 4-day rotation/eviction — `T1`(newest)→T2→T3→T4→evicted, `rotate_clonepool_tiers()` wired into `intake prune`, R2 untouched by moves (hex-keyed, tier-agnostic)
- [x] Dependency graph — `deps` table + `GET/POST /deps`, `translator.sh`'s new `deps` verb across all 9 backends, wired into `intake_from_backend()`
- [x] Location-aware QR — header/footer QR strings now carry a hex-encoded relative path segment, self-describing without a D1 round trip
- [ ] Propagator rebuilt in sector2/propagator/

### Phase 5 — Sector 3 (Comms/networking)
- [ ] romeo.py + juliet.py + dbl_juliet.py placed
- [ ] translator.sh placed — OUTPUT ONLY rule enforced
- [ ] quadengine.py placed
- [x] phoenix-dashboard.service written → sector3/services/phoenix-dashboard.service
- [ ] All .service + .target files deployed via install-units.sh on Ubuntu

### Phase 6 — Apps (Entourage)
- [x] Dashboard Electron app — real D1/R2 data, Claude HUD, boot-time auth modal
  (terminology resolved 2026-09-19: this app IS the HUD — `dashboard/index.html`
  already builds it as `hud-zone`/`hud-nav-btn`/holographic-display internally.
  "Dashboard" was always the wrong external name for it. It is the base for the
  in-game Monster Phoenix HUD — see [[project_monster_phoenix_game]] in memory.
  Folder/service rename (dashboard/ → hud/, phoenix-dashboard.service →
  phoenix-hud.service) is a separate, deliberate follow-up — not done yet.)
- [x] Claude HUD wired — subscription / API key / Ollama (three-tier, nobody excluded)
- [x] Helix memory on both ends — helix_packet.js (JS) + ClaudeMemory (Python, QuadralingualPacket)
- [ ] MapTiler integration (next session — paid, goes in dashboard map panel)
- [ ] Glossary wired to D1 (glossary panel in dashboard) — backend/API confirmed working end-to-end 2026-08-21 (see docs/GLOSSARY.md); dashboard UI panel itself still not built
- [x] Real PS7 shell in dashboard HUD (ps7-shell.js — actual pwsh.exe spawns, not a mock; verified via live Playwright drive-through 2026-08-21) + clonepool browser + screenshot analysis panels
- [x] Dedicated Claude "subscription" mode in dashboard chat — real Claude Code CLI with `--dangerously-skip-permissions`, fully separated from Ollama (no fallback, no interference); real SSE streaming added for the plain API-key path too
- [x] Live Monitor panel — on-demand desktop/window screen capture (desktopCapturer) streamed to Claude chat, separate capture destination from the watched screenshots folder so the two don't storm each other
- [x] Clonepool panel converted to async (fs.promises) with search + result capping — was freezing the whole Electron main process once the pool passed ~15k files
- [x] Clonepool made available at the repo root as a Windows directory junction (already gitignored); PS7 shell dot-sources `scripts/usys.ps1` so `clone`/`usys` work inside it (previously silently missing under `-NoProfile`)
- [ ] Desktop (shade UI, drawer filesystem) — dashboard transforms into this
- [ ] Office (dual browser pane)
- [ ] Sketchpad/Concepts
- [ ] Music Notation Transcriber
- [ ] Review Platform

### Phase 7 — GRUB + polish
- [ ] Custom Phoenix GRUB theme
- [ ] Boot entries configured
- [ ] Vault recovery pointer in GRUB
- [ ] External drive boots clean as Phoenix

## SESSION PROTOCOL
**START:** Read this file. Know where we are. Run status.sh if available.
Life First's real backend is the `lifefirst-mcp` Cloudflare Worker, already exposed
every session as the `mcp__claude_ai_lifefirst-current__*` tools (schedule, messenger,
budget, memory, notification, reminder, voice) — no extra pull step needed, they're
loaded by default. Use them proactively on Life First-relevant work because Life First
is why Phoenix exists (see ## PURPOSE). The PHP tree at sector2/apps/lifefirst/
(module_3_schedule_ai.php, module_4_messenger_ai.php, module_5_ai_memory.php,
module_6_notification_ai.php, module_7_voice_ai.php) is a retired fossil — confirmed
2026-08-19, hardcoded plaintext creds, never run its setup/deploy scripts.
**WORK:** Stay in sector. Real code only. Everything through Frank/intake.
**END:** Update ## BUILD STATUS checkboxes. Add session notes below. Push.

## SESSION LOG
<!-- Claude appends a one-line note here at end of every session -->
<!-- Format: YYYY-MM-DD — what was done -->
2026-06-28 — C core Helix double-strand proven (ingress + egress, D1 + R2 + local cache). packages-worker /stats endpoint live. Dashboard wired to real data. Claude HUD added — 3-tier auth (subscription/API key/Ollama, nobody excluded). Helix memory on both ends: helix_packet.js (QuadralingualPacket JS), ClaudeMemory (Python via HelixTranslationPipeline + DoubleHelixStorage). SectorID.CLAUDE added. phoenix-dashboard.service written to sector3/services/. helix_memory.py placed in SECTOR4/vault/.
2026-06-29 — Full architecture audit. Corrected clone pool (R2+D1+cache, not JSON). Documented physical drive reality (breach_coms1-4 are labeled HDDs, Frank is hardware orchestrator, WSL is the bridge). Corrected Entourage (apps ARE the engine team — franken2/quadengine/paging/guardian/conductor). AI safety rules written into CLAUDE.md after rogue session damage history confirmed (3 PCs, 4 HDs lost). Purpose documented: Life First LLM app for Laurie. Completion revised to ~63% against full scope.

2026-08-21 — Repo-wide cleanup pass: root triage (deleted superseded/stub files, archived New folder/ + SECTOR4-coms fossils), sector1 (untracked an accidental dev-VM dotfile dump without deleting it, fixed naming, confirmed sector1/kernel/ is its own separate project not a duplicate), sector2 (fixed 3 badly-named files/folders, intaked 219 files), sector3 (clean, intaked 26 files), scripts/ + tools/ intaked. Found and fixed real bugs along the way: packages-worker D1 binding mismatch (env.PHOENIX_DB vs env.DEV_DB — was silently breaking every DB endpoint) redeployed; added clonepool.sensitive D1 column + full intake.sh/worker wiring so sensitive files (auth, secrets, tokens) land in D1 flagged rather than excluded or silently unmarked; fixed a foreign-key bug in intake_directory's glossary report (missing "directory" category — every prior directory-level intake had been silently failing this); expanded intake.sh's known-extension whitelist (was silently dropping Kotlin/PHP/gradle/etc into the same bucket as binary junk); fixed 5 tools (usys.ps1, scripts/intake.ps1, tools/clone.ps1, tools/clone.sh, bin/intake) that all had stale nested intake.sh path candidates — `usys clone`/`clone` were completely broken on this repo before today. Converted sector2/package-handler from an independently-maintained copy into a real git subtree of the standalone Phoenix-Package_handler repo (caught and worked around: the script's own bugs — unconditional success messages masking real failures — and a case-insensitive-filesystem collision between SECTOR4 fossil-archive target and the live sector4/ vault code, which would have archived live code). PHOENIX_AUTH rotated (old token was stale/mismatched between local env and the Cloudflare secret, silently blocking all D1 sync). Verified dashboard's real PS7 shell + clonepool browser + screenshot-analysis panels via live Playwright-driven Electron test — all three work end-to-end, zero console errors. Everything pushed to origin/main through commit b7478e7. docs/GLOSSARY.md and tools/poc/README.md written.

2026-08-22 — Dashboard debugging pass: fixed the clonepool panel freeze (sync fs walk → async, capped+searchable), wired R2 uploads into the bash intake.sh pipeline for real (was documented as canonical since June, never actually bound — confirmed via byte-identical fetch-back of dashboard/main.js), fixed PS7 shell stdin delay and the OPEN PS7 button (stdio:'ignore' was giving pwsh.exe a closed stdin, not an interactive window — cmd.exe /c start fixes it), removed an invalid --no-color flag breaking every Claude CLI call, fixed a data-loss bug where re-saving AI auth without retyping the key silently dropped it, stopped Ollama auto-starting at boot regardless of configured provider, built real SSE streaming for the Claude API chat path, and gave the dashboard a genuinely dedicated "subscription" Claude mode (full Claude Code CLI, --dangerously-skip-permissions, zero Ollama fallback/interference — user's explicit ask: "yours to have and to hold"). Added a Live Monitor screen-capture panel (separate capture destination from the watched screenshots folder, avoiding a capture/chat feedback loop the user caught before it shipped). Made the clonepool available at the repo root via a Windows directory junction and fixed the PS7 shell to dot-source scripts/usys.ps1 (global clone/usys commands were silently missing under -NoProfile).

Archived the old 1.6GB local clonepool and did a full clean re-intake of all 10 top-level folders (sector1-4, scripts, tools, bin, bootstrap, deploy, dashboard) to backfill R2 with real content now that upload is wired — 0 D1 failures, 0 R2 failures. Along the way, restored QR generation (header/footer, USYS:<b58>:HEADER / :FOOTER:<hex>) into the bash intake.sh pipeline by porting the working logic out of the older phoenix-core/tools/intake.py — user correctly called out that this "worked once upon a time," it just wasn't in the currently-active pipeline. Rotated PHOENIX_AUTH (old token silently mismatched between local env and the Cloudflare secret — same class of bug as 08-21's rotation) and fixed everywhere it's consumed (all pure env-var reads, nothing hardcoded, so the fix was just the rotation itself).

Built a real content-integrity system end to end, per user direction that "validated" should mean the clonepool copy is checked against custody before it's ever handed to a working directory or hot-swapped: intake.sh now computes SHA3-512 + BLAKE2b at intake time and stores them as the trusted baseline on the clonepool D1 row; a new `POST /clonepool/:hex/validate` endpoint compares a freshly-computed hash against that baseline and flips `qr_valid`/`verified_at`; `intake clone` (both single-file and directory-snapshot forms) now hashes the local copy and refuses the clone outright on a mismatch, warns-and-proceeds if there's no baseline yet (pre-fix legacy files). Backfilled hashes+QR for all 286 already-intaked files (0 failures) since none of this existed before tonight. Excluded `clonepool` and `archive` from intake.sh's SKIP_DIRS (the junction and the fossil dump were both about to get walked into the live catalog) and ran one final whole-repo intake pass (376 files, 93 new) to catch everything not covered by the folder-by-folder run — root files, docs/, phoenix-core/, poc/. Documented the whole integrity system in sector2/package-handler/README.md (which also didn't document `intake clone` at all before this).

2026-09-20 — Huge session, several threads. **Drives:** E: (was "VAULT-B") reformatted into "Claude Operational Zone" — dedicated to Phoenix logs/memory/models and Monster Phoenix game/state, kept strictly separate (Phoenix ≠ the game — Jerry corrected an early draft that blurred them). Real content on old E: (clonepool snapshot, helix-pages POC, claude-setop) migrated to F:\Phoenix\migrated-from-E\ first; confirmed-junk Windows-install debris wiped — **except a real 748GB Steam library that got caught in that wipe by mistake** (bundled into the debris batch without being sized/checked separately first — a real error, logged honestly). D: (Claude's dedicated drive) partially cleaned of old-Windows-install debris (Program Files/ProgramData/WindowsApps/Config.Msi/Recovery/junction/pagefile/swapfile all removed) — `D:\Windows` and `D:\Users` still have ~20K items/20GB of deeply-protected TrustedInstaller files that `takeown`+`icacls` couldn't fully clear; `hiberfil.sys` needs `powercfg /hibernate off` first. Not finished — pick back up if it matters.

**Clonepool/versioning system — found and fixed real, previously-invisible bugs, then built real features:** the deployed packages-worker was silently 500ing on every `POST /clonepool` call this whole time (`CLONEPOOL_DIR` is a Windows backslash path, and the worker's hand-built JSON strings were never escaping it — invalid JSON, silently dropped). Same root cause broke the hash-integrity verification (`verify_clonepool_copy`) and the new `rotate_clonepool_tiers` — both parsed D1/local JSON with a regex that didn't allow for pretty-printed spacing. All fixed: added `json_escape()`/`normalize_path()` used everywhere paths and strings enter JSON. Built real per-file version history (`versions` table, was designed but dead — 0 rows, dead FK to `packages` too) — immutable, content-hash-triggered, byte-retrievable via new `/clonepool/:hex/versions/:hashPrefix` R2 route. Built real tier placement + 4-day rotation/eviction (`T1`→T2→T3→T4→evicted, `rotate_clonepool_tiers()`, wired into `intake prune`) — the physical half of the long-documented-but-never-built "4-day versioning" design; R2 untouched by tier moves since it's hex-keyed, not tier-keyed. Built real dependency tracking — `deps` table, `GET/POST /deps`, and (new) a `deps` verb across all 9 `translator.sh` backends, wired into `intake_from_backend()` — `intake.sh` and `translator.sh` had never actually called each other before tonight despite both existing for a long time. Added location-aware QR (header=status shade, footer=identical payload/tier color, per the original design intent) — hex-encoded relative path appended to both strings so they're self-describing without a D1 round trip. **Found a real filename-collision bug that's NOT fixed**: `hex_id = to_hex(basename)` — every file sharing a name anywhere in the repo (multiple `README.md`s, etc.) collapses into the same D1 row/R2 object, last-intake-wins. QR now labels location correctly even though storage still collides — the actual address-scheme fix (hash path+name, not name alone) is still open. Merged the sector2/sector3 packages-worker divergence (sector3's copy had R2 binding + hash writing that sector2's live-deployed copy was missing) into sector2 (the canonical location per existing migration direction), bound the previously-unbound `phoenix-clonepool` R2 bucket. Ran a full clean re-intake under all these fixes: 441 clonepool rows, 213 new immutable versions logged, 0 D1 failures.

**R2/D1 waste audit:** found and fixed a `windows` R2 bucket holding a stale (6-week-old) 475MB/6,358-object "emergency network-boot" snapshot stored as loose files instead of a git bundle — replaced with a single current 11.6MB bundle, dropped a fossil PHP-tree folder with old (pre-auth-rework, confirmed dead) credentials. Audited all 49 D1 tables — 11 actually populated, ~38 are designed-but-never-wired schema (same pattern as `versions`/`mirrors` before tonight). Found `deps`/`dependencies` as two genuinely different, never-reconciled table designs for the same concept — picked `deps` (name-keyed, matches the rest of the system), `dependencies` should get dropped once permission allows.

**Security — real findings, not fixed tonight, fully spec'd for next session** (see `project_security_gap_plan` memory + NEXT SESSION below): every GET endpoint on packages-worker has zero auth. Recovered the real "quadralingual" implementation (archive fossil, `QuadralingualPacket`) and confirmed it was never a security/confidentiality mechanism — two of its four views store plaintext unmodified. Both are real, live gaps, not documentation-only.

**Also:** installed the GitHub plugin and authenticated the Cloudflare plugin (both now available). Fixed `phoenix_auth.py`'s D: PS7 startup issue class of bugs (self-inflicted `set -e` + `BASH_SOURCE` fragility in a new `TRANSLATOR_SH` line — hardened). Verified the Electron dashboard still launches and renders correctly post-migration (had to fix a broken local `electron` binary install along the way — pure environment issue, unrelated to any code change). Confirmed `hud/` (WPF) stays the real HUD, `dashboard/` (Electron) stays as-is and is never converted into it — Jerry: "electron is a fabulous dashboard but not a HUD." Agreed GLOSSARY/CODES/GUIDE become Claude Skills instead of coded WPF panes; PS7 shell/MAP/SCREENSHOT/Live Monitor/voice stay coded since they're live/interactive, not skill-shaped.

## NEXT SESSION
- Build GLOSSARY/CODES/GUIDE as Claude Skills for the HUD (not coded WPF panes) — chat-driven, backed by existing worker API access. PS7 shell/MAP/SCREENSHOT/Live Monitor/voice stay coded (live/interactive, not skill-shaped). Also build a skill for Laurie's new regulatory-writing consulting business — Jerry confirmed 2026-09-20 it should cover all three, connected as one workflow: finding leads/opportunities, writing proposals/pitches to win the work, and drafting the actual regulatory documents once landed.
- **SECURITY — start here.** Every GET endpoint on packages-worker has zero auth (confirmed 2026-09-20) — anyone with the worker URL can read all clonepool file bytes, including sensitive-flagged ones, no credentials needed. And "quadralingual" storage was never a confidentiality mechanism — real code exists (`archive/.../freewheeling.py` `QuadralingualPacket`) but two of its four views store plaintext unmodified; no encryption/obfuscation of file content has ever existed anywhere in Phoenix. Full fix spec (both gaps) written up and ready to build from — see memory `project_security_gap_plan.md`, don't re-derive.
- docs/ reconciliation — QUICK_START.md vs GETTING_STARTED.md vs root README.md look like they may overlap, not yet audited (last item on the repo cleanup pass)
- MapTiler map panel in dashboard (Jerry paying, integrate as desktop panel)
- Glossary dashboard UI panel — superseded by 2026-09-20's decision to build GLOSSARY as a Claude Skill instead (see above); revisit whether a dashboard panel is still wanted alongside the skill, or the skill replaces this item entirely
- Shade UI + drawer filesystem (desktop transformation begins — real shell is now in place as a foundation piece)
- Deploy phoenix-dashboard.service on Ubuntu 192.168.1.133
- Start manual/phoenix_manual.md
- Consolidate the 3 redundant PS7 buttons (top-left quick button, sidebar OPEN PS7, bottom-nav PS7 SHELL tab) into one
- **Real filename-collision bug (found 2026-09-20, not fixed)**: `hex_id = to_hex(basename)` in intake.sh means any two files sharing a name anywhere in the repo (multiple `README.md`s, `dashboardDEP/` vs its live counterpart, etc.) collapse into the same D1 row/R2 object — last intake wins, silently. QR labeling now shows the correct location regardless, but storage itself still collides. Real fix needs the address scheme to hash path+name, not name alone — bigger change, ripples into the documented TAV addressing scheme, deliberately deferred tonight.
- Directory-summary intake entries get an ugly hex when the intake path is "." (e.g. tonight's whole-repo pass: hex "2e", name ".") — cosmetic only, all per-file entries underneath are correct, but worth passing the resolved dirname instead of the raw arg
- `dependencies` table should be dropped (superseded by `deps`, see 2026-09-20 log) — blocked on adding the `autoMode.allow` permission rule to `.claude/settings.local.json` (Jerry needs to do this himself, Claude can't self-grant it)
- Finish D: cleanup — `D:\Windows`/`D:\Users` still have ~20GB of TrustedInstaller-protected files `takeown`+`icacls` couldn't clear; `hiberfil.sys` needs `powercfg /hibernate off` first
2026-05-03 — New canonical CLAUDE.md written. Repos audited. External Ubuntu build target established. Import method confirmed as intake strategy. Build plan phased across 7 phases.
