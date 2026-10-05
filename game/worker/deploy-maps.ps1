<#
deploy-maps.ps1 — Sacrifice: our own OpenStreetMap maps, live (DEPLOY.md step 6)
Phoenix DevOps OS | jwl247 | GPL v3

  pwsh -File game\worker\deploy-maps.ps1                 # Ardennes test theater
  pwsh -File game\worker\deploy-maps.ps1 -DryRun         # show the steps, touch nothing
  pwsh -File game\worker\deploy-maps.ps1 -Bbox "5.90,49.80,6.30,50.05","10.0,47.0,10.5,47.3"

Steps (stops at the first failure; safe to run again):
  1. tests            game + worker tests must pass first
  2. extract          cut the theaters out of the OSM planet  -> F:\Phoenix\maps\
  3. intake           custody through Frank's import method (hsf-intake.sh)
  4. bucket           sacrifice-maps (created only if missing)
  5. upload           the archive into sacrifice-maps
  6. deploy           the worker with the new tile route
  7. MapTiler secret  removed from the worker (skipped if already gone)
  8. verify           /health, a tile inside the theater (200), one outside (204)

Map data (c) OpenStreetMap contributors, ODbL.
#>
[CmdletBinding()]
param(
    [string[]] $Bbox    = @("5.90,49.80,6.30,50.05"),
    [string]   $MapDir  = "F:\Phoenix\maps",
    [string]   $Worker  = "https://sacrifice-worker.phoenix-jwl.workers.dev",
    [switch]   $DryRun,
    [switch]   $SkipTests
)

$ErrorActionPreference = "Stop"
$Repo     = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$WorkerDir = $PSScriptRoot
$Archive  = Join-Path $MapDir "sacrifice-world.pmtiles"
$Bash     = "C:\Program Files\Git\bin\bash.exe"
$Npx      = if (Get-Command npx.cmd -ErrorAction SilentlyContinue) { "npx.cmd" } else { "npx" }

function Step($n, $text) { Write-Host "`n[$n/8] $text" -ForegroundColor Cyan }
function Ok($text)       { Write-Host "      OK  $text" -ForegroundColor Green }
function Fail($text)     { Write-Host "      FAILED  $text" -ForegroundColor Red; exit 1 }

# Run a native command; stop the script if it fails. In -DryRun, only print it.
function Run([string] $What, [scriptblock] $Cmd) {
    if ($DryRun) { Write-Host "      would run: $What" -ForegroundColor DarkGray; return "" }
    $out = & $Cmd 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0) { Write-Host $out; Fail $What }
    return $out
}

function Get-Status([string] $Url) {
    try   { return (Invoke-WebRequest -Uri $Url -Method Get -UserAgent "phoenix-sacrifice/1.0" -SkipHttpErrorCheck).StatusCode }
    catch { return 0 }
}

Write-Host "Sacrifice maps -> $Worker" -ForegroundColor White
Write-Host "  theaters: $($Bbox -join '  ')"
Write-Host "  archive:  $Archive"
if ($DryRun) { Write-Host "  DRY RUN - nothing will be changed" -ForegroundColor Yellow }

# ── preflight ────────────────────────────────────────────────────────────────
foreach ($b in $Bbox) {
    $p = $b.Split(",") | ForEach-Object { [double]$_ }
    if ($p.Count -ne 4 -or $p[0] -ge $p[2] -or $p[1] -ge $p[3]) { Fail "bad -Bbox '$b' (minlon,minlat,maxlon,maxlat)" }
}
if (-not (Test-Path $Bash)) { Fail "Git Bash not found at $Bash" }
foreach ($tool in "python", "node", $Npx) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { Fail "$tool not found on PATH" }
}

# ── 1. tests ─────────────────────────────────────────────────────────────────
Step 1 "tests"
if ($SkipTests) { Write-Host "      skipped (-SkipTests)" -ForegroundColor Yellow }
else {
    Push-Location $Repo
    try {
        foreach ($t in "test_maps", "test_phase5") {
            Run "python game/tests/$t.py" { python "game/tests/$t.py" } | Out-Null
            if (-not $DryRun) { Ok $t }
        }
        Run "node game/worker/test/worker.test.mjs" { node game/worker/test/worker.test.mjs } | Out-Null
        if (-not $DryRun) { Ok "worker" }
    } finally { Pop-Location }
}

# ── 2. extract ───────────────────────────────────────────────────────────────
Step 2 "extract theaters from the OpenStreetMap planet"
if (-not $DryRun) { New-Item -ItemType Directory -Force $MapDir | Out-Null }
$bboxArgs = $Bbox | ForEach-Object { "--bbox"; $_ }
Push-Location $Repo
try {
    $out = Run "python -m game.map_extract extract $Archive $($bboxArgs -join ' ')" {
        python -m game.map_extract extract $Archive @bboxArgs
    }
    if (-not $DryRun) { Ok (($out -split "`n" | Where-Object { $_ -match "tiles," } | Select-Object -Last 1).Trim()) }
} finally { Pop-Location }

# ── 3. intake (custody) ──────────────────────────────────────────────────────
Step 3 "intake - custody through Frank's import method"
$archiveFwd = $Archive -replace "\\", "/"
Push-Location $Repo
try {
    Run "bash scripts/hsf-intake.sh $archiveFwd" { & $Bash scripts/hsf-intake.sh $archiveFwd } | Out-Null
    if (-not $DryRun) { Ok "intaked" }
} finally { Pop-Location }

Push-Location $WorkerDir
try {
    # ── 4. bucket ────────────────────────────────────────────────────────────
    Step 4 "R2 bucket sacrifice-maps"
    $list = Run "$Npx wrangler r2 bucket list" { & $Npx wrangler r2 bucket list }
    if ($DryRun)                              { Write-Host "      would create it if missing" -ForegroundColor DarkGray }
    elseif ($list -match "(?m)\bsacrifice-maps\b") { Ok "already exists" }
    else {
        Run "$Npx wrangler r2 bucket create sacrifice-maps" { & $Npx wrangler r2 bucket create sacrifice-maps } | Out-Null
        Ok "created"
    }

    # ── 5. upload ────────────────────────────────────────────────────────────
    Step 5 "upload the archive"
    Run "$Npx wrangler r2 object put sacrifice-maps/sacrifice-world.pmtiles --file $Archive --remote" {
        & $Npx wrangler r2 object put sacrifice-maps/sacrifice-world.pmtiles --file $Archive --remote
    } | Out-Null
    if (-not $DryRun) { Ok ("{0:N1} MB uploaded" -f ((Get-Item $Archive).Length / 1MB)) }

    # ── 6. deploy ────────────────────────────────────────────────────────────
    Step 6 "deploy the worker"
    $dep = Run "$Npx wrangler deploy" { & $Npx wrangler deploy }
    if (-not $DryRun) { Ok (($dep -split "`n" | Where-Object { $_ -match "Current Version ID" }) -join "").Trim() }

    # ── 7. MapTiler secret ───────────────────────────────────────────────────
    Step 7 "remove the MapTiler key from the worker"
    $secrets = Run "$Npx wrangler secret list" { & $Npx wrangler secret list }
    if ($DryRun)                                  { Write-Host "      would delete it if present" -ForegroundColor DarkGray }
    elseif ($secrets -notmatch "MAPTILER_API_KEY") { Ok "already gone" }
    else {
        Run "$Npx wrangler secret delete MAPTILER_API_KEY" { "y" | & $Npx wrangler secret delete MAPTILER_API_KEY } | Out-Null
        Ok "deleted"
    }
} finally { Pop-Location }

# ── 8. verify ────────────────────────────────────────────────────────────────
Step 8 "verify the live worker"
if ($DryRun) { Write-Host "      would check /health, an inside tile (200) and an outside tile (204)" -ForegroundColor DarkGray; exit 0 }
Start-Sleep -Seconds 3                                  # let the new version settle
$health = Invoke-RestMethod "$Worker/health" -UserAgent "phoenix-sacrifice/1.0"
if (-not $health.ok) { Fail "/health" }
Ok "health - worker $($health.version), $($health.history) history entries"

# a tile in the middle of the first theater, at zoom 14
$p = $Bbox[0].Split(",") | ForEach-Object { [double]$_ }
$lon = ($p[0] + $p[2]) / 2; $lat = ($p[1] + $p[3]) / 2
$n = [math]::Pow(2, 14)
$x = [math]::Floor(($lon + 180) / 360 * $n)
$s = [math]::Sin($lat * [math]::PI / 180)
$y = [math]::Floor((0.5 - [math]::Log((1 + $s) / (1 - $s)) / (4 * [math]::PI)) * $n)
$inside = Get-Status "$Worker/tiles/14/$x/$y.mvt"
if ($inside -ne 200) { Fail "tile 14/$x/$y inside the theater returned $inside (expected 200)" }
Ok "tile 14/$x/$y inside the theater - 200"
$outside = Get-Status "$Worker/tiles/14/0/0.mvt"
if ($outside -ne 204) { Fail "tile 14/0/0 outside the theaters returned $outside (expected 204)" }
Ok "tile outside the theaters - 204"

Write-Host "`nMaps are live: our own OpenStreetMap, no vendor." -ForegroundColor Green
