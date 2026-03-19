#Requires -Version 5.0
# ============================================================
# install_global.ps1 — Phoenix DevOps Global Translator Install
# Self-elevating: triggers UAC automatically if not Admin
# Installs translator globally on Windows AND WSL/Debian
#
# Usage: Right-click → "Run with PowerShell"
#        OR from any terminal: powershell -File install_global.ps1
# ============================================================

param([switch]$Elevated)

# ── Self-elevation ────────────────────────────────────────────
function Test-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $pr = [Security.Principal.WindowsPrincipal]$id
    return $pr.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-Admin)) {
    Write-Host "[PHOENIX] Not running as Administrator — requesting UAC elevation..."
    $argList = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`" -Elevated"
    Start-Process PowerShell -Verb RunAs -ArgumentList $argList
    exit
}

# ── Paths ─────────────────────────────────────────────────────
$ScriptDir     = Split-Path -Parent $MyInvocation.MyCommand.Path
$TranslatorRaw = Join-Path $ScriptDir "..\translator\translator.sh"
$TranslatorSh  = (Resolve-Path $TranslatorRaw).Path
$System32      = "$env:SystemRoot\System32"
$CmdShim       = "$System32\translator.cmd"
$GlobalBin     = "/usr/local/bin/translator"

# Convert Windows path to WSL/bash mountpoint path
$WslSrc = ($TranslatorSh -replace '\\', '/') -replace '^([A-Za-z]):', { "/mnt/$($args[0].Groups[1].Value.ToLower())" }

Write-Host ""
Write-Host "============================================================"
Write-Host "  PHOENIX DevOps — Global Translator Installer"
Write-Host "============================================================"
Write-Host "  Source : $TranslatorSh"
Write-Host "  Windows: $CmdShim"
Write-Host "  Linux  : $GlobalBin"
Write-Host ""

# ── Windows: write translator.cmd shim into System32 ─────────
Write-Host "[1/3] Installing Windows shim → $CmdShim"
try {
    $shim = @"
@echo off
:: Phoenix DevOps — translator global shim
:: Routes to translator.sh via bash (Git Bash or WSL)
bash "$WslSrc" %*
"@
    Set-Content -Path $CmdShim -Value $shim -Encoding ASCII
    Write-Host "      OK — translator.cmd written to System32"
} catch {
    Write-Host "      ERROR: $($_.Exception.Message)"
}

# ── WSL/Debian: symlink into /usr/local/bin ───────────────────
Write-Host ""
Write-Host "[2/3] Installing Linux symlink → $GlobalBin (via WSL)"

$wslAvailable = Get-Command wsl -ErrorAction SilentlyContinue
if ($wslAvailable) {
    $wslCmd = "sudo ln -sf '$WslSrc' '$GlobalBin' && sudo chmod +x '$GlobalBin' && echo PHOENIX_OK"
    $result  = wsl -- bash -c $wslCmd 2>&1
    if ($result -match "PHOENIX_OK") {
        Write-Host "      OK — $GlobalBin → $WslSrc"
    } else {
        Write-Host "      WARN: WSL symlink step needed sudo password or failed."
        Write-Host "      Run manually inside WSL:"
        Write-Host "        sudo ln -sf '$WslSrc' '$GlobalBin'"
    }
} else {
    Write-Host "      SKIP — WSL not detected on this machine."
    Write-Host "      On bare Debian/Linux run:"
    Write-Host "        sudo ln -sf <path-to-translator.sh> $GlobalBin"
}

# ── Verify ────────────────────────────────────────────────────
Write-Host ""
Write-Host "[3/3] Verifying..."

if (Test-Path $CmdShim) {
    Write-Host "      [OK] Windows : 'translator' available in all CMD/PS terminals"
} else {
    Write-Host "      [FAIL] Windows shim not found at $CmdShim"
}

if ($wslAvailable) {
    $check = wsl -- which translator 2>&1
    if ($check -match "translator") {
        Write-Host "      [OK] Linux   : 'translator' available system-wide in WSL/Debian"
    } else {
        Write-Host "      [WARN] Linux : symlink not confirmed — may need manual sudo step"
    }
}

Write-Host ""
Write-Host "============================================================"
Write-Host "  Done. Test it:"
Write-Host "    Windows CMD/PS : translator search curl"
Write-Host "    WSL / Debian   : translator search curl"
Write-Host "============================================================"
Write-Host ""
pause
