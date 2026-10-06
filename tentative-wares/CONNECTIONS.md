# tentative-wares — tested work waiting to graduate

Written 2026-10-03. Every ware here passes its own tests but is not yet "tested, polished,
pro+" for the real tree: nothing is wired into the kernel, Genie, Atlas or any deploy. When a
ware graduates it moves to its home and leaves here.

## What it is
| Ware | Graduates to | State |
|---|---|---|
| `dashboard/` | `dashboard/` | Folder bar across the top (HOME · ROOT · PHOENIX + 6 slots; drag = copy, Shift = move, ✎ rename), CONSOLE/HUD launchers, repo-root fix. Tested in Electron on Linux; 6 Windows checks in `INSTALL.md`. |
| `package-handler-3.9.0/` | `sector2/package-handler/` | packages-worker 3.9.0 member keys + intake.sh asks `/may-write` first. Tested on local wrangler with the real intake.sh. `DEPLOY.md` (migration BEFORE deploy). |
| `genie-cloud/` | `sector1/kernel/genie/` | Genie on R2 + D1 only (no kernel): tour, find, info, cat, clone, verify, intake, custody, key. README written for a second user. |
| `peer-review/` | `sector2/apps/peer-review/` | Forum building blocks: SHA3-512 for Workers, passkeys (WebAuthn), two-way Discord bridge, forum schema with rules in triggers. Worker + website still to build. |

## Dependencies
- dashboard: the dashboard's own npm deps (Electron 28).
- package-handler-3.9.0: wrangler 4.x, D1 `phoenix_dev_db`, R2 `phoenix-clonepool`.
- genie-cloud: PowerShell 7.2+; Git for Windows (bash) for `genie intake`.
- peer-review: Node 18+ for the tests; Python for the SHA3 cross-check and schema tests.

## Commands / entry points
- `node tentative-wares/dashboard/slot-transfer.test.js` — 22 folder-bar rule checks.
- `. tentative-wares/genie-cloud/genie-cloud.ps1` then `genie help`.
- `node tentative-wares/peer-review/test/sha3.test.mjs` / `webauthn.test.mjs` / `discord.test.mjs`; `python tentative-wares/peer-review/test/schema.test.py`.

## Connects to / connected from
- `dashboard/phoenix-apps-launcher.js` → `portal/server.py` (Console) and `hud/bin/*/Hud.exe` (HUD).
- `dashboard/slot-transfer.js` → `~/.phoenix/hud-dropdown-slots.json` (via `hud-layout-backend.js readSlots`).
- `genie-cloud/genie-cloud.ps1` → packages-worker (`/clonepool`, `/search`, `/versions`, `/custody`, `/whoami`, `/keys`) and runs `intake.sh` cloned from the pool.
- `package-handler-3.9.0/intake.sh` → packages-worker `GET /may-write/<hex>` before any write.
- `peer-review/worker/*` → future `phoenix-review` worker (own D1/R2), service binding to packages-worker.

## Known issues (verified, not guessed)
- Pool names are global (hex = file name): a member can't reuse any name the owner has.
- `/packages` and `/deps` list names without filtering sensitive rows for members (bytes and records stay private).
- Not run on Windows yet: ROOT's drive list, the PhoenixPortal task launch, Hud.exe launch, Explorer drops.
