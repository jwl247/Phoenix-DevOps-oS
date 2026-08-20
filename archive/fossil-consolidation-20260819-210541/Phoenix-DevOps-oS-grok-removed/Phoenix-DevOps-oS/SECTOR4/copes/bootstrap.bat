@echo off
echo Starting CoPES Bootstrap with PowerShell 7...
echo.

REM Try to find pwsh.exe (PowerShell 7)
where pwsh >nul 2>nul
if %errorlevel% neq 0 (
    echo ERROR: PowerShell 7 (pwsh) was not found.
    echo Please install PowerShell 7 and try again.
    pause
    exit /b 1
)

REM Run the bootstrap script in PowerShell 7
pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0install\bootstrap.ps1"

echo.
echo Bootstrap finished. Press any key to close this window.
pause >nul
