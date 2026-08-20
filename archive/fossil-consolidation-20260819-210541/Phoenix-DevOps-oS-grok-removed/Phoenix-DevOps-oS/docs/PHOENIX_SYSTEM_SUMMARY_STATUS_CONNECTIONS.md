# PHOENIX SYSTEM SUMMARY + STATUS REPORT + CONNECTIONS LIST

**Living Document** — Read this first every session. Update at end of every build session (date + status deltas + new connections).  
**Date:** 2026-06-30 (making system operational - deps + services)  
**Workspace:** C:\Phoenix\Repos\Phoenix-Devops-oS_II (primary working copy for this doc)  
**Primary Source Tree:** ../Phoenix-DevOps-oS  
**Purpose:** Daily briefing + complete guide to install every component, dependency, service, and integration ("install all the shit").

> One pipeline. Every platform. Everything tracked.  
> Agnostic. Deterministic. Prefetched. Self-healing.

---

## 1. Executive Overview

Phoenix DevOps OS is a fully open-source, self-hostable "OS layer" (not a full distro kernel replacement) built on top of curated hosts (trimmed Win10 Pro dev machine + target external Ubuntu Server minimal + HWE). 

**Core innovation:** Helix — a Double Helix twin single-pass memory manager (C implementation) that speaks 4 languages simultaneously (quadralingual), benchmarked 300k–700k ops/sec, 100% cache hit, zlib level 5, thermal-limited 4/8 GB RAM.

Everything is versioned at 100-point / 4-day granularity via the **Phoenix Package Handler** (intake → deterministic hex ID + sidecar.json → clonepool versioning + custody ledger in D1 + primary storage in R2). 

**Four-sector corridor** (strict order, translator boundary on *output only*):

S1 (boot/kernel/hardware) → S2 (services / package handler / clonepool / Frank) → S3 (translator / Romeo ingress / Juliet egress) → S4 (master vault / intake / breach_coms tiers / rsync mirror chain)

**Global interface:** 7 commands (run, usys, clone, intake, status, align_dirs, get_distros) + Electron dashboard + suite execution from clonepool without install.

**Target build:** External drive Ubuntu + Prometheus + Nextcloud + PowerShell + full Phoenix on top. Dev primarily from Windows (PS7 + Git Bash) or WSL. GPU drivers blacklisted.

**Key repos:**
- github.com/jwl247/Phoenix-DevOps-oS (this everything)
- github.com/jwl247/Phoenix-Package_handler (intake/worker — planned migration into sector2)
- GitHub MCP integration (grok_com_github) for agent actions

---

## 2. People, Loyalty, License

- Jerry Leftwich (@jwl247) — architecture, systems, ironworker, United Systems / Phoenix DevOps LLC
- Wife Laurie — high-functioning autistic, protected share, this is her cushion
- Co-founders: Jerry + Jerilynn (UX, switches, InfoSec, red team)
- Anthropic/Claude credited and ships with Phoenix
- License: GPL-3.0 (open to the bone)

---

## 3. Immutable Rules (Never Break)

1. Everything stays **quadralingual** until `translator.sh` at sector3 boundary (output ONLY — never intake/clone).
2. Romeo = ingress, Juliet = egress at S3.
3. Breach_coms drives hold quadralingual vault — never translate inside.
4. Header QR before hash / Footer QR after hash.
5. All scripts: #!/usr/bin/env bash (external Ubuntu) or zsh (WSL dev).
6. GPU drivers blacklisted — never GPU-dependent solutions.
7. Never delete from breach_coms4 (master vault).
8. Nothing enters repo unless tested, polished, pro+.
9. No demos. Real code only.
10. Immutable: reviews, switches, custody chain.
11. Open source by default.
12. One repo. One OS. Everything in its sector.
13. Frank is import authority + audit logger; never moves.

---

## 4. High-Level Architecture

### Helix (C Core — Double Strand)
- Ingress (write path) + Egress (read path)
- libhelix.a static lib built from: helix_core.c, helix_diagnostics.c, helix_ingress.c, helix_egress.c, helix_http.c
- CLI tool: phoenix-intake (also prebuilt .exe for Win)
- Memory tiers, compression, multi-language simultaneous handling

### Frank / Franken
- Environment orchestrator, import authority, audit logger
- Multiple variants (franken.py, frankenhelix.py, frank_helix.py, franken2.py, etc.)
- ZMQ router, auto-venv, sideload bridge

### Package Handler / Intake / Clonepool (Sector 2 heart)
```
file/package/config → intake.sh → hex ID + sidecar.json (metadata, companions, QR state/tier) 
  → clonepool versioning (v1, v2..., deep T1/T2/T3/T4 structure)
  → local custody + append to D1 (custody + glossary)
  → R2 primary storage (recent evolution)
```
- TAV address: filename → SHA3-512 → first 8 bytes → base58 (e.g. 3vKmRp4x)
- States: white/grey/black (QR header)
- Tiers: T1 primary (breach_coms4) → T2/T3/T4 mirrors

**Worker:** packages-worker (Cloudflare) — full CRUD on clonepool/custody/glossary/packages/versions/installed. Auth via PHOENIX_AUTH / X-Phoenix-Auth header. Health at /health.

### Corridor & Translator
S1→S2→S3 (translator boundary — output only)→S4  
Everything upstream stays quadralingual.

### Global Commands + Dashboard
Thin wrappers (bin/ + .cmd) locate PHOENIX_ROOT, source env, delegate.  
Electron app (main.js + dashboard.js + index.html) executes real usys commands + shows live metrics/sectors.

### Vault & Mirror Chain (S4)
breach_coms4 (master) ←rsync— breach_coms3 ← breach_coms2 ← breach_coms1 (4-day window, timer every 15 min).

---

## 5. Component Inventory (Observed 2026-06-29)

**Legend for Status:** ✅ Present/prebuilt/configured in tree | ⚠️ Partial/stale paths | 🔴 Needs install/build/deploy | (notes)

### Core / Helix Layer
| Component | Paths | Lang | Purpose | Key Files | Status |
|-----------|-------|------|---------|-----------|--------|
| Helix C Core (lib) | ../Phoenix-DevOps-oS/phoenix-core/ | C11 | Double helix memory engine (ingress/egress/http/diag) | Makefile, libhelix.a, src/*.c + *.o (5), include/helix*.h | ✅ libhelix.a + all .o + phoenix-intake.exe present |
| phoenix-intake CLI | phoenix-core/tools/ | C | Built intake tool | main.c, phoenix-intake.exe | ✅ exe present |
| Test harness | phoenix-core/tests/ | C | Smoke tests | test_core.c | ✅ |
| Kernel / frank3 slots | sector1/kernels/ | C | Sector1 kernels | frank3_slot_a.c, _b.c, Makefile | ✅ sources present |

### Sector 1 (Boot / Kernel / Hardware)
| Component | Paths | Lang | Purpose | Key Files | Status |
|-----------|-------|------|---------|-----------|--------|
| frankenhelix | sector1/ + SECTOR4/coms* | Python + C bridge | ZZZring0 bidirectional, COM1-4 daisy, 11/11 self-tests, Freewheeling | frankenhelix.py, frank3-*.service | ✅ sources + units |
| frank-helix (RAM daemon) | sector1 + sector2 | Python | L1/L2/L3 tiers (60/75/88%), ZMQ 5557, Frank bridge | frank_helix.py, phoenix-frank-helix.service | ✅ |
| phoenix_auth | sector1/auth/ | Python | SHA3-512 + BLAKE2b over 10 hardware signals | phoenix_auth.py | ✅ |
| Concierge | sector1/concierge/ | C + Python | Bridge + linux_concierge | concierge.c, bridge.py, linux_concierge.py | ✅ (build_windows.bat references) |
| Auto-config | sector1 + services | Python | First-boot hardware/profile + systemd oneshot | auto_config_installer.py (ref), phoenix-auto-config.service | ✅ unit present |

### Sector 2 (Services / Package Handler / Buffer)
| Component | Paths | Lang | Purpose | Key Files | Status |
|-----------|-------|------|---------|-----------|--------|
| Package Handler / Intake | sector2/package-handler (planned), clonepool/, packages-worker/ (II), II clonepool | sh + JS + sidecars | Universal intake, hex+sidecar, clonepool versioning, D1 custody | intake.sh, worker/index.js, wrangler.jsonc, sidecar.json examples | ✅ worker source + II clonepool populated with examples; main intake in separate repo clone (or nested) |
| Propagator + dispatch | sector2/propagator/ | Python + json | dispatch.json router (vault/sql/d1/frank3/peer/windows) | propagator.py, dispatch.json, propcoms.sh | ✅ dispatch.json present |
| Frank variants (ring0 etc) | sector2/ring0, frank/ | Python/JS | frank_helix.py, frank_http.py, frank_save.py, frank_client.js, frankenhelix.py | Multiple | ✅ |
| Intent parser / mega-security | sector2 (refs) | Python | Service bus, port guardian, threat, port 8888? | intent_parser.py, mega_system_manager.py | ⚠️ (referenced in docs/services) |
| Life First Suite | sector2/lifefirst (refs in docs) | PHP + MySQL | AI calendar/messenger/notifications/budget for JW+Laurie | sql/*.sql, ai/*.php | ⚠️ Partial in current tree (docs describe) |

### Sector 3 (Translator Boundary)
| Component | Paths | Lang | Purpose | Key Files | Status |
|-----------|-------|------|---------|-----------|--------|
| Translator | sector3/translator/ + services | sh | Output-only quadralingual boundary | translator.sh | ✅ unit + script ref |
| Romeo (ingress) | sector3/romeo_juliet/ | Python | ZMQ PULL 5560 | romeo.py, dbl_juliet.py | ✅ |
| Juliet (egress) | sector3/romeo_juliet/ | Python | ZMQ PUSH 5561 | juliet.py | ✅ |
| Quadengine | sector3/quadengine/ + SECTOR4 | Python | Octahedron storage / engine | quadengine.py | ✅ multiple copies |
| Services / units (21) | sector3/services/ | systemd + sh/ps1 | Full corridor units + targets + dashboard push | * .service .target, install-units.sh, install-dashboard-windows.ps1, push-*.sh/ps1, scout-ubuntu.sh | ✅ 21 units + installer scripts present (list: auto-config, franken*, frank-helix, intent-parser, propagator, mega-security, unoserver, doc-worker, scheduler, ollama, dashboard, sector targets, translator, romeo, juliet, intake, rsync-clone, etc.) |

### Sector 4 (Master Vault)
| Component | Paths | Lang | Purpose | Key Files | Status |
|-----------|-------|------|---------|-----------|--------|
| Intake (S4) | SECTOR4/intake/ + SECTOR4/ | sh | TAV SQL versioning into master vault | intake.sh | ✅ |
| Vault / push / memory | SECTOR4/vault/ | sh + py | phoenix_push.sh, download.sh, helix_memory.py | Various | ✅ |
| Coms layers (1-4) | SECTOR4/coms1..4 | Python + sh | Conductor sync, franken, freewheeling, helix_api, propcoms, guardians, syncthing_module, quadengine, rebound, installer_registry | Many .py + .sh + .json | ✅ full structure present in 4 coms copies |
| Conductor / paging / pcs | SECTOR4/ | Python | cpt_conductor.py, paging.py, pcs.py, setupsec4.py | - | ✅ |
| **Connections System (core)** | SECTOR4/connections.py (canonical) + workspace copy | Python | Unified ConnectionManager: register, ZMQ/Syncthing/HTTP/dispatch targets/helix_mesh, daisy COM relay, health checks, glossary publish, friendships, diagnostics (What+Why+Action) | connections.py | 🆕 **Implemented 2026-06-30** — see SECTOR4/connections.py. Wires to dispatch.json, helix_mesh.conf, propcoms, guardians, known ports (5555/5557/5560/5561/...). Auto-registers core mesh + worker. |
| Syncthing | SECTOR4/.../syncthing_module.py | Python | Sync module | syncthing_module.py | ✅ |

### Dashboard (Electron)
| Component | Paths | Lang/Runtime | Purpose | Key Files | Status |
|-----------|-------|--------------|---------|-----------|--------|
| Phoenix Dashboard | dashboard/ | Node + Electron 28 | Native sci-fi command center, real usys execution, sector toggles, metrics, Claude HUD (3-tier) | package.json, main.js, index.html, dashboard.js, styles.css, start.ps1, start-desktop.sh | ✅ Full node_modules (thousands of files), package.json present, start scripts, integration docs |

### Global Commands & Status
| Component | Paths (bin + wrappers) | Purpose | Status |
|-----------|------------------------|---------|--------|
| usys, clone, intake, run, status, align_dirs, get_distros + .cmd | ../Phoenix-DevOps-oS/bin/ + status.sh | Global PATH access (PS7/CMD + bash) | ✅ All 14 files present; wrappers source .phoenix_env + delegate to repo scripts or pwsh |
| status.sh (core) | root status.sh + bin/status wrapper | Sector counts, mounts, systemd, catalog sqlite, git | ⚠️ Hardcoded ~/projects paths in some versions; current bin wrapper tries $HOME/Phoenix and env |

### Workspace II Specific (DevOps / Grok Session Context)
- `clonepool/` : Active local clonepool with hex-named dirs + sidecars + v* versioned files (e.g. README.md hex snapshot)
- `packages-worker/` : Source for the CF worker (wrangler + index.js)
- `mcps/grok_com_github/` : 91 tool definition JSONs — enables full GitHub MCP actions (issues, PRs, code search, actions, etc.)
- `terminals/` : Captured output logs (1-5.txt)
- `test-cache/` : Sidecar + content caches

### Other / Supporting
- Deploy helpers: deploy/windows/* (build_windows.bat for MinGW, start_wsl)
- Website tree (git internals + wrangler for CF Pages?)
- Archive/ (old snapshots)
- _kali_import/ (recovered scripts)

**Component count estimate:** 50+ distinct pieces across layers.

---

## 6. External Integrations & Accounts (Connection List — External)

**GitHub**
- Primary: jwl247/Phoenix-DevOps-oS
- Package handler: jwl247/Phoenix-Package_handler
- Website: jwl247/authenticcoder-website (Cloudflare Pages)
- Sponsors badge
- **MCP Integration (this session):** grok_com_github server (91 tools) — full repo, issue, PR, actions, code search, discussions, secrets, etc. control plane for agent.

**Cloudflare**
- Worker: packages-worker.phoenix-jwl.workers.dev
- D1 Primary: phoenix_dev_db (id: 27958687-4349-47ed-8b6a-dbc4ab29730f) bound as DEV_DB
- D1 Secondary: phoenix-catalog (id: 0514d761-1db4-4e4f-8d1b-e5657909c0c0) bound as CATALOG_DB
- R2: primary clonepool storage (per latest CLAUDE notes)
- Wrangler deploy for worker
- Possible Pages for website

**Local Services / Runtimes**
- Ollama: 127.0.0.1:11434 (phoenix-ollama.service — "Ollama primary, Grok fallback" for Help Desk / Claude HUD 3-tier)
- ZMQ mesh: 5557 (Frank RAM), 5555 (frank3 dispatch ref), 5560 (Romeo ingress), 5561 (Juliet egress)
- UNO server: port 2003 (LibreOffice daemon for doc-worker)
- Mega security / dashboard metrics: ~8888 (ref)
- Syncthing (via module in SECTOR4)

**Other Targets (build phase)**
- Prometheus, Nextcloud on external Ubuntu
- PowerShell on Linux target
- MySQL (Life First scheduler/budget)
- Git + SSH from Win/WSL to external

**PHOENIX_AUTH token** — required for all worker write endpoints (D1 custody/glossary updates).

---

## 7. Detailed Internal Connections & Wiring Map

### Sector Flow (Strict)
S1 (kernel/boot/auth/concierge/frankenhelix)  
↓ (after units)  
S2 (intent-parser → propagator + mega-security + doc-worker + scheduler + unoserver + package/clonepool/Frank)  
↓  
S3 (translator → romeo + juliet)  
↓  
S4 (intake → vault master + rsync timer to T2/T3/T4)

### Key Ports & Protocols Table
| Port/Endpoint | Component | Direction | Notes |
|---------------|-----------|-----------|-------|
| 5557 (ZMQ) | frank-helix | Router / sideload | Frank-to-Frank bridge |
| 5560 (ZMQ PULL) | romeo.py | Ingress | S3 boundary |
| 5561 (ZMQ PUSH) | juliet.py | Egress | S3 boundary |
| 11434 (HTTP) | ollama | Local LLM | phoenix-ollama.service |
| 2003 | unoserver (LibreOffice) | Doc worker | phoenix-unoserver.service |
| HTTPS (packages-worker.phoenix-jwl.workers.dev) | packages-worker | Intake custody + glossary + health | POST needs auth header |
| File + sidecar | Intake everywhere | All files | Companions travel together |
| rsync (timer) | S4 vault | Mirror chain | 15 min, breach_coms4→3→2→1 |
| dispatch.json targets | Propagator | Multi | vault, sql (~/.catalog), d1, frank3 (ZMQ), peer, windows (via translator) |
| PATH + .phoenix_env | Global cmds | All | usys / clone / intake etc. |
| MCP (stdio / transport) | grok_com_github | GitHub control | 91 tools |

### Data Flow (Intake / Clone)
1. Any file → intake.sh (or clone command)
2. Hex from name + sidecar.json (usys_intake ver, sha, state white, tier, companions, QR, pool_path, notes)
3. Versioned in clonepool/<hex>/vN/
4. Custody receipt appended locally + POST /custody (D1)
5. Optional /clonepool POST + glossary upsert
6. For suites: .suite.json manifest → `run <name>` executes from pool (no install)

### Other Wiring
- Frank import method: registers → intake generates hex/sidecar → clonepool + D1
- Dashboard: spawns real commands via child_process / exec, reads env, shows sector file counts + clonepool data
- Helix C ↔ JS/Python: helix_packet.js (QuadralingualPacket), HelixTranslationPipeline + DoubleHelixStorage, ClaudeMemory
- COM daisy-chain in frankenhelix (COM4→3→2→1)
- Translator fires only on OUTPUT (sector2_backup + sector3_primary refs)

Cross-ref: See New folder/Lost_Ark_Connections_Wiring_Map.md and Phoenix_Structure_and_Connections.md for diagrams and Lost Ark specifics (R2 primary, D1 custody-ledger focused).

---

## 8. Full "Install All The Shit" — Windows-First Prerequisites & Sequence

### Base Tools (winget recommended)
- PowerShell 7: `winget install Microsoft.PowerShell`
- Git (with Bash): `winget install Git.Git`
- Node.js (LTS): `winget install OpenJS.NodeJS`
- GCC / build (for Helix C): `winget install GnuWin32.Gcc` **or** `winget install MSYS2.MSYS2` then `pacman -S mingw-w64-x86_64-gcc`
- Python 3.10+: usually via winget or Microsoft Store / official
- curl: usually present with Git / Windows
- sqlite3 (for local catalog checks): via Git Bash or install

**Accounts / Tokens**
- GitHub account (clone + future MCP/personal access)
- Cloudflare account → create D1s (or use existing ids), generate PHOENIX_AUTH token for worker writes, wrangler login
- (Optional) Ollama download from ollama.com

### Primary Install Sequence (Windows)
1. **Bootstrap (recommended)**  
   `irm https://raw.githubusercontent.com/jwl247/Phoenix-DevOps-oS/main/bootstrap/lol-bootstrap.ps1 | iex`  
   Then: `lol install phoenix-devops-os`

2. **Or direct**  
   `powershell -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/jwl247/Phoenix-DevOps-oS/main/install.ps1 | iex"`

   (Local: `pwsh -ExecutionPolicy Bypass -File .\install.ps1` from source tree)

3. **Open NEW terminal** (critical for PATH + env)
   - Verify: `usys status` or `status`
   - Check env: `$env:PHOENIX_ROOT`, `Get-Content $HOME\.phoenix_env.ps1`

4. **Package Handler / Worker pieces**
   - The install.ps1/sh also clones Phoenix-Package_handler (or use intake of sector2 version)
   - `cd ~/Phoenix/package-handler` (or equivalent) ; follow its install if separate
   - For worker: have wrangler (`npm install -g wrangler`), `wrangler deploy` (uses pre-defined DB ids in wrangler.jsonc)

5. **Dashboard**
   ```powershell
   cd dashboard
   .\start.ps1   # or npm install ; npm start
   ```
   (First time: 1-2 min for electron)

6. **C / Helix build (if source changes or verify)**
   ```powershell
   cd phoenix-core
   # ensure gcc in PATH (MinGW or MSYS)
   make
   make test
   make intake
   ```
   (Prebuilts already exist — exe + lib + objects)

7. **Linux target side (external drive / WSL or SSH)**
   - Run `install.sh` (curl one-liner)
   - `sudo zsh sector3/services/install-units.sh`
   - `sudo systemctl enable --now phoenix-sector4.target` (pulls whole chain)
   - `journalctl -u 'phoenix-*' -f`

8. **Post-install checks**
   - New terminal: `status`, `usys status`, `clone --help`
   - Clone a test file: `clone .\README.md scripts "test"`
   - Check clonepool dir: `~/Phoenix/clonepool`
   - Worker health (once PHOENIX_AUTH + internet): curl or browser to /health
   - Dashboard launch + exercise buttons

### Environment Files Written
- `~/.phoenix_env.ps1` (Win) / `~/.phoenix_env.sh`
- `~/.usys/bin` (global shims)
- File associations for .lol / .phx (optional, controllable by switches)

### Windows vs Linux Notes
- Windows: heavy on PS7 wrappers + Git Bash for sh, winget prereqs, Electron native.
- Linux target: systemd units (21), full corridor start via targets, rsync timers, ZMQ daemons.
- WSL bridge scripts exist in deploy/.

**Ollama (soft dep):** Install separately; service template exists (ExecStart=OLLAMA_BIN serve).

---

## 9. Current Status Report (Snapshot 2026-06-29)

**Overall:** Core architecture solid and documented. Significant prebuilt artifacts and full source tree present. Package Handler + worker fully specified + deployed config ready. Dashboard functional. Global commands wired. Many Linux services defined. C core proven in recent notes.

**From CLAUDE.md (build target + recent notes, condensed):**
- Phase 1 (external Ubuntu base): [ ] Ubuntu + HWE, Prometheus, Nextcloud, PowerShell, SSH from Win
- Phase 2/3/4 sector placement: many pieces already in tree (sources + units)
- Recent (2026-06-28 notes in CLAUDE): C core Helix double-strand proven (ingress+egress, D1+R2+local cache). packages-worker /stats live. Dashboard wired to real data + Claude HUD (3-tier: subscription/API/Ollama). Helix memory on both ends. phoenix-dashboard.service written. helix_memory.py in vault. packages-worker healthy (v3.4+).

**Artifact Inventory (directly observed via tools):**
- phoenix-core: libhelix.a, 5 .o files, all src + include, phoenix-intake.exe, Makefile, tests — ✅ built
- dashboard/: package.json (electron 28 + builder), full node_modules tree (thousands files), start.ps1, html/js/css — ✅
- sector3/services/: 21 .service/.target files + install scripts — ✅
- packages-worker/: wrangler.jsonc (exact 2 D1 bindings + ids), index.js (full endpoints, health, auth, tables) — ✅
- clonepool/ (II workspace): multiple hex dirs with sidecar.json + v1.. files (e.g. README.md snapshot) — active
- bin/: all 7 cmds + .cmd — ✅
- SECTOR4/coms1-4 + other sectors: full py/sh/json structure duplicated for com layers — ✅
- **NEW**: SECTOR4/connections.py (full ConnectionManager implementation ~24kB) + SECTOR4/connections/README.md + workspace connections_full.py — 🆕 Implemented core wiring, registration, daisy relay, health, Syncthing hooks, glossary integration, friendships. Matches Phase 1 of Lost_Ark_Implementation_Outline exactly. Integrated into coms1/propcoms.py example.
- dispatch.json, sidecar example (usys_intake 1.5, hex, state white, tier, sha, companions empty, qr), ollama.service template — ✅
- Installers + bootstrap + docs (CLAUDE, sector READMEs, wiring maps, GLOBAL_COMMANDS, SUITE_MANIFEST, QUICK_START) — ✅

**Gaps / Needs Install on this Win machine (high level):**
- Full run of lol-bootstrap or install.ps1 + open new terminals + verify env
- Node + npm install for dashboard (node_modules may be present in source tree but not user ~/Phoenix copy)
- Wrangler global + auth + deploy (or confirm worker live)
- PHOENIX_AUTH token into ~/.phoenix_env.ps1 + restart terminals
- gcc/MinGW for any C rebuilds (prebuilts exist)
- Ollama binary + service wiring
- Linux external drive full setup (Phase 1)
- Possible MySQL / LibreOffice / Syncthing for full LifeFirst + doc + sync features
- Migration of package-handler into sector2 (still separate repo)
- Update stale paths in some status.sh / older scripts

**Worker note:** /health reports counts for clonepool/custody/glossary/packages/versions/installed. Version in code ~2.1.0.

**Ready today for dev:** Source exploration, reading docs, synthesizing (this doc), GitHub MCP actions, local file work, planning installs using this summary.

**2026-06-30 Operationalization Progress (this session):**
- ExecutionPolicy relaxed to RemoteSigned (CurrentUser).
- Manual bootstrap: $HOME\Phoenix dirs, .phoenix_env.ps1, .usys\bin populated with wrappers from bin/.
- PHOENIX_ROOT pointed to source tree for immediate dev use.
- PowerShell 7 MSI download + quiet install started (will require new terminal after finish).
- Node.js LTS (v20) MSI download + quiet install started (for dashboard + wrangler).
- Connections system (SECTOR4/connections.py) tested and confirmed operational in Python (factory, registration from dispatch/helix, daisy COM relay, health, summary).
- Prebuilt Helix artifacts (libhelix.a, phoenix-intake.exe) ready; no gcc needed for basic use.
- Dashboard node_modules present in source (ready once node in PATH).
- winget not in current PATH/session (use Microsoft Store "App Installer" if needed for future).
- No full $HOME\Phoenix\Phoenix-DevOps-oS yet (manual setup + local source used).
- Next after restart: dot-source env, test usys/status, launch dashboard, test connections more, intake the connections.py itself.

---

## 10. Environment Variables Reference

| Var | Description | Set By |
|-----|-------------|--------|
| PHOENIX_ROOT | Install dir (usually ~/Phoenix or $HOME/Phoenix) | installers |
| PHOENIX_AUTH | Bearer token for worker writes (D1) | User (CF) |
| PHOENIX_WORKER_URL | https://packages-worker.phoenix-jwl.workers.dev | installers |
| CLONEPOOL_DIR | ~/Phoenix/clonepool | installers |
| PHOENIX_INTAKE / PHOENIX_INTAKE_SECTOR4 | Paths to intake scripts | installers |

Also injected: PATH updates for ~/.usys/bin .

View: `Get-Content $HOME\.phoenix_env.ps1` or `cat ~/.phoenix_env.sh`

---

## 11. Global Commands Quick Reference

See full in docs/GLOBAL_COMMANDS.md. All available after install + new terminal.

- `usys <cmd>` — main interface (status, clone, intake, search, open, init)
- `clone <file> [category] ["tag"]` — Sector 2 clonepool + sidecar + D1
- `intake <file>` — Sector 4 vault
- `run <suite-name>[@ver]` — execute suite from pool (no install)
- `status` — health (sectors, mounts, systemd, catalog, git)
- `align_dirs`, `get_distros`

Wrappers handle Win (pwsh) / bash detection.

---

## 12. Daily Build Workflow & Document Maintenance

1. Start session: open this file (or the copy in main tree).
2. Run `status` / `usys status` / dashboard as available.
3. Build / intake / code / test.
4. **End of session (mandatory):**
   - Update "Current Status Report" section (date, new artifacts, deltas, gaps closed).
   - Add any newly discovered connections/ports/wiring.
   - Bump top date.
   - Optionally: `intake` this .md file itself so it enters clonepool + glossary.
   - Commit + push (use MCP tools or git).
5. Update CLAUDE.md if architectural or rules changed.

---

## 13. Sources & Cross-References (Accurate as of Exploration)

- CLAUDE.md (architecture bible + rules + build phases + recent 2026-06-28 notes)
- Main README.md + docs/ (QUICK_START, GLOBAL_COMMANDS, SUITE_MANIFEST, sector1-4 READMEs, systemd/README)
- New folder/ (Phoenix_Structure_and_Connections.md, Lost_Ark_Connections_Wiring_Map.md, others)
- Installers (install.ps1/sh, lol-bootstrap, install-units.sh, dashboard installers)
- phoenix-core/Makefile + built artifacts
- packages-worker (wrangler + full index.js)
- SECTOR4/coms* + sector* source trees
- bin/ + status.sh + dispatch.json + example sidecar
- dashboard/ package + start files
- Grep results across tree for ports, deps, wiring

For deeper: read the originals. All paths relative to the OS repo root unless noted as II workspace.

---

## 14. Appendix — Key Snippets

**Worker health example (conceptual from code):**
`/health` returns worker version, status, counts of clonepool/custody/glossary/packages/versions/installed.

**Example sidecar (README.md snapshot):**
```json
{
  "usys_intake": "1.5",
  "hex_name": "524541444d452e6d64",
  "original_name": "README.md",
  "state": "white",
  "version": "v1",
  ...
  "qr": { "header": {"role": "state", "state": "white"}, "footer": {"role": "location", "tier": 1} }
}
```

**dispatch.json targets:**
```json
{ "targets": { "vault": {...}, "d1": {...}, "frank3": {"zmq_port": 5555}, "peer": {"zmq_port": 5560} }, "com_chain": ["COM4","COM3","COM2","COM1"] }
```

**wrangler bindings (exact):**
D1 phoenix_dev_db + phoenix-catalog.

**Ollama service (template):**
Environment=OLLAMA_HOST=127.0.0.1:11434 ; ExecStart=OLLAMA_BIN serve

**One-liners:**
- Win: irm .../install.ps1 | iex
- Linux: curl -fsSL .../install.sh | bash
- Worker: wrangler deploy
- C: make (in phoenix-core)

---

**End of living document.**  
Update this after every session. Use it to drive the next install or build step.

**Last verification note (in plan execution):** This doc was synthesized directly from the listed sources on 2026-06-29 via exhaustive read/grep/list. All paths, IDs, ports, artifacts, and flows were cross-checked against actual files.

---

*Built for daily use with Grok in the Phoenix-Devops-oS_II workspace. One pipeline.*
