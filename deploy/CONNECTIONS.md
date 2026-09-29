# deploy — local translator promotion script

Rewritten 2026-09-29 (Round 2 fix pass, S34OPS-F23 / CONN-F02) against the actual files.
The 2026-09-12 version described a remote rsync/ssh deploy that `deploy.sh` never did.

## What it is
One small local script, plus a WSL-era folder kept for history.
- `deploy.sh` — 24-line local script: `sudo cp`s `sector3/translator/translator.sh` to `/etc/systemd/system/translator.sh` (sector3) and `/etc/systemd/translator.sh` (sector2 backup), `chmod +x`, prints a check. Runs on the box it is invoked on; no rsync, no ssh, no remote host, no dashboard.
- `windows/` — retired WSL2 concierge-bridge helpers (`build-windows.bat`, `start-wsl.sh`); Phoenix does not use WSL, and the concierge sources they expect live in `sector1/concierge/`. Marked RETIRED in each file's header; not deleted (Jerry's call).

## Dependencies
`bash`, `sudo`, `cp`, `chmod` on the target Linux box. Nothing else.

## Commands / entry points
`bash deploy/deploy.sh` — run on the Linux box itself (needs sudo). It is not a remote deploy.

The remote push that the old version of this file described is
`sector3/services/push-dashboard.ps1` (Windows, scouts then `scp`s `sector3/services/` +
`dashboard/` and runs `deploy-dashboard.sh` on the target) and its older bash twin
`sector3/services/push-dashboard.sh`. See `sector3/CONNECTIONS.md`.

## Connects to / connected from
- `deploy.sh` → `sector3/translator/translator.sh` (copied into systemd dirs).
- `sector3/romeo_juliet/juliet.py` → reads the promoted copy at `/etc/systemd/system/translator.sh` (its `TRANSLATOR_SH`), so `deploy.sh` is what makes juliet's output translation work on a box.
- `deploy/windows/start-wsl.sh` → `sector1/concierge/` (historical: expected `bridge.py` / `linux_concierge.py` next to itself).
- Nothing in the repo calls `deploy.sh`.

## Known issues (verified, not guessed)
- `deploy.sh` puts a shell script in `/etc/systemd/system/`, which is an unusual home
  (systemd does not execute it; only `juliet.py` reads it). No unit in `sector3/services/`
  references it. Moving it (e.g. `/usr/local/lib/phoenix/`) would need juliet.py changed in
  step — left as-is, Jerry's call.
- `deploy/windows/` is kept only for history (WSL is not used, not planned); deleting it is
  Jerry's call.
