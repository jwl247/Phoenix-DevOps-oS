#!/usr/bin/env pwsh
# =============================================================================
# setup-shared-fs.ps1 — Phoenix Shared Filesystem Bootstrap
#
# One-time idempotent setup. Run once; safe to repeat.
# Creates F:\Phoenix\{Desktop,Documents,Downloads,Projects,Vault},
# stamps each with a _PHOENIX_DIR.txt marker, prints the full mount table,
# and wires the profile if not already wired.
#
# No elevation required. No writes to C: except $PROFILE (via usys init).
# All new filesystem activity confined to F:\Phoenix\.
#
# Usage:
#   pwsh -NoProfile -ExecutionPolicy Bypass -File tools\poc\setup-shared-fs.ps1
#
# Or via usys:
#   usys fs-init
# =============================================================================

$ErrorActionPreference = 'Stop'

# Resolve repo root: this script lives at tools\poc\, so go up two levels.
$RepoRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent

# Dot-source usys.ps1 to get $script:PhxSharedRoot, $script:PhxSharedDirs,
# Write-PhxFsBanner, and the phx- wrapper functions.
. (Join-Path $RepoRoot 'scripts\usys.ps1')

Write-Host ''
Write-PhxFsBanner
Write-Host ''
Write-Host '  Phoenix Shared Filesystem — One-time setup' -ForegroundColor Cyan
Write-Host '  Windows hosts F:\Phoenix\   Debian mounts /phoenix/ via QEMU virtio-9p' -ForegroundColor White
Write-Host ''

# =============================================================================
# 1. Create canonical shared directories
# =============================================================================
Write-Host '  Creating shared directories...' -ForegroundColor Yellow
foreach ($dir in $script:PhxSharedDirs) {
    $fullPath = Join-Path $script:PhxSharedRoot $dir
    if (-not (Test-Path $fullPath)) {
        New-Item -ItemType Directory -Path $fullPath -Force | Out-Null
        Write-Host "    created  $fullPath" -ForegroundColor Green
    } else {
        Write-Host "    exists   $fullPath" -ForegroundColor DarkGray
    }

    # Stamp a marker file so the directory is identifiable from Debian.
    $markerPath = Join-Path $fullPath '_PHOENIX_DIR.txt'
    if (-not (Test-Path $markerPath)) {
        $tag = "phoenix-$($dir.ToLower())"
        @"
Phoenix shared directory
name      : $dir
mount_tag : $tag
debian    : /phoenix/$dir
created   : $(Get-Date -Format 'yyyy-MM-ddTHH:mm:ssZ')
host      : Windows — $script:PhxSharedRoot
note      : All operations through phx-import / phx-export / phx-sync / phx-ls
"@ | Set-Content $markerPath -Encoding UTF8
        Write-Host "    marker   $markerPath" -ForegroundColor DarkGray
    }
}

# =============================================================================
# 2. Print the mount table
# =============================================================================
Write-Host ''
Write-Host '  Mount table (QEMU -virtfs tag contract):' -ForegroundColor Yellow
Write-Host ''
Write-Host '  Windows path              virtio-9p tag          Debian path' -ForegroundColor White
Write-Host '  ------------------------  ---------------------  ----------------------' -ForegroundColor DarkGray
foreach ($dir in $script:PhxSharedDirs) {
    $winPath = Join-Path $script:PhxSharedRoot $dir
    $tag     = "phoenix-$($dir.ToLower())"
    $deb     = "/phoenix/$dir"
    Write-Host ("  {0,-24}  {1,-21}  {2}" -f $winPath, $tag, $deb)
}
Write-Host ''

# =============================================================================
# 3. Wire profile if not already done
# =============================================================================
$profileContent = if (Test-Path $PROFILE.CurrentUserAllHosts) {
    Get-Content $PROFILE.CurrentUserAllHosts -Raw -ErrorAction SilentlyContinue
} else { '' }

if ($profileContent -notmatch 'Phoenix USys') {
    Write-Host '  Profile not wired — running usys init...' -ForegroundColor Yellow
    usys init
} else {
    Write-Host '  Profile already wired — phx-import/export/sync/ls available in every terminal.' -ForegroundColor Green
}

Write-Host ''
Write-Host '  Setup complete.' -ForegroundColor Green
Write-Host '  Run Debian with shared FS: usys run debian --share' -ForegroundColor Cyan
Write-Host '  Run with full speed + FS : usys run debian --accel hyperv --share' -ForegroundColor Cyan
Write-Host ''
