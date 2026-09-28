@echo off
REM ============================================================
REM Phoenix Global Command: status
REM Windows CMD wrapper for Phoenix Status Check
REM ============================================================

setlocal enabledelayedexpansion

REM Find Git Bash
set "BASH_EXE="
if exist "%ProgramFiles%\Git\bin\bash.exe" (
    set "BASH_EXE=%ProgramFiles%\Git\bin\bash.exe"
) else if exist "%ProgramFiles(x86)%\Git\bin\bash.exe" (
    set "BASH_EXE=%ProgramFiles(x86)%\Git\bin\bash.exe"
) else (
    where bash.exe >nul 2>&1
    if !errorlevel! equ 0 (
        for /f "tokens=*" %%i in ('where bash.exe') do set "BASH_EXE=%%i"
    )
)

if not defined BASH_EXE (
    echo [ERROR] Git Bash not found. Install: winget install Git.Git
    exit /b 1
)

REM Find Phoenix root
set "PHOENIX_ROOT=%PHOENIX_ROOT%"
if not defined PHOENIX_ROOT (
    if exist "%USERPROFILE%\Phoenix\Phoenix-DevOps-oS\status.sh" (
        set "PHOENIX_ROOT=%USERPROFILE%\Phoenix\Phoenix-DevOps-oS"
    )
)

if not defined PHOENIX_ROOT (
    echo [ERROR] PHOENIX_ROOT not set. Run install.ps1 first.
    exit /b 1
)

REM Find status.sh
set "STATUS_SH=%PHOENIX_ROOT%\status.sh"
if not exist "%STATUS_SH%" (
    echo [ERROR] status.sh not found at %STATUS_SH%
    exit /b 1
)

REM Convert Windows path to Git Bash path
set "STATUS_SH=%STATUS_SH:\=/%"
set "STATUS_SH=%STATUS_SH:C:=/c%"
set "STATUS_SH=%STATUS_SH:c:=/c%"

REM Execute status command
"%BASH_EXE%" -lc "bash '%STATUS_SH%' %*"

exit /b !errorlevel!

@REM Made with Bob
