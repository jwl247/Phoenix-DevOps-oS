@echo off
echo === Phoenix Context Push ===
node "%~dp0push-context.js"
if %errorlevel% neq 0 (
    echo FAILED - check node is installed and phoenix-secrets.env exists
    pause & exit /b 1
)
pause
