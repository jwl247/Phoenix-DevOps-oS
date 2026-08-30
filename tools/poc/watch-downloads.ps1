#!/usr/bin/env pwsh
# =============================================================================
# watch-downloads.ps1 — Phoenix Auto-Intake Watcher
#
# Watches F:\Phoenix\Downloads. The moment a file finishes landing, it runs
# phx-import on it (hex ID, sidecar, clonepool, D1 custody). No manual step.
#
# Usage:
#   pwsh -NoProfile -ExecutionPolicy Bypass -File tools\poc\watch-downloads.ps1
#
# Run in the background; Ctrl+C to stop. Safe to leave running.
# =============================================================================

$ErrorActionPreference = 'Stop'

# Resolve repo root: this script lives at tools\poc\, so go up two levels.
$RepoRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent

# Dot-source usys.ps1 to get $script:PhxSharedRoot and the phx- wrapper functions.
. (Join-Path $RepoRoot 'scripts\usys.ps1')

$WatchDir = Join-Path $script:PhxSharedRoot 'Downloads'

if (-not (Test-Path $WatchDir)) {
    New-Item -ItemType Directory -Path $WatchDir -Force | Out-Null
    Write-Host "  Created watch directory: $WatchDir" -ForegroundColor Yellow
}

# Track files already handled this session so we don't double-import.
$processed = @{}

function Invoke-Intake {
    param([string]$FilePath)

    if (-not (Test-Path -LiteralPath $FilePath)) { return }

    $item = Get-Item -LiteralPath $FilePath -ErrorAction SilentlyContinue
    if (-not $item -or $item.PSIsContainer) { return }
    if ($item.Length -le 0) { return }

    $name = $item.Name
    if ($name -like '_PHOENIX*' -or $name -like '.*') { return }
    if ($processed.ContainsKey($name)) { return }

    $processed[$name] = $true
    Write-Host "  intake -> $name" -ForegroundColor Cyan
    try {
        phx-import $FilePath
    } catch {
        Write-Host "  [WARN] phx-import failed for $name : $_" -ForegroundColor Yellow
        $processed.Remove($name)
    }
}

Write-Host ''
Write-Host '  Phoenix Downloads Watcher' -ForegroundColor Cyan
Write-Host "  Watching: $WatchDir" -ForegroundColor White
Write-Host '  Drop a file here -> it gets intaked automatically.' -ForegroundColor White
Write-Host '  Ctrl+C to stop.' -ForegroundColor DarkGray
Write-Host ''

# Catch anything already sitting in the folder.
Get-ChildItem -LiteralPath $WatchDir -File -ErrorAction SilentlyContinue |
    ForEach-Object { Invoke-Intake $_.FullName }

# Watch for new arrivals.
$watcher = New-Object System.IO.FileSystemWatcher
$watcher.Path = $WatchDir
$watcher.Filter = '*'
$watcher.NotifyFilter = [System.IO.NotifyFilters]'FileName, LastWrite, Size'
$watcher.IncludeSubdirectories = $false
$watcher.EnableRaisingEvents = $true

$action = {
    $path = $Event.SourceEventArgs.FullPath
    Start-Sleep -Milliseconds 1000   # let the download finish writing
    if ((Test-Path -LiteralPath $path)) {
        $len = (Get-Item -LiteralPath $path -ErrorAction SilentlyContinue).Length
        if ($len -gt 0) {
            Invoke-Intake $path
        }
    }
}

Register-ObjectEvent -InputObject $watcher -EventName Created -Action $action | Out-Null
Register-ObjectEvent -InputObject $watcher -EventName Changed -Action $action | Out-Null

try {
    while ($true) { Start-Sleep -Seconds 1 }
} finally {
    $watcher.EnableRaisingEvents = $false
    $watcher.Dispose()
    Get-EventSubscriber | Unregister-Event
    Write-Host ''
    Write-Host '  Watcher stopped.' -ForegroundColor Yellow
}
