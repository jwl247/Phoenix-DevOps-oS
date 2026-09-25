# Phoenix Package Handler
**UnitedSys — United Systems | jwl247**
**License:** GPL-3.0
**Part of:** Phoenix DevOps OS

> **Standalone-readiness (as of 2026-09-20):** this is already a real `git subtree`
> of the standalone `Phoenix-Package_handler` GitHub repo (not just a copy —
> `git subtree push` works today), and none of its core logic hard-depends on
> the rest of Phoenix. It is NOT yet a one-command deploy elsewhere. To get there:
> 1. **Write a full `schema.sql`.** Only `peer-review/schema.sql` exists today
>    (just the review-voting tables). The other ~40 tables that make this
>    system work — `clonepool`, `custody`, `glossary`, `versions`, `deps`,
>    `mirrors`, `manifests`, etc. — only exist as whatever's live on
>    `phoenix_dev_db` right now, never captured as migrations. Without this,
>    standing up a second independent instance means manually reverse-engineering
>    the schema from a live database.
> 2. **Decide what belongs in that schema.** `phoenix_dev_db` is shared across
>    more than just this system — exclude tables that belong to other Phoenix
>    apps sharing the same database (e.g. `office_authors`/`office_documents`/
>    `office_notifications` belong to the separate Office app, not here).
> 3. **Know the one soft coupling:** `intake.sh`'s dependency-tracking feature
>    (added 2026-09-20) calls `sector3/translator/translator.sh` by relative
>    path, which sits outside this subtree. It degrades gracefully if that path
>    doesn't exist (dependency-edge tracking just silently no-ops), so it won't
>    break a standalone deploy — but it's worth knowing about before showcasing.
>
> None of this is urgent — parked until it's actually needed.

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

### `intake.sh`

Universal intake script (lives directly in this directory — there is no
`intake/` subdirectory). Runs on Linux, macOS, and Windows (Git Bash).

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
| GET | /health | — | Worker health check — returns version, DB table count. **The only unauthenticated route on this worker.** |
| GET | /clonepool | ✓ | List all files in clonepool. Filter by `?state=` (white/grey/black) or `?sensitive=1`. Paginate with `?limit=` |
| GET | /clonepool/:id | ✓ | Fetch single clonepool entry by hex_id or name |
| POST | /clonepool | ✓ | Register a new file into the pool (called by intake.sh) |
| GET | /custody | ✓ | View custody ledger. Filter by `?hex=`. Paginate with `?limit=` |
| POST | /custody | ✓ | Append a custody receipt (called by intake.sh, append-only) |
| GET | /glossary | ✓ | Browse the package glossary. Search with `?q=`, filter with `?category=` |
| GET | /glossary/:id | ✓ | Fetch single glossary entry by hex or name |
| POST | /glossary | ✓ | Add or upsert a glossary entry |
| PUT | /glossary/:id | ✓ | Update description, category, state, or notes on an existing entry |
| DELETE | /glossary/:id | ✓ | Remove a glossary entry by hex or name |
| GET | /categories | ✓ | List all glossary categories |
| GET | /packages | ✓ | List all registered packages |
| GET | /packages/:id | ✓ | Fetch a single package by name or ID |
| GET | /toc | ✓ | Live table of contents — TOC tree + clonepool pool summary |
| GET | /connections | ✓ | The Atlas — every component/feature documented in a `CONNECTIONS.md`. Search with `?q=`, filter with `?area=`. See `docs/ATLAS.md` |
| GET | /connections/:id | ✓ | Fetch one Atlas entry (fuzzy — falls back to a LIKE match if there's no exact hex/name/path hit) |
| GET | /connections/:id/related | ✓ | The "snow globe" — the entry plus exactly 8 related entries |
| POST | /connections | ✓ | Add or upsert an Atlas entry (used by `parse-connections.js`) |

`clonepool.sensitive` (boolean) is separate from `state` — `state` is lifecycle
status (active/deprecated/retired), `sensitive` flags content intake.sh's
filename heuristic caught (`*auth*`, `*secret*`, `*password*`, `*credential*`,
`*token*`, `.env`) as needing restricted handling downstream, independent of
whether it's active. Set automatically by intake.sh when a matching file is
intaked and the operator confirms; not inferred by the worker.
| GET | /versions | ✓ | Version history. Filter by `?package=`. Paginate with `?limit=` |
| GET | /deps | ✓ | Dependency edges. Filter by `?package=`, or `?package=&reverse=true` for reverse lookup (what depends on this) |
| POST | /deps | ✓ | Record a dependency edge (package, depends_on, version_req, optional) — reported by `intake_from_backend()` via `translator.sh`'s `deps` verb |
| GET | /search | ✓ | Cross-search clonepool + glossary + packages. Requires `?q=` |

**Auth — two layers, both required (verified against `index.js` and Cloudflare
Access config, 2026-09-24):**
1. **App layer:** every route above except `/health` requires
   `Authorization: Bearer <PHOENIX_AUTH>` — this used to be write-only; as of
   the 2026-09-21 security fix, GET routes are gated too. If you're following
   an older example that only hits GET routes without this header, it will
   401.
2. **Edge layer:** Cloudflare Access sits in front of the whole worker.
   Machine/script access (not a browser login) needs a service token sent as
   `CF-Access-Client-Id` / `CF-Access-Client-Secret` headers, or requests get
   silently redirected to the Access login page — which some HTTP clients
   (Node's `fetch`, Python's `urllib`) will follow and report back as a
   false "200 OK" even though nothing actually happened. Always check the
   response is real JSON, not an HTML login page, if a script's success is
   ever in doubt.

### `worker/wrangler.jsonc`

Cloudflare Wrangler configuration. Binds worker to `phoenix_dev_db` D1 database via `PHOENIX_DB` binding.

---

## Installation

> **Two different setups exist, and they install two different command names —
> verified against the actual `install.sh` in this directory (2026-09-24).
> Pick the one that matches what you're doing:**

### If you're inside this monorepo (Phoenix-DevOps-oS) — most likely case

No install step needed. `intake.sh` runs directly:

```bash
bash sector2/package-handler/intake.sh status
bash sector2/package-handler/intake.sh ./myfile.sh
```

Or, once `scripts/usys.ps1` is loaded in your shell profile (the repo-root
`install.ps1` sets this up), the global wrapper reaches the same script:

```powershell
usys clone ./myfile.sh    # confirmed: bin/clone → tools/clone.sh → this intake.sh
```

### Standalone install (outside the monorepo, via the mirrored `Phoenix-Package_handler` repo)

```bash
curl -fsSL https://raw.githubusercontent.com/jwl247/Phoenix-Package_handler/main/install.sh | bash
```

The installer will (verified against `install.sh` directly, not assumed):
1. Detect platform + package manager
2. Clone the repo to `~/Phoenix/Phoenix-Package_handler` (not `~/Phoenix/package-handler`)
3. Create `~/Phoenix/{clonepool,intake,logs,workers}/`
4. Write `~/.phoenix_env` with `PHOENIX_HOME`/`PHOENIX_INSTALL_DIR`/`PHOENIX_CLONEPOOL`/`PHOENIX_LOG` and hook it into your shell profile
5. Install a shim at `/usr/local/bin/phoenix-handler` (falls back to `~/Phoenix/bin/phoenix-handler` if `/usr/local/bin` isn't writable) — **the command is `phoenix-handler`, not `intake`** on this path
6. Best-effort register this machine with the worker (`POST /installed/register` — non-fatal if it fails)

The installer's own final output tells you to run `phoenix-handler status` —
that's the real command name this path sets up, confirmed by reading the
script's summary block directly.

### Reinstall / Update (standalone path)

```bash
curl -fsSL https://raw.githubusercontent.com/jwl247/Phoenix-Package_handler/main/install.sh | bash
```

Or manually:

```bash
cd ~/Phoenix/Phoenix-Package_handler
git pull --ff-only
chmod +x intake.sh
sudo ln -sf "$PWD/intake.sh" /usr/local/bin/intake   # your own choice of command name — the installer itself uses "phoenix-handler"
```

### Windows (PowerShell, standalone path)

```powershell
irm https://raw.githubusercontent.com/jwl247/Phoenix-Package_handler/main/install.ps1 | iex
```

`install.ps1` is a separate script from the monorepo's own repo-root
`install.ps1` — verify which one you're running if both are on the machine.

---

## Environment Variables

```bash
export PHOENIX_AUTH="your-token-here"
export PHOENIX_WORKER_URL="https://packages-worker.phoenix-jwl.workers.dev"
export CLONEPOOL_DIR="$HOME/Phoenix/clonepool"    # or E:/Phoenix/clonepool on the primary dev machine — see CLAUDE.md drive map
export CF_ACCESS_CLIENT_ID="..."       # required as of 2026-09-21 — Cloudflare Access sits in front of every worker route now
export CF_ACCESS_CLIENT_SECRET="..."   # see "Auth" note under Endpoints below
```

Inside the monorepo these are normally already set by `~/.phoenix/phoenix.env`
(written by the repo-root `install.ps1`) — check `usys status` before setting
them by hand. On the standalone path, the installer writes `~/.phoenix_env`
(no `CF_ACCESS_*` — that requirement postdates this installer script; add it
yourself if you're pulling from the standalone repo after 2026-09-21).

Source them in your current shell:

```bash
source ~/.phoenix_env
```

---

## Quick Start

Command name depends on which install path you used — see above
(`intake.sh` directly / `usys clone` inside the monorepo, `phoenix-handler`
on the standalone path). Examples below use `intake.sh` directly, which
always works regardless of install path:

```bash
# Verify it runs
bash intake.sh help

# Check worker + D1 connection status
bash intake.sh status

# Intake a file
bash intake.sh ./myfile.sh
bash intake.sh ./nginx.conf direct "production config"
bash intake.sh ./franken.py scripts "Frank v2"

# Register a backend-installed package
bash intake.sh backend nodejs winget 20.11.0
bash intake.sh backend python apt 3.13.0
```

---

## Command Reference

> `intake` below is a stand-in for whatever you actually set up — `bash intake.sh`,
> `usys clone` (monorepo), or `phoenix-handler` (standalone installer). See
> Installation above for which one applies to you.

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

### `intake clone <name>` / `intake clone <dir>`

Pulls a file (or, for directory snapshots, a whole restored directory) back out of the clonepool into the current working directory — the reverse of `intake <file>`. Directory detection is automatic: if the hex has a directory-type sidecar, `intake clone` restores the snapshot; otherwise it clones the latest single-file version.

Before copying anything, it hashes the local clonepool copy (SHA3-512) and compares it against the baseline recorded in D1 at intake time. A mismatch refuses the clone outright rather than handing back a corrupted or altered file — this is what gates hot-swap and clone-to-workdir. Files intaked before this check existed have no baseline yet and clone through with a warning instead of a hard block.

```bash
intake clone nginx.conf
intake clone myproject           # restores the latest directory snapshot
intake clone myproject v2        # restores a specific version
```

See [Integrity Verification](#integrity-verification) below for what the pass/fail output means.

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

Every call below needs all three headers (see the Auth note under Endpoints
above) — shown once here via a reusable variable, omitted from each example
line for readability:

```bash
AUTH_HEADERS=(-H "Authorization: Bearer $PHOENIX_AUTH" -H "CF-Access-Client-Id: $CF_ACCESS_CLIENT_ID" -H "CF-Access-Client-Secret: $CF_ACCESS_CLIENT_SECRET")

# Browse full glossary
curl "${AUTH_HEADERS[@]}" https://packages-worker.phoenix-jwl.workers.dev/glossary

# Search by name
curl "${AUTH_HEADERS[@]}" "https://packages-worker.phoenix-jwl.workers.dev/glossary?q=nginx"

# Filter by category
curl "${AUTH_HEADERS[@]}" "https://packages-worker.phoenix-jwl.workers.dev/glossary?category=scripts"

# Fetch a specific entry
curl "${AUTH_HEADERS[@]}" https://packages-worker.phoenix-jwl.workers.dev/glossary/nginx.conf

# Add a new entry
curl -X POST "${AUTH_HEADERS[@]}" https://packages-worker.phoenix-jwl.workers.dev/glossary \
  -H "Content-Type: application/json" \
  -d '{
    "hex": "abc123...",
    "name": "nginx.conf",
    "description": "Production nginx configuration",
    "state": "white",
    "platform": "linux",
    "backend": "apt"
  }'

# Update an entry
curl -X PUT "${AUTH_HEADERS[@]}" https://packages-worker.phoenix-jwl.workers.dev/glossary/nginx.conf \
  -H "Content-Type: application/json" \
  -d '{"description": "Updated production nginx config", "state": "grey"}'

# Delete an entry
curl -X DELETE "${AUTH_HEADERS[@]}" https://packages-worker.phoenix-jwl.workers.dev/glossary/nginx.conf
```

### Categories

Categories group glossary entries into logical buckets. Each category has its own hex identity.

```bash
# List all categories (auth required — see above)
curl "${AUTH_HEADERS[@]}" https://packages-worker.phoenix-jwl.workers.dev/categories
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

## Integrity Verification

Every file gets a SHA3-512 and BLAKE2b hash computed at intake time and stored on its `clonepool` D1 row (`hash_sha3`, `hash_blake2`) — the trusted baseline for that hex.

`intake clone` re-hashes the local clonepool copy against that baseline every time it's used, before the file ever reaches your working directory:

- **Match** → clone proceeds, and a `POST /clonepool/:hex/validate` call flips `qr_valid`/`verified_at` on the D1 row.
- **Mismatch** → clone is refused with an `INTEGRITY FAILURE` message. Re-intake the file from a trusted source to clear it.
- **No baseline** (older intakes, from before this check existed) → clone proceeds with a warning; the baseline gets set the next time that file is re-intaked.

Directory snapshots (`intake clone <dir>`) verify every file inside the restored snapshot the same way — one mismatch anywhere in the directory blocks the whole restore.

```bash
# Check a hex's stored baseline directly (needs all three headers — see Auth note above)
curl -H "Authorization: Bearer $PHOENIX_AUTH" \
  -H "CF-Access-Client-Id: $CF_ACCESS_CLIENT_ID" -H "CF-Access-Client-Secret: $CF_ACCESS_CLIENT_SECRET" \
  "https://packages-worker.phoenix-jwl.workers.dev/clonepool/<hex>?meta=true"
```

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
wrangler deploy
```

**Do not** run `wrangler secret put PHOENIX_AUTH` directly here — `worker/wrangler.jsonc`
itself warns against this (as of 2026-09-21, three other workers share this same
token and drifting out of sync silently breaks auth on all of them, which has
happened more than once). Use `../rotate-phoenix-auth.sh` instead — it sets
and verifies `PHOENIX_AUTH` across every worker leg together.

---

## Part of Phoenix DevOps OS

- **Sector 2** → intake lives here (file intake authority)
- **Sector 3** → pattern recognition, bypass routing
- **Sector 4** → stage, prefetch, systemd
- **D1** → phoenix_dev_db (the backbone — 50 tables as of 2026-09-24; table count drifts, check `GET /health` for the current number rather than trusting this line)
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
| GET | /review | ✓ | List all submissions (filter by `?status=`) |
| GET | /review/:hex | ✓ | Fetch review record for a specific artifact |
| POST | /review | ✓ | Submit an artifact for review |
| POST | /review/:hex/vote | ✓ | Cast a vote (approve / reject / abstain) |
| GET | /review/:hex/votes | ✓ | View all votes on a submission |
| POST | /review/:hex/revoke | ✓ | Revoke an approved artifact |
| GET | /verify/:hex | ✓ | Verify an artifact — returns status + review provenance |
| GET | /feed | ✓ | Opt-in availability feed of approved artifacts |

> **Note (2026-09-24):** all of these were public GET routes before the
> 2026-09-21 security fix gated every route except `/health`. That fix was
> aimed at `clonepool`/`glossary`, but it also caught the peer-review browsing
> routes — which this same worker serves an anonymous public HTML frontend
> for (`/review`, `/submit`, `/feed` pages). If that frontend's own JS
> (`apiFetch()` in `worker/index.js`'s embedded HTML) doesn't attach
> `Authorization`/`CF-Access-*` headers, public browsing of the review queue
> is now broken, not just curl examples — this wasn't verified in this pass
> and is worth checking before relying on the "opt-in distribution" flow
> described below working for anonymous visitors.

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
