# sector2 — Intake authority, package handler, clone pool, apps

Written 2026-09-12; corrected 2026-09-29 against the Round 2 functionality audit
(`docs/compliance/pentest/2026-09-28-round2-functionality.md`, S2CORE + CONN sections);
brought up to date 2026-09-30 with the clone-pool work since (packages-worker 3.6.0 at the time;
**packages-worker 2026-10-07: live 3.8.0 (`/health`); repo 3.8.2 not deployed (Jerry deploys)**;
version backfill, pool-tidy, intake.sh 1.7.0, the road-test data plane).
Verify against current code before trusting a specific line number.

## What it is
The busiest sector: the canonical intake/clonepool pipeline, plus every Entourage app
(LifeFirst, Office, ScriptForge, the dormant lifefirst-android), plus the UnitedSys CLI
project and Frank's file-orchestration code.
- `package-handler/` — **the canonical intake pipeline** (see below). Also holds the standalone-product installers (install.sh, install.ps1, uninstall.ps1), which are not the monorepo dev-box setup.
- `package-handler/intake.sh` — intake/clone/prune CLI (version 1.7.0): hex, sidecar, T1-T4 pool, D1 custody, R2 current + per-version bytes, SHA3-512/BLAKE2b gate. Added 2026-09-29: files over ~95 MB go to R2 in 64 MB pieces through the worker's multipart routes (before that, anything over 100 MB was never uploaded); a version whose bytes are already in R2 is copied inside R2 instead of uploaded again; `intake clone` of a directory works on a machine with no local copy (pulled from R2, checked against D1); a local copy that is out-of-date against D1 is refreshed from R2 on clone (Phoenix stays the authority); directory files are pulled and verified 8 at a time (`INTAKE_PARALLEL`); a re-intaked directory keeps its unchanged files in the snapshot and manifest.
- `package-handler/worker/` — packages-worker (D1 `phoenix_dev_db` + R2 `phoenix-clonepool`): clonepool, custody, glossary, versions, deps, connections (Atlas), peer review, `/stats`, and as of 2026-10-01 the `/player` node session lifecycle routes. **Live 3.8.0 per `/health` (2026-10-07); repo `worker/index.js` is 3.8.2, not deployed (Jerry deploys).** Version 3.6.0 added the `/clonepool/<key>/mpu` multipart routes and `POST /clonepool/<key>/copy`; deployed 2026-10-01 (Version ID `324b61b9-f55f-493a-920f-90978df0aff1`) with the `/player/:uid/*` block. R2 layout for player data: `players/{uid}/state.json`, `players/{uid}/hardware.json`, `players/{uid}/sidecars/{hash}.sidecar.json`, `players/{uid}/blobs/{hash}`. All `/player` routes gated by `PHOENIX_AUTH` bearer token. Canonical deploy directory: `sector2/package-handler/worker/` — `sector3/workers/packages-worker/` is an intentionally bricked stale copy (its `main` points at a nonexistent file to trip any accidental deploy).
- `package-handler/worker/schema-d1.sql` — the custody database's structure only, no data (50 tables, 35 indexes, exported from phoenix_dev_db 2026-09-29). Used to stand up a fresh data plane on another Cloudflare account; re-export after any live schema change so it stays the truth.
- `apps/lifefirst/suits/lifefirst_checkin.py` — Life First's first kernel suit (2026-10-03). An addressed stage `{"suit":"lifefirst_checkin","who","type","text"[,lat,lon]}` is validated, appended to `~/.phoenix/lifefirst/checkins.jsonl` with a SHA3-512 hash chain (`python lifefirst_checkin.py verify` walks it; a hand-edit shows as broken), stored in the userspace Helix, and answered through Ollama-local (`LIFEFIRST_MODEL`, default llama3.2:3b). Ollama down/model missing → still logged, plain acknowledgement with `"ai": false` and the reason. Reaches the kernel by intake → `genie import lifefirst_checkin.py`.
- `package-handler/backfill-versions.py` — one-time repair: finds the exact bytes of every old version that had a D1 `versions` row but no bytes in R2 (searches the local clone pools on D:, E:, F: and every blob in this repo's git history, LF and CRLF), and sends only bytes whose SHA3-512 matches D1. `python backfill-versions.py` = dry run, `--upload` = send. Needs `PHOENIX_WORKER_URL`, `PHOENIX_AUTH`, `CF_ACCESS_CLIENT_ID`, `CF_ACCESS_CLIENT_SECRET`. Run 2026-09-29: 408 version keys restored.
- `package-handler/pool-tidy.py` — keeps the local clone pool small: R2 is the home, a local copy stays only if it is pinned (e.g. a VM image a program must read from disk). `python pool-tidy.py audit` (what would go and why), `tidy [--apply]` (removes local copies only after proving their exact bytes are in R2; dry run without `--apply`), `pin|unpin <name|hex>`, `pins`. Anything it cannot prove is kept. Only reads from the worker; deletes only local files.
- `package-handler/parse-connections.js` — Atlas backfill: every CONNECTIONS.md to the D1 `connections` table (+ `connections-seed.json`).
- `package-handler/peer-review/` — peer-review schema (`schema.sql` is the truth; `PEER_REVIEW.md` is design intent).
- `apps/lifefirst/` — **retired PHP fossil** (hardcoded creds; never run its setup/deploy scripts). The live Life First backend is the `lifefirst-mcp` Cloudflare Worker at `https://lifefirst-mcp.phoenix-jwl.workers.dev` (not in this repo; Anthropic managed-agent MCP server for agent `agent_016KkiogQouh7byVcSjU6Q2j` in env `env_01M6JT8FZ39zGUJaWR2p6PwS`); `meds-worker/` and `laurie/` live here.
- `apps/lifefirst-android/` — dormant Android app (`HIBERNATION_STATUS.md` present).
- `apps/office/` — tamper-evident document app. Usable end-to-end; only Module 4
  (LibreOffice format-following) is unbuilt, not on the critical path.
- `apps/scriptforge/` — sandboxed code-widget Electron app.
- `frank/` — dormant (nothing runs it; re-checked 2026-09-30). Frank3's older Python side: `frank_save.py` (Office save scheduler: picks a drive by pressure with `best_drive()`/`drive_pressure()` across `/mnt/d` to `/mnt/g`, writes to the vault CLONEPOOL), `frank_http.py` (small HTTP bridge on port 7347: `/status`, `/save`, `/catalog`), `frank_client.js` (browser-side poller for that bridge, meant for Office), `frank_helix.py` (RAM-pressure daemon, L1/L2/L3 tiers at 60/75/88 %, ZMQ). Debian-VM-shaped, no working wiring on Windows; keep or retire is Jerry's call (S2CORE-F38). The road test copies the folder to worker boxes as files, but nothing there runs it.
- `propagator/` — dormant (nothing runs it). `propagator.py` is a signal router meant to pass messages down the COM4 to COM1 chain and out to every target in `dispatch.json` (vault, sqlite, D1, Frank3, peer, Windows); `propcoms.sh` is the shell side (`propcoms.sh relay` is a stub). Same audit, same open call (S2CORE-F38).
- `ring0/` — dormant (nothing runs it). `frankenhelix.py` is the original Frank bridge: a ring0 listener with COM1-4 prefetch routing over the four physical breach_coms drives at `/media/<user>/breach_coms1-4` (needs zmq/psutil). Same open call.
- `apps/game/` — `COMPANION_VOICE.md` only: a draft of the game companion's voice and persona (2026-09-12, Monster Phoenix era). Notes, no code. The game is now **Sacrifice** and its code lives in `game/` at the repo root (see `game/CONNECTIONS.md`): client engine Godot 4.7.2 (no client in the repo yet), our own OpenStreetMap PMTiles in R2 `sacrifice-maps` served by the live `sacrifice-worker`. The old Maptiler / Babylon.js / Electron stack is gone (MapTiler dropped 2026-10-05). Corrected 2026-10-07 (CONN-F25).
- `apps/jarvis/` — Jarvis, the local-AI tier: OpenJarvis on the llama.cpp `llama-server` engine on pbmIII (`install-jarvis.sh`, `pins.sha256`, `phoenix-llm.service`, `openjarvis.service`, `config.toml`, `jarvis_identity.md`). The only door in from off the box is `jarvis-gate.py`, run as the SSH forced command for user `jarvis-call` (mesh `10.42.0.0/16` only, no shell, one JSON ask per call, journaled as `jarvis-gate`); both services are localhost-only with a key. `suits/jarvis.py` is the Genie suit that asks it over the mesh (`jarvis-call@10.42.0.10`, pinned host key). **Ollama REMOVED 2026-10-07** (it phoned home). The engine swap on pbmIII was still in flight 2026-10-07 (see `docs/history/HANDOFF-2026-10-07.md`); not re-verified live by this edit. Leftover: `suits/jarvis.py`'s docstring still says "Ollama llama3.2:3b".
- `apps/security/` — Phoenix Security, the file motion sensor (`README.md`, `install-security.sh` / `.ps1`, `suits/security.py`): metadata sweeps every 5 min on pbmIII, awslh and PBMII, SHA3-512 of what moved, hash-chained `motion.jsonl`, alerts on sensitive paths, outbox for intake. Leftover: its `summary` verb still calls Ollama (`OLLAMA_HOST`, default `127.0.0.1:11434`) and falls back to the raw alert list when Ollama is not there; on boxes where Ollama has been removed (2026-10-07 on) that is every call until it is pointed at llama-server.
- `assets/` — `phoenix-logo.png`. Nothing in the code points at this copy (the dashboard and phoenix-office each use their own `assets/phoenix-logo.png`).
- `unitedsys/` — a separate CLI project (`bin/us`, `bin/us.ps1`, `core/*.py`, `db/schema.sql`, `manifests/*.toml`). Confirmed 2026-09-28: a different implementation from `scripts/usys.ps1` (different DB, different verbs); neither supersedes the other.

## Node session package — `scripts/node_session/`
Three-file Frank-managed importable package for the player login/logout ring (added 2026-10-01).
Stdlib urllib only — zero external dependencies. Runs on Python 3.8+ on any platform (Windows, Linux, macOS, Android/Termux).

- `scripts/node_session/__init__.py` — public API: `login()`, `logout()`, `clone_to()`, `content_hash`, `verify_hash`, `make_sidecar`, `Frank`
- `scripts/node_session/frank.py` — `Frank` class. Ring lifecycle: born → mount → run → sync → die. Holds `ingress_url` (pull) and `egress_url` (push) separately (GDD §2.2 DMZ-per-player). In-memory ledger cleared on `die()` — Frank leaves no trace.
- `scripts/node_session/session.py` — all HTTP calls. `pull()` via ingress tunnel, `push()` via egress tunnel, `clone_to()` for mesh replication (push cached blobs/sidecars to a destination node). Dual-hash: SHA3-256 XOR BLAKE2b. Hash = filename = D1 key = R2 object key ("a sum of its whole"). Sidecars travel. Files never travel unless a node genuinely lacks them. Blob hash verified on both pull (before caching) and push (before sending). Corrupt data is never cached or forwarded.
- `scripts/test_node_session.py` — smoke test: full login → mutate state → write blob+sidecar → logout/push → verify login (confirms R2 round-trip). Reads `PHOENIX_AUTH` from env. Target: `https://packages-worker.phoenix-jwl.workers.dev`.

Usage:
```python
from node_session import login, logout, clone_to
ctx = login(uid="player-uid", ingress_url="...", egress_url="...", auth_token="...")
# session runs, ctx["state"] mutates freely
ok = logout(ctx, wipe_local=True)
# mesh replication
result = clone_to(ctx, destination_url="https://other-node-worker.dev")
```

Node design principle: must be light enough to run H.L.K-10 alongside the game. Node footprint: Python 3 (stdlib), `node_session/` (3 files), `helix_complete_stack.py` (1 file). Zero pip installs.

## Phoenix mesh — Tailscale
WireGuard was retired (too fragile). Tailscale is the sole mesh VPN as of 2026-10-01.
Tailscale hostnames to be confirmed with `tailscale status` on each machine.
Known nodes:
- `precision.phx` / PBMII — i7/32GB dev machine, project root at `F:\Phoenix\Phoenix-DevOps-oS`
- `compaq.phx` — Compaq 2600, stable Phoenix node, primary smoke-test target
- `pbm3.phx` — old HP, ethernet-connected to PBMII via Windows ICS (192.168.137.x), offline as of 2026-10-01
- Samsung Galaxy S23 FE — Termux node, `helix-env` Python 3.13.12 venv at `~/downloads/helix-env`

The worker reads this table into `/meta/atlas` → `nodes` (session bootstrap). Keep it current here — nothing else holds these.

| Node | Tailscale IP | OS | Role |
|---|---|---|---|
| pbmii | 100.72.7.92 | windows | primary dev / PBMII (`precision.phx`) |
| pbm-compaq | 100.94.101.53 | linux | ground forces node / Compaq (`compaq.phx`) |
| pbm3 | — | linux | old HP on the direct cable, offline since 2026-10-01 |
| galaxy-s23fe | — | android | Termux node |

## Trip-wires
Hard rules for any session touching this sector. The worker reads these bullets into `/meta/atlas` → `trip_wires`.
- NEVER deploy from `sector3/workers/packages-worker/` — intentionally bricked (unauthenticated routes, `main` points at a nonexistent file)
- ALL packages-worker routes are gated by `Authorization: Bearer <PHOENIX_AUTH>`
- Canonical packages-worker source: `sector2/package-handler/worker/index.js`
- `PHOENIX_AUTH` is a Windows user env var — never `wrangler secret put PHOENIX_AUTH` directly; use `rotate-phoenix-auth.sh`
- R2 access for nodes routes through packages-worker only — nodes never hold direct R2 credentials
- Tailscale is the sole mesh VPN — WireGuard retired 2026-10-01
- No vendor model names hardcoded anywhere
- The Atlas is fed by intake, not by hand: edit a `CONNECTIONS.md`, commit (the hook runs `parse-connections.js`) or run it yourself — never PUT `/meta/atlas` or POST `/connections` by hand

## Dependencies
- `package-handler/worker/wrangler.jsonc` — D1 `PHOENIX_DB`→`phoenix_dev_db` and R2
  `CLONEPOOL_BUCKET`→`phoenix-clonepool`. Never `wrangler secret put PHOENIX_AUTH`
  directly here — use `rotate-phoenix-auth.sh`.
- `package-handler/r2-worker/` — the retired `phoenix-clonepool-r2` worker (retired
  2026-09-21, deleted from Cloudflare 2026-09-25). Its `wrangler.jsonc` is still intact, so a
  `wrangler deploy` there would recreate it against the real bucket — don't; removal is
  Jerry's call (S2CORE-F40).
- `apps/lifefirst/meds-worker/wrangler.jsonc` — D1 `DB`→`lifefirst-db`, cron `*/5 * * * *`.
  Secrets needed: `PHOENIX_AUTH`, `PUSHOVER_*`, `RESEND_API_KEY`, email/SMS contacts.
  **Code-complete, tested (20/20), not deployed.**
- `apps/office/notify-worker/wrangler.jsonc` — D1 `PHOENIX_DB`, cron `* * * * *`. Deployed
  live 2026-09-09; `RESEND_API_KEY` has since been set (`/health` → `transport: resend`, 2026-09-28).
- `apps/lifefirst-android/functions/requirements.txt` — `firebase_functions~=0.1.0`.
- `unitedsys/db/schema.sql`, `unitedsys/manifests/example.toml` — UnitedSys's own schema/format.
- `openssl` (SHA3-512/BLAKE2b) is required by `intake.sh`; `sqlite3` CLI and `jq` are optional
  (without `sqlite3` the local custody ledger is a no-op).

## Commands / entry points
- `sector2/package-handler/intake.sh <cmd>` — the canonical intake pipeline (R2 upload,
  SHA3-512+BLAKE2b integrity, QR gen, sensitive-file flagging). Reached via `usys clone`,
  `tools/clone.sh` and `scripts/hsf-intake.sh`. `INTAKE_YES=1` for unattended runs.
- `sector2/package-handler/rotate-phoenix-auth.sh` — rotates `PHOENIX_AUTH` across every
  worker leg, verifying each before moving on.
- `node sector2/package-handler/parse-connections.js [--dry-run]` — refresh the Atlas.
- `wrangler deploy` inside any `apps/*/notify-worker` or `meds-worker` — deploys that worker.
- `sector2/unitedsys/bin/us` (zsh) / `bin/us.ps1` (Windows) — UnitedSys CLI entry points.
- Do **not** run `apps/lifefirst/install.sh`, `lifefirst_setup.sh` or `deploy_lifefirst.sh`
  (retired PHP tree, see above).

## Connects to / connected from
- `bin/clone` → `tools/clone.sh` → `sector2/package-handler/intake.sh` (confirmed).
- `scripts/usys.ps1` (`Get-UsysCloneIntakeSh`) → `sector2/package-handler/intake.sh` (canonical clone path).
- `scripts/hsf-intake.sh` → `sector2/package-handler/intake.sh` (directly, not via usys).
- `dashboard/office-launcher.js` → `sector2/package-handler/intake.sh` (Office "save" = intake).
- `sector2/apps/lifefirst/suits/lifefirst_checkin.py` → `sector1/helix/helix_vram.py` (via `phoenix_ctx`, each check-in allocated in her).
- `sector2/package-handler/intake.sh` → `sector3/translator/translator.sh` (`deps` verb, backend intakes).
- `dashboard/main.js` (`get-phoenix-stats`) → `sector2/package-handler/worker` `GET /stats`.
- `sector2/package-handler/parse-connections.js` → `sector2/package-handler/worker` (`POST /connections`, `/connections/reconcile`).
- `sector2/package-handler/intake.sh` → `sector2/package-handler/worker/index.js` (the /mpu multipart routes for big objects and /copy for version keys, both new in 3.6.0).
- `sector2/package-handler/backfill-versions.py` → `sector2/package-handler/worker/index.js` (GET /versions, then PUT /clonepool/<hex>/versions/<sha3> for each recovered version).
- `sector2/package-handler/pool-tidy.py` → `sector2/package-handler/worker/index.js` (read-only GET /clonepool/... checks before a local copy is removed).
- `sector3/worker-up/dataplane-up.sh` → `sector2/package-handler/worker/schema-d1.sql` (creates the D1 tables of a new data plane, then deploys the worker there).
- `sector3/worker-up/seed-dataplane.sh` → `sector2/package-handler/intake.sh` (seeds the new data plane through the import method).
- `sector3/worker-up/worker-bootstrap.sh` → `sector2/package-handler/intake.sh` (a worker box pulls intake.sh itself from R2, checked against D1, then uses it to pull the rest).
- `sector3/worker-up/operations-set.txt` → `sector2/frank/` (the road test ships Frank's folder, as files, to a worker box).
- `scripts/node_session/` → `sector2/package-handler/worker/index.js` `/player/:uid/*` routes (login/logout/clone ring via ingress+egress tunnels).
- `scripts/test_node_session.py` → `scripts/node_session/` → `sector2/package-handler/worker/` (end-to-end smoke test: pull → mutate → push → verify R2 round-trip).
- `sector1/concierge/bridge.py` → `sector2/frank/frank_http.py` (hands chunks to the Frank3 HTTP bridge on port 7347; the only code caller, and the concierge bridge itself is not run on this project).
- Anthropic managed agent (`agent_016KkiogQouh7byVcSjU6Q2j`, env `env_01M6JT8FZ39zGUJaWR2p6PwS`) → `lifefirst-mcp` Cloudflare Worker (`https://lifefirst-mcp.phoenix-jwl.workers.dev`) via URL MCP server config. This is the LifeFirst/assistant agent's live tool backend. Auth via `PHOENIX_LIFEFIRST_MCP_TOKEN` (currently unset — blocks MCP tool calls from the agent).
- `dashboard/scriptforge-launcher.js` → `sector2/apps/scriptforge/index.html`.
- `dashboard/office-launcher.js` → `sector2/apps/office/index.html` (+ `sector2/apps/office/preload.js`; its IPC channels are cross-checked against office-launcher.js, the Office index.html and `dashboard/button-generator.js`).
- `apps/office/notify-worker/wrangler.jsonc` comment → points at
  `sector2/package-handler/rotate-phoenix-auth.sh` for secret rotation.
- `install.ps1` (repo root) clones the standalone `Phoenix-Package_handler` GitHub repo into
  `$INSTALL_ROOT/package-handler`, a sibling of the OS repo (plain clone, no git subtree) —
  this is the 3-way package-handler drift.

## Known issues (verified, not guessed)
- `sector2/frank/frank_save.py`'s tiering logic (`best_drive()` etc.) is unused: nothing calls it.
  `intake.sh` always places new intakes in T1; its own T1→T4 rotation only runs on a manual
  `intake prune` (nothing schedules it — S2CORE-F24, Jerry's call).
- Local vN labels and D1 `versions` labels are independent counters (S2CORE-F23), and
  `hex_id = to_hex(basename)` collides for same-named files (S2CORE-F25) — both open.
- Per-version R2 bytes: `intake.sh` uploads them from 2026-09-29 on, and the 408 older
  `versions` rows got their bytes the same night through `backfill-versions.py`. Measured
  read-only 2026-10-07: D1 `versions` 464 rows → 433 distinct `store_path` keys; R2
  `phoenix-clonepool` 944 objects, 430 `/versions/` keys; 429 of 433 paths have their key,
  4 do not (a `test_500` test row, `tier_rotation_test.txt`, an `index.html`, and the 2 GB
  `llama3.2-3b-q4km.gguf` whose version copy failed 2026-10-07); 1 R2 version key has no row
  (XCUT-F37).
- The systemd units for the dormant code point at files that do not exist:
  `sector3/services/phoenix-frank-helix.service` runs `sector1/frank_helix.py`,
  `phoenix-frankenhelix.service` runs `sector1/frankenhelix.py`, `phoenix-propagator.service`
  runs `sector2/propagator.py`, all under `/home/jwl247/projects/phoenix`. `install-units.sh`
  refuses to install them (S34OPS-F04).
- 86 of 534 clonepool rows have no SHA3/BLAKE2 baseline (D1, 2026-10-03): ~26 directory snapshots (no single-file hash by design), ~38 old `/home/jwlef/...` WSL-era rows (no size/version), ~22 Windows files where hashing failed silently. Root cause fixed 2026-10-03: `report_clonepool` threw away openssl errors, so a failed SHA3 sent a blank baseline; it now falls back to Python hashlib (identical hashes) and prints `NO CUSTODY HASH` if both fail. Repair path: `genie custody` (read-only audit + reviewed re-intake script) — Genie refuses all 86 until re-intaked.
- `intake.sh`'s header comment still says `Version: 1.5.0`; the real `VERSION` is 1.7.0.
- `apps/lifefirst-android/` is dormant (`HIBERNATION_STATUS.md`), has a typo'd
  `TransformViewModek.kt` and a stray `.gitmore` file — stale, not actively maintained.
- `apps/lifefirst/lifefirst_setup.sh` and `deploy_lifefirst.sh` are deprecated and still on
  disk — don't use them (nor the rest of the retired PHP tree).
- `apps/lifefirst/meds-worker` is still not deployed; its 2026-09-14 deadline was voided
  2026-09-21.
- `package-handler/.github/workflows/deploy.yml` only works at the standalone repo's root;
  GitHub never evaluates it inside this monorepo.

---

## Decoys — Never Deploy From These
Intentionally bricked directories. Their `wrangler.jsonc` points at a nonexistent entry-point so any `wrangler deploy` fails loudly. Do not fix them — that is the protection.

| Path | Reason bricked | Canonical location |
|---|---|---|
| `sector3/workers/packages-worker/` | Pre-Gap-1 copy — `/custody`, `/clonepool`, `/packages` GETs had no auth; deploying would silently overwrite production and reopen those routes | `sector2/package-handler/worker/` |
| `sector2/package-handler/r2-worker/` | Retired 2026-09-25; functionality absorbed into packages-worker; do not redeploy | packages-worker handles all R2 via `CLONEPOOL_BUCKET` binding |

Rule: if `wrangler deploy` says "entry-point file not found" with a `STALE-COPY-DO-NOT-DEPLOY` filename, you are in a decoy directory. `cd` to the canonical path above and re-run.

---

## Atlas Upgrade Log
Append an entry here every time a significant component is added, changed, or retired.
Format: `YYYY-MM-DD | version or tag | what changed | deployed/committed by`

| Date       | Component                        | Change                                                                                      | By    |
|------------|----------------------------------|---------------------------------------------------------------------------------------------|-------|
| 2026-09-12 | sector2 / CONNECTIONS.md         | Initial Atlas document written                                                              | Jerry |
| 2026-09-21 | packages-worker                  | Gap 1 security fix: `/custody`, `/clonepool`, `/packages` GETs gated with bearer auth; old unauthenticated sector3 copy bricked | Jerry |
| 2026-09-25 | phoenix-clonepool-r2 worker      | Retired and deleted from Cloudflare; `r2-worker/` left on disk, do not redeploy            | Jerry |
| 2026-09-29 | packages-worker v3.6.0           | `/clonepool/<key>/mpu` multipart routes + `POST /clonepool/<key>/copy`; deployed live      | Jerry |
| 2026-09-29 | CONNECTIONS.md                   | Corrected against Round 2 functionality audit (S2CORE + CONN sections)                     | Jerry |
| 2026-09-29 | backfill-versions.py             | 408 version keys restored to R2; `clonepool_versions` 7-day/8-version pruning design set   | Jerry |
| 2026-09-30 | CONNECTIONS.md                   | Brought up to date with clone-pool work, pool-tidy, intake.sh 1.7.0, road-test data plane  | Jerry |
| 2026-10-01 | Mesh VPN                         | WireGuard retired (too fragile); Tailscale adopted as sole mesh VPN                        | Jerry |
| 2026-10-01 | packages-worker v3.7.0           | `/player/:uid/*` node session lifecycle routes added (state, hardware, sidecars, blobs, wipe); deployed to sector2/package-handler/worker/ — Version ID `324b61b9-f55f-493a-920f-90978df0aff1` | Jerry + Claude |
| 2026-10-01 | scripts/node_session/            | New Frank-managed importable package: `__init__.py`, `frank.py`, `session.py`. Stdlib urllib only, zero deps. Ingress/egress tunnel split. `login()`, `logout()`, `clone_to()` public API | Jerry + Claude |
| 2026-10-01 | scripts/test_node_session.py     | Smoke test: full login→mutate→push→verify R2 round-trip against live packages-worker       | Jerry + Claude |
| 2026-10-01 | sector2/CONNECTIONS.md           | Atlas upgrade log added; node_session, /player routes, Monster Phoenix stack, Tailscale mesh documented | Claude |
| 2026-10-01 | Monster Phoenix GDD v2           | Architecture confirmed: Maptiler + Babylon.js + Electron (no Unity); H.L.K-10 on every node; photogrammetry pipeline for vehicle art | Jerry |
| 2026-10-02 | packages-worker /meta route      | Fixed ReferenceError: `parts` and `method` were undefined at route scope; replaced with `path.startsWith('/meta/')` and `req.method`; deployed from sector2/package-handler/worker/ | Jerry + Claude |
| 2026-10-02 | CONNECTIONS.md                   | Added `## Decoys` section; PS7 set as default terminal + execution policy RemoteSigned | Jerry + Claude |
| 2026-10-03 | packages-worker 3.8.1            | ON CONFLICT keeps source_path; clonepool.version follows the ledger; schema-d1 seeds the 17 categories; intake.sh walk fixes; sync-standalone.sh (public repo) | Claude (Jerry deploys) |
| 2026-10-07 | packages-worker version check    | Live `/health` = 3.8.0; repo = 3.8.2; 3.8.1 and 3.8.2 never deployed (Jerry deploys). Audit CONN-F29 / XCUT-F36 | Claude |
| 2026-10-03 | packages-worker 3.9.0 (pending)  | Member keys (`api_keys`, `clonepool.owner`, `/keys`, `/may-write`), intake asks before writing — in `tentative-wares/package-handler-3.9.0/`, migration before deploy | Claude (Jerry deploys) |
| 2026-10-03 | tentative-wares/                 | New: staging area for tested work not yet in the tree (dashboard folder bar, 3.9.0, cloud Genie, peer-review blocks) | Jerry + Claude |
| 2026-10-04 | lifefirst-mcp URL                | Added `https://lifefirst-mcp.phoenix-jwl.workers.dev` to Atlas — Anthropic managed-agent MCP server for LifeFirst/assistant agent (`agent_016KkiogQouh7byVcSjU6Q2j`, env `env_01M6JT8FZ39zGUJaWR2p6PwS`). URL now in `## What it is` and `## Connects to`. Run `run-atlas.bat` to push to `/meta/atlas`. | Jerry + Claude |

---

## Session State
Updated at the end of each working session. The worker reads this table into `/meta/atlas` → `frames` whenever the Atlas bundle is intaked (`parse-connections.js`).
Format: `Frame | Status | Next | Blocked by`
Status values: `live` · `in-flight` · `blocked` · `retired`

| Frame | Status | Next | Blocked by |
|---|---|---|---|
| packages-worker (sector2) | live | Live 3.8.0; repo 3.8.2 not deployed (2026-10-07) | Jerry deploy |
| /meta route + atlas blob | in-flight | Run run-atlas.bat to seed /meta/atlas (worker deployed 2026-10-02) | — |
| parse-connections.js | in-flight | Run run-atlas.bat, confirm atlas.json PUT returns 200 | — |
| node_session package | live | Run smoke test on Compaq (`ssh pbm-compaq`, `python test_node_session.py`) | — |
| /player routes | live | Smoke test confirms R2 round-trip | — |
| Smoke test (Compaq) | in-flight | SSH pbm-compaq (100.94.101.53), cd to scripts/, run test, log timing numbers | — |
| Atlas frame table | live | Decoys section added to CONNECTIONS.md 2026-10-02 | — |
| Security A2-N1 | live | Fixed 2026-10-03: intake.sh sends keys from a 0600 header file (`-H @file`), never argv | — |
| Monster Phoenix GDD | in-flight | ORCID + grant bundle — waiting on JW's concept notebooks | JW notebooks |
| Stripe live keys | blocked | Vault + stripe-setup.sh live | — |
| /terms route | blocked | Build route reading phoenix-catalog.glossary + dashboard panel UI | — |
| PHOENIX_LIFEFIRST_MCP_TOKEN | blocked | URL added to Atlas 2026-10-04; token still unset — set `PHOENIX_LIFEFIRST_MCP_TOKEN` worker secret to unblock agent MCP tool calls | — |
| Session bootstrap (/meta/atlas) | in-flight | After deploy + atlas run, validate cold-start GET returns full system blob | /meta route deploy |
| Dashboard folder bar + launchers | in-flight | Install from tentative-wares/dashboard, run the 6 Windows checks, commit | Windows checks |
| packages-worker 3.9.0 member keys | in-flight | Migrate D1, deploy, intake the new intake.sh, `genie key new <son>` | Jerry deploy |
| Cloud Genie (son's machine) | in-flight | After 3.9.0: son installs PS7 + Git, sets keys, `genie intake setup`, `genie tour` | 3.9.0 deploy, son's CF Access token |
| Console on Tailscale | blocked | Move portal bind/firewall/hands allow-list from WireGuard 10.47.0.x to the tailnet | — |
| Peer Review forum | in-flight | Build phoenix-review worker + website on the tested blocks | — |
