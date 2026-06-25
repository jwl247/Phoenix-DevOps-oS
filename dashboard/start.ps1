#!/usr/bin/env pwsh
# Phoenix Dashboard - Quick Start Script
# Checks dependencies and launches the Electron app

$ErrorActionPreference = 'Stop'

Write-Host ""
Write-Host "  ╔═══════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "  ║   Phoenix DevOps OS Dashboard        ║" -ForegroundColor Cyan
Write-Host "  ║   Electron Quick Start               ║" -ForegroundColor Cyan
Write-Host "  ╚═══════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# Check if Node.js is installed
Write-Host "[1/3] Checking Node.js..." -ForegroundColor Yellow
$node = Get-Command node -ErrorAction SilentlyContinue
if (-not $node) {
    Write-Host "  ✗ Node.js not found!" -ForegroundColor Red
    Write-Host ""
    Write-Host "  Please install Node.js:" -ForegroundColor Yellow
    Write-Host "  1. Download from: https://nodejs.org" -ForegroundColor White
    Write-Host "  2. Or run: winget install OpenJS.NodeJS" -ForegroundColor White
    Write-Host ""
    exit 1
}
$nodeVersion = & node --version
Write-Host "  ✓ Node.js $nodeVersion" -ForegroundColor Green

# Check if npm is installed
$npm = Get-Command npm -ErrorAction SilentlyContinue
if (-not $npm) {
    Write-Host "  ✗ npm not found!" -ForegroundColor Red
    exit 1
}
$npmVersion = & npm --version
Write-Host "  ✓ npm $npmVersion" -ForegroundColor Green

# Check if dependencies are installed
Write-Host ""
Write-Host "[2/3] Checking dependencies..." -ForegroundColor Yellow
if (-not (Test-Path "node_modules")) {
    Write-Host "  → Installing dependencies (this may take a minute)..." -ForegroundColor Yellow
    & npm install
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  ✗ Failed to install dependencies" -ForegroundColor Red
        exit 1
    }
    Write-Host "  ✓ Dependencies installed" -ForegroundColor Green
} else {
    Write-Host "  ✓ Dependencies already installed" -ForegroundColor Green
}

# Check Phoenix environment
Write-Host ""
Write-Host "[3/3] Checking Phoenix environment..." -ForegroundColor Yellow
if ($env:PHOENIX_ROOT) {
    Write-Host "  ✓ PHOENIX_ROOT: $env:PHOENIX_ROOT" -ForegroundColor Green
} else {
    Write-Host "  ⚠ PHOENIX_ROOT not set (will use defaults)" -ForegroundColor Yellow
}

if ($env:CLONEPOOL_DIR) {
    Write-Host "  ✓ CLONEPOOL_DIR: $env:CLONEPOOL_DIR" -ForegroundColor Green
} else {
    Write-Host "  ⚠ CLONEPOOL_DIR not set (will use defaults)" -ForegroundColor Yellow
}

# Launch the app
Write-Host ""
Write-Host "  🚀 Launching Phoenix Dashboard..." -ForegroundColor Cyan
Write-Host ""
Write-Host "  Press Ctrl+C to stop the dashboard" -ForegroundColor DarkGray
Write-Host ""

& npm start

# Made with Bob
