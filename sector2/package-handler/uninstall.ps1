# ============================================================
# uninstall.ps1 — Phoenix Package Handler
# Removes everything Phoenix installed — clean slate
#
# ONE-LINER TRIGGER:
#   powershell -ExecutionPolicy Bypass -Command "iwr https://raw.githubusercontent.com/jwl247/Phoenix-Package_handler/main/uninstall.ps1 | iex"
# ============================================================

$ErrorActionPreference = "SilentlyContinue"

# ── Config ───────────────────────────────────────────────────
$INSTALL_DIR     = "$env:USERPROFILE\Phoenix\package-handler"
$PHOENIX_DIR     = "$env:USERPROFILE\Phoenix"
$ENV_FILE_PS1    = "$env:USERPROFILE\.phoenix_env.ps1"
$ENV_FILE_SH     = "$env:USERPROFILE\.phoenix_env.sh"
$BASH_SECRETS    = "$env:USERPROFILE\phoenix-env.cmd"
$INTAKE_SHIM     = "$env:WINDIR\System32\intake.cmd"
$PS7_PROFILE     = "$env:USERPROFILE\Documents\PowerShell\Microsoft.PowerShell_profile.ps1"
$PS7_PATH        = "$env:ProgramFiles\PowerShell\7\pwsh.exe"
$GIT_UNINST      = "$env:ProgramFiles\Git\unins000.exe"
$PYTHON_UNINST   = "$env:LOCALAPPDATA\Programs\Python\Python312\uninstall.exe"

# ── Helpers ──────────────────────────────────────────────────
function PHX-Banner {
    Write-Host ""
    Write-Host "  ======================================" -ForegroundColor Red
    Write-Host "   Phoenix Package Handler Uninstaller " -ForegroundColor Red
    Write-Host "   UnitedSys / Phoenix DevOps OS       " -ForegroundColor Red
    Write-Host "  ======================================" -ForegroundColor Red
    Write-Host ""
}

function PHX-Info  { param($m) Write-Host "[PHX] $m" -ForegroundColor Cyan }
function PHX-OK    { param($m) Write-Host "[OK]  $m" -ForegroundColor Green }
function PHX-Warn  { param($m) Write-Host "[WARN] $m" -ForegroundColor Yellow }
function PHX-Skip  { param($m) Write-Host "[SKIP] $m" -ForegroundColor DarkGray }

PHX-Banner

# ── Confirm ───────────────────────────────────────────────────
Write-Host "  This will remove:" -ForegroundColor Yellow
Write-Host "    - Phoenix repo, clonepool, logs, sidecars" -ForegroundColor White
Write-Host "    - intake.cmd from System32" -ForegroundColor White
Write-Host "    - phoenix-env.cmd, .phoenix_env files" -ForegroundColor White
Write-Host "    - PS7 profile injections (gbash, env, watcher)" -ForegroundColor White
Write-Host "    - Git, Python, PowerShell 7" -ForegroundColor White
Write-Host "    - Phoenix environment variables" -ForegroundColor White
Write-Host ""
$confirm = Read-Host "  Type UNINSTALL to confirm"
if ($confirm -ne "UNINSTALL") {
    Write-Host "  Aborted." -ForegroundColor Yellow
    exit 0
}
Write-Host ""

# ── Stop watcher job ──────────────────────────────────────────
PHX-Info "Stopping Phoenix watcher..."
$job = Get-Job -Name "PhoenixWatcher" -ErrorAction SilentlyContinue
if ($job) {
    Stop-Job -Name "PhoenixWatcher"
    Remove-Job -Name "PhoenixWatcher"
    PHX-OK "Watcher stopped."
} else {
    PHX-Skip "No watcher job running."
}

# ── Remove PS7 profile injections ────────────────────────────
PHX-Info "Cleaning PS7 profile..."
if (Test-Path $PS7_PROFILE) {
    $content = Get-Content $PS7_PROFILE -Raw
    # Strip all Phoenix blocks
    $markers = @(
        "# Phoenix Package Handler",
        "# Phoenix — always use Git Bash",
        "# Phoenix Auto-Intake Watcher"
    )
    $lines = Get-Content $PS7_PROFILE
    $cleaned = @()
    $skip = $false
    foreach ($line in $lines) {
        # Start skipping at any Phoenix marker
        if ($markers | Where-Object { $line -match [regex]::Escape($_) }) {
            $skip = $true
        }
        # Stop skipping at next blank line after a block ends
        if ($skip -and $line.Trim() -eq "" -and $cleaned.Count -gt 0 -and $cleaned[-1].Trim() -eq "") {
            $skip = $false
            continue
        }
        if (-not $skip) { $cleaned += $line }
    }
    $cleaned | Set-Content $PS7_PROFILE -Encoding UTF8
    PHX-OK "PS7 profile cleaned."
} else {
    PHX-Skip "No PS7 profile found."
}

# ── Remove intake shim ────────────────────────────────────────
PHX-Info "Removing intake.cmd from System32..."
if (Test-Path $INTAKE_SHIM) {
    Remove-Item -Force $INTAKE_SHIM
    PHX-OK "intake.cmd removed."
} else {
    PHX-Skip "intake.cmd not found."
}

# ── Remove env files ──────────────────────────────────────────
PHX-Info "Removing Phoenix env files..."
@($ENV_FILE_PS1, $ENV_FILE_SH, $BASH_SECRETS) | ForEach-Object {
    if (Test-Path $_) {
        Remove-Item -Force $_
        PHX-OK "Removed: $_"
    } else {
        PHX-Skip "Not found: $_"
    }
}

# ── Remove environment variables ──────────────────────────────
PHX-Info "Removing Phoenix environment variables..."
@("PHOENIX_AUTH", "PHOENIX_WORKER_URL", "CLONEPOOL_DIR", "PHOENIX_INSTALL_DIR", "PHOENIX_GIT_BASH") | ForEach-Object {
    [System.Environment]::SetEnvironmentVariable($_, $null, "User")
    [System.Environment]::SetEnvironmentVariable($_, $null, "Machine")
    Remove-Item "Env:\$_" -ErrorAction SilentlyContinue
}
PHX-OK "Environment variables cleared."

# ── Remove Phoenix folders ────────────────────────────────────
PHX-Info "Removing Phoenix directories..."
@($INSTALL_DIR, $PHOENIX_DIR) | ForEach-Object {
    if (Test-Path $_) {
        Remove-Item -Recurse -Force $_
        PHX-OK "Removed: $_"
    } else {
        PHX-Skip "Not found: $_"
    }
}

# ── Remove from system PATH ───────────────────────────────────
PHX-Info "Cleaning system PATH..."
$phoenixPaths = @(
    "$env:ProgramFiles\Git\cmd",
    "$env:ProgramFiles\PowerShell\7",
    "$env:LOCALAPPDATA\Programs\Python\Python312",
    "$env:LOCALAPPDATA\Programs\Python\Python312\Scripts"
)
$machinePath = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
foreach ($p in $phoenixPaths) {
    $machinePath = ($machinePath -split ";" | Where-Object { $_ -ne $p }) -join ";"
}
[System.Environment]::SetEnvironmentVariable("Path", $machinePath, "Machine")
PHX-OK "System PATH cleaned."

# ── Uninstall Python ──────────────────────────────────────────
PHX-Info "Uninstalling Python 3.12..."
if (Test-Path $PYTHON_UNINST) {
    Start-Process $PYTHON_UNINST -ArgumentList "/quiet" -Wait
    PHX-OK "Python uninstalled."
} else {
    # Fallback — try via winget
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        winget uninstall --id Python.Python.3.12 --silent 2>$null
        PHX-OK "Python uninstalled via winget."
    } else {
        PHX-Warn "Python uninstaller not found — remove manually via Add/Remove Programs."
    }
}

# ── Uninstall Git ─────────────────────────────────────────────
PHX-Info "Uninstalling Git..."
if (Test-Path $GIT_UNINST) {
    Start-Process $GIT_UNINST -ArgumentList "/VERYSILENT /NORESTART" -Wait
    PHX-OK "Git uninstalled."
} else {
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        winget uninstall --id Git.Git --silent 2>$null
        PHX-OK "Git uninstalled via winget."
    } else {
        PHX-Warn "Git uninstaller not found — remove manually via Add/Remove Programs."
    }
}

# ── Uninstall PS7 ─────────────────────────────────────────────
PHX-Info "Uninstalling PowerShell 7..."
# PS7 is an MSI — find it via registry
$ps7Reg = Get-ChildItem "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall" |
    Get-ItemProperty | Where-Object { $_.DisplayName -match "PowerShell 7" } |
    Select-Object -First 1

if ($ps7Reg) {
    $productCode = $ps7Reg.PSChildName
    Start-Process msiexec.exe -ArgumentList "/x $productCode /quiet /norestart" -Wait
    PHX-OK "PowerShell 7 uninstalled."
} else {
    PHX-Warn "PS7 uninstaller not found — remove manually via Add/Remove Programs."
}

# ── Done ──────────────────────────────────────────────────────
Write-Host ""
Write-Host "  ======================================" -ForegroundColor Green
Write-Host "   Phoenix removed successfully.        " -ForegroundColor Green
Write-Host "  ======================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Close this terminal — it's running in PS7 which was just removed." -ForegroundColor Yellow
Write-Host "  Everything else is clean." -ForegroundColor DarkGray
Write-Host ""
