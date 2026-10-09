---
name: atlas
description: Look up any Phoenix file, folder, or feature - where it is (sector + path) and what it really connects to - from the Atlas tree built from the CODE on disk (8 sectors, edges from imports/calls/paths). Use BEFORE grepping or reading files whenever asked "where is X", "what touches X", "what's near X", "what's in sector N", or before editing anything (Directive #1 - know what an edit touches). Claude IS the atlas; the Console shows the same tree.
---

# Atlas - one source, two views (Jerry 2026-10-09)

The Atlas is a tree: 8 sectors at the top (S1 ring zero, S2 apps, S3 system+output, S4 storage,
S5 .lol hub, S6 security, S7 AI brain, S8 faces) + Products, Archive, Docs. Name + location only;
expand to go down. Edges come from the CODE (Python imports, JS require/import, any path or unique
file name one file names that is another real file). `.md` never draws a line; Archive is left out.

Rules: `sector2/package-handler/atlas/sectors.json` (the ONE source - most specific key wins).
Builder + queries: `sector2/package-handler/atlas/atlas-tree.js`. Output: `atlas/atlas-tree.json`
(rebuilt at session start by the SessionStart hook; rebuild by hand after moving/adding files).

## Use it first - it keeps context small

Run from the repo root (any shell with node):

    node sector2/package-handler/atlas/atlas-tree.js show                 # the sectors
    node sector2/package-handler/atlas/atlas-tree.js show S3/sector3/mesh # one branch, one level
    node sector2/package-handler/atlas/atlas-tree.js find buddy           # where is it (sector + path)
    node sector2/package-handler/atlas/atlas-tree.js near phoenix_buddy.py # touches / touched by
    node sector2/package-handler/atlas/atlas-tree.js build                # after adding/moving files

Answer from that output: the thing's sector + path, then what it touches and what touches it,
grouped by sector. Only open a file when the answer needs its contents - and before editing,
read the code (Directive #1), not this tree.

## Rules
- UNMAPPED in `build` output = a file no rule covers. Add a rule to sectors.json right then
  (Atlas gap = stop and add it); never leave it.
- A bare name links only when exactly one live file has it; duplicates stay unlinked (say so).
- Sector tags are labels, not move orders. Moves go by the move method, one at a time.
- The worker's `/connections` graph (built from CONNECTIONS.md prose) is a fallback for notes
  only - it drifted before (audit A-01..A-03). Never trust its edges over the tree's.
