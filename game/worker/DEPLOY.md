# sacrifice-worker — first deploy

The Sacrifice game state API: world history (append-only, hash-chained), named ground,
territory, and map tiles from **our own OpenStreetMap extract** (no map vendor).
First deployed 2026-10-05 (steps 1–5); step 6 switches the maps from MapTiler to our own.
Deploys are yours (Claude Code blocks production deploys). Account: the
**jw.leftwich1** Cloudflare account, the one this PC reaches.

Run from `game/worker/` in PowerShell 7 (`npx.cmd` if `npx` isn't found).

## 1. Test first (nothing touches Cloudflare)

```powershell
node test/worker.test.mjs                       # checks against real SQLite
cd ..\..; python game/tests/test_phase5.py; python game/tests/test_maps.py   # + Python→worker cross-checks
```

## 2. Create the database and apply the schema

```powershell
npx wrangler d1 create sacrifice_world
```

Paste the printed `database_id` into `wrangler.jsonc` (replace `REPLACE_WITH_ID_FROM_d1_create`).

```powershell
npx wrangler d1 execute sacrifice_world --remote --file schema.sql
```

The schema can be run again safely (`IF NOT EXISTS` everywhere).

## 3. Secrets: values from the vault, never typed onto a command line

`wrangler secret put` reads the value from stdin, so pipe it in from the vault instead of
typing it as an argument (this is the A2-N1 lesson: keys never go on argv).

```powershell
# Frank's write token: new, random, 48 hex chars. Kept in the vault.
$t = [Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(24)).ToLower()
"SACRIFICE_FRANK_TOKEN=$t" | Set-Content F:\Phoenix\Vault\secrets\sacrifice.env
$t | npx wrangler secret put FRANK_TOKEN
Remove-Variable t

```

## 4. Deploy and check

```powershell
npx wrangler deploy
curl.exe https://sacrifice-worker.<your-subdomain>.workers.dev/health
```

`/health` → `{"ok":true,"worker":"sacrifice-worker","version":"1.0.0","history":0}`.

## 5. Point Frank at it

Set these as Windows User environment variables (not in any file in the repo):

- `SACRIFICE_WORKER_URL`: the workers.dev URL above
- `SACRIFICE_FRANK_TOKEN`: the value in `sacrifice.env`

Then Frank's world history syncs with `WorldHistory.sync(HistoryClient())`. Each row is
re-hashed and re-chained by the worker, then again by D1's own triggers.

## What is public, what isn't

- **Public reads** (GDD §11.2: "accessible to any player at any time"): `/history`,
  `/named-ground`, `/territory`, `/tiles`. Short cache headers on each.
- **Writes**: `POST /history` only, Bearer `FRANK_TOKEN`, timing-safe compare. A server token
  shorter than 32 characters means nobody can write.
- **Tiles**: our own data, no key, no quota to drain. Responses are cached at the edge for a day.

## 6. Maps: our own OpenStreetMap tiles (replaces MapTiler)

MapTiler's terms forbid proxying their tiles, caching them on a server, or making static images from
them. That is everything Phoenix needs, so we dropped MapTiler (JW, 2026-10-05). Maps are now
OpenStreetMap data (© OpenStreetMap contributors, ODbL), cut from the Protomaps daily planet build.
Only the theater boxes are read, never the whole planet.

**One command does all of it**: tests, extract, intake, bucket, upload, deploy, remove the MapTiler key,
and verify the live tiles. It stops at the first failure and is safe to run again:

```powershell
pwsh -File F:\Phoenix\Phoenix-DevOps-oS\game\worker\deploy-maps.ps1            # add -DryRun to preview
```

The same steps by hand, from the repo root in PowerShell 7:

```powershell
# a. Cut the theaters (repeat --bbox per theater; 25 % margin is added around each)
python -m game.map_extract extract F:\Phoenix\maps\sacrifice-world.pmtiles --bbox 5.90,49.80,6.30,50.05

# b. Custody: through Frank's import method like everything else
& "C:\Program Files\Git\bin\bash.exe" scripts/hsf-intake.sh F:/Phoenix/maps/sacrifice-world.pmtiles

# c. The maps bucket. Only the map lives here, and the worker can't reach the vault.
cd game\worker
npx wrangler r2 bucket create sacrifice-maps
npx wrangler r2 object put sacrifice-maps/sacrifice-world.pmtiles --file F:\Phoenix\maps\sacrifice-world.pmtiles --remote

# d. Deploy the new tile route, then remove the MapTiler key from the worker
npx wrangler deploy
npx wrangler secret delete MAPTILER_API_KEY
```

Check: `curl.exe -sI https://sacrifice-worker.phoenix-jwl.workers.dev/tiles/14/8465/5563.mvt` returns
`200` with `content-type: application/vnd.mapbox-vector-tile`. A tile outside the theaters returns `204`.

New theaters later: re-run (a) with every theater's `--bbox`, then (b) and the `r2 object put` in (c).
The worker picks up the new file by its etag. No redeploy needed.
