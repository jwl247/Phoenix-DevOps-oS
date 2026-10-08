# Phoenix Commands — what each one does (as of 2026-10-07 night)

Global = works from any folder in any terminal. On this PC: `F:\Phoenix\Phoenix-DevOps-oS\bin`,
`...\scripts` and `C:\Users\jwlef\.usys\bin` are on PATH (`.usys\bin` = forwarders that run the repo's
`bin\` copies, so they cannot drift — 2026-10-07).
Status: ✅ tested working · ❌ tested broken · ⚠ works but wrong/confusing · — not tested yet.
2026-10-03: the Sector 2 pool commands were walked end to end against the real packages-worker
(3.8.1, run locally with a D1 built from `worker/schema-d1.sql` and a local R2). ✅ below = passed that walk.
2026-10-07 (Round 4 command walk): `clone.cmd`, `lol.cmd`, the repo `intake.cmd`, `usys clone`
(OUT) and `usys pull -Destination` were run on Windows and work.

## The two directions (the rule)
- **IN — `intake`**: a file/folder goes INTO the clone pool (hex, sidecar, R2 bytes, D1 custody + version).
- **OUT — `clone`**: a file/folder comes OUT of the pool into a directory (latest or `vN`, checked against D1).
  Original design: `sector1/grub/usys.sh` — `usys clone <name> <dest>` = "clone with full history".
  Since 2026-10-02/10-06 every command follows this rule: `clone`, `usys clone`, `lol` and `bin/clone`
  are OUT (all run `bin/clone` → `intake.sh clone`); `tools/clone.sh` is a forwarder to `bin/clone`.

## Clone pool — IN
| Command | Does | Status |
|---|---|---|
| `intake <file> [backend] [notes]` | File into the pool (PS7: `scripts\intake.ps1` → `intake.sh`). Version comes from the D1 ledger; a DIFFERENT file whose name is taken gets a longer name (`folder/name`, then `parent/folder/name`) — never refused or merged (2026-10-07) | ✅ |
| `intake <folder>/` | Whole folder into the pool, with preview. Each re-intake is a new snapshot (was: stuck at v1, overwritten) | ✅ |
| `intake backend <pkg> <be> <ver>` | Register a package installed by a backend (winget, apt…) | ✅ |
| `intake.cmd <file>` (repo `bin\intake.cmd`) | Same as `intake`, from CMD | ✅ 2026-10-07 |
| `usys intake <file>` / `usys intake dir <path>` | Sector 4 **vault** intake (`sector4/intake/intake.sh`, TAV / breach_coms4) — a different pipeline from the Sector 2 pool | — |
| `usys download <url> [-OutFile p] [-NoIntake]` | Download, then intake | — |
| `usys watch start [-Auto] [-Path d]` / `stop` / `pending` / `status` | Watch Downloads (or a folder) and intake new files | — |
| `usys fs-import <path>` / `fs-sync <dir>` (`phx-import`, `phx-sync`) | Shared-FS file/folder into the pool | — |
| `scripts/hsf-intake.sh` | Unattended intake (no prompts) | — |

## Clone pool — OUT (clone to a directory)
| Command | Does | Status |
|---|---|---|
| `intake clone <file>` (bash `intake.sh`) | Latest version into the current folder; reports the ledger version | ✅ |
| `intake clone <file> vN` | Version N into the current folder | ✅ |
| `intake clone <folder>` / `<folder>/` / `<folder> vN` | Folder snapshot into the current folder (trailing `/` was "not found") | ✅ |
| `intake clone <file>` (shim `bin/intake` / `intake.cmd`) | Same as above via the shim; a dead `PHOENIX_INTAKE` now falls back to the repo copy | ✅ bash · ✅ .cmd 2026-10-07 |
| `clone <name> [vN] [folder] [--force]` | Pool file/folder into `[folder]` (default: here). `bin/clone` (bash) → `intake.sh clone`; `clone.cmd` runs the same script through Git Bash; refuses to overwrite a working file without `--force` | ✅ bash · ✅ .cmd 2026-10-07 |
| `usys clone <name> [vN] [folder]` | Same engine as `clone` (`Invoke-UsysCloneOut` → `bin/clone`) | ✅ 2026-10-07 |
| `lol <name> [vN] [--force]` | Pool file into the current folder — a wrapper over `clone` (overwrite guard; `lol.cmd` no longer builds a PowerShell script from the name) | ✅ bash · ✅ .cmd 2026-10-07 |
| `usys open <name>.lol` | Pool file into the current folder, SHA3-checked vs D1 (when no local file of that name) | ✅ |
| `usys pull <name> -Destination <dir>` | Pool item into `<dir>` (created if missing), SHA3-checked vs D1 | ✅ 2026-10-07 |
| `usys fs-export <name> <dir>` (`phx-export`) | Pool item into a shared-FS dir | — |

## Search / status
| Command | Does | Status |
|---|---|---|
| `usys search <query>` | Search clone pool + catalog | — |
| `intake status` | Clone pool summary | ✅ |
| `usys status` / `status` | Repo sectors, engines, env, catalog | — |
| `usys doctor` | Health check of the setup | — |
| `usys fs-ls [dir]` (`phx-ls`) | Shared dirs + pool registration | — |
| `usys version` / `usys help` | Version / help | — |

## Suites (run from the pool, no install)
| Command | Does | Status |
|---|---|---|
| `usys run <name>` / `run <name>` | Run a suite from the pool (gated: trust-stamp first) | — |
| `usys run <name> --unverified` | Run an unstamped suite anyway | — |
| `usys suite-promote <name> [-Desc x]` | Wrap an intaked file as a runnable suite | — |
| `usys suite-list` / `list-suites` | List runnable suites | — |
| `usys suite-trust <name>[@ver]` | Trust-stamp a suite on this machine | — |
| `usys load …` | Load a suite (see `usys help`) | — |

## Distros (Linux VMs via QEMU — no WSL)
| Command | Does |
|---|---|
| `usys distro list` / `fetch-qemu` / `intake-qemu` | Registered distros / how to get QEMU / intake QEMU into the pool |
| `usys run debian` / `ubuntu` `[--accel tcg\|hyperv] [--share]` | Boot a VM (`--share` mounts F:\Phoenix\* at /phoenix/*) |
| `get_distros <dest> --yes` | **Downloads** ~10 Linux ISOs (tens of GB, `wget`) into `<dest>` for Ventoy. Without both `<dest>` and `--yes` it only prints usage and downloads nothing |

## Setup / maintenance
| Command | Does |
|---|---|
| `usys init` | First-time setup (dirs, config, PATH) |
| `usys path-register` | Add usys to user PATH |
| `usys fs-init` | One-time shared-FS setup |
| `align_dirs` | Keep path parity between the Debian VM and bare metal |
| `intake prune` | Evict versions beyond the keep count; T1→T4 tier rotation (✅ 2026-10-03) |
| `node sector2/package-handler/parse-connections.js [--dry-run\|--rebuild]` | Refresh the Atlas (also runs on commit when a CONNECTIONS.md changes) |
| `usys <file>.py/.sh/.ps1/.js/.qcow2…` | Run/open a file by extension |

## Fixed (Jerry 2026-10-02: names must do what they say, globally)
- `clone <name> [vN] [folder]` and `usys clone` are **OUT**; IN is `intake` (done 10-02/10-06, docs 10-07).
- `usys pull -Destination` is honoured (run 2026-10-07).
- Shims fall back to the repo `intake.sh` when `PHOENIX_INTAKE` is dead (2026-10-03).
- `intake clone` reports the D1 ledger's version number; intake numbers new versions from the ledger (2026-10-03).

## Maintenance note
- Publish: `bash sector2/package-handler/sync-standalone.sh [--push]` keeps the public Phoenix-Package_handler repo in sync with this copy (allowlist, do-not-deploy worker name, secret scan).

---

# Added 2026-10-03: every command from today, with what it does and how to use it

Status: ✅ tested · 🟡 tested in the cloud sandbox, not yet on PBMII · ⏳ waiting on a deploy
or install (the ware is in `tentative-wares/`). Where a command needs a key, it reads it from the
environment (`PHOENIX_AUTH`, `CF_ACCESS_CLIENT_ID`, `CF_ACCESS_CLIENT_SECRET`) and never from the
command line.

## Genie: the Phoenix Universal Kernel in PS7 (`sector1/kernel/genie/genie.ps1`)
Load once per window with `. F:\Phoenix\Phoenix-DevOps-oS\sector1\kernel\genie\genie.ps1`, or run
`genie profile` and it loads in every PS7 window.

| Command | What it does | Usage | Status |
|---|---|---|---|
| `genie up` | Boots the kernel in the background (Frank5 → closet → FrankSpawn → Helix-I 7701-7704 → Helix-E 7805-7808, status on :8765, control socket on :8766) | `genie up` | ✅ |
| `genie down` | Stops the kernel Genie started. It never touches one it didn't start | `genie down` | ✅ |
| `genie restart` | Down, then up. Use it after changing env vars or kernel code | `genie restart` | ✅ |
| `genie status` | Kernel state, Helix ports, closet, Helix tiers and Dandelion, paging pressure and Doppelgangers | `genie status` | ✅ |
| `genie log` | Last lines of the kernel log | `genie log -Lines 80` | ✅ |
| `genie doctor` | Checks Python, the kernel file, SHA3, keys, the worker and the control socket | `genie doctor` | ✅ |
| `genie find` | Searches the clonepool (D1) | `genie find romeo` | ✅ |
| `genie clone` | OUT: pulls from R2 and checks SHA3-512 against D1 before anything is written | `genie clone romeo.py -To C:\work` (`-Force` = accept a row with no baseline) | ✅ |
| `genie import` | Clone + verify + hot-load into the running kernel's closet as a suit | `genie import lifefirst_checkin.py [-Sector 2] [-Family user] [-Type PYTHON] [-Name s] [-Write]` | ✅ |
| `genie closet` | Every suit in the live closet; green = imported by Genie | `genie closet` | ✅ |
| `genie custody` | Read-only audit of rows with no SHA3 baseline. Writes a CSV report plus a reviewed re-intake script to `~\.phoenix\genie\`. **Fixed tonight: it now reads every row, not just the newest 100** | `genie custody` | ✅ (fix 🟡) |
| `genie profile` | Adds Genie to your PS7 profile, auto-booting the kernel (`$env:PHOENIX_GENIE_AUTOUP='0'` to skip the boot) | `genie profile` | ✅ |

**Settings Genie and the kernel read:**
- `PHOENIX_WORKER_URL` · `PHOENIX_GENIE_HOME` · `PHOENIX_GENIE_PORT` (8766) · `PHOENIX_STATUS_PORT` (8765)
- `PHOENIX_TREE_PORT` / `PHOENIX_CLONE_PORT`: Genie sets 7713 / 7714 so they don't collide with Helix-I
- `HELIX_VRAM_STRAND_B`: folder for Strand B; put it on the big fast drive
- `PHOENIX_HELIX_B_MAX_MB`: cap on how far Doppelgangers can grow Strand B
- `HELIX_SOCKET_TOKEN` + `HELIX_I_BIND` / `HELIX_E_BIND`: open Helix to the Tailscale mesh. Without a token the kernel stays on 127.0.0.1

## Genie, cloud edition: R2 + D1 only, no kernel (`tentative-wares/genie-cloud/genie-cloud.ps1`) ⏳
Load it with `. C:\Phoenix\genie-cloud.ps1`. It needs only PS7, plus Git for Windows for `intake`.
The setup for a second person is in its `README.md`.

| Command | What it does | Usage | Status |
|---|---|---|---|
| `genie tour` | Guided walk on real files: find → info → cat → clone → verify → change one byte and verify again. Writes nothing to Phoenix | `genie tour` (`-Force` = no pauses) | 🟡 |
| `genie doctor` | Keys, worker, D1 row count, SHA3 self-test, and who you're signed in as | `genie doctor` | 🟡 |
| `genie find` | Every matching record (not capped at 20), plus the glossary | `genie find kid` | 🟡 |
| `genie info` | The record, its fingerprint, the version ledger and its custody receipts | `genie info romeo.py` | 🟡 |
| `genie cat` | Shows the code with line numbers, but only if its SHA3 matches | `genie cat romeo.py` | 🟡 |
| `genie clone` | OUT, SHA3-checked before writing. A duplicate name is refused, with the hex_ids to pick from | `genie clone romeo.py -To C:\work` | 🟡 |
| `genie verify` | Is my local file byte-identical to custody? | `genie verify .\romeo.py [romeo.py]` | 🟡 |
| `genie intake setup` | First time on a machine: fetches `intake.sh` from the pool, SHA3-checked | `genie intake setup` | 🟡 |
| `genie intake` | IN: runs intake for each file or folder. It re-checks `intake.sh` against custody first | `genie intake .\my_tool.py .\proj\` | 🟡 |
| `genie custody` | The same audit as above. `-Root` points it at local copies to compare | `genie custody -Root F:\Phoenix\Phoenix-DevOps-oS` | 🟡 |
| `genie key list` | Owner only: every person's key and when it was last used | `genie key list` | ⏳ 3.9.0 |
| `genie key new` | Owner only: issues one key per person, shown once | `genie key new son` (`-Scopes read` = read-only) | ⏳ 3.9.0 |
| `genie key revoke` | Owner only: that key stops working on its next request | `genie key revoke son` | ⏳ 3.9.0 |

## Intake (IN): package handler `sector2/package-handler/intake.sh`
| Command / setting | What it does | Usage | Status |
|---|---|---|---|
| `intake <file>` | Into the pool. Keys go in a 0600 header file, never on the curl command line | `intake .\tool.py` | ✅ |
| `INTAKE_SAME_NAME_OK=1` | Accepts a different file with an existing name as its next version. Unattended runs refuse without it | `$env:INTAKE_SAME_NAME_OK='1'; intake .\romeo.py` | ✅ |
| `intake help` | Help, offline (no network calls) | `intake help` | ✅ |
| 3.9.0: write check | Before writing, intake asks the worker `/may-write`. A name someone else owns prints `[intake:REFUSED] '<name>': <reason>` and nothing is written | automatic | ⏳ 3.9.0 |
| `sync-standalone.sh` | Publishes this package handler to the public Phoenix-Package_handler repo: only listed files, a do-not-deploy worker name, a secret scan. Dry run by default | `bash sector2/package-handler/sync-standalone.sh` then `... --push` | ✅ |

## packages-worker 3.9.0: member keys (`tentative-wares/package-handler-3.9.0/DEPLOY.md`) ⏳
| Step / route | What it does | Usage |
|---|---|---|
| Migration (first) | Adds the `api_keys` table and `clonepool.owner` | `npx wrangler d1 execute phoenix_dev_db --remote --file migrate-3.9.0-member-keys.sql` |
| Deploy (second) | The worker with member keys | `npx wrangler deploy` (in `sector2/package-handler/worker`) |
| `POST /keys` · `GET /keys` · `POST /keys/<who>/revoke` | Owner key only: issue, list, revoke | `genie key new / list / revoke` |
| `GET /may-write/<hex>` | Can this key write this name? Owner: yes. Member: only new names or its own | used by intake |
| `GET /whoami` | Now also says `who` and the key's scopes | `genie doctor` |

## Dashboard (`tentative-wares/dashboard/INSTALL.md`) ⏳
| Control | What it does | Use |
|---|---|---|
| Folder bar: HOME · ROOT · PHOENIX + 6 slots | Each drops down to every entry in its folder, hidden files included, with sizes. ROOT = every drive | Click the name to open or close it |
| Click a folder / `↑` | Go into a folder / up one | One click |
| Click a file / Ctrl-click | Select one / add to the selection | One click |
| Drag (plain) | **Copy** to another dropdown or onto a folder row. The original stays | Drag and drop |
| Shift-drag | **Move**. On another drive: copy, SHA-256 check, then remove the original | Hold Shift while dropping |
| `✎` | Rename in place. Enter saves, Esc cancels, an existing name is refused | Hover a row → ✎ |
| `↗` | Open a file with its app | Hover a file → ↗ |
| Drop from Explorer | Copies into that folder. Dropped on an empty `+` slot, a folder becomes that slot | Drag from Explorer |
| `◉` / `×` on a slot | Make it the working directory (shell + Claude follow it) / clear the slot (the folder is untouched) | Click |
| CONSOLE button | Starts `portal/server.py` if it's down (PhoenixPortal task, or else pythonw), then opens it in a locked window | Click |
| HUD button | Starts the newest `Hud.exe`; warns if the build is older than its source | Click |
| Protected | Never overwrites, never moves out of `breach_coms4`, never writes into or moves the Windows / Program Files / ProgramData folders | — |

## Phone node (Termux) `sector3/phone-node/` 🟡 (not yet run on a phone)
| Command | What it does | Usage |
|---|---|---|
| `phone-setup.sh` | One-time setup. Keys are typed in hidden. It fetches the client from R2 and SHA3-checks it, only accepts a Tailscale brain address, and starts at boot. `--with-kernel` adds proot Debian + PS7 | `bash phone-setup.sh [--with-kernel]` |
| `lifefirst say` | Sends a check-in to the brain (Helix-I) | `lifefirst say "took my meds"` |
| `lifefirst voice` | Speak a check-in (speech to text) | `lifefirst voice` |
| `lifefirst where` | Location check-in | `lifefirst where` |
| `lifefirst listen` | Stay connected; every reply becomes a notification (`PHOENIX_SPEAK=1` reads it aloud) | `lifefirst listen` |
| `lifefirst flush` | Retry the outbox (check-ins saved while the brain was unreachable) | `lifefirst flush` |
| `lifefirst doctor` | Config + reachability check | `lifefirst doctor` |

## Life First suit (`sector2/apps/lifefirst/suits/lifefirst_checkin.py`)
| Command | What it does | Usage | Status |
|---|---|---|---|
| `genie import lifefirst_checkin.py` | Puts the check-in suit into the live kernel | see Genie | ✅ |
| `verify` | Walks the hash-chained check-in log and reports any tampering | `python lifefirst_checkin.py verify` | 🟡 |
| `LIFEFIRST_MODEL` | Ollama model for replies (default `llama3.2:3b`). If Ollama is down, the reply says `"ai": false` | env var | 🟡 |

## Atlas + checks
| Command | What it does | Usage |
|---|---|---|
| `node sector2/package-handler/parse-connections.js` | Rebuilds the Atlas from every `CONNECTIONS.md` (`--dry-run` = count only) | Run after CONNECTIONS changes. Tonight added `tentative-wares/CONNECTIONS.md` |
| `node tentative-wares/dashboard/slot-transfer.test.js` | 22 folder-bar rule checks | — |
| `python sector1/helix/test_helix_vram.py` | Helix tiers, Dandelion, Strand B: 11 checks | — |
| `node tentative-wares/peer-review/test/sha3.test.mjs` · `webauthn.test.mjs` · `discord.test.mjs` · `python .../schema.test.py` | Peer Review blocks: 12 · 12 · 22 · 47 | — |
| `python portal/test_server.py` | Console summary logic + HTTP guard: 4 checks | — |

## Added 2026-10-07 (night)
| Command | Does | Status |
|---|---|---|
| `bash scripts/pool-bundles.sh [sector1..4 \| system]` | The repo section of the pool: `phoenix-sector1..4.tar` + `phoenix-system.tar` (the complete Phoenix). Same files = same bytes, so a rerun is "unchanged", not a new version | ✅ |
| `python scripts/heal_check.py --box pbmiii \| pbmii` | Healing step 1, CHECK ONLY: what's deployed vs the repo vs the pool; reference + drift report in `docs/heal/`. Changes nothing | ✅ pbmiii |
| HUD tray **Suit look-up…** / Console **SUITS** | Find a suit by name or what it does, read its code (custody-checked), Import (= `genie import`) | ✅ |
| HUD tray **Hide the eye / Show the eye** | Eye out of the way; it also hides by itself behind full-screen windows | ✅ |
| `python sector1/helix/bench_three.py [--only x] [--hold s] [--check]` | Storage bench: Frank, New Horizon, OG, Freewheeling, OG-original — same test, every answer checked | ✅ |
| `python sector1/helix/bench_routers.py [--only x] [--check]` | Router bench: Capulet, Slim, FrankenHelix — msgs/s, delay, lost | ✅ |
| `python sector4/ring/bench_ring.py` | Ring baseline: one ball at a time + a burst, in a scratch home (never a breach drive) | ✅ |
| `ssh pbm-compaq` | The Compaq (user a; same key as `pb3`) | ✅ |
