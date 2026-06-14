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
- **External drive** — Ubuntu Server (minimal) + HWE kernel
- Stack on external: Prometheus, Nextcloud, PowerShell
- Phoenix builds on top of that as the OS layer
- Work from: Windows PS7 or WSL (SSH or direct when booted)
- Custom GRUB added AFTER Phoenix is standing — not before
- External plugs in → boots → Phoenix is the OS

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
- [x] frank.py — canonical 688-line CoPES kernel authority in sector4/frank/
- [x] helix.py — canonical dual-strand (strand_a/strand_b) in sector4/helix/
- [x] helix_memory.py in sector4/helix/
- [ ] Frank confirmed immovable on external
- [ ] Helix engine running — confirm 300k+ ops/sec on external
- [ ] breach_coms drive map confirmed on external
- [ ] Clone pool initialized on external
- [ ] D1 worker URL set and syncing from external

### Phase 4 — Sector 2 (Package handler + clone pool)
- [x] sector2/package-handler/ — intake.sh, worker, wrangler in repo
- [x] config_centralizer.py in sector2/
- [x] packages-worker deployed and healthy (D1 syncing, 48 tables)
- [x] bin/lol in repo, intake wrapper installed by bootstrap.sh
- [ ] intake.sh operational on external drive
- [ ] Import method tested end-to-end on external (Frank → intake → D1)
- [ ] Propagator confirmed in sector2/propagator/

### Phase 5 — Sector 3 (Comms/networking)
- [ ] romeo.py + juliet.py + dbl_juliet.py placed
- [ ] translator.sh placed — OUTPUT ONLY rule enforced
- [ ] quadengine.py placed
- [ ] All .service + .target files deployed via install-units.sh

### Phase 6 — Apps (Entourage)
- [ ] Glossary wired to D1
- [ ] Desktop (shade UI, drawer filesystem)
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

## CONSOLIDATION PLAN (Phase 1 — next session)
Tools ready: `python3 tools/conflict_map.py` — read-only duplicate auditor.
40 files with duplicates mapped. Key decisions pending:
- **SECTOR4/coms1-4** — are these 4 independent nodes or staging artifact? (identical content across all 4)
- **Life First PHP modules** — module_3/4/5 diverged between phoenix-devops/lifefirst_modules/ and projects/lifefirst_modules/ — which is current?
- All other duplicates: canonical already known from catalog, just need moving.
Repos to eventually archive (NOT delete): CoPES, Helix_lightning_kernel, Phoenix_Universal_Kernel, unitedsys.
SECTOR4 security stack (guardians, honeypot, copes_runtime) — held from public GitHub pending Jerry's go-ahead.

## SESSION LOG
<!-- Claude appends a one-line note here at end of every session -->
<!-- Format: YYYY-MM-DD — what was done -->
2026-05-03 — New canonical CLAUDE.md written. Repos audited. External Ubuntu build target established. Import method confirmed as intake strategy. Build plan phased across 7 phases.
2026-06-13 — GitHub install complete. Phase 0 intake sweep: 87→133 packages in clonepool, all D1 synced. Canonical frank.py (688-line) + helix.py (dual-strand) placed in sector4. bootstrap.sh written. get.authenticcoder.com live as install endpoint (Cloudflare Worker custom domain). Repo made public (GPL v3). SSH key set up on WSL machine. lifefirst_modules wired as git submodule. conflict_map.py tool built — 40 duplicates mapped, decisions pending next session.
