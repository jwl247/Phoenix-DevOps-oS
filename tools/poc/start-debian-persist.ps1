# start-debian-persist.ps1
# Always boots Debian with persistence + shared FS so Helix + /phoenix survive reboots

$ErrorActionPreference = 'Stop'

# Walk up from tools/poc → tools → repo root
$RepoRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent

. (Join-Path $RepoRoot 'scripts\usys.ps1')

Write-Host ''
Write-Host '  Phoenix: Debian (persistent + shared FS)' -ForegroundColor Cyan
Write-Host '  Helix kernel will start on both sides via /phoenix' -ForegroundColor White
Write-Host ''

# -Persist  = keep changes in the qcow2
# --share   = enable F:\Phoenix → /phoenix
usys run debian -Persist --share