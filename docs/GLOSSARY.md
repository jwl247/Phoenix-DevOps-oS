# Phoenix Glossary — How To

The Glossary is Phoenix's unified package dictionary — every file, package,
config, and dependency that flows through intake gets an entry, indexed by
hex identity, searchable by name or category. It's one of the Entourage apps
(see `CLAUDE.md` → APPS) — the TOC/index over the clonepool and D1.

## Status

- **Backend: live.** The `glossary` table on D1 (`phoenix_dev_db`, via
  `packages-worker`) has real data — 995+ entries as of this writing, going
  back to mid-June 2026 intakes.
- **Population: automatic.** `intake.sh` calls `report_glossary()` after every
  file, directory, or package intake. You don't add glossary entries by hand
  — they arrive as a side effect of `usys clone` / `usys intake`.
- **Dashboard panel: built.** The Electron dashboard has a GLOSSARY pane
  (`dashboard/index.html` `#hud-pane-glossary` — search + category/state
  filters + version history). Per `CLAUDE.md` (2026-09-20), the WPF `hud/`
  gets Glossary as a chat-driven Claude Skill rather than a coded pane.
  Everything below is the API level, for scripting or `curl`.

## Prerequisites

- `PHOENIX_WORKER_URL` and `PHOENIX_AUTH` set (see `dashboard/manual/PHOENIX_MANUAL.md`
  §8, or run `usys init`). **Every route — reads included — requires the
  `Authorization: Bearer $PHOENIX_AUTH` header** (Security Gap 1, fixed
  2026-09-21; unauthenticated GETs return `401`). On the
  `packages-worker.phoenix-jwl.workers.dev` hostname, Cloudflare Access also sits
  in front, so add `-H "CF-Access-Client-Id: $CF_ACCESS_CLIENT_ID" -H
  "CF-Access-Client-Secret: $CF_ACCESS_CLIENT_SECRET"` or you get a `302` to the
  Access login page (the `get.authenticcoder.com` custom domain skips Access but
  still enforces the bearer token). The token must match the worker's
  deployed secret — `usys status` shows what's set locally, but that's no
  guarantee it matches the Cloudflare secret. If writes 401, the two are out
  of sync — fix it only with `sector2/package-handler/rotate-phoenix-auth.sh`
  (see `docs/SECRETS.md`); hand-setting one side is what caused the
  2026-08-21 / 08-22 / 09-21 drift incidents.

## Querying

```bash
# All examples need the auth headers from Prerequisites, e.g.:
H=(-H "Authorization: Bearer $PHOENIX_AUTH" -H "CF-Access-Client-Id: $CF_ACCESS_CLIENT_ID" -H "CF-Access-Client-Secret: $CF_ACCESS_CLIENT_SECRET")

# Browse everything (paginated)
curl "${H[@]}" "$PHOENIX_WORKER_URL/glossary?limit=25"

# Search by name substring
curl "${H[@]}" "$PHOENIX_WORKER_URL/glossary?q=phoenix_auth"

# Filter by category
curl "${H[@]}" "$PHOENIX_WORKER_URL/glossary?category=scripts"

# Fetch one entry by hex or name
curl "${H[@]}" "$PHOENIX_WORKER_URL/glossary/phoenix_auth.py"
```

## Writing

Normally you never POST/PUT to `/glossary` directly — `intake.sh` does it for
you. Direct writes are for corrections or manual registration:

```bash
# Add or upsert an entry
curl -X POST "$PHOENIX_WORKER_URL/glossary" \
  "${H[@]}" -H "Content-Type: application/json" \
  -d '{"hex":"...", "name":"nginx.conf", "description":"Production config", "state":"white"}'

# Amend description/category/state/notes on an existing entry
curl -X PUT "$PHOENIX_WORKER_URL/glossary/nginx.conf" \
  "${H[@]}" -H "Content-Type: application/json" \
  -d '{"description":"Updated production config", "state":"grey"}'
```

## Fields

| Field | Type | Meaning |
|---|---|---|
| `hex` / `b58` | string | Deterministic hex identity (filename-derived) and its base58 shorthand — primary key |
| `name` | string | Canonical file/package name |
| `category_hex` | string | Hex of the parent category |
| `description` | string | What this entry is — auto-filled at intake, editable after |
| `state` | string | Lifecycle: `white` (active), `grey` (deprecated), `black` (retired/compromised) — **not** a confidentiality flag |
| `version`, `platform`, `backend`, `size` | — | Standard package metadata |
| `pool_path`, `sidecar` | string | Where the actual file and its sidecar.json live in the clonepool |
| `amended` | boolean | 1 if updated since the original intake |
| `intaked_at` | timestamp | First registration time |

`state` (glossary) and `sensitive` (clonepool table, not glossary) answer
different questions — `state` is "is this still in active use," `sensitive`
is "does this need restricted handling regardless of whether it's active."
Don't conflate them; see `sector2/package-handler/README.md` for the
`clonepool.sensitive` field.

## Known issues

A handful of pre-existing sidecar.json files on disk have malformed JSON
(bad escape sequences) — found while scripting a D1 backfill, not sector1's
files, looked like Frank's. They weren't fixed as part of this pass; if a
script iterating `clonepool/*/*.sidecar.json` needs to be JSON-decode-safe,
wrap each read in a try/except rather than assuming every sidecar parses.

## See also

- `sector2/package-handler/README.md` — full `packages-worker` API reference
  (clonepool, custody, glossary, packages, categories, peer review)
- `CLAUDE.md` — TAV address system, QR state semantics, Entourage apps
