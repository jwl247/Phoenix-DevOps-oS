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

- Self-registers on first run (as `intake.sh`, hex `696e74616b652e7368`, in `T1/`)
- Accepts any file type (scripts, configs, binaries, yaml, json, service units)
- Auto-detects companion files (.service, .conf, .env, .yaml travel with parent)
- Generates hex identity from filename
- Writes sidecar.json with full metadata
- Versions files in the local pool (`T1/<hex>/v1_<name>`, `v2_…`; keeps 7)
- Writes local custody log (sqlite3 CLI, optional)
- Reports to D1 via packages-worker (clonepool + custody + glossary, and a
  `versions` row whenever the content hash changes)
- Uploads bytes to R2 twice: the overwritten "current" key `<hex>` and the
  immutable per-version key `<hex>/versions/<sha3[0:16]>` (the second since
  2026-09-29; versions logged before that have no bytes in R2)
- `INTAKE_YES=1` for unattended runs (no prompts; a closed stdin picks the safe
  answer: skip a sensitive file, keep an identical existing version)

### `worker/index.js`

Cloudflare Worker — **packages-worker**. The catalog API. Serves and receives data from `phoenix_dev_db` (D1).

**Endpoints** (regenerated 2026-09-29 from the route table in `worker/index.js`, v3.5.0):

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health`, `/` | — | Health: worker version + D1 table count. No app-layer auth (Access still fronts it). |
| GET | `/platform` (or `/` with `Accept: text/html`) | — | The only HTML page: tabs Glossary / Review Queue / Submit / Opt-In Feed / Verify. The page itself has no app-layer auth; its API calls send the token typed into its "Auth Token" box. |
| GET | `/whoami` | ✓ | Auth round-trip check (used by `intake.sh` preflight/status and `rotate-phoenix-auth.sh`). |
| GET | `/stats` | ✓ | Counts for the dashboard: `glossary_total`, `custody_total`, `clonepool_total`, `versions_total`, `r2_objects` (+ `r2_objects_capped`). |
| GET | `/clonepool` | ✓ | List pool rows. `?state=`, `?sensitive=1`, `?limit=` (default 100). |
| POST | `/clonepool` | ✓ | Upsert a pool row (intake.sh). Logs a `versions` row when `hash_sha3` changed; returns `version_logged`. |
| PUT | `/clonepool/:hex` | ✓ | Upload the CURRENT bytes for a hex (overwritten on every re-intake). |
| GET | `/clonepool/:id` | ✓ | Bytes from R2 by default; `?meta=true` (or no R2 object) returns the D1 row (hash baseline, `qr_valid`, …). `:id` = hex_id or name. |
| DELETE | `/clonepool/:id` | ✓ | Delete one row and its hex-keyed R2 object. A name shared by several rows → 409 with the hex list. |
| PUT, GET | `/clonepool/:hex/versions/:hash16` | ✓ | Immutable per-version bytes, keyed by the first 16 hex chars of the content's SHA3-512 (the `versions.store_path`). |
| POST | `/clonepool/:hex/validate` | ✓ | Report a client-side hash check (`hash_sha3` + `hash_blake2`); flips `qr_valid`/`verified_at`. |
| PATCH | `/clonepool/:hex/tier` | ✓ | Tier move / eviction (`tier`, optional `pool_path`, `state`) — used by `intake prune`. |
| GET | `/custody` | ✓ | Custody ledger. `?hex=`, `?limit=` (default 50). |
| POST | `/custody` | ✓ | Append a custody receipt (append-only). |
| GET | `/glossary` | ✓ | Browse the glossary. `?q=`, `?category=`. |
| POST | `/glossary` | ✓ | Add or upsert an entry. |
| GET | `/glossary/:id` | ✓ | One entry by hex or name. |
| GET | `/glossary/:id/code` | ✓ | The entry's current bytes from R2 (text/plain), 404 if never uploaded. |
| PUT | `/glossary/:id` | ✓ | Update description, category, state or notes. |
| DELETE | `/glossary/:id` | ✓ | Remove an entry. |
| GET | `/categories` | ✓ | Glossary categories. |
| GET | `/packages`, `/packages/:id` | ✓ | Package rows (mostly stubs created by the versions logger). |
| GET | `/toc` | ✓ | TOC tree + pool summary by state. |
| GET | `/versions` | ✓ | Version history. `?package=`, `?limit=` (default 50). Used by `intake clone <name> vN`. |
| GET | `/deps` | ✓ | Dependency edges. `?package=`, `&reverse=true` for what depends on it. |
| POST | `/deps` | ✓ | Record an edge (intake.sh `intake backend` via `translator.sh deps`). |
| GET | `/search` | ✓ | Cross-search clonepool + glossary + packages. `?q=` required. |
| GET | `/connections` | ✓ | The Atlas (see `docs/ATLAS.md`). `?q=`, `?area=`. Rows carry `file_state`/`file_pool_path` when the node's name was intaked. |
| POST | `/connections` | ✓ | Upsert an Atlas node (`parse-connections.js`). |
| POST | `/connections/reconcile` | ✓ | `{keep:[hex…]}` — delete nodes no longer in any CONNECTIONS.md (`parse-connections.js`, after a clean upload). |
| GET | `/connections/:id` | ✓ | One node: exact hex/name/path, then name/path LIKE, then description LIKE. |
| GET | `/connections/:id/related` | ✓ | The "snow globe": up to 8 neighbours, each tagged with `via` = `edge`, `area` or `backfill`. |
| GET, POST | `/review`, `/review/:hex`, `/review/:hex/vote`, `/review/:hex/votes`, `/review/:hex/revoke`, `/verify/:hex`, `/feed` | ✓ | Peer review — see below. |

There is no `/installed/register` route (the installers no longer call it).

`clonepool.sensitive` (boolean) is separate from `state` — `state` is lifecycle
status (active/deprecated/retired), `sensitive` flags content intake.sh's
filename heuristic caught (`*auth*`, `*secret*`, `*password*`, `*credential*`,
`*token*`, `.env`) as needing restricted handling downstream, independent of
whether it's active. Set automatically by intake.sh when a matching file is
intaked and the operator confirms (or `INTAKE_YES=1`); not inferred by the worker.

**Auth — two layers, both required (verified against `index.js` and Cloudflare
Access config, 2026-09-24):**
1. **App layer:** every route above except `/health`, `/` and `/platform` requires
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

Cloudflare Wrangler configuration. Binds the worker to the `phoenix_dev_db` D1 database (`PHOENIX_DB`) and the `phoenix-clonepool` R2 bucket (`CLONEPOOL_BUCKET`).

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
4. Write `~/.phoenix_env` with `PHOENIX_HOME`/`PHOENIX_INSTALL_DIR`/`CLONEPOOL_DIR`/`PHOENIX_LOG` and hook it into your shell profile (an existing `CLONEPOOL_DIR` is kept)
5. Install a shim at `/usr/local/bin/phoenix-handler` (falls back to `~/Phoenix/bin/phoenix-handler` if `/usr/local/bin` isn't writable) — **the command is `phoenix-handler`, not `intake`** on this path

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

# Check the auth round trip + local cache
bash intake.sh status

# Intake a file:  intake.sh <file> [backend] [notes]
bash intake.sh ./myfile.sh
bash intake.sh ./nginx.conf direct "production config"

# Register a backend-installed package
bash intake.sh backend nodejs winget 20.11.0
bash intake.sh backend python apt 3.13.0

# Pull a file back out (latest, or a specific version)
bash intake.sh clone nginx.conf
bash intake.sh clone nginx.conf v2
```

---

## Command Reference

> `intake` below is a stand-in for whatever you actually set up — `bash intake.sh`,
> `usys clone` (monorepo), or `phoenix-handler` (standalone installer). See
> Installation above for which one applies to you.

### `intake <file> [backend] [notes]`

Intakes a file into the clonepool. Generates a hex identity, writes a sidecar, versions the file, logs custody, reports to D1 and uploads the bytes to R2. The category is derived from the file extension (there is no category argument). A directory argument runs directory intake (preview + one snapshot version).

```bash
intake ./myapp.sh
intake ./nginx.conf direct "production nginx"
INTAKE_YES=1 intake ./deploy.py manual "deploy v3"   # unattended
```

**Arguments:**
- `<file>` — path to the file (or directory) to intake (required)
- `[backend]` — how it arrived (default `direct`); stored on the sidecar/custody row
- `[notes]` — optional free-text note

---

### `intake backend <name> <manager> <version> [install_path]`

Registers a backend-installed package (one not physically intaked as a file — e.g. system packages, language runtimes). With `install_path` pointing at a file, that file is intaked too. Dependency edges come from `translator.sh deps` when it knows the backend.

```bash
intake backend nodejs winget 20.11.0
intake backend python apt 3.13.0
intake backend nginx brew 1.25.0
```

**Arguments:**
- `<name>` — package name
- `<manager>` — package manager used (winget, apt, brew, dnf, pip, npm, etc.)
- `<version>` — installed version string
- `[install_path]` — optional installed file to intake as well

---

### `intake status`

Prints the worker URL and an auth check (`GET /whoami`: `OK`, `MISMATCH`, or `not set`), the pool path, the Python found, and counts of the **local cache** (sidecars on this machine, by state). The pool of record is D1/R2 — local counts are normally much smaller (use `GET /toc` or `GET /stats` for the full numbers).

```bash
intake status
```

---

### `intake clone <name>` / `intake clone <dir>`

Pulls a file (or, for directory snapshots, a whole restored directory) back out of the clonepool into the current working directory — the reverse of `intake <file>`. Directory detection is automatic: if the hex has a directory-type sidecar, `intake clone` restores the snapshot; otherwise it clones the latest single-file version.

Before copying anything, it hashes the local clonepool copy (SHA3-512) and compares it against the baseline recorded in D1 at intake time. A mismatch refuses the clone outright rather than handing back a corrupted or altered file — this is what gates hot-swap and clone-to-workdir. Files intaked before this check existed have no baseline yet and clone through with a warning instead of a hard block.

Older versions are verified too: a non-current version passes only if its SHA3-512 is a recorded `versions` row for the same hex (`GET /versions?package=`). On a machine with no local copy, `intake clone` falls back to R2 — the current key for the latest version, and `/clonepool/<hex>/versions/<hash16>` for an older one (looked up by its D1 version label), hash-checked before it lands.

```bash
intake clone nginx.conf
intake clone nginx.conf v2       # a specific file version
intake clone myproject           # restores the latest directory snapshot
intake clone myproject v2        # restores a specific snapshot
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
"intake.sh" → 696e74616b652e7368      (raw hex of the file name: to_hex in intake.sh)
```

This hex is:
- The clonepool directory name
- The sidecar filename
- The D1 primary key
- Permanent and reproducible

Known limitation: two different files with the same name share one hex (one
bucket, one D1 row, one R2 key) — see audit S2CORE-F25.

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
- **Older version** (not the current row) → valid only if its hash is a recorded `versions` row for this hex; `qr_valid` is left alone (it describes the current version).
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

Companions are copied into the same bucket with the parent's version prefix (`v3_nginx.service` next to `v3_nginx.sh`) and listed in the parent's sidecar. They are not synced anywhere on their own.

---

## Platform Support

| Platform | Shell | Status |
|----------|-------|--------|
| Linux | bash | ✅ Native |
| macOS | bash | Supported, not tested on a Mac (tier rotation falls back to BSD `date -j` since 2026-09-29) |
| Windows | Git Bash | ✅ Supported (the primary dev box) |

Requires `openssl` (SHA3-512/BLAKE2b) and `xxd`; `sqlite3` and `jq` are optional.

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

> **Verified 2026-09-28:** every review / verify / feed route answers 401 without
> the bearer (and Cloudflare Access fronts the worker), so the "opt-in
> distribution for anonymous visitors" flow is not available as deployed. The
> `/platform` page's calls send whatever token is typed into its "Auth Token"
> box. Live usage so far: 0 submissions, 0 feed rows.

### Website Pages

There is one HTML page, `/platform`, with tabs **Glossary**, **Review Queue**,
**Submit**, **Opt-In Feed** and **Verify**. `/review`, `/feed` and
`/verify/:hex` are JSON API routes, not pages; there is no `/submit` or
`/revoked` route (revocations show up in `/verify/:hex` and on the Verify tab).

### Full Specification

See [PEER_REVIEW.md](./PEER_REVIEW.md) for the complete platform specification including:
- All 9 lifecycle stages
- D1 schema additions (submissions, reviews, revocations, advertisement_feed)
- QR state system (white / grey / black)
- Economic model and non-goals
- Where community contributions are welcome
