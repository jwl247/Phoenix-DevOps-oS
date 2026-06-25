#!/usr/bin/env pwsh
# Phoenix Dashboard - Complete Automated Setup
# This script will set up everything you need and launch the dashboard

$ErrorActionPreference = 'Stop'

Write-Host ""
Write-Host "  ╔═══════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "  ║   Phoenix DevOps OS Dashboard                    ║" -ForegroundColor Cyan
Write-Host "  ║   Complete Automated Setup                       ║" -ForegroundColor Cyan
Write-Host "  ╚═══════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# Step 1: Check Node.js
Write-Host "[1/5] Checking Node.js..." -ForegroundColor Yellow
$node = Get-Command node -ErrorAction SilentlyContinue
if (-not $node) {
    Write-Host "  ✗ Node.js not found!" -ForegroundColor Red
    Write-Host ""
    Write-Host "  Installing Node.js via winget..." -ForegroundColor Yellow
    
    try {
        winget install OpenJS.NodeJS --silent --accept-package-agreements --accept-source-agreements
        Write-Host "  ✓ Node.js installed!" -ForegroundColor Green
        Write-Host "  → Please close this terminal and run setup.ps1 again" -ForegroundColor Yellow
        Write-Host ""
        pause
        exit 0
    } catch {
        Write-Host "  ✗ Auto-install failed. Please install manually:" -ForegroundColor Red
        Write-Host "  → Download from: https://nodejs.org" -ForegroundColor White
        Write-Host "  → Or run: winget install OpenJS.NodeJS" -ForegroundColor White
        Write-Host ""
        pause
        exit 1
    }
}

$nodeVersion = & node --version
Write-Host "  ✓ Node.js $nodeVersion" -ForegroundColor Green

# Step 2: Verify files
Write-Host ""
Write-Host "[2/5] Verifying dashboard files..." -ForegroundColor Yellow

$requiredFiles = @(
    'index.html',
    'styles.css',
    'dashboard.js',
    'main.js',
    'package.json'
)

$allFilesPresent = $true
foreach ($file in $requiredFiles) {
    if (Test-Path $file) {
        $size = (Get-Item $file).Length
        if ($size -gt 0) {
            Write-Host "  ✓ $file ($size bytes)" -ForegroundColor Green
        } else {
            Write-Host "  ✗ $file is empty!" -ForegroundColor Red
            $allFilesPresent = $false
        }
    } else {
        Write-Host "  ✗ $file not found!" -ForegroundColor Red
        $allFilesPresent = $false
    }
}

if (-not $allFilesPresent) {
    Write-Host ""
    Write-Host "  ✗ Some files are missing or empty!" -ForegroundColor Red
    Write-Host "  → Please ensure all dashboard files are present" -ForegroundColor Yellow
    Write-Host ""
    pause
    exit 1
}

# Step 3: Install dependencies
Write-Host ""
Write-Host "[3/5] Installing dependencies..." -ForegroundColor Yellow
Write-Host "  → This may take 1-2 minutes on first run..." -ForegroundColor DarkGray

if (Test-Path "node_modules") {
    Write-Host "  → node_modules exists, checking..." -ForegroundColor DarkGray
}

try {
    $output = & npm install 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  ✓ Dependencies installed successfully" -ForegroundColor Green
    } else {
        Write-Host "  ✗ npm install failed!" -ForegroundColor Red
        Write-Host $output
        pause
        exit 1
    }
} catch {
    Write-Host "  ✗ Error during npm install: $_" -ForegroundColor Red
    pause
    exit 1
}

# Step 4: Check Phoenix environment
Write-Host ""
Write-Host "[4/5] Checking Phoenix environment..." -ForegroundColor Yellow

if ($env:PHOENIX_ROOT) {
    Write-Host "  ✓ PHOENIX_ROOT: $env:PHOENIX_ROOT" -ForegroundColor Green
} else {
    Write-Host "  ⚠ PHOENIX_ROOT not set" -ForegroundColor Yellow
    $defaultRoot = Join-Path $HOME "Phoenix\Phoenix-DevOps-oS"
    if (Test-Path $defaultRoot) {
        Write-Host "  → Found Phoenix at: $defaultRoot" -ForegroundColor Green
        $env:PHOENIX_ROOT = $defaultRoot
    } else {
        Write-Host "  → Will use default paths" -ForegroundColor DarkGray
    }
}

if ($env:CLONEPOOL_DIR) {
    Write-Host "  ✓ CLONEPOOL_DIR: $env:CLONEPOOL_DIR" -ForegroundColor Green
} else {
    Write-Host "  ⚠ CLONEPOOL_DIR not set" -ForegroundColor Yellow
    $defaultClonepool = Join-Path $HOME "Phoenix\clonepool"
    if (Test-Path $defaultClonepool) {
        Write-Host "  → Found clonepool at: $defaultClonepool" -ForegroundColor Green
        $env:CLONEPOOL_DIR = $defaultClonepool
    } else {
        Write-Host "  → Will use default paths" -ForegroundColor DarkGray
    }
}

# Check if usys command is available
$usys = Get-Command usys -ErrorAction SilentlyContinue
if ($usys) {
    Write-Host "  ✓ usys command available" -ForegroundColor Green
} else {
    Write-Host "  ⚠ usys command not found in PATH" -ForegroundColor Yellow
    Write-Host "  → Dashboard will work but may show simulated data" -ForegroundColor DarkGray
}

# Step 5: Launch
Write-Host ""
Write-Host "[5/5] Setup complete!" -ForegroundColor Green
Write-Host ""
Write-Host "  ╔═══════════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "  ║   🚀 Launching Phoenix Dashboard...              ║" -ForegroundColor Green
Write-Host "  ╚═══════════════════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""
Write-Host "  The dashboard will open in a new window." -ForegroundColor White
Write-Host "  Press Ctrl+C in this terminal to stop the dashboard." -ForegroundColor DarkGray
Write-Host ""

Start-Sleep -Seconds 2

# Launch the dashboard
& npm start

# Made with Bob
