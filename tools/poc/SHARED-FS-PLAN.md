# Phoenix PoC — Shared Filesystem: Windows Hosts, Debian Mounts
# Plan file — read this before implementing any sub-task
# =============================================================================

## Overview

Windows is the bare metal host. F: drive holds the canonical shared directories.
Debian running inside QEMU sees those same directories via virtio-9p passthrough —
the same bytes, no sync, no copy, no WSL, no Wine. QEMU is the only bridge.

The PS7 profile is the enforcement layer. It holds named wrappers that define
the only legal operations against the shared area. There is no raw path.
Import goes through intake. Export goes through clone. The profile makes that
non-negotiable in every terminal session, on both sides of the boundary.

**The principle:** Windows owns the FS. QEMU bridges it. The PS7 profile enforces it.
Intake a suite once — it is immediately runnable. No install. No manual clone step.

**Scope:** tools/poc/, scripts/usys.ps1, tools/poc/debian-seed/, sector2/package-handler/intake.sh
Nothing outside those four locations is touched.

**Non-goals:**
- No WSL. No Wine. No hidden middleware. No Hyper-V shared folders.
- No changes to breach_coms drives or Frank's drive routing.
- No GUI tooling — CLI and profile only.
- No raw filesystem access patterns — everything through the named wrappers.

---

## Shared Directory Layout

Windows host (F: drive) — canonical locations:

```
F:\Phoenix\
  Desktop\
  Documents\
  Downloads\
  Projects\
  Vault\
```


Debian mounts at:

```
/phoenix/
  Desktop    ← mount_tag: phoenix-desktop
  Documents  ← mount_tag: phoenix-documents
  Downloads  ← mount_tag: phoenix-downloads
  Projects   ← mount_tag: phoenix-projects
  Vault      ← mount_tag: phoenix-vault
```

The mount tag is the QEMU virtio-9p contract. It is a stable string — does not
encode a Windows path, so the host-side location can change without touching
the Debian fstab.

---

## System Identity Output

Minimal. Two lines. Appears at `usys run debian --share`, `setup-shared-fs.ps1`,
and `phx-ls`. No ASCII art. No color prose. States the contract.

```
  Phoenix FS  Windows reliable  Debian fast  QEMU bridges
  Desktop  Documents  Downloads  Projects  Vault
```

Implemented as `Write-PhxFsBanner` in `usys.ps1`. Called by setup, run, and ls.

---

## PS7 Profile Wrappers — The Enforcement Layer

These are the only legal operations against the Phoenix shared FS.
They are loaded by the profile on every terminal open — no session starts
without them. The names are unambiguous verbs. There is no "usys copy".

| Wrapper | Direction | What it does |
|---------|-----------|--------------|
| `phx-import <path>` | shared FS → clonepool | Runs intake on a file in the shared area; gives it a hex ID and registers it in D1 |
| `phx-export <hex-or-name> <dir>` | clonepool → shared FS | Clones a hex-identified item out of the pool into a named shared directory |
| `phx-sync <dir>` | shared FS dir → clonepool | Walks a shared directory and imports everything not yet in the pool (idempotent) |
| `phx-ls [dir]` | read-only | Lists the shared FS directories and their Phoenix registration status |

Rules embedded in each wrapper:
- `phx-import` validates the source path is inside `F:\Phoenix\` before proceeding
- `phx-export` validates the destination is inside `F:\Phoenix\` before proceeding
- `phx-sync` is read-only toward the clonepool direction (import only, never destructive)
- All four wrappers log their action via `Write-UsysInfo` so there is an audit trail in the terminal

These wrappers are defined inside `usys.ps1` as named functions and then the
profile block (written by `usys init`) includes them by dot-sourcing usys.ps1.
No separate file is needed — they live in the same script, same audit trail.

---

## Sub-Tasks

---

### Sub-Task 0a — Suite Auto-Registration on Intake (.suite.json files)

**Status:** `[ ] pending`

**Intent**
Today `intake_file()` treats a `.suite.json` as a raw blob — it lands in
`clonepool/<hex>/v1_debian.suite.json`. `Invoke-UsysRun` reads suites from
`clonepool/<suitename>/.suite.json` — a named directory. The two never connect.

Fix: when `intake_file()` sees a `.suite.json` extension, after the standard
hex/D1/R2 pipeline completes, it reads the `name` field from the JSON and
creates `clonepool/<name>/.suite.json`. The file is immediately runnable.
No `usys clone` step. No manual directory setup. Intake → run.

**Versioning Status**
- Pool versioning: ✅ the `.suite.json` file gets versioned as `v1_debian.suite.json`,
  `v2_debian.suite.json` etc. each time it is re-intaked — `get_next_version()` handles this
- Latest always wins: ✅ `get_latest_file()` returns highest version number — the copy
  placed at `clonepool/<name>/.suite.json` is always from the latest pool version
- Eviction rule — INTENDED: a version is only evicted when bumped past 7 versions.
  The 3-day figure is a rollback window (how long you have to roll back before a version
  can be displaced), not a forced deletion timer. A file is never forcibly deleted just
  because it is 3 days old — it can only be evicted if a new intake pushes it beyond
  the 7-version limit.
- Eviction rule — CURRENT CODE: `evict_old_versions()` uses `age > EVICT_DAYS=3` —
  age-based deletion, not count-based. **This is a bug.** The code does not implement
  the intended rule. It will delete versions older than 3 days regardless of version count.
- **Fix required in Sub-Task 0a**: change `evict_old_versions()` to count-based eviction:
  keep the 7 most recent versions, evict anything beyond that. Remove `EVICT_DAYS` age check.
  Retain the "latest is never evicted" guard. The 3-day figure moves to documentation only
  as a description of the expected rollback window, not a code constant.
- `clone_history` in sidecar: ⚠️ `write_sidecar_basic` always overwrites the sidecar
  with a fresh single-entry `clone_history`. Prior versions are in D1 custody chain but
  not in the local sidecar. Out of scope for this plan — recorded as known loose end.

**Expected Outcomes**
- `intake_file()` in `sector2/package-handler/intake.sh` detects `.suite.json`
  after the standard pipeline succeeds (after `upload_to_r2`, `report_glossary`)
- Reads `name` field: try `jq -r .name` first, fall back to portable `grep`/`sed`
- Validates name is non-empty and contains no path separators
- Creates `$CLONEPOOL_DIR/<name>/` with `mkdir -p`
- Copies file to `$CLONEPOOL_DIR/<name>/.suite.json` — always from the latest pool version
- Prints `[intake:SUITE] <name> → clonepool/<name>/ — runnable: usys run <name>`
- All other file types completely unchanged

**Rollback / Version Listing Scope Note**
Version history browsing and rollback initiation belong to the **Glossary** — that is
the index, the TOC, the place you go to see what versions of a file exist and act on them.
The D1 custody table (`GET /custody?hex=`) already holds every action ever taken.
The `/versions` endpoint already exists in `packages-worker/index.js` (line 944).
The Glossary UI panel is Phase 6 — not this plan.

What `intake.sh` IS responsible for: the **local mechanical primitive** —
`intake clone <file> <version>` must honour the version argument for single files
(currently it ignores it and always returns latest). This is the low-level path
the Glossary will call. It does not surface version lists — that is Glossary's job.

**Todo List**
1. Fix `evict_old_versions()` (lines ~246-273):
   - Remove `age > EVICT_DAYS` condition entirely
   - Replace with count-based: sort all versions by number, keep 7 most recent, evict rest
   - `EVICT_DAYS=3` → `MAX_VERSIONS=7` at top of file
   - "Latest is never evicted" guard stays exactly as-is
   - Update `intake_prune` output: "Retention: 7 versions" not "3 days"
   - Update `intake_status` output: line 814 shows `EVICT_DAYS` — update to `MAX_VERSIONS`
   - Update `show_help` lines 861-862: correct the eviction description
2. Extend `intake_clone()` (lines ~637-701) to honour an optional version argument:
   - Add `local version="${2:-latest}"` parameter
   - If version is not "latest": target `${pool_dir}/${version}_${name}` directly
   - If that file does not exist: print clear error listing available versions
   - Same integrity check (`verify_clonepool_copy`) and custody log as the latest path
   - Entry point line 1287 already passes `version` to `intake_clone_directory` —
     add the same pass-through for `intake_clone "${name}" "${version}"`
3. Read `intake_file()` lines ~607-632 to find exact post-pipeline insertion point
4. Add conditional block after `evict_old_versions` call: `if [[ "${orig}" == *.suite.json ]]`
   — after eviction so the copy placed is confirmed to be the surviving latest
5. Extract name: `jq -r .name 2>/dev/null` with `grep`/`sed` fallback
6. Guard: skip if name is empty or contains `/` or `\`
7. `mkdir -p "${CLONEPOOL_DIR}/${suite_name}"`
8. Re-resolve latest after eviction: `latest=$(get_latest_file "${pool_dir}" "${orig}")`
9. `cp "${latest}" "${CLONEPOOL_DIR}/${suite_name}/.suite.json"`
10. Print `[intake:SUITE]` confirmation line

**Relevant Context**
- `sector2/package-handler/intake.sh` line 21 — `EVICT_DAYS=3` to rename
- `sector2/package-handler/intake.sh` lines 246-273 — `evict_old_versions()` to fix
- `sector2/package-handler/intake.sh` lines 637-701 — `intake_clone()` to extend
- `sector2/package-handler/intake.sh` line 1287 — entry point, add version pass-through
- `sector2/package-handler/intake.sh` lines 607-632 — pipeline tail, suite hook goes here
- `scripts/usys.ps1` line 732 — `Get-UsysSuiteManifest` reads `<suitepath>/.suite.json`
- `sector3/workers/packages-worker/index.js` line 944 — `/versions` endpoint already live
- D1 custody table — full action history, queryable at `GET /custody?hex=<hex>`
- Suite name field: always a simple identifier like `"debian"`, `"yt-dlp"` — never a path

---

### Sub-Task 0b — Suite Promote: Any Intaked File Becomes Runnable

**Status:** `[ ] pending`

**Intent**
Any file that Phoenix has intaked — a `.py` script, a `.sh`, a `.exe` binary,
a `.qcow2` image — can be promoted to a runnable suite without reinstalling or
re-importing it. The file is already in the pool with a hex ID; `usys suite-promote`
generates a `.suite.json` for it and places it in `clonepool/<name>/`, making it
immediately runnable via `usys run <name>`.

Runtime is auto-detected from the file extension — mirroring the logic in
`detect_filetype()` in `intake.sh`, not reimplementing it.

This is the mechanism that makes collaboration output runnable: a script, tool,
or binary produced by any workflow — local, AI-assisted, remote — is intaked once
and promoted once. Phoenix runs it. No install. No platform dependency.
The suite is the unit of execution.

**QR / Integrity Status**
- The **source file** (already intaked) has full QR codes + hash baseline from its original `intake_file()` run ✅
- The **generated `.suite.json`** written by `suite-promote` is a new artifact — it bypasses `intake_file()` and therefore has no hex identity, no QR strings, no D1 record, no hash baseline ❌
- Fix: `suite-promote` writes manifest to a temp path, calls `Invoke-UsysClone` on it — `intake_file()` issues hex, QR, hash baseline, D1, R2. Sub-Task 0a hook then fires and places it at `clonepool/<name>/.suite.json` ✅

**Versioning Status**
- Source file pool version: ✅ the source file's pool version (e.g. `v3`) is read from
  `get_latest_file()` and stamped into the generated manifest's `version` field — not hardcoded `v1`
- Generated manifest pool version: ✅ when `Invoke-UsysClone` re-intakes the manifest,
  it enters the pool as `v1_<name>.suite.json` (first intake of that manifest) — correct
- 3-day eviction: ✅ not a concern for the generated manifest — it enters the pool fresh
  as `v1` and eviction only fires on re-intake when a new version exists
- Sidecar `clone_history` accumulation: ⚠️ known loose end (out of scope) —
  `write_sidecar_basic` always overwrites with a single-entry history. Full history
  lives in D1 custody chain. Local sidecar only shows current version.

**Expected Outcomes**
- New `usys` subcommand: `usys suite-promote <name> [--version v1] [--desc "..."]`
- Resolves the named file from the clonepool (finds latest versioned file matching name)
- Auto-detects runtime from extension:
  `.py`→`python`, `.sh`→`bash`, `.ps1`→`powershell`,
  `.js`→`node`, `.exe`→`binary`, `.qcow2`→`qemu`, `.img`→`qemu`, default→`binary`
- Generates a minimal `.suite.json`: name, version, entry (filename), runtime,
  description, hex_id in metadata
- Writes to `clonepool/<name>/.suite.json`
- **Intakes the generated `.suite.json` through `Invoke-UsysClone`** so it receives:
  hex identity, `USYS:<b58>:HEADER` + `USYS:<b58>:FOOTER:<hex>` QR strings,
  SHA3-512 + BLAKE2b hash baseline, D1 record, R2 upload
- Prints `[suite:OK] <name> promoted — hex + QR issued — runnable: usys run <name>`
- `usys suite-list` aliases the existing `usys list-suites`

**Todo List**
1. Add `Get-UsysRuntimeForExt` helper to `scripts/usys.ps1` — maps file extension
   to runtime string, mirrors `detect_filetype()` extension map from `intake.sh`
2. Add `Invoke-UsysSuitePromote` function to `scripts/usys.ps1`
3. Param block: `-Name` (mandatory), `-Desc` (optional) — version is read from source file's pool version, not user-supplied
4. Resolve file: search `clonepool/` for latest versioned file matching the name
5. Determine entry filename and runtime via `Get-UsysRuntimeForExt`
6. Build `.suite.json` hashtable with all required fields (name, version, entry,
   runtime, description, author `phoenix`, type `script`, dependencies `[]`,
   environment `{}`, metadata.hex_id)
7. Write to a temp path first, then call `Invoke-UsysClone` on it — this triggers
   `intake_file()` which issues hex, QR strings, hash baseline, D1, R2
8. Sub-Task 0a's auto-registration hook then fires: the intaked `.suite.json` is
   copied to `clonepool/<name>/.suite.json` automatically
9. Print confirmation showing name, hex, and `usys run <name>` instruction
10. Add `suite-promote` and `suite-list` cases to dispatcher switch block
11. Add to `Show-UsysHelp` under new "Suites" section

**Relevant Context**
- `scripts/usys.ps1` lines 1021-1051 — `Invoke-UsysListSuites` (existing `list-suites`)
  — `suite-list` is an alias for this, same function
- `scripts/usys.ps1` line 1162 — main dispatcher, add two new cases here
- `sector2/package-handler/intake.sh` lines 127-155 — `detect_filetype()` —
  mirror extension→runtime map in PS7
- `.suite.json` fields required by `Invoke-UsysRun`: `name`, `version`, `entry`,
  `runtime`, `type` — all others optional but include for completeness

---

### Sub-Task 0c — Project Intake: Multi-Directory as One Named Unit

**Status:** `[ ] pending`

**Intent**
A collaboration build is never a single directory. It spans `src/`, `config/`,
`scripts/`, `tests/`, docs. Today each top-level folder must be intaked and
restored separately. There is no way to name a collection of directories as
one versioned unit and restore the whole thing in one command.

Phoenix itself is intaked at the top-tier level (`sector1/`, `sector2/`, etc.)
and as a whole. The same must be true for collaboration output. If you build
something with Phoenix — or receive it as output from any collaborative process
— it should be intake-able as a project and restorable as a project. No install.
The project is the unit.

**Scope — what this is NOT:**
Not a package manager. Does not resolve dependencies. Does not compile. Does not
install. Intakes a named snapshot of multiple directories under one project
identity, gives the whole thing a hex + QR, restores it on demand.

**What exists already:**
- `intake_directory()` — single directory recursive intake with snapshot. The primitive. ✅
- `intake_clone_directory()` — single directory version-specific restore. The primitive. ✅
- Both are correct and complete. Project intake calls them per component.

**Expected Outcomes**
- New function `intake_project()` in `intake.sh`:
  - Takes a project `name` and one or more directory paths
  - Calls `intake_directory()` on each component directory (all existing logic reused)
  - Computes project hex: `to_hex "${name}"`
  - Writes a project sidecar to `clonepool/<project_hex>/project.sidecar.json`:
    name, version, component list (each: dirname, hex, version, original path)
  - Calls `report_clonepool` and `report_glossary` for the project hex
  - Prints: project name, hex, version, component list, restore command
- New function `intake_clone_project()`:
  - Resolves `clonepool/<project_hex>/project.sidecar.json`
  - If version arg given: finds the sidecar for that project version
  - For each component in the manifest: calls `intake_clone_directory()` with
    that component's name and the version recorded in the project snapshot
  - Prints restore summary
- Entry point dispatcher:
  - `intake project <name> <dir1> [dir2...]` → `intake_project()`
  - `intake clone project <name> [v2]` → `intake_clone_project()`
- `show_help()` updated with project section

**Versioning:**
- Each component is versioned independently via `intake_directory()` ✅
- Project sidecar records which component version was current at each project snapshot
- Rolling back a project restores all components to their versions at that snapshot

**QR / Integrity:**
- Each component gets its own QR and hash via `report_clonepool()` as today ✅
- The project-level sidecar gets its own `report_clonepool()` call — project has
  its own QR identity ✅

**Pre-requisite fixes required before intake_project() can work:**

Fix A — `intake_directory()` interactive prompt blocks non-interactive calls:
- Line 1039: `read -rp "Choice [1/2/3]:"` blocks if called from `intake_project()`
- Add `local noninteractive="${INTAKE_YES:-false}"` check at the top of `intake_directory()`
- When caller sets `INTAKE_YES=1` env var: skip the prompt, proceed with full intake
- `intake_project()` sets `INTAKE_YES=1` before each component call, unsets after

Fix B — `intake_directory()` returns no machine-readable output for caller:
- Currently only prints progress to stdout, no structured return
- After the final summary block, add two lines when `INTAKE_YES` is set:
  `echo "[intake:DIR:HEX] ${hex}"` and `echo "[intake:DIR:VER] ${version}"`
- `intake_project()` captures stdout and greps these lines to build the component list

Fix C — `.qcow2` and `.img` missing from `SKIP_EXTENSIONS` (line 882):
- These are VM disk images (400MB+), not source files
- R2 upload ceiling is 100MB — hitting one logs a warning and wastes time
- Add `.qcow2` and `.img` to the `SKIP_EXTENSIONS` array

**Todo List**
1. Fix `intake_directory()` for non-interactive use (Fix A + Fix B above):
   - Read lines ~927-1186 to find the prompt block (line 1039) and summary block
   - Add `INTAKE_YES` env var check before the prompt
   - Add `[intake:DIR:HEX]` and `[intake:DIR:VER]` output lines in non-interactive mode
2. Fix `SKIP_EXTENSIONS` (Fix C): add `".qcow2"` and `".img"` to array at line 882
3. Add `intake_project()` function after `intake_directory()` (~line 1186):
   a. Validate: name is non-empty, no slashes; at least one dir arg exists
   b. `project_hex=$(to_hex "${name}")`; `project_pool="${CLONEPOOL_DIR}/${project_hex}"`
   c. `project_version=$(get_next_version "${project_pool}")`
   d. For each dir arg: set `INTAKE_YES=1`, call `intake_directory()`, capture output,
      grep for `[intake:DIR:HEX]` and `[intake:DIR:VER]`, unset `INTAKE_YES`
   e. Build `components` JSON array: each entry has dirname, hex, version, path
   f. Write `project.sidecar.json` to `${project_pool}/`
   g. `report_clonepool` and `report_glossary` for project hex
   h. Print project summary
4. Add `intake_clone_project()` function after `intake_clone_directory()` (~line 1260):
   a. Read `project.sidecar.json` for the named project
   b. If version arg: locate the sidecar version matching it
   c. For each component: call `intake_clone_directory()` with name + version
   d. Print restore summary
5. Add dispatcher cases to entry point (~line 1278):
   - `project)` → `shift; intake_project "$@"`
   - In `clone)` block: check if `name == "project"` → shift to `intake_clone_project`
6. Update `show_help()` with:
   - `intake project <name> <dir1> [dir2...]   Intake multiple dirs as one named project`
   - `intake clone project <name> [v2]          Restore a full project snapshot`

**Relevant Context**
- `sector2/package-handler/intake.sh` lines 927-1186 — `intake_directory()` — call per component
- `sector2/package-handler/intake.sh` lines 1189-1260 — `intake_clone_directory()` — restore per component
- `sector2/package-handler/intake.sh` lines 1278-1301 — entry point dispatcher
- A project with 3 dirs = 4 pool entries: 3 dir hexes + 1 project hex
- Project sidecar type field: `"type": "project"` — distinct from `"type": "directory"`
- Glossary category hex for projects: `"70726f6a656374"` (hex of "project")

---

### Sub-Task 1 — Path Wrapper in usys.ps1

**Status:** `[ ] pending`

**Intent**
QEMU's -virtfs argument takes a Windows path. A centralized converter function
eliminates the slash problem in the QEMU argument builder. This function extends
the existing `ConvertTo-GitBashPath` pattern (usys.ps1 line 113) but targets
QEMU's virtfs path= syntax specifically — forward slashes, drive letter and
colon preserved (QEMU on Windows accepts this directly).

Also defines `$script:PhxSharedRoot` — the single canonical variable that holds
`F:\Phoenix` so no sub-task hardcodes the drive letter. All other sub-tasks
reference this variable.

**Expected Outcomes**
- `$script:PhxSharedRoot = 'F:\Phoenix'` defined near the top of usys.ps1
  module metadata section, next to the other `$script:` variables
- New function `ConvertTo-QemuHostPath` added immediately after `ConvertTo-GitBashPath`
- `C:\Users\jerry\Phoenix` → `C:/Users/jerry/Phoenix`
- `F:\Phoenix\Desktop` → `F:/Phoenix/Desktop`
- All backslashes to forward slashes; drive letter and colon preserved
- Existing `ConvertTo-GitBashPath` unchanged

**Todo List**
1. Read usys.ps1 lines 29-40 (module metadata block) to confirm exact insertion point
2. Add `$script:PhxSharedRoot = 'F:\Phoenix'` to the metadata block
3. Add `$script:PhxSharedDirs  = @('Desktop','Documents','Downloads','Projects','Vault')` alongside it
4. Read usys.ps1 lines 113-120 to confirm insertion point after ConvertTo-GitBashPath
5. Add `ConvertTo-QemuHostPath` function immediately after — replaces backslash with
   forward slash, preserves drive letter and colon

**Relevant Context**
- `scripts/usys.ps1` lines 29-40 — module metadata, where `$script:` vars are defined
- `scripts/usys.ps1` line 113 — `ConvertTo-GitBashPath` to insert after
- QEMU virtfs path= on Windows: `F:/Phoenix/Desktop` is correct form

---

### Sub-Task 2 — Shared Directory Bootstrap Script

**Status:** `[ ] pending`

**Intent**
One-time idempotent setup that creates the canonical shared directories on F:,
stamps a `_PHOENIX_DIR.txt` marker in each, and prints the mount table.
Also adds the `phx-` wrappers to the profile (calling `usys fs-init`).
Running it is safe to repeat — nothing is overwritten destructively.

**Expected Outcomes**
- New file: `tools/poc/setup-shared-fs.ps1`
- Creates `F:\Phoenix\{Desktop,Documents,Downloads,Projects,Vault}` if absent
- Writes `_PHOENIX_DIR.txt` marker (dir name + timestamp + Phoenix identity)
- Prints the mount table: Windows path → virtio-9p tag → Debian path
- Idempotent, no elevation required, PS7 only
- After this script runs, `phx-import`, `phx-export`, `phx-sync`, `phx-ls`
  are available in the current and all future terminals (via profile)

**Todo List**
1. Create `tools/poc/setup-shared-fs.ps1`
2. Dot-source `scripts/usys.ps1` to get access to `$script:PhxSharedRoot`
   and `$script:PhxSharedDirs`
3. Create each directory under `$script:PhxSharedRoot` with `New-Item -Force`
4. Write `_PHOENIX_DIR.txt` marker in each: name, timestamp, `phoenix-<tag>`
5. Print mount table as a formatted PS7 table
6. Call `usys init` silently if profile not yet wired (detected by checking
   `$PROFILE` content for 'Phoenix USys'), otherwise print "profile already wired"

**Relevant Context**
- `tools/poc/run-debian.ps1` — style/convention reference for launcher scripts
- `$script:PhxSharedRoot` and `$script:PhxSharedDirs` defined in Sub-Task 1
- `usys init` profile-wiring code lives at usys.ps1 lines 264-285 — re-use it,
  don't duplicate it

---

### Sub-Task 3 — PS7 Profile Wrappers (phx-import, phx-export, phx-sync, phx-ls)

**Status:** `[ ] pending`

**Intent**
These are the enforcement boundary. They are defined in usys.ps1 so they are
loaded by every terminal that dot-sources it (which the profile does after
`usys init`). They are the only legal operations against the shared area.
No sub-task, no user session, no Debian-side script bypasses them.

Each wrapper:
- Validates paths stay inside `$script:PhxSharedRoot`
- Routes through the existing `Invoke-UsysClone` / `Invoke-UsysIntake` machinery
- Writes a `Write-UsysInfo` audit line before acting
- The `usys` dispatcher gets four new cases: `fs-import`, `fs-export`, `fs-sync`, `fs-ls`

**Expected Outcomes**
- `Invoke-PhxImport` — validates source is inside PhxSharedRoot, then calls
  `Invoke-UsysClone` on it (Sector 2 intake path: hex ID + D1 registration)
- `Invoke-PhxExport` — validates destination dir is inside PhxSharedRoot, resolves
  hex/name from clonepool, copies the file there
- `Invoke-PhxSync` — walks a named shared dir, calls `Invoke-PhxImport` on every
  file not yet in the pool (checks by filename against D1 via worker API)
- `Invoke-PhxLs` — lists each shared dir, file count, and pool registration status
- All four exposed as `usys fs-import`, `usys fs-export`, `usys fs-sync`, `usys fs-ls`
  via the main dispatcher
- Help text updated with the four new commands

**Todo List**
1. Read usys.ps1 around line 1092 (help section) and line 1162 (dispatcher) to
   understand insertion points
2. Add `Invoke-PhxImport` function — path guard (`Test-PhxSharedPath` helper),
   then delegate to `Invoke-UsysClone`
3. Add `Invoke-PhxExport` function — resolve clonepool item by name or hex,
   path guard on destination, then `Copy-Item` into the shared dir
4. Add `Invoke-PhxSync` function — enumerate files in named shared dir,
   call `Invoke-PhxImport` on each, skip already-registered (check
   `$env:PHOENIX_WORKER_URL/clonepool/<hex>` returns 200)
5. Add `Invoke-PhxLs` function — list each shared dir with file count and
   D1-registered/unregistered breakdown
6. Add `Test-PhxSharedPath` helper — returns true if path starts with PhxSharedRoot
7. Add four dispatcher cases to `global:usys` switch block
8. Add four lines to `Show-UsysHelp` under a new "Shared FS" section

**Relevant Context**
- `scripts/usys.ps1` line 455 — `Invoke-UsysClone` (delegate target for import)
- `scripts/usys.ps1` line 1092 — help section insertion point
- `scripts/usys.ps1` line 1162 — main dispatcher switch block
- `$script:PhxSharedRoot` and `$script:PhxSharedDirs` from Sub-Task 1
- Worker API pattern: `GET $PHOENIX_WORKER_URL/clonepool/<hex>` returns 200 if known

---

### Sub-Task 4 — virtio-9p Arguments in Invoke-UsysRun

**Status:** `[ ] pending`

**Intent**
Wire the shared directories into the QEMU launch arguments. Each shared directory
becomes a `-virtfs` argument. A new `-Share` switch on `Invoke-UsysRun` enables
it — default `usys run debian` is unchanged. Uses `ConvertTo-QemuHostPath` from
Sub-Task 1 for every path.

`security_model=mapped-xattr` is used throughout — this is the only model that
works without QEMU running elevated on Windows. `passthrough` requires admin.
That would violate the no-elevation rule and hide an implicit dependency.

**Expected Outcomes**
- `Invoke-UsysRun` gains `[switch]$Share` parameter
- When `-Share` is passed: five `-virtfs local,path=...,mount_tag=...,
  security_model=mapped-xattr,readonly=off` arguments are appended
- Directories that do not exist on F: are skipped with `Write-UsysWarn`
- `usys run debian` without `-Share` is completely unchanged
- `usys run debian --share` now boots Debian with all five directories mounted
- Help text updated: `run debian --share` documented

**Todo List**
1. Read `Invoke-UsysRun` param block (usys.ps1 ~line 782) to confirm current params
2. Add `[switch]$Share` parameter to the param block
3. After snapshot resolution (~line 907), add virtfs argument builder block:
   - Loop over `$script:PhxSharedDirs`
   - For each: check `Test-Path (Join-Path $script:PhxSharedRoot $_)`
   - If present: call `ConvertTo-QemuHostPath`, build virtfs string, append to `$virtfsArgs`
   - If absent: `Write-UsysWarn "Shared dir not found, skipping: $_"`
4. Append `$virtfsArgs` to `$qemuArgs` when `$Share` is set (after net args, before accel args)
5. Add a summary `Write-UsysInfo` line listing mounted shares when `-Share` is active
6. Add `run debian --share` to help and dispatcher

**Relevant Context**
- `scripts/usys.ps1` lines 782-1019 — `Invoke-UsysRun` full body
- `scripts/usys.ps1` lines 976-1004 — QEMU arg construction block to extend
- virtfs arg format: `-virtfs local,path=F:/Phoenix/Desktop,mount_tag=phoenix-desktop,security_model=mapped-xattr,readonly=off`
- `security_model=mapped-xattr` not `passthrough` — passthrough needs admin

---

### Sub-Task 5 — Cloud-init: Auto-mount on Debian

**Status:** `[ ] pending`

**Intent**
Debian must mount the virtio-9p shares on boot automatically.
Cloud-init handles this at first provisioning via `runcmd` and fstab injection.
The fstab entries use `noauto,x-systemd.automount` so a missing virtfs tag
(QEMU launched without `-Share`) never stalls boot.

`plan9-fs-utils` provides the `mount.9p` helper on Debian 12. The kernel
modules `9p`, `9pnet`, `9pnet_virtio` are in-tree — no DKMS.

**Expected Outcomes**
- `tools/poc/debian-seed/user-data` updated (existing 12-line file extended):
  - `packages: [plan9-fs-utils]` section added
  - `runcmd` section added: `mkdir -p /phoenix/{Desktop,...}` for each dir
  - `runcmd` section: one `tee -a /etc/fstab` call per mount_tag
  - fstab format: `phoenix-desktop /phoenix/Desktop 9p trans=virtio,version=9p2000.L,noauto,x-systemd.automount 0 0`
- On first boot with updated seed: all five `/phoenix/*` dirs exist and mount
  if QEMU was launched with `-Share`
- Without `-Share`: boot is unaffected, mount points exist but are empty

**Todo List**
1. Read current `tools/poc/debian-seed/user-data` to know exact current content
2. Add `packages` section: `[plan9-fs-utils]`
3. Add `runcmd` section — order: mkdir first, then fstab entries
4. For each of the five directories, write the fstab line with
   `noauto,x-systemd.automount` — never `auto` or plain `defaults`
5. Keep all existing user/password/sudo/ssh lines verbatim — do not touch them
6. Re-read the result to verify cloud-init YAML is syntactically valid

**Relevant Context**
- `tools/poc/debian-seed/user-data` — current 12-line file
- `tools/poc/debian-seed/meta-data` — unchanged
- Debian 12 `plan9-fs-utils` package: provides `/sbin/mount.9p`
- `noauto,x-systemd.automount` means: systemd mounts on first access,
  skips the tag if not present in QEMU — boot never blocks

---

### Sub-Task 6 — Update PoC README and suite manifest

**Status:** `[ ] pending`

**Intent**
Document the shared filesystem feature from every entry point that a new user
would read first. README gets a full section. The suite manifest gets a
`shared_fs` metadata block so tooling can read the mount table programmatically.

**Expected Outcomes**
- `tools/poc/README.md` gains a "Shared filesystem" section covering:
  - One-time setup: `pwsh tools\poc\setup-shared-fs.ps1`
  - Running with shares: `usys run debian --share`
  - The four PS7 wrappers: `phx-import`, `phx-export`, `phx-sync`, `phx-ls`
  - The rule: all operations against the shared area go through the wrappers
  - Note that `usys run debian` without `--share` is unchanged
- `tools/poc/debian.suite.json` gains `shared_fs` in metadata — array of
  five objects: `{ "windows": "...", "tag": "...", "debian": "..." }`

**Todo List**
1. Read current README.md to find exact insertion point (after "Running" section)
2. Write "Shared filesystem" section in the same style as existing sections
3. Read current debian.suite.json to confirm metadata block structure
4. Add `shared_fs` array to metadata

**Relevant Context**
- `tools/poc/README.md` — existing doc, insert after "Running" section
- `tools/poc/debian.suite.json` — suite manifest metadata block

---

## Implementation Order

```
0a (suite auto-register in intake.sh) — bash-side, self-contained, do first
0b (suite-promote in usys.ps1)        — PS7-side, depends on 0a being done
                                         (0b calls Invoke-UsysClone → 0a hook fires)

1  (path wrapper + PhxSharedRoot)     — must precede 2, 3, 4
2  (bootstrap script)                 — depends on 1
3  (profile wrappers)                 — depends on 1
4  (virtio-9p QEMU args)              — depends on 1
5  (cloud-init)                       — independent of all above
6  (docs)                             — always last
```

0a/0b are self-contained from 1-6 and can be done in a separate pass.
Sub-tasks 2, 3, 4, 5 can be done in any order after Sub-task 1 completes.

---

## Key Technical Decisions

| Decision | Rationale |
|----------|-----------|
| Suite auto-registration on intake (.suite.json) | intake_file() detects extension → places manifest at clonepool/name/.suite.json → immediately runnable. No manual step. |
| suite-promote for any intaked file | Any file already in the pool — script, binary, image — is promoted to a suite in one command. No reinstall. |
| suite-promote re-intakes the generated .suite.json | The manifest is a new artifact. Must go through intake_file() to receive hex + QR + hash baseline. 0b writes to temp, calls Invoke-UsysClone, 0a's hook places it as the named suite automatically. |
| QR status — intake_file() path ✅ | Every file through intake_file() gets USYS:<b58>:HEADER + FOOTER, SHA3-512 + BLAKE2b baseline, D1 record, R2 upload. .suite.json files included. No gap. |
| QR status — suite-promote ✅ (by re-intake) | Generated .suite.json has no QR until passed back through intake. Re-intake via Invoke-UsysClone closes this. |
| Versioning — eviction rule was wrong, fixed in 0a | EVICT_DAYS=3 age-based deletion is a bug. Intended rule: evict only when bumped past 7 versions. 3 days is the rollback window — how long you have to roll back before a version can be displaced. Not a forced deletion timer. Fix: replace age check with count check, MAX_VERSIONS=7. |
| Versioning — latest never evicted ✅ | get_latest_file() guard in evict_old_versions() stays — latest version is always safe regardless of count. |
| Versioning — sidecar clone_history ⚠️ known loose end | write_sidecar_basic always overwrites with single-entry history. Full history in D1 custody chain. Out of scope this plan. |
| Runtime auto-detected from extension | Mirrors detect_filetype() in intake.sh — one canonical map, not two diverging ones. |
| PS7 profile holds wrappers | Every terminal loads them — no session starts without the boundary in place. |
| `phx-` prefix for wrappers | Unambiguous namespace — no collision with `usys` or system commands. |
| Wrappers delegate to Invoke-UsysClone / Invoke-UsysIntake | One intake path, one audit trail — wrappers are enforcement, not reimplementation. |
| `Test-PhxSharedPath` guard in every wrapper | Path outside PhxSharedRoot is rejected before any action. |
| `$script:PhxSharedRoot` in usys.ps1 metadata block | Single canonical drive/path definition — change once, everything updates. |
| `security_model=mapped-xattr` not `passthrough` | passthrough requires QEMU admin on Windows — violates no-elevation rule. |
| `noauto,x-systemd.automount` in fstab | Missing virtfs tag must never stall Debian boot. |
| `-Share` is opt-in | Default `usys run debian` unchanged — no regressions. |
| F: not C: | F: is breach_coms3 user-owned storage, not the system drive. |
| Mount tags are stable strings | Host-side path can change without touching Debian fstab. |
| No WSL. No Wine. No Hyper-V. | Windows hosts, QEMU bridges — dependency declared, visible, auditable. |
