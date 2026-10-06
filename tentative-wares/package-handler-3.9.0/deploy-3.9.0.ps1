#Requires -Version 7.2
# deploy-3.9.0.ps1 — packages-worker 3.9.0 (member keys) to production, in the safe order.
# Phoenix DevOps OS | jwl247 | GPL v3
#
#   Where: PBMII, PowerShell 7 (your normal window, PHOENIX_AUTH loaded), from the repo root:
#     cd F:\Phoenix\Phoenix-DevOps-oS
#     .\tentative-wares\package-handler-3.9.0\deploy-3.9.0.ps1 -Who <son's name>
#
# Order (DEPLOY.md): local test -> copy into sector2 -> D1 migration -> deploy -> verify ->
# intake the new intake.sh (so `genie intake setup` hands it out) -> his key, shown once.
# Stops at the first failure. Re-runnable: a migration already applied is skipped.
param(
    [Parameter(Mandatory)][ValidatePattern('^[a-z0-9][a-z0-9._-]{1,31}$')][string]$Who,
    [ValidateSet('read,intake', 'read')][string]$Scopes = 'read,intake',
    [switch]$SkipTest
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$ware = $PSScriptRoot
$wdir = Join-Path $repo 'sector2/package-handler/worker'
$url  = if ($env:PHOENIX_WORKER_URL) { $env:PHOENIX_WORKER_URL.TrimEnd('/') } else { 'https://packages-worker.phoenix-jwl.workers.dev' }
function Step([string]$m) { Write-Host "`n== $m" -ForegroundColor Cyan }
function Die([string]$m)  { Write-Host "STOPPED: $m" -ForegroundColor Red; exit 1 }
function Auth { $h = @{ Authorization = "Bearer $($env:PHOENIX_AUTH)" }
    if ($env:CF_ACCESS_CLIENT_ID -and $env:CF_ACCESS_CLIENT_SECRET) { $h['CF-Access-Client-Id'] = $env:CF_ACCESS_CLIENT_ID; $h['CF-Access-Client-Secret'] = $env:CF_ACCESS_CLIENT_SECRET }
    $h }

Step 'preflight'
if (-not $env:PHOENIX_AUTH) { Die 'PHOENIX_AUTH is not set in this window.' }
$live = (Invoke-RestMethod "$url/health").version
Write-Host "live worker: $live"
$me = Invoke-RestMethod "$url/whoami" -Headers (Auth) -SkipHttpErrorCheck
if (-not $me.ok) { Die 'your PHOENIX_AUTH is refused by the live worker — fix that first.' }

if (-not $SkipTest) {
    Step 'local test (no live data touched)'
    pwsh -NoProfile -File (Join-Path $ware 'test/member-keys.test.ps1')
    if ($LASTEXITCODE) { Die 'local test failed — nothing deployed.' }
}

Step 'copy 3.9.0 into sector2'
Copy-Item (Join-Path $ware 'worker/index.js'), (Join-Path $ware 'worker/schema-d1.sql'), (Join-Path $ware 'worker/migrate-3.9.0-member-keys.sql') $wdir -Force
Copy-Item (Join-Path $ware 'intake.sh') (Join-Path $repo 'sector2/package-handler/intake.sh') -Force

Push-Location $wdir
try {
    Step 'D1 migration (before the deploy)'
    $cols = npx.cmd wrangler d1 execute phoenix_dev_db --remote --json --command "SELECT name FROM pragma_table_info('clonepool') WHERE name='owner'" 2>$null | Out-String
    if ($cols -match '"owner"') { Write-Host 'already migrated — skipped' }
    else {
        npx.cmd wrangler d1 execute phoenix_dev_db --remote --file migrate-3.9.0-member-keys.sql
        if ($LASTEXITCODE) { Die 'migration failed — worker NOT deployed (3.8 keeps running).' }
    }
    Step 'deploy'
    npx.cmd wrangler deploy
    if ($LASTEXITCODE) { Die 'deploy failed.' }
} finally { Pop-Location }

Step 'verify'
Start-Sleep -Seconds 3
$v = (Invoke-RestMethod "$url/health").version
if ($v -ne '3.9.0') { Die "live worker says $v, not 3.9.0." }
$me = Invoke-RestMethod "$url/whoami" -Headers (Auth)
if ($me.who -ne 'owner') { Die 'your key is not seen as owner.' }
Write-Host "live 3.9.0, you = owner" -ForegroundColor Green

Step 'intake the new intake.sh (custody, so his genie can fetch it)'
& (Join-Path $repo 'bin/intake.cmd') (Join-Path $repo 'sector2/package-handler/intake.sh')

Step "key for $Who"
$k = Invoke-RestMethod "$url/keys" -Method Post -Headers (Auth) -ContentType 'application/json' -Body (@{ who = $Who; scopes = $Scopes } | ConvertTo-Json) -SkipHttpErrorCheck
if (-not $k.key) { Die "key not issued: $($k.error)" }
Write-Host ''
Write-Host "  $Who's key (shown ONCE — Phoenix keeps only its hash):" -ForegroundColor Yellow
Write-Host "  $($k.key)" -ForegroundColor White
Write-Host '  Send it by Signal or tell him in person. Not email, not a file.' -ForegroundColor Yellow
Write-Host "  Lost laptop:  Invoke-RestMethod $url/keys/$Who/revoke -Method Post -Headers @{Authorization=`"Bearer `$env:PHOENIX_AUTH`"}"
