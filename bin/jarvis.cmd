@echo off
REM ============================================================
REM Phoenix Global Command: jarvis - ask Jarvis (pbmIII) from any terminal
REM   jarvis <question>        jarvis --json <question>
REM Runs bin\jarvis (Python) - the same door the Genie suit uses.
REM ============================================================
setlocal
set "PY=python"
where python >nul 2>nul || set "PY=py"
set "JARVIS_PY=%~dp0jarvis"
if not exist "%JARVIS_PY%" if defined PHOENIX_ROOT set "JARVIS_PY=%PHOENIX_ROOT%\bin\jarvis"
"%PY%" "%JARVIS_PY%" %*
exit /b %ERRORLEVEL%
