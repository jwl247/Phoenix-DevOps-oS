# CLAUDE.md — Phoenix DevOps OS
# jwl247 / Jerry Leftwich / Phoenix DevOps LLC
# READ THIS FIRST EVERY SESSION. UPDATE AND PUSH AT END OF EVERY SESSION.
# =============================================================================

## WHO
- Jerry Leftwich (@jwl247) — ironworker, systems builder, United Systems
- Wife: Laurie — high-functioning autistic, protected share in Phoenix, this is her cushion
- Co-founders: Jerry (architecture, systems) + Jerilynn (UX, switches, InfoSec, red team)
- Loyalty: absolute. Anthropic credited. Claude ships with Phoenix.
- License: GPL v3 — open source to the bone

## WHAT PHOENIX IS
A deterministic, agnostic, prefetched, self-healing, versioned OS.
Easier than anything on the planet. More advanced than anything in existence.
CLI, GUI, or never type again — Phoenix meets you where you are.
Built on Debian stable root. We fill in the root, add our own GRUB, Phoenix on top.

## CURRENT BUILD TARGET
- **phoenix-ext** = Dell Inspiron PC, 192.168.1.133, Ubuntu 24.04 LTS + HWE kernel
- This IS the Phoenix machine — not a USB drive, a dedicated PC
- Stack on phoenix-ext: Prometheus, Nextcloud, PowerShell (PS already installed)
- Phoenix builds on top of the Ubuntu base as the OS layer
- Work from: Windows PS7 or WSL via SSH (phoenix-ext alias)
- Custom GRUB added AFTER Phoenix is standing — not before

## REPOS
| Repo | URL | Purpose |
|------|-----|---------|
| Phoenix-DevOps-oS | github.com/jwl247/Phoenix-DevOps-oS | Parent OS repo — **PUBLIC** — one repo, everything in sectors |
| lifefirst_modules | github.com/jwl247/lifefirst_modules | Life First backend — git submodule inside Phoenix-DevOps-oS |
| Phoenix-Package_handler | github.com/jwl247/Phoenix-Package_handler | Legacy — sector2/ now has the canonical copy |
| authenticcoder-website | github.com/jwl247/authenticcoder-website | authenticcoder.com — Cloudflare Pages |

## INSTALL
```bash
curl -fsSL https://get.authenticcoder.com | bash
```
- Served by packages-worker via custom domain `get.authenticcoder.com`
- Proxies `bootstrap.sh` from GitHub raw (5-min cache)
- Browser requests get a minimal install page
- Fallback: `curl -fsSL https://packages-worker.phoenix-jwl.workers.dev/get | bash`

**Pending repo work:**
- Keep Phoenix-Package_handler repo alive with redirect README pointing to sector2/

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
  vault/             phoenix_push.sh, download.sh
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
- One big JSON
- Nothing moves until output
- Output IS the clone
- D1 backed — chain of evidence

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

### 4-day versioning
- What was it + custody = complete file history
- breach_coms drive map:
  ```
  breach_coms4 → T1 PRIMARY    master vault, intake writes here
  breach_coms3 → T2 SECONDARY  day-1 mirror
  breach_coms2 → T3 TERTIARY   day-2 mirror
  breach_coms1 → T4 TERTIARY   day-3 mirror, 4-day window
  clonepool    → callable face of the vault
  ```

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

### Phase 1 — External Ubuntu base ✅ COMPLETE
- [x] Ubuntu 24.04 LTS + HWE kernel 6.8.0-124-generic on Dell Inspiron (phoenix-ext)
- [x] Prometheus healthy — snap version, port 9090, running since Jun 7
- [x] Nextcloud 33.0.5 — snap installed
- [x] PowerShell 7.6.2 installed
- [x] SSH access confirmed from WSL (key-based, phoenix-lan / phoenix-ext aliases)
- [x] Phoenix kernel OPERATIONAL — Frank5 v5.1.0-alpha, 20 suits, HelixI 7701-7704, HelixE 7805-7808
- [x] phoenix-kernel.service installed and running as systemd unit (auto-starts on boot)

### Phase 2 — Sector 1 (Boot/Kernel) ✅ COMPLETE
- [x] frank3_slot_a.c + frank3_slot_b.c placed in sector1/kernels/
- [x] Makefile placed in sector1/kernels/ + sector1/helix/kernel/
- [x] helix stack placed in sector1/helix/ (slim, complete, vram, translator, conf, kernel, run)
- [x] phoenix_auth.py placed in sector1/auth/
- [x] concierge placed in sector1/concierge/ (concierge.c, linux_concierge.py, bridge.py)
- [x] saddle_block.sh placed in sector1/
- [ ] Real frank3 kernel modules (more complete versions) — pending disk recovery + intake

### Phase 3 — Sector 4 (Helix + Frank engine) ✅ COMPLETE
- [x] frank.py — canonical 688-line CoPES kernel authority in sector4/frank/
- [x] helix.py — canonical dual-strand (strand_a/strand_b) in sector4/helix/
- [x] helix_memory.py in sector4/helix/
- [x] Frank confirmed immovable on external (phoenix-kernel.service running)
- [x] breach_coms drive map confirmed on external (sdc1=T1, sdb1=T2, sdc2=T3, sda2=T4)
- [x] Clone pool initialized on external (/breach_coms4/clonepool → ~/Phoenix/clonepool)
- [x] D1 worker syncing from external — intake.sh test: /clonepool + /custody + /glossary all OK
- [ ] Helix 300k+ ops/sec benchmark on external (kernel running, benchmark not yet run)

### Phase 4 — Sector 2 (Package handler + clone pool) ✅ COMPLETE
- [x] sector2/package-handler/ — intake.sh, worker, wrangler in repo
- [x] config_centralizer.py in sector2/
- [x] packages-worker deployed and healthy (D1 syncing, 48 tables)
- [x] bin/lol in repo, intake wrapper installed by bootstrap.sh
- [x] intake.sh operational on phoenix-ext — tested, D1 receipts confirmed
- [x] Import method tested end-to-end (intake.sh → clonepool → D1: /clonepool + /custody + /glossary OK)
- [x] Propagator confirmed in sector2/propagator/ (propagator.py, propcoms.sh, dispatch.json)

### Phase 5 — Sector 3 (Comms/networking) ✅ COMPLETE
- [x] romeo.py + juliet.py + dbl_juliet.py placed in sector3/romeo_juliet/
- [x] translator.sh placed in sector3/translator/ — OUTPUT ONLY rule enforced
- [x] quadengine.py placed in sector3/quadengine/
- [x] All .service + .target files written (18 units, install-units.sh templates username)
- [x] WireGuard mesh config — all 3 nodes (wg0-windows, wg0-wsl, wg0-phoenix-ext)
- [x] WireGuard installed on WSL + phoenix-ext; Windows hub active
- [x] WireGuard auto-start on WSL (.bashrc) + passwordless sudo in /etc/sudoers.d/phoenix-wg
- [x] WireGuard on phoenix-ext enabled and handshaking (wg0 already up, 10.77.0.3)
- [x] WSL wg0.conf installed to /etc/wireguard/wg0.conf — all 3 peers handshaking Now
- [x] windows_concierge.py added to sector1/concierge/
- [x] Input Leap KVM config — inputleap-server.conf (Windows LEFT, phoenix-ext RIGHT)
- [x] SSH bridge — bridge.sh installed, SSH aliases: windows-host / phoenix-ext / phoenix-lan / phx

### Life First — (parallel track, not Entourage)
- [x] Modules 3-6 updated: credentials from env, model → claude-sonnet-4-6, Ubuntu paths
- [x] Module 2 (API router): DB + API secret from env, deployment path updated
- [x] Module 7 (Voice Commander): written — intent detection + Claude fallback handler
- [x] config.php: shared config (API key, model, getDB from env vars)
- [x] deploy_lifefirst.sh: one-script deploy to phoenix-ext (Apache2 + MySQL already running)
- [x] Life First LIVE on phoenix-ext — all 5 modules responding, Laurie's user tested
- [x] ai_interactions table created in MySQL
- [x] PHP-FPM credential injection via lf_secrets.php (Apache SetEnv workaround)
- [x] Frank bridge: frank_lifefirst.py (sector4/frank/) — dispatch packets to Life First HTTP
- [x] /lifefirst routes added to frank_http.py (port 7347)
- [x] D1 custody logging wired into frank_lifefirst.py dispatch cycle
- [x] Ollama primary AI wired: callOllama() in config.php, Module 7 uses llama3.1 first, Claude fallback
- [x] MODEL_LIFEFIRST = llama3.1 (dedicated, never shared) — dispatch_lifefirst() in frank_ollama_bridge.py
- [ ] Rotate Claude API key
- [ ] D1 custody table dedicated to Life First interactions (currently uses shared custody table)
- [ ] Pre-warm llama3.1 on boot via Frank PCS (eliminates 60s cold-start on first Laurie message)

### Phase 6 — Apps (Entourage)
- [x] Glossary wired to D1 — dark cockpit UI, 135 entries, drawer/LED/copy, live at /glossary/
- [x] Review Platform — general peer review, immutable D1, 6 submission types, auto-promote at 2 votes, live at /review/
- [x] Operator Manual — 13-section interactive web manual, dark cockpit, copy buttons, live at /manual/
- [ ] Desktop (shade UI, drawer filesystem) — needs UI/UX collaborator for 3D shell
- [ ] Office (dual browser pane)
- [ ] Sketchpad/Concepts
- [ ] Music Notation Transcriber

### Phase 7 — GRUB + polish
- [ ] Custom Phoenix GRUB theme
- [ ] Boot entries configured
- [ ] Vault recovery pointer in GRUB
- [ ] External drive boots clean as Phoenix

## SESSION PROTOCOL
**START:** Read this file. Know where we are. Run status.sh if available.
**WORK:** Stay in sector. Real code only. Everything through Frank/intake.
**END:** Update ## BUILD STATUS checkboxes. Add session notes below. Push.

## CONSOLIDATION PLAN (Phase 1 — next session)
Tools ready: `python3 tools/conflict_map.py` — read-only duplicate auditor.
40 files with duplicates mapped. Key decisions pending:
- **SECTOR4/coms1-4** — are these 4 independent nodes or staging artifact? (identical content across all 4)
- **Life First PHP modules** — module_3/4/5 diverged between phoenix-devops/lifefirst_modules/ and projects/lifefirst_modules/ — which is current?
- All other duplicates: canonical already known from catalog, just need moving.
Repos to eventually archive (NOT delete): CoPES, Helix_lightning_kernel, unitedsys.
Phoenix_Universal_Kernel — added as submodule (phoenix_universal_kernel/). No longer needs separate archiving.
SECTOR4 security stack (guardians, honeypot, copes_runtime) — held from public GitHub pending Jerry's go-ahead.

## OLLAMA AI STACK
- **llama3.1** (4.9GB) — Laurie / Life First — dedicated, never shared
- **llama3.2:3b** (2.0GB) — kernel/code fast path (routes on keywords)
- **deepseek-r1:1.5b** (1.1GB) — reasoning, shows chain of thought
- **phi3.5** (pending pull) — chat/conversational desktop AI
- qwen2.5 — BANNED (dishonest about task completion, removed)
- Benchmark (Jun 16): llama3.2:3b warm = 6.1 tok/s, avg 4.1 tok/s (CPU-only)
- Cold start penalty: ~60s first call (model load). Pre-warm via Frank PCS = next priority.
- Life First fallback: if Ollama unreachable → Claude API (automatic, transparent)

## SESSION LOG
<!-- Claude appends a one-line note here at end of every session -->
<!-- Format: YYYY-MM-DD — what was done -->
2026-05-03 — New canonical CLAUDE.md written. Repos audited. External Ubuntu build target established. Import method confirmed as intake strategy. Build plan phased across 7 phases.
2026-06-13 — GitHub install complete. Phase 0 intake sweep: 87→133 packages in clonepool, all D1 synced. Canonical frank.py (688-line) + helix.py (dual-strand) placed in sector4. bootstrap.sh written. get.authenticcoder.com live as install endpoint (Cloudflare Worker custom domain). Repo made public (GPL v3). SSH key set up on WSL machine. lifefirst_modules wired as git submodule. conflict_map.py tool built — 40 duplicates mapped, decisions pending next session.
2026-06-15 — intake.py rebuilt (unitedsys/core/, TAV address system, sidecar + D1 sync). All sector 3/4 systemd units written (18 units). install-units.sh templates username at install time. Self-hosted WireGuard mesh: WSL↔Windows handshake confirmed. bootstrap.sh fixed (pip PEP 668, submodule auth graceful skip). SSH key-based auth to phoenix-ext operational. WireGuard installed on phoenix-ext — pending final enable+handshake. Input Leap KVM config written (upgrade to Synergy Friday). Repo remote switched to SSH. All pushed to GitHub.
2026-06-15 (session 2) — Node.js (v24 LTS) + wrangler (4.100.0) installed natively in WSL. packages-worker fixed + redeployed (all 12 status.sh checks green). WireGuard auto-start + passwordless sudo configured. Life First LIVE on phoenix-ext: modules 2-7 deployed, Apache+MySQL+PHP-FPM, Laurie's first response "It's 7:00 PM on Monday, June 15th." LAURIE.md written with full business roadmap. Next: Frank bridge, D1 custody for Life First interactions, rotate Claude API key.
2026-06-16 (session 1) — Full pipeline mapped (PCS→Freewheeling→Cpt_conductor→Propcoms→coms rings→Frank→Helix). Phoenix_Universal_Kernel added as submodule (phoenix_universal_kernel/). Frank×LifeFirst bridge complete: frank_lifefirst.py (sector4/frank/) dispatches Double Helix AI packets through Frank proxy wall → Life First HTTP API → D1 custody. /lifefirst routes added to frank_http.py (port 7347). intake.py updated — description now extracted from file headers automatically (Python docstring, shell comments, JS blocks). Frank×Ollama3 test suite written (test_frank_ollama.py, 26 unit tests pass). Next: wire Frank→Universal Kernel process resolution, dedicated D1 custody table for LF interactions, rotate Claude API key.
2026-06-16 (session 2) — HLK (Helix_lightning_kernel) added as submodule — full kernel: franken5/helixi/helixe/frank_ring/frank_spawn/process_library. UK main_kernel.py now boots HLK (CoPES substrate). FrankSpawn wired to ProcessLibrary for suit resolution. ProcessLibrary falls back to lol/clonepool when suit not on disk. Import names fixed (helixi/helixe), frank_ring syntax error fixed. Kernel confirmed OPERATIONAL on WSL (668ms boot, 20 suits, 8 channels). Kernel confirmed OPERATIONAL on phoenix-ext (668ms boot). setup_phoenix_ext.sh written — installs Prometheus, Nextcloud, phoenix-kernel.service in one sudo run. HLK repo: make private on GitHub (Settings → Make private). Next: run setup_phoenix_ext.sh on phoenix-ext, Phase 2 sector1 files, breach_coms drive map, clonepool init on external.
2026-06-16 (session 3) — Phases 2-5 all complete. breach_coms 4-tier vault live. PHOENIX_AUTH rotated + wired to kernel service. D1 sync confirmed end-to-end. Propagator wired. WireGuard mesh fully handshaking — all 3 nodes (Windows hub 10.77.0.1, WSL 10.77.0.2, phoenix-ext 10.77.0.3) peered Now. windows_concierge.py recovered from Phone Link backup + committed. WSL wg0.conf installed to /etc/wireguard/wg0.conf. Next: Phase 6 Apps (Glossary → D1, Desktop HUD, Office, Sketchpad, Music Notation, Review Platform).
2026-06-16 (session 4) — Ollama installed on phoenix-ext. Models: llama3.1 (4.9GB, Life First/Laurie dedicated), llama3.2:3b, deepseek-r1:1.5b live. phi3.5 pending pull. frank_ollama_bridge.py complete: MODEL_LIFEFIRST, dispatch_lifefirst(), LIFEFIRST_SYSTEM prompt, benchmark CLI. Benchmark: llama3.2:3b warm=6.1 tok/s, avg 4.1 tok/s CPU-only. Life First Module 7 + config.php updated: callOllama() primary, Claude API fallback. Review Platform live at /review/ (immutable D1, 6 types, auto-approve). Operator Manual live at /manual/ (13 sections, dark cockpit, interactive). Next: pull phi3.5, pre-warm llama3.1 on boot, desktop temp shell, rotate Claude API key.
