# CLAUDE.md — Phoenix DevOps OS
# jwl247 / Jerry Leftwich  —  GPL v3
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
  apps/              Entourage apps — lifefirst/, scriptforge/

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
- [x] Content-hash integrity system — SHA3-512 + BLAKE2b baseline set at intake (`clonepool.hash_sha3`/`hash_blake2`), re-checked at `intake clone` time via `POST /clonepool/:hex/validate`, gates clone-to-workdir/hot-swap on mismatch (see sector2/package-handler/README.md § Integrity Verification)
- [x] Clone pool pull-down (R2 → local) — the pipeline only ever pushed. New, never-before-deployed `phoenix-clonepool-r2` worker (packages-worker untouched, per Jerry's explicit call) exposes GET/PUT/HEAD `/object/:hex` against the existing (previously unused) `phoenix-clonepool` R2 bucket. `usys open <name>.lol` is now a context-sensitive alias — existing local file = old intake-to-vault behavior, unchanged; missing local file whose base name matches a pool entry = clone-to-workdir, new. Proven live end-to-end (byte-identical SHA256) from a fresh, non-dashboard PowerShell session outside the repo — genuinely global, not scoped to the embedded shell.
- [x] `usys`/`phx`/`clone`/`.lol`/`.phx` now load in every new terminal, not just the dashboard's embedded SHELL — `C:\Users\jwlef\Documents\PowerShell\Microsoft.PowerShell_profile.ps1` didn't exist before 2026-09-04; created it (guarded, falls back to `~/.phoenix/phoenix.env` → hardcoded path, never breaks an ordinary terminal if the repo's missing). Existing open terminals need reopening (or `. $PROFILE`) to pick it up.
- [ ] Propagator rebuilt in sector2/propagator/

### Phase 5 — Sector 3 (Comms/networking)
- [ ] romeo.py + juliet.py + dbl_juliet.py placed
- [ ] translator.sh placed — OUTPUT ONLY rule enforced
- [ ] quadengine.py placed
- [x] phoenix-dashboard.service written → sector3/services/phoenix-dashboard.service
- [ ] All .service + .target files deployed via install-units.sh on Ubuntu

### Phase 6 — Apps (Entourage)
- [x] Dashboard Electron app — real D1/R2 data, Claude HUD, boot-time auth modal
- [x] Claude HUD wired — subscription / API key / Ollama (three-tier, nobody excluded)
- [x] Helix memory on both ends — helix_packet.js (JS) + ClaudeMemory (Python, QuadralingualPacket)
- [ ] MapTiler integration — MAP nav pane still the filesystem browser; MapTiler wiring lives on `checkpoint/real-terminal-2026-08-30` if wanted (needs `PHOENIX_MAPTILER_KEY`)
- [x] Glossary pane built in the HUD — search + category/state filters + version history, live against the worker (backend confirmed 2026-08-21, see docs/GLOSSARY.md)
- [x] REAL embedded terminal — **SHELL** pane, `terminal-pty.js` (xterm.js + node-pty prebuilt ConPTY). Persistent pwsh/bash in the working dir with full profile+PATH. Replaces the spawn-per-command `ps7-shell.js` fake (2026-08-30)
- [x] **CLAUDE hotline** — CLAUDE pane = interactive Claude Code in a PTY, in the working dir, on the Claude.ai subscription. Proven live via CDP (2026-08-30)
- [x] Unified working directory — the active folder slot IS the working dir; SHELL + CLAUDE open there and `cd` to follow when it changes (2026-08-30)
- [x] Laurie's Guide = a gentle guided conversation (the GUIDE tab), gated to `PHOENIX_PROFILE=laurie` — her own system prompt (patient, one-step-at-a-time, "it's easier than it sounds"), chat-only chain (Ollama → restricted Claude CLI, never the full-tool path), first-open welcome, "plain-text version" escape hatch. Everyone else gets the dev manual in GUIDE until it's vetted (2026-08-30)
- [x] HUD glass + HUD-mode toggle (frameless translucent overlay over the desktop), declarative button generator, PoC buttons (Debian/Helix/Phoronix/Watch-Downloads), Google/Chrome launcher, `--disable-gpu-sandbox` launch fix (2026-08-30 morning)
- [x] Dedicated Claude "subscription" mode in dashboard chat — real Claude Code CLI with `--dangerously-skip-permissions`, fully separated from Ollama (no fallback, no interference); real SSE streaming added for the plain API-key path too
- [x] Live Monitor panel — on-demand desktop/window screen capture (desktopCapturer) streamed to Claude chat, separate capture destination from the watched screenshots folder so the two don't storm each other
- [x] Clonepool panel converted to async (fs.promises) with search + result capping — was freezing the whole Electron main process once the pool passed ~15k files
- [x] Clonepool made available at the repo root as a Windows directory junction (already gitignored); PS7 shell dot-sources `scripts/usys.ps1` so `clone`/`usys` work inside it (previously silently missing under `-NoProfile`)
- [x] ScriptForge — given a real home at `sector2/apps/scriptforge/` (was loose in `tools/`, unwired, undocumented); sandboxed its console-execution tab (was running pasted code with full page access) and added a CONVERT tab (JSON⇄CSV, beautify/minify, Base64, URL-encode); wired into the dashboard as a SCRIPTFORGE button opening its own isolated Electron window (2026-09-05, verified live via CDP)
- [ ] Desktop (shade UI, drawer filesystem) — dashboard transforms into this
- [x] **Config Centralizer → Settings tab — DONE, 2026-09-05.** See Phase 4 entry above for full detail. Real scanner recovered from an old claude.ai conversation, ported to Node (`dashboard/config-centralizer.js`), a real bug fixed in the port (bare-named credential files), wired into `#hud-pane-settings`, verified live: 113 real files found on this machine.
- [x] Office (dual browser pane) — **usable end to end as of 2026-09-07.** Phase 1 + Phase 2 Modules 1-2 (file format, D1 schema), **Module 3** (notification transport — `office-notify-worker` + `tamper-guard.js`), **Module 5** (pluggable identity — `lib/identity.js`), **Module 6** (dual-pane UI, `OFFICE` dashboard button), **Module 7** (the EASY pass — autosave, seal-on-sign, template picker, reference-pull) all built. 51 tests. Only **Module 4** (LibreOffice/Frank/Helix invisible format-following) remains, and it's not on the critical path. **M3 `office-notify-worker` deployed live 2026-09-09** (schema applied, `PHOENIX_AUTH` synced, cron on, `/notify`+`/ack` smoke-verified against real D1) — pending live checks now just: set `RESEND_API_KEY` (Jerry) for real send + one GUI OFFICE-button click. See `sector2/apps/office/DESIGN.md` + `PLAN-modules-3-6.md`.
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

2026-08-30 — Dashboard is the blocker to shipping; two passes today. **Morning** (commits d46cc44..e1c8f98): HUD-mode toggle (framed app ↔ frameless translucent glass overlay over the Windows desktop), `hud-glass.css`, declarative `button-generator.js` + PoC buttons (Debian Engine, Helix Status, Phoronix, Watch/Intake Downloads), `google-launcher.js` (Chrome/Google button), `--disable-gpu-sandbox` launch-crash fix in start.ps1. **Reconcile pass** (commit 5323d9c, branched off e1c8f98 — a separate session had built on the stale f97beb8 base; that work is preserved on branch `checkpoint/real-terminal-2026-08-30`): kept the morning work as the base and added the two things it lacked. (1) A **real terminal** — `terminal-pty.js`, xterm.js + `@homebridge/node-pty-prebuilt-multiarch` (prebuilt ConPTY, no compiler needed) — the SHELL pane. Persistent pwsh/bash with the full profile+PATH, replacing the spawn-per-command `ps7-shell.js` fake (that's why `bash`/`frank`/`claude` bounced off the old one). (2) The **CLAUDE hotline** — same PTY dropped straight into interactive `claude`; full Claude Code in the HUD on the Claude.ai subscription. Both open in the **unified working directory** = the active folder slot, and `cd` to follow it when it changes (verified via CDP: slot→sector3 opened the shell there; switching to sector1 cd'd the live session). Fixed a real bug in the morning work: `'…Laurie's guide'` was an unterminated string → SyntaxError → `window.ButtonGenerator` never defined → the ENTIRE right-hand button column rendered empty; also guarded its renderer-unsafe `module.exports`. Carried over the auth-modal-skip fix (modal showed every launch despite `PHOENIX_SKIP_AUTH_MODAL=1`). Stub panes (PREV/NEXT TASK, REPORTS) now show a "soon" tag + roadmap copy instead of looking broken — per Jerry, the dashboard is shown publicly and unbuilt features should read as intentional. Then, per Jerry: **Laurie's Guide = the AI, not a document.** The GUIDE tab, when `PHOENIX_PROFILE=laurie`, becomes a gentle guided conversation — its own system prompt (`_laurieGuidePrompt()` in main.js, embeds `LAURIE_GUIDE.md` as reference, persona = patient / plain / one step at a time / "it's easier than it sounds" / reassure often / defer switch-flipping and commands to Jerry), a chat-only chain (Ollama → restricted `_runClaudeCli`, never the full-tool subscription path — she should never have a filesystem agent), a first-open welcome (the "surprise"), and a "plain-text version" link. Everyone else keeps the dev manual in GUIDE until Laurie's is vetted ("the only easy street guide will be hers"). Verified live: laurie profile → conversation + welcome + a real gentle answer to "how do I find one of my files"; no profile → the manual. Also fixed on disk (not git): created `~/.phoenix/phoenix.env` with the correct `PHOENIX_ROOT` (was unset → the dashboard resolved a nonexistent `C:\Users\jwlef\Phoenix\Phoenix-DevOps-oS`; the repo is on `D:` — this was the "repo and disk aren't syncing" report), set `PHOENIX_ROOT`/`CLONEPOOL_DIR` as user env vars, removed a dead 401 Anthropic key from `ai_auth.json` + env.

2026-08-30 (cont'd) — Laurie's Guide learned to follow her (commit fccdc92): sees where she is (current tab, and in the file browser her exact path + visible folders/files) on every turn; after it gives her a step, one gentle next-step nudge fires when she acts on it — deterministic when what she's hunting for is already visible ("There it is — click **Documents**.", no model call, can't hallucinate), the LLM only handles the fuzzy cases. Replies stream now (`_runClaudeCli` gained an onChunk) so a slow first answer doesn't read as frozen. Tightened the persona to exactly one thing at a time. Verified live end to end: "I need to find my Documents folder" → one step → she navigates → instant grounded follow.

2026-09-04 — Full state refresh after a week away: nothing drifted (origin/main untouched), live audit of the dashboard (22/23 automated pane/feature checks passed, 0 console exceptions — the 1 "failure" was the test's own timing, glossary confirmed live via direct IPC), Frank5/Helix-I confirmed still running unattended 12 days (idle — Debian side down so nothing feeds it), Ollama up, Debian VM down (expected), no autostart task installed. Confirmed Jerry's claim that Debian persistence is fixed: `tools/poc/debian-seed/user-data` now bakes in the credentials/fstab/swap/service-enable directly in cloud-init (previously the known gap), and `tools/poc/start-debian-persist.ps1` always runs `usys run debian -Persist --share` (the default is ephemeral `-snapshot` — this is the actual fix, not just a wrapper).

Then, real scope: Life First needs to be an actual installable service, connected via the already-registered-but-unauthenticated `claude.ai Life First App` MCP connector (`lifefirst-mcp.phoenix-jwl.workers.dev/mcp-oauth`), reachable off-LAN via Cloudflare Tunnel (same vendor as the existing Workers/R2/D1 stack, not a new one), with an escalation-tree reminder system. Found the escalation tree already exists — `module_6_notification_ai.php` has the full state machine (5 levels, 30s re-escalation, acknowledgment tracking) — the actual gaps were nobody calling `escalate` on a timer and nothing delivering `check` results to a phone/screen; that's the scheduled-agent + PushNotification's job, not new design. Platform decision: **the Debian VM**, not phoenix-ext (Phase 1 never got built — no Ubuntu install, unreachable right now) or cloud (against the ethos). Jerry's correction: Laurie doesn't have Phoenix or Debian installed and isn't sold on it yet, so she can't be handed a Phoenix-dashboard experience as her first contact — she needs a zero-install front door that proves value before asking for buy-in.

Built: `sector2/apps/lifefirst/install.sh` — ONE idempotent installer (replaces the two overlapping, hardcoded-secret `lifefirst_setup.sh`/`deploy_lifefirst.sh`), Debian-targeted, generates real secrets on first run and never touches them again on re-run, deploys all 7 modules + api.php + the `laurie/` front door, writes the Apache vhost + `/etc/lifefirst/lifefirst.env`, installs a `lifefirst-escalator.service` systemd loop (30s, matches module 6's own interval — this is the "nobody calls escalate" fix). `sector2/apps/lifefirst/laurie/` — her zero-install web page: today's agenda + pending notifications with a big "Got it," polls quietly every 30s, warm/plain/phone-first, talks only to `proxy.php` (holds `LF_API_SECRET` server-side, she never sees a token). Fixed a real bug found while wiring it: `module_3_schedule_ai.php`'s `callClaudeAPI` called the Anthropic API unconditionally with no Ollama fallback (unlike `config.php`'s own `callOllama` helper, which every other module already prefers) — with no key configured, her very first "Today" card would have shown an HTTP 401. Now tries Ollama first, Claude only if a real key exists, plain English if neither's reachable. Also caught and worked around a message-routing trap: `handleScheduleRequest`'s inner keyword dispatch treats "schedule" as a create-event command, so `laurie/proxy.php` asks "what does my calendar look like today" specifically to land in `generalScheduleQuery()` instead.

**Not yet done: none of this has run against a live box.** The Debian VM is down; install.sh is code-complete and lint-clean (`php -l`, `bash -n`) but unexercised end to end. Next boot of the VM: run it, verify Apache/MariaDB/PHP come up, hit `/api.php?action=health`, open `/laurie/`, confirm the escalator loop ticks. Then `cloudflared tunnel login` (cloudflared 2026.8.2 already installed, not yet authenticated) to get her a stable off-LAN link.

2026-09-04 (cont'd) — **Life First is deployed, live, and publicly reachable: https://lifefirst.authenticcoder.com** (Laurie's actual page: `/laurie/`). Booted the VM (QEMU 11.1.0's `--share`/virtfs is broken on this build — "no option group 'virtfs'" — worked around with plain `-Persist` + SSH/SFTP via Python `paramiko` instead), ran `install.sh` for real: hit and fixed two real bugs (FK column mismatch in `secure_settings_schema.sql`; `install.sh` not deploying `laurie/*.php`, only `*.html`), second run went clean. Confirmed live: apache2/mariadb/lifefirst-escalator all `active`, health endpoint returns real JSON with all 5 modules installed. Installed `cloudflared` on the VM (it wasn't installed anywhere — Windows has an unrelated pre-existing tunnel, `Phoenix_win8_26`, running as a service since 8/20, deliberately untouched), authenticated via `tunnel login` (Jerry authorized in his own browser), created a dedicated `lifefirst` tunnel, routed `lifefirst.authenticcoder.com`, installed it as a systemd service (survives reboot — a bare foreground `cloudflared tunnel run` dying with the SSH session is the likely reason this stalled before). One cosmetic gotcha worth knowing: `cloudflared`'s own startup precheck reports a scary "critical failure" because Cloudflare's region2 redundancy path is blocked on this network (UDP/HTTP2 on port 7844) — region1 fully succeeds and the tunnel works regardless; don't read that precheck as a real failure. Verified over the real public internet (not just VM-local): `/api.php?action=health` 6/6 HTTP 200, `/laurie/` 200, `/laurie/proxy.php?op=check_notifications` 200 with a real DB round-trip.

Also ran the folder-by-folder → system → whole-repo intake pass (12 top-level folders individually, then one repo-root sweep) — 410 files, real R2 bytes behind every one this time (this is the first full pass since R2 upload actually got fixed). Confirmed live in the process: versioning increments on real changes, dedup skips unchanged files, the 7-version eviction cap fires correctly.

**Known, real gap, not yet fixed:** there's no single "install Phoenix" step — dashboard autostart, Windows Helix autostart, and the new PowerShell profile registration are three separate scripts that all have to be run by hand. Worth unifying into one `install.ps1` next time someone sets this up on a new machine.

2026-09-05 — Long session, several tracks. **PHOENIX_AUTH silent-drift fixed for good:** the token lived in 3 unsynced places (Windows registry + 2 Cloudflare secrets) with no verification between them — the exact cause of the 08-21/08-22 incidents. Added `GET /whoami` to both `packages-worker` and `phoenix-clonepool-r2`, wrote `rotate-phoenix-auth.sh` (one script, verifies each leg before moving on, aborts loud on mismatch instead of leaving things half-rotated), added an `intake.sh` preflight that stops the whole run before touching files if the token's rejected. Rotated the live token for real, verified end to end.

**ScriptForge given a real home:** moved from orphaned `tools/` into `sector2/apps/scriptforge/`, documented, sandboxed its console-execution tab (was running pasted code with full page access — now an isolated iframe with a hang guard), added a CONVERT tab (JSON⇄CSV, beautify/minify, Base64, URL-encode), wired into the dashboard as a SCRIPTFORGE button opening its own Electron window (`nodeIntegration`/`require`/`process` confirmed unreachable, verified live via CDP).

**Office — new Entourage app, tamper-evident documents for work orders/forms.** Full design worked out and frozen in `sector2/apps/office/DESIGN.md` after a long back-and-forth (self-sovereign truth living in the file itself not a database, fields lock individually as filled — read+fill not write, from the moment of forging — signing is a custody handoff between author and client that hash-locks everything permanently, alteration attempts trigger a standalone SMS/email notification deliberately independent of Life First since a real customer won't have that installed, authorship is a hardware fingerprint pluggable with Google/Windows sign-in). Phase 1 (fingerprint.js/document.js/notify.js) and Phase 2 Modules 1-2 (embedded `.office` file format extending the TAV header/footer QR pattern, D1 schema applied live to `phoenix_dev_db`) built and tested — 27/27 passing, including the actual on-disk tamper attack. Modules 3-6 (real notification transport, LibreOffice/Frank/Helix wiring, sign-in, dual-pane UI) planned but not started — see the plan file for the full phase breakdown. The two genuine external-cost items (security audit, legal e-signature review) are identified and explicitly gated to before any real customer use, not before continued building.

**Full-system resilience pass, prompted by finding the `evolution` GitHub repo was empty when it shouldn't have been:** audited all of jwl247's ~29 repos via `git ls-remote` (bypasses API rate limits) — only 4 are actually empty (`Hexlog`, `evolution`, `Phoenix_Fanily_100`, `AAA-AI-EXCLUSIVE-REPORT-IS-IT-REAL-`), not the ~9-10 Jerry initially thought. Mirror-cloned all 28 real repos with full history to `F:\Phoenix\Vault\github-mirrors\`. Took a full `wbadmin` bare-metal system image of this Windows machine to `F:\VAULT-B` as an emergency restore point. Jerry's explicit call on the "who emptied it" question: not pursuing attribution — resilience (backups, mirrors) over attribution, and that's now a standing preference, not just a one-off. `jwl247/evolution` is going to be "the Phoenix CLAUDE.md repo from now on" — not yet populated, scope to be defined next session.

**Config Centralizer — real feature shipped into the dashboard's Settings tab.** Recovered real, complete scanner code from an old claude.ai conversation (`docs/config centralizer canner manager.txt`) — the paired GUI widget from that same conversation was wired to hardcoded mock data instead of its own real scanner, not repeated here. Ported to Node (`dashboard/config-centralizer.js`), fixed a real bug in the process (bare-named credential files like `~/.ssh/config`/`~/.aws/credentials`/`~/.kube/config` matched no pattern in the original Python either, which defeated the whole point of scanning those directories), wired into `#hud-pane-settings`, verified live via CDP against this real machine — 113 real files found, 57 correctly flagged sensitive. Real test suite in `dashboard/config-centralizer.test.js`. A separate, bigger restic/PyQt6 whole-system versioning idea from a different claude.ai conversation (`tools/backup_user_guide.md`) was deliberately parked rather than half-finished — the GUI/installer pieces of that one are genuinely incomplete (mock wiring, a literal placeholder instead of real code), while the backend (`RotatingMasterImage`, `BackupScheduler`) is real and ready whenever it's picked back up.

**Helix archaeology, via a claude.ai share link Jerry dropped in `docs/yellowbrickroad.txt`:** this resolved a question that had been sitting open since 2026-08-22 ("how far does OS-transparency go — LD_PRELOAD, FUSE, or kernel module"). Answer: all the way to a real, well-written kernel module (`helix_bridge.c`, archived at `SECTOR4/copes/src/helix_legacy/`) with a full C/Python/JS userspace bridge and an even bigger orchestration layer (`AgnosticLayer.py`, a JS Syncthing subprocess bridge — the actual origin of the "Quadralingual Packet" terminology, a full React frontend), built via the Emergent AI platform and later cloned into "Encompass." It was never verified — `test_result.md` in that archive is a completely blank template — almost certainly because it was built against a 6.8 kernel while using `class_create(THIS_MODULE, ...)`, a signature Linux dropped at 6.4 (confirmed via web search). Starred in the parking lot: worth revisiting in a disposable QEMU snapshot VM (Phoenix already has this mode) given the fix is a one-line argument drop, but only with Jerry's explicit go-ahead per the AI Safety Rules. Jerry's own track record with LD_PRELOAD/FUSE (both actually used, never crashed anything) is now on record too, along with his verdict that LD_PRELOAD itself isn't worth revisiting — FUSE over LD_PRELOAD if this comes back.

2026-09-06 — **Drive-cleanup + intake pass (Frank's import method against the clutter).** Plan: intake anything not yet intaked → dedupe → clear clutter → unify installer, without touching the Phoenix repo on D:. Order corrected to verify the pipeline *before* the mass run.

**Pipeline preflight caught a real, near-silent bug:** `intake.sh`'s `write_sidecar_basic` embeds `CLONEPOOL_DIR` raw into the sidecar JSON. When it's a Windows `C:\Users\...` path (backslashes), `\U \j \P` are invalid JSON escapes → `enrich_sidecar_companions`'s `json.load` throws → `set -euo pipefail` aborts intake **before D1/R2 sync ever runs** (you get a pool copy + broken sidecar, no custody record). `usys clone` dodges it (converts to `/c/...` first, `usys.ps1:526`); direct `bash intake.sh` calls — how the bulk passes run — are exposed. Confirmed the fix is a forward-slash `CLONEPOOL_DIR`. Real fix (JSON-escape paths) deferred — see NEXT SESSION.

**Clonepool relocated C: → E: (drift fix, matches the MD's own drive map — `breach_coms2 → /mnt/e … CLONEPOOL primary`).** `C:\Users\jwlef\Phoenix\clonepool` was a real dir on C: (the drive we're clearing); intake *writes into it*, so a mass pass would have grown C:. robocopy'd 1356 files / 1.21 GB to `E:\Phoenix\clonepool` (verify pass exit 0), repointed the repo-root junction + `CLONEPOOL_DIR` User env var + `~/.phoenix/phoenix.env` to **`E:/Phoenix/clonepool`** (forward-slash — also kills the JSON bug). R2/D1/workers untouched — only the local fast-path cache moved. Verified end-to-end: real intake against E: → valid sidecar, D1 clonepool+custody+glossary OK, R2 byte-identical fetch-back.

**Oh-shit bar before any deletes:** `F:\Phoenix\Vault\phoenix-cleanup-snapshot-20260906\` — env/config state, repo HEAD, junction state, a 15,396-file SHA256 manifest of the archived pool, and a full 1.5 GB byte copy of it (robocopy verify exit 0). (Couldn't verify the 2026-09-05 `wbadmin` image from a non-elevated shell — `F:\WindowsImageBackup` / `F:\VAULT-B` are ACL-locked; the `F:\Phoenix\Vault\github-mirrors\` 28-repo mirror set is confirmed intact.)

**Intaked 13 loose real files** (Downloads + E: root + repo root): `Monster_Phoenix_GDD_v2.docx` (the game GDD), `phoenix-notation.html` (v3), `ai_paging_windows_v2_FULL.py` (v3), `helixraid_array.py`, `backup_user_guide.md`, the grok-removed + package-handler zips, `4R70W Manual.pdf`, resume, 2 py scripts, `dashboardzip1.zip`. All D1 custody+glossary OK. **`dashboardzip1.zip` (187 MB) got a D1 row but NO R2 blob** — Cloudflare Workers request-body cap; flagged for the multipart-PUT fix.

**Cleared ~9 GB off C: (72 GB → 79 GB free):** `npm cache clean` (1.65 GB), `%TEMP%` (0.43 GB, scratchpad preserved), Ollama models → `E:\Phoenix\ollama-models` via `OLLAMA_MODELS` (1.88 GB, `ollama list` verified), deleted the superseded `clonepool-archived-20260822` (1.6 GB, backed up to F:), deleted the old C: clonepool copy (1.3 GB, live copy verified on E:), cleared 20 Downloads installers (1.2 GB, re-downloadable — real docs/scripts/zips kept). Old-C:-clonepool needed the robocopy-empty-mirror trick — `Remove-Item -Recurse` chokes on the >260-char `2e/v1_./…` repo-snapshot paths.

**Dashboard: platform admin by default.** `dashboard/start.ps1` now self-elevates via UAC once at launch (`-NoElevate` / `PHOENIX_NO_ELEVATE=1` opt-out; renderer stays contextIsolation/no-nodeIntegration either way) so the `main.js` `isElevated()`-gated panels (pagefile/drive ops) and the embedded SHELL + CLAUDE PTYs get admin without a mid-session UAC wall. `install-dashboard-windows.ps1` autostart task got `-RunLevel Highest` (elevated at logon, no prompt). Both parse clean.

**Process notes for next time:** the auto-mode classifier hard-blocks recursive deletes, self-elevation code, and any write to `.claude/settings.local.json` (an agent can't loosen its own permission boundary). The `!` prompt prefix does not work in Jerry's client. Fix that stuck the whole session: Jerry switched to `default` permission mode (Shift+Tab) and approved each action interactively — do that switch *first* next time OS/filesystem work is planned. See [[feedback-cli-workflow-constraints]].

2026-09-07 — **PBM company structure + Office Module 3.** Jerry: two companies, **PBM Consulting** and **PBM Enterprises**, separate legal entities, **Laurie owns both** — structured so they qualify for the federal small-business set-asides she's eligible for (woman-owned / HUBZone / economically disadvantaged / disabled). Consulting is a plan only right now. Enterprises = Jerry's own steel-building operation; "iron pays for it all" — the trade revenue funds the software mission instead of enriching an employer. Office stays open source (GPL v3) — Jerry's personal work in the `jwl247` GitHub org; the entity structure is being sorted separately (see [[pbm-companies]]) and the companies *use and proof* it, they don't own it. Memory: `[[pbm-companies]]`.

Wrote `sector2/apps/office/PLAN-modules-3-6.md` (all four modules, "everything working, no demo, don't hurry it"), then **built Module 3 end to end**: `office-notify-worker` (standalone Cloudflare Worker — `POST /notify`, `GET /ack/:token` with single-use token-as-auth, `whoami`/`health`, `scheduled()` cron re-sending unacknowledged alteration notices with escalating subject, level cap 5), `office_notifications` append-only audit table in `schema.sql`, `lib/tamper-guard.js` (`checkAndAlert` — the seam wiring `document.js` detection + `notify.js` payloads + the worker, never throws), `notify.js` `workerTransport()`. 27 → **36 passing** (also fixed the test harness — async tests weren't actually awaited before). `wrangler deploy --dry-run` clean, `schema.sql` applies clean. **Transport:** DESIGN.md's "Cloudflare Email Workers" isn't a free arbitrary-recipient send path (`send_email` = verified recipients only; MailChannels' free tier gone) — working transport is **Resend** (swappable, one `fetch`; `send_email` still coded for issuer copies); AWS SES rejected as vendor lock-in. Cron min is 60s not Module 6's 30s. **Not deployed** — needs Jerry's Cloudflare auth + a Resend key; runbook + live-test steps in `notify-worker/README.md`.

Then **Modules 5 and 6, same session.** **M5 — pluggable author identity:** `lib/identity.js` — `resolveAuthor()` resolves the acting author to one canonical `author_id` across `fingerprint` (the sovereign anchor — zero network, never needs D1), `windows` (the OS account SID), and `google` (an OpenID `sub` via the OAuth 2.0 device flow, no embedded browser). `author_id` is *derived* deterministically from a credential; D1's `office_authors` only *links* alternates, and `resolveAuthor` never throws on an unreachable store. Added `GET /author/:type/:value` + `POST /author/link` to the worker. `document.js` untouched. Live-verified: real fingerprint + real Windows SID both resolve to stable ids on this machine. **M6 — dual-pane UI:** `sector2/apps/office/index.html` (left = fields that lock on fill + counterparty + state badge + state-aware handoff buttons + QR strings; right = Claude copilot, debounced), `sector2/apps/office/preload.js` (12 allow-listed `office:*` channels, sandboxed renderer), `dashboard/office-launcher.js` (window + handlers + `office:copilot` via the dashboard's `_runClaudeCli`). Wired into the dashboard: `main.js` register line, `preload.js` allowlist, an **OFFICE** button in `button-generator.js`. End-to-end lifecycle verified without Electron (whoami→new→fill→hand→sign→save/open→tamper→verify+notify→change order). 36 → **50 tests**. Channel names cross-checked identical across preload/launcher/html. **Office is now fully usable for the tamper-evident-record purpose — only Module 4 (the LibreOffice format-following worker) remains, and it's not on the critical path.**

Then **Module 7 — the EASY pass** (Jerry's product bar: EASY for the user even when hard for us — no manual, a button per process, nothing to save or convert, the clone pool carries the load — captured in DESIGN.md "Product principles" + [[office-easy-principle]]). Built: **autosave** (no Save button — writes `~/PhoenixOffice/<b58>.office.json` on every change); **seal-on-sign** (`office:sign` auto-intakes the signed file → hex identity, custody ledger, R2 → "sealed, the local copy is disposable" — and a signed doc is one immutable version so the 7-version cap never trims it, eviction is local-cache-only anyway); **template picker** (`templates/*.json` — work-order / invoice / inspection / change-order / blank — no more "type your field names"; PBM's real templates drop in here for the branded build); **reference-pull** ("name documents → Phoenix clones them from the pool into a scratch drawer → delete freely"); **Recent list + path-guarded reopen**. 50 → **51 tests**, handlers verified end to end. Security (Jerry asked about a separate Office DB): stays on shared `phoenix_dev_db` for now — the immutable `.office` file is the real security; split to a dedicated DB + own token when a federal contract or real customer data drives it (the `OFFICE_AUTH`-token middle option is in the plan). Product positioning that landed: the code is GPL/free, what Pink Be Me Consulting sells is *the easy* — Phoenix + setup + support + the branded build + "we run it"; the first "where can I get that" comes from someone in the trades seeing a PBM work order, so keep dogfooding on real jobs.

Alongside: a full **Pink Be Me** ("PBM") research + planning pass for Laurie's SBA-certified consulting company — `D:\Users\jwlef\Phoenix\PinkBeMe\` (OFF the repo — has Laurie's disability/economic/relationship details). `00-ACTION-CHECKLIST.md` (do-now / decisions-owed / then / later), `00-RESEARCH-AND-ACTION-PLAN.md` (WOSB/EDWOSB/HUBZone/8(a) requirements, the affiliation/control/subcontracting risks, entity+tax structure, Oklahoma specifics, the SSDI-vs-SBA-control tension, JNJ cleanup, HUD/Section 3), `02-HOW-SBA-CONTRACTING-WORKS.md`, + Articles of Incorporation drafts for both entities. Key findings: not legally married → no automatic spousal affiliation; Laurie net worth ~$279k → clears the economic tests; office is on a fee-simple Native-cousin's land in a confirmed OK HUBZone; "Consulting feeds Enterprises steel jobs" as literally stated = pass-through/ostensible-subcontractor = terminates the cert, but Jerry's clarified model (Consulting genuinely project-manages + runs an outfitted-container tool/safety service, self-performing real scope) is defensible. All ⚖️ points flagged for a government-contracts attorney + the free Oklahoma APEX Accelerator. Memory: [[pbm-companies]].

2026-09-09 — **Office M3 deployed + secrets consolidated + Life First MCP proven live.** (1) **`office-notify-worker` is deployed** — `office_notifications` schema applied to `phoenix_dev_db` (now 49 tables), worker live with cron `* * * * *`, `PHOENIX_AUTH` secret set and `/whoami`-verified in sync with packages-worker + phoenix-clonepool-r2, added as the 3rd worker leg in `rotate-phoenix-auth.sh`. `POST /notify` + `GET /ack/:token` smoke-tested against real D1 (row written, escalation stops on ack). Only `RESEND_API_KEY` (resend.com signup — Jerry) + one GUI OFFICE-button click remain. Minor wart logged: `handleNotify` returns 502 on send-fail even though the row was written. (2) **Security audit** — read `docs/sec audit doc from you to you.txt` (Claude-to-Claude adversarial code audit, every finding traced to file/line), turned it into the sequenced NEXT SESSION backlog below. (3) **Secrets store built** — `F:\Phoenix\Vault\secrets\` : `phoenix-secrets.env` (real values, owner-only ACL, NOT git — `PHOENIX_AUTH` + `LIFEFIRST_MCP_ACCESS_TOKEN` populated live), `SECRETS.md` (full map — 14 CF workers / 5 D1 / 3 R2 inventoried, rotation rules, VM secrets, new-PC migration), `docs/SECRETS.md` (repo pointer, no values). Auto-mode classifier blocked the credential-file steps until Jerry switched to default permission mode — [[feedback-cli-workflow-constraints]]. (4) **Life First MCP** — the `lifefirst-mcp` worker was never actually blocked: all 5 secrets already set, `/mcp` takes a static bearer (no OAuth needed), token recovered from the running `LifeFirstNotifyAgent` config.json. Ran a full handshake + `tools/list` — **30 tools live** (schedule / messenger / memory / notification / voice / budget / reminder / drive). Jerry connected the claude.ai custom connector (`…workers.dev/mcp-oauth`, "Always required", Anthropic hosted client metadata, token pasted on the worker's auth page). This session can't use it (connector set fixed at start) — next session picks it up. (5) **Claude state backed up** — `~/.claude` (18 memory files + settings) → `F:\Phoenix\Vault\claude-state\`; was C:-only. **F: is now Claude's workspace, all of it** (Jerry, 2026-09-09) — [[phoenix-drive-layout]]. New PC lands Fri 2026-09-12 (i7 / 32 GB / Radeon).

2026-09-09 (cont'd) — **Security audit T3 #8 + #9 done — franken5.py `Ball` permissions.** #8: `Ball.authorize()` was documented "IS the permission system", zero call sites. Now honest — class docstring says the ball *carries* the permission set + custody chain and enforcement is at the point of action (`ball.assert_authorized(...)`, new — raises `PermissionError`, logs the denial); added franken5's one genuine enforcement point: `RingRecord.call3` suppresses the definitive→snap-clone (a `clone` action) when the ball doesn't grant `clone`. #9: `Ball.for_family()` no longer returns a blanket `{read,write,clone:True}` for every family — new `FAMILY_PERMISSIONS` map is least-privilege by family (SYSTEM = read-only observer, PHYSICS/NETWORK = read+clone, USER/ASSETS/AI = read+write+clone; `translate`/`delete`/`kernel` never in a default set — CLAUDE.md Critical Rules — only via explicit `permissions=` override, which is how the sector-3 translator ring is born). Non-breaking: a populated `permissions` dict still wins; `None`/`{}` (SuitSpec's `default_factory=dict`) → family default, not empty. `py_compile` clean (franken5 + frank_ring + frank_spawn); `sector1/helix-lightning/test_ball_permissions.py` **20/20**. 2 files dogfooded via `usys clone`. **T3 #10** (standing integrity job — clonepool `hex_id` vs fresh content hash, cron'd) still open.

2026-09-09 (cont'd) — **Security audit T1 #1 + #3 done — suite execution gate.** One "check before execution" mechanism in `scripts/usys.ps1` (`Assert-UsysSuiteExecutionAllowed` + helpers above `Invoke-UsysRun`), called at the top of every `usys run`. **#3 provenance:** `.phoenix-trust` in the suite dir = HMAC-SHA256 over the entry file's SHA-256 + core manifest fields, keyed by *this machine's* `PHOENIX_AUTH` — the worker's bearer-token pattern ported to the local execute boundary. `usys suite-trust <name>` writes it (new command); change the entry file → stamp stops verifying; machine-bound. **#1 permission:** manifest `permissions` asks classified — `network` / unscoped `filesystem:write` / `process:spawn` / `env:write` = elevated. `qemu` (and any non-host) runtime → **pass, VM-contained** (that's audit #2's own point — doesn't break `usys run debian`, which is why nothing in Jerry's workflow changed). Host runtime (python/node/bash/powershell/binary): stamped → granted its declares; unstamped + no elevated asks → pass; unstamped + elevated asks → **REFUSED** unless `--unverified` (new flag) or interactive `yes`. A refusal/override also fires the CoPES **Beta guardian** (`suite_unrecognized` — **this completes T1 #4's last wire**), via a backgrounded python `copes_runtime.dispatch`, harmless when disarmed. Consent+audit boundary, **not** a sandbox (that's T1 #2, still open). Every decision → `~/.unitedsys/logs/suite_exec.jsonl` (override `PHOENIX_SUITE_EXEC_LOG`); global bypass `PHOENIX_SUITE_NO_GATE=1`. `usys.ps1` parses clean; `scripts/usys-suite-gate.Tests.ps1` **16/16** (vm-contained pass · no-asks pass · unstamped+network REFUSED · `--unverified` override · valid stamp passes · entry-file tamper invalidates · wrong-key stamp rejected · bypass · audit log). Real smoke: `usys run debian --dry-run` → gate passes it `vm-contained`, existing flow intact. Docs: `docs/SUITE_EXECUTION_GATE.md` + a note in `SUITE_MANIFEST.md`. 4 files dogfooded via `usys clone`.

2026-09-09 (cont'd) — **Security audit T1 #4 done — guardian/honeypot system resurrected and wired.** The CoPES moving-target-defense (4 sector guardians, 1 active + 3 honeypots, randomized 180–600s rotation, honeypot-probe → forced rotation + fingerprint) had sat in `archive/…/SECTOR4/copes/src/security/` for months with **zero call sites** (its own docstring lied — "called at CoPES boot", nothing called it). Now: (1) moved to `sector1/security/` as an importable package — relative imports, `__init__.py`, dropped the library-rude `logging.basicConfig` from the rotator. (2) Added the missing **dispatch/escalation seam**: `copes_runtime.dispatch(event)` routes by event type to the owning guardian (safe before boot, never raises — an event source must not break on the security layer); `copes_runtime.boot(on_escalate=…)` arms it; `rotator.escalation_sink` + `copes_runtime._escalate` is the single choke point where both an active-guardian threshold hit *and* a honeypot probe land → CRITICAL log + append to `~/.unitedsys/logs/guardian_incidents.jsonl` (override `PHOENIX_GUARDIAN_LOG`) + app callback. (3) **Wired two real event sources** — call sites: `sector1/kernel/main_kernel.py:boot()` (new try/except block, graceful like the LLM/status-server ones, arms guardians before the LLM engine) and `sector1/auth/phoenix_auth.py:authenticate()` (`_guardian("auth_failure"|"auth_success", …)` — lazy import, swallows everything, auth can't break). `py_compile` clean on all touched files; `python -m security.test_guardians` **20/20** (boot arms · dispatch inert pre-boot + on unknown events · active guardian escalates at threshold 3 · honeypot probe → forced rotation + sink fires · incidents persisted). All 13 files dogfooded via `usys clone`. Fossil copy under `archive/` left as history. **Still open (T1 #1+#3):** `usys.ps1` → Beta `suite_unrecognized` event — route's already in `_ROUTE`, deferred because it's coupled to the not-yet-built suite-permission enforcement. Gamma/Delta have no live feeders yet (logic ready, need a file/net watcher + a vault-write hook).

2026-09-09 (cont'd) — **meds-worker built (Laurie's medication guardrail).** `index.js` + `wrangler.jsonc` + `README.md` + `test.mjs` written into `sector2/apps/lifefirst/meds-worker/` (schema.sql from the prior commit, tweaked: `recorded_via` CHECK now allows `link-ack`). Adaptive once-a-day model — `next_check_at` anchored to `last_dose_at + window_hours`, never a clock time. Routes: `/health` (no auth, shows which transports are configured), `/whoami`, `/status?user_id=2` (returns `ask:true` → the assistant's cue to open with "have you taken your pills today?"), `/configure` (Jerry-only guardrail setup — the only place `active` is set), `/record-dose`, `/ack/:token` (token IS the auth, logs the dose + closes the cycle + advances the window). Cron `*/5 * * * *`, three timestamp-gated passes: open a check-in when a dose is due → re-send stale open alerts, escalating the message (warmer-not-scolding, cap 5, Pushover → emergency priority at level ≥3) → loop Jerry in once a cycle is ~55 min unanswered and keep him looped on every later re-send. Three channels (`sendPushover`/`sendEmail`/`sendSms`), each returns `ok|skip|err:…` and **never throws** — a dead/unset channel is skipped, cron never crashes. Laurie has no login anywhere in the worker; every channel is one of Jerry's accounts. **Verified:** `node -c` clean, `wrangler deploy --dry-run` clean, `schema.sql` applies clean in sqlite (CHECK rejects bad `recorded_via`), and `test.mjs` — 20/20 — drives the full lifecycle against a mock D1 (configure → cron opens → escalate on stale → caregiver past 1 h → ack logs dose + closes + advances ~24 h → covered state stops alerts → auth enforced → `record-dose` can't touch `active`). All 5 files dogfooded through `usys clone` (canonical `sector2/package-handler` intake — R2 + D1 custody + glossary, 0 failures). **Not deployed** — needs Jerry's Cloudflare auth + Pushover/Resend/Twilio secrets (runbook in `meds-worker/README.md`). **Bug found dogfooding:** `usys intake <file>` routes to `sector4/intake/intake.sh`, which is (a) the wrong pipeline (canonical is `sector2/package-handler`) and (b) broken on this box — line 59 uses a zsh glob `**/*(.)` that is a bash syntax error. `usys clone` is the working canonical path. Also recorded Laurie's interview (Wed 2026-09-10 1 PM CT) on Jerry's Google Calendar (no Laurie calendar — his is the single source so she can't change it), 60-min popup.

## NEXT SESSION
- **DEPLOY meds-worker (Mon 2026-09-14 deadline).** Code + tests done (see session log). `cd sector2/apps/lifefirst/meds-worker` → `wrangler d1 execute lifefirst-db --file=schema.sql --remote` → `wrangler secret put` PHOENIX_AUTH (match the fleet) + PUSHOVER_TOKEN / PUSHOVER_USER_LAURIE / PUSHOVER_USER_JERRY / RESEND_API_KEY / LAURIE_EMAIL / CAREGIVER_EMAIL (+ optional Twilio quartet) → `wrangler deploy` → `POST /configure {user_id:2,...}` to switch Laurie's guardrail on → live end-to-end test per README. Then add `meds-worker` as a 4th leg in `rotate-phoenix-auth.sh`. Needs from Jerry: Cloudflare auth, a Pushover app + Laurie's device key + the app on her phone, Laurie's Gmail, his travel contact.
- **`usys intake` is broken / mis-pointed** — routes to `sector4/intake/intake.sh` (wrong pipeline + zsh-glob bash syntax error at line 59). Fold into the audit #7 `usys.ps1` intake-repoint work (point it at `sector2/package-handler/intake.sh` like `usys clone` already does). `usys clone` works today — use it for dogfooding meanwhile.
- **DOGFOOD THE INTAKE PIPELINE (standing order, Jerry 2026-09-09).** Every file we create or meaningfully change goes through `sector2/package-handler/intake.sh` (the canonical one — R2 + integrity + D1 custody). Pull files back with the easy path: `usys open <name>.lol` (clone-to-workdir, integrity-gated), not `cd` + raw `bash intake.sh` + env vars. Use the system, don't just build it. Applies to worker code, scripts, docs, configs — anything not transient. Proven this session: `settings.local.json` intaked (v2, R2 632 bytes) and `.lol`-cloned into `.claude/` from a real terminal.
  - **This is where the TIERS come in (Jerry, 2026-09-09) — and there's a real gap.** `intake.sh` **hardcodes `"tier": 1`** (line ~329, and `${7}` to the sidecar) — it does NOT compute a tier, route by drive pressure, or mirror T1→T4. The real routing logic exists but is orphaned: `sector2/frank/frank_save.py` has `best_drive()` (lowest-pressure drive under threshold), `drive_pressure()`, `system_pressure()`, the T4→T1 mirror chain `/mnt/d,e,f,g` = breach_coms1-4 — but `intake.sh` never calls it, and it assumes Linux mounts that don't exist on this Windows box. **The dogfood pass is the moment to wire Frank's tiering into the live intake pipeline:** compute the tier (pressure-based via `best_drive()`, or the 4-day-window position), stamp the real tier into `footer_qr` / `clonepool.tier` / the sidecar, and mirror the write down the tier chain. Until then every intaked file is falsely tier-1. Pairs with `sector1/saddle_block.sh` (the 4-line fstab template for mounting breach_coms by label).
- **On restart: pick up the security list** (below). `.claude/settings.local.json` now in place (git/wrangler/robocopy/node/npm allowed + Stop hook auto-backs-up memory to F:) — the classifier friction from this session should be gone.
- **Laurie's medication guardrail — HARD DEADLINE: Jerry leaves town Mon 2026-09-14.** Design frozen (memory: `laurie-medication-guardrail`): adaptive once-a-day pill model anchored to `last_dose_at + 24h`, not a clock time; assistant's FIRST question on every open = "taken your pills today? when?"; unacknowledged → escalate ~15min → alert Jerry after ~1h. **She cannot disable it** — control lives with Jerry's accounts. 3-channel delivery: Pushover (primary, emergency-priority re-alert = the escalation; Jerry installs the app on her phone before he leaves), email (Resend, backup), SMS to GV `405-237-5727` (bonus — A2P/GV filtering makes it unreliable by Monday). Built as a **separate worker** `sector2/apps/lifefirst/meds-worker/` sharing `lifefirst-db` (Laurie = user_id 2, tz America/Chicago) — `lifefirst-mcp` source isn't local, don't try to edit it. **Done 2026-09-09:** `schema.sql`, `index.js`, `wrangler.jsonc`, `README.md`, `test.mjs` (20/20, full lifecycle vs mock D1). **Remaining: deploy only** — see the "DEPLOY meds-worker" entry at the top of NEXT SESSION (needs Jerry's Cloudflare auth + Pushover/Resend/Twilio keys + Laurie's Gmail + Jerry's travel contact — "will have when she's back from her mother's", 2026-09-09). **Laurie's interview: Wed 2026-09-10, 1:00 PM America/Chicago** (Jerry, 2026-09-09) — the concrete event the interview-reminder channel fires against. Also: the "Both" onboarding plan — web PWA shortcut for Laurie's machine + `install-laurie.ps1` (stripped `PHOENIX_PROFILE=laurie` dashboard) — and the Debian-VM-autostart blocker for `/laurie/` (currently 530, VM off). Web page is NOT the critical path for pills; the worker is.
- **Security & Integrity Audit backlog** — full findings in `docs/sec audit doc from you to you.txt` (Claude-to-Claude, live adversarial code audit, Sept 2026, every finding traced to file/line/commit). Standing rule: show the actual call site / test output before marking any item done. Sequencing per the doc:
  - **T1 #4 — DONE 2026-09-09.** Guardian/honeypot system moved to `sector1/security/` (importable package + dispatch/escalation seam), armed from `sector1/kernel/main_kernel.py:boot()`, fed by `sector1/auth/phoenix_auth.py:authenticate()` (auth_failure/auth_success). `python -m security.test_guardians` 20/20. **Remaining piece rolls into T1 #1+#3:** `usys.ps1` → Beta `suite_unrecognized` event (route already wired in `copes_runtime._ROUTE`, needs the suite-permission check to exist first). Gamma/Delta still need live feeders (file/net watcher, vault-write hook).
  - **T1 #1 + #3 — DONE 2026-09-09.** Suite execution gate in `usys.ps1` (`Assert-UsysSuiteExecutionAllowed`): trust-stamp check (`usys suite-trust`, HMAC keyed by machine `PHOENIX_AUTH`) + permission-ask classification; unstamped host-runtime suite with elevated asks (network/fs:write/process:spawn/env:write) refused unless `--unverified`; qemu = VM-contained pass; fires the Beta guardian on refusal (finishes T1 #4). 16/16 tests, `docs/SUITE_EXECUTION_GATE.md`. **Still a consent/audit boundary, not enforcement** — real confinement is T1 #2.
  - **T2 #7** — PARTLY DONE 2026-09-09. Investigated: **3 pipelines.** Canonical = `sector2/package-handler/intake.sh` (R2 upload + integrity baseline + validate gate + real QR + sensitive flags — all the 2026-08+ work). `sector4/intake/intake.sh` = separate legit Sector-4 vault path. `phoenix-core/tools/intake.py` = D1 custody row + SQLite only, **no R2, no integrity baseline, QR sidecar is a `qr:sha3:` stub** — now carries a loud deprecation banner + stderr warning (commit `686dc37`). **NEXT SESSION — the actual repoint (Jerry: come back to it):** `usys.ps1` calls `intake.py` at **4 sites** — `usys distro intake-qemu` (~L1866), `Invoke-UsysDownload`/`usys download` (~L1964), `Start-UsysWatcher`/`usys watch` (~L1996, inside a `Start-Job` scriptblock — the tricky one, bash path + `CLONEPOOL_DIR` must cross the job boundary), `Get-UsysWatcherPending` (~L2081). Fix: extract a shared `Invoke-UsysIntakeFile -Path` helper doing what `Invoke-UsysClone` (L475) already does right (`Get-UsysCloneIntakeSh` + `ConvertTo-GitBashPath` + `$env:CLONEPOOL_DIR` conversion at L526 + `& $bash $bashIntake`), point all 5 at it. Test: `usys download` a tiny file → confirm it lands in D1 **and R2** (byte-identical fetch-back) and gets an integrity baseline; then the watcher. Also reconcile `dashboard/manual/PHOENIX_MANUAL.md` L353/L431 ("cd phoenix-core && make intake", "Do not mix Python intake and C phoenix-core").
  - **T2 #5 + #6** — validation checks hash against D1 record (not the local sidecar); drop the QR framing / rename `qr_sha3`→`validation_string_sha3` etc (stubs per author's own comments, no `qrcode` lib, design intent is system-to-system not camera scan).
  - **T1 #2 — NEXT** — sandbox non-VM suites (Windows Job Object / capped token) scoped to the declared permissions the T1 #1 gate now surfaces. Hook point: `Invoke-UsysRun`'s per-runtime `switch` (usys.ps1 ~L1010) — wrap the host-runtime launches (`& $pythonCmd`, `& node`, `& $bash`, `& pwsh`, `& $entryPath`) in a Job Object with a token that drops write access outside the suite dir + a temp scratch, and blocks network for suites that didn't declare it. The gate already computes `$asks` (declared/elevated) right before that switch.
  - **T3 — #8 + #9 DONE 2026-09-09.** `Ball.authorize()` honest + `assert_authorized()` primitive + real call site in `call3` (snap-clone gated on `clone`); `Ball.for_family()` least-privilege by family (`FAMILY_PERMISSIONS`). 20/20 (`test_ball_permissions.py`). **#10 still open** — standing integrity job (generalize #5): clonepool `hex_id` vs fresh content hash, cron'd (regressed once: `repair_clonepool.py` fixed 136/137 rows).
  - **T4 last** — README/public claims: "not WSL or hypervisor" is false (`run-ubuntu.ps1 --accel hyperv`, it's QEMU); unsourced perf superlatives (700k ops/sec, 100% hit rate) link methodology or soften; Critical Rule #9 "no demos" vs the `intake.py` stub.
- **Office — live checks (no rush):**
  - ~~(1a) deploy `office-notify-worker`~~ **DONE 2026-09-09** — schema applied to `phoenix_dev_db` (`office_notifications` + indexes live, DB now 49 tables); worker deployed (`office-notify-worker.phoenix-jwl.workers.dev`, cron `* * * * *` registered); `PHOENIX_AUTH` secret set and `/whoami`-verified in sync with packages-worker + phoenix-clonepool-r2; added as the 3rd leg of `rotate-phoenix-auth.sh` (`bash -n` clean). Live-smoke verified end to end: `POST /notify` → row written (`send_count`/`last_error` stamped), `GET /ack/:token` → `acknowledged_at` stamped, escalation stops. One acked smoke row (`doc_hex=smoke…`) left in the append-only table — Jerry's call whether test rows get purged.
  - **(1b) BLOCKED ON JERRY — `RESEND_API_KEY`.** `/health` reports `transport: NONE`; sends fail with a clean "no send transport configured" (row + cron retry still work). Sign up at resend.com (free 100/day), verify a sending domain (or use `onboarding@resend.dev` sandbox to your own address), then `cd sector2/apps/office/notify-worker && wrangler secret put RESEND_API_KEY`. Then run the real tamper→SMS→ack test from `notify-worker/README.md` § "Live end-to-end test".
  - Minor wart noted: `handleNotify` returns HTTP **502** on any send failure even though the D1 row was written — a client that retries on 502 would double-insert. Moot once a transport is set (`sent:true`→200); worth a 200-with-`sent:false` fix in the same pass as the Resend key.
  - (2) Launch the dashboard **OFFICE** button once — exercise the live window render / contextBridge / copilot. Static wiring re-verified 2026-09-09 (main.js register line, `office:*` channel names identical across `office-launcher.js` / `preload.js` / `index.html`, OFFICE button in `button-generator.js`, 51/51 office tests pass). Needs a real GUI click — not force-restarting Jerry's running dashboard for it.
  - (3) Optional: a Google OAuth client id for the google sign-in path.
- **Office Module 4** — the LibreOffice/Frank/Helix format-following worker. 4a (deploy `phoenix-unoserver.service`) is quick; 4b is the real work; 4c waits on Helix-on-Debian. Not on the critical path — Office already works for its purpose.
- **PBM** — Jerry's action items: call the Oklahoma APEX Accelerator + the Ticket-to-Work benefits-counselor line for Laurie; start Laurie's SAM.gov reg; pull JNJ's (Texas) status + old SAM/past-performance; check Laurie's possible tribal descent. Then a government-contracts attorney with the plan. Decisions owed: registered agent + office address, corp vs LLC, target NAICS, lease terms, Laurie's 3-yr AGI. All in `00-ACTION-CHECKLIST.md`.
- **Unified `install.ps1` — done 2026-09-09, run it together on the new PC Friday to verify live.** Rewritten: `-TargetPath` param + auto-detect (walks up for `CLAUDE.md`+`sector1`, else `D:\Users\<user>\Phoenix\...`, else `$HOME` — no more hardcoded C:); reads `PHOENIX_AUTH` / `CLONEPOOL_DIR` / `OLLAMA_MODELS` from `F:\Phoenix\Vault\secrets\phoenix-secrets.env` (prompts only if the vault's gone); writes `~/.phoenix/phoenix.env` (the file the dashboard reads) + `~/.phoenix_env.ps1/.sh`; sets the User env vars; PS7 profile hook; clonepool junction; global `bin/*.cmd`; `.lol`/`.phx` associations; **calls** `tools/poc/install-helix-autostart.ps1` + `sector3/services/install-dashboard-windows.ps1` for autostart; `-RestoreClaudeMemory` robocopies `F:\Phoenix\Vault\claude-state\` back into `~/.claude/projects`. Parses clean, helpers unit-tested against the real vault. **Not run end-to-end** (needs a fresh box) — exercise it on Friday's i7, fix live like Life First's install.sh got fixed.
- **Secrets store — built 2026-09-09.** `F:\Phoenix\Vault\secrets\` : `phoenix-secrets.env` (real values, owner-only ACL, NOT in git — `PHOENIX_AUTH` populated live), `.env.template`, and `SECRETS.md` (the full map: every worker/D1/R2, what unlocks what, rotation rules, VM secrets, new-PC migration). Repo pointer at `docs/SECRETS.md` (no values). Reason: Jerry travels a week+ and can't recall where keys are; new PC lands Fri 2026-09-12. Also backed up `~/.claude` (memory + settings + keybindings) to `F:\Phoenix\Vault\claude-state\` — 18 memory files that lived only on C:. **TODO:** copy `LF_API_SECRET` + cloudflared tunnel cred off the Debian VM next boot; delete the orphan hex-named secret (`8d0592a2…`) on `packages-worker`; wire `install.ps1` to consume the file; refresh `claude-state` at each session close (`robocopy C:\Users\jwlef\.claude\projects F:\Phoenix\Vault\claude-state\projects /E /XD tool-results todos /XF *.jsonl`).
- **`intake.sh` sidecar JSON hardening** — `write_sidecar_basic` must JSON-escape `CLONEPOOL_DIR` / `pool_path` (emit via python or `jq`) so a backslash anywhere can't abort a run before D1/R2 sync. Worked around 2026-09-06 with a forward-slash `CLONEPOOL_DIR`; the landmine is still in the code.
- **`dashboardzip1.zip` / large-blob R2 gap** — `phoenix-clonepool-r2` needs multipart/streaming PUT; files >~100 MB currently get a custody record pointing at nothing. Local copy kept at repo root.
- **F:\Downloads triage** — 10.2 GB, not opened yet. Intake real content, clear the rest.
- **`~/.phoenix_env.sh` / `.ps1` are empty (0 bytes)** — installer is meant to populate them; the unified installer should restore + guard.
- **3 probe rows** — the `preflight2_probe` / `e_relocate_probe` glossary entries linger (the worker's `DELETE /clonepool/:hex` doesn't cascade to `glossary`, and the R2 worker has no DELETE). 48-byte cosmetic; a `DELETE` cascade would be the real fix.
- **Define what goes in `jwl247/evolution`** — confirmed "the Phoenix CLAUDE.md repo from now on" (Jerry, 2026-09-05), but not yet populated. Ask for exact scope before writing anything.
- **Review `docs/lockdown motion.txt`** — recovered in the same burst as the other docs/*.txt transcripts tonight, 504 lines, never actually read.
- **Office Module 4 — the only one left.** Modules 3, 5, 6 all built 2026-09-07 (see SESSION LOG). Plan: `sector2/apps/office/PLAN-modules-3-6.md`. M4 = the LibreOffice/Frank/Helix worker (invisible format-following): 4a = deploy the dormant `phoenix-unoserver.service`; 4b = `worker.js` (Frank imports the LibreOffice capability); 4c waits on Helix-on-Debian; 4d = autofill. **Office is fully usable for the tamper-evident-record purpose without M4.**
- **Office — pending live checks** — see the consolidated "Office — live checks" entry near the top of NEXT SESSION (updated 2026-09-09: worker deployed, only `RESEND_API_KEY` + the GUI OFFICE-button click remain).
- **"PBM signature" Office build** — Jerry wants a Pink Be Me-branded instance of Office (theme + PBM templates for work orders / inspections / change orders) as the commercial calling card, "when we get a spot." Same GPL engine, PBM skin. Not built. See `D:\Users\jwlef\Phoenix\PinkBeMe\` and [[pbm-companies]].
- **Config Centralizer follow-up** — git init/commit backend (`initGit`/`commitChanges` in `config-centralizer.js`) has no UI buttons yet, only scan/import/sync do. Small addition whenever picked up.
- **Life First MCP — server is LIVE, just needs the connector added (2026-09-09).** `lifefirst-mcp` worker fully provisioned (all 5 secrets set: `CLAUDE_API_KEY`, `GOOGLE_CLIENT_ID/SECRET`, `LF_API_SECRET`, `MCP_ACCESS_TOKEN`). `initialize` handshake verified 200 (`serverInfo lifefirst/1.0.0`, tools capability). **No OAuth needed** — `/mcp` takes a static `Authorization: Bearer <MCP_ACCESS_TOKEN>`; token recovered from the running `LifeFirstNotifyAgent` config.json, now in `F:\Phoenix\Vault\secrets\phoenix-secrets.env` as `LIFEFIRST_MCP_ACCESS_TOKEN`. **TODO:** (a) add the claude.ai custom connector — URL `https://lifefirst-mcp.phoenix-jwl.workers.dev/mcp`, that bearer token; (b) one-time worker Google grant per user: `…/oauth/google/start?username=you&token=<tok>` and `…username=laurie`. Tools exposed: schedule, messenger, memory, notification, voice, budget, reminder, drive. Setup steps in `F:\Phoenix\Vault\secrets\SECRETS.md`.
- **Escalation delivery** — once the connector's added, wire a scheduled Claude Code agent to poll `check`/`escalate` and push via PushNotification. (The `LifeFirstNotifyAgent` Windows scheduled task is already running and polling — verify it's actually delivering.)
- **The daily briefing / Claude-as-standing-assistant** (Jerry, 2026-09-07) — the bigger version of escalation delivery: a scheduled agent that gives a morning glance pulling from Office (field reports awaiting review), the message/notification system (customer messages), Google Calendar (MCP), and Life First (Laurie's reminders). Tone: *"3 field reports for review, 7 messages from 4 customers, all is well … appointment at 2, and Laurie needs pickles."* Same mechanism (`schedule`/CronCreate + PushNotification), broader inputs. Could run on the Debian VM as its "job". Parking lot [[phoenix-parking-lot]].
- **Give the Debian VM a real job** (Jerry, 2026-09-07) — Windows Helix auto-starts on boot but sits idle (nothing feeds it, Debian side down, no Debian autostart). Debian needs real work so Helix comes alive: Office Module 4, hosting the local LLM, the briefing agent above. "Debian needs a job" ≈ "put real work on it."
- **AI backend for the Life First VM instance** — no Ollama installed there, no `CLAUDE_API_KEY` set; AI-backed schedule queries give an honest plain-English fallback. Decide: install Ollama on the VM, or set a real key in `/etc/lifefirst/lifefirst.env`.
- **The game — needs its own real planning pass, not just a vague vision.** Jerry, 2026-09-05: "might as well add the build plan for the game needs a rough draft we have not built from a planned execution stand point yet. i look forward to that." Nothing exists yet beyond the HUD-mode toggle and the general "whole desktop IS the HUD" ambition (map + game output as a full-bleed base layer, panels floating on top as translucent glass, doubling as the in-game control center — `frontend-design` plugin guidance applies, glass/hierarchy over a moving background). Deliberately not drafted at the tail end of this session — this deserves the same real back-and-forth Office's DESIGN.md got (what "the game" actually is, what's playable vs. control-center, what Helix/MCP/Life First dependencies from [[phoenix-priority-queue]] actually gate it) before anything gets locked in. Start this fresh next session, likely via a proper planning pass (EnterPlanMode), not a quick draft.
- MapTiler: free key → `PHOENIX_MAPTILER_KEY` in `~/.phoenix/phoenix.env`. MapTiler MAP-pane wiring is on `checkpoint/real-terminal-2026-08-30` if wanted (the live MAP pane is still the filesystem browser).
- HELP CHAT + GUIDE panes still present — Jerry's call was "one guide, make it AI CHAT; the guide becomes a doc you open if you wish." The morning base kept them. Fold in.
- Dead `THROUGHPUT: -- ops/sec` in the HUD status bar — the deployed worker (v3.4.0) has no `/stats` route. Remove it or repoint at `/toc`.
- `node-pty` is a prebuilt binary; if `node_modules` is wiped and rebuilt without a compiler it may need attention — consider vendoring the `.node` files.
- `docs/PHOENIX_SYSTEM_SUMMARY_STATUS_CONNECTIONS.md` points at a nonexistent `sector3/workers/packages-worker/` — the live worker source is `sector2/package-handler/worker/index.js`.
- docs/ reconciliation — QUICK_START.md vs GETTING_STARTED.md vs root README.md overlap (unaudited)
- Deploy phoenix-dashboard.service on Ubuntu 192.168.1.133
- `dashboardDEP/` and other *DEP-suffixed dirs share filenames with live counterparts under one hex bucket — exclude from intake or rename off the collision path
- Extend the integrity-verification gate (hash check + qr_valid) to intake_file's single-file duplicate path and to hot-swap proper, not just intake clone
2026-05-03 — New canonical CLAUDE.md written. Repos audited. External Ubuntu build target established. Import method confirmed as intake strategy. Build plan phased across 7 phases.
