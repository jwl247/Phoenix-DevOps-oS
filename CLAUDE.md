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
- **ScriptForge** (`sector2/apps/scriptforge/`) — single-file Helix-branded code widget: paste JS/TS/PY/CSS/HTML/JSON/SH, get lint issues, dependency detection, a security scanner, "Auto Fixes — Helix Self-Heal", and a CONVERT tab (JSON⇄CSV, JSON beautify/minify, Base64, URL-encode). Moved 2026-09-05 from `tools/` (was orphaned there, unwired, undocumented) — no dashboard pane wired to it yet. Console-execution tab runs pasted JS in a sandboxed iframe (no allow-same-origin, 1.5s hang guard), not in the page's own context — the old version ran arbitrary pasted code with full DOM/cookie access, the exact class of risk the SECURITY tab flags in other people's code.

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
- [x] ScriptForge — given a real home at `sector2/apps/scriptforge/` (was loose in `tools/`, unwired, undocumented); sandboxed its console-execution tab (was running pasted code with full page access) and added a CONVERT tab (JSON⇄CSV, beautify/minify, Base64, URL-encode) (2026-09-05). Not yet wired to a dashboard pane.
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

## NEXT SESSION
- **Life First MCP auth** — `/mcp` → claude.ai Life First App (Jerry's side, OAuth) — the one piece of the original ask still not done.
- **Escalation delivery** — once the MCP's live, wire a scheduled Claude Code agent to poll `check`/`escalate` and push via PushNotification.
- **AI backend for the Life First VM instance** — no Ollama installed there, no `CLAUDE_API_KEY` set; AI-backed schedule queries give an honest plain-English fallback. Decide: install Ollama on the VM, or set a real key in `/etc/lifefirst/lifefirst.env`.
- **Unify the installer** — fold dashboard autostart, Helix autostart, and the PowerShell profile hook into one real `install.ps1` so a fresh machine is one step, not three manual scripts.
- **`config_centralizer` → Settings tab** — Jerry: its functionality should resolve into the dashboard's SETTINGS tab. Bytes are gone (confirmed unrecoverable — June-era, predates R2, no local copy anywhere), so this is a rebuild-into-Settings job, not a restore. Explicitly deferred — todo later, not this session.
- **HUD overlay retool** — map (MapTiler) + game output as a full-bleed base layer with the panels floating on top as translucent glass. The HUD-mode toggle is a start; this is the full "the whole desktop IS the HUD" that also doubles as the in-game control center. `frontend-design` plugin guidance applies here (glass, hierarchy over a moving background).
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
