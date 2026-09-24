#!/usr/bin/env pwsh
# =============================================================================
# install-compliance-check-autostart.ps1 — register the weekly local
# compliance check (compliance-local-check.ps1) via Windows Task Scheduler.
# Same install pattern as tools/poc/install-helix-autostart.ps1.
#
# Usage (run as Administrator for the preferred Task Scheduler method):
#   Start-Process pwsh -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PWD\scripts\install-compliance-check-autostart.ps1`""
#
# To remove:
#   schtasks /delete /tn "Phoenix-ComplianceCheck" /f
# =============================================================================

$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path $PSScriptRoot -Parent
$Script   = Join-Path $PSScriptRoot 'compliance-local-check.ps1'
$TaskName = 'Phoenix-ComplianceCheck'

Write-Host ''
Write-Host '  Phoenix Compliance Check -- Weekly Autostart Installer'
Write-Host '  --------------------------------------------------------'
Write-Host ''

if (-not (Test-Path $Script)) {
    Write-Host "  [ERROR] Check script not found: $Script" -ForegroundColor Red
    exit 1
}

$PwshPath = (Get-Command pwsh -ErrorAction SilentlyContinue)?.Source
if (-not $PwshPath) {
    Write-Host "  [ERROR] pwsh not found. Install PowerShell 7 first." -ForegroundColor Red
    exit 1
}

$Arg = "-NonInteractive -NoProfile -ExecutionPolicy Bypass -File `"$Script`""

schtasks /delete /tn $TaskName /f 2>$null | Out-Null

# Weekly, Mondays at 9:00 AM local, only runs while logged on (so the
# MessageBox alert on failure is actually visible to someone, not fired
# into an empty session).
$result = schtasks /create `
    /tn $TaskName `
    /tr "`"$PwshPath`" $Arg" `
    /sc WEEKLY `
    /d MON `
    /st 09:00 `
    /rl LIMITED `
    /f 2>&1

if ($LASTEXITCODE -ne 0) {
    Write-Host "  [ERROR] Task Scheduler registration failed:" -ForegroundColor Red
    Write-Host "  $result" -ForegroundColor Red
    Write-Host ''
    Write-Host '  Re-run this script as Administrator.' -ForegroundColor Yellow
    exit 1
}

Write-Host "  [OK]  Task registered: $TaskName" -ForegroundColor Green
Write-Host "  [OK]  Trigger: weekly, Mondays 9:00 AM (only while logged on)" -ForegroundColor Green
Write-Host "  [OK]  Script: $Script" -ForegroundColor Green
Write-Host "  [OK]  Log: $env:USERPROFILE\.unitedsys\logs\compliance-check.jsonl" -ForegroundColor Green
Write-Host ''
Write-Host '  To run it right now without waiting for Monday:' -ForegroundColor Cyan
Write-Host "    schtasks /run /tn `"$TaskName`"" -ForegroundColor White
Write-Host ''
Write-Host '  To verify it is registered:' -ForegroundColor Cyan
Write-Host "    schtasks /query /tn `"$TaskName`" /fo LIST" -ForegroundColor White
Write-Host ''
Write-Host '  To remove:' -ForegroundColor Cyan
Write-Host "    schtasks /delete /tn `"$TaskName`" /f" -ForegroundColor White
Write-Host ''
