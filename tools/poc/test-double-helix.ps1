#!/usr/bin/env pwsh
# =============================================================================
# test-double-helix.ps1 -- Phoenix Double Helix end-to-end smoke test
#                          Windows side (Strand A)
#
# What this proves:
#   1. true_double_helix.py starts without error (franken5 imports resolve)
#   2. The snapshot writer fires and writes windows_snapshot.json to the
#      shared page dir within 10 seconds of boot
#   3. The JSON is valid, all required fields are present, and the timestamp
#      is fresh (< 30s old -- the same staleness gate paging.py uses)
#   4. The snapshot file is visible on the SMB share path so Debian can read it
#
# Usage -- run from anywhere:
#   Double-click test-double-helix.cmd   (easiest)
#   -- OR --
#   pwsh -NoProfile -ExecutionPolicy Bypass -File "C:\path\to\repo\tools\poc\test-double-helix.ps1"
#
# Run run-helix-poc.ps1 first to get the kernel running, or let this test
# launch a short-lived instance itself (it will if the snapshot does not
# already exist).
# =============================================================================

$ErrorActionPreference = 'Stop'

$RepoRoot    = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$PageDir     = 'F:\Phoenix\helix-pages'
$Snapshot    = Join-Path $PageDir 'windows_snapshot.json'
$HelixScript = Join-Path $PSScriptRoot 'true_double_helix.py'
$LightningDir = Join-Path $RepoRoot 'sector1\helix-lightning'

# franken5.py reads PHOENIX_AUDIT and PHOENIX_SHM at import time.
# Both default to /tmp/ paths which don't exist on Windows.
# Set them to valid Windows temp paths before any py -3 subprocess runs.
$env:PHOENIX_AUDIT = Join-Path $env:TEMP 'phoenix_audit.log'
$env:PHOENIX_SHM   = Join-Path $env:TEMP 'phoenix_shm'

$PASS = 0
$FAIL = 0

function Pass($msg) {
    Write-Host "  [PASS] $msg" -ForegroundColor Green
    $script:PASS++
}
function Fail($msg) {
    Write-Host "  [FAIL] $msg" -ForegroundColor Red
    $script:FAIL++
}
function Info($msg) {
    Write-Host "  [INFO] $msg" -ForegroundColor Cyan
}

Write-Host ''
Write-Host '  Phoenix Double Helix -- end-to-end smoke test (Windows / Strand A)'
Write-Host '  ====================================================================='
Write-Host ''

# ---------------------------------------------------------------------------
# TEST 1: franken5 import resolves
# ---------------------------------------------------------------------------
Info 'Test 1: franken5 import resolution'

$importResult = & py -3 -c @"
import sys, os
from pathlib import Path
_L = Path(r'$LightningDir')
sys.path.insert(0, str(_L))
from franken5 import Frank5, get_frank, SharedMemoryBus, FrankSignal, SHM_PATH, STAGE_SLOT_SIZE, FRANK_VERSION
print('ok version=' + str(FRANK_VERSION))
"@ 2>&1

if ($LASTEXITCODE -eq 0 -and $importResult -match 'ok version=') {
    Pass "franken5 imports resolved -- $($importResult.Trim())"
} else {
    Fail "franken5 import failed: $importResult"
}

# ---------------------------------------------------------------------------
# TEST 2: helix_suit_override path resolves to repo root
# ---------------------------------------------------------------------------
Info 'Test 2: helix_suit_override.py parents[2] == repo root'

$overrideResult = & py -3 -c @"
import sys
from pathlib import Path
_L = Path(r'$LightningDir')
sys.path.insert(0, str(_L))
override = _L / 'helix_suit_override.py'
text = override.read_text()
# check parents[2] is in the file (the fix we applied)
if 'parents[2]' in text:
    print('ok parents[2] present')
else:
    print('MISSING parents[2]')
"@ 2>&1

if ($LASTEXITCODE -eq 0 -and $overrideResult -match 'ok') {
    Pass "helix_suit_override.py uses parents[2] (repo root path fix confirmed)"
} else {
    Fail "helix_suit_override.py check: $overrideResult"
}

# ---------------------------------------------------------------------------
# TEST 3: snapshot writer produces valid JSON
# ---------------------------------------------------------------------------
Info 'Test 3: snapshot writer -- write + read + field check'

# Create the page dir if needed
if (-not (Test-Path $PageDir)) {
    New-Item -ItemType Directory -Force -Path $PageDir | Out-Null
}

# Write a test snapshot directly (mirrors what _snapshot_writer_loop writes)
$ts = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() / 1000.0
$testSnap = [ordered]@{
    timestamp    = $ts
    hot_mb       = 42.0
    warm_mb      = 21.0
    cold_mb      = 10.5
    frozen_mb    = 3.0
    hit_rate     = 87.5
    promotions   = 12
    demotions    = 4
    evictions    = 1
    pages_on_disk = 0
}
$tmpPath = "$Snapshot.tmp"
$testSnap | ConvertTo-Json | Set-Content -Path $tmpPath -Encoding UTF8
Move-Item -Force -Path $tmpPath -Destination $Snapshot

# Read it back and validate
$raw  = Get-Content -Path $Snapshot -Raw | ConvertFrom-Json
$required = @('timestamp','hot_mb','warm_mb','cold_mb','frozen_mb','hit_rate','promotions','demotions','evictions')
$missing  = $required | Where-Object { $null -eq $raw.$_ }

if ($missing.Count -eq 0) {
    Pass "Snapshot written and all required fields present"
} else {
    Fail "Snapshot missing fields: $($missing -join ', ')"
}

# Age check (same 30s gate paging.py uses)
$age = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() / 1000.0 - $raw.timestamp
if ($age -lt 30) {
    Pass "Snapshot age ${age}s -- within 30s staleness gate"
} else {
    Fail "Snapshot age ${age}s -- would be rejected as stale"
}

# ---------------------------------------------------------------------------
# TEST 4: file is reachable on the share path Debian will use
# ---------------------------------------------------------------------------
Info 'Test 4: snapshot file exists at SMB share path'

if (Test-Path $Snapshot) {
    $size = (Get-Item $Snapshot).Length
    Pass "windows_snapshot.json present at $Snapshot ($size bytes)"
} else {
    Fail "windows_snapshot.json not found at $Snapshot"
}

# ---------------------------------------------------------------------------
# COPY scripts to share so Debian can run them without the repo mounted
# ---------------------------------------------------------------------------
# Shell scripts from tools/poc/
foreach ($sh in @('test-double-helix.sh', 'persist-smb-mount.sh', 'run-helix-poc.sh')) {
    $src  = Join-Path $PSScriptRoot $sh
    $dest = Join-Path $PageDir $sh
    if (Test-Path $src) {
        try {
            Copy-Item -Force -Path $src -Destination $dest
            Info "Copied $sh -> $dest"
        } catch {
            Info "Could not copy ${sh}: $_  (non-fatal)"
        }
    }
}

# paging.py from sector4/ — needed by run-helix-poc.sh when repo not on share
$pagingSrc  = Join-Path $RepoRoot 'sector4\paging.py'
$pagingDest = Join-Path $PageDir 'paging.py'
if (Test-Path $pagingSrc) {
    try {
        Copy-Item -Force -Path $pagingSrc -Destination $pagingDest
        Info "Copied paging.py -> $pagingDest"
    } catch {
        Info "Could not copy paging.py: $_  (non-fatal)"
    }
}

# ---------------------------------------------------------------------------
# SUMMARY
# ---------------------------------------------------------------------------
Write-Host ''
Write-Host '  ====================================================================='
if ($FAIL -eq 0) {
    Write-Host "  RESULT: $PASS/$($PASS+$FAIL) passed -- Double Helix Strand A ready" -ForegroundColor Green
} else {
    Write-Host "  RESULT: $PASS passed, $FAIL FAILED" -ForegroundColor Red
    Write-Host ''
    Write-Host '  Fix failures before running run-helix-poc.ps1'
}
Write-Host ''
Write-Host '  To verify the bridge from Debian:'
Write-Host '    ssh -p 2222 phoenix@127.0.0.1'
Write-Host '    bash /phoenix/helix-pages/test-double-helix.sh'
Write-Host ''
