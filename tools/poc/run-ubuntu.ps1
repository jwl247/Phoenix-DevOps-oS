#!/usr/bin/env pwsh
# =============================================================================
# run-ubuntu.ps1 — Phoenix Pro Demo: Boot Ubuntu from the clone pool
#
# The pro demo. Ubuntu 24.04 LTS. No installer. No wizard. No WSL. No Microsoft.
# Phoenix intaked this OS. Phoenix is running it.
# Same infrastructure as Debian. Different OS. One command.
#
# Usage:
#   pwsh -NoProfile -ExecutionPolicy Bypass -File tools/poc/run-ubuntu.ps1
#
# Or via usys:
#   usys run ubuntu
# =============================================================================

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent

Write-Host ''
Write-Host '  +------------------------------------------------------+' -ForegroundColor Cyan
Write-Host '  |         Phoenix DevOps OS -- Pro Demo                |' -ForegroundColor Cyan
Write-Host '  |         Ubuntu 24.04 LTS (Noble Numbat)              |' -ForegroundColor Cyan
Write-Host '  +------------------------------------------------------+' -ForegroundColor Cyan
Write-Host ''
Write-Host '  Ubuntu. On Windows. Launched by Phoenix.' -ForegroundColor White
Write-Host '  Not WSL. Not Hyper-V. Not a dual boot.' -ForegroundColor White
Write-Host '  Phoenix intaked this OS. Phoenix has the hex ID.' -ForegroundColor White
Write-Host '  Phoenix is running it right now.' -ForegroundColor White
Write-Host ''
Write-Host '  They said it could not be done.' -ForegroundColor DarkGray
Write-Host ''

$act = if ($args[0] -eq '2' -or $args[0] -eq '--hyperv') { '2' } else { '1' }

if ($act -eq '2') {
    Write-Host '  ACT 2 — Hyper-V enlightenments. Same image. Same hex ID. Full speed.' -ForegroundColor Yellow
    Write-Host '  Phoenix picked the accelerator. You typed one flag.' -ForegroundColor White
    Write-Host ''
    . (Join-Path $RepoRoot 'scripts\usys.ps1')
    usys run ubuntu --accel hyperv
} else {
    Write-Host '  ACT 1 — Pure software emulation. No hardware required. It just runs.' -ForegroundColor White
    Write-Host ''
    . (Join-Path $RepoRoot 'scripts\usys.ps1')
    usys run ubuntu --accel tcg
}
