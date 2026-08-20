# Phoenix DevOps OS — Getting Started

**License:** GPL v3 · **Repo:** [jwl247/Phoenix-DevOps-oS](https://github.com/jwl247/Phoenix-DevOps-oS)

---

## What is Phoenix?

Phoenix DevOps OS is a deterministic, self-healing, agnostic operating environment.
It was built from the ground up to run a local LLM without any cloud dependency —
no vendor, no subscription, no single point of failure.

Everything runs on four sectors:

| Sector | Role |
|--------|------|
| **1** | Boot, GRUB, kernel (frank3, phoenix_auth) |
| **2** | Package handler, clone pool, intake authority |
| **3** | Comms and networking (romeo/juliet, quadengine) |
| **4** | Helix engine, Frank orchestrator, vault |

The core engine is **Helix** — a double-strand memory manager running 700k+ ops/sec
with a 100% cache hit rate, speaking four languages simultaneously.
**Frank** is the import authority and audit logger. He never moves.

---

## Requirements

### Windows (development / daily use)
- PowerShell 7 (`winget install Microsoft.PowerShell`)
- Git for Windows (`winget install Git.Git`)
- WSL2 with Debian or Ubuntu recommended for full sector access

### Linux (bare metal / external drive target)
- Ubuntu Server 22.04+ minimal (HWE kernel recommended)
- bash 5+, git, curl

### All platforms
- 4 GB RAM minimum (8 GB recommended for Helix engine)
- No GPU required — Phoenix is CPU-only by design

---

## Install

### Windows — one-liner

```powershell
irm https://raw.githubusercontent.com/jwl247/Phoenix-DevOps-oS/main/install.ps1 | iex
```

### Linux / macOS — one-liner

```bash
curl -fsSL https://raw.githubusercontent.com/jwl247/Phoenix-DevOps-oS/main/install.sh | bash
```

### What the installer does

1. Clones the repo to `~/Phoenix/Phoenix-DevOps-oS`
2. Creates `~/.usys/bin/` and adds it to your PATH
3. Writes `~/.phoenix_env.ps1` (Windows) or `~/.phoenix_env.sh` (Linux/macOS)
4. Registers the 7 global commands: `run`, `usys`, `clone`, `intake`, `status`, `align_dirs`, `get_distros`

> Open a **new terminal** after install. PATH changes do not apply to the current session.

---

## Verify the install

```bash
usys status
```

You should see sector file counts, mount status, and catalog statistics.
If the command is not found, see [Troubleshooting](#troubleshooting).

---

## The Dashboard

The Phoenix desktop surface is an Electron application.

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

**Auto-start at login:**

```powershell
# Windows — creates a Scheduled Task
cd sector3\services
.\install-dashboard-windows.ps1
```

```bash
# Linux — installs user systemd units
bash sector3/services/deploy-dashboard.sh
```

On first launch you will see an **auth modal**. Choose your AI provider:

| Option | When to use |
|--------|-------------|
| **OLLAMA** | Local model — no internet, no key needed. Requires `ollama serve`. |
| **SUBSCRIPTION** | Claude Code CLI already logged in (`claude login`). |
| **API KEY** | Anthropic API key. |

Check **Save** to persist the choice to `~/.phoenix/ai_auth.json`.

---

## Your first intake

Intake is how a file enters Phoenix. Frank registers it, assigns a hex identity,
writes a sidecar record, copies the bytes to the clone pool, and logs it in D1.

```bash
# PowerShell
intake .\myfile.py

# Bash / WSL
intake ./myfile.py
```

Check the result:

```bash
intake status
```

The file now lives in `~/Phoenix/clonepool` with a sidecar JSON next to it.
It is versioned, fingerprinted (SHA3-512), and logged. Nothing in the clone pool
is ever deleted.

---

## Global commands reference

| Command | What it does |
|---------|--------------|
| `usys status` | System health — sectors, mounts, catalog stats |
| `usys clone <file>` | Clone a file into the clone pool (Sector 2) |
| `usys search "<query>"` | Search the catalog |
| `intake <file>` | Full intake via Frank: hex → sidecar → clone pool → D1 |
| `clone <file> [cat] ["tag"]` | Shorthand clone with optional category and tag |
| `run <suite>` | Execute a suite from the clone pool without installation |
| `status` | Quick system health check |
| `align_dirs` | Align directory structures across Phoenix installations |
| `get_distros` | Detect Linux distributions and WSL environments |

Full detail: [`GLOBAL_COMMANDS.md`](./GLOBAL_COMMANDS.md)

---

## Environment variables

Set these in `~/.phoenix_env.ps1` (Windows) or `~/.phoenix_env.sh` (Linux/macOS).

| Variable | Purpose | Default |
|----------|---------|---------|
| `PHOENIX_ROOT` | Phoenix install root | `~/Phoenix/Phoenix-DevOps-oS` |
| `CLONEPOOL_DIR` | Local clone pool path | `~/Phoenix/clonepool` |
| `PHOENIX_WORKER_URL` | Cloudflare Worker URL for R2 + D1 sync | *(unset — offline mode)* |
| `PHOENIX_AUTH` | Worker auth token | *(unset)* |
| `PHOENIX_OLLAMA_URL` | Ollama endpoint | `http://localhost:11434` |

Without `PHOENIX_WORKER_URL` Phoenix works fully offline — intake writes local sidecars only and skips D1 sync.

---

## External drive build (Ubuntu target)

The canonical Phoenix build runs from an external drive booted as the OS.

### Phase 1 — Ubuntu base

1. Flash Ubuntu Server 22.04 minimal (HWE kernel) to an external drive.
2. Boot it. Confirm SSH access.
3. Run the Phoenix installer on the live system:
   ```bash
   curl -fsSL https://raw.githubusercontent.com/jwl247/Phoenix-DevOps-oS/main/install.sh | bash
   ```

### Physical drives (breach_coms)

Frank manages four labeled drives. Mount them by label, not UUID:

```
breach_coms4  →  /mnt/g  →  T1 PRIMARY  (master vault — never delete from here)
breach_coms3  →  /mnt/f  →  T2 SECONDARY
breach_coms2  →  /mnt/e  →  T3 TERTIARY (clone pool primary)
breach_coms1  →  /mnt/d  →  T4 TERTIARY (4-day window)
```

In WSL the same drives appear at `/mnt/d` through `/mnt/g` automatically.

The fstab template is in [`sector1/saddle_block.sh`](../sector1/saddle_block.sh) — uncomment 4 lines to mount by label.

### Deploy systemd services

```bash
bash sector3/services/deploy-dashboard.sh
systemctl --user status phoenix-desktop.target
```

---

## Project layout

```
Phoenix-DevOps-oS/
├── sector1/          Boot, kernel, auth, concierge
├── sector2/          Package handler, frank, clone pool, propagator
├── sector3/          Translator, romeo/juliet, quadengine, services
├── SECTOR4/          Helix engine, Frank vault
├── phoenix-core/     C-core Helix ingress/egress
├── dashboard/        Electron desktop
├── docs/             All documentation (you are here)
├── bootstrap/        LOL one-time bootstrap scripts
├── install.ps1       Windows installer
└── install.sh        Linux/macOS installer
```

---

## Troubleshooting

### Commands not found after install

Open a **new terminal**. PATH changes require a new session.

If still not found:

```powershell
# Windows — verify PATH
$env:PATH -split ';' | Select-String "usys"

# Linux/macOS — source manually
source ~/.phoenix_env.sh
export PATH="$HOME/.usys/bin:$PATH"
```

### PowerShell 7 not found (Windows)

```powershell
winget install Microsoft.PowerShell
```

### Git not found (Windows)

```powershell
winget install Git.Git
```

### Help Desk shows "AI offline"

Start Ollama locally:

```bash
ollama serve
ollama pull llama3.2   # or your chosen model
```

Or open the auth settings panel in the dashboard and switch to Claude.

### Throughput shows `--` in dashboard

The packages-worker is unreachable. Check `PHOENIX_WORKER_URL` is set correctly.
Offline mode still works — throughput just won't display.

### Intake fails D1 sync

Set `PHOENIX_WORKER_URL` and `PHOENIX_AUTH`. Without them, intake writes a local
sidecar only — this is normal offline operation, not an error.

---

## Further reading

| Document | Contents |
|----------|---------|
| [`QUICK_START.md`](./QUICK_START.md) | Condensed install + first commands |
| [`GLOBAL_COMMANDS.md`](./GLOBAL_COMMANDS.md) | Full command reference with examples |
| [`dashboard/manual/phoenix_manual.md`](../dashboard/manual/phoenix_manual.md) | Operator manual (also in the HUD) |
| [`dashboard/manual/laurie_guide.md`](../dashboard/manual/laurie_guide.md) | Plain-English guide, no technical knowledge needed |
| [`CLAUDE.md`](../CLAUDE.md) | Architecture master reference |

---

## License

GNU General Public License v3.0.
Build on Phoenix and your work stays open source too.

---

*Built with love. For Laurie. For everyone.*
