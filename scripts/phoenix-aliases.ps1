# phoenix-aliases.ps1 — short commands for Jerry's PS7 (loaded by usys.ps1, like g and rotate-key).
# Phoenix DevOps OS | jwl247 | GPL v3
# Jerry 2026-10-07: "any cool shit for alias is a go". Every name was checked free first.
#   ..  ...        up one / two folders
#   repo           the Phoenix repo
#   snap           screenshot every screen for Claude (same as the desktop icon)
#   lastsnap       open the newest screenshot
#   pb3  aws1      SSH to pbmIII / the awslh lighthouse over the Phoenix Mesh (hosts.json)
#   box <name>     SSH to any host in hosts.json
#   pulse          one-screen health: worker (through Access), Jarvis, mesh peers, sensor, repo
#   glog  gst      short git log / git status
#   here           this folder in Explorer
#   pool <text>    search the clone pool (usys search)
#   security <x>   the file sensor: status, scan, alerts, verify, lock-hud, unlock-hud, off, on

$script:PhxRepo = [Environment]::GetEnvironmentVariable('PHOENIX_ROOT', 'User')
if (-not $script:PhxRepo) { $script:PhxRepo = Split-Path $PSScriptRoot }

function global:.. { Set-Location .. }
function global:... { Set-Location ..\.. }
function global:repo { Set-Location $script:PhxRepo }
function global:here { Start-Process explorer.exe -ArgumentList "`"$((Get-Location).Path)`"" }
function global:glog { git log --oneline -15 @args }
function global:gst { git status -sb @args }
function global:pool { Invoke-UsysMain search @args }
function global:security {
    $sec = Join-Path $HOME '.phoenix\security\bin\security.py'          # the installed sensor (install-security.ps1)
    if (-not (Test-Path $sec)) { Write-Host '  security: sensor not installed (sector2\apps\security\install-security.ps1)' -ForegroundColor Yellow; return }
    python $sec @args
}

function global:snap { pwsh -NoProfile -Sta -ExecutionPolicy Bypass -File (Join-Path $script:PhxRepo 'scripts\snap-to-claude.ps1') }
function global:lastsnap {
    $f = Join-Path $HOME '.phoenix\screenshots\latest.png'
    if (Test-Path $f) { Invoke-Item $f } else { Write-Host '  no screenshot yet - snap first' -ForegroundColor Yellow }
}

function global:box([Parameter(Mandatory)][string]$Name, [Parameter(ValueFromRemainingArguments)]$Rest) {
    $h = (Get-Content (Join-Path $script:PhxRepo 'sector3\mesh\hosts.json') -Raw | ConvertFrom-Json).hosts.$Name
    if (-not $h) { Write-Host "  box: no host '$Name' in hosts.json" -ForegroundColor Yellow; return }
    $user = if ($h.ssh) { ($h.ssh -split '@')[0] } else { $env:USERNAME }
    $key = if ($h.ssh_key) { Join-Path $HOME ".ssh\$($h.ssh_key)" } else { $null }
    $sshArgs = @('-o', 'ConnectTimeout=6')
    if ($key) { $sshArgs += @('-i', $key) }
    ssh @sshArgs "$user@$($h.ip)" @Rest                                  # the mesh address, not the LAN one
}
function global:pb3 { box pbmiii @args }
function global:aws1 { box awslh @args }

function global:pulse {
    $ok = { param($b, $t) Write-Host ('  {0} {1}' -f $(if ($b) { 'OK  ' } else { 'FAIL' }), $t) -ForegroundColor $(if ($b) { 'Green' } else { 'Red' }) }
    $url = if ($env:PHOENIX_WORKER_URL) { $env:PHOENIX_WORKER_URL } else { 'https://packages-worker.phoenix-jwl.workers.dev' }
    $hdr = @{ 'CF-Access-Client-Id' = $env:CF_ACCESS_CLIENT_ID; 'CF-Access-Client-Secret' = $env:CF_ACCESS_CLIENT_SECRET }
    try { $v = (Invoke-RestMethod "$url/health" -Headers $hdr -TimeoutSec 10).version; & $ok $true "packages-worker $v (through Access)" }
    catch { & $ok $false "packages-worker: $($_.Exception.Message)" }
    $t = Get-Date
    $j = (python (Join-Path $script:PhxRepo 'bin\jarvis') 'Reply with one word: ok' 2>&1 | Out-String).Trim()
    & $ok ($LASTEXITCODE -eq 0) ("Jarvis: {0} ({1:N1} s)" -f $j, ((Get-Date) - $t).TotalSeconds)
    $peers = python (Join-Path $script:PhxRepo 'sector3\mesh\phoenix_buddy.py') check --me pbmii 2>&1
    foreach ($l in $peers) { & $ok ($l -match 'healthy') "mesh $($l -replace '\s+', ' ')" }
    $sec = Join-Path $HOME '.phoenix\security\bin\security.py'
    if (Test-Path $sec) { $s = python $sec status | ConvertFrom-Json; & $ok $s.healthy "security sensor $($s.version)" }
    Push-Location $script:PhxRepo
    $dirty = @(git status --porcelain 2>$null | Where-Object { $_ -notmatch '^\?\?' }).Count
    $ahead = (git rev-list --count '@{u}..HEAD' 2>$null)
    & $ok ($ahead -eq '0') ("repo: {0} changed file(s), {1} commit(s) not pushed" -f $dirty, $ahead)
    Pop-Location
}
