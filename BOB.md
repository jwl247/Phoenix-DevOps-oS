# BOB.md — Session Record
Phoenix DevOps OS · Session 2026-08-24

---

## What was built this session

### 1. `tools/poc/true_double_helix.py` — path fix + snapshot writer

**Problem:** File was a copy of `helixi.py` from the Helix Lightning Kernel with
`from franken5 import ...` failing because `sector1/helix-lightning/` was not on
`sys.path`. Also missing the snapshot writer needed for cross-platform paging.

**What changed:**

- `sys.path.insert` added at top: resolves `sector1/helix-lightning/` relative to
  `__file__` (`tools/poc/ → tools/ → Phoenix-DevOps-oS/ → sector1/helix-lightning/`).
  All existing `franken5` imports resolve without any further changes.
- `HelixI.__init__()` gains `page_dir` param. Reads `PHOENIX_HELIX_PAGE_DIR` env var
  if not passed directly. Creates the directory. Starts the snapshot writer thread.
- `attach_helix_system(helix)` — wires a live `HelixSystem` into the snapshot writer
  so it reports real L1/L2/L3/L5 data instead of zeros.
- `_snapshot_writer_loop()` — background daemon thread. Writes `windows_snapshot.json`
  to `page_dir` every 5 seconds. Atomic write (`.tmp` → `os.replace()`) so `paging.py`
  on Debian never reads a half-written file. Writes zeros if no `HelixSystem` attached
  (graceful — writer starts before suits initialise).
- `stop()` updated with comment: snapshot writer is a daemon thread, exits on `_alive=False`.
- Module docstring updated: correct filename, Strand A/B description, snapshot note.

---

### 2. `sector1/helix-lightning/helix_suit_override.py` — parents index fix

**Problem:** `repo = Path(os.environ.get("PHOENIX_SUITS", Path(__file__).parents[1]))`
— `parents[1]` is `sector1/`, not the repo root. `s1 = repo / "sector1"` then resolves
to `sector1/sector1/helix/helix_complete_stack.py` — wrong. All 13 suit overrides
were silently skipped with "not found" warnings whenever `PHOENIX_SUITS` was not set.

**What changed:**

- `parents[1]` → `parents[2]`. `parents[2]` is `Phoenix-DevOps-oS/` (repo root).
  `s1 = repo / "sector1"` now correctly resolves to `Phoenix-DevOps-oS/sector1/`.
- Comment added explaining the parents index chain.
- One-line fix. No other changes.

---

### 3. `sector4/paging.py` — Helix tier feed wired in (Linux)

**Problem:** `AIPagingManager._get_vrram_snapshot()` estimated tier state from
`/proc/meminfo` with hardcoded 40/30/20 ratios. No visibility into Helix's real
L1/L2/L3 state, and no path to read the Windows strand's snapshot from the shared FS.
`paging_windows.py` had already received this treatment; `paging.py` had not.

**What changed:**

- `self._helix = None` and `self._snapshot_path = None` in `__init__()`.
- `'helix_snapshots': 0` added to stats dict.
- `attach_helix(helix)` — attach a live `HelixSystem` instance. Same pattern as
  `paging_windows.py`.
- `attach_snapshot_path(path)` — set path to `windows_snapshot.json` on the SMB mount
  (`/phoenix/helix-pages/windows_snapshot.json` on Debian).
- `_read_snapshot_json(path)` — reads JSON, validates age < 30s, constructs `TierSnapshot`.
  Returns `None` on any error (missing file, stale, malformed, missing fields).
- `_get_vrram_snapshot()` rewritten with 3-tier priority:
  1. Local `HelixSystem` attached → real tier data
  2. Snapshot path set + file exists + age < 30s → Windows strand data via SMB
  3. Fallback → existing `/proc/meminfo` ratio logic (unchanged)
- `_log_helix_status(snap)` — logs L1/L2/L3/L5 MB + hit rate when a real source is active.
- `monitor_and_adapt()` gains `helix_paging` signal: `frozen_mb > 0` and Helix source
  is active → expand swap proactively before threshold is reached.
- Shrink gated on `not helix_paging` — won't shrink while Helix is writing disk pages.
- `helix_source` field added to `get_status_dict()` return.
- `start()` auto-reads `PHOENIX_PAGING_SNAPSHOT_PATH` env var if snapshot path not
  already set — so `run-helix-poc.sh` can wire it without code changes.
- `PredictiveEngine`, `VirtualProcessor`, `LinuxSwapManager`, `ControlSystem` unchanged.

---

### 4. `tools/poc/run-helix-poc.ps1` — Windows launcher (new)

Sets `PHOENIX_SUITS`, `PHOENIX_HELIX_PAGE_DIR`, `PHOENIX_SECTOR1/2/3`, `PYTHONPATH`.
Creates `F:\Phoenix\helix-pages\` if missing. Runs `py -3 true_double_helix.py`.
Prints instructions for starting the Debian paging brain.

### 5. `tools/poc/run-helix-poc.sh` — Debian launcher (new)

Verifies SMB mount at `/phoenix/`. Sets `PHOENIX_HELIX_PAGE_DIR` and
`PHOENIX_PAGING_SNAPSHOT_PATH`. Re-executes with `sudo` if not root (paging.py
requires root for swapfile ops). Runs `python3 sector4/paging.py start`.

### 6. `tools/poc/helix-poc.suite.json` — suite registration (new)

Registers the PoC as a runnable suite. `usys run helix-poc` works.
Metadata: kernel path, cache backend, paging brains, shared FS mapping, strand
definitions, port assignments, plan file reference.

### 7. `tools/poc/DOUBLE-HELIX-PLAN.md` — plan file (renamed, final)

Renamed from `HELIX-DOUBLE-STRAND-PLAN.md` to match Phoenix's `SUBJECT-PLAN.md`
convention (matches `SHARED-FS-PLAN.md`).

---

## The loop that now exists

```
Windows (Strand A)                         Debian (paging brain)
──────────────────                         ─────────────────────
true_double_helix.py                       paging.py
  HelixI (channels 1-4)                      AIPagingManager
  HelixSystem (L1/L2/L3/L5)                  attach_snapshot_path()
  _snapshot_writer_loop()                     _read_snapshot_json()
         │                                          │
         └──── F:\Phoenix\helix-pages\ ─────────────┘
               windows_snapshot.json
               (written every 5s, read every 5s)

Windows Helix L3 full
    → _demote_to_disk() writes .page files to helix-pages\
    → frozen_mb > 0 in windows_snapshot.json
    → paging.py reads snapshot: helix_paging = True
    → monitor_and_adapt() expands swapfile proactively
    → Linux swap grows
    → OS has more headroom for Helix pages via shared FS
```

Before this session: kernel existed but was unconnected — franken5 imports failed,
suit override pointed at wrong directory, paging.py had no snapshot reader.
After: one closed loop across two OSes. No sockets. No networking. One JSON file.

---

## What is NOT done yet (next session)

### Run the PoC end-to-end

The code is complete. It has not been run with both sides live yet.
Steps:
1. Windows: `pwsh -File tools\poc\run-helix-poc.ps1`
2. Debian (SSH): `bash /phoenix/Phoenix-DevOps-oS/tools/poc/run-helix-poc.sh`
3. Verify `F:\Phoenix\helix-pages\windows_snapshot.json` appears and updates every 5s
4. Verify `paging.py` log shows `[SNAPSHOT]` tier lines

### Delete superseded plan file

`tools/poc/HELIX-DOUBLE-STRAND-PLAN.md` — superseded by `DOUBLE-HELIX-PLAN.md`.

### Linux paging.py `attach_helix()` — local path

`attach_helix()` is wired but the PoC currently only uses `attach_snapshot_path()`.
When `helix_complete_stack.py` is running directly on Debian, the local attach path
should be used instead. Needs a Debian-side `true_double_helix.py` equivalent or
`helix_e.py` (Helix-E) running on Debian with `attach_helix_system()` wired.

---

## Files changed this session

| File | Change |
|------|--------|
| `tools/poc/true_double_helix.py` | sys.path fix, snapshot writer, attach_helix_system |
| `sector1/helix-lightning/helix_suit_override.py` | parents[1] → parents[2] |
| `sector4/paging.py` | attach_helix, attach_snapshot_path, _read_snapshot_json, helix_paging signal |
| `tools/poc/run-helix-poc.ps1` | NEW — Windows launcher |
| `tools/poc/run-helix-poc.sh` | NEW — Debian launcher |
| `tools/poc/helix-poc.suite.json` | NEW — suite registration |
| `tools/poc/DOUBLE-HELIX-PLAN.md` | NEW — plan file (canonical) |
| `SESSION_STATE.md` | Updated |

## Files unchanged but relevant next session

| File | Why |
|------|-----|
| `sector1/helix-lightning/main_kernel.py` | Full boot sequence — Frank → Library → Spawn → Helix-I/E |
| `sector1/helix-lightning/helixi.py` | Source of truth for HelixI (true_double_helix.py is its PoC copy) |
| `sector1/helix-lightning/helixe.py` | Helix-E (egress, channels 5-8) — Debian Strand B |
| `sector1/helix/helix_complete_stack.py` | The suit — all rings run through this |
| `sector4/paging_windows.py` | Windows paging brain — already complete |

---

## Environment facts confirmed this session

- `sector1/helix-lightning/__pycache__/` has `cpython-314.pyc` files — kernel was run before
- `PHOENIX_SUITS` → repo root `Phoenix-DevOps-oS/`
- `PHOENIX_HELIX_PAGE_DIR` → `F:\Phoenix\helix-pages\` (Windows) / `/phoenix/helix-pages/` (Debian)
- `PHOENIX_PAGING_SNAPSHOT_PATH` → `/phoenix/helix-pages/windows_snapshot.json` (Debian)
- `py -3` is the working Python 3 invocation on this machine
- SMB mount `F:\Phoenix\` ↔ `/phoenix/` proven live 2026-08-23
- Atomic JSON write (`os.replace`) confirmed as the correct pattern for cross-OS file sharing
