#!/usr/bin/env pwsh
# =============================================================================
# demo-collab.ps1 — Phoenix Collaboration Demo (Windows side)
#
# This is the Windows half of the collaboration demo.
# Run AFTER demo-collab.sh has completed inside Debian.
#
# What this does:
#   1. Watches F:\Phoenix\Projects\ for demo-collab.ready (Debian's signal)
#   2. Reads and displays what Debian wrote
#   3. Intakes hello-phoenix.py through Phoenix (hex ID, QR, D1, R2)
#   4. Promotes it as a runnable suite
#   5. Runs it — on Windows — proving the round trip
#
# Prerequisites:
#   - usys init done (PHOENIX_AUTH, PHOENIX_WORKER_URL set)
#   - Debian has run demo-collab.sh (files are in F:\Phoenix\Projects\)
#   - Git Bash installed (for the bash intake pipeline)
#
# Usage:
#   pwsh -NoProfile -ExecutionPolicy Bypass -File tools\poc\demo-collab.ps1
#   -- or --
#   . scripts\usys.ps1; usys run demo-collab
# =============================================================================

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
. (Join-Path $RepoRoot 'scripts\usys.ps1')

$ShareProjects = 'F:\Phoenix\Projects'
$ReadyFile     = Join-Path $ShareProjects 'demo-collab.ready'
$ScriptFile    = Join-Path $ShareProjects 'hello-phoenix.py'
$OutputFile    = Join-Path $ShareProjects 'output.txt'

# ── Banner ────────────────────────────────────────────────────────────────────
Write-Host ''
Write-Host '  +----------------------------------------------------------+' -ForegroundColor Cyan
Write-Host '  |     Phoenix Collaboration Demo — Windows side            |' -ForegroundColor Cyan
Write-Host '  |     Debian wrote it. Windows intakes it. Both run it.    |' -ForegroundColor Cyan
Write-Host '  +----------------------------------------------------------+' -ForegroundColor Cyan
Write-Host ''

# ── Step 1: check for Debian's ready signal ───────────────────────────────────
Write-Host '  Step 1 — Checking for Debian signal...' -ForegroundColor Yellow
Write-Host ''

if (-not (Test-Path $ReadyFile)) {
    Write-Host '  Waiting for demo-collab.ready from Debian...' -ForegroundColor DarkGray
    $waited = 0
    while (-not (Test-Path $ReadyFile) -and $waited -lt 60) {
        Start-Sleep -Seconds 2
        $waited += 2
        Write-Host "  ...waiting ($waited s)" -ForegroundColor DarkGray
    }
    if (-not (Test-Path $ReadyFile)) {
        Write-Host ''
        Write-Host '  Timed out. Run demo-collab.sh on Debian first:' -ForegroundColor Red
        Write-Host '    bash /phoenix/Projects/demo-collab.sh' -ForegroundColor White
        Write-Host ''
        exit 1
    }
}

Write-Host '  Debian signal received.' -ForegroundColor Green
$manifest = Get-Content $ReadyFile -Raw
Write-Host ''
Write-Host '  --- Manifest from Debian ---' -ForegroundColor DarkGray
$manifest -split "`n" | Where-Object { $_.Trim() } | ForEach-Object {
    Write-Host "    $_" -ForegroundColor DarkGray
}
Write-Host ''

# ── Step 2: show what Debian produced ────────────────────────────────────────
Write-Host '  Step 2 — Reading Debian output from shared FS...' -ForegroundColor Yellow
Write-Host ''

if (Test-Path $OutputFile) {
    Write-Host '  --- output.txt (written by Debian, read by Windows) ---' -ForegroundColor Cyan
    Get-Content $OutputFile | ForEach-Object { Write-Host "  $_" -ForegroundColor White }
    Write-Host ''
    Write-Host '  Same file. No copy. No sync. QEMU bridges the FS.' -ForegroundColor Green
} else {
    Write-Host '  output.txt not found — did Debian run successfully?' -ForegroundColor Red
}
Write-Host ''

# ── Step 3: intake hello-phoenix.py through Phoenix ──────────────────────────
Write-Host '  Step 3 — Intaking hello-phoenix.py through Phoenix...' -ForegroundColor Yellow
Write-Host '  (hex ID · QR · D1 record · R2 upload)' -ForegroundColor DarkGray
Write-Host ''

if (-not (Test-Path $ScriptFile)) {
    Write-Host "  Script not found: $ScriptFile" -ForegroundColor Red
    Write-Host '  Run demo-collab.sh on Debian first.' -ForegroundColor White
    exit 1
}

Invoke-PhxImport -Path $ScriptFile

Write-Host ''

# ── Step 4: promote as a runnable suite ──────────────────────────────────────
Write-Host '  Step 4 — Promoting as a runnable Phoenix suite...' -ForegroundColor Yellow
Write-Host ''

Invoke-UsysSuitePromote -Name 'hello-phoenix' -Desc 'Written on Debian. Intaked on Windows. Runs anywhere Phoenix runs.'

Write-Host ''

# ── Step 5: run it on Windows ────────────────────────────────────────────────
Write-Host '  Step 5 — Running hello-phoenix on Windows...' -ForegroundColor Yellow
Write-Host '  (same script, same hex ID, different OS)' -ForegroundColor DarkGray
Write-Host ''

Invoke-UsysRun -SuiteName 'hello-phoenix'

# ── Final ─────────────────────────────────────────────────────────────────────
Write-Host ''
Write-Host '  +----------------------------------------------------------+' -ForegroundColor Green
Write-Host '  |  ROUND TRIP COMPLETE                                     |' -ForegroundColor Green
Write-Host '  |                                                          |' -ForegroundColor Green
Write-Host '  |  Written on Debian.  Shared via QEMU.                   |' -ForegroundColor Green
Write-Host '  |  Intaked on Windows. Hex ID issued. D1 record created.  |' -ForegroundColor Green
Write-Host '  |  Ran on Windows.     Same script. Same bytes.           |' -ForegroundColor Green
Write-Host '  |                                                          |' -ForegroundColor Green
Write-Host '  |  No install. No wizard. No WSL.                         |' -ForegroundColor Green
Write-Host '  |  Phoenix brought the OS. Phoenix ran the script.        |' -ForegroundColor Green
Write-Host '  +----------------------------------------------------------+' -ForegroundColor Green
Write-Host ''
Write-Host '  usys list-suites   — see hello-phoenix in the pool' -ForegroundColor DarkGray
Write-Host '  usys run hello-phoenix   — run it again any time' -ForegroundColor DarkGray
Write-Host '  phx-ls Projects   — see what else Debian left in the share' -ForegroundColor DarkGray
Write-Host ''
