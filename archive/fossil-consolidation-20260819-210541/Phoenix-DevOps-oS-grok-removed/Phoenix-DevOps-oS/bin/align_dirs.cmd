@echo off
REM ============================================================
REM Phoenix Global Command: align_dirs
REM Windows CMD wrapper for Phoenix Directory Alignment
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
    if exist "%USERPROFILE%\Phoenix\Phoenix-DevOps-oS\tools\align_dirs.sh" (
        set "PHOENIX_ROOT=%USERPROFILE%\Phoenix\Phoenix-DevOps-oS"
    )
)

if not defined PHOENIX_ROOT (
    echo [ERROR] PHOENIX_ROOT not set. Run install.ps1 first.
    exit /b 1
)

REM Find align_dirs.sh
set "ALIGN_SH=%PHOENIX_ROOT%\tools\align_dirs.sh"
if not exist "%ALIGN_SH%" (
    echo [ERROR] align_dirs.sh not found at %ALIGN_SH%
    exit /b 1
)

REM Convert Windows path to Git Bash path
set "ALIGN_SH=%ALIGN_SH:\=/%"
set "ALIGN_SH=%ALIGN_SH:C:=/c%"
set "ALIGN_SH=%ALIGN_SH:c:=/c%"

REM Execute align_dirs command
"%BASH_EXE%" -lc "bash '%ALIGN_SH%' %*"

exit /b !errorlevel!

@REM Made with Bob
