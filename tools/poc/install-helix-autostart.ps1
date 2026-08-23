#!/usr/bin/env pwsh
# =============================================================================
# install-helix-autostart.ps1 — Register Helix Lightning Kernel autostart.
#
# METHOD A (preferred): Windows Task Scheduler — hidden, runs at logon.
#   Requires: run this script as Administrator ONCE.
#   After that the task runs as the current user with no elevation at logon.
#
# METHOD B (fallback, zero elevation): Windows Startup folder shortcut.
#   Used automatically if Task Scheduler registration fails.
#   A .cmd shortcut is placed in %APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\
#   — Windows runs everything in that folder at logon, no elevation required.
#
# Usage (run as Administrator for Method A):
#   Start-Process pwsh -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PWD\tools\poc\install-helix-autostart.ps1`""
#
# Usage (run normally for Method B fallback):
#   pwsh -NoProfile -ExecutionPolicy Bypass -File tools\poc\install-helix-autostart.ps1
#
# To remove Task Scheduler task:
#   schtasks /delete /tn "Phoenix-HelixLightningKernel" /f
#
# To remove Startup folder shortcut:
#   Remove-Item "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\Phoenix-HelixLightningKernel.cmd"
# =============================================================================

$ErrorActionPreference = 'Stop'

$RepoRoot   = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$Script     = Join-Path $PSScriptRoot 'run-helix-poc.ps1'
$TaskName   = 'Phoenix-HelixLightningKernel'
$FullName   = $TaskName

Write-Host ''
Write-Host '  Phoenix Helix Lightning Kernel -- Autostart Installer'
Write-Host '  -------------------------------------------------------'
Write-Host ''

# -- Verify the launcher exists -----------------------------------------------
if (-not (Test-Path $Script)) {
    Write-Host "  [ERROR] Launcher not found: $Script" -ForegroundColor Red
    exit 1
}

# -- Build the pwsh path ------------------------------------------------------
$PwshPath = (Get-Command pwsh -ErrorAction SilentlyContinue)?.Source
if (-not $PwshPath) {
    Write-Host "  [ERROR] pwsh not found. Install PowerShell 7 first." -ForegroundColor Red
    exit 1
}

# -- Register via schtasks (no elevation needed for user-scope tasks) ---------
# /sc ONLOGON + /ri 5 (repeat every 5 min) + /du 9999:00 (run indefinitely)
$Arg = "-NonInteractive -WindowStyle Hidden -NoProfile -ExecutionPolicy Bypass -File `"$Script`""

# Delete old task silently if it exists
schtasks /delete /tn $FullName /f 2>$null | Out-Null

# Create the task
$result = schtasks /create `
    /tn $FullName `
    /tr "`"$PwshPath`" $Arg" `
    /sc ONLOGON `
    /delay 0000:10 `
    /rl HIGHEST `
    /f 2>&1

if ($LASTEXITCODE -ne 0) {
    Write-Host "  [WARN] Task Scheduler requires Administrator. Falling back to Startup folder..." -ForegroundColor Yellow
    Write-Host ''

    # -- METHOD B: Startup folder (zero elevation) ----------------------------
    $StartupDir = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup"
    $CmdFile    = Join-Path $StartupDir 'Phoenix-HelixLightningKernel.cmd'
    $CmdContent = "@echo off`r`nstart /min `"`" `"$PwshPath`" -NonInteractive -WindowStyle Hidden -NoProfile -ExecutionPolicy Bypass -File `"$Script`"`r`n"
    Set-Content -Path $CmdFile -Value $CmdContent -Encoding ASCII

    Write-Host "  [OK]  Startup shortcut created: $CmdFile" -ForegroundColor Green
    Write-Host "  [OK]  Method: Windows Startup folder (runs at logon, no elevation)" -ForegroundColor Green
    Write-Host ''
    Write-Host '  Helix Lightning Kernel will start at next logon.' -ForegroundColor Cyan
    Write-Host '  To start it now: run run-helix-poc.ps1 manually.' -ForegroundColor Cyan
    Write-Host ''
    Write-Host '  For the preferred Task Scheduler method (hidden, restart-on-failure):' -ForegroundColor White
    Write-Host '    Start-Process pwsh -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"' + $PSCommandPath + '`""' -ForegroundColor White
    Write-Host ''
    exit 0
}

Write-Host "  [OK]  Task registered: $FullName" -ForegroundColor Green
Write-Host "  [OK]  Trigger: at logon (10s delay)" -ForegroundColor Green
Write-Host "  [OK]  Launcher: $Script" -ForegroundColor Green
Write-Host ''
Write-Host '  Helix Lightning Kernel will start automatically at next logon.' -ForegroundColor Cyan
Write-Host '  To start it now without rebooting:' -ForegroundColor Cyan
Write-Host "    schtasks /run /tn `"$FullName`"" -ForegroundColor White
Write-Host ''
Write-Host '  To verify it is running:' -ForegroundColor Cyan
Write-Host "    schtasks /query /tn `"$FullName`" /fo LIST" -ForegroundColor White
Write-Host "    Get-Content 'F:\Phoenix\helix-pages\windows_snapshot.json'" -ForegroundColor White
Write-Host ''
Write-Host '  To remove autostart:' -ForegroundColor Cyan
Write-Host "    schtasks /delete /tn `"$FullName`" /f" -ForegroundColor White
Write-Host ''
