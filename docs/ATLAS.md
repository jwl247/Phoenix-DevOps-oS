# Phoenix Atlas — How To

The Atlas is Phoenix's connections library — every component/feature documented
across the 13 `CONNECTIONS.md` files (root index + one per sector/dir), turned
into a queryable graph. Ask about anything, get the direct answer plus exactly
8 related things nearby — a bounded "snow globe" view of that one area, not the
whole repo dumped on you at once. Same role as the Glossary: Claude itself is
the interface (see `.claude/skills/atlas/SKILL.md`) — no coded UI panel.

## Status

- **Backend: live.** The `connections` table on D1 (`phoenix_dev_db`, via
  `packages-worker`) — 37 entries as of the first parse (2026-09-24), one per
  component/feature bullet across the 13 `CONNECTIONS.md` files, each carrying
  its own `description` and a `links` edge list.
- **Population: manual re-run, not intake-driven.** Unlike the Glossary
  (populated automatically on every `intake.sh` run), the Atlas is backfilled
  by running `sector2/package-handler/parse-connections.js` directly. It does
  **not** watch `CONNECTIONS.md` for changes — re-run it after editing any of
  them.
- **No dashboard/HUD panel** — and none planned. This mirrors the 2026-09-20
  decision that GLOSSARY/CODES/GUIDE become chat-driven Claude Skills instead
  of coded panes: Claude answers Atlas questions directly in the HUD chat.

## Populating / refreshing

```bash
cd sector2/package-handler
node parse-connections.js            # parses + POSTs to the live worker
node parse-connections.js --dry-run  # parse only, writes connections-seed.json, no network
```

Requires `PHOENIX_WORKER_URL` / `PHOENIX_AUTH` env vars (same as everything
else that talks to the worker), plus `CF_ACCESS_CLIENT_ID` / `CF_ACCESS_CLIENT_SECRET`
now that Cloudflare Access sits in front of every worker route (Security Gap 1,
2026-09-21) — without those two, POSTs get silently redirected to the Access
login page. The script detects that specific failure mode (a real D1 write
never redirects) and reports it as a failure rather than a false "ok".

## Querying

```bash
# Search by name/path/description substring, optionally scoped to an area
curl "$PHOENIX_WORKER_URL/connections?q=intake" \
  -H "Authorization: Bearer $PHOENIX_AUTH" \
  -H "CF-Access-Client-Id: $CF_ACCESS_CLIENT_ID" -H "CF-Access-Client-Secret: $CF_ACCESS_CLIENT_SECRET"

# Fetch one entry by hex, name, or path (fuzzy — falls back to a LIKE match
# on the shortest/most-specific hit if there's no exact match)
curl "$PHOENIX_WORKER_URL/connections/package-handler" -H "Authorization: Bearer $PHOENIX_AUTH" ...

# The "snow globe": the entry plus exactly 8 related entries
curl "$PHOENIX_WORKER_URL/connections/package-handler/related" -H "Authorization: Bearer $PHOENIX_AUTH" ...
```

## Fields

| Field | Type | Meaning |
|---|---|---|
| `hex` | string | Deterministic id — first 16 hex chars of SHA-256 of the node's repo-relative path (not the TAV b58 scheme; these aren't intaked physical objects, so no QR/tier semantics apply) |
| `name` | string | As written in the source `CONNECTIONS.md` bullet/table row |
| `path` | string | Repo-relative path this node documents |
| `area` | string | Top-level directory (sector1, dashboard, docs, etc.) |
| `description` | string | The "what it is" text for this node |
| `key_fact` | string\|null | The root index's "Key fact" column, where applicable |
| `source_file` | string | Which `CONNECTIONS.md` this node was parsed from |
| `state` | string | `white` (active) or `grey` — auto-flagged if the source prose contains words like "stale"/"dead"/"deprecated"/"orphaned" |
| `links` | JSON string | Array of other nodes' `hex` ids this one connects to |
| `file_state`, `file_pool_path` | — | Present on `GET /connections` only — `LEFT JOIN glossary` enrichment when this node is also a real intaked file |

## The "snow globe" algorithm (`GET /connections/:id/related`)

Always returns exactly 8 related entries (fewer only if the whole graph has
fewer than 8 other nodes total), picked in this priority order:

1. Explicit edges in `links`, both directions (this node's own edges, plus any
   other node that lists this one).
2. Same-`area` entries not already picked.
3. Backfill from anywhere else in the table, only if still short — the graph
   is sparse in a first pass, so a lightly-connected node may pad out with a
   genuinely unrelated entry. Don't present a backfill pick as a real
   relationship; it's there to guarantee the count, not the relevance.

## Known limits

- Nodes are directories/subsystems parsed from prose, not individual files —
  use `glossary` (see `docs/GLOSSARY.md`) for file-level lookups, `connections`
  for area-level discovery.
- The parser's path-resolution is heuristic (hand-written prose doesn't always
  match a node's canonical path byte-for-byte) — a `LIKE`-based suffix match
  handles most of it, but isn't perfect. Verify anything load-bearing.
- 37 nodes from a first pass is a thin graph — several nodes still have 0
  explicit edges and lean entirely on the same-area/backfill tiers. Expect
  this to get richer as `CONNECTIONS.md` files are extended and re-parsed.

## See also

- `.claude/skills/atlas/SKILL.md` — how Claude answers Atlas questions in chat
- `sector2/package-handler/parse-connections.js` — the parser/backfill script
- `CONNECTIONS.md` (repo root) — the human-readable index this is built from
- `docs/GLOSSARY.md` — the file-level equivalent this is modeled on
