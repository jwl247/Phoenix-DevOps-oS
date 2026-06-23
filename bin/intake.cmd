@echo off
REM ============================================================
REM Phoenix Global Command: intake
REM Windows CMD wrapper for Phoenix Intake (Sector 4 vault)
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
if not defined INTAKE_SH (
    if exist "%USERPROFILE%\Phoenix\package-handler\intake\intake.sh" (
        set "INTAKE_SH=%USERPROFILE%\Phoenix\package-handler\intake\intake.sh"
    ) else if exist "%USERPROFILE%\Phoenix\Phoenix-Package_handler\intake\intake.sh" (
        set "INTAKE_SH=%USERPROFILE%\Phoenix\Phoenix-Package_handler\intake\intake.sh"
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
"%BASH_EXE%" -lc "%ENV_SOURCE% bash '%INTAKE_SH%' %*"

exit /b !errorlevel!

@REM Made with Bob
