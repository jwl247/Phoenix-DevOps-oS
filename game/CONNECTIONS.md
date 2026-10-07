# game — Sacrifice (game systems + sacrifice-worker)

Written 2026-10-07 (Round 4 audit CONN-F25) from reading `game/` and live read-only checks.
Verify against current code before trusting a specific line number.

## What it is
Sacrifice: the permadeath military MMO (GDD + build sheet: `press-room/Sacrifice Build Plan.md`).
Client engine is **Godot 4.7.2** (build plan, 2026-10-05). **No Godot client exists in this repo
yet** (no `project.godot` or `.gd` files, checked 2026-10-07). What is here is Phoenix's side:
Frank's game-state systems in Python and the live game-state API worker.
- `__init__.py` — the package; re-exports the Phase 2-5 systems.
- `frank_world.py` — `FrankWorld`: Frank as world orchestrator, the one gate to game state. Witnesses accords, enforces laws, writes world history, sends events out through Helix-E (`sector1/helix-lightning/helix_ring.py`).
- `draft_card.py`, `mos.py`, `rank.py`, `hospital.py`, `archive.py`, `jacket.py` — player identity (signed draft card), MOS from observed play, rank + unit issuance, real-time wounds, permadeath archive, the public service record.
- `accord.py`, `tribunal.py`, `king_theater.py`, `footage.py` — challenges, player tribunals, King of Theater, footage registration (clips carry an R2 key in the clone pool).
- `equipment.py`, `vehicle.py`, `vehicle_world.py`, `asset_intake.py` — gear, vehicles, upgrades; vehicle photo → Frank's import method → live art.
- `territory.py`, `named_ground.py`, `world_history.py` — AOs and battles, ground that carries a name, the append-only hash-chained world record.
- `pmtiles.py`, `mvt.py`, `map_extract.py`, `theater_map.py` — our own maps: OpenStreetMap vector tiles in one PMTiles archive cut from the Protomaps planet build (no map vendor; MapTiler dropped 2026-10-05). Pure Python, no dependencies.
- `worker/` — **sacrifice-worker** (`index.mjs` 1.1.0, `wrangler.jsonc`, `schema.sql`, `DEPLOY.md`, `deploy-maps.ps1`): public reads `/health`, `/history`, `/named-ground`, `/territory`, `/tiles/{z}/{x}/{y}.mvt`; write `POST /history` only with Bearer `FRANK_TOKEN`. Live at `https://sacrifice-worker.phoenix-jwl.workers.dev` (jw.leftwich1 account): `/` 200 `{"ok":true,"worker":"sacrifice-worker","version":"1.1.0","history":0}`, `/territory` 200, `/tiles/0/0/0.mvt` 200 (checked 2026-10-07).
- `tests/` — `test_phase3.py`, `test_phase4.py`, `test_phase5.py`, `test_maps.py`, `test_helix_agnostic.py`; `worker/test/worker.test.mjs` (Node, real SQLite).

## Dependencies
- `worker/wrangler.jsonc` — D1 `DB` → `sacrifice_world` (its own database, never `phoenix_dev_db`); R2 `MAPS` → `sacrifice-maps` (maps only: deliberately not the clone pool, so this worker cannot touch the vault); var `MAP_KEY` = `sacrifice-world.pmtiles`.
- Worker secret: `FRANK_TOKEN` (the only secret bound, listed 2026-10-07; the old MapTiler key is gone). Client side: `SACRIFICE_WORKER_URL`, `SACRIFICE_FRANK_TOKEN` (Windows User env; value in vault `sacrifice.env`). Names only: `docs/SECRETS.md`.
- Other env read by the Python side: `PHOENIX_FRANK_KEY` / `PHOENIX_FRANK_KEY_FILE`, `PHOENIX_ARCHIVE_ROOT`, `PHOENIX_EVENT_RING`, `PHOENIX_MAP_ARCHIVE`, `PHOENIX_ASSET_STAGING`, `PHOENIX_VEHICLE_REGISTRY`.
- Python 3 standard library only. Map data © OpenStreetMap contributors, ODbL.

## Commands / entry points
- `python -m game.map_extract extract <out.pmtiles> --bbox w,s,e,n` / `info <file>` — cut theater maps (HTTP range reads, never the whole planet).
- `pwsh -File game\worker\deploy-maps.ps1 [-DryRun]` — tests, extract, intake, bucket, upload, deploy, verify tiles (Jerry runs deploys).
- `node game/worker/test/worker.test.mjs`; `python game/tests/test_phase5.py`; `python game/tests/test_maps.py`; `python game/tests/test_helix_agnostic.py`.
- From `game/worker/`: `npx wrangler deploy`, `npx wrangler tail`.

## Connects to / connected from
- `game/frank_world.py` → `sector1/helix-lightning/helix_ring.py` (`HelixRing`, `RingFrank`: lossless event ring; world events go out on Helix-E).
- `game/asset_intake.py` → `scripts/hsf-intake.sh` → `sector2/package-handler/intake.sh` (vehicle art enters through Frank's import method; hex identity computed the same way as intake.sh).
- `game/worker/deploy-maps.ps1` → `scripts/hsf-intake.sh` (the map archive gets custody before upload).
- `game/theater_map.py` → `game/worker` (`SACRIFICE_WORKER_URL`: `/territory`, `/named-ground`, `/tiles`).
- `game/world_history.py` → `game/worker` `POST /history` (Frank's sync, Bearer `FRANK_TOKEN`).
- `game/worker` → R2 `sacrifice-maps`, D1 `sacrifice_world`.
- Godot 4.7.2 client (not built yet) → `game/worker` (all world state; Frank/Helix never touch the client directly).
- `press-room/Sacrifice Build Plan.md` → `game/` (the build sheet).

## Known issues (verified, not guessed)
- No Godot client yet: the worker's public reads have no game caller today (checked 2026-10-07).
- `/health` reports `history: 0` — nothing has been synced into world history on the live worker yet (2026-10-07).
- `sector2/apps/game/` holds only `COMPANION_VOICE.md` (persona notes from the Monster Phoenix era); the code is here.
- `game/worker/DEPLOY.md` §4 still quotes `/health` as version 1.0.0; live is 1.1.0.
