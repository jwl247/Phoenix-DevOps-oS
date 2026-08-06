# Phoenix DevOps OS

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg?style=for-the-badge)](https://www.gnu.org/licenses/gpl-3.0)
[![Sponsor jwl247](https://img.shields.io/badge/Sponsor%20jwl247-%E2%9D%A4-red?logo=github&style=for-the-badge)](https://github.com/sponsors/jwl247)

> Agnostic. Deterministic. Prefetched. Self-healing. Fast as you please.

One repo. One OS. Everything in its sector.

Phoenix is a fully open source, self-hostable operating system built for real people
regardless of circumstance, skill level, or budget. No vendor lock-in. No paywalls.
No barriers. Built from the ground up after vendor lock-in threatened a project built
for someone who needed it.

---

## What is Phoenix?

At its core is **Helix** — a true Double Helix twin single-pass memory engine running
700,000 ops/sec with 100% cache hit rate. It speaks four languages simultaneously,
compresses under load to create more effective RAM, and self-heals.

On top of Helix sits **CoPES** (Core Operating and Processing Engine Substrate), which
handles the clone pool, Frank output coordination, paged LLM execution, and the
package handler that talks to 10 distros at once.

On top of CoPES sits the OS layer — four sectors, seven global commands, a
drag-and-drop file tree, and a Seelen UI toolbar that shows you exactly what Phoenix
is doing at all times.

Running on top of all of it: **Life First App** — the AI-powered accountability
companion that started this whole project. Built for Laurie. Open sourced for everyone.

---

## Architecture — Four Sectors

```
sector1/   Boot, kernel, GRUB, Helix Lightning Kernel, Seelen UI plugins
sector2/   Intake authority, package handler, clone pool, apps (Life First)
sector3/   Comms, romeo/juliet egress, quadengine, Cloudflare workers
sector4/   CoPES substrate, Helix engine, Frank, vault, storage
```

### Helix — The Engine

| Metric | Value |
|--------|-------|
| Throughput | 700,000 ops/sec |
| Cache hit rate | 100% |
| Languages | 4 simultaneously (Python, Bash, PS, Zsh) |
| Compression | zlib level 5 — more load = more effective RAM |
| Architecture | Twin single-pass, peer-optimized, PCS torrent model |

### LLM Engine — Bigger Than Your Hardware

Phoenix runs LLMs larger than physical RAM permits via paged vRAM through the Helix
memory stack. Context is split into pages — hot pages stay in L1, cold pages compress
into L3. A 70B model's full context fits on an 8GB machine.

Model ladder (intent-aware, automatic fallback):
- `llama3.1:70b` — Memory AI (deep recall)
- `llama3.1:8b` — Schedule, Messenger, Voice
- `phi3:mini` — Notifications, quick replies

### Life First App — The Reason Phoenix Exists

7-module AI companion for high-functioning autism support:

| Module | Function |
|--------|----------|
| 1 | Database |
| 2 | API Router |
| 3 | Schedule AI |
| 4 | Messenger AI |
| 5 | Memory AI |
| 6 | Notification AI |
| 7 | Voice Commander |

Self-hosted on Ubuntu Server. No subscriptions. No vendor lock-in. Claude or Ollama
for AI — your choice, your data.

---

## Install

**Windows (PowerShell):**
```powershell
irm https://raw.githubusercontent.com/jwl247/Phoenix-DevOps-oS/main/install.ps1 | iex
```

**Linux / macOS:**
```bash
curl -fsSL https://raw.githubusercontent.com/jwl247/Phoenix-DevOps-oS/main/install.sh | bash
```

**Seelen UI toolbar plugins (Windows):**
```powershell
irm https://raw.githubusercontent.com/jwl247/Phoenix-DevOps-oS/main/sector1/kernel/seelen/install-phoenix-seelen.ps1 | iex
```

**Pull LLM models (after Ollama is installed):**
```bash
ollama pull llama3.1:8b
ollama pull llama3.1:70b
```

---

## Global Commands

After install, these work from anywhere:

| Command | What it does |
|---------|-------------|
| `usys status` | Full system health |
| `run <suite>` | Run a package from clonepool without installing |
| `clone <src> <dst>` | Clone file/dir into clone pool |
| `intake <file>` | Register a file through the Phoenix intake pipeline |
| `status` | Quick health check |
| `align_dirs` | Directory alignment |
| `get_distros` | Fetch/update distro cache |

---

## Seelen UI Toolbar

Four live toolbar plugins surface Phoenix state on your Windows desktop:

| Plugin | Shows |
|--------|-------|
| Phoenix Status | Helix ops/sec, Frank ring count, clone pool size |
| Phoenix LLM | Active model, session count, large model indicator |
| Clone Pool | Active item count, deprecated/retired warnings |
| Life First | Heart icon, pending notification count from Module 6 |

Status server: `http://localhost:8765` (starts with the kernel)

---

## Structure

```
sector1/
  kernel/           Phoenix Universal Kernel, LLM engine, file tree service
  kernel/seelen/    Seelen UI plugins + one-liner installer
  helix-lightning/  Helix Lightning Kernel (Frank5, HelixI/E, 8-channel IPC)
  grub/             Phoenix GRUB boot controller, PAM auth, usys registry
  auth/             phoenix_auth.py
  concierge/        Concierge bridge
  helix/            Helix stack (kernel, run, conf)
  kernels/          frank3_slot_a.c, frank3_slot_b.c

sector2/
  package-handler/  Universal intake, clone pool API, QR state system
  unitedsys/        Multi-backend package manager (11 backends)
  apps/lifefirst/   Life First AI modules 1-7 (PHP + MySQL)
  apps/lifefirst-android/  Kotlin Android app
  frank/            frank_helix.py, frank_save.py, frank_http.py
  ring0/            frankenhelix.py
  propagator/       propagator.py

sector3/
  translator/       translator.sh (OUTPUT ONLY — never intake)
  romeo_juliet/     romeo.py, juliet.py, dbl_juliet.py
  quadengine/       quadengine.py
  workers/          Cloudflare Workers, D1 distribution backend
  services/         systemd .service + .target files

sector4/
  copes/            CoPES substrate (helix.py, frank.py, helix_memory.py, security/)
  copes-preload/    Bootstrap config for CoPES
  storage/          Double-Helix StorageOS (97k ops/sec, OctahedronBlock)
  heix/             HEix7.3GII multi-layer Helix (C + Python + JS)
  vault/            phoenix_push.sh, download.sh
  helix/            Master Helix engine
  frank/            Frank (environment orchestrator, audit logger)
```

---

## Critical Rules

1. Everything stays quadralingual until `translator.sh` at sector3 boundary
2. `translator.sh` fires on OUTPUT ONLY — never on intake or clone
3. Romeo handles ingress / Juliet handles egress
4. Never translate inside breach_coms drives — vault stays quadralingual
5. Never delete from breach_coms4 (master vault)
6. No GPU-dependent solutions — blacklisted
7. Frank is the only path to the LLM — nothing calls Ollama directly
8. Header QR before hashing / Footer QR after — never swap
9. Real code only — no demos

---

## TAV Address System

Every file in Phoenix gets a permanent, deterministic identity:

```
filename -> SHA3-512 -> first 8 bytes -> base58 = shortest unique address

Header QR (before hash):  USYS:<b58>:HEADER        state: white/grey/black
Footer QR (after hash):   USYS:<b58>:FOOTER:<sha3>  tier:  T1/T2/T3/T4
```

---

## The Story

Phoenix was born from necessity. When vendor lock-in threatened everything built for
the person I love, I had no choice but to build the foundation myself.

I'm a blue-collar ironworker — no smarter than anyone I can name — but I have a knack
for turning plans into reality, whether that's steel or software.

Built with love. For Laurie. For everyone.

---

## License

GNU General Public License v3.0 — free to use, free to build on.
If you build on Phoenix, your work stays open source too.

[![Sponsor jwl247](https://img.shields.io/badge/Sponsor%20jwl247-%E2%9D%A4-red?logo=github&style=for-the-badge)](https://github.com/sponsors/jwl247)
