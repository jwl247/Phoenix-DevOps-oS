# Phoenix: commands and suits from 2026-10-03

Every command from today with what it does and how to use it, plus every suit in the kernel's
closet. The command list is the same as the 2026-10-03 section of `docs/COMMANDS.md`.

## Commands from today

Status: ✅ tested · 🟡 tested in the cloud sandbox, not yet on PBMII · ⏳ waiting on a deploy
or install (the ware is in `tentative-wares/`). Where a command needs a key, it reads it from the
environment (`PHOENIX_AUTH`, `CF_ACCESS_CLIENT_ID`, `CF_ACCESS_CLIENT_SECRET`) and never from the
command line.

### Genie: the Phoenix Universal Kernel in PS7 (`sector1/kernel/genie/genie.ps1`)
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

### Genie, cloud edition: R2 + D1 only, no kernel (`tentative-wares/genie-cloud/genie-cloud.ps1`) ⏳
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

### Intake (IN): package handler `sector2/package-handler/intake.sh`
| Command / setting | What it does | Usage | Status |
|---|---|---|---|
| `intake <file>` | Into the pool. Keys go in a 0600 header file, never on the curl command line | `intake .\tool.py` | ✅ |
| `INTAKE_SAME_NAME_OK=1` | Accepts a different file with an existing name as its next version. Unattended runs refuse without it | `$env:INTAKE_SAME_NAME_OK='1'; intake .\romeo.py` | ✅ |
| `intake help` | Help, offline (no network calls) | `intake help` | ✅ |
| 3.9.0: write check | Before writing, intake asks the worker `/may-write`. A name someone else owns prints `[intake:REFUSED] '<name>': <reason>` and nothing is written | automatic | ⏳ 3.9.0 |
| `sync-standalone.sh` | Publishes this package handler to the public Phoenix-Package_handler repo: only listed files, a do-not-deploy worker name, a secret scan. Dry run by default | `bash sector2/package-handler/sync-standalone.sh` then `... --push` | ✅ |

### packages-worker 3.9.0: member keys (`tentative-wares/package-handler-3.9.0/DEPLOY.md`) ⏳
| Step / route | What it does | Usage |
|---|---|---|
| Migration (first) | Adds the `api_keys` table and `clonepool.owner` | `npx wrangler d1 execute phoenix_dev_db --remote --file migrate-3.9.0-member-keys.sql` |
| Deploy (second) | The worker with member keys | `npx wrangler deploy` (in `sector2/package-handler/worker`) |
| `POST /keys` · `GET /keys` · `POST /keys/<who>/revoke` | Owner key only: issue, list, revoke | `genie key new / list / revoke` |
| `GET /may-write/<hex>` | Can this key write this name? Owner: yes. Member: only new names or its own | used by intake |
| `GET /whoami` | Now also says `who` and the key's scopes | `genie doctor` |

### Dashboard (`tentative-wares/dashboard/INSTALL.md`) ⏳
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

### Phone node (Termux) `sector3/phone-node/` 🟡 (not yet run on a phone)
| Command | What it does | Usage |
|---|---|---|
| `phone-setup.sh` | One-time setup. Keys are typed in hidden. It fetches the client from R2 and SHA3-checks it, only accepts a Tailscale brain address, and starts at boot. `--with-kernel` adds proot Debian + PS7 | `bash phone-setup.sh [--with-kernel]` |
| `lifefirst say` | Sends a check-in to the brain (Helix-I) | `lifefirst say "took my meds"` |
| `lifefirst voice` | Speak a check-in (speech to text) | `lifefirst voice` |
| `lifefirst where` | Location check-in | `lifefirst where` |
| `lifefirst listen` | Stay connected; every reply becomes a notification (`PHOENIX_SPEAK=1` reads it aloud) | `lifefirst listen` |
| `lifefirst flush` | Retry the outbox (check-ins saved while the brain was unreachable) | `lifefirst flush` |
| `lifefirst doctor` | Config + reachability check | `lifefirst doctor` |

### Life First suit (`sector2/apps/lifefirst/suits/lifefirst_checkin.py`)
| Command | What it does | Usage | Status |
|---|---|---|---|
| `genie import lifefirst_checkin.py` | Puts the check-in suit into the live kernel | see Genie | ✅ |
| `verify` | Walks the hash-chained check-in log and reports any tampering | `python lifefirst_checkin.py verify` | 🟡 |
| `LIFEFIRST_MODEL` | Ollama model for replies (default `llama3.2:3b`). If Ollama is down, the reply says `"ai": false` | env var | 🟡 |

### Atlas + checks
| Command | What it does | Usage |
|---|---|---|
| `node sector2/package-handler/parse-connections.js` | Rebuilds the Atlas from every `CONNECTIONS.md` (`--dry-run` = count only) | Run after CONNECTIONS changes. Tonight added `tentative-wares/CONNECTIONS.md` |
| `node tentative-wares/dashboard/slot-transfer.test.js` | 22 folder-bar rule checks | — |
| `python sector1/helix/test_helix_vram.py` | Helix tiers, Dandelion, Strand B: 11 checks | — |
| `node tentative-wares/peer-review/test/sha3.test.mjs` · `webauthn.test.mjs` · `discord.test.mjs` · `python .../schema.test.py` | Peer Review blocks: 12 · 12 · 22 · 47 | — |
| `python portal/test_server.py` | Console summary logic + HTTP guard: 4 checks | — |

## Suits in the closet

Read from the kernel's own code (`sector1/helix-lightning/process_library.py`, `frank_ring.py`,
`helix_suit_override.py`) on 2026-10-03. **`genie closet` shows what is actually loaded on a
machine right now.** A suit whose file is missing on that machine is skipped at boot.

### Core suits: 4 sectors × 4 rings (always registered)
| Sector | Ring 0 | Ring 1 | Ring 2 | Ring 3 |
|---|---|---|---|---|
| 1 Boot/Kernel | `frank3_slot_a` | `frank3_slot_b` | `phoenix_auth` | `concierge` |
| 2 Intake/Package | `intake` | `clone_pool` | `propagator` | `packages_worker` |
| 3 Comms/Network | `romeo` | `juliet` | `dbl_juliet` | `quadengine` |
| 4 Core Engine | `helix` | `freewheeling` | `propcoms` | `conductor` |

**Where they point (`helix_suit_override.py`):**
- `romeo`, `juliet` and `dbl_juliet` point at their real files in `sector3/romeo_juliet/`, and
  `quadengine` at `sector3/quadengine/quadengine.py`.
- `frank3_slot_a/b`, `concierge`, `clone_pool`, `packages_worker`, `helix`, `freewheeling`,
  `propcoms` and `conductor` all point at `sector1/helix/helix_complete_stack.py`.
  - **Known issue S1-F28:** that file has no `run()`, so these suits load but do nothing when
    a stage reaches them.

### System suits (Phoenix OS, always available)
| Suit | Sector / ring | What it does |
|---|---|---|
| `config_centralizer` | 2 / 0 | Config scanner, importer, desktop card writer |
| `integrated_guardian` | 4 / 3 | REALsure security: file guardian, threat response |
| `syncthing_module` | 4 / 2 | Syncthing: Frank clone sync across rings |
| `helix_audit` | 4 / 3 | Helix audit: scans sector files for health (shell, read-only) |

### App suits
| Suit | Sector / ring | What it does |
|---|---|---|
| `warthunder` | 2 / 10 | War Thunder RT interface: telemetry, tactical AI, D1 session logging |
| `x4_foundations` | 2 / 11 | X4 Foundations (GOG): save manager, mod loader, Frank session logging |
| `phoronix` | 2 | Phoronix Test Suite: CPU/memory/I/O/network benchmarks, results to D1 |

### Imported through Genie (custody-verified, hot-loaded)
| Suit | How it got there | What it does |
|---|---|---|
| `lifefirst_checkin` | `genie import lifefirst_checkin.py` | Life First check-in: validate → hash-chained log → stored in Helix → reply from Ollama (`"ai": false` fallback) |
| anything else you import | `genie import <name>` | Only Genie-imported suits answer **addressed stages** (`{"suit": "<name>"}` into Helix-I); core suits never do |

To see the live list with types, families and which were imported: `genie closet`. Green rows
were imported by Genie.
