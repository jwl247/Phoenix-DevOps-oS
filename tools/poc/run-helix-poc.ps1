#!/usr/bin/env pwsh
# =============================================================================
# run-helix-poc.ps1 -- Phoenix Double Helix PoC launcher (Windows / Strand A)
#
# Starts Helix-I (Strand A: channels 1-4 ingress, executing) and the snapshot
# writer loop. The snapshot is written to F:\Phoenix\helix-pages\ every 5s so
# paging.py on Debian can watch both strands as one paging brain.
#
# Usage:
#   pwsh -NoProfile -ExecutionPolicy Bypass -File tools\poc\run-helix-poc.ps1
#
# Prerequisites:
#   - py -3 available (Python 3 on PATH)
#   - QEMU Debian running if you want the Linux paging brain active
#   - Shared FS mounted: F:\Phoenix\ hosted on Windows (setup-shared-fs.ps1)
# =============================================================================

$ErrorActionPreference = 'Stop'

# Repo root is two levels up from tools/poc/
$RepoRoot  = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$PageDir   = 'F:\Phoenix\helix-pages'
$LightningDir = Join-Path $RepoRoot 'sector1\helix-lightning'
$Script    = Join-Path $PSScriptRoot 'true_double_helix.py'

Write-Host ''
Write-Host '  +------------------------------------------------------+' -ForegroundColor Cyan
Write-Host '  |    Phoenix Double Helix PoC -- Windows / Strand A    |' -ForegroundColor Cyan
Write-Host '  |    Helix-I ingress, channels 1-4, snapshot writer    |' -ForegroundColor Cyan
Write-Host '  +------------------------------------------------------+' -ForegroundColor Cyan
Write-Host ''

# -- Create shared page dir if missing ----------------------------------------
if (-not (Test-Path $PageDir)) {
    Write-Host "  [SETUP] Creating $PageDir"
    New-Item -ItemType Directory -Force -Path $PageDir | Out-Null
}
Write-Host "  [OK]    Page dir: $PageDir" -ForegroundColor Green

# -- Set environment ----------------------------------------------------------
$env:PHOENIX_SUITS           = $RepoRoot
$env:PHOENIX_HELIX_PAGE_DIR  = $PageDir
$env:PHOENIX_SECTOR1         = Join-Path $RepoRoot 'sector1'
$env:PHOENIX_SECTOR2         = Join-Path $RepoRoot 'sector2'
$env:PHOENIX_SECTOR3         = Join-Path $RepoRoot 'sector3'

# franken5.py reads these at import time; defaults are /tmp/ paths that don't
# exist on Windows. Point them at %TEMP% so import never fails.
$env:PHOENIX_AUDIT           = Join-Path $env:TEMP 'phoenix_audit.log'
$env:PHOENIX_SHM             = Join-Path $env:TEMP 'phoenix_shm'

# Add helix-lightning to PYTHONPATH so imports resolve if running outside poc/
$existing = $env:PYTHONPATH
if ($existing) {
    if ($existing -notlike "*$LightningDir*") {
        $env:PYTHONPATH = "$LightningDir;$existing"
    }
} else {
    $env:PYTHONPATH = $LightningDir
}

Write-Host "  [OK]    PHOENIX_SUITS=$env:PHOENIX_SUITS" -ForegroundColor Green
Write-Host "  [OK]    PHOENIX_HELIX_PAGE_DIR=$env:PHOENIX_HELIX_PAGE_DIR" -ForegroundColor Green
Write-Host ''
Write-Host '  Starting Helix-I (Strand A)...' -ForegroundColor White
Write-Host '  Listening on ports 7701-7704. Snapshot -> F:\Phoenix\helix-pages\windows_snapshot.json'
Write-Host ''
Write-Host '  To start Debian paging brain (Strand B watcher):' -ForegroundColor Cyan
Write-Host '    SSH into Debian: ssh -p 2222 phoenix@127.0.0.1'
Write-Host '    Then run:        bash /phoenix/Phoenix-DevOps-oS/tools/poc/run-helix-poc.sh'
Write-Host ''

# -- Launch -------------------------------------------------------------------
py -3 $Script
