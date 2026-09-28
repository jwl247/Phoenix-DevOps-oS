# pull-run-test.ps1 — the game-gate test from a Windows box (the Precision):
# usys pull the Helix team from D1/R2 onto an EMPTY clone pool, verify, run.
# Twin of pull-run-test.sh (which runs the same test on Linux / against the
# fake worker). Requires: PHOENIX_WORKER_URL + PHOENIX_AUTH (+ the CF-Access
# pair on the workers.dev host), Git Bash (intake.sh), python3.
#
#   pwsh -File tools\cloudflare\pull-run-test.ps1 [-Suite helix-team-ingress] [-SkipIntake]
#
# -SkipIntake: the suite is already in the worker (intaked from another box);
#              only pull + run here — the real two-machine shape.
[CmdletBinding()]
param([string]$Suite = 'helix-team-ingress', [switch]$SkipIntake, [int]$RunSeconds = 20)
$ErrorActionPreference = 'Stop'
$root = Resolve-Path (Join-Path $PSScriptRoot '..\..')
Set-Location $root
if (-not $env:PHOENIX_WORKER_URL -or -not $env:PHOENIX_AUTH) { throw 'set PHOENIX_WORKER_URL and PHOENIX_AUTH first' }
$date = (Get-Date).ToUniversalTime().ToString('yyyy-MM-dd')
$out = Join-Path $root "verification\$date"; New-Item -ItemType Directory -Force $out | Out-Null
$log = Join-Path $out 'game-gate-pull-run-windows.log'
function Say([string]$s) { $s | Tee-Object -FilePath $log -Append }
$commit = (git rev-parse --short HEAD).Trim()
Say "# game-gate pull-run test (windows)  commit=$commit  worker=$env:PHOENIX_WORKER_URL  suite=$Suite  utc=$((Get-Date).ToUniversalTime().ToString('o'))  host=$env:COMPUTERNAME"

# an empty pool for this test, never the real one
$pool = Join-Path $env:TEMP ("phx-gate-pool-" + [guid]::NewGuid().ToString('N').Substring(0, 8))
New-Item -ItemType Directory -Force $pool | Out-Null
$env:CLONEPOOL_DIR = $pool.Replace('\', '/')
$env:INTAKE_YES = '1'
. "$root\scripts\usys.ps1"

if (-not $SkipIntake) {
    Say '## 1-2. stage from HEAD + intake into the worker (hsf-intake.sh)'
    bash tools/helix-team/stage.sh "$env:TEMP/phx-gate-stage" | Select-Object -Last 1 | ForEach-Object { Say $_ }
    $src = "$env:TEMP/phx-gate-stage/$Suite"
    bash scripts/hsf-intake.sh "$src/" 2>&1 | Select-String 'intake:SUITE|intake:OK\] .* → clonepool' | Select-Object -Last 2 | ForEach-Object { Say $_.Line }
    Remove-Item -Recurse -Force $pool; New-Item -ItemType Directory -Force $pool | Out-Null
}
Say "## 3. pool is empty: $((Get-ChildItem $pool -Force | Measure-Object).Count) entries"

Say '## 4. usys pull (hash-verified, D1 -> manifest -> R2)'
$sw = [Diagnostics.Stopwatch]::StartNew()
usys pull $Suite 2>&1 | ForEach-Object { Say "  $_" }
$sw.Stop()
$dest = Join-Path $pool $Suite
$n = (Get-ChildItem $dest -Recurse -File -Force | Where-Object Name -notin '.suite.json', '.pool-manifest.json' | Measure-Object).Count
Say "pulled $n files in $([math]::Round($sw.Elapsed.TotalSeconds,1)) s -> $dest"
if (-not (Test-Path (Join-Path $dest '.suite.json'))) { Say 'FAIL: no .suite.json after pull'; exit 1 }

Say "## 5. usys run $Suite (for $RunSeconds s)"
$env:PHOENIX_TEAM_HOME = Join-Path $env:TEMP 'phx-gate-teamhome'
$p = Start-Process -FilePath 'bash' -ArgumentList @('-lc', "cd '$($dest.Replace('\','/'))' && PHOENIX_TEAM_ROOT=. PHOENIX_HELIX_ROLE=ingress PHOENIX_RJ_SECRET=gate bash tools/helix-team/run-team.sh") -PassThru -WindowStyle Hidden -RedirectStandardOutput (Join-Path $out 'game-gate-run.out')
$ready = Join-Path $env:PHOENIX_TEAM_HOME 'ready'
$up = $false
for ($i = 0; $i -lt ($RunSeconds * 2); $i++) { if (Test-Path $ready) { $up = $true; break }; Start-Sleep -Milliseconds 500 }
Start-Sleep 3
$runOut = Get-Content (Join-Path $out 'game-gate-run.out') -Raw
Say ("team up=$up  " + (($runOut -split "`n") | Select-String 'up \(' | Select-Object -First 1))
Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
Get-Process python3, python -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -match 'helix_vramd|integrated_guardian|helixi|romeo' } | Stop-Process -Force -ErrorAction SilentlyContinue

Say '## 6. verdict'
if ($up) { Say "PASS: $Suite ($n files, commit $commit) pulled from $env:PHOENIX_WORKER_URL onto an empty pool, verified, and ran on $env:COMPUTERNAME"; exit 0 }
Say 'FAIL: the pulled suite did not come up'; Say $runOut; exit 1
