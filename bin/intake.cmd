@echo off
REM ============================================================
REM Phoenix Global Command: intake
REM Windows CMD wrapper for Phoenix Intake (Sector 2 clonepool -- same
REM pipeline as `clone`; Sector 4 vault intake is `usys intake`)
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

REM Load Phoenix environment
if exist "%USERPROFILE%\.phoenix_env.sh" (
    set "ENV_SOURCE=source ~/.phoenix_env.sh 2>/dev/null;"
) else (
    set "ENV_SOURCE="
)

REM Find intake.sh
set "INTAKE_SH=%PHOENIX_INTAKE%"
REM A stale PHOENIX_INTAKE (moved/deleted path - on PBMII it points at a dead
REM D: path) falls back to the repo copy instead of failing (2026-10-03).
if defined INTAKE_SH if not exist "%INTAKE_SH%" set "INTAKE_SH="
REM In-repo Sector 2 pipeline only (the standalone package-handler repo
REM keeps intake.sh at its root and was archived 2026-09-13 -- S34OPS-F41).
if not defined INTAKE_SH (
    if exist "%~dp0..\sector2\package-handler\intake.sh" (
        set "INTAKE_SH=%~dp0..\sector2\package-handler\intake.sh"
    ) else if exist "%PHOENIX_ROOT%\sector2\package-handler\intake.sh" (
        set "INTAKE_SH=%PHOENIX_ROOT%\sector2\package-handler\intake.sh"
    ) else if exist "%USERPROFILE%\Phoenix\Phoenix-DevOps-oS\sector2\package-handler\intake.sh" (
        set "INTAKE_SH=%USERPROFILE%\Phoenix\Phoenix-DevOps-oS\sector2\package-handler\intake.sh"
    )
)

if not defined INTAKE_SH (
    echo [ERROR] intake.sh not found. Set PHOENIX_INTAKE or run install.ps1
    exit /b 1
)

REM Convert Windows path to Git Bash path
set "INTAKE_SH=%INTAKE_SH:\=/%"
set "INTAKE_SH=%INTAKE_SH:C:=/c%"
set "INTAKE_SH=%INTAKE_SH:c:=/c%"

REM Execute intake command
REM Script path and arguments go to bash as positional parameters ($0, $@),
REM never interpolated into the -c string: %* inside the string let a
REM filename such as "a$(whoami).lol" execute as shell code (S34OPS-F20 class).
"%BASH_EXE%" -lc "%ENV_SOURCE% exec bash \"$0\" \"$@\"" "%INTAKE_SH%" %*

exit /b !errorlevel!

@REM Made with Bob
