@echo off
REM ============================================================
REM Phoenix Global Command: usys
REM Windows CMD wrapper for USys (United Systems)
REM ============================================================

setlocal enabledelayedexpansion

REM Find PowerShell 7
set "PWSH_EXE="
if exist "%ProgramFiles%\PowerShell\7\pwsh.exe" (
    set "PWSH_EXE=%ProgramFiles%\PowerShell\7\pwsh.exe"
) else if exist "%ProgramFiles(x86)%\PowerShell\7\pwsh.exe" (
    set "PWSH_EXE=%ProgramFiles(x86)%\PowerShell\7\pwsh.exe"
) else (
    where pwsh.exe >nul 2>&1
    if !errorlevel! equ 0 (
        for /f "tokens=*" %%i in ('where pwsh.exe') do set "PWSH_EXE=%%i"
    )
)

if not defined PWSH_EXE (
    echo [ERROR] PowerShell 7 not found. Install: winget install Microsoft.PowerShell
    exit /b 1
)

REM Load Phoenix environment if available
if exist "%USERPROFILE%\.phoenix_env.ps1" (
    "%PWSH_EXE%" -NoProfile -ExecutionPolicy Bypass -Command ". '%USERPROFILE%\.phoenix_env.ps1'" >nul 2>&1
)

REM Find Phoenix root
set "PHOENIX_ROOT=%PHOENIX_ROOT%"
if not defined PHOENIX_ROOT (
    if exist "%USERPROFILE%\Phoenix\Phoenix-DevOps-oS\scripts\usys.ps1" (
        set "PHOENIX_ROOT=%USERPROFILE%\Phoenix\Phoenix-DevOps-oS"
    )
)

if not defined PHOENIX_ROOT (
    echo [ERROR] PHOENIX_ROOT not set. Run install.ps1 first.
    exit /b 1
)

REM Execute usys command
"%PWSH_EXE%" -NoProfile -ExecutionPolicy Bypass -Command ^
    ". '%PHOENIX_ROOT%\scripts\usys.ps1'; usys %*"

exit /b !errorlevel!

@REM Made with Bob
