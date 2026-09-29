# bootstrap — minimal `lol install` bootstrapper

Written 2026-09-12; re-checked 2026-09-29 (Round 2 audit). Verify against current code before trusting a specific line number.

## What it is
`lol-bootstrap.sh` / `lol-bootstrap.ps1` — a separate, minimal installer enabling
`lol install <package>` (writes to `~/.lol`). Documented in `docs/LOL_INSTALLER.md`.
- `lol-bootstrap.sh` — Linux/macOS: writes `~/.lol/bin/lol` and adds it to PATH in shell rc files.
- `lol-bootstrap.ps1` — Windows PowerShell equivalent.

## Dependencies
No packages. Runtime: `bash` + `curl` or `wget` (`lol-bootstrap.sh`), or PowerShell
(`lol-bootstrap.ps1`); both scripts handle a missing downloader. The generated `lol`
pipes the target `install.sh`/`install.ps1` from GitHub straight into the shell (unpinned).

## Commands / entry points
`bash bootstrap/lol-bootstrap.sh` or `bootstrap/lol-bootstrap.ps1` directly — standalone,
user-invoked.

## Connects to / connected from
**None found.** Zero inbound references from anywhere else in the repo (root `install.ps1`/
`install.sh` don't call into this) — appears fully disconnected from the sector1-4/
scripts/tools install flow.

## Known issues (verified, not guessed)
- Given zero inbound references, this reads as either early-stage/experimental or a
  candidate for `archive/` — genuinely unclear which from the code alone. **Ask Jerry**
  before assuming either; don't delete or archive it without confirming.
