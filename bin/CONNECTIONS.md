# bin — global CLI wrappers

Rewritten 2026-09-29 (Round 2 fix pass: S34OPS-F19/F20/F21/F32/F41). Verify against current
code before trusting a specific line number.

## What it is
11 commands × {bash, `.cmd`} = 22 thin shims (align_dirs, clone, get_distros, intake, jarvis, lol, phoenix-map, run, status, usys + `phoenix-paths.sh`). On Linux `install.sh` copies the bash ones into
`~/.usys/bin` (on PATH); on Windows `install.ps1` copies the `.cmd` ones. Every shim passes
its arguments as arguments (`-File … "$@"` / `%*`, or `bash -c 'exec bash "$0" "$@"'`),
never spliced into a PowerShell or bash command string.
- `bin/usys` — bash → `pwsh -File scripts/usys.ps1 "$@"`; needs PowerShell 7 (no bash engine exists).
- `bin/run` — bash → `pwsh -File scripts/usys.ps1 run "$@"`.
- `bin/clone` — bash, OUT of the pool: `clone <name> [vN] [folder] [--force]` → `sector2/package-handler/intake.sh clone`. `bin/lol`, `clone.cmd`, `usys clone` and `tools/clone.sh` all run this script.
- `bin/intake` — bash, IN to the pool: → `sector2/package-handler/intake.sh` (`intake <file-or-folder>`; also `intake clone …` OUT). Sector 4 vault intake is `usys intake`.
- `bin/status` — bash → root `status.sh`.
- `bin/align_dirs` — bash → `tools/align_dirs.sh`.
- `bin/get_distros` — bash → `tools/get_distros.sh`.
- `usys.cmd`, `run.cmd` — Windows → `pwsh -File scripts/usys.ps1 [run] %*`.
- `clone.cmd` — Windows → Git Bash running `bin/clone` (OUT) with `%*`.
- `bin/lol`, `lol.cmd` — **the `.lol` front door** (2026-10-08/09): a known word (`LOL_WORDS`: intake, suit, get, import, run, open, install, help…) → `bin/usys` / `usys.cmd` → `scripts/usys.ps1`; no word → `help`; anything else is a file to summon → `bin/clone` (= `lol get <name>`). The word list lives in both files — keep them the same. Bare words in PS7 come from the profile hook, not these shims.
- `bin/jarvis`, `jarvis.cmd` — Python: ask Jarvis from any terminal (`--json`, `--no-tools`, `--pbmiii`, `ui`). SSH over the mesh as `jarvis-call` → `sector2/apps/jarvis/jarvis-gate.py`; the HUD Console's JARVIS box runs this same file.
- `bin/phoenix-map`, `phoenix-map.cmd` — Python, read-only: per machine, every component | present | running | where (probes the Linux boxes over the mesh).
- `intake.cmd`, `status.cmd`, `align_dirs.cmd`, `get_distros.cmd` — Windows → Git Bash with the target script and `%*` as positional args.

## Dependencies
None — thin shims. Runtime: PowerShell 7 for `usys`/`run`, Git for Windows'
bash for the `.cmd` bash shims. Line endings pinned by `.gitattributes` (`bin/** eol=lf`,
`bin/*.cmd eol=crlf`).

## Commands / entry points
Each file here IS an entry point once installed on PATH.

## Connects to / connected from
- `bin/usys` → `scripts/usys.ps1`.
- `bin/run` → `scripts/usys.ps1` (`usys run`).
- `bin/clone` → `sector2/package-handler/intake.sh clone` (OUT). `tools/clone.sh` → `bin/clone`.
- `bin/intake` → `sector2/package-handler/intake.sh`.
- `bin/status` → `status.sh`.
- `bin/align_dirs` → `tools/align_dirs.sh`.
- `bin/get_distros` → `tools/get_distros.sh`.
- `install.sh` → `bin/` (Linux install of the bash shims); `install.ps1` → `bin/` (`.cmd` shims).

## Known issues (verified, not guessed)
- On Linux, `usys`/`run` need `pwsh`; `install.sh` warns when it is missing. Whether all of
  `scripts/usys.ps1` works under pwsh on Linux has not been exercised end to end.
- A Windows clone checked out before `.gitattributes` covered `bin/` still has CRLF bash shims
  on disk until the one-time re-checkout is run (S34OPS-F18).
