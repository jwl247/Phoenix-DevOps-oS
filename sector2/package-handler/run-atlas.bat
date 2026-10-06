@echo off
cd /d "F:\Phoenix\Phoenix-DevOps-oS\sector2\package-handler"
echo Regenerating Phoenix Atlas (connections-seed.json)...
node parse-connections.js
echo.
echo Done. Press any key to close.
pause
