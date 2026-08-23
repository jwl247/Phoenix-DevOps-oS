@echo off
:: =============================================================================
:: test-double-helix.cmd -- Phoenix Double Helix smoke test launcher
::
:: Double-click this file from anywhere. It finds the repo, sets the right
:: working directory, and runs the PS1 test in a pwsh window that stays open.
:: =============================================================================

:: %~dp0 is always the directory this .cmd lives in, regardless of where you
:: launched it from. The repo root is two levels up: tools\poc\ -> tools\ -> root
set REPO_ROOT=%~dp0..\..

:: Resolve to absolute path
pushd "%REPO_ROOT%"
set REPO_ROOT=%CD%
popd

echo.
echo   Phoenix Double Helix -- Windows Strand A smoke test
echo   Repo: %REPO_ROOT%
echo.

pwsh -NoProfile -ExecutionPolicy Bypass -File "%REPO_ROOT%\tools\poc\test-double-helix.ps1"

if errorlevel 1 (
    echo.
    echo   pwsh not found or test failed. Trying powershell.exe...
    powershell -NoProfile -ExecutionPolicy Bypass -File "%REPO_ROOT%\tools\poc\test-double-helix.ps1"
)

echo.
pause
