@echo off
REM ============================================================
REM Phoenix Global Command: get_distros
REM Windows CMD wrapper for Phoenix Distribution Detection
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
    if exist "%USERPROFILE%\Phoenix\Phoenix-DevOps-oS\tools\get_distros.sh" (
        set "PHOENIX_ROOT=%USERPROFILE%\Phoenix\Phoenix-DevOps-oS"
    )
)

if not defined PHOENIX_ROOT (
    echo [ERROR] PHOENIX_ROOT not set. Run install.ps1 first.
    exit /b 1
)

REM Find get_distros.sh
set "DISTROS_SH=%PHOENIX_ROOT%\tools\get_distros.sh"
if not exist "%DISTROS_SH%" (
    echo [ERROR] get_distros.sh not found at %DISTROS_SH%
    exit /b 1
)

REM Convert Windows path to Git Bash path
set "DISTROS_SH=%DISTROS_SH:\=/%"
set "DISTROS_SH=%DISTROS_SH:C:=/c%"
set "DISTROS_SH=%DISTROS_SH:c:=/c%"

REM Execute get_distros command
"%BASH_EXE%" -lc "bash '%DISTROS_SH%' %*"

exit /b !errorlevel!

@REM Made with Bob
