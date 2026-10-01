---
name: atlas
description: Look up any Phoenix component, file, or feature and answer in plain English with what it is plus the things it really connects to — a bounded "snow globe" view sourced from the real CONNECTIONS.md-derived relationship graph, never random filler. Use whenever asked "what's near X", "what touches X", "what else is in this area", or when a lookup should surface adjacent features someone didn't know existed. This is the same role Claude already plays as "the glossary" in the HUD chat — no separate UI panel, Claude IS the atlas.
---

# Atlas — Phoenix's connections library

Phoenix's whole system is documented across 13 `CONNECTIONS.md` files (root index +
one per sector/dir). Those files got parsed into a live D1 table (`connections`,
`phoenix_dev_db`, served by `packages-worker`) — one row per component/feature bullet,
with a real description, plus a `links` edge list built from each doc's own
"Connects to / connected from" section. This skill is how you act as the query
interface over that table, in chat — the same pattern as answering glossary
questions: no coded UI panel exists or is needed.

## When to use this

- "What's related to `<thing>`?" / "what else is near the clone pool?" / "what
  don't I know about in Office?"
- Anyone exploring a part of the system who'd benefit from seeing adjacent
  features, not just the literal thing they asked about.
- Before making a change somewhere — surfacing what else lives in that area
  catches "didn't know that was here" surprises before they become regressions.

## How to answer

1. Resolve the query against the live worker:
   ```
   GET {PHOENIX_WORKER_URL}/connections/<query>/related
   Authorization: Bearer {PHOENIX_AUTH}
   CF-Access-Client-Id: {CF_ACCESS_CLIENT_ID}
   CF-Access-Client-Secret: {CF_ACCESS_CLIENT_SECRET}
   ```
   The lookup is fuzzy (exact hex/name/path match first, then a LIKE fallback
   picking the shortest/most-specific match) — you don't need the query to be
   an exact stored path.
   If it 404s or the `center` is clearly not what was asked (e.g. "radar" lands
   on an unrelated folder), run `GET /connections?q=<query>` and use the best hit
   as the center instead.
2. The response is the "snow globe": `center` (the direct hit) plus up to 8
   `related`, each tagged `via`: `edge` = a real documented connection, `area`
   = lives in the same folder, `backfill` = random filler to reach 8.
3. **Answer in plain English for a person, not a data dump** (Jerry, 2026-09-30:
   "it needs a human readable resolution"):
   - Start with the thing itself: its plain name and one sentence on what it does,
     in everyday words (rewrite the stored `description`, don't paste it).
   - **Works with:** every `edge` neighbor — plain name + what the connection *is*
     ("Office's save goes through it"), one line each.
   - **Also in the same place:** `area` neighbors, only if they help; at most 3.
   - **Never show `backfill`.** If there are few real connections, say so in one
     line ("Nothing else is directly connected.") instead of padding.
   - No hex ids, no `source_file`/`state`/`updated_at`, no raw JSON. A file path
     only in backticks after a plain name, and only when someone would need it
     to find the thing.
   - If the entry has a `key_fact` that matters (legacy, not live, test mode),
     say it in plain words.
   Example:
   > **Dashboard** — the old Phoenix Command Center app (kept running, not
   > developed; the Console is the front door now).
   > **Works with:** • **Intake** — Office "save" goes through it
   > • **usys** (`scripts/usys.ps1`) — what its RUN and CODES boxes run
   > • **packages-worker** — where it reads the glossary from
   > Nothing else is directly connected.
4. If `GET /connections?q=<term>` (no `/related`) is more appropriate — the
   user wants a broader search, not one center + neighbors — use that instead
   and summarize the matches the same plain way.

## Keeping it current

The table is a snapshot from `sector2/package-handler/parse-connections.js`,
run against whatever `CONNECTIONS.md` files exist at parse time. It does not
auto-update when those docs change. Re-run it (`node parse-connections.js`
from `sector2/package-handler/`) after any `CONNECTIONS.md` edit, or when a
lookup surfaces something obviously stale.

## Known limits (v1, honest about scope)

- The graph is only as rich as `CONNECTIONS.md` prose — some nodes have 0
  explicit edges yet, and the "snow globe" backfills those with same-area
  entries, then (if still short) truly unrelated entries just to reach 8
  (`via: backfill`). Never show those (see step 3).
- Nodes are directories/subsystems, not individual files — this is not a
  replacement for the file-level `glossary` table. Use `glossary` for "what
  is this specific file," `connections` for "what's near this area."
- See `docs/ATLAS.md` for the full API reference.
