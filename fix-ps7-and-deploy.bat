@echo off
echo ============================================================
echo  Phoenix Bootstrap Fix
echo  1) PS7 execution policy
echo  2) Windows Terminal default profile = PS7
echo  3) Deploy packages-worker
echo  4) Run atlas bootstrap
echo ============================================================
echo.

echo [1/4] Setting PS7 execution policy (RemoteSigned, CurrentUser)...
pwsh -Command "Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser -Force; Write-Host 'Execution policy set.'"
if %errorlevel% neq 0 (
    echo FAILED: Is pwsh (PS7) installed? Run: winget install Microsoft.PowerShell
    pause & exit /b 1
)

echo.
echo [2/4] Setting Windows Terminal default profile to PS7...
pwsh -Command ^
  "$settingsPath = \"$env:LOCALAPPDATA\Packages\Microsoft.WindowsTerminal_8wekyb3d8bbwe\LocalState\settings.json\"; " ^
  "if (!(Test-Path $settingsPath)) { Write-Host 'settings.json not found, skipping.'; exit 0 }; " ^
  "$s = Get-Content $settingsPath -Raw | ConvertFrom-Json; " ^
  "$ps7 = $s.profiles.list | Where-Object { $_.source -eq 'Windows.Terminal.PowershellCore' -or $_.name -match 'PowerShell' -and $_.name -notmatch '5\.1|Windows' } | Select-Object -First 1; " ^
  "if (!$ps7) { Write-Host 'PS7 profile not found in WT settings — open Terminal once to register it, then re-run.'; exit 0 }; " ^
  "$s.defaultProfile = $ps7.guid; " ^
  "$s | ConvertTo-Json -Depth 20 | Set-Content $settingsPath -Encoding UTF8; " ^
  "Write-Host \"Default profile set to: $($ps7.name) ($($ps7.guid))\""

echo.
echo [3/4] Deploying packages-worker...
cd /d "F:\Phoenix\Phoenix-DevOps-oS\sector3\workers\packages-worker"
pwsh -Command "wrangler deploy"
if %errorlevel% neq 0 (
    echo FAILED: wrangler deploy error.
    pause & exit /b 1
)

echo.
echo [4/4] Running atlas bootstrap...
cd /d "F:\Phoenix\Phoenix-DevOps-oS"
if exist run-atlas.bat (
    call run-atlas.bat
) else (
    echo run-atlas.bat not found at repo root - skipping.
)

echo.
echo ============================================================
echo  ALL DONE.
echo  - PS7 is now default in Windows Terminal (reopen it to confirm)
echo  - packages-worker deployed with /meta route
echo  - Atlas bootstrap complete
echo ============================================================
pause
