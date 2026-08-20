#Requires -Version 5.1
# ============================================================
# LOL Bootstrap Installer for Windows
# Ultra-minimal installer that enables: lol install <package>
# ============================================================

$ErrorActionPreference = 'Stop'

Write-Host ""
Write-Host "  🔥 LOL Bootstrap Installer" -ForegroundColor Cyan
Write-Host "  Installing minimal LOL command..." -ForegroundColor Cyan
Write-Host ""

# Create LOL directory
$LOL_HOME = Join-Path $HOME '.lol'
$LOL_BIN = Join-Path $LOL_HOME 'bin'
New-Item -ItemType Directory -Force -Path $LOL_BIN | Out-Null

# Create lol.cmd wrapper
$lolCmd = Join-Path $LOL_BIN 'lol.cmd'
@'
@echo off
setlocal enabledelayedexpansion

if "%1"=="" goto :usage
if "%1"=="install" goto :install
if "%1"=="help" goto :usage
if "%1"=="--help" goto :usage

:usage
echo.
echo   LOL - Live Ops Loader
echo   Ultra-simple package installer
echo.
echo   Usage:
echo     lol install ^<package^>
echo     lol help
echo.
echo   Examples:
echo     lol install phoenix-devops-os
echo     lol install phoenix-package-handler
echo.
exit /b 0

:install
if "%2"=="" (
    echo [ERROR] Package name required
    echo Usage: lol install ^<package^>
    exit /b 1
)

set "PACKAGE=%2"
echo.
echo   [LOL] Installing: %PACKAGE%
echo.

REM Package registry
if /i "%PACKAGE%"=="phoenix-devops-os" (
    set "INSTALL_URL=https://raw.githubusercontent.com/jwl247/Phoenix-DevOps-oS/main/install.ps1"
) else if /i "%PACKAGE%"=="phoenix-package-handler" (
    set "INSTALL_URL=https://raw.githubusercontent.com/jwl247/Phoenix-Package_handler/main/install.ps1"
) else (
    echo [ERROR] Unknown package: %PACKAGE%
    echo.
    echo Available packages:
    echo   - phoenix-devops-os
    echo   - phoenix-package-handler
    echo.
    exit /b 1
)

REM Find PowerShell
set "PWSH_EXE="
if exist "%ProgramFiles%\PowerShell\7\pwsh.exe" (
    set "PWSH_EXE=%ProgramFiles%\PowerShell\7\pwsh.exe"
) else (
    where pwsh.exe >nul 2>&1
    if !errorlevel! equ 0 (
        for /f "tokens=*" %%i in ('where pwsh.exe') do set "PWSH_EXE=%%i"
    ) else (
        set "PWSH_EXE=powershell.exe"
    )
)

REM Execute installer
"%PWSH_EXE%" -ExecutionPolicy Bypass -Command "irm %INSTALL_URL% | iex"

if !errorlevel! equ 0 (
    echo.
    echo   [LOL] Installation complete!
    echo.
) else (
    echo.
    echo   [LOL] Installation failed
    echo.
    exit /b 1
)

exit /b 0
'@ | Set-Content -Path $lolCmd -Encoding ASCII

Write-Host "  ✅ Created: lol.cmd" -ForegroundColor Green

# Add to PATH
$userPath = [Environment]::GetEnvironmentVariable('PATH', 'User')
if ($userPath -notlike "*$LOL_BIN*") {
    $newPath = if ($userPath) { "$userPath;$LOL_BIN" } else { $LOL_BIN }
    [Environment]::SetEnvironmentVariable('PATH', $newPath, 'User')
    $env:PATH = "$LOL_BIN;$env:PATH"
    Write-Host "  ✅ Added to PATH" -ForegroundColor Green
} else {
    Write-Host "  ℹ️  Already in PATH" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "  =====================================" -ForegroundColor Green
Write-Host "   LOL Bootstrap Complete!" -ForegroundColor Green
Write-Host "  =====================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Open a NEW terminal and run:" -ForegroundColor Yellow
Write-Host "    lol install phoenix-devops-os" -ForegroundColor Cyan
Write-Host ""

# Made with Bob
