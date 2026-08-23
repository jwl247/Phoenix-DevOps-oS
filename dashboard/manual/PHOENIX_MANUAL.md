# Phoenix DevOps OS — Master Manual

**Version:** 0.1.0 · **HUD location:** Help Desk → MANUAL tab
**Repo:** [jwl247/Phoenix-DevOps-oS](https://github.com/jwl247/Phoenix-DevOps-oS) · **License:** GPL v3

This is the single canonical reference for Phoenix — install, architecture,
commands, dashboard, deployment, troubleshooting. Everything that used to be
split across README/QUICK_START/GETTING_STARTED/AUTHENTICATION/
GLOBAL_COMMANDS now lives here. See [`LAURIE_GUIDE.md`](./LAURIE_GUIDE.md)
for the plain-English, no-jargon version.

---

## 1. What Phoenix Is

Phoenix DevOps OS is a deterministic, self-healing, agnostic operating
environment, built to run a local LLM without any cloud dependency — no
vendor, no subscription, no single point of failure. One repo, one OS,
everything in its sector.

| Sector | Role |
|--------|------|
| **1** | Boot, GRUB, kernel (frank3, helix, phoenix_auth) |
| **2** | Package handler, clone pool, intake authority, apps (Life First) |
| **3** | Comms and networking (romeo/juliet egress, quadengine, Cloudflare workers) |
| **4** | Helix engine, Frank orchestrator, vault |

**Helix** is the double-strand memory engine — twin single-pass,
peer-optimized, 700,000 ops/sec benchmarked with a 100% cache hit rate,
speaking four languages simultaneously (Python, Bash, PS, Zsh), compressing
under load (zlib level 5) to create more effective RAM.

**Frank** is the import authority and audit logger — every action logged,
never moves.

**Clone pool:** D1 glossary + custody ledger; R2 holds raw file bytes. Local
cache at `~/Phoenix/clonepool` or `PHOENIX_CACHE`. Output is the clone —
nothing translates inside the vault, ever.

### LLM engine — bigger than your hardware

Phoenix runs LLMs larger than physical RAM permits via paged vRAM through
the Helix memory stack. Context splits into pages — hot pages stay in L1,
cold pages compress into L3. A 70B model's full context can fit on an 8GB
machine.

Model ladder (intent-aware, automatic fallback):
- `llama3.1:70b` — Memory AI (deep recall)
- `llama3.1:8b` — Schedule, Messenger, Voice
- `phi3:mini` — Notifications, quick replies

### Life First App — the reason Phoenix exists

7-module AI companion for high-functioning autism support, self-hosted, no
subscriptions, no vendor lock-in:

| Module | Function |
|--------|----------|
| 1 | Database |
| 2 | API Router |
| 3 | Schedule AI |
| 4 | Messenger AI |
| 5 | Memory AI |
| 6 | Notification AI |
| 7 | Voice Commander |

---

## 2. Requirements

**Windows (development / daily use):**
- PowerShell 7 (`winget install Microsoft.PowerShell`)
- Git for Windows (`winget install Git.Git`)
- WSL2 with Debian or Ubuntu recommended for full sector access

**Linux (bare metal / external drive target):**
- Ubuntu Server 22.04+ minimal (HWE kernel recommended)
- bash 5+, git, curl

**All platforms:**
- 4 GB RAM minimum (8 GB recommended for the Helix engine)
- No GPU required — Phoenix is CPU-only by design, GPU drivers blacklisted

---

## 3. Install

**Windows — one-liner:**
```powershell
irm https://raw.githubusercontent.com/jwl247/Phoenix-DevOps-oS/main/install.ps1 | iex
```

**Linux / macOS — one-liner:**
```bash
curl -fsSL https://raw.githubusercontent.com/jwl247/Phoenix-DevOps-oS/main/install.sh | bash
```

Or for local development, clone the repo first, then run
`pwsh -ExecutionPolicy Bypass -File .\install.ps1` (Windows) or
`bash install.sh` (Linux/macOS) from inside it.

**Seelen UI toolbar plugins (Windows, optional):**
```powershell
irm https://raw.githubusercontent.com/jwl247/Phoenix-DevOps-oS/main/sector1/kernel/seelen/install-phoenix-seelen.ps1 | iex
```

**Pull LLM models (after Ollama is installed):**
```bash
ollama pull llama3.1:8b
ollama pull llama3.1:70b
```

### What the installer does

1. Clones the repo to `~/Phoenix/Phoenix-DevOps-oS`
2. Creates `~/.usys/bin/` and adds it to your PATH
3. Writes `~/.phoenix_env.ps1` (Windows, legacy/Git-Bash-on-Windows copy —
   see §11 for the canonical Windows auth store) or `~/.phoenix_env.sh`
   (Linux/macOS, canonical there)
4. Registers the 7 global commands: `run`, `usys`, `clone`, `intake`,
   `status`, `align_dirs`, `get_distros`
5. On Windows, installs a `Phoenix Dashboard` desktop shortcut

Open a **new terminal** after install — PATH changes don't apply to the
current session.

### Verify

```bash
usys status
```

You should see sector file counts, mount status, and catalog statistics.

---

## 4. Global Commands

| Command | Purpose |
|---------|---------|
| `run <suite>[@version] [args...]` | Execute a suite from the clone pool without installing it. Supports version pinning, arg passthrough, `--dry-run`. |
| `usys <command>` | Main Phoenix interface — `status`, `clone <file>`, `intake <file>`, `search <query>`, `open <file>` (`.lol`/`.phx`), `init` |
| `clone <file> [category] ["tag"]` | Clone a file into the clone pool with versioning + JSON sidecar metadata. `--dry-run` to test. |
| `intake <file>` | Full intake via Frank: hex ID → sidecar → clone pool → D1 custody. |
| `status` | Quick system health check (sector file counts, mounts, systemd, catalog, git). |
| `align_dirs [source] [target]` | Align directory structures across Phoenix installations. |
| `get_distros` | Detect Linux distributions and WSL environments. |

All 7 work from Windows CMD/PowerShell 7, Linux bash, and macOS zsh (bash-dependent ones via Git Bash on Windows).

Examples:
```bash
usys search "nginx config"
clone ./deploy.sh scripts "production deployment"
run data-processor@1.2.3 --source /data
for file in *.py; do clone "$file" scripts "python scripts"; done
```

### Environment variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `PHOENIX_ROOT` | Phoenix install root | `~/Phoenix/Phoenix-DevOps-oS` |
| `CLONEPOOL_DIR` | Local clone pool path | `~/Phoenix/clonepool` |
| `PHOENIX_WORKER_URL` | Cloudflare Worker URL for R2 + D1 sync | *(unset — offline mode)* |
| `PHOENIX_AUTH` | Shared bearer token for protected Worker routes | *(unset)* |
| `PHOENIX_CACHE` | Local trimmed cache directory | *(unset)* |
| `PHOENIX_OLLAMA_URL` | Ollama endpoint | `http://localhost:11434` |
| `PHOENIX_GROK_KEY` | xAI Grok API key (cloud fallback) | *(unset)* |
| `PHOENIX_INTAKE` | Path to intake.sh (Sector 2) | set by install.ps1/sh |
| `PHOENIX_INTAKE_SECTOR4` | Path to Sector 4 intake | set by install.ps1/sh |

Without `PHOENIX_WORKER_URL`, Phoenix works fully offline — intake writes
local sidecars only and skips D1 sync. See §11 for how to set
`PHOENIX_AUTH`/`PHOENIX_WORKER_URL` correctly per platform.

### Running a full distro (`usys run <distro>`)

`run` isn't limited to scripts — a `runtime: qemu` suite (see
`tools/poc/debian.suite.json`) boots a full disk image via QEMU. No
installer, no WSL, no Hyper-V required; Phoenix brings the OS. Confirmed
working: `usys run debian` boots Debian 12 (Bookworm) from the clone pool.

**One-time setup** (suite + disk image aren't bundled in git — too large):
1. `usys distro fetch-qemu` for instructions, or `winget install
   SoftwareFreedomConservancy.QEMU` then copy the install directory's
   contents into the `qemu-system` suite folder in your clone pool
2. Download the distro image into its suite folder (e.g.
   `clonepool/debian/debian-12.5-genericcloud-amd64.qcow2` from
   `cloud.debian.org` — verify against the published `SHA512SUMS` first)
3. Copy `tools/poc/debian-seed/` to `clonepool/debian/seed/` — this is the
   cloud-init login (see below)

**Run it:** `usys run debian --accel tcg` (or `--accel hyperv` on Windows
with the Hypervisor Platform feature enabled, for near-native speed instead
of software emulation)

**Login:** cloud disk images ship with no usable console password —
`root`'s password login is blocked by Debian's default sshd config
regardless of what's set. `usys run` auto-detects a `seed/user-data` folder
next to the suite's image and serves it over a local HTTP server
(`127.0.0.1:8000`, reachable from the Debian side at `10.0.2.2` — QEMU user-mode
networking's standard host mapping) via a `-smbios` cloud-init hint. No ISO
tooling needed. This seeds a sudo-capable `phoenix` user (password
`phoenix`), reachable once booted via:
```bash
ssh -p 2222 phoenix@127.0.0.1
```
(`hostfwd=tcp::2222-:22` is added to the VM's networking automatically
whenever a seed is detected.)

To add a new distro suite, copy `tools/poc/debian.suite.json` as a
template and drop a `seed/user-data`+`seed/meta-data` pair (standard
cloud-init NoCloud format) next to the new image.

---

## 5. Desktop Command Center

The Electron dashboard is the Phoenix desktop surface.

**Start it:**
```powershell
# Windows
cd dashboard
.\start.ps1
```
```bash
# Linux
cd dashboard
bash start-desktop.sh
```

### Left panel — Sector control panel

**Switches** gate each subsystem. **ON** = that sector is active, its status
command runs, and sector-specific CLI commands are allowed. **OFF** =
blocked for gated commands (e.g. `intake` needs Sector 2 ON).

| Switch | Controls |
|--------|----------|
| **Sector 1** | Boot/kernel — `sector1/`, frank3, GRUB |
| **Sector 2** | Packages/clone — `intake`, clonepool (`intake status`, `usys clone`) |
| **Sector 3** | Comms/network — `sector3/services/`, dashboard systemd units |
| **Sector 4** | Helix/Frank — `sector4/`, vault (`usys search`) |
| **Helix Engine** | C-core — `phoenix-core/` ingress/egress |

**Sector actions** (dropdown + EXECUTE):
- **status** — run that sector's health command in the CLI drawer
- **open** — open the sector folder in the OS and navigate the file tree
- **services** — list `sector3/services/` (Sector 3)

Quick buttons: **STATUS** (`usys status`), **INTAKE** (`intake status`), **HELP** (manual excerpt).

Switch state persists in browser storage between sessions.

### Center — Operator surface

**Filesystem** — browse Phoenix root, home, drives, ROOT tree. Runnable
files (`.ps1`, `.sh`, `.py`, `.js`, `.exe`, `.cmd`, `.bat`) show a **▶**
button; click loads **RUNIT**, double-click runs.

**Operator drawer** (bottom of filesystem zone):
- **PHOENIX CLI** — preset dropdown, command input, RUN/CLR. Output scrolls above the input (like a terminal).
- **RUNIT DRAWER** — drop a file, browse, or pick from the tree; optional args; **▶ RUNIT** executes via Phoenix (`run-file` IPC).

### Center — Holographic viewport
- **SYSTEM STATUS** — operational state
- **HELIX ENGINE** — core engine status
- **THROUGHPUT** — live ops/sec from packages-worker when reachable
- **HELP DESK** — Ollama availability (Claude fallback)

### Navigation bar
Browse Phoenix root, home, documents, desktop, drives, and pinned frequent paths. Use **+ add path** to pin directories.

### Right panel — Metrics + Help Desk
CPU, memory, disk gauges. Below that: **Help Desk** (chat) and **Manual** (this document).

---

## 6. Help Desk (AI)

The Help Desk answers operator questions about Phoenix.

### Provider chain (automatic)
1. **Ollama** (local) — primary. Requires Ollama running at `http://localhost:11434`.
2. **Claude** (subscription or API key) — fallback when Ollama is unavailable.

Click the provider line at the bottom of the Help Desk to change auth settings.

### Boot auth modal
On launch, choose:

| Option | When to use |
|--------|-------------|
| **OLLAMA** | Local model — no internet, no key needed. Requires `ollama serve`. Default for Help Desk. |
| **GROK** | xAI cloud fallback. Paste your `XAI_API_KEY`/`PHOENIX_GROK_KEY`. |
| **SUBSCRIPTION** | Claude Code CLI already logged in (`claude login`). |
| **API KEY** | Anthropic API key. |

Check **Save** to persist the choice to `~/.phoenix/ai_auth.json`.

### Example questions
- "How do I intake a file?"
- "What is Sector 4?"
- "Why is throughput showing --?"
- "How do I set PHOENIX_WORKER_URL?"

---

## 7. Intake Flow

Intake is how a file enters Phoenix. Frank registers it, assigns a hex
identity, writes a sidecar record, copies the bytes to the clone pool, and
logs it in D1.

```
file → hex ID (SHA3-512) → sidecar.json → R2 bytes → D1 custody → local cache
```

**PowerShell (Windows):**
```powershell
intake .\myfile.py
intake status
```

**Bash / WSL:**
```bash
intake ./myfile.py
```

**C core (when built):**
```bash
cd phoenix-core && make intake
./tools/phoenix-intake myfile.py
./tools/phoenix-intake --resolve <hex_id>
```

The file now lives in `~/Phoenix/clonepool` with a sidecar JSON next to it —
versioned, fingerprinted, logged. Nothing in the clone pool is ever deleted.
Offline mode works without `PHOENIX_WORKER_URL` — local sidecar only.

**Folder naming rule:** once a folder's name is confirmed correct per the
repo's naming convention, intake it (`usys intake`/`usys clone`) as part of
finalizing that folder — don't leave it un-intaked.

---

## 8. Worker Authentication

Worker sync is optional. Set `PHOENIX_WORKER_URL` and `PHOENIX_AUTH` only
when this machine should access the protected D1/R2 Worker.

Phoenix uses **one** HTTP format for every protected Phoenix service:

```http
Authorization: Bearer <PHOENIX_AUTH>
```

Clients read the token from `PHOENIX_AUTH`; services compare it to their
deployed secret of the same name. Never send it in query parameters, custom
`X-Phoenix-Auth` headers, logs, screenshots, source code, or the dashboard
AI settings.

`PHOENIX_AUTH` is currently a shared service token — suitable for a trusted
self-hosted deployment, but it is **not** per-user identity or authorization.
Keep distinct credentials for third-party providers (e.g. `ANTHROPIC_API_KEY`)
and for future role-specific services. This is separate from
`lifefirst-mcp`'s `MCP_ACCESS_TOKEN` — don't confuse the two.

Local Electron IPC and loopback-only utilities are not HTTP services; they
rely on the signed local application boundary and must not expose their
privileged actions to remote content.

### Setting it, per platform

**Windows — canonical:**
```powershell
usys init
```
Prompts once for `PHOENIX_WORKER_URL`/`PHOENIX_AUTH` (skips anything already
set), stores them as your Windows **user-scope environment variables**
(registry-backed, visible under System Properties → Environment Variables —
not a plaintext file), and wires your PowerShell profile (`$PROFILE`) so
every new terminal loads them silently. Re-running `usys init` any time is
safe. Don't hand-edit `~/.phoenix_env.ps1` with the token — that file is a
legacy copy for Git-Bash-on-Windows contexts, not the source of truth.

**Linux/macOS — canonical:**
`~/.phoenix_env.sh` *is* the source of truth. Edit it directly, or re-run
the installer to be prompted again:
```bash
export PHOENIX_WORKER_URL="https://your-worker.example.workers.dev"
export PHOENIX_AUTH="your-token-here"
```

Restart the terminal or dashboard after changing either value.

---

## 9. Four Repos / Remotes

| Remote | Repo | Line |
|--------|------|------|
| `origin` | Phoenix-DevOps-oS | Python-era main |
| `ii` | Phoenix-Devops-oS_II | C / Lost Ark line |

`sector2/package-handler/` is a `git subtree` of the standalone
`Phoenix-Package_handler` repo — edit it in place here, it stays in sync via
subtree merges, not a submodule checkout.

**Do not mix:** Python intake scripts and C `phoenix-core` share endpoints
but are separate code paths. Edit `phoenix-core/` for C work; `New folder/`
is scaffold only.

---

## 10. Desktop Boot (starts with the system)

**Windows — autostart at logon:**
```powershell
cd sector3\services
.\install-dashboard-windows.ps1
```
Creates Scheduled Task `PhoenixDesktop` → runs `dashboard\start.ps1` at login.
Config: `~/.phoenix/phoenix.env` (sets `PHOENIX_SKIP_AUTH_MODAL=1` for unattended boot).

**Linux — autostart at graphical login:**
```bash
bash sector3/services/deploy-dashboard.sh
```
Installs user systemd target `phoenix-desktop.target`:
- `phoenix-ollama.service` — local Help Desk LLM
- `phoenix-dashboard.service` — Electron shell via `dashboard/start-desktop.sh`

```bash
loginctl enable-linger $USER    # done automatically by deploy script
systemctl --user status phoenix-desktop.target
journalctl --user -u phoenix-dashboard -f
```

**Manual launch (any platform):**
```powershell
cd dashboard
.\start.ps1
```

---

## 11. External Drive Build (Ubuntu Target)

The canonical Phoenix build runs from an external drive booted as the OS.

### Phase 1 — Ubuntu base

1. Flash Ubuntu Server 22.04 minimal (HWE kernel) to an external drive.
2. Boot it. Confirm SSH access.
3. Run the Phoenix installer on the live system:
   ```bash
   curl -fsSL https://raw.githubusercontent.com/jwl247/Phoenix-DevOps-oS/main/install.sh | bash
   ```

### Physical drives (breach_coms)

Frank manages four labeled physical drives — real hardware, mounted by
label (not UUID), never treated as an abstract/software construct:

```
breach_coms4  →  /mnt/g  →  T1 PRIMARY   (master vault — never delete from here)
breach_coms3  →  /mnt/f  →  T2 SECONDARY
breach_coms2  →  /mnt/e  →  T3 TERTIARY  (clone pool primary)
breach_coms1  →  /mnt/d  →  T4 TERTIARY  (4-day window)
```

In WSL the same drives appear at `/mnt/d` through `/mnt/g` automatically.
The fstab template is in `sector1/saddle_block.sh` — uncomment 4 lines to
mount by label.

### Deploy systemd services

```bash
bash sector3/services/deploy-dashboard.sh
systemctl --user status phoenix-desktop.target
```

---

## 12. Project Layout

```
Phoenix-DevOps-oS/
├── sector1/
│   ├── kernel/           Phoenix Universal Kernel, LLM engine, file tree service
│   ├── kernel/seelen/    Seelen UI plugins + one-liner installer
│   ├── helix-lightning/  Helix Lightning Kernel (Frank5, HelixI/E, 8-channel IPC)
│   ├── grub/             Phoenix GRUB boot controller, PAM auth, usys registry
│   ├── auth/              phoenix_auth.py
│   ├── concierge/        Concierge bridge
│   ├── helix/             Helix stack (kernel, run, conf)
│   └── kernels/           frank3_slot_a.c, frank3_slot_b.c
├── sector2/
│   ├── package-handler/  Universal intake, clone pool API, QR state system (git subtree)
│   ├── unitedsys/        Multi-backend package manager (11 backends)
│   ├── apps/lifefirst/   Life First AI modules 1-7 (PHP + MySQL)
│   ├── apps/lifefirst-android/  Kotlin Android app
│   ├── frank/             frank_helix.py, frank_save.py, frank_http.py
│   ├── ring0/             frankenhelix.py
│   └── propagator/       propagator.py
├── sector3/
│   ├── translator/       translator.sh (OUTPUT ONLY — never intake)
│   ├── romeo_juliet/     romeo.py, juliet.py, dbl_juliet.py
│   ├── quadengine/       quadengine.py
│   ├── workers/          Cloudflare Workers, D1 distribution backend
│   └── services/         systemd .service + .target files
├── sector4/               intake/, pcs.py, vault/
├── phoenix-core/          C-core Helix ingress/egress
├── dashboard/             Electron desktop (this manual lives in dashboard/manual/)
├── docs/                  Remaining reference docs (GLOSSARY.md, GITHUB_SETUP.md, etc.)
├── bootstrap/             LOL one-time bootstrap scripts
├── install.ps1            Windows installer
└── install.sh             Linux/macOS installer
```

---

## 13. Critical Rules

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

## 14. TAV Address System

Every file in Phoenix gets a permanent, deterministic identity:

```
filename -> SHA3-512 -> first 8 bytes -> base58 = shortest unique address

Header QR (before hash):  USYS:<b58>:HEADER        state: white/grey/black
Footer QR (after hash):   USYS:<b58>:FOOTER:<sha3>  tier:  T1/T2/T3/T4
```

---

## 15. Troubleshooting

| Symptom | Fix |
|---------|-----|
| Help Desk says "AI offline" | Start Ollama: `ollama serve`. Or set Claude/Grok key in auth modal. |
| Throughput shows `--` | packages-worker not reachable; check `PHOENIX_WORKER_URL` and network. Offline mode still works — throughput just won't display. |
| Intake fails D1 sync | Set `PHOENIX_WORKER_URL` and `PHOENIX_AUTH` per §11. Offline intake still writes a local sidecar — this is normal, not an error. |
| Claude CLI not found | `npm install -g @anthropic-ai/claude-code` then `claude login` |
| Ollama model missing | `ollama pull llama3.2` (or your chosen model) |
| Commands not found after install | Open a **new terminal** (PATH updates need a new session). Windows: `$env:PATH -split ';' \| Select-String "usys"`. Linux/macOS: `source ~/.phoenix_env.sh; export PATH="$HOME/.usys/bin:$PATH"`. Still missing → re-run the installer. |
| Permission denied (Linux/macOS) | `chmod +x ~/.usys/bin/*` |
| Git Bash not found (Windows) | `winget install Git.Git` — needed by bash-dependent commands (`intake`, `status`, `align_dirs`, `get_distros`) |
| PowerShell 7 not found (Windows) | `winget install Microsoft.PowerShell` — needed by `usys`/`clone` |

---

## 16. Uninstall

**Windows:**
```powershell
Remove-Item -Recurse -Force "$HOME\Phoenix"
Remove-Item -Recurse -Force "$HOME\.usys"
Remove-Item "$HOME\.phoenix_env.ps1"
```
Then remove `%USERPROFILE%\.usys\bin` from user PATH in System Properties
(Environment Variables), and delete `PHOENIX_ROOT`/`PHOENIX_AUTH`/etc. from
the same User-scope list if you want to fully clear `usys init`'s values.

**Linux/macOS:**
```bash
rm -rf ~/Phoenix
rm -rf ~/.usys
rm ~/.phoenix_env.sh
```
Then remove the Phoenix block from `~/.bashrc` and `~/.zshrc`.

---

## 17. Architecture Notes (C Line)

`phoenix-core/` implements Helix ingress/egress in C:
- `helix_ingress_intake()` — write path
- `helix_egress_resolve()` — read path with local cache + R2 fallback
- `helix_http.c` — Worker HTTP via libcurl

**Currency note (2026-08-22):** earlier versions of this manual referenced a
Python "sector4 Helix" (`freewheeling.py`, `helix_memory.py`) as a live
in-process memory engine running alongside the C line. Neither file exists
outside `archive/fossil-consolidation-20260819-210541/` anymore — they were
archived as fossils in the 2026-08-21 repo cleanup. Live `sector4/` today
only contains `intake/`, `pcs.py`, `vault/`, and `paging.py`/
`paging_windows.py` (see §4, revived from archive same session).

**But** a *different*, real Python Helix memory engine does exist live at
`sector1/helix/helix_complete_stack.py` — `HelixCache`/`HelixMemoryManager`/
`HelixFS`/`HelixSystem`, real L1/L2/L3 tiering with compression and
promotion/demotion, zero external deps, 883 lines. Verified working this
session with a real stress test
(`sector1/helix/helix_stack_stress_test.py`) that forces actual tiering
pressure — 360 demotions, 170 compressions, 40 promotions, all genuine.
Its own demo() is misleading (test data too small to ever trigger tiering,
looks broken when it isn't) — trust the stress test's numbers over the
demo's. What's genuinely still missing: OS-level transparency — only code
that explicitly calls `helix.memory.malloc()` benefits today. The file's
own roadmap comments already scope the options (LD_PRELOAD malloc
interception, or a kernel module) — not undertaken yet, a real scope
decision for a future session, not a small addition.

---

## 18. Contacts & License

- **Operator:** Jerry Leftwich (@jwl247) — ironworker, systems builder
- **Co-founder:** Jerilynn (UX, switches, InfoSec/red team)
- **License:** GNU General Public License v3.0 — free to use, free to build
  on. If you build on Phoenix, your work stays open source too.

Phoenix was built from necessity — vendor lock-in threatened a project built
for someone who needed it. It runs the Life First app: an AI-powered
accountability companion built for Laurie, open sourced for everyone.

*This manual lives in the HUD. Ask the Help Desk anything not covered here.*
