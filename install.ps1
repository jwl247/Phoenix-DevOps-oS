#Requires -Version 5.1
# ============================================================
# install.ps1 — Phoenix DevOps OS Windows Installer
# USys — United Systems | jwl247 | GPL-3.0
#
# Installs: PS7, Git (if missing), clones OS repo, wires usys,
#           PATH registration, .lol/.phx file associations,
#           optional Cloudflare tunnel (cloudflared).
#
# ONE-LINER (any PS/cmd window):
#   powershell -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/jwl247/Phoenix-DevOps-oS/main/install.ps1 | iex"
#
# Local dev install:
#   pwsh -ExecutionPolicy Bypass -File .\install.ps1
#   pwsh -ExecutionPolicy Bypass -File .\install.ps1 -LocalRepo "C:\Phoenix-DevOps-oS"
# ============================================================

param(
    [string]$LocalRepo = '',
    [switch]$SkipTunnel,
    [switch]$SkipAssociations,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'

# ── Config ────────────────────────────────────────────────────
$WORKER_URL     = 'https://packages-worker.phoenix-jwl.workers.dev'
$OS_REPO_URL    = 'https://github.com/jwl247/Phoenix-DevOps-oS.git'
$PKG_REPO_URL   = 'https://github.com/jwl247/Phoenix-Package_handler.git'
$INSTALL_ROOT   = Join-Path $HOME 'Phoenix'
$OS_DIR         = Join-Path $INSTALL_ROOT 'Phoenix-DevOps-oS'
$PKG_DIR        = Join-Path $INSTALL_ROOT 'package-handler'
$CLONEPOOL_DIR  = Join-Path $INSTALL_ROOT 'clonepool'
$ENV_PS1        = Join-Path $HOME '.phoenix_env.ps1'
$ENV_SH         = Join-Path $HOME '.phoenix_env.sh'
$TEMP_DIR       = Join-Path $env:TEMP 'phoenix-os-install'
$USYS_MAGIC     = @('.lol', '.phx')

$PS7_URL    = 'https://github.com/PowerShell/PowerShell/releases/download/v7.4.6/PowerShell-7.4.6-win-x64.msi'
$GIT_URL    = 'https://github.com/git-for-windows/git/releases/download/v2.47.1.windows.1/Git-2.47.1-64-bit.exe'
$PS7_PATH   = if (Test-Path "$env:ProgramFiles\PowerShell\7\pwsh.exe") {
    "$env:ProgramFiles\PowerShell\7\pwsh.exe"
} else {
    (Get-Command pwsh -ErrorAction Stop).Source
}
$GIT_PATH   = "$env:ProgramFiles\Git\cmd\git.exe"
$GIT_BASH   = "$env:ProgramFiles\Git\bin\bash.exe"

# ── Helpers ─────────────────────────────────────────────────
function PHX-Banner {
    Write-Host ''
    Write-Host '  ======================================' -ForegroundColor Cyan
    Write-Host '   Phoenix DevOps OS Installer          ' -ForegroundColor Cyan
    Write-Host '   UnitedSys / USys v0.1                ' -ForegroundColor Cyan
    Write-Host '  ======================================' -ForegroundColor Cyan
    Write-Host ''
}

function PHX-Info  { param($m) Write-Host "[PHX] $m" -ForegroundColor Cyan }
function PHX-OK    { param($m) Write-Host "[OK]  $m" -ForegroundColor Green }
function PHX-Warn  { param($m) Write-Host "[WARN] $m" -ForegroundColor Yellow }
function PHX-Error { param($m) Write-Host "[ERR] $m" -ForegroundColor Red; exit 1 }

function Download-File {
    param([string]$Url, [string]$Dest)
    PHX-Info "Downloading $(Split-Path $Dest -Leaf)..."
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -Uri $Url -OutFile $Dest -UseBasicParsing
    if (-not (Test-Path $Dest)) { PHX-Error "Download failed: $Url" }
    PHX-OK 'Downloaded.'
}

function ConvertTo-GitBashPath([string]$p) {
    $p = $p.Replace([char]92, [char]47)
    if ($p -match '^([A-Za-z]):(.*)') { return "/$($Matches[1].ToLower())$($Matches[2])" }
    return $p
}

New-Item -ItemType Directory -Force -Path $TEMP_DIR | Out-Null
PHX-Banner

# ── STAGE 1: Bootstrap PS7 from PS 5.1 ──────────────────────
if ($PSVersionTable.PSVersion.Major -lt 7) {
    PHX-Info "Running in PS $($PSVersionTable.PSVersion) — upgrading to PS7..."
    if (-not (Test-Path $PS7_PATH)) {
        $msi = Join-Path $TEMP_DIR 'ps7.msi'
        Download-File $PS7_URL $msi
        Start-Process msiexec.exe -ArgumentList "/i `"$msi`" /quiet /norestart ADD_EXPLORER_CONTEXT_MENU_OPENPOWERSHELL=1 ENABLE_PSREMOTING=0 REGISTER_MANIFEST=1" -Wait
        if (-not (Test-Path $PS7_PATH)) { PHX-Error 'PS7 install failed.' }
        PHX-OK 'PowerShell 7 installed.'
    }
    $localScript = if ($LocalRepo -and (Test-Path (Join-Path $LocalRepo 'install.ps1'))) {
        Join-Path $LocalRepo 'install.ps1'
    } else {
        $s = Join-Path $TEMP_DIR 'install.ps1'
        Download-File 'https://raw.githubusercontent.com/jwl247/Phoenix-DevOps-oS/main/install.ps1' $s
        $s
    }
    $args = @('-ExecutionPolicy', 'Bypass', '-File', $localScript)
    if ($LocalRepo) { $args += '-LocalRepo', $LocalRepo }
    if ($SkipTunnel) { $args += '-SkipTunnel' }
    if ($SkipAssociations) { $args += '-SkipAssociations' }
    if ($Force) { $args += '-Force' }
    & $PS7_PATH @args
    exit $LASTEXITCODE
}

PHX-Info "Running in PS $($PSVersionTable.PSVersion) — good."

# ── Worker health (non-fatal) ───────────────────────────────
PHX-Info 'Checking packages-worker health...'
try {
    Invoke-RestMethod -Uri "$WORKER_URL/health" -TimeoutSec 10 | Out-Null
    PHX-OK 'Worker is live.'
} catch {
    PHX-Warn "Worker unreachable ($WORKER_URL) — continuing offline."
}

# ── Git ─────────────────────────────────────────────────────
if (-not (Test-Path $GIT_PATH)) {
    PHX-Info 'Git not found — installing...'
    $gitExe = Join-Path $TEMP_DIR 'git-installer.exe'
    Download-File $GIT_URL $gitExe
    Start-Process $gitExe -ArgumentList '/VERYSILENT /NORESTART /NOCANCEL /SP- /CLOSEAPPLICATIONS /COMPONENTS="icons,ext\reg\shellhere,assoc,assoc_sh"' -Wait
    if (-not (Test-Path $GIT_PATH)) { PHX-Error 'Git install failed.' }
    PHX-OK 'Git installed.'
} else {
    PHX-OK 'Git already installed.'
}
$env:PATH = "$env:ProgramFiles\Git\cmd;$env:ProgramFiles\PowerShell\7;$env:PATH"

# ── Directory structure ─────────────────────────────────────
PHX-Info 'Creating Phoenix directory structure...'
@($INSTALL_ROOT, $OS_DIR, $PKG_DIR, $CLONEPOOL_DIR,
  (Join-Path $HOME '.usys'), (Join-Path $HOME '.usys\bin'),
  (Join-Path $HOME '.catalog')) | ForEach-Object {
    New-Item -ItemType Directory -Force -Path $_ | Out-Null
}
PHX-OK 'Directories ready.'

# ── Clone or copy OS repo ───────────────────────────────────
if ($LocalRepo -and (Test-Path $LocalRepo)) {
    PHX-Info "Local repo install from $LocalRepo ..."
    if ($Force -or -not (Test-Path (Join-Path $OS_DIR 'construct.md'))) {
        if (Test-Path $OS_DIR) { Remove-Item $OS_DIR -Recurse -Force -ErrorAction SilentlyContinue }
        Copy-Item $LocalRepo $OS_DIR -Recurse -Force
        PHX-OK "Copied local repo to $OS_DIR"
    } else {
        PHX-Warn 'OS repo exists — use -Force to recopy local repo.'
    }
} elseif (Test-Path (Join-Path $OS_DIR '.git')) {
    PHX-Info 'OS repo exists — pulling latest...'
    & $GIT_PATH -C $OS_DIR pull --ff-only 2>$null
    PHX-OK "OS repo updated at $OS_DIR"
} else {
    PHX-Info "Cloning Phoenix-DevOps-oS to $OS_DIR ..."
    & $GIT_PATH clone $OS_REPO_URL $OS_DIR
    if (-not (Test-Path (Join-Path $OS_DIR '.git'))) { PHX-Error 'OS repo clone failed.' }
    PHX-OK 'OS repo cloned.'
}

# ── Clone package-handler (Sector 2 intake) ─────────────────
if (Test-Path (Join-Path $PKG_DIR '.git')) {
    PHX-Info 'package-handler exists — pulling...'
    & $GIT_PATH -C $PKG_DIR pull --ff-only 2>$null
} else {
    PHX-Info "Cloning package-handler to $PKG_DIR ..."
    & $GIT_PATH clone $PKG_REPO_URL $PKG_DIR
}
if (Test-Path (Join-Path $PKG_DIR 'intake\intake.sh')) {
    PHX-OK 'Sector 2 intake.sh ready.'
} else {
    PHX-Warn 'package-handler intake.sh not found — clone/intake will fail until fixed.'
}

# ── PHOENIX_AUTH ────────────────────────────────────────────
if (Test-Path $ENV_PS1) { . $ENV_PS1; PHX-Info "Loaded $ENV_PS1" }

if (-not $env:PHOENIX_AUTH -and [Environment]::UserInteractive) {
    Write-Host ''
    Write-Host '  Enter PHOENIX_AUTH token (Enter to skip — D1 sync disabled):' -ForegroundColor Yellow
    Write-Host '  Cloudflare -> packages-worker -> Settings -> Variables' -ForegroundColor DarkGray
    Write-Host ''
    $secureToken = Read-Host '  PHOENIX_AUTH'
    if ($secureToken) { $env:PHOENIX_AUTH = $secureToken }
} elseif (-not $env:PHOENIX_AUTH) {
    PHX-Warn 'PHOENIX_AUTH not set — D1 sync disabled (non-interactive install).'
}

# ── Write env files (user scope, locked down) ───────────────
$timestamp = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
$bashPool  = ConvertTo-GitBashPath $CLONEPOOL_DIR
$bashPkg   = ConvertTo-GitBashPath (Join-Path $PKG_DIR 'intake\intake.sh')

@"
# Phoenix DevOps OS environment — generated $timestamp
`$env:PHOENIX_ROOT          = "$OS_DIR"
`$env:PHOENIX_AUTH          = "$($env:PHOENIX_AUTH)"
`$env:PHOENIX_WORKER_URL    = "$WORKER_URL"
`$env:CLONEPOOL_DIR         = "$CLONEPOOL_DIR"
`$env:PHOENIX_INTAKE        = "$(Join-Path $PKG_DIR 'intake\intake.sh')"
`$env:PHOENIX_INTAKE_SECTOR4 = "$(Join-Path $OS_DIR 'sector4\intake\intake.sh')"
"@ | Set-Content -Path $ENV_PS1 -Encoding UTF8

icacls $ENV_PS1 /inheritance:r /grant:r "$($env:USERNAME):(R,W)" | Out-Null

@"
export PHOENIX_AUTH="$($env:PHOENIX_AUTH)"
export PHOENIX_WORKER_URL="$WORKER_URL"
export CLONEPOOL_DIR="$bashPool"
export PHOENIX_INTAKE="$bashPkg"
"@ | Set-Content -Path $ENV_SH -Encoding UTF8

icacls $ENV_SH /inheritance:r /grant:r "$($env:USERNAME):(R,W)" | Out-Null

[Environment]::SetEnvironmentVariable('PHOENIX_ROOT', $OS_DIR, 'User')
[Environment]::SetEnvironmentVariable('PHOENIX_WORKER_URL', $WORKER_URL, 'User')
[Environment]::SetEnvironmentVariable('CLONEPOOL_DIR', $CLONEPOOL_DIR, 'User')
[Environment]::SetEnvironmentVariable('PHOENIX_INTAKE', (Join-Path $PKG_DIR 'intake\intake.sh'), 'User')
[Environment]::SetEnvironmentVariable('PHOENIX_INTAKE_SECTOR4', (Join-Path $OS_DIR 'sector4\intake\intake.sh'), 'User')
if ($env:PHOENIX_AUTH) {
    [Environment]::SetEnvironmentVariable('PHOENIX_AUTH', $env:PHOENIX_AUTH, 'User')
}
PHX-OK 'Environment files written and secured.'

# ── User PATH (no machine-wide mutation — security-first) ───
PHX-Info 'Updating user PATH...'
$pathsToAdd = @(
    "$env:ProgramFiles\PowerShell\7",
    "$env:ProgramFiles\Git\cmd",
    (Join-Path $OS_DIR 'scripts'),
    (Join-Path $HOME '.usys\bin')
)
$userPath = [Environment]::GetEnvironmentVariable('PATH', 'User')
foreach ($p in $pathsToAdd) {
    if ($userPath -notlike "*$p*") { $userPath = if ($userPath) { "$userPath;$p" } else { $p } }
}
[Environment]::SetEnvironmentVariable('PATH', $userPath, 'User')
$env:PATH = "$($pathsToAdd -join ';');$env:PATH"
PHX-OK 'User PATH updated.'

# ── PS7 profile — usys + phoenix env ───────────────────────
$ps7Profile = Join-Path $HOME 'Documents\PowerShell\Microsoft.PowerShell_profile.ps1'
New-Item -ItemType Directory -Force -Path (Split-Path $ps7Profile) | Out-Null
if (-not (Test-Path $ps7Profile)) { New-Item -ItemType File -Force -Path $ps7Profile | Out-Null }

$profileBlock = @"

# Phoenix DevOps OS — installed $timestamp
. "$ENV_PS1"
. "$(Join-Path $OS_DIR 'scripts\usys.ps1')"
"@

$existing = Get-Content $ps7Profile -Raw -ErrorAction SilentlyContinue
if ($existing -notmatch 'Phoenix DevOps OS') {
    Add-Content -Path $ps7Profile -Value $profileBlock
    PHX-OK 'USys sourced into PS7 profile.'
} else {
    PHX-Warn 'PS7 profile already has Phoenix block — skipped.'
}

# ── Global Commands Installation ────────────────────────────
PHX-Info 'Installing global Phoenix commands...'

# Initialize usys first
$usysPs1 = Join-Path $OS_DIR 'scripts\usys.ps1'
if (Test-Path $usysPs1) {
    & pwsh -NoProfile -ExecutionPolicy Bypass -File $usysPs1 init
    PHX-OK 'usys init complete.'
} else {
    PHX-Warn 'scripts/usys.ps1 not found — usys init skipped.'
}

# Install all global command wrappers from bin/ to ~/.usys/bin/
$binSource = Join-Path $OS_DIR 'bin'
$binDest = Join-Path $HOME '.usys\bin'

if (Test-Path $binSource) {
    $globalCommands = @('usys.cmd', 'clone.cmd', 'intake.cmd', 'status.cmd', 'align_dirs.cmd', 'get_distros.cmd', 'run.cmd')
    
    foreach ($cmd in $globalCommands) {
        $srcFile = Join-Path $binSource $cmd
        $dstFile = Join-Path $binDest $cmd
        
        if (Test-Path $srcFile) {
            Copy-Item $srcFile $dstFile -Force
            PHX-OK "Installed: $cmd"
        } else {
            PHX-Warn "Source not found: $cmd"
        }
    }
    
    PHX-OK 'Global commands installed to ~/.usys/bin/'
} else {
    PHX-Warn "bin/ directory not found at $binSource"
}

# ── File associations: .lol and .phx ────────────────────────
function Register-PhoenixFileAssociation {
    param([string]$Extension, [string]$Description, [string]$HandlerCmd)

    $extKey = "HKCU:\Software\Classes\$Extension"
    $progId = "Phoenix.USys$($Extension.Replace('.',''))"
    $progKey = "HKCU:\Software\Classes\$progId"

    New-Item -Path $extKey -Force | Out-Null
    Set-ItemProperty -Path $extKey -Name '(Default)' -Value $progId

    New-Item -Path $progKey -Force | Out-Null
    Set-ItemProperty -Path $progKey -Name '(Default)' -Value $Description

    New-Item -Path "$progKey\shell\open\command" -Force | Out-Null
    Set-ItemProperty -Path "$progKey\shell\open\command" -Name '(Default)' -Value $HandlerCmd
}

if (-not $SkipAssociations) {
    PHX-Info 'Registering magic file associations (.lol, .phx)...'
    $pwshExe = (Get-Command pwsh -ErrorAction Stop).Source
    $openCmd = "`"$pwshExe`" -NoProfile -ExecutionPolicy Bypass -File `"$usysPs1`" open `"%1`""
    foreach ($ext in $USYS_MAGIC) {
        $desc = if ($ext -eq '.phx') { 'Phoenix Script Manifest' } else { 'Phoenix Live Ops Loader' }
        Register-PhoenixFileAssociation -Extension $ext -Description $desc -HandlerCmd $openCmd
        PHX-OK "Associated $ext -> usys open"
    }
} else {
    PHX-Warn 'File associations skipped (-SkipAssociations).'
}

# Note: intake.cmd and other global commands are now installed from bin/ directory above

# ── Optional Cloudflare tunnel ──────────────────────────────
if (-not $SkipTunnel) {
    $cloudflared = Get-Command cloudflared -ErrorAction SilentlyContinue
    if ($cloudflared) {
        PHX-Info 'cloudflared found — checking tunnel config...'
        $tunnelDir = Join-Path $HOME '.phoenix\tunnel'
        New-Item -ItemType Directory -Force -Path $tunnelDir | Out-Null
        $tunnelCfg = Join-Path $tunnelDir 'config.yml'
        if (-not (Test-Path $tunnelCfg)) {
            @"
# Phoenix DevOps OS — Cloudflare tunnel stub
# Edit ingress rules, then: cloudflared tunnel --config "$tunnelCfg" run <tunnel-name>
ingress:
  - hostname: phoenix.local
    service: http://localhost:8787
  - service: http_status:404
"@ | Set-Content -Path $tunnelCfg -Encoding UTF8
            PHX-OK "Tunnel config stub: $tunnelCfg"
            PHX-Warn 'Tunnel not auto-started — configure cloudflared credentials first.'
        }
    } else {
        PHX-Warn 'cloudflared not installed — tunnel setup skipped. Install: winget install Cloudflare.cloudflared'
    }
}

# ── Register machine with D1 (non-fatal) ────────────────────
if ($env:PHOENIX_AUTH) {
    PHX-Info 'Registering machine with D1...'
    $regBody = @{
        package_name = 'phoenix-devops-os'
        hostname     = $env:COMPUTERNAME
        os           = 'Windows'
        version      = (Get-CimInstance Win32_OperatingSystem -ErrorAction SilentlyContinue).Caption
        installed_by = 'install.ps1'
        install_dir  = $OS_DIR
    } | ConvertTo-Json
    try {
        $reg = Invoke-WebRequest -Uri "$WORKER_URL/installed/register" -Method POST `
            -Headers @{ 'Authorization' = "Bearer $($env:PHOENIX_AUTH)"; 'Content-Type' = 'application/json' } `
            -Body $regBody -UseBasicParsing -TimeoutSec 15
        if ($reg.StatusCode -in 200, 201) { PHX-OK 'Machine registered.' }
    } catch {
        PHX-Warn "D1 registration failed: $_"
    }
}

# ── Cleanup ─────────────────────────────────────────────────
Remove-Item -Recurse -Force $TEMP_DIR -ErrorAction SilentlyContinue

# ── Desktop launcher ─────────────────────────────────────────
function Install-PhoenixDashboardShortcut {
    $dashboardDir = Join-Path $OS_DIR 'dashboard'
    $launcher = Join-Path $dashboardDir 'start.ps1'
    if (-not (Test-Path $launcher)) {
        PHX-Warn "Dashboard launcher not found at $launcher — desktop shortcut skipped."
        return
    }

    try {
        $desktop = [Environment]::GetFolderPath('Desktop')
        $shortcutPath = Join-Path $desktop 'Phoenix Dashboard.lnk'
        $pwsh = (Get-Command pwsh -ErrorAction Stop).Source
        $shell = New-Object -ComObject WScript.Shell
        $shortcut = $shell.CreateShortcut($shortcutPath)
        $shortcut.TargetPath = $pwsh
        $shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$launcher`""
        $shortcut.WorkingDirectory = $dashboardDir
        $shortcut.Description = 'Launch Phoenix DevOps OS Dashboard'
        $shortcut.IconLocation = "$pwsh,0"
        $shortcut.Save()
        PHX-OK "Desktop shortcut created: $shortcutPath"
    } catch {
        PHX-Warn "Could not create Phoenix Dashboard desktop shortcut: $_"
    }
}

Install-PhoenixDashboardShortcut

# ── Done ────────────────────────────────────────────────────
Write-Host ''
Write-Host '  ======================================' -ForegroundColor Green
Write-Host '   Phoenix DevOps OS installed.         ' -ForegroundColor Green
Write-Host '  ======================================' -ForegroundColor Green
Write-Host ''
Write-Host '  Open a NEW terminal, then:' -ForegroundColor Yellow
Write-Host '    usys status          <- system health' -ForegroundColor Cyan
Write-Host '    usys clone <file>    <- Sector 2 clonepool intake' -ForegroundColor Cyan
Write-Host '    usys intake <file>   <- Sector 4 vault intake' -ForegroundColor Cyan
Write-Host '    intake <file>        <- bash intake shim' -ForegroundColor Cyan
Write-Host ''
Write-Host "  Repo: $OS_DIR" -ForegroundColor DarkGray
Write-Host ''
