# UnitedSys (usys) — Command Reference
**Version:** 0.2.0 | Target: v4.6

Universal file registration, versioning, clone pool, and hotswap system. Like apt — but for any file, any distro, any language.

---

## Install

```bash
bash scripts/install.sh
source ~/.bashrc
```

---

## Commands

### Core
| Command | Description |
|---------|-------------|
| `usys init` | First time setup — creates `~/.usys/`, initializes DB |
| `usys register <file> <name>` | Register any file into the system |
| `usys call <name> [args]` | Call a registered file by name |
| `usys swap <name> <newfile>` | Hotswap live — no restart needed |
| `usys rollback <name> [version]` | Roll back to previous version |
| `usys list` | List all registered packages |
| `usys info <name>` | Full version history + swap log |
| `usys remove <name>` | Unregister (keeps version history) |
| `usys where <name>` | Show file location |
| `usys search <query>` | Search registry by name/description/type |
| `usys install <pkg> [--mgr]` | Install via system pkg manager + auto-register |
| `usys version` | Show usys version |

### Clone Pool
| Command | Description |
|---------|-------------|
| `usys intake <file> <pool> [state] [desc]` | Full intake pipeline into clone pool |
| `usys deprecate <name>` | Mark grey — queued for auto-hotswap |
| `usys hotswap-check` | Scan for deprecated files ready to swap |
| `usys sync <name> <dest>` | Sync current version to destination |
| `usys clone <name> <dest>` | Clone with full version history |

---

## usys install — Package Manager Auto-Detection

```bash
usys install sqlite3          # auto-detects: apt → pip → npm → cargo
usys install flask --pip      # force pip
usys install webpack --npm    # force npm
usys install ripgrep --cargo  # force cargo
usys install htop --apt       # force apt
```

Detection order: `apt` → `pacman` → `dnf` → `yum` → `brew` → `pip` → `npm` → `cargo`

---

## Aliases (from phoenix_aliases.sh)

```bash
ul          # usys list
ur          # usys register
ui          # usys info
uc          # usys call
uw          # usys where
us          # usys swap
urb         # usys rollback
uss         # usys search
udep        # usys deprecate
uhc         # usys hotswap-check
```

---

## File Locations

```
~/.usys/
├── usys.db          — SQLite registry (packages, versions, swaplog)
├── usys.sh          — main binary
├── bin/             — callable wrappers (auto-added to PATH)
├── versions/        — stored version history per package
│   └── <name>/
│       └── v1_<filename>, v2_<filename>, ...
├── intake.sh        — clone pool intake pipeline
├── node.json        — this node's identity
└── log/             — operation log
```

---

## Clone Pool

Default root: `/mnt/clonepool` (override with `POOL_ROOT` env var)

```
/mnt/clonepool/
└── <hex_of_filename>/
    ├── v1_<filename>          — versioned file
    ├── <hex>.sidecar.json     — source of truth metadata
    ├── <hex>_header.png       — QR code: state (white/black/grey)
    ├── <hex>_footer.png       — QR code: location/tier color
    └── <hex>_sheet.png        — combined header+footer sheet
```

**States:**
- `white` — good / active
- `black` — corrupt / trash
- `grey` — deprecated → auto-hotswaps when opportunity presents

**Tier colors (bottom QR):**
- Tier 1: red, blue, yellow
- Tier 2: green, orange, purple
- Tier 3: cyan, magenta, lime
- Tier 4: brown, pink, teal, navy

---

## DB Schema

```sql
packages  — name, current_ver, source_path, filetype, tags, description
versions  — package, version, store_path, hash, size, note
swaplog   — package, from_ver, to_ver, action, ts, note
```

All foreign keys enforced. WAL mode. No sudo required.
