#Requires -Version 5.1
# ============================================================
# install.ps1 — Phoenix DevOps OS Windows Installer (unified)
# USys — United Systems | jwl247 | GPL-3.0
#
# One script: bare Windows box -> working Phoenix.
#   - PS7 + Git (installed if missing)
#   - repo in the RIGHT place (param / auto-detect / D: default — no
#     more hardcoded C:\Users\<you>\Phoenix)
#   - secrets pulled from the vault (F:\Phoenix\Vault\secrets\phoenix-secrets.env)
#     instead of prompting — falls back to prompt only if the vault is gone
#   - env vars (PHOENIX_ROOT / PHOENIX_AUTH / CLONEPOOL_DIR / OLLAMA_MODELS)
#   - ~/.phoenix/phoenix.env + ~/.phoenix_env.ps1/.sh
#   - PS7 profile hook (usys / clone / .lol / .phx in every terminal)
#   - clonepool junction, global bin commands, file associations
#   - Helix autostart  (tools/poc/install-helix-autostart.ps1)
#   - Dashboard autostart  (sector3/services/install-dashboard-windows.ps1)
#   - optional: restore Claude's memory from F:\Phoenix\Vault\claude-state
#
# ONE-LINER (fresh box, no repo yet):
#   powershell -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/jwl247/Phoenix-DevOps-oS/main/install.ps1 | iex"
#
# LOCAL (repo already cloned — the normal case on a dev box):
#   pwsh -ExecutionPolicy Bypass -File .\install.ps1
#   pwsh -ExecutionPolicy Bypass -File .\install.ps1 -TargetPath 'D:\Users\jwlef\Phoenix\Phoenix-DevOps-oS' -RestoreClaudeMemory
# ============================================================

param(
    # Where the OS repo lives (or should be cloned). Empty = auto-detect:
    # (1) the repo this script is running from, (2) an existing D:\...\Phoenix-DevOps-oS,
    # (3) D:\Users\<user>\Phoenix\Phoenix-DevOps-oS if D: exists, (4) $HOME\Phoenix\...
    [string]$TargetPath = '',
    # Vault secrets file — parsed for PHOENIX_AUTH / CLONEPOOL_DIR / OLLAMA_MODELS.
    [string]$SecretsFile = 'F:\Phoenix\Vault\secrets\phoenix-secrets.env',
    # Local clonepool cache. Empty = from vault, else E:\ if present, else <root>\clonepool.
    [string]$ClonepoolDir = '',
    # Ollama model store. Empty = from vault, else E:\Phoenix\ollama-models if E: exists.
    [string]$OllamaModels = '',
    # Legacy alias for -TargetPath's parent (kept for old muscle memory).
    [string]$LocalRepo = '',
    [switch]$RestoreClaudeMemory,
    [switch]$SkipAutostart,
    [switch]$SkipTunnel,
    [switch]$SkipAssociations,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'

# ── Config ────────────────────────────────────────────────────
$WORKER_URL       = 'https://packages-worker.phoenix-jwl.workers.dev'
$OS_REPO_URL      = 'https://github.com/jwl247/Phoenix-DevOps-oS.git'
$PKG_REPO_URL     = 'https://github.com/jwl247/Phoenix-Package_handler.git'
$CLAUDE_STATE_SRC = 'F:\Phoenix\Vault\claude-state\projects'
$ENV_PS1          = Join-Path $HOME '.phoenix_env.ps1'
$ENV_SH           = Join-Path $HOME '.phoenix_env.sh'
$PHX_CONF_DIR     = Join-Path $HOME '.phoenix'
$PHX_ENV_FILE     = Join-Path $PHX_CONF_DIR 'phoenix.env'
$TEMP_DIR         = Join-Path $env:TEMP 'phoenix-os-install'
$USYS_MAGIC       = @('.lol', '.phx')

$PS7_URL  = 'https://github.com/PowerShell/PowerShell/releases/download/v7.4.6/PowerShell-7.4.6-win-x64.msi'
$GIT_URL  = 'https://github.com/git-for-windows/git/releases/download/v2.47.1.windows.1/Git-2.47.1-64-bit.exe'
$PS7_PATH = if (Test-Path "$env:ProgramFiles\PowerShell\7\pwsh.exe") {
    "$env:ProgramFiles\PowerShell\7\pwsh.exe"
} else {
    (Get-Command pwsh -ErrorAction SilentlyContinue)?.Source
}
$GIT_PATH = "$env:ProgramFiles\Git\cmd\git.exe"

# ── Helpers ─────────────────────────────────────────────────
function PHX-Banner {
    Write-Host ''
    Write-Host '  ======================================' -ForegroundColor Cyan
    Write-Host '   Phoenix DevOps OS Installer (unified) ' -ForegroundColor Cyan
    Write-Host '   UnitedSys / USys                      ' -ForegroundColor Cyan
    Write-Host '  ======================================' -ForegroundColor Cyan
    Write-Host ''
}
function PHX-Info  { param($m) Write-Host "[PHX] $m"  -ForegroundColor Cyan }
function PHX-OK    { param($m) Write-Host "[OK]  $m"  -ForegroundColor Green }
function PHX-Warn  { param($m) Write-Host "[WARN] $m" -ForegroundColor Yellow }
function PHX-Error { param($m) Write-Host "[ERR] $m"  -ForegroundColor Red; exit 1 }

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

# KEY=value parser for the vault secrets file. Ignores comments / blanks.
# Returns a hashtable. Never echoes a value.
function Read-EnvFile([string]$path) {
    $h = @{}
    if (-not (Test-Path $path)) { return $h }
    foreach ($line in Get-Content $path) {
        $t = $line.Trim()
        if (-not $t -or $t.StartsWith('#')) { continue }
        $i = $t.IndexOf('=')
        if ($i -lt 1) { continue }
        $k = $t.Substring(0, $i).Trim()
        $v = $t.Substring($i + 1).Trim().Trim('"').Trim("'")
        if ($k) { $h[$k] = $v }
    }
    return $h
}

# Resolve the repo root: is $dir inside a Phoenix-DevOps-oS checkout?
function Find-RepoRoot([string]$dir) {
    $d = $dir
    while ($d -and (Test-Path $d)) {
        if ((Test-Path (Join-Path $d 'CLAUDE.md')) -and (Test-Path (Join-Path $d 'sector1'))) { return $d }
        $parent = Split-Path $d -Parent
        if ($parent -eq $d) { break }
        $d = $parent
    }
    return $null
}

New-Item -ItemType Directory -Force -Path $TEMP_DIR | Out-Null
PHX-Banner

# ── STAGE 1: Bootstrap PS7 from PS 5.1 ──────────────────────
if ($PSVersionTable.PSVersion.Major -lt 7) {
    PHX-Info "Running in PS $($PSVersionTable.PSVersion) — upgrading to PS7..."
    if (-not $PS7_PATH -or -not (Test-Path $PS7_PATH)) {
        $msi = Join-Path $TEMP_DIR 'ps7.msi'
        Download-File $PS7_URL $msi
        Start-Process msiexec.exe -ArgumentList "/i `"$msi`" /quiet /norestart ADD_EXPLORER_CONTEXT_MENU_OPENPOWERSHELL=1 ENABLE_PSREMOTING=0 REGISTER_MANIFEST=1" -Wait
        $PS7_PATH = "$env:ProgramFiles\PowerShell\7\pwsh.exe"
        if (-not (Test-Path $PS7_PATH)) { PHX-Error 'PS7 install failed.' }
        PHX-OK 'PowerShell 7 installed.'
    }
    # Re-invoke self under PS7 with the same args.
    $selfPath = $PSCommandPath
    if (-not $selfPath -or -not (Test-Path $selfPath)) {
        $selfPath = Join-Path $TEMP_DIR 'install.ps1'
        Download-File 'https://raw.githubusercontent.com/jwl247/Phoenix-DevOps-oS/main/install.ps1' $selfPath
    }
    $fwd = @('-ExecutionPolicy', 'Bypass', '-File', $selfPath)
    if ($TargetPath)          { $fwd += '-TargetPath', $TargetPath }
    if ($SecretsFile)         { $fwd += '-SecretsFile', $SecretsFile }
    if ($ClonepoolDir)        { $fwd += '-ClonepoolDir', $ClonepoolDir }
    if ($OllamaModels)        { $fwd += '-OllamaModels', $OllamaModels }
    if ($LocalRepo)           { $fwd += '-LocalRepo', $LocalRepo }
    if ($RestoreClaudeMemory) { $fwd += '-RestoreClaudeMemory' }
    if ($SkipAutostart)       { $fwd += '-SkipAutostart' }
    if ($SkipTunnel)          { $fwd += '-SkipTunnel' }
    if ($SkipAssociations)    { $fwd += '-SkipAssociations' }
    if ($Force)               { $fwd += '-Force' }
    & $PS7_PATH @fwd
    exit $LASTEXITCODE
}

PHX-Info "Running in PS $($PSVersionTable.PSVersion) — good."

# ── Git (needed before we can clone) ────────────────────────
if (-not (Test-Path $GIT_PATH)) {
    if (Get-Command git -ErrorAction SilentlyContinue) {
        $GIT_PATH = (Get-Command git).Source
        PHX-OK "Git found on PATH: $GIT_PATH"
    } else {
        PHX-Info 'Git not found — installing...'
        $gitExe = Join-Path $TEMP_DIR 'git-installer.exe'
        Download-File $GIT_URL $gitExe
        Start-Process $gitExe -ArgumentList '/VERYSILENT /NORESTART /NOCANCEL /SP- /CLOSEAPPLICATIONS /COMPONENTS="icons,ext\reg\shellhere,assoc,assoc_sh"' -Wait
        if (-not (Test-Path $GIT_PATH)) { PHX-Error 'Git install failed.' }
        PHX-OK 'Git installed.'
    }
} else {
    PHX-OK 'Git already installed.'
}
$env:PATH = "$env:ProgramFiles\Git\cmd;$env:ProgramFiles\PowerShell\7;$env:PATH"

# ── Resolve where the repo lives ────────────────────────────
if ($LocalRepo -and -not $TargetPath) {
    # legacy: -LocalRepo pointed at a repo to copy from; treat its own path as the target
    $TargetPath = $LocalRepo
}

$OS_DIR = $null
if ($TargetPath) {
    $OS_DIR = $TargetPath
} else {
    $fromHere = Find-RepoRoot $PSScriptRoot
    if ($fromHere) {
        $OS_DIR = $fromHere
        PHX-OK "Using the repo this installer is in: $OS_DIR"
    } elseif (Test-Path 'D:\Users\jwlef\Phoenix\Phoenix-DevOps-oS\CLAUDE.md') {
        $OS_DIR = 'D:\Users\jwlef\Phoenix\Phoenix-DevOps-oS'
    } elseif (Test-Path 'D:\') {
        $OS_DIR = "D:\Users\$env:USERNAME\Phoenix\Phoenix-DevOps-oS"
    } else {
        $OS_DIR = Join-Path $HOME 'Phoenix\Phoenix-DevOps-oS'
    }
}
$INSTALL_ROOT = Split-Path $OS_DIR -Parent
$PKG_DIR      = Join-Path $INSTALL_ROOT 'package-handler'
PHX-Info "Repo target: $OS_DIR"

# ── Clone / update the OS repo ──────────────────────────────
New-Item -ItemType Directory -Force -Path $INSTALL_ROOT | Out-Null
if (Test-Path (Join-Path $OS_DIR '.git')) {
    PHX-Info 'OS repo exists — pulling latest (ff-only)...'
    & $GIT_PATH -C $OS_DIR pull --ff-only 2>$null
    PHX-OK "OS repo at $OS_DIR"
} elseif (Test-Path (Join-Path $OS_DIR 'CLAUDE.md')) {
    PHX-Warn "Non-git repo already at $OS_DIR — leaving it as-is."
} else {
    PHX-Info "Cloning Phoenix-DevOps-oS to $OS_DIR ..."
    & $GIT_PATH clone $OS_REPO_URL $OS_DIR
    if (-not (Test-Path (Join-Path $OS_DIR '.git'))) { PHX-Error 'OS repo clone failed.' }
    PHX-OK 'OS repo cloned.'
}

# ── package-handler (Sector 2 intake) ──────────────────────
if (Test-Path (Join-Path $PKG_DIR '.git')) {
    & $GIT_PATH -C $PKG_DIR pull --ff-only 2>$null
    PHX-OK 'package-handler updated.'
} else {
    PHX-Info "Cloning package-handler to $PKG_DIR ..."
    & $GIT_PATH clone $PKG_REPO_URL $PKG_DIR 2>$null
    if (Test-Path (Join-Path $PKG_DIR '.git')) { PHX-OK 'package-handler cloned.' }
    else { PHX-Warn 'package-handler clone failed — sector2/package-handler in the OS repo still works.' }
}

# ── Secrets: read the vault, don't prompt if we don't have to ─
PHX-Info "Reading secrets from $SecretsFile ..."
$vault = Read-EnvFile $SecretsFile
if ($vault.Count) { PHX-OK "Vault loaded ($($vault.Count) keys)." }
else { PHX-Warn "Vault not found at $SecretsFile — will prompt / use existing env." }

if (Test-Path $ENV_PS1) { . $ENV_PS1; PHX-Info "Loaded $ENV_PS1" }

if (-not $env:PHOENIX_AUTH -and $vault['PHOENIX_AUTH']) {
    $env:PHOENIX_AUTH = $vault['PHOENIX_AUTH']
    PHX-OK 'PHOENIX_AUTH from vault.'
}
if (-not $env:PHOENIX_AUTH -and [Environment]::UserInteractive) {
    Write-Host ''
    Write-Host '  PHOENIX_AUTH not in vault or env. Paste it (Enter to skip — D1/R2 sync off):' -ForegroundColor Yellow
    $t = Read-Host '  PHOENIX_AUTH'
    if ($t) { $env:PHOENIX_AUTH = $t }
}
if (-not $env:PHOENIX_AUTH) { PHX-Warn 'PHOENIX_AUTH unset — D1/R2 sync disabled.' }

# clonepool + ollama: param > vault > E: > fallback
if (-not $ClonepoolDir) {
    $ClonepoolDir = if ($vault['CLONEPOOL_DIR']) { $vault['CLONEPOOL_DIR'] }
                    elseif (Test-Path 'E:\') { 'E:/Phoenix/clonepool' }
                    else { (Join-Path $INSTALL_ROOT 'clonepool').Replace([char]92,[char]47) }
}
if (-not $OllamaModels) {
    $OllamaModels = if ($vault['OLLAMA_MODELS']) { $vault['OLLAMA_MODELS'] }
                    elseif (Test-Path 'E:\') { 'E:\Phoenix\ollama-models' }
                    else { Join-Path $INSTALL_ROOT 'ollama-models' }
}
PHX-Info "Clonepool: $ClonepoolDir"
PHX-Info "Ollama models: $OllamaModels"

# ── Directory structure ────────────────────────────────────
@($INSTALL_ROOT,
  ($ClonepoolDir -replace '/', '\'),
  $OllamaModels,
  (Join-Path $HOME '.usys\bin'),
  (Join-Path $HOME '.catalog'),
  $PHX_CONF_DIR) | ForEach-Object {
    $dir = $_
    try { New-Item -ItemType Directory -Force -Path $dir | Out-Null } catch { PHX-Warn "mkdir $dir failed: $($_.Exception.Message)" }
}

# clonepool junction at the repo root (gitignored) — matches dev-box convention
$poolJunction = Join-Path $OS_DIR 'clonepool'
$poolTarget   = $ClonepoolDir -replace '/', '\'
if (-not (Test-Path $poolJunction) -and (Test-Path $poolTarget)) {
    try { cmd /c "mklink /J `"$poolJunction`" `"$poolTarget`"" | Out-Null; PHX-OK "clonepool junction -> $poolTarget" }
    catch { PHX-Warn "Could not create clonepool junction: $_" }
}

# ── Env files ──────────────────────────────────────────────
$timestamp = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
$bashPool  = ConvertTo-GitBashPath ($ClonepoolDir -replace '/', '\')
$bashPkg   = ConvertTo-GitBashPath (Join-Path $PKG_DIR 'intake\intake.sh')

@"
# Phoenix DevOps OS environment — generated $timestamp
`$env:PHOENIX_ROOT       = "$OS_DIR"
`$env:PHOENIX_AUTH       = "$($env:PHOENIX_AUTH)"
`$env:PHOENIX_WORKER_URL = "$WORKER_URL"
`$env:CLONEPOOL_DIR      = "$ClonepoolDir"
`$env:OLLAMA_MODELS      = "$OllamaModels"
`$env:PHOENIX_INTAKE     = "$(Join-Path $PKG_DIR 'intake\intake.sh')"
"@ | Set-Content -Path $ENV_PS1 -Encoding UTF8
try { icacls $ENV_PS1 /inheritance:r /grant:r "$($env:USERNAME):(R,W)" | Out-Null } catch {}

@"
export PHOENIX_AUTH="$($env:PHOENIX_AUTH)"
export PHOENIX_WORKER_URL="$WORKER_URL"
export CLONEPOOL_DIR="$bashPool"
export PHOENIX_INTAKE="$bashPkg"
"@ | Set-Content -Path $ENV_SH -Encoding UTF8
try { icacls $ENV_SH /inheritance:r /grant:r "$($env:USERNAME):(R,W)" | Out-Null } catch {}

# ~/.phoenix/phoenix.env — the file the DASHBOARD reads (main.js loadPhoenixEnv)
@"
# Phoenix Dashboard boot config — generated $timestamp by install.ps1
PHOENIX_ROOT=$OS_DIR
CLONEPOOL_DIR=$ClonepoolDir
PHOENIX_WORKER_URL=$WORKER_URL
PHOENIX_AI_PROVIDER=subscription
PHOENIX_OLLAMA_URL=http://localhost:11434
PHOENIX_SKIP_AUTH_MODAL=1
# PHOENIX_MAPTILER_KEY=
# PHOENIX_PROFILE=laurie   # uncomment ONLY on Laurie's login
"@ | Set-Content -Path $PHX_ENV_FILE -Encoding UTF8
PHX-OK "Wrote $PHX_ENV_FILE"

# ── User env vars ──────────────────────────────────────────
[Environment]::SetEnvironmentVariable('PHOENIX_ROOT', $OS_DIR, 'User')
[Environment]::SetEnvironmentVariable('PHOENIX_WORKER_URL', $WORKER_URL, 'User')
[Environment]::SetEnvironmentVariable('CLONEPOOL_DIR', $ClonepoolDir, 'User')
[Environment]::SetEnvironmentVariable('OLLAMA_MODELS', $OllamaModels, 'User')
[Environment]::SetEnvironmentVariable('PHOENIX_INTAKE', (Join-Path $PKG_DIR 'intake\intake.sh'), 'User')
if ($env:PHOENIX_AUTH) { [Environment]::SetEnvironmentVariable('PHOENIX_AUTH', $env:PHOENIX_AUTH, 'User') }
PHX-OK 'User env vars set.'

# ── User PATH ──────────────────────────────────────────────
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

# ── PS7 profile — usys + phoenix env in every terminal ─────
$ps7Profile = Join-Path $HOME 'Documents\PowerShell\Microsoft.PowerShell_profile.ps1'
New-Item -ItemType Directory -Force -Path (Split-Path $ps7Profile) | Out-Null
if (-not (Test-Path $ps7Profile)) { New-Item -ItemType File -Force -Path $ps7Profile | Out-Null }
$existing = Get-Content $ps7Profile -Raw -ErrorAction SilentlyContinue
if ($existing -notmatch 'Phoenix DevOps OS') {
    Add-Content -Path $ps7Profile -Value @"

# Phoenix DevOps OS — installed $timestamp
if (Test-Path "$ENV_PS1") { . "$ENV_PS1" }
if (Test-Path "$(Join-Path $OS_DIR 'scripts\usys.ps1')") { . "$(Join-Path $OS_DIR 'scripts\usys.ps1')" }
"@
    PHX-OK 'USys sourced into PS7 profile.'
} else {
    PHX-Warn 'PS7 profile already has a Phoenix block — left it.'
}

# ── Global command wrappers ───────────────────────────────
$usysPs1 = Join-Path $OS_DIR 'scripts\usys.ps1'
if (Test-Path $usysPs1) {
    try { & pwsh -NoProfile -ExecutionPolicy Bypass -File $usysPs1 init; PHX-OK 'usys init done.' }
    catch { PHX-Warn "usys init: $_" }
}
$binSource = Join-Path $OS_DIR 'bin'
$binDest   = Join-Path $HOME '.usys\bin'
if (Test-Path $binSource) {
    Get-ChildItem $binSource -Filter '*.cmd' | ForEach-Object {
        Copy-Item $_.FullName (Join-Path $binDest $_.Name) -Force
    }
    PHX-OK 'Global commands installed to ~/.usys/bin/'
} else {
    PHX-Warn "bin/ not found at $binSource"
}

# ── File associations: .lol / .phx ────────────────────────
function Register-PhoenixFileAssociation {
    param([string]$Extension, [string]$Description, [string]$HandlerCmd)
    $extKey  = "HKCU:\Software\Classes\$Extension"
    $progId  = "Phoenix.USys$($Extension.Replace('.',''))"
    $progKey = "HKCU:\Software\Classes\$progId"
    New-Item -Path $extKey -Force | Out-Null
    Set-ItemProperty -Path $extKey -Name '(Default)' -Value $progId
    New-Item -Path $progKey -Force | Out-Null
    Set-ItemProperty -Path $progKey -Name '(Default)' -Value $Description
    New-Item -Path "$progKey\shell\open\command" -Force | Out-Null
    Set-ItemProperty -Path "$progKey\shell\open\command" -Name '(Default)' -Value $HandlerCmd
}
if (-not $SkipAssociations -and (Test-Path $usysPs1)) {
    $pwshExe = (Get-Command pwsh -ErrorAction Stop).Source
    $openCmd = "`"$pwshExe`" -NoProfile -ExecutionPolicy Bypass -File `"$usysPs1`" open `"%1`""
    foreach ($ext in $USYS_MAGIC) {
        $desc = if ($ext -eq '.phx') { 'Phoenix Script Manifest' } else { 'Phoenix Live Ops Loader' }
        Register-PhoenixFileAssociation -Extension $ext -Description $desc -HandlerCmd $openCmd
    }
    PHX-OK 'File associations (.lol, .phx) registered.'
}

# ── Autostart: Helix + Dashboard ──────────────────────────
if (-not $SkipAutostart) {
    $helixInstaller = Join-Path $OS_DIR 'tools\poc\install-helix-autostart.ps1'
    $dashInstaller  = Join-Path $OS_DIR 'sector3\services\install-dashboard-windows.ps1'

    if (Test-Path $helixInstaller) {
        PHX-Info 'Registering Helix autostart...'
        try { & pwsh -NoProfile -ExecutionPolicy Bypass -File $helixInstaller; PHX-OK 'Helix autostart registered.' }
        catch { PHX-Warn "Helix autostart: $_ (run it manually elevated for the Task Scheduler path)" }
    } else { PHX-Warn "Helix autostart script not found: $helixInstaller" }

    if (Test-Path $dashInstaller) {
        PHX-Info 'Registering Dashboard autostart...'
        try { & pwsh -NoProfile -ExecutionPolicy Bypass -File $dashInstaller; PHX-OK 'Dashboard autostart registered.' }
        catch { PHX-Warn "Dashboard autostart: $_" }
    } else { PHX-Warn "Dashboard autostart script not found: $dashInstaller" }
} else {
    PHX-Warn 'Autostart registration skipped (-SkipAutostart).'
}

# ── Restore Claude's memory from the vault ─────────────────
if ($RestoreClaudeMemory) {
    if (Test-Path $CLAUDE_STATE_SRC) {
        $claudeProjects = Join-Path $HOME '.claude\projects'
        New-Item -ItemType Directory -Force -Path $claudeProjects | Out-Null
        PHX-Info "Restoring Claude memory from $CLAUDE_STATE_SRC ..."
        cmd /c "robocopy `"$CLAUDE_STATE_SRC`" `"$claudeProjects`" /E /NJH /NJS >nul 2>&1 & exit /b 0"
        PHX-OK 'Claude memory restored (~/.claude/projects).'
    } else {
        PHX-Warn "Claude state not found at $CLAUDE_STATE_SRC — skipped."
    }
}

# ── Register machine with D1 (non-fatal) ──────────────────
if ($env:PHOENIX_AUTH) {
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
        if ($reg.StatusCode -in 200, 201) { PHX-OK 'Machine registered with D1.' }
    } catch { PHX-Warn "D1 registration failed (non-fatal): $_" }
}

# ── Desktop launcher shortcut ─────────────────────────────
$dashStart = Join-Path $OS_DIR 'dashboard\start.ps1'
if (Test-Path $dashStart) {
    try {
        $desktop  = [Environment]::GetFolderPath('Desktop')
        $lnk      = Join-Path $desktop 'Phoenix Dashboard.lnk'
        $pwsh     = (Get-Command pwsh -ErrorAction Stop).Source
        $shell    = New-Object -ComObject WScript.Shell
        $shortcut = $shell.CreateShortcut($lnk)
        $shortcut.TargetPath       = $pwsh
        $shortcut.Arguments        = "-NoProfile -ExecutionPolicy Bypass -File `"$dashStart`""
        $shortcut.WorkingDirectory = (Split-Path $dashStart)
        $shortcut.Description      = 'Launch Phoenix DevOps OS Dashboard'
        $shortcut.IconLocation     = "$pwsh,0"
        $shortcut.Save()
        PHX-OK "Desktop shortcut: $lnk"
    } catch { PHX-Warn "Desktop shortcut: $_" }
}

Remove-Item -Recurse -Force $TEMP_DIR -ErrorAction SilentlyContinue

# ── Done ──────────────────────────────────────────────────
Write-Host ''
Write-Host '  ======================================' -ForegroundColor Green
Write-Host '   Phoenix DevOps OS installed.         ' -ForegroundColor Green
Write-Host '  ======================================' -ForegroundColor Green
Write-Host ''
Write-Host "  Repo:      $OS_DIR"           -ForegroundColor DarkGray
Write-Host "  Clonepool: $ClonepoolDir"     -ForegroundColor DarkGray
Write-Host "  Config:    $PHX_ENV_FILE"     -ForegroundColor DarkGray
Write-Host ''
Write-Host '  Open a NEW terminal, then:' -ForegroundColor Yellow
Write-Host '    usys status          <- system health'            -ForegroundColor Cyan
Write-Host '    usys clone <file>    <- clonepool intake'          -ForegroundColor Cyan
Write-Host '  Dashboard: double-click the desktop shortcut, or run dashboard\start.ps1' -ForegroundColor Cyan
Write-Host ''
if (-not $env:PHOENIX_AUTH) {
    Write-Host '  [!] PHOENIX_AUTH was not set — put it in the vault or env and re-run.' -ForegroundColor Yellow
    Write-Host ''
}
