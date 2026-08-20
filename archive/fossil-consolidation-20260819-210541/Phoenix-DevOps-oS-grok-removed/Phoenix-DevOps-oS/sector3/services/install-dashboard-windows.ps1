# install-dashboard-windows.ps1 — Register Phoenix desktop for logon autostart (Windows)
# Phoenix DevOps OS / jwl247 / GPL v3
#
# Usage (elevated not required):
#   .\install-dashboard-windows.ps1
#   .\install-dashboard-windows.ps1 -Uninstall

param(
    [switch]$Uninstall
)

$ErrorActionPreference = 'Stop'

function ok($m)  { Write-Host "  [OK] $m" -ForegroundColor Green }
function hdr($m) { Write-Host "`n-- $m --" -ForegroundColor Cyan }
function die($m) { Write-Host "  [FAIL] $m" -ForegroundColor Red; exit 1 }

$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot    = (Resolve-Path "$ScriptDir\..\..").Path
$Dashboard   = Join-Path $RepoRoot 'dashboard'
$StartPs1    = Join-Path $Dashboard 'start.ps1'
$PhoenixConf = Join-Path $HOME '.phoenix'
$EnvFile     = Join-Path $PhoenixConf 'phoenix.env'
$TaskName    = 'PhoenixDesktop'

if (-not (Test-Path $StartPs1)) { die "start.ps1 not found at $StartPs1" }

hdr 'Phoenix Desktop — Windows autostart'
Write-Host "  Dashboard: $Dashboard"
Write-Host "  Task:      $TaskName"

if ($Uninstall) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    ok "Removed scheduled task '$TaskName'"
    exit 0
}

hdr 'Phoenix config'
New-Item -ItemType Directory -Force -Path $PhoenixConf | Out-Null

if (-not (Test-Path $EnvFile)) {
    @"
# Phoenix environment — loaded at desktop boot (Windows Scheduled Task + start.ps1)
PHOENIX_ROOT=$RepoRoot
PHOENIX_WORKER_URL=https://packages-worker.phoenix-jwl.workers.dev
PHOENIX_AI_PROVIDER=helpdesk
PHOENIX_OLLAMA_URL=http://localhost:11434
PHOENIX_SKIP_AUTH_MODAL=1
"@ | Set-Content -Path $EnvFile -Encoding UTF8
    ok "Created $EnvFile"
} else {
    ok "$EnvFile already exists — not overwritten"
}

hdr 'Scheduled Task (At logon)'
$pwsh = Get-Command pwsh -ErrorAction SilentlyContinue
if (-not $pwsh) { $pwsh = Get-Command powershell -ErrorAction SilentlyContinue }
if (-not $pwsh) { die 'PowerShell not found' }

$action = New-ScheduledTaskAction `
    -Execute $pwsh.Source `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$StartPs1`"" `
    -WorkingDirectory $Dashboard

$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description 'Phoenix DevOps OS Desktop — boots Help Desk + operator shell at login' `
    -Force | Out-Null

ok "Registered '$TaskName' — runs at logon"

hdr 'Ollama reminder'
$ollama = Get-Command ollama -ErrorAction SilentlyContinue
if ($ollama) {
    ok "Ollama found at $($ollama.Source) — run 'ollama serve' or install Ollama as a Windows service"
} else {
    Write-Host "  [WARN] Ollama not in PATH — Help Desk will use Claude fallback until installed" -ForegroundColor Yellow
    Write-Host "         https://ollama.com/download" -ForegroundColor DarkGray
}

Write-Host ""
Write-Host '================================================================' -ForegroundColor Green
Write-Host '  Phoenix desktop will start at next Windows logon.' -ForegroundColor Green
Write-Host '================================================================' -ForegroundColor Green
Write-Host ""
Write-Host "  Test now:  pwsh -File `"$StartPs1`"" -ForegroundColor Yellow
Write-Host "  Remove:    .\install-dashboard-windows.ps1 -Uninstall" -ForegroundColor Yellow
Write-Host "  Config:    $EnvFile" -ForegroundColor Yellow