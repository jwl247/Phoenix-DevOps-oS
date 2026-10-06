@echo off
REM Phoenix Global Command: phoenix-map - where everything is / is it running, every machine.
setlocal
set "PY=python"
where python >nul 2>nul || set "PY=py"
set "M=%~dp0phoenix-map"
if not exist "%M%" if defined PHOENIX_ROOT set "M=%PHOENIX_ROOT%\bin\phoenix-map"
"%PY%" "%M%" %*
exit /b %ERRORLEVEL%
