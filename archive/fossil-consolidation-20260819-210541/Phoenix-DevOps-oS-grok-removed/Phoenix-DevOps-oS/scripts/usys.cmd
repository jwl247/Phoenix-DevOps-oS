@echo off
REM ============================================================
REM usys.cmd — PATH shim for United Systems command layer
REM Invokes PowerShell 7 with scripts/usys.ps1
REM Install.ps1 registers this directory in user PATH
REM ============================================================
setlocal
set "USYS_PS1=%~dp0usys.ps1"
set "PWSH=%ProgramFiles%\PowerShell\7\pwsh.exe"
if not exist "%PWSH%" set "PWSH=pwsh"
"%PWSH%" -NoProfile -ExecutionPolicy Bypass -File "%USYS_PS1%" %*