# Phoenix Package Handler
**UnitedSys — United Systems | jwl247**
**License:** GPL-3.0
**Part of:** Phoenix DevOps OS

---

## What This Is

The Phoenix Package Handler is the universal intake and catalog system for the Phoenix DevOps OS. It intercepts, registers, and tracks every file, package, config, and dependency that enters the system — regardless of origin or platform.

One pipeline. Every platform. Everything tracked.

```
file / package / config / api def
           ↓
       intake.sh
           ↓
  hex → sidecar → clonepool
           ↓
    custody receipt
           ↓
  D1 via packages-worker
           ↓
  catalog is always current
```

---

## Components

### `intake/intake.sh`

Universal intake script. Runs on Linux, macOS, and Windows (Git Bash).

- Self-registers on first run
- Accepts any file type (scripts, configs, binaries, yaml, json, service units)
- Auto-detects companion files (.service, .conf, .env, .yaml travel with parent)
- Generates hex identity from filename
- Writes sidecar.json with full metadata
- Versions files in clonepool (v1, v2, v3…)
- Writes local custody log (sqlite3)
- Reports to D1 via packages-worker (clonepool + custody + glossary)

### `worker/index.js`

Cloudflare Worker — **packages-worker**. The catalog API. Serves and receives data from `phoenix_dev_db` (D1).

**Endpoints:**

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | /health | — | Worker health check — returns version, DB table count |
| GET | /clonepool | — | List all files in clonepool. Filter by `?state=` (white/grey/black). Paginate with `?limit=` |
| GET | /clonepool/:id | — | Fetch single clonepool entry by hex_id or name |
| POST | /clonepool | ✓ | Register a new file into the pool (called by intake.sh) |
| GET | /custody | — | View custody ledger. Filter by `?hex=`. Paginate with `?limit=` |
| POST | /custody | ✓ | Append a custody receipt (called by intake.sh, append-only) |
| GET | /glossary | — | Browse the package glossary. Search with `?q=`, filter with `?category=` |
| GET | /glossary/:id | — | Fetch single glossary entry by hex or name |
| POST | /glossary | ✓ | Add or upsert a glossary entry |
| PUT | /glossary/:id | ✓ | Update description, category, state, or notes on an existing entry |
| DELETE | /glossary/:id | ✓ | Remove a glossary entry by hex or name |
| GET | /categories | — | List all glossary categories |
| GET | /packages | — | List all registered packages |
| GET | /packages/:id | — | Fetch a single package by name or ID |
| GET | /toc | — | Live table of contents — TOC tree + clonepool pool summary |
| GET | /versions | — | Version history. Filter by `?package=`. Paginate with `?limit=` |
| GET | /search | — | Cross-search clonepool + glossary + packages. Requires `?q=` |

**Auth:** All write endpoints (POST, PUT, DELETE) require `Authorization: Bearer <PHOENIX_AUTH>` header.

### `worker/wrangler.jsonc`

Cloudflare Wrangler configuration. Binds worker to `phoenix_dev_db` D1 database via `PHOENIX_DB` binding.

---

## Installation

### One-line install (Linux / macOS / Git Bash)

```bash
curl -fsSL https://raw.githubusercontent.com/jwl247/Phoenix-Package_handler/main/install.sh | bash
```

The installer will:
1. Check worker health at `pho-installer-worker`
2. Verify dependencies (git, curl, python3) — auto-installs if missing
3. Clone the repo to `~/Phoenix/package-handler`
4. Create directory structure (clonepool/, logs/, sidecars/)
5. Prompt for your `PHOENIX_AUTH` token
6. Write `~/.phoenix_env` and inject it into your shell profile
7. Symlink `intake.sh` → `/usr/local/bin/intake`
8. Register this machine with D1
9. Fetch and display the package glossary count

### Reinstall / Update

If the repo is already cloned, the installer pulls the latest automatically:

```bash
curl -fsSL https://raw.githubusercontent.com/jwl247/Phoenix-Package_handler/main/install.sh | bash
```

Or manually:

```bash
cd ~/Phoenix/package-handler
git pull --ff-only
chmod +x intake/intake.sh
sudo ln -sf "$PWD/intake/intake.sh" /usr/local/bin/intake
```

### Windows (PowerShell)

```powershell
irm https://raw.githubusercontent.com/jwl247/Phoenix-Package_handler/main/install.ps1 | iex
```

---

## Environment Variables

Set these before running `intake` (the installer writes them to `~/.phoenix_env`):

```bash
export PHOENIX_AUTH="your-token-here"
export PHOENIX_WORKER_URL="https://packages-worker.phoenix-jwl.workers.dev"
export CLONEPOOL_DIR="$HOME/Phoenix/clonepool"
```

Source them in your current shell:

```bash
source ~/.phoenix_env
```

---

## Quick Start

```bash
# Verify intake is installed
intake help

# Check worker + D1 connection status
intake status

# Intake a file
intake ./myfile.sh
intake ./nginx.conf direct "production config"
intake ./franken.py scripts "Frank v2"

# Register a backend-installed package
intake backend nodejs winget 20.11.0
intake backend python apt 3.13.0
```

---

## Command Reference

### `intake <file> [category] [label]`

Intakes a file into the clonepool. Generates a hex identity, writes a sidecar, versions the file, logs custody, and reports to D1.

```bash
intake ./myapp.sh
intake ./nginx.conf direct "production nginx"
intake ./deploy.py scripts "deploy v3"
```

**Arguments:**
- `<file>` — path to the file to intake (required)
- `[category]` — optional category name (e.g. `scripts`, `configs`, `direct`)
- `[label]` — optional human-readable label or note

---

### `intake backend <name> <manager> <version>`

Registers a backend-installed package (one not physically intaked as a file — e.g. system packages, language runtimes).

```bash
intake backend nodejs winget 20.11.0
intake backend python apt 3.13.0
intake backend nginx brew 1.25.0
```

**Arguments:**
- `<name>` — package name
- `<manager>` — package manager used (winget, apt, brew, dnf, pip, npm, etc.)
- `<version>` — installed version string

---

### `intake status`

Checks the live connection to the packages-worker and D1. Prints worker health, version, and DB table count.

```bash
intake status
```

---

### `intake help`

Prints full usage information and available commands.

```bash
intake help
```

---

## Glossary

The glossary is the Phoenix system's unified package dictionary. Every file, package, config, and dependency that flows through intake gets a glossary entry — indexed by hex identity, searchable by name or category.

### Glossary Entry Fields

| Field | Type | Description |
|-------|------|-------------|
| `hex` | string | Deterministic hex identity derived from filename (primary key) |
| `b58` | string | Base58 encoding of hex (compact alternative ID) |
| `name` | string | Canonical package or file name |
| `category_hex` | string | Hex of the parent category (joins to `categories` table) |
| `description` | string | Human-readable description of what this package does |
| `state` | string | QR state: `white` (active), `grey` (deprecated), `black` (retired/compromised) |
| `version` | string | Package version string |
| `platform` | string | Target platform (linux, macos, windows, all) |
| `backend` | string | Package manager or install method (apt, winget, brew, pip, etc.) |
| `size` | integer | File size in bytes |
| `pool_path` | string | Path to the clonepool directory for this entry |
| `sidecar` | string | Path to the sidecar.json metadata file |
| `amended` | boolean | 1 if this entry has been updated since initial intake |
| `intaked_at` | timestamp | When the entry was first registered |
| `grace_until` | timestamp | Grace period end (for deprecated entries) |
| `evicted_at` | timestamp | When the entry was retired/evicted |
| `notes` | string | Free-form notes or annotations |

### Glossary API Usage

```bash
# Browse full glossary
curl https://packages-worker.phoenix-jwl.workers.dev/glossary

# Search by name
curl "https://packages-worker.phoenix-jwl.workers.dev/glossary?q=nginx"

# Filter by category
curl "https://packages-worker.phoenix-jwl.workers.dev/glossary?category=scripts"

# Fetch a specific entry
curl https://packages-worker.phoenix-jwl.workers.dev/glossary/nginx.conf

# Add a new entry (auth required)
curl -X POST https://packages-worker.phoenix-jwl.workers.dev/glossary \
  -H "Authorization: Bearer $PHOENIX_AUTH" \
  -H "Content-Type: application/json" \
  -d '{
    "hex": "abc123...",
    "name": "nginx.conf",
    "description": "Production nginx configuration",
    "state": "white",
    "platform": "linux",
    "backend": "apt"
  }'

# Update an entry (auth required)
curl -X PUT https://packages-worker.phoenix-jwl.workers.dev/glossary/nginx.conf \
  -H "Authorization: Bearer $PHOENIX_AUTH" \
  -H "Content-Type: application/json" \
  -d '{"description": "Updated production nginx config", "state": "grey"}'

# Delete an entry (auth required)
curl -X DELETE https://packages-worker.phoenix-jwl.workers.dev/glossary/nginx.conf \
  -H "Authorization: Bearer $PHOENIX_AUTH"
```

### Categories

Categories group glossary entries into logical buckets. Each category has its own hex identity.

```bash
# List all categories
curl https://packages-worker.phoenix-jwl.workers.dev/categories
```

---

## File Identity System

Every file gets a deterministic hex identity derived from its name:

```
"intake.sh" → 737363726970747332f696e74616b65
```

This hex is:
- The clonepool directory name
- The sidecar filename
- The D1 primary key
- Permanent and reproducible

---

## QR State System

Every file in the clonepool carries two QR codes:

- **Top QR** → status pointer
  - White = active
  - Grey = deprecated
  - Black = compromised/retired
- **Bottom QR** → location pointer
  - T1/T2/T3/T4 — max 4 folders deep

---

## Companion Files

Files that belong together travel together:

```
nginx.sh       ← main file
nginx.service  ← auto-detected companion
nginx.conf     ← auto-detected companion
```

All versioned as one unit. Edit the `.service` file in the clonepool, it propagates via HelixSync.

---

## Platform Support

| Platform | Shell | Status |
|----------|-------|--------|
| Linux | bash | ✅ Native |
| macOS | bash | ✅ Native |
| Windows | Git Bash | ✅ Supported |

> **Windows note:** Git Bash required. Python 3.x required. Both ship with Phoenix installer.

---

## Deploy the Worker

```bash
cd worker
wrangler secret put PHOENIX_AUTH
wrangler deploy
```

---

## Part of Phoenix DevOps OS

- **Sector 2** → intake lives here (file intake authority)
- **Sector 3** → pattern recognition, bypass routing
- **Sector 4** → stage, prefetch, systemd
- **D1** → phoenix_dev_db (the backbone — 41 tables)
- **Frank** → kernel micro, orchestrates all sectors

---

Built by JW — Phoenix DevOps OS | UnitedSys — United Systems
GPL-3.0 — Free as in freedom

---

## Community & Peer Review

Phoenix uses an **opt-in distribution model** — reviewed content is identified by a content hash, verified via QR, advertised through an update channel, and only downloaded if you explicitly choose to pull it.

> Nothing is pushed. Availability is announced. Users pull only what they choose.

### How It Works

```
Create → Submit → Review → Approve → Hash → Register → Advertise → Opt-In Pull → Verify → Use
```

- **Submit** — any community member can submit an artifact for peer review
- **Review** — human or multi-party review determines acceptability (not authenticity)
- **Hash** — approved artifacts get a SHA-256 hex identity (the canonical fingerprint)
- **QR** — a QR code is generated encoding the hash — a pointer to verification, not the content
- **Advertise** — availability is announced via the update feed (metadata only, no payload)
- **Pull** — users opt-in to fetch and verify — most never pull, incurring zero cost
- **Verify** — hex hash is verified at pull time; QR can be scanned at any time post-distribution
- **Revoke** — artifacts can be revoked in the registry without deleting them from the clonepool

### Peer Review API (packages-worker)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | /review | — | List all submissions (filter by `?status=`) |
| GET | /review/:hex | — | Fetch review record for a specific artifact |
| POST | /review | ✓ | Submit an artifact for review |
| POST | /review/:hex/vote | ✓ | Cast a vote (approve / reject / abstain) |
| GET | /review/:hex/votes | — | View all votes on a submission |
| POST | /review/:hex/revoke | ✓ | Revoke an approved artifact |
| GET | /verify/:hex | — | Verify an artifact — returns status + review provenance |
| GET | /feed | — | Opt-in availability feed of approved artifacts |

### Website Pages

| Page | Path | Description |
|------|------|-------------|
| Review Queue | `/review` | Active submissions, filterable by category/status/platform |
| Submit | `/submit` | Submit an artifact for community review |
| Verified Feed | `/feed` | Approved artifacts available for opt-in pull |
| Verify | `/verify/:hex` | Verify any artifact by hex hash or QR scan |
| Revocation Log | `/revoked` | Public log of revoked artifacts and reasons |

### Full Specification

See [PEER_REVIEW.md](./PEER_REVIEW.md) for the complete platform specification including:
- All 9 lifecycle stages
- D1 schema additions (submissions, reviews, revocations, advertisement_feed)
- QR state system (white / grey / black)
- Economic model and non-goals
- Where community contributions are welcome
