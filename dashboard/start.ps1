#!/usr/bin/env pwsh
# Phoenix Dashboard - Quick Start Script
# Checks dependencies and launches the Electron app

param([switch]$NoElevate)

$ErrorActionPreference = 'Stop'

# Always run from the dashboard directory regardless of where the script was invoked from
Set-Location $PSScriptRoot

# --- Platform admin by default -----------------------------------------------
# The dashboard is the Phoenix control plane: pagefile / drive / service ops
# (main.js isElevated() gates) and the embedded SHELL + CLAUDE panes need
# Administrator to be useful. Self-elevate once at launch so there is no
# mid-session UAC wall. Opt out: -NoElevate, or set PHOENIX_NO_ELEVATE=1.
# The autostart Scheduled Task runs with RunLevel Highest, so it lands here
# already elevated and this block is a no-op (no logon-time prompt).
# Elevation raises what the main process and its shells can do; the renderer
# stays locked down (contextIsolation, no nodeIntegration) either way.
$__phxAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $__phxAdmin -and -not $NoElevate -and -not $env:PHOENIX_NO_ELEVATE) {
    Write-Host "  [PHX] Elevating to Administrator (-NoElevate / PHOENIX_NO_ELEVATE=1 to skip)..." -ForegroundColor Yellow
    $__hostExe = (Get-Process -Id $PID).Path
    if (-not $__hostExe) { $__hostExe = 'pwsh.exe' }
    try {
        Start-Process -FilePath $__hostExe -Verb RunAs -WorkingDirectory $PSScriptRoot `
            -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $PSCommandPath)
        exit 0
    } catch {
        Write-Host "  [PHX] Elevation declined - continuing unelevated; admin-only panels disabled." -ForegroundColor DarkYellow
    }
}

# Load ~/.phoenix/phoenix.env (same file systemd / Scheduled Task uses)
$envFile = Join-Path $HOME '.phoenix\phoenix.env'
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        $line = $_.Trim()
        if ($line -eq '' -or $line.StartsWith('#')) { return }
        $idx = $line.IndexOf('=')
        if ($idx -lt 1) { return }
        $key = $line.Substring(0, $idx).Trim()
        $val = $line.Substring($idx + 1).Trim().Trim('"').Trim("'")
        if (-not [string]::IsNullOrEmpty($key)) {
            $current = [Environment]::GetEnvironmentVariable($key, 'Process')
            if ([string]::IsNullOrEmpty($current)) {
                [Environment]::SetEnvironmentVariable($key, $val, 'Process')
            }
        }
    }
    Write-Host "  [OK] Loaded $envFile" -ForegroundColor DarkGray
}

if (-not $env:PHOENIX_AI_PROVIDER) {
    $env:PHOENIX_AI_PROVIDER = 'helpdesk'
}
if (-not $env:PHOENIX_SKIP_AUTH_MODAL) {
    $env:PHOENIX_SKIP_AUTH_MODAL = '1'
}

# GPU fix for junction / network-share launches (Favorites\ path).
# error_code=18 = SBOX_ERROR_CREATE_PROCESS: the GPU child never spawns when
# Electron runs from a junction or mapped drive. --disable-gpu-sandbox is the
# confirmed fix (Electron issues 36698, 31659; open-webui#110).
# Do NOT combine with --in-process-gpu + --disable-software-rasterizer:
# that trio crashes with 'Validating command decoder is not supported'
# (Electron issue 42688). Keep software rasterizer ON so acrylic/mica glass
# still has a compositor to blur against.
$env:ELECTRON_EXTRA_LAUNCH_ARGS = "--disable-gpu-sandbox"

Write-Host ""
Write-Host "  +---------------------------------------+" -ForegroundColor Cyan
Write-Host "  |   Phoenix DevOps OS Dashboard        |" -ForegroundColor Cyan
Write-Host "  |   Electron Quick Start               |" -ForegroundColor Cyan
Write-Host "  +---------------------------------------+" -ForegroundColor Cyan
Write-Host ""

# Check if Node.js is installed
Write-Host "[1/3] Checking Node.js..." -ForegroundColor Yellow
$node = Get-Command node -ErrorAction SilentlyContinue
if (-not $node) {
    Write-Host "  [FAIL] Node.js not found!" -ForegroundColor Red
    Write-Host ""
    Write-Host "  Please install Node.js:" -ForegroundColor Yellow
    Write-Host "  1. Download from: https://nodejs.org" -ForegroundColor White
    Write-Host "  2. Or run: winget install OpenJS.NodeJS" -ForegroundColor White
    Write-Host ""
    exit 1
}
$nodeVersion = & node --version
Write-Host "  [OK] Node.js $nodeVersion" -ForegroundColor Green

# Check if npm is installed
$npm = Get-Command npm -ErrorAction SilentlyContinue
if (-not $npm) {
    Write-Host "  [FAIL] npm not found!" -ForegroundColor Red
    exit 1
}
$npmVersion = & npm --version
Write-Host "  [OK] npm $npmVersion" -ForegroundColor Green

# Check if dependencies are installed
Write-Host ""
Write-Host "[2/3] Checking dependencies..." -ForegroundColor Yellow
if (-not (Test-Path "node_modules")) {
    Write-Host "  --> Installing dependencies (this may take a minute)..." -ForegroundColor Yellow
    & npm install
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  [FAIL] Failed to install dependencies" -ForegroundColor Red
        exit 1
    }
    Write-Host "  [OK] Dependencies installed" -ForegroundColor Green
} else {
    Write-Host "  [OK] Dependencies already installed" -ForegroundColor Green
}

# Check Phoenix environment
Write-Host ""
Write-Host "[3/3] Checking Phoenix environment..." -ForegroundColor Yellow
if ($env:PHOENIX_ROOT) {
    Write-Host "  [OK] PHOENIX_ROOT: $env:PHOENIX_ROOT" -ForegroundColor Green
} else {
    Write-Host "  [WARN] PHOENIX_ROOT not set (will use defaults)" -ForegroundColor Yellow
}

if ($env:CLONEPOOL_DIR) {
    Write-Host "  [OK] CLONEPOOL_DIR: $env:CLONEPOOL_DIR" -ForegroundColor Green
} else {
    Write-Host "  [WARN] CLONEPOOL_DIR not set (will use defaults)" -ForegroundColor Yellow
}

# Launch the app
Write-Host ""
Write-Host "  >>> Launching Phoenix Dashboard..." -ForegroundColor Cyan
Write-Host ""
Write-Host "  Press Ctrl+C to stop the dashboard" -ForegroundColor DarkGray
Write-Host ""

& npm start
