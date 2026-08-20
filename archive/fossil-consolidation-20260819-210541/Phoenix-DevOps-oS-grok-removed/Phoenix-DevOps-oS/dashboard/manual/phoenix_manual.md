# Phoenix DevOps OS — Operator Manual

**Version:** 0.1.0 · **HUD location:** Help Desk → MANUAL tab

---

## 1. What Phoenix Is

Phoenix DevOps OS is a deterministic, versioned operating environment with four sectors:

| Sector | Role |
|--------|------|
| **Sector 1** | Boot, GRUB, kernel (frank3, helix, phoenix_auth) |
| **Sector 2** | Package handler, clone pool, intake |
| **Sector 3** | Comms, networking (romeo/juliet, quadengine) |
| **Sector 4** | Helix engine, Frank orchestrator, vault |

**Helix** is the double-strand memory engine. **Frank** is the import authority and audit logger — it never moves.

**Clone pool:** D1 glossary + custody ledger; R2 holds raw file bytes. Local cache at `~/Phoenix/clonepool` or `PHOENIX_CACHE`.

---

## 2. Desktop Command Center

The Electron dashboard is the Phoenix desktop surface.

### Left panel — Sector control panel

**Switches** gate each subsystem. **ON** = that sector is active, its status command runs, and sector-specific CLI commands are allowed. **OFF** = blocked for gated commands (e.g. `intake` needs Sector 2 ON).

| Switch | Controls |
|--------|----------|
| **Sector 1** | Boot/kernel — `sector1/`, frank3, GRUB |
| **Sector 2** | Packages/clone — `intake`, clonepool (`intake status`, `usys clone`) |
| **Sector 3** | Comms/network — `sector3/services/`, dashboard systemd units |
| **Sector 4** | Helix/Frank — `SECTOR4/`, vault (`usys search`) |
| **Helix Engine** | C-core — `phoenix-core/` ingress/egress |

**Sector actions** (dropdown + EXECUTE):
- **status** — run that sector's health command in the CLI drawer
- **open** — open the sector folder in the OS and navigate the file tree
- **services** — list `sector3/services/` (Sector 3)

Quick buttons: **STATUS** (`usys status`), **INTAKE** (`intake status`), **HELP** (manual excerpt).

Switch state persists in browser storage between sessions.

### Center — Operator surface

**Filesystem** — browse Phoenix root, home, drives, ROOT tree. Runnable files (`.ps1`, `.sh`, `.py`, `.js`, `.exe`, `.cmd`, `.bat`) show a **▶** button; click loads **RUNIT**, double-click runs.

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

## 3. Help Desk (AI)

The Help Desk answers operator questions about Phoenix.

### Provider chain (automatic)
1. **Ollama** (local) — primary. Requires Ollama running at `http://localhost:11434`.
2. **Claude** (subscription or API key) — fallback when Ollama is unavailable.

Click the provider line at the bottom of the Help Desk to change auth settings.

### Boot auth modal
On launch, choose:
- **OLLAMA** — local model (default for Help Desk)
- **SUBSCRIPTION** — Claude Code CLI (`claude login`)
- **API KEY** — Anthropic API key

Settings save to `~/.phoenix/ai_auth.json` when the save checkbox is checked.

### Example questions
- "How do I intake a file?"
- "What is Sector 4?"
- "Why is throughput showing --?"
- "How do I set PHOENIX_WORKER_URL?"

---

## 4. Global Commands

| Command | Action |
|---------|--------|
| `usys status` | System summary |
| `usys clone <file>` | Clone file into clonepool (Sector 2) |
| `intake <file>` | Intake via package handler (hex → sidecar → clonepool → D1) |
| `phoenix-intake <file>` | C-core intake (when `phoenix-core` is built) |
| `clone <file>` | Global clone shortcut |

### Environment variables

| Variable | Purpose |
|----------|---------|
| `PHOENIX_ROOT` | Phoenix install root |
| `CLONEPOOL_DIR` | Local clonepool path (default `~/Phoenix/clonepool`) |
| `PHOENIX_WORKER_URL` | Cloudflare Worker URL for R2 + D1 sync |
| `PHOENIX_AUTH` | Worker auth token |
| `PHOENIX_CACHE` | Local trimmed cache directory |
| `PHOENIX_OLLAMA_URL` | Ollama endpoint (default `http://localhost:11434`) |

---

## 5. Intake Flow

```
file → hex ID (SHA-256) → sidecar.json → R2 bytes → D1 custody → local cache
```

**PowerShell (Windows):**
```powershell
intake .\myfile.py
intake status
```

**C core (when built):**
```bash
cd phoenix-core && make intake
./tools/phoenix-intake myfile.py
./tools/phoenix-intake --resolve <hex_id>
```

Offline mode works without `PHOENIX_WORKER_URL` — local sidecar only.

---

## 6. Four Repos / Remotes

| Remote | Repo | Line |
|--------|------|------|
| `origin` | Phoenix-DevOps-oS | Python-era main |
| `ii` | Phoenix-Devops-oS_II | C / Lost Ark line |

**Do not mix:** Python intake scripts and C `phoenix-core` share endpoints but are separate code paths. Edit `phoenix-core/` for C work; `New folder/` is scaffold only.

---

## 7. Desktop Boot (starts with the system)

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

## 8. Troubleshooting

| Symptom | Fix |
|---------|-----|
| Help Desk says "AI offline" | Start Ollama: `ollama serve`. Or set Claude key in auth modal. |
| Throughput shows `--` | packages-worker not reachable; check Worker URL and network. |
| Intake fails D1 sync | Set `PHOENIX_WORKER_URL` and `PHOENIX_AUTH`. Offline intake still writes local sidecar. |
| Claude CLI not found | `npm install -g @anthropic-ai/claude-code` then `claude login` |
| Ollama model missing | `ollama pull llama3.2` (or your chosen model) |

---

## 9. Architecture Notes (C Line)

`phoenix-core/` implements Helix ingress/egress in C:
- `helix_ingress_intake()` — write path
- `helix_egress_resolve()` — read path with local cache + R2 fallback
- `helix_http.c` — Worker HTTP via libcurl

Python SECTOR4 Helix (`freewheeling.py`, `helix_memory.py`) is the in-process memory engine — separate from C-core, same vocabulary.

---

## 10. Contacts & License

- **Operator:** Jerry Leftwich (@jwl247)
- **Co-founder:** Jerilynn (UX, InfoSec)
- **License:** GPL v3

*This manual lives in the HUD. Ask the Help Desk anything not covered here.*