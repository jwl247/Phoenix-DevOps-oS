# deploy — remote Ubuntu deploy scripts

Written 2026-09-12. Verify against current code before trusting a specific line number.

## What it is
`deploy.sh` — promotes `sector3/translator/translator.sh` into systemd on a remote box,
plus rsyncs `sector3/services/` and `dashboard/` there and runs the remote dashboard
deploy script. `deploy/windows/` — `build-windows.bat`, `start-wsl.sh`.

## Dependencies
None beyond `rsync`/`ssh` (remote-ops shell script).

## Commands / entry points
`bash deploy/deploy.sh` — targets a remote Ubuntu box (per root `CLAUDE.md`'s current
build target, `192.168.1.133` at time of writing — verify this hasn't changed).

## Connects to / connected from
- `deploy.sh` → `sector3/translator/translator.sh` (promoted into systemd).
- `deploy.sh` → rsyncs `sector3/services/` to the remote box, then runs
  `sector3/services/deploy-dashboard.sh` remotely.
- `deploy.sh` → also manages a remote copy of `dashboard/`.

## Known issues (verified, not guessed)
None found this pass — not deeply exercised/verified live (no remote box access checked
during this audit). Treat as documented-but-unverified rather than confirmed-working.
