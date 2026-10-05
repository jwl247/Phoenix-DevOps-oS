# sacrifice-worker — first deploy

The Sacrifice game state API: world history (append-only, hash-chained), named ground,
territory, and the map-tile proxy. Built and tested locally on 2026-10-05; **not deployed**.
Deploys are yours (Claude Code blocks production deploys). Account: the
**jw.leftwich1** Cloudflare account, the one this PC reaches.

Run from `game/worker/` in PowerShell 7 (`npx.cmd` if `npx` isn't found).

## 1. Test first (nothing touches Cloudflare)

```powershell
node test/worker.test.mjs                       # 26 checks against real SQLite
cd ..\..; python game/tests/test_phase5.py      # Python side + Python→worker cross-check
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

# MapTiler key from the vault file.
((Get-Content F:\Phoenix\Vault\secrets\maptiler.env) -match '^MAPTILER_API_KEY=' -replace '^MAPTILER_API_KEY=','') |
  npx wrangler secret put MAPTILER_API_KEY
```

## 4. Deploy and check

```powershell
npx wrangler deploy
curl.exe https://sacrifice-worker.<your-subdomain>.workers.dev/health
curl.exe -o tile.png https://sacrifice-worker.<your-subdomain>.workers.dev/tiles/5/16/10.png
```

`/health` → `{"ok":true,"worker":"sacrifice-worker","version":"1.0.0","history":0}`.
`tile.png` should open as a map tile.

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
- **Tiles**: the key stays in the worker. Responses are cached at Cloudflare's edge for 7 days,
  which limits how fast anyone can draw down the MapTiler quota. If abuse shows up, add a
  Cloudflare rate-limiting rule on `/tiles/*`. No code change is needed for that.
