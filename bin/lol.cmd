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

REM .lol is the front door (2026-10-08): a known word runs that command; anything else is
REM a file to summon (the original lol, = lol get <name>). Same engine as usys.
if "%~1"=="" goto :lolhelp
set "LOL_WORD="
for %%w in (intake suit get import run open install remove upgrade rollback info closet suites start stop status log jump watch glossary ask console map vm setup version help intakes intakec clone pull load list-suites suite-list suite-trust suite-promote app-intake download search doctor init path-register distro fs-init fs-ls fs-import fs-export fs-sync) do if /i "%~1"=="%%w" set "LOL_WORD=1"
if /i "%~1"=="-h" set "LOL_WORD=1"
if /i "%~1"=="--help" set "LOL_WORD=1"
REM (outside a ( ) block: %ERRORLEVEL% inside one is read before the call runs)
if not defined LOL_WORD goto :summon
call "%~dp0usys.cmd" %*
exit /b %ERRORLEVEL%
:lolhelp
call "%~dp0usys.cmd" help
exit /b 0
:summon

set "CLONE_SH=%~dp0clone"
if not exist "%CLONE_SH%" if defined PHOENIX_ROOT set "CLONE_SH=%PHOENIX_ROOT%\bin\clone"
if not exist "%CLONE_SH%" (
    echo [lol] bin\clone not found - set PHOENIX_ROOT to your Phoenix-DevOps-oS checkout.
    exit /b 1
)

"%BASH_EXE%" "%CLONE_SH%" %*
exit /b %ERRORLEVEL%
