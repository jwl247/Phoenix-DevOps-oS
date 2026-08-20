#!/usr/bin/env pwsh
# =============================================================================
# run-debian.ps1 — Phoenix Demo: Boot Debian from the clone pool
#
# This is the demo. No installer. No wizard. No WSL. No Microsoft.
# Phoenix intaked this OS. Phoenix is running it.
#
# Usage:
#   pwsh -NoProfile -ExecutionPolicy Bypass -File tools/poc/run-debian.ps1
#
# Or via usys:
#   usys run debian
# =============================================================================

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent

Write-Host ''
Write-Host '  +------------------------------------------------------+' -ForegroundColor Cyan
Write-Host '  |         Phoenix DevOps OS -- Distro Demo             |' -ForegroundColor Cyan
Write-Host '  |         Debian 12 (Bookworm)                         |' -ForegroundColor Cyan
Write-Host '  +------------------------------------------------------+' -ForegroundColor Cyan
Write-Host ''
Write-Host '  This OS was intaked by Phoenix.' -ForegroundColor White
Write-Host '  It has a hex ID. It lives in the clone pool.' -ForegroundColor White
Write-Host '  It runs anywhere Phoenix runs.' -ForegroundColor White
Write-Host '  No installer. No wizard. No WSL. Phoenix brings the OS.' -ForegroundColor White
Write-Host ''

. (Join-Path $RepoRoot 'scripts\usys.ps1')
usys run debian
