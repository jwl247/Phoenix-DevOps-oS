# Kernel Import Operational Plan
## Goal
Confirm the application kernel (Phoenix DevOps OS) can execute the import method end-to-end.
The import method is: `file → intake.sh → hex identity → sidecar.json → clone pool → D1 custody`

The project has moved to `W:\vault\phoenix-predeploy\Phoenix-DevOps-oS\`.

## Scope
Fix the four blocking issues that prevent the import pipeline from running, then verify
the pipeline can be called from both PowerShell (Windows) and Bash (Git Bash / WSL).

Four blockers must be resolved in order:
1. `intake.py` is missing — `intake.sh` calls it but the file does not exist
2. `SECTOR4/coms1/helix_api.py` has two bugs that crash the coms ring
3. `SECTOR4/vault/helix_memory.py` is missing four classes that `HelixSystem` instantiates
4. The `PHOENIX_ROOT` environment variable must point at the new W: path

## Non-Goals
- Do not touch `helix_core.c`, `helix_ingress.c`, or any C source (C layer remains a stub)
- Do not implement R2 upload or D1 POST in this pass (those are Phase 2)
- Do not modify the dashboard or any sector3/sector1 components
- Do not refactor anything beyond the exact fix needed

---

## Sub-Task 1 — Fix helix_api.py bugs

**Intent**
Two Python bugs in `SECTOR4/coms1/helix_api.py` cause `AttributeError` and
`NameError` at runtime. Any coms ring that imports `Franken2` or `Freewheeling`
will crash. Fix them so the coms ring can load cleanly.

**Bugs:**
- Line 24: `self.OVERFLOW_PATH` does not exist — should be `self.RESPONSIBILITY_PATH`
- Line ~58: method signature `def load_warm(self, ket)` uses `ket` but the body
  calls `key` — rename parameter to `key`

**Expected Outcomes**
- `python -c "from helix_api import Franken2, Freewheeling"` executes without error
- No AttributeError on `OVERFLOW_PATH`
- No NameError on `key` vs `ket`

**Todo List**
1. Open `W:\vault\phoenix-predeploy\Phoenix-DevOps-oS\SECTOR4\coms1\helix_api.py`
2. Line 24: replace `self.OVERFLOW_PATH` → `self.RESPONSIBILITY_PATH`
3. Line ~58: replace `def load_warm(self, ket):` → `def load_warm(self, key):`
4. Confirm the body already uses `key` (it does — `self.warm_memory.get(key)`)
5. Run import smoke test

**Relevant Context**
- File: `SECTOR4/coms1/helix_api.py`
- `RESPONSIBILITY_PATH` is defined at class level on line ~8 of the same file
- The `Freewheeling.load_warm` method body is `return self.warm_memory.get(key)` — key is correct, only the parameter name is wrong

**Status:** [ ] pending

---

## Sub-Task 2 — Define 4 missing classes in helix_memory.py

**Intent**
`HelixSystem` (in `helix_memory.py`) tries to instantiate four classes that are
referenced but never defined: `HelixMemoryManager`, `HelixFS`, `FrankCastReel`,
and `SectorRouter`. Write minimal stub implementations so `HelixSystem` can be
instantiated without crashing. Full behavior can be fleshed out in a later pass.

**Expected Outcomes**
- `python -c "from helix_memory import HelixSystem; HelixSystem()"` runs without ImportError or NameError
- All four classes exist and accept the constructor signatures `HelixSystem` passes to them
- No existing logic in `helix_memory.py` is altered

**Todo List**
1. Read `SECTOR4/vault/helix_memory.py` in full to understand exactly how
   `HelixSystem` calls each of the four classes (constructor args, methods called)
2. Write minimal stub for `HelixMemoryManager(cache, virtual_mb)`
3. Write minimal stub for `HelixFS(memory)`
4. Write minimal stub for `FrankCastReel(memory)`
5. Write minimal stub for `SectorRouter(memory)`
6. Append the four stubs to the end of `helix_memory.py` (before the `run()` function)
7. Run import smoke test

**Relevant Context**
- File: `SECTOR4/vault/helix_memory.py`
- `HelixCache` and `PCSTorrentModel` are already fully defined — use them as style guides
- The `run()` entry point at the bottom of the file must remain intact
- Use `pass`-body methods where behavior is not yet known — no invented logic

**Status:** [ ] pending

---

## Sub-Task 3 — Write intake.py

**Intent**
`intake.sh` calls `python3 "${INTAKE_PY}" "${target}"` where `INTAKE_PY` points to
`~/projects/unitedsys/core/intake.py`. This file does not exist anywhere on the system.
Write a minimal `intake.py` that implements the TAV intake contract:
`file_path → SHA3-512 hex_id → sidecar.json → local clone pool write → D1 custody POST (best-effort)`

The file must be placed at `phoenix-core/tools/intake.py` and also symlinked / copied to
the path `intake.sh` expects (`~/projects/unitedsys/core/intake.py`).

**TAV contract (from CLAUDE.md and PHOENIX_BUILD_MASTER.md):**
```
hex_id   = SHA3-512(file_content) → first 8 bytes → base58   [TAV address]
header   = USYS:<b58>:HEADER   state: white/grey/black
footer   = USYS:<b58>:FOOTER:<sha3_full>   tier: T1/T2/T3/T4
sidecar  = { hex_id, name, original_name, state, tier, size, hash_sha3,
             category, label, intaked_at, notes }
```

**Expected Outcomes**
- `python intake.py <any-file>` exits 0 and prints hex_id
- A `sidecar.json` is written alongside the file in the clone pool directory
- A custody receipt is written to `~/.catalog/` (local, no network required)
- D1 POST is attempted but failure is non-fatal (best-effort)
- `intake.sh status` shows `intake.py` found

**Todo List**
1. Read `SECTOR4/intake/intake.sh` fully to understand exact `INTAKE_PY` path logic
2. Read `phoenix-core/include/helix.h` `helix_sidecar_t` struct for field names to match
3. Write `phoenix-core/tools/intake.py` with:
   - CLI entry: `intake.py <file_path> [category] [label]`
   - SHA3-512 of file content → full hex string
   - Base58 encode first 8 bytes → short TAV address
   - Build sidecar dict matching `helix_sidecar_t` field names
   - Write `sidecar.json` to clonepool directory (env var `CLONEPOOL_DIR` or default)
   - Write custody receipt to `~/.catalog/`
   - Attempt D1 POST to `PHOENIX_WORKER_URL` — log warning on failure, do not exit 1
   - Print `hex_id` and sidecar path on success
4. Confirm the script is executable (`chmod +x` note for Linux)
5. Update `intake.sh` `INTAKE_PY` path variable to point at the new location
   OR add a note that `PHOENIX_ROOT` must be set so `intake.sh` resolves it

**Relevant Context**
- File to create: `phoenix-core/tools/intake.py`
- Reference struct: `phoenix-core/include/helix.h` lines 52-65 (`helix_sidecar_t`)
- Caller: `SECTOR4/intake/intake.sh` (uses `$HOME/projects/unitedsys/core/intake.py`)
- Clonepool location: env `CLONEPOOL_DIR` → default `~/Phoenix/clonepool`
- Worker URL: env `PHOENIX_WORKER_URL`
- Auth token: env `PHOENIX_AUTH`
- No base58 library is guaranteed installed — implement a minimal base58 encoder inline (alphabet: `123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz`)

**Status:** [ ] pending

---

## Sub-Task 4 — Update PHOENIX_ROOT and path resolution

**Intent**
The project moved from `C:\Users\jwlef\Phoenix\Phoenix-DevOps-oS` to
`W:\vault\phoenix-predeploy\Phoenix-DevOps-oS`. Scripts that hard-code the old path
or rely on `PHOENIX_ROOT` will fail silently. Update the path references so that
`intake.ps1`, `intake.sh`, and the dashboard can find the kernel files on W:.

**Expected Outcomes**
- `$env:PHOENIX_ROOT` resolves to `W:\vault\phoenix-predeploy\Phoenix-DevOps-oS`
- `scripts/intake.ps1` resolves `intake.sh` correctly under the new root
- `SECTOR4/intake/intake.sh` `INTAKE_PY` variable resolves to the newly created `intake.py`
- Running `intake status` (ps1 or sh) prints OK with no missing-file errors

**Todo List**
1. Read `scripts/intake.ps1` fully to find all hard-coded path references
2. Read `SECTOR4/intake/intake.sh` to confirm `INTAKE_PY` default path
3. Update `intake.sh` `INTAKE_PY` to use `${PHOENIX_ROOT}/phoenix-core/tools/intake.py`
   with a fallback to the old `~/projects/unitedsys/core/intake.py`
4. Add a note to `CLAUDE.md` under environment variables:
   `PHOENIX_ROOT = W:\vault\phoenix-predeploy\Phoenix-DevOps-oS`
5. Verify `intake.ps1` uses `$env:PHOENIX_ROOT` (it already does) — no edit needed if so

**Relevant Context**
- `scripts/intake.ps1` line 57: `if ($env:PHOENIX_ROOT -and (Test-Path $env:PHOENIX_ROOT))`
  — already uses the env var, just needs the var set externally
- `SECTOR4/intake/intake.sh` line ~15: `INTAKE_PY="${HOME}/projects/unitedsys/core/intake.py"`
  — this is the hard-coded path that needs to change

**Status:** [ ] pending

---

## Smoke Test Checklist (run after all 4 sub-tasks complete)

After implementation, confirm each check passes:

```
[ ] python -c "from helix_api import Franken2, Freewheeling, Propcoms"  → no error
[ ] python -c "from helix_memory import HelixSystem; s = HelixSystem()"  → no error
[ ] python intake.py <any-test-file>  → prints hex_id, writes sidecar.json
[ ] intake status  (bash)  → vault OK + intake.py found
[ ] intake <any-test-file>  (bash)  → hex_id + sidecar written + custody receipt
[ ] PHOENIX_ROOT=W:\vault\... intake status  (powershell)  → OK
```
