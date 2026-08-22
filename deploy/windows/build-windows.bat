@echo off
:: build_windows.bat — build concierge.exe on Windows
:: Run this from the phoenix-bridge directory
:: Supports MinGW (gcc) or MSVC (cl)

echo Phoenix Concierge — Windows build
echo.

:: ── detect compiler ──────────────────────────────────────────────────────────
where gcc >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo Compiler: MinGW gcc
    goto :mingw
)

where cl >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo Compiler: MSVC cl
    goto :msvc
)

echo ERROR: No compiler found.
echo.
echo Install one of:
echo   MinGW-w64  — https://www.mingw-w64.org/
echo   MSYS2      — https://www.msys2.org/  then: pacman -S mingw-w64-x86_64-gcc
echo   MSVC       — Visual Studio Build Tools
echo.
echo Quickest: open PowerShell as admin and run:
echo   winget install msys2.msys2
echo   Then in MSYS2 terminal: pacman -S mingw-w64-x86_64-gcc
exit /b 1

:mingw
gcc -O2 -o concierge.exe concierge.c -lws2_32
if %ERRORLEVEL% NEQ 0 (
    echo BUILD FAILED
    exit /b 1
)
goto :done

:msvc
cl concierge.c ws2_32.lib /Fe:concierge.exe /O2
if %ERRORLEVEL% NEQ 0 (
    echo BUILD FAILED
    exit /b 1
)
goto :done

:done
echo.
echo BUILD OK — concierge.exe
echo.
echo Usage:
echo   concierge.exe               — server mode ^(port 9901^)
echo   concierge.exe status        — ping bridge in WSL2
echo   concierge.exe send "hello"  — one-shot test
echo.
echo Make sure WSL2 bridge is running first:
echo   wsl python3 bridge.py
