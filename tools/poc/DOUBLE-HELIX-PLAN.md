# Helix Double Strand PoC — Plan
# Phoenix DevOps OS | jwl247 | GPL v3
# READ THIS BEFORE TOUCHING ANY FILE IN THIS PLAN
# =============================================================================

## Top-Level Overview

**Goal:** Boot the full Helix Lightning Kernel as the Double Helix PoC, wired to
`helix_complete_stack.py` as the memory backend, with the Linux paging brain watching
both strands via the shared filesystem.

**What already exists and works:**
- `sector1/helix-lightning/` — full kernel: Frank5, Helix-I/E, FrankRing, FrankSpawn,
  ProcessLibrary. Has compiled `__pycache__` (cpython-314) — it has been run on this machine.
- `sector1/helix/helix_complete_stack.py` — HelixSystem L1-L5 with `get_tier_snapshot()`
- `sector1/helix-lightning/helix_suit_override.py` — already points `helix_complete_stack.py`
  as the suit for all core kernel rings. The two systems were always meant to connect.
- `sector4/paging_windows.py` — already has `attach_helix()` wired
- `tools/poc/true_double_helix.py` — is `helixi.py` (Helix-I) with the import from
  `franken5`. Needs path fix only — the logic is correct.

**Architecture:**
```
Double Helix = 8 channels total
  Strand A = channels 1-4 (Helix-I ingress)  — Windows executing
  Strand B = channels 5-8 (Helix-E egress)   — Debian prefetching / flushing

Frank5 conductor — wears every process as a suit, rides clean, dies clean
helix_complete_stack.py — the suit for all rings (L1/L2/L3/L5 cache backend)
paging.py (Linux) — one brain watching both strands via windows_snapshot.json
Shared page dir = F:\Phoenix\helix-pages\ (SMB proven live 2026-08-23)
```

**What needs to be done:**
1. Fix `true_double_helix.py` — add sys.path insert for `sector1/helix-lightning/`
2. Fix `helix_suit_override.py` — ensure `PHOENIX_SUITS` path resolves correctly from poc/
3. Wire `paging.py` — `attach_helix()` + `attach_snapshot_path()` + snapshot reader
4. Add snapshot writer to `true_double_helix.py`
5. Write launcher scripts — set env, boot kernel, start paging brain
6. Register suite + update session docs

**What does NOT change:**
- `sector1/helix-lightning/` files — no edits to the kernel itself
- `sector1/helix/helix_complete_stack.py` — complete, no edits needed
- `sector4/paging_windows.py` — already wired, no edits needed

---

## Sub-Tasks

---

### Sub-Task 1 — Fix `true_double_helix.py` path resolution

**Status:** [ ] pending

**Intent:**
`true_double_helix.py` is a copy of `helixi.py` (Helix-I ingress). It fails to import
because `franken5` is not on the Python path. The fix is a single `sys.path.insert` at
the top pointing at `sector1/helix-lightning/`. No logic changes needed — the code is
correct as written.

**Expected Outcomes:**
- `py -3 tools/poc/true_double_helix.py` runs without ImportError
- Helix-I boots: Frank5 initialises, SharedMemoryBus mounts, channels 1-4 listen on
  ports 7701-7704
- Status loop prints channel stats every second

**Todo List:**
1. Add at top of file (after `#!/usr/bin/env python3` docstring, before other imports):
   ```python
   import sys
   from pathlib import Path
   _LIGHTNING = Path(__file__).parent.parent.parent / "sector1" / "helix-lightning"
   if str(_LIGHTNING) not in sys.path:
       sys.path.insert(0, str(_LIGHTNING))
   ```
2. Verify all existing imports resolve: `Frank5`, `get_frank`, `SharedMemoryBus`,
   `FrankSignal`, `SHM_PATH`, `STAGE_SLOT_SIZE`, `FRANK_VERSION`
3. No other changes to the file

**Relevant Context:**
- `tools/poc/true_double_helix.py` — file to fix, lines 1-41 (path + imports)
- `sector1/helix-lightning/franken5.py` — provides all imported names
- `sector1/helix-lightning/__pycache__/` — cpython-314 pyc files confirm prior successful run
- Path from `tools/poc/` to `sector1/helix-lightning/`: `../../sector1/helix-lightning`

---

### Sub-Task 2 — Fix `helix_suit_override.py` path resolution

**Status:** [ ] pending

**Intent:**
`helix_suit_override.py` uses `PHOENIX_SUITS` env var to find the repo root, then builds
paths to `sector1/helix/helix_complete_stack.py`. When run from `tools/poc/` as the PoC
launch point, this env var is not set. The fix adds a fallback that walks up from `__file__`
to find the repo root — same pattern used throughout Phoenix.

**Expected Outcomes:**
- When `PHOENIX_SUITS` is not set, `helix_suit_override.py` correctly resolves the repo
  root as the parent of `sector1/`
- `helix_complete_stack.py` is found and registered as the suit for all 13 core rings
- "Suit {name} → {path}" log lines confirm all suits wired, no "not found — skipping" warnings

**Todo List:**
1. In `helix_suit_override.py`, replace the `repo` line:
   ```python
   # current:
   repo = Path(os.environ.get("PHOENIX_SUITS", Path(__file__).parents[1]))
   # fix: __file__ is in sector1/helix-lightning/, so parents[2] is the repo root
   repo = Path(os.environ.get("PHOENIX_SUITS", Path(__file__).parents[2]))
   ```
2. Confirm `str(s1 / "helix" / "helix_complete_stack.py")` resolves to a file that exists
3. No other changes

**Relevant Context:**
- `sector1/helix-lightning/helix_suit_override.py` — file to fix, line 15
- `Path(__file__).parents[0]` = `sector1/helix-lightning/`
- `Path(__file__).parents[1]` = `sector1/` (current — wrong, points at sector1 not repo root)
- `Path(__file__).parents[2]` = repo root `Phoenix-DevOps-oS/` (correct)
- `sector1/helix/helix_complete_stack.py` must exist relative to repo root — it does

---

### Sub-Task 3 — Wire `attach_helix()` into `paging.py` (Linux)

**Status:** [ ] pending

**Intent:**
`paging.py`'s `_get_vrram_snapshot()` currently estimates tier state from `/proc/meminfo`
using hardcoded 40/30/20 ratios. Give it the same real-data path that `paging_windows.py`
already has — either a locally attached `HelixSystem` OR the `windows_snapshot.json` from
the shared SMB mount. This is the "one paging brain" piece: Linux sees both strands.

**Expected Outcomes:**
- `AIPagingManager.attach_helix(helix)` — sets live HelixSystem reference
- `AIPagingManager.attach_snapshot_path(path)` — sets path to shared snapshot JSON
- `_get_vrram_snapshot()` priority order:
  1. Local HelixSystem attached → read directly
  2. Snapshot path set + file exists + age < 30s → read JSON, return TierSnapshot
  3. Fallback → existing `/proc/meminfo` ratio logic (unchanged)
- `monitor_and_adapt()` gains `helix_paging` signal: `frozen_mb > 0` → expand swap proactively
- Shrink gated on `not helix_paging`
- Log line prints tier data every cycle when Helix source is active
- `get_status_dict()` includes snapshot source in output

**Todo List:**
1. Add to `AIPagingManager.__init__()`:
   ```python
   self._helix = None
   self._snapshot_path = None
   ```
2. Add `attach_helix(self, helix)` method — sets `self._helix`, logs source
3. Add `attach_snapshot_path(self, path: str)` method — sets `self._snapshot_path`, logs path
4. Add `_read_snapshot_json(self, path: str) -> Optional[TierSnapshot]` helper:
   - Read JSON, check `timestamp` field age < 30s, construct `TierSnapshot(**data)`
   - Return `None` on any error (missing file, stale, malformed, missing fields)
5. Rewrite `_get_vrram_snapshot()` with 3-tier priority (attach_helix → snapshot_json → fallback)
6. Add `helix_paging` signal into `monitor_and_adapt()` — identical pattern to `paging_windows.py`
7. Gate shrink on `not helix_paging`
8. Add `helix_source` field to `get_status_dict()` return

**Relevant Context:**
- `sector4/paging_windows.py` lines 455-498 — `attach_helix()`, `_get_vrram_snapshot()` —
  exact pattern to follow
- `sector4/paging_windows.py` lines 547-597 — `monitor_and_adapt()` with `helix_paging` signal
- `sector4/paging.py` line 849 — current `_get_vrram_snapshot()` to replace
- `sector4/paging.py` line 914 — `monitor_and_adapt()` to extend
- `sector4/paging.py` line 124 — `TierSnapshot` dataclass fields are the contract
- Snapshot JSON path on Debian: `/phoenix/helix-pages/windows_snapshot.json`
- Age check: reject snapshots older than 30s (writer runs every 5s; 30s = 6 missed cycles)

---

### Sub-Task 4 — Snapshot writer in `true_double_helix.py`

**Status:** [ ] pending

**Intent:**
After the path fix (Sub-Task 1), add the snapshot writer loop to `true_double_helix.py`.
This is the Windows side of the cross-platform paging feed: every 5 seconds, read tier
state from the active HelixSystem suits and write `windows_snapshot.json` to the shared
page dir. The Linux paging brain reads this file.

**Expected Outcomes:**
- Background thread starts automatically when `HelixI` boots with `page_dir` set
- `windows_snapshot.json` written to `page_dir` every 5 seconds
- JSON contains all `TierSnapshot` fields: `timestamp, hot_mb, warm_mb, cold_mb,
  frozen_mb, hit_rate, promotions, demotions, evictions, pages_on_disk`
- Graceful: if no HelixSystem is attached (suits not yet initialised), writes zeros
- Snapshot writer stops cleanly when `HelixI.stop()` is called

**Todo List:**
1. Add `page_dir` parameter to `HelixI.__init__()` — reads `PHOENIX_HELIX_PAGE_DIR` env var
   if not passed directly
2. Add `_snapshot_writer_loop()` method — aggregates tier data, writes JSON atomically
   (write to `.tmp` then rename) every 5 seconds
3. Start writer thread in `__init__` when `page_dir` is set
4. Add `attach_helix_system(self, helix: object)` — stores reference used by writer loop
5. Stop writer thread in `stop()`
6. Plain text log output only — no emoji

**Relevant Context:**
- `sector1/helix/helix_complete_stack.py` `HelixSystem.get_tier_snapshot()` — the data source
- `sector4/paging_windows.py` `_get_vrram_snapshot()` — the JSON schema consumer
- Atomic write: `path.with_suffix('.tmp')` → write → `os.replace(tmp, final)`
- `PHOENIX_HELIX_PAGE_DIR` env var — already used by `helix_complete_stack.py`
- Windows path: `F:\Phoenix\helix-pages\windows_snapshot.json`
- Debian path (reader): `/phoenix/helix-pages/windows_snapshot.json`

---

### Sub-Task 5 — Launcher scripts

**Status:** [ ] pending

**Intent:**
Two launcher scripts — one per OS — that set env vars and start the correct piece.
Mirror the `run-debian.ps1` / `demo-collab.sh` pattern already in `tools/poc/`.

**Expected Outcomes:**
- `tools/poc/run-helix-poc.ps1`:
  - Sets `PHOENIX_SUITS` to the repo root (`Phoenix-DevOps-oS/`)
  - Sets `PHOENIX_HELIX_PAGE_DIR` to `F:\Phoenix\helix-pages\`
  - Creates `F:\Phoenix\helix-pages\` if missing
  - Adds `sector1/helix-lightning/` to `PYTHONPATH`
  - Runs `py -3 tools/poc/true_double_helix.py`
  - Prints instructions for starting the Debian side
- `tools/poc/run-helix-poc.sh`:
  - Sets `PHOENIX_HELIX_PAGE_DIR=/phoenix/helix-pages/`
  - Verifies SMB mount live (`/phoenix/` exists and is non-empty)
  - Runs `python3 sector4/paging.py start` with snapshot path set
  - Exits with usage message if mount not available

**Todo List:**
1. Write `run-helix-poc.ps1` — env setup, dir create, `py -3 true_double_helix.py`
2. Write `run-helix-poc.sh` — mount check, env setup, `python3 paging.py start`
3. Plain text output. No emoji. Consistent with Phoenix log style.

**Relevant Context:**
- `tools/poc/run-debian.ps1` — PS7 launcher pattern to follow
- `tools/poc/demo-collab.sh` — Debian-side script pattern
- `py -3` confirmed working Python 3 invocation on this machine
- SMB mount: Windows `F:\Phoenix\` ↔ Debian `/phoenix/` — proven live 2026-08-23

---

### Sub-Task 6 — Register suite + update session docs

**Status:** [ ] pending

**Intent:**
Register the PoC as a runnable suite. Update `SESSION_STATE.md` and `BOB.md`.

**Expected Outcomes:**
- `tools/poc/helix-poc.suite.json` — registers `true_double_helix.py` as runnable via
  `usys run helix-poc`
- `SESSION_STATE.md` updated: Helix Lightning Kernel + Double Strand PoC listed
- `BOB.md` replaced: session record for this session

**Todo List:**
1. Write `helix-poc.suite.json` — match schema of `debian.suite.json`
2. Update `SESSION_STATE.md` — add to WHAT WAS BUILT, update NEXT STEPS
3. Write `BOB.md` — replace current session record with this session

**Relevant Context:**
- `tools/poc/debian.suite.json` — suite schema reference
- `SESSION_STATE.md` — current state (last updated 2026-08-23)
- `BOB.md` — session record (last session: helix_complete_stack + paging_windows wiring)

---

## Implementation Order

Sub-tasks 1 and 2 are independent — do either first.
Sub-task 3 is independent of 1 and 2.
Sub-task 4 depends on Sub-task 1 being complete.
Sub-task 5 depends on Sub-tasks 1, 2, 3, 4 being complete.
Sub-task 6 is always last.

## Key Facts for Implementation

- `py -3` is the confirmed Python 3 invocation on this machine
- All kernel files are in `sector1/helix-lightning/` — do NOT edit them
- `helix_complete_stack.py` is in `sector1/helix/` — do NOT edit it
- The kernel has been run before (`__pycache__` cpython-314 present)
- `PHOENIX_SUITS` → repo root (`Phoenix-DevOps-oS/`)
- `PHOENIX_HELIX_PAGE_DIR` → `F:\Phoenix\helix-pages\` (Windows) / `/phoenix/helix-pages/` (Debian)
- Snapshot JSON keys must match `TierSnapshot` fields exactly:
  `timestamp, hot_mb, warm_mb, cold_mb, frozen_mb, hit_rate, promotions, demotions, evictions`
- Atomic JSON write: write to `.tmp` then `os.replace()` — prevents Linux reading half-written file
- `true_double_helix.py` path from repo root: `tools/poc/true_double_helix.py`
- Path from `tools/poc/` to `sector1/helix-lightning/`: `../../sector1/helix-lightning/`
