# PHOENIX DEVOPS OS — MASTER BUILD DOCUMENT
# jwl247 / Jerry Leftwich / Phoenix DevOps LLC
# READ ALONGSIDE CLAUDE.md — this is the build map, CLAUDE.md is the law
# Last updated: 2026-06-29
# =============================================================================

## THE GOAL
Run a high-B local LLM for the Life First app. Laurie's cushion.
Everything in this document exists to serve that single outcome.

## THE SEQUENCE
Import method leads. Everything else wires to it.
1. Import method running end-to-end (intake → Frank → Helix → clone pool → D1)
2. Lost Ark deployment (trimmed Windows 10 Pro host + Debian WSL bridge)
3. Full pipeline — all sectors wired as one monolithic modular system
4. Life First LLM running on Phoenix

---

## PART 1 — WHAT RUNS TODAY (no changes needed)

| Component | File | Status | Notes |
|---|---|---|---|
| PCS lifecycle | SECTOR4/pcs.py | ✅ runs | stdlib only, self-contained |
| Freewheeling stage | SECTOR4/freewheeling_stage.py | ✅ runs | needs PHOENIX_STAGE_TMP env |
| Paging manager | SECTOR4/paging.py | ✅ runs | Linux only, root req'd |
| Helix C kernel | sector1/helix/kernel/helix_kernel.c | ✅ compiles | gcc -O2 -lm |
| Frank3 kernel module | sector1/kernels/frank3_slot_a.c | ✅ compiles | needs linux-headers |
| Helix slim ZMQ | sector1/helix/helix_slim.py | ✅ runs | needs pyzmq |
| Frank daemon | sector2/frank/frank_helix.py | ✅ runs | needs pyzmq + psutil |
| Frank save scheduler | sector2/frank/frank_save.py | ✅ runs | needs /mnt/d-g mounts |
| Frank HTTP bridge | sector2/frank/frank_http.py | ✅ runs | needs frank_save.py |
| Ring0 interceptor | sector2/ring0/frankenhelix.py | ✅ runs | needs pyzmq |
| Signal propagator | sector2/propagator/propagator.py | ✅ runs | needs D1_WORKER_URL env |
| Dispatch config | sector2/propagator/dispatch.json | ✅ valid | all 6 targets active |
| Translator | sector3/translator/translator.sh | ✅ runs | 9 backends, complete |
| Romeo ingress | sector3/romeo_juliet/romeo.py | ✅ runs | needs pyzmq |
| Juliet egress | sector3/romeo_juliet/juliet.py | ✅ runs | needs translator.sh path |
| Quadengine | sector3/quadengine/quadengine.py | ✅ runs | needs pyzmq |
| DoubleHelixStorage | SECTOR4/coms1/freewheeling.py | ✅ runs* | *fix bracket line 97 |
| Helix translation pipeline | SECTOR4/helix_universal_translation.py | ✅ runs | passthrough fallback |
| CPT conductor | SECTOR4/cpt_conductor.py | ✅ runs | needs watch dirs |
| Helix diagnostics C | phoenix-core/src/helix_diagnostics.c | ✅ compiles | |
| Helix egress C | phoenix-core/src/helix_egress.c | ✅ compiles | needs PHOENIX_WORKER_URL |
| Dashboard Electron | dashboard/main.js + dashboard.js | ✅ runs | needs Electron |
| align_dirs.sh | tools/align_dirs.sh | ✅ runs | WSL audit + live create |
| saddle_block.sh | sector1/saddle_block.sh | ✅ runs | run from Windows side |

---

## PART 2 — WHAT NEEDS COMPLETION (abandoned / half-baked)

These files exist, have real architecture, but are incomplete.
Each needs a worker session to finish. Notation for each.

---

### 2.1 CRITICAL — blocks import method

**intake.py** — MISSING ENTIRELY
- Location: needs to be created at `phoenix-core/tools/intake.py`
  OR wire `phoenix-intake.exe` (already compiled in phoenix-core/tools/)
- What it does: SHA3-512 hex ID + sidecar.json + D1 custody receipt
- intake.sh already calls it — just needs the file at the right path
- `helix.h` already defines `helix_sidecar_t` struct — use it
- Worker: write intake.py OR write a Python wrapper around phoenix-intake.exe
- Notation: `intake(file_path) → hex_id + sidecar.json + D1 POST`

**SECTOR4/vault/helix_memory.py** — INCOMPLETE CLASSES
- HelixSystem.__init__() instantiates 4 undefined classes:
  - `HelixMemoryManager(cache, virtual_mb)` — not defined
  - `HelixFS(memory)` — not defined
  - `FrankCastReel(memory)` — not defined
  - `SectorRouter(memory)` — not defined
- Comment at line 224 says "remain functionally same" — they were in an earlier
  version that got scraped. Need to be restored.
- Worker: define 4 stub classes sufficient for HelixSystem to instantiate
- Notation: each class manages its domain (memory mgr, filesystem, frank cast/reel, sector routing)

**SECTOR4/coms1/freewheeling.py** — SYNTAX ERROR
- Line 96-97: unmatched bracket in `_to_vector()` list comprehension
- Fix: `for v in value])` → close correctly
- Worker: one-line fix, then verify import works

**SECTOR4/coms1/helix_api.py** — TWO BUGS
- Line 24: `self.OVERFLOW_PATH` → `self.RESPONSIBILITY_PATH`
- load_warm method: parameter `ket` → `key`, then use `key` not `ket`
- Worker: two-line fix

---

### 2.2 HIGH — needed for full pipeline

**SECTOR4/setupsec4.py** — CHAT LOG, NOT CODE
- Currently contains a pasted chat conversation (not Python)
- Purpose: sector 4 bootstrap — creates dirs, mounts, registers coms rings,
  verifies breach_coms drives are labeled and mounted
- Worker: replace entirely with a proper bootstrap script
- Notation: `setupsec4.py` runs once on fresh deploy, idempotent

**franken.py / franken2.py — merge target no longer exists, needs re-scoping**
- Was: `SECTOR4/coms1/franken.py` (sketch-level Franken2 LEAD for coms
  ring 1 — load balancer, PCS stage, overflow handler, medic) with a
  fuller version at `_kali_import/franken2.py` (real bodies, but a
  circular import bug — tries to import from itself at line 34; real
  Frank RAM manager, 8GB → 16GB+ via zlib compression).
- **Neither `SECTOR4/coms1/franken.py` nor `helix_api.py` exist in the
  live tree anymore** — both were archived as fossils in the 2026-08-21
  cleanup, along with the whole Python-side Helix engine (see
  `dashboard/manual/PHOENIX_MANUAL.md` §17). The old merge plan ("pull
  franken2.py's real bodies into SECTOR4/coms1/franken.py, fix the
  circular import to pull from helix_api + freewheeling") has no live
  target left to merge into.
- `_kali_import/` itself was a stale one-time recovery dump (not live
  code — see its own IMPORT_NOTES.md), archived 2026-08-22 to
  `archive/kali-import-consolidation-20260822-113129/franken2.py`.
- This needs a fresh decision, not a bug fix: rebuild Frank's RAM-tier
  management fresh against current sector2/4 code, or leave franken2.py
  archived as reference-only.

**phoenix-core/src/helix_core.c** — STUB
- Only helix_generate_hex_id() defined (SHA256 of input string)
- helix.h defines full API: sidecar ops, log_event, generate_hex_id
- Missing: helix_create_sidecar(), helix_log_event(), helix_verify_hex_id()
- Worker: implement remaining functions declared in helix.h
- Notation: horseshoe flow, fail-fast diagnostics on every function

**phoenix-core/src/helix_ingress.c** — STUB
- hex generation works, sidecar creation is a printf placeholder
- Missing: actual sidecar.json write, R2 upload call, D1 custody POST
- Worker: implement sidecar write (use helix_sidecar_t from helix.h),
  wire libcurl for R2 + D1 HTTP calls
- Notation: horseshoe flow — hex → sidecar → R2 → D1 → return result

---

### 2.3 MEDIUM — wiring and bridges

**CPT conductor systemd template**
- `phoenix-cpt@{hash}.service` — template so post-stage signaling fires for real
- freewheeling_stage.py already calls `systemctl --user start phoenix-cpt@{hash}.service`
- Worker: write the .service template to sector3/services/
- Notation: `ExecStart=python3 /path/to/cpt_conductor.py start`

**QR code generator**
- TAV system needs: top QR = state (white/grey/black), bottom QR = tier (T1-T4)
- Header QR BEFORE hash, footer QR AFTER hash — this is CRITICAL RULE 7
- No file exists for this yet
- Worker: write `sector4/tav_qr.py` — takes hex_id + state + tier → writes dual QR
- Notation: use `qrcode` library, embed in sidecar workflow

**sector2/clone-pool/ directory**
- Directory doesn't exist on disk
- Should contain: clone pool index JSON + R2 manifest
- Worker: create dir + write clone_pool_index.json schema
- Notation: index maps hex_id → R2 key → tier → state → version history

**dblhelix.py — DONE, was blocking on stale context**
- Original DoubleHelixStorage with numpy dependency. Task used to say
  "verify coms1/freewheeling.py is canonical, then archive dblhelix.py" —
  but coms1/freewheeling.py no longer exists anywhere in the live tree
  (archived as a fossil in the 2026-08-21 cleanup, along with the whole
  Python-side Helix engine — see PHOENIX_MANUAL.md §17 Architecture Notes).
  Nothing left to verify against.
- Resolved 2026-08-22: `_kali_import/` itself was a stale one-time
  recovery dump (not live code, see its own IMPORT_NOTES.md), so the whole
  folder was archived to
  `archive/kali-import-consolidation-20260822-113129/`. dblhelix.py is
  there now — reference only, not for production use.

**franken2.py** — see the fuller "franken.py / franken2.py" entry in
PRIORITY 1 above (2026-08-22: merge target archived, needs re-scoping).
- Notation: this is the Frank that manages physical RAM tiers, runs as daemon

---

### 2.4 LOW — polish and integration

**sector1/helix/helix_complete_stack.py** — 8-point TODO list
- Kernel hooks (mmap/page fault), FUSE filesystem, OOM handling, benchmarks
- Runs in userspace currently — needs LD_PRELOAD or FUSE for real vRAM
- Worker: implement FUSE integration (lowest-effort real vRAM path)
- Notation: LD_PRELOAD hook was built on Kali, may be recoverable

**sector1/helix/helix_vram.py** — EXPERIMENTAL
- Marked "use at own risk"
- Worker: review, either promote to stable or archive

**sector3/romeo_juliet/dbl_juliet.py** — not reviewed
- Worker: read + document what double-barrel juliet does differently

**sector3/quadengine/quadengine.py** — only 40 lines read
- Worker: read full file, verify quad stream handler is complete

**SECTOR4/coms1/propcoms.py** — only 40 lines read
- Leech module, 3-buffer versioning, magnet index
- Worker: read full file, document what's complete vs stub

**SECTOR4/coms1/integrated_guardian.py** — 40 lines read
- InstallerGuardian with friendship registry
- Worker: read full file, verify port + config guardian logic complete

**SECTOR4/coms1/syncthing_module.py** — WRONG LANGUAGE
- File is .py but contains JavaScript (HeIXSync class, require(), node-fetch)
- Worker: either rename to syncthing_module.js and wire into Node context
  OR rewrite as Python equivalent
- Notation: handles versioned distribution to test nodes + rollback

---

## PART 3 — LOST ARK DEPLOYMENT SEQUENCE

Once import method is wired, deploy in this order:

```
1. PREP (Linux side)
   - Build Phoenix_Prep folder (Ventoy USB, repos, phoenix_first_boot.ps1)
   - MinGW-w64 for C toolchain
   - Chris Titus winutil for debloat

2. TARGET MACHINE
   - Fresh Windows 10 Pro on new HD
   - Run phoenix_first_boot.ps1
   - Set env vars: PHOENIX_ROOT, CLONEPOOL_DIR, PHOENIX_AUTH, PHOENIX_WORKER_URL, D1_WORKER_URL

3. WSL BRIDGE
   - Install Debian on WSL2
   - Run saddle_block.sh (blocks Windows DNS/hosts hijacking)
   - Run align_dirs.sh in WSL (audit mode first, then live)
   - Uncomment breach_coms fstab lines in saddle_block.sh

4. DRIVES
   - Label 4 physical drives: breach_coms1-4
   - Verify Frank sees them: frank_save.py → system_pressure() → all 4 listed
   - Confirm best_drive() picks correct lowest-pressure mount

5. SERVICES
   - Run sector3/services/install-units.sh
   - Enable phoenix-frank-helix.service
   - Enable phoenix-frankenhelix.service
   - Enable phoenix-propagator.service
   - Enable phoenix-sector1.target + phoenix-sector2.target

6. INTAKE TEST
   - Drop test file → intake.sh file <path>
   - Verify: hex_id generated, sidecar.json written, D1 receipt POST'd
   - Verify: file appears in R2 clonepool
   - Verify: catalog.db has custody record

7. PIPELINE SMOKE TEST
   - python3 SECTOR4/pcs.py (all families should hit DEFINITIVE)
   - python3 SECTOR4/freewheeling_stage.py (3 test cases should commit)
   - python3 SECTOR4/cpt_conductor.py status
   - python3 sector2/propagator/propagator.py status
   - bash sector3/translator/translator.sh help
```

---

## PART 4 — FULL PIPELINE MAP (monolithic modular)

```
PHYSICAL HARDWARE
  breach_coms1-4 (labeled drives) → /mnt/d /mnt/e /mnt/f /mnt/g
  Frank routes by pressure, WSL bridges to Debian runtime

  ↓

SECTOR 1 — BOOT / KERNEL
  frank3_slot_a.ko + frank3_slot_b.ko  (kernel sideloads, 30s heartbeat)
  helix_kernel.c                        (C tier cache, L1/L2/L3, 88% pressure)
  phoenix_auth.py                       (SHA3-512 + BLAKE2b, 10-signal fingerprint)
  saddle_block.sh                       (blocks Windows control of WSL)
  align_dirs.sh                         (parity between WSL and bare metal)

  ↓

SECTOR 4 — HELIX + FRANK ENGINE (runs deepest, closest to hardware)
  ring0 interrupt → prefetch_interrupt() → PCS born
  FreewheelStage.call1/2/3 → probability climbs → definitive check
  snap_clone() → staged data → clonepool zone (breach_coms tier by zipcode)
  CptConductor → kernel slot selection → QuadralingualPacket
  HelixTranslationPipeline → DoubleHelixStorage → 4-language simultaneous
  helix_memory.py → L1/L2/L3/L4/L5 → ClaudeMemory → SectorRouter
  paging.py → dynamic swap, NVMe optimized, emergency circuit breaker

  ↓

SECTOR 2 — SERVICES / ORCHESTRATION
  frankenhelix.py → ring0 owner, COM4→1 chain, NVMe warm path
  frank_helix.py  → pressure daemon, ZMQ router, sideload bridge
  frank_save.py   → drive pressure, vault write, L2 buffer, D1 fan-out
  frank_http.py   → HTTP bridge :7347 /status /save /catalog
  propagator.py   → 6-target dispatch (vault/sql/d1/frank3/peer/windows)
  intake.sh       → TAV shell entry, vault mount check, calls intake.py

  ↓

SECTOR 3 — COMMS / NETWORKING (boundary layer)
  romeo.py        → ingress, opt2 mount verify, ZMQ PUSH to juliet
  juliet.py       → egress, payload execution, calls translator.sh on output
  quadengine.py   → keeps data quadralingual in transit
  translator.sh   → 9-backend package translation, catalog logging
  23 systemd units → service orchestration for all sectors

  ↓

CLONE POOL + CUSTODY
  R2 (Cloudflare)     → primary content storage (full blobs)
  D1 custody tables   → append-only immutable ledger
  D1 glossary tables  → real-time queryable catalog
  local trimmed cache → fast path, not source of truth
  packages-worker     → Cloudflare edge, /stats endpoint live

  ↓

LIFE FIRST LLM
  High-B local model running on Phoenix
  Quadralingual context via ClaudeMemory + HelixTranslationPipeline
  No vendor. No subscription. No internet required.
  Laurie's cushion.
```

---

## PART 5 — WORKER QUEUE (ordered by import method priority)

Each item below is one focused session.

```
PRIORITY 1 — import method
[ ] Write intake.py (hex + sidecar + D1) OR wire phoenix-intake.exe
[ ] Fix freewheeling.py bracket syntax error (line 97)
[ ] Fix helix_api.py two bugs (OVERFLOW_PATH, load_warm param)
[ ] Define 4 missing classes in helix_memory.py

PRIORITY 2 — pipeline wiring
[ ] Re-scope franken.py/franken2.py — merge target archived 2026-08-22, see PART 2.1
[ ] Complete helix_core.c (helix_create_sidecar, helix_log_event)
[ ] Complete helix_ingress.c (sidecar write + R2 upload + D1 POST)
[ ] Write setupsec4.py (proper bootstrap, replace chat log)
[ ] Write phoenix-cpt@.service template
[ ] Write sector4/tav_qr.py (dual QR generator, TAV system)

PRIORITY 3 — Lost Ark deployment
[ ] Write phoenix_first_boot.ps1 (dirs, env vars, PATH, C toolchain)
[ ] Uncomment breach_coms fstab entries in saddle_block.sh
[ ] Run align_dirs.sh on target machine (WSL audit → live create)
[ ] Run install-units.sh on Debian
[ ] End-to-end intake smoke test

PRIORITY 4 — complete abandoned files
[ ] Read + document propcoms.py full implementation
[ ] Read + document dbl_juliet.py
[ ] Read + verify integrated_guardian.py
[ ] Rename syncthing_module.py → .js OR rewrite in Python
[ ] Implement helix_complete_stack.py FUSE integration
[ ] Review + promote or archive helix_vram.py
[ ] Create sector2/clone-pool/ directory + index schema

PRIORITY 5 — Life First integration
[ ] Wire Life First app to local LLM endpoint on Phoenix
[ ] Wire ClaudeMemory / HelixTranslationPipeline to Life First context
[ ] MapTiler map panel in dashboard
[ ] Glossary panel wired to D1 live data
[ ] Shade UI + drawer filesystem
```

---

## ENVIRONMENT VARIABLES REQUIRED

```bash
PHOENIX_ROOT          = ~/Phoenix/Phoenix-DevOps-oS
PHOENIX_STAGE_TMP     = /tmp/phoenix_snap
CLONEPOOL             = /mnt/e/CLONEPOOL
PHOENIX_AUTH          = <hardware fingerprint token>
PHOENIX_WORKER_URL    = <Cloudflare worker URL>
D1_WORKER_URL         = packages-worker.phoenix-jwl.workers.dev
PHOENIX_CACHE         = ~/.phoenix/cache
```

---

## DEPENDENCIES TO INSTALL (one-time)

```bash
# Python
pip install pyzmq psutil qrcode pillow

# C toolchain (Debian/Ubuntu)
apt install gcc libssl-dev libcurl4-openssl-dev linux-headers-$(uname -r)

# Node (for syncthing_module.js)
apt install nodejs npm
npm install node-fetch

# Electron (for dashboard)
cd dashboard && npm install
```

---
# End of master build document
# Push this alongside CLAUDE.md at end of every session
