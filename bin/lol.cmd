@echo off
REM ============================================================
REM Phoenix Global Command: lol - a pool file into the current folder
REM   lol <name> [vN] [--force]        (same as: clone <name>)
REM Runs bin\clone through Git Bash - the one clone engine (D1-checked,
REM never overwrites without --force). 2026-10-03: this used to write the
REM name into a temp PowerShell script, so a name containing a quote ran
REM as code, and it went through `usys pull`, which dropped -Destination.
REM Arguments go through as arguments (%*), never spliced into a script.
REM ============================================================
setlocal

set "BASH_EXE=%PHOENIX_BASH%"
if not defined BASH_EXE if exist "%ProgramFiles%\Git\bin\bash.exe" set "BASH_EXE=%ProgramFiles%\Git\bin\bash.exe"
if not defined BASH_EXE if exist "%ProgramFiles(x86)%\Git\bin\bash.exe" set "BASH_EXE=%ProgramFiles(x86)%\Git\bin\bash.exe"
if not defined BASH_EXE if exist "%LOCALAPPDATA%\Programs\Git\bin\bash.exe" set "BASH_EXE=%LOCALAPPDATA%\Programs\Git\bin\bash.exe"
if not defined BASH_EXE (
    echo [lol] Git Bash not found. Install Git for Windows or set PHOENIX_BASH.
    exit /b 1
)

if "%~1"=="" (
    echo usage: lol ^<name^> [vN] [--force]
    exit /b 2
)

set "CLONE_SH=%~dp0clone"
if not exist "%CLONE_SH%" if defined PHOENIX_ROOT set "CLONE_SH=%PHOENIX_ROOT%\bin\clone"
if not exist "%CLONE_SH%" (
    echo [lol] bin\clone not found - set PHOENIX_ROOT to your Phoenix-DevOps-oS checkout.
    exit /b 1
)

"%BASH_EXE%" "%CLONE_SH%" %*
exit /b %ERRORLEVEL%
