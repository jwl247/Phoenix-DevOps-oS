---
name: atlas
description: Look up any Phoenix component, file, or feature and answer with what it is plus exactly 8 related things nearby — a bounded "snow globe" view sourced from the real CONNECTIONS.md-derived relationship graph, not a random or popularity-based pick. Use whenever asked "what's near X", "what touches X", "what else is in this area", or when a lookup should surface adjacent features someone didn't know existed. This is the same role Claude already plays as "the glossary" in the HUD chat — no separate UI panel, Claude IS the atlas.
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
2. The response is the "snow globe": `center` (the direct hit) plus `related`
   — **always exactly 8** neighbors (fewer only if the whole graph is smaller
   than that), each with its own real `description`.
3. Present it as: the direct answer first, then the 8 related items each with
   a one-line description — framed as "you may not know these exist," not as
   a flat list. Bounded to that one area; don't pull in the rest of the repo.
4. If `GET /connections?q=<term>` (no `/related`) is more appropriate — the
   user wants a broader search, not one center + neighbors — use that instead
   and summarize the matches with their descriptions.

## Keeping it current

The table is a snapshot from `sector2/package-handler/parse-connections.js`,
run against whatever `CONNECTIONS.md` files exist at parse time. It does not
auto-update when those docs change. Re-run it (`node parse-connections.js`
from `sector2/package-handler/`) after any `CONNECTIONS.md` edit, or when a
lookup surfaces something obviously stale.

## Known limits (v1, honest about scope)

- The graph is only as rich as `CONNECTIONS.md` prose — some nodes have 0
  explicit edges yet, and the "snow globe" backfills those with same-area
  entries, then (if still short) truly unrelated entries just to reach 8.
  Don't present a random backfill entry as if it were a real relationship.
- Nodes are directories/subsystems, not individual files — this is not a
  replacement for the file-level `glossary` table. Use `glossary` for "what
  is this specific file," `connections` for "what's near this area."
- See `docs/ATLAS.md` for the full API reference.
