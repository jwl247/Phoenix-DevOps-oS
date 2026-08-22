#Requires -Version 7.0
<#
.SYNOPSIS
    United Systems (USys) — Phoenix DevOps global command layer for Windows.

.DESCRIPTION
    Full-featured PowerShell 7 module + shim.  Single entry point for intake,
    clone, status, search, registry ops, and magic extension handling (.lol, .phx).

    Design rules:
      - PowerShell 7 first (Windows focus)
      - Security-first: minimal local surface, no elevation required
      - No unnecessary dependencies (PS7 + Git Bash for bash pipelines)
      - Forward-compatible with Desktop Phase 2 shell

    Install (manual):
      . "$HOME\Phoenix\Phoenix-DevOps-oS\scripts\usys.ps1"
      usys init

    Or add to $PROFILE:
      . "$HOME\Phoenix\Phoenix-DevOps-oS\scripts\usys.ps1"

.NOTES
    Author  : jwl247 / Phoenix DevOps LLC
    License : GPL v3
    Sector  : Global command layer (wraps Sector 2 clone + Sector 4 intake)
#>

# =============================================================================
# MODULE METADATA
# =============================================================================
$script:UsysVersion     = '0.1.0'
$script:UsysScriptRoot  = $PSScriptRoot
$script:UsysRepoRoot    = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$script:UsysHome        = Join-Path $HOME '.usys'
$script:UsysBin         = Join-Path $script:UsysHome 'bin'
$script:UsysConfig      = Join-Path $script:UsysHome 'config.json'
$script:UsysLogDir      = Join-Path $script:UsysHome 'log'
$script:UsysMagicExts   = @('.lol', '.phx')

# =============================================================================
# OUTPUT HELPERS — consistent banner style across all commands
# =============================================================================
function Write-UsysInfo([string]$Message) {
    Write-Host "  usys: $Message" -ForegroundColor Cyan
}

function Write-UsysOk([string]$Message) {
    Write-Host "  usys: $Message" -ForegroundColor Green
}

function Write-UsysWarn([string]$Message) {
    Write-Warning "usys: $Message"
}

function Write-UsysErr([string]$Message) {
    Write-Error "usys: $Message"
}

# =============================================================================
# SECURITY — refuse accidental elevation; validate paths stay local
# =============================================================================
function Test-UsysElevation {
    # Running as admin widens attack surface; USys is designed for user scope only.
    $identity  = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]$identity
    if ($principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        Write-UsysWarn 'Running elevated. USys operates in user scope — avoid sudo/admin for normal ops.'
        return $true
    }
    return $false
}

function Test-UsysSafePath([string]$Path) {
    if ([string]::IsNullOrWhiteSpace($Path)) { return $false }
    try {
        $resolved = Resolve-Path -Path $Path -ErrorAction Stop
        return [bool]$resolved
    } catch {
        return $false
    }
}

# =============================================================================
# PATH RESOLUTION — repo, bash, intake engines
# =============================================================================
function Get-UsysRepoRoot {
    if ($env:PHOENIX_ROOT -and (Test-Path $env:PHOENIX_ROOT)) {
        return (Resolve-Path $env:PHOENIX_ROOT).Path
    }
    return $script:UsysRepoRoot
}

function Get-UsysGitBash {
    # Git Bash is required for bash intake pipelines on Windows (no WSL dependency).
    $candidates = @(
        $env:PHOENIX_BASH,
        'C:\Program Files\Git\bin\bash.exe',
        'C:\Program Files (x86)\Git\bin\bash.exe',
        "$env:ProgramFiles\Git\bin\bash.exe",
        "$env:LOCALAPPDATA\Programs\Git\bin\bash.exe"
    ) | Where-Object { $_ -and (Test-Path $_) }

    if ($candidates) { return $candidates[0] }

    $found = Get-Command bash -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty Source -First 1
    if ($found -and $found -notmatch 'wsl') { return $found }

    return $null
}

function ConvertTo-GitBashPath([string]$WindowsPath) {
    # C:\Users\foo\bar -> /c/Users/foo/bar
    $p = $WindowsPath.Replace([char]92, [char]47)
    if ($p -match '^([A-Za-z]):(.*)') {
        return "/$($Matches[1].ToLower())$($Matches[2])"
    }
    return $p
}

function Get-UsysIntakeSh {
    # Sector 4 vault intake wrapper (zsh/bash).
    $repo = Get-UsysRepoRoot
    $candidates = @(
        $env:PHOENIX_INTAKE_SECTOR4,
        (Join-Path $repo 'sector4\intake\intake.sh')
    ) | Where-Object { $_ -and (Test-Path $_) }
    return $candidates | Select-Object -First 1
}

function Get-UsysCloneIntakeSh {
    # Sector 2 package-handler intake (clone pipeline).
    $repo = Get-UsysRepoRoot
    $parent = Split-Path $repo -Parent
    $candidates = @(
        $env:PHOENIX_INTAKE,
        (Join-Path $parent 'Phoenix-Package_handler\intake\intake.sh'),
        (Join-Path $HOME 'Phoenix\Phoenix-Package_handler\intake\intake.sh'),
        (Join-Path $repo 'sector2\package-handler\intake.sh')
    ) | Where-Object { $_ -and (Test-Path $_) }
    return $candidates | Select-Object -First 1
}

function Get-UsysBashUsys {
    # Legacy unitedsys bash engine (forward compat for register/call/swap).
    $candidates = @(
        $env:USYS_ENGINE,
        (Join-Path $script:UsysHome 'usys.sh'),
        (Join-Path $HOME '.usys\usys.sh')
    ) | Where-Object { $_ -and (Test-Path $_) }
    return $candidates | Select-Object -First 1
}

function Get-UsysClonepoolDir {
    if ($env:CLONEPOOL_DIR) { return $env:CLONEPOOL_DIR }
    return (Join-Path $HOME 'Phoenix\clonepool')
}

function Get-UsysQemu {
    # Resolve QEMU binary — check clonepool suite first, then PATH, then common install locations.
    # Phoenix carries its own QEMU so no system install is required.
    $suites = Find-UsysSuites -Name 'qemu-system'
    if ($suites.Count -gt 0) {
        $candidate = Join-Path $suites[0].Path 'qemu-system-x86_64.exe'
        if (Test-Path $candidate) { return $candidate }
    }

    $fromPath = Get-Command 'qemu-system-x86_64' -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty Source -First 1
    if ($fromPath) { return $fromPath }

    foreach ($loc in @(
        'C:\Program Files\qemu\qemu-system-x86_64.exe',
        'C:\qemu\qemu-system-x86_64.exe',
        "$env:LOCALAPPDATA\qemu\qemu-system-x86_64.exe"
    )) {
        if (Test-Path $loc) { return $loc }
    }
    return $null
}

function Get-UsysCatalogDb {
    Join-Path $HOME '.catalog\catalog.db'
}

# =============================================================================
# CONFIG PERSISTENCE — ~/.usys/config.json
# =============================================================================
function Get-UsysConfig {
    if (-not (Test-Path $script:UsysConfig)) { return @{} }
    try {
        return (Get-Content $script:UsysConfig -Raw | ConvertFrom-Json -AsHashtable)
    } catch {
        Write-UsysWarn "config.json corrupt — using defaults"
        return @{}
    }
}

function Save-UsysConfig([hashtable]$Config) {
    $Config | ConvertTo-Json -Depth 6 | Set-Content $script:UsysConfig -Encoding UTF8
}

# =============================================================================
# COMMAND: init — first-time setup (dirs, PATH hint, config seed)
# =============================================================================
function Invoke-UsysInit {
    Write-Host ''
    Write-Host '  UnitedSys init v' -NoNewline -ForegroundColor Cyan
    Write-Host $script:UsysVersion -ForegroundColor White
    Write-Host ''

    Test-UsysElevation | Out-Null

    # ── Directories ──────────────────────────────────────────────────────────
    @($script:UsysHome, $script:UsysBin, $script:UsysLogDir,
      (Join-Path $script:UsysHome 'versions'),
      (Get-UsysClonepoolDir),
      (Join-Path $HOME '.catalog')) | ForEach-Object {
        if (-not (Test-Path $_)) {
            New-Item -ItemType Directory -Path $_ -Force | Out-Null
            Write-UsysOk "created $_"
        }
    }

    # ── Auth setup — silent after first run ──────────────────────────────────
    $existingUrl  = [Environment]::GetEnvironmentVariable('PHOENIX_WORKER_URL', 'User')
    $existingAuth = [Environment]::GetEnvironmentVariable('PHOENIX_AUTH', 'User')

    if (-not $existingUrl) {
        Write-Host ''
        Write-Host '  Phoenix worker URL not set.' -ForegroundColor Yellow
        $url = Read-Host '  Enter PHOENIX_WORKER_URL (e.g. https://packages-worker.phoenix-jwl.workers.dev)'
        if ($url) {
            [Environment]::SetEnvironmentVariable('PHOENIX_WORKER_URL', $url.Trim(), 'User')
            $env:PHOENIX_WORKER_URL = $url.Trim()
            Write-UsysOk "PHOENIX_WORKER_URL saved (user scope)"
        }
    } else {
        Write-UsysOk "PHOENIX_WORKER_URL already set"
    }

    if (-not $existingAuth) {
        Write-Host ''
        Write-Host '  Phoenix auth token not set.' -ForegroundColor Yellow
        $token = Read-Host '  Enter PHOENIX_AUTH token'
        if ($token) {
            [Environment]::SetEnvironmentVariable('PHOENIX_AUTH', $token.Trim(), 'User')
            $env:PHOENIX_AUTH = $token.Trim()
            Write-UsysOk "PHOENIX_AUTH saved (user scope)"
        }
    } else {
        Write-UsysOk "PHOENIX_AUTH already set"
    }

    # Load into current session immediately
    if (-not $env:PHOENIX_WORKER_URL) {
        $env:PHOENIX_WORKER_URL = [Environment]::GetEnvironmentVariable('PHOENIX_WORKER_URL', 'User')
    }
    if (-not $env:PHOENIX_AUTH) {
        $env:PHOENIX_AUTH = [Environment]::GetEnvironmentVariable('PHOENIX_AUTH', 'User')
    }

    # ── Wire into $PROFILE so every new terminal loads silently ──────────────
    $profilePath = $PROFILE.CurrentUserAllHosts
    $profileDir  = Split-Path $profilePath
    if (-not (Test-Path $profileDir)) { New-Item -ItemType Directory -Path $profileDir -Force | Out-Null }

    $loaderLine  = ". `"$(Join-Path $script:UsysScriptRoot 'usys.ps1')`""
    $envBlock = @"

# Phoenix USys — auto-loaded by usys init
`$env:PHOENIX_WORKER_URL = [Environment]::GetEnvironmentVariable('PHOENIX_WORKER_URL','User')
`$env:PHOENIX_AUTH       = [Environment]::GetEnvironmentVariable('PHOENIX_AUTH','User')
$loaderLine
"@

    $profileContent = if (Test-Path $profilePath) { Get-Content $profilePath -Raw } else { '' }
    if ($profileContent -notmatch 'Phoenix USys') {
        Add-Content -Path $profilePath -Value $envBlock
        Write-UsysOk "Profile updated: $profilePath"
        Write-UsysInfo "Auth + usys will load silently in every new terminal"
    } else {
        Write-UsysOk "Profile already wired"
    }

    # ── Config ────────────────────────────────────────────────────────────────
    $cfg = @{
        version    = $script:UsysVersion
        repo_root  = (Get-UsysRepoRoot)
        clonepool  = (Get-UsysClonepoolDir)
        installed  = (Get-Date -Format 'yyyy-MM-ddTHH:mm:ss')
        magic_exts = $script:UsysMagicExts
    }
    Save-UsysConfig $cfg
    Write-UsysOk "config written: $script:UsysConfig"

    $registered = Register-UsysPath
    if ($registered) {
        Write-UsysOk 'PATH updated (user scope)'
    } else {
        Write-UsysOk 'PATH already registered'
    }

    Write-Host ''
    Write-UsysOk 'Init complete. Open a new terminal — everything loads silently.'
    Write-UsysInfo 'Run: usys status   to verify'
    Write-Host ''
}

# =============================================================================
# COMMAND: path-register — add ~/.usys/bin and repo scripts to user PATH
# =============================================================================
function Register-UsysPath {
    $pathsToAdd = @(
        $script:UsysBin,
        (Join-Path (Get-UsysRepoRoot) 'scripts')
    )

    $userPath = [Environment]::GetEnvironmentVariable('PATH', 'User')
    $changed  = $false

    foreach ($p in $pathsToAdd) {
        if ($userPath -notlike "*$p*") {
            $userPath = if ($userPath) { "$userPath;$p" } else { $p }
            $changed  = $true
        }
    }

    if ($changed) {
        [Environment]::SetEnvironmentVariable('PATH', $userPath, 'User')
        $env:PATH = "$env:PATH;$($pathsToAdd -join ';')"
    }

    return $changed
}

# =============================================================================
# COMMAND: status — repo health, env, intake engines, catalog
# =============================================================================
function Invoke-UsysStatus {
    Write-Host ''
    Write-Host '  === USys Status ===' -ForegroundColor Cyan
    Write-Host "  Version   : $($script:UsysVersion)"
    Write-Host "  Repo      : $(Get-UsysRepoRoot)"
    Write-Host "  USys home : $script:UsysHome"
    Write-Host ''

    Write-Host '  -- Sector tree --' -ForegroundColor Yellow
    $repo = Get-UsysRepoRoot
    foreach ($sector in @('sector1', 'sector2', 'sector3', 'sector4')) {
        $dir = Join-Path $repo $sector
        if (Test-Path $dir) {
            $count = (Get-ChildItem $dir -Recurse -File -ErrorAction SilentlyContinue | Measure-Object).Count
            Write-Host "    $sector : $count files"
        } else {
            Write-Host "    $sector : MISSING" -ForegroundColor Red
        }
    }
    Write-Host ''

    Write-Host '  -- Engines --' -ForegroundColor Yellow
    $bash = Get-UsysGitBash
    Write-Host "    Git Bash       : $(if ($bash) { $bash } else { 'NOT FOUND' })"
    Write-Host "    intake.sh (S4) : $(Get-UsysIntakeSh)"
    Write-Host "    intake.sh (S2) : $(Get-UsysCloneIntakeSh)"
    Write-Host "    usys.sh        : $(Get-UsysBashUsys)"
    Write-Host ''

    Write-Host '  -- Environment --' -ForegroundColor Yellow
    foreach ($var in @('PHOENIX_AUTH', 'PHOENIX_WORKER_URL', 'CLONEPOOL_DIR', 'PHOENIX_INTAKE', 'PHOENIX_ROOT')) {
        $val = [Environment]::GetEnvironmentVariable($var, 'User')
        if (-not $val) { $val = [Environment]::GetEnvironmentVariable($var, 'Process') }
        Write-Host "    $var : $(if ($val) { $val } else { '(not set)' })"
    }
    Write-Host ''

    Write-Host '  -- Catalog --' -ForegroundColor Yellow
    $db = Get-UsysCatalogDb
    if (Test-Path $db) {
        $sqlite = Get-Command sqlite3 -ErrorAction SilentlyContinue
        if ($sqlite) {
            $count = & sqlite3 $db "SELECT COUNT(*) FROM packages;" 2>$null
            Write-Host "    packages : $count"
        } else {
            Write-Host "    catalog.db exists (sqlite3 not in PATH)"
        }
    } else {
        Write-Host '    catalog.db not yet initialized'
    }

    $pool = Get-UsysClonepoolDir
    if (Test-Path $pool) {
        $poolCount = (Get-ChildItem $pool -Recurse -File -ErrorAction SilentlyContinue | Measure-Object).Count
        Write-Host "    clonepool : $poolCount files at $pool"
    }
    Write-Host ''
}

# =============================================================================
# COMMAND: intake — Sector 4 TAV intake (vault / breach_coms4 path)
# =============================================================================
function Invoke-UsysIntake {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory, Position = 0)]
        [string]$Path,

        [ValidateSet('file', 'dir', 'status')]
        [string]$Mode = 'file',

        [switch]$DryRun
    )

    $bash   = Get-UsysGitBash
    $intake = Get-UsysIntakeSh

    if (-not $bash)   { Write-UsysErr 'Git Bash not found. Install Git for Windows or set PHOENIX_BASH.'; return }
    if (-not $intake) { Write-UsysErr 'Sector 4 intake.sh not found. Set PHOENIX_INTAKE_SECTOR4.'; return }

    if ($Mode -eq 'status') {
        & $bash (ConvertTo-GitBashPath $intake) 'status'
        return
    }

    if (-not (Test-UsysSafePath $Path)) {
        Write-UsysErr "path not found — '$Path'"
        return
    }

    $resolved = (Resolve-Path $Path).Path
    $bashFile = ConvertTo-GitBashPath $resolved
    $bashIntk = ConvertTo-GitBashPath $intake

    if ($DryRun) {
        Write-Host ''
        Write-Host '  [DRY RUN] USys Intake (Sector 4)' -ForegroundColor Cyan
        Write-Host "  File   : $resolved"
        Write-Host "  Mode   : $Mode"
        Write-Host "  Intake : $intake"
        Write-Host ''
        return
    }

    Write-Host ''
    Write-UsysInfo "intake $Mode -> $Path"
    & $bash $bashIntk $Mode $bashFile
    if ($LASTEXITCODE -eq 0) { Write-UsysOk 'intake complete' } else { Write-UsysErr "intake exited $LASTEXITCODE" }
    Write-Host ''
}

# =============================================================================
# COMMAND: clone — Sector 2 clonepool intake (wraps tools/clone.ps1 logic)
# =============================================================================
function Invoke-UsysClone {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory, Position = 0)]
        [string]$Path,

        [string]$Tag         = '',
        [string]$Category    = '',
        [string]$Destination = '',
        [switch]$DryRun
    )

    $resolved = Resolve-Path -Path $Path -ErrorAction SilentlyContinue
    if (-not $resolved) {
        Write-UsysErr "path not found — '$Path'"
        return
    }
    $fullPath = $resolved.Path

    $bash   = Get-UsysGitBash
    $intake = Get-UsysCloneIntakeSh

    if (-not $bash)   { Write-UsysErr 'Git Bash not found. Install Git for Windows or set PHOENIX_BASH.'; return }
    if (-not $intake) { Write-UsysErr 'clone intake.sh not found. Clone Phoenix-Package_handler or set PHOENIX_INTAKE.'; return }

    if (-not $env:PHOENIX_AUTH)       { Write-UsysWarn 'PHOENIX_AUTH not set — D1 sync skipped' }
    if (-not $env:PHOENIX_WORKER_URL) { Write-UsysWarn 'PHOENIX_WORKER_URL not set — D1 sync skipped' }
    if (-not $env:CLONEPOOL_DIR)      { $env:CLONEPOOL_DIR = Get-UsysClonepoolDir }

    $bashFile   = ConvertTo-GitBashPath $fullPath
    $bashIntake = ConvertTo-GitBashPath $intake
    $intakeArgs = @($bashFile)
    if ($Category) { $intakeArgs += $Category }
    if ($Tag)      { $intakeArgs += "`"$Tag`"" }

    if ($DryRun) {
        Write-Host ''
        Write-Host '  [DRY RUN] USys Clone (Sector 2)' -ForegroundColor Cyan
        Write-Host "  File      : $fullPath"
        Write-Host "  Intake    : $intake"
        Write-Host "  Category  : $(if ($Category) { $Category } else { '(none)' })"
        Write-Host "  Tag       : $(if ($Tag) { $Tag } else { '(none)' })"
        Write-Host "  Dest      : $(if ($Destination) { $Destination } else { '(none)' })"
        Write-Host "  Clonepool : $env:CLONEPOOL_DIR"
        Write-Host ''
        return
    }

    Write-Host ''
    Write-UsysInfo "clone -> $Path"
    $env:PHOENIX_DESTINATION = $Destination
    $env:CLONEPOOL_DIR       = ConvertTo-GitBashPath $env:CLONEPOOL_DIR

    & $bash $bashIntake @intakeArgs
    if ($LASTEXITCODE -eq 0) { Write-UsysOk 'cloned OK' } else { Write-UsysErr "clone exited $LASTEXITCODE" }
    Write-Host ''
}

# =============================================================================
# COMMAND: search — grep clonepool + optional catalog sqlite
# =============================================================================
function Invoke-UsysSearch {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory, Position = 0)]
        [string]$Query,

        [switch]$CatalogOnly,
        [int]$Limit = 25
    )

    if ([string]::IsNullOrWhiteSpace($Query)) {
        Write-UsysErr 'search requires a query string'
        return
    }

    Write-Host ''
    Write-UsysInfo "search: '$Query'"
    $hits = 0

    if (-not $CatalogOnly) {
        $pool = Get-UsysClonepoolDir
        if (Test-Path $pool) {
            Write-Host "  -- clonepool ($pool) --" -ForegroundColor Yellow
            Get-ChildItem $pool -Recurse -File -ErrorAction SilentlyContinue |
                Where-Object { $_.Name -like "*$Query*" -or $_.FullName -like "*$Query*" } |
                Select-Object -First $Limit |
                ForEach-Object {
                    Write-Host "    $($_.FullName)"
                    $hits++
                }
        }
    }

    $db = Get-UsysCatalogDb
    $sqlite = Get-Command sqlite3 -ErrorAction SilentlyContinue
    if ($sqlite -and (Test-Path $db)) {
        Write-Host '  -- catalog --' -ForegroundColor Yellow
        $rows = & sqlite3 $db "SELECT name, hex_id FROM packages WHERE name LIKE '%$Query%' LIMIT $Limit;" 2>$null
        if ($rows) {
            $rows | ForEach-Object { Write-Host "    $_"; $hits++ }
        }
    }

    if ($hits -eq 0) { Write-Host '    (no matches)' -ForegroundColor DarkGray }
    Write-Host ''
}

# =============================================================================
# COMMAND: open — magic extension handler (.lol, .phx)
# =============================================================================
function Invoke-UsysOpen {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory, Position = 0)]
        [string]$Path,

        [switch]$Intake,
        [switch]$DryRun
    )

    if (-not (Test-UsysSafePath $Path)) {
        Write-UsysErr "path not found — '$Path'"
        return
    }

    $resolved = (Resolve-Path $Path).Path
    $ext      = [System.IO.Path]::GetExtension($resolved).ToLowerInvariant()

    if ($script:UsysMagicExts -notcontains $ext) {
        Write-UsysWarn "extension '$ext' is not a USys magic extension ($($script:UsysMagicExts -join ', '))"
        Write-UsysInfo 'opening with default handler'
        Start-Process $resolved
        return
    }

    Write-Host ''
    Write-UsysInfo "magic open $ext -> $Path"

    # .phx = Phoenix script manifest → clone into pool
    # .lol = Live Ops Loader → intake to vault + register for call
    switch ($ext) {
        '.phx' {
            if ($DryRun) {
                Write-Host '  [DRY RUN] would clone .phx via Sector 2' -ForegroundColor Cyan
            } else {
                Invoke-UsysClone -Path $resolved
            }
        }
        '.lol' {
            if ($DryRun) {
                Write-Host '  [DRY RUN] would intake .lol via Sector 4' -ForegroundColor Cyan
            } else {
                Invoke-UsysIntake -Path $resolved -Mode 'file'
            }
        }
    }

    if ($Intake) {
        Write-UsysInfo 'secondary intake pass requested'
        Invoke-UsysIntake -Path $resolved -Mode 'file' -DryRun:$DryRun
    }
    Write-Host ''
}

# =============================================================================
# UNITEDSYS FORWARD COMPAT — delegate to bash usys.sh when present
# =============================================================================
function Invoke-UsysDelegate {
    param(
        [Parameter(Mandatory)][string]$SubCommand,
        [Parameter(ValueFromRemainingArguments = $true)][string[]]$Args
    )

    $engine = Get-UsysBashUsys
    $bash   = Get-UsysGitBash

    if (-not $engine) {
        Write-UsysErr "bash usys engine not found — run: usys init (or install unitedsys)"
        Write-UsysInfo 'Commands: register, call, swap, rollback, list, info, remove, where, sync'
        return
    }
    if (-not $bash) {
        Write-UsysErr 'Git Bash not found'
        return
    }

    $bashEngine = ConvertTo-GitBashPath $engine
    & $bash $bashEngine $SubCommand @Args
}

# =============================================================================
# COMMAND: pull — fetch a suite from D1/clonepool by name and stage it locally
# =============================================================================
function Invoke-UsysPull {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory, Position = 0)]
        [string]$SuiteName,
        [switch]$DryRun
    )

    $workerUrl  = $env:PHOENIX_WORKER_URL
    $workerAuth = $env:PHOENIX_AUTH

    if (-not $workerUrl) {
        Write-UsysErr 'PHOENIX_WORKER_URL not set — cannot pull from D1'
        return
    }

    Write-Host ''
    Write-UsysInfo "Pulling suite from D1: $SuiteName"

    # Ask D1 for the record
    try {
        $uri = "$($workerUrl.TrimEnd('/'))/clonepool/$([Uri]::EscapeDataString($SuiteName))"
        $headers = @{ 'Accept' = 'application/json' }
        if ($workerAuth) { $headers['Authorization'] = "Bearer $workerAuth" }
        $resp = Invoke-RestMethod -Uri $uri -Headers $headers -Method GET -ErrorAction Stop
    } catch {
        Write-UsysErr "Suite '$SuiteName' not found in D1 — has it been intaked?"
        return
    }

    $hexDisplay = if ($resp.hex_id) { $resp.hex_id.Substring(0,16) } else { $resp.b58 }
    Write-UsysOk "Found in D1: $($resp.name) hex=$hexDisplay..."

    if ($DryRun) {
        Write-Host ''
        Write-Host '  [DRY RUN] Would stage suite to clonepool:' -ForegroundColor Cyan
        Write-Host "    Name     : $($resp.name)"
        Write-Host "    hex_id   : $($resp.hex_id)"
        Write-Host "    pool_path: $($resp.pool_path)"
        Write-Host ''
        return
    }

    # If pool_path is a local path on the source machine it won't exist here —
    # that is expected on a second machine. We stage from what D1 knows.
    $suiteDir = Join-Path (Get-UsysClonepoolDir) $resp.name
    New-Item -ItemType Directory -Path $suiteDir -Force | Out-Null

    # Write a stub .suite.json so the suite is runnable if the binary is already present
    $manifest = @{
        name        = $resp.name
        version     = 'v1'
        description = "Pulled from Phoenix D1 — hex $hexDisplay"
        type        = 'script'
        entry       = $resp.name
        runtime     = 'binary'
        metadata    = @{
            hex_id     = $resp.hex_id
            b58        = $resp.b58
            pulled_at  = (Get-Date -Format 'o')
            source     = 'D1'
        }
    }
    $manifest | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $suiteDir '.suite.json') -Encoding UTF8

    Write-UsysOk "Staged at: $suiteDir"
    if ($resp.hex_id) { Write-Host "  hex_id  : $($resp.hex_id)" -ForegroundColor DarkGray }
    if ($resp.b58)    { Write-Host "  b58     : $($resp.b58)"    -ForegroundColor DarkGray }
    Write-Host ''
    Write-UsysInfo "Next: place the binary/script in $suiteDir then: usys run $SuiteName"
    Write-Host ''
}

# =============================================================================
# SUITE EXECUTION — run suites from clonepool without installation
# =============================================================================
function Get-UsysSuiteManifest {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$SuitePath
    )
    
    $manifestPath = Join-Path $SuitePath '.suite.json'
    if (-not (Test-Path $manifestPath)) {
        return $null
    }
    
    try {
        $manifest = Get-Content $manifestPath -Raw | ConvertFrom-Json
        return $manifest
    } catch {
        Write-UsysErr "Failed to parse suite manifest: $_"
        return $null
    }
}

function Find-UsysSuites {
    [CmdletBinding()]
    param(
        [string]$Name = '',
        [string]$Type = '',
        [string]$Runtime = ''
    )
    
    $clonepoolDir = Get-UsysClonepoolDir
    if (-not (Test-Path $clonepoolDir)) {
        return @()
    }
    
    $suites = @()
    Get-ChildItem -Path $clonepoolDir -Directory | ForEach-Object {
        $manifest = Get-UsysSuiteManifest -SuitePath $_.FullName
        if ($manifest) {
            # Filter by criteria
            if ($Name -and $manifest.name -ne $Name) { return }
            if ($Type -and $manifest.type -ne $Type) { return }
            if ($Runtime -and $manifest.runtime -ne $Runtime) { return }
            
            $suites += [PSCustomObject]@{
                Name = $manifest.name
                Version = $manifest.version
                Type = $manifest.type
                Runtime = $manifest.runtime
                Path = $_.FullName
                Manifest = $manifest
            }
        }
    }
    
    return $suites
}

function Invoke-UsysRun {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$SuiteName,

        [string]$Version = '',
        [switch]$DryRun,

        # Override accelerator: auto | tcg | whpx | hyperv | kvm
        # 'auto' = Phoenix picks the best available (default)
        # 'tcg'  = pure software, always works, slow
        # 'whpx' = Windows Hypervisor Platform, fast
        # 'hyperv' = WHPX + full Hyper-V enlightenments, fastest on Windows
        # 'kvm'  = Linux KVM, fast on Linux/WSL
        [ValidateSet('auto','tcg','whpx','hyperv','kvm')]
        [string]$Accel = 'auto',

        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]]$Arguments
    )
    
    Write-Host ''
    Write-UsysInfo "Running suite: $SuiteName"
    
    # Find suite
    $suites = Find-UsysSuites -Name $SuiteName
    if ($suites.Count -eq 0) {
        Write-UsysErr "Suite not found: $SuiteName"
        Write-UsysInfo "Run 'usys list-suites' to see available suites"
        return
    }
    
    # Handle version selection
    $suite = if ($Version) {
        $suites | Where-Object { $_.Version -eq $Version } | Select-Object -First 1
    } else {
        $suites | Sort-Object { [version]$_.Version } -Descending | Select-Object -First 1
    }
    
    if (-not $suite) {
        Write-UsysErr "Suite version not found: $SuiteName@$Version"
        return
    }
    
    $manifest = $suite.Manifest
    $entryPath = Join-Path $suite.Path $manifest.entry
    
    if (-not (Test-Path $entryPath)) {
        Write-UsysErr "Entry point not found: $($manifest.entry)"
        return
    }
    
    Write-UsysInfo "Suite: $($manifest.name) v$($manifest.version)"
    Write-UsysInfo "Type: $($manifest.type)"
    Write-UsysInfo "Runtime: $($manifest.runtime)"
    Write-UsysInfo "Entry: $($manifest.entry)"
    
    if ($DryRun) {
        Write-Host ''
        Write-Host '  [DRY RUN] Would execute:' -ForegroundColor Cyan
        Write-Host "    Runtime: $($manifest.runtime)" -ForegroundColor White
        Write-Host "    Entry: $entryPath" -ForegroundColor White
        Write-Host "    Args: $($Arguments -join ' ')" -ForegroundColor White
        Write-Host ''
        return
    }
    
    # Set environment variables from manifest
    if ($manifest.environment) {
        $manifest.environment.PSObject.Properties | ForEach-Object {
            $value = $_.Value
            # Handle variable substitution ${VAR:-default}
            if ($value -match '\$\{([^:}]+)(?::-(.*))?\}') {
                $envVar = $matches[1]
                $default = $matches[2]
                $value = if ([Environment]::GetEnvironmentVariable($envVar)) { [Environment]::GetEnvironmentVariable($envVar) } else { $default }
            }
            Set-Item -Path "env:$($_.Name)" -Value $value
        }
    }
    
    # Execute based on runtime
    Write-Host ''
    Write-UsysInfo 'Executing suite...'
    Write-Host ''
    
    try {
        switch ($manifest.runtime) {
            'python' {
                $pythonCmd = if (Get-Command python3 -ErrorAction SilentlyContinue) { 'python3' } else { 'python' }
                & $pythonCmd $entryPath @Arguments
            }
            'node' {
                & node $entryPath @Arguments
            }
            'bash' {
                $bash = Get-UsysGitBash
                if (-not $bash) {
                    Write-UsysErr 'Git Bash not found for bash runtime'
                    return
                }
                & $bash $entryPath @Arguments
            }
            'powershell' {
                & pwsh -File $entryPath @Arguments
            }
            'binary' {
                & $entryPath @Arguments
            }
            'qemu' {
                $qemu = Get-UsysQemu
                if (-not $qemu) {
                    Write-UsysErr 'QEMU not found. Run: usys distro fetch-qemu'
                    Write-UsysInfo 'Or drop qemu-system-x86_64.exe into your qemu-system suite directory.'
                    return
                }

                # Pull VM parameters from manifest environment (with defaults)
                $ram     = if ($manifest.environment.PHOENIX_VM_RAM)    { $manifest.environment.PHOENIX_VM_RAM }    else { '512M' }
                $cpus    = if ($manifest.environment.PHOENIX_VM_CPUS)   { $manifest.environment.PHOENIX_VM_CPUS }   else { '1' }
                $display = if ($manifest.environment.PHOENIX_VM_DISPLAY){ $manifest.environment.PHOENIX_VM_DISPLAY } else { 'sdl' }

                # Snapshot mode: writes go to a temp overlay — disk image stays pristine
                # Pass -Persist to write changes back to the image
                $snapshot = if ($Arguments -contains '-Persist') { '' } else { '-snapshot' }

                Write-UsysInfo "QEMU   : $qemu"
                Write-UsysInfo "Image  : $entryPath"
                Write-UsysInfo "RAM    : $ram  CPUs: $cpus  Display: $display"
                if ($snapshot) { Write-UsysInfo 'Mode   : ephemeral (changes discarded on exit — pass -Persist to save)' }
                else           { Write-UsysInfo 'Mode   : persistent (changes saved to image)' }
                Write-Host ''

                # ── Accelerator resolution ────────────────────────────────
                # 'hyperv' = WHPX + every Hyper-V enlightenment QEMU supports
                #            This is the Act 2 demo — near-native speed,
                #            Phoenix picked the engine, not Windows.
                # 'auto'   = Phoenix picks the best available
                # explicit = user override via --accel flag

                $resolvedAccel = $Accel

                if ($Accel -eq 'auto') {
                    if ($IsWindows -or $env:OS -eq 'Windows_NT') {
                        $hvFeature = Get-WindowsOptionalFeature -Online -FeatureName 'HypervisorPlatform' -ErrorAction SilentlyContinue
                        if ($hvFeature -and $hvFeature.State -eq 'Enabled') {
                            $resolvedAccel = 'whpx'
                        } else {
                            $resolvedAccel = 'tcg'
                        }
                    } else {
                        $resolvedAccel = if (Test-Path '/dev/kvm') { 'kvm' } else { 'tcg' }
                    }
                }

                switch ($resolvedAccel) {
                    'hyperv' { Write-UsysInfo 'Accelerator: Hyper-V enlightenments (WHPX + full HV) — maximum speed' }
                    'whpx'   { Write-UsysInfo 'Accelerator: WHPX (Windows Hypervisor Platform) — near-native speed' }
                    'kvm'    { Write-UsysInfo 'Accelerator: KVM — near-native speed' }
                    'tcg'    { Write-UsysInfo 'Accelerator: TCG (software emulation) — works everywhere, no HW required' }
                }
                if ($resolvedAccel -eq 'tcg' -and ($IsWindows -or $env:OS -eq 'Windows_NT')) {
                    Write-UsysInfo '  → For full speed run: usys run debian --accel hyperv'
                }

                # ── Cloud-init seed (convention: a 'seed/user-data' dir next to
                #    the suite's disk image) — no ISO tooling needed. Serves the
                #    seed over HTTP on loopback; QEMU's user-mode network maps
                #    that to 10.0.2.2 inside the guest. See PHOENIX_MANUAL.md
                #    "Distro demo" section for the story behind this.
                $seedDir = Join-Path $suite.Path 'seed'
                $netArgs = @('-net', 'nic,model=virtio', '-net', 'user')
                if (Test-Path (Join-Path $seedDir 'user-data')) {
                    $seedPort = 8000
                    $listening = Get-NetTCPConnection -LocalPort $seedPort -State Listen -ErrorAction SilentlyContinue
                    if (-not $listening) {
                        $pythonCmd = if (Get-Command python -ErrorAction SilentlyContinue) { (Get-Command python).Source }
                                     elseif (Get-Command python3 -ErrorAction SilentlyContinue) { (Get-Command python3).Source }
                                     else { $null }
                        if ($pythonCmd) {
                            Start-Process -FilePath $pythonCmd -ArgumentList @('-m','http.server',"$seedPort",'--bind','127.0.0.1') `
                                -WorkingDirectory $seedDir -WindowStyle Hidden
                            Write-UsysInfo "Cloud-init seed server started on 127.0.0.1:$seedPort ($seedDir)"
                            Start-Sleep -Milliseconds 500
                        } else {
                            Write-UsysWarn 'python not found — cannot serve cloud-init seed. VM will boot with no login.'
                        }
                    }
                    $netArgs = @('-net', "user,hostfwd=tcp::2222-:22", '-net', 'nic,model=virtio')
                    $smbiosArg = @('-smbios', "type=1,serial=ds=nocloud-net;s=http://10.0.2.2:$seedPort/")
                    Write-UsysInfo "Cloud-init: user 'phoenix' / password 'phoenix' (sudo, no key needed) — SSH: ssh -p 2222 phoenix@127.0.0.1"
                }

                # ── Build QEMU argument list ──────────────────────────────
                $qemuArgs = @(
                    '-m',       $ram,
                    '-smp',     $cpus,
                    '-display', $display,
                    '-drive',   "file=$entryPath,format=qcow2,if=virtio"
                ) + $netArgs
                if ($smbiosArg) { $qemuArgs += $smbiosArg }

                # Accelerator args — hyperv gets the full enlightenment set
                # These tell the guest kernel to use Hyper-V hypercalls instead of
                # emulated hardware for timers, spinlocks, APIC, etc.
                # Result: boot time drops from minutes to seconds.
                if ($resolvedAccel -eq 'hyperv') {
                    $qemuArgs += @('-accel', 'whpx')
                    $qemuArgs += @('-cpu', 'host,hv_relaxed,hv_spinlocks=0x1fff,hv_vapic,hv_time,hv_crash,hv_reset,hv_vpindex,hv_runtime,hv_synic,hv_stimer,hv_tlbflush,hv_ipi')
                } elseif ($resolvedAccel -eq 'kvm') {
                    $qemuArgs += @('-accel', 'kvm')
                    $qemuArgs += @('-cpu', 'host')
                } else {
                    $qemuArgs += @('-accel', $resolvedAccel)
                }
                if ($snapshot) { $qemuArgs += $snapshot }

                # Pass any extra user args through (e.g. -cdrom seed.iso for cloud-init)
                $extraArgs = $Arguments | Where-Object { $_ -ne '-Persist' }
                if ($extraArgs) { $qemuArgs += $extraArgs }

                & $qemu @qemuArgs
            }
            default {
                Write-UsysErr "Unsupported runtime: $($manifest.runtime)"
            }
        }
        
        Write-Host ''
        Write-UsysOk "Suite execution complete"
    } catch {
        Write-Host ''
        Write-UsysErr "Suite execution failed: $_"
    }
    
    Write-Host ''
}

function Invoke-UsysListSuites {
    [CmdletBinding()]
    param(
        [string]$Type = '',
        [string]$Runtime = ''
    )
    
    Write-Host ''
    Write-UsysInfo 'Available suites in clonepool:'
    Write-Host ''
    
    $suites = Find-UsysSuites -Type $Type -Runtime $Runtime
    
    if ($suites.Count -eq 0) {
        Write-UsysWarn 'No suites found in clonepool'
        Write-UsysInfo 'Clone a suite with: usys clone <suite-directory>'
        Write-Host ''
        return
    }
    
    $suites | Sort-Object Name, { [version]$_.Version } | ForEach-Object {
        $desc = if ($_.Manifest.description) { " - $($_.Manifest.description)" } else { '' }
        Write-Host "  $($_.Name) " -NoNewline -ForegroundColor Cyan
        Write-Host "v$($_.Version) " -NoNewline -ForegroundColor Green
        Write-Host "[$($_.Type)/$($_.Runtime)]" -NoNewline -ForegroundColor DarkGray
        Write-Host $desc -ForegroundColor White
    }
    
    Write-Host ''
    Write-Host "  Total: $($suites.Count) suite(s)" -ForegroundColor DarkGray
    Write-Host ''
}

function Invoke-UsysLoad {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$SuiteName,
        
        [string]$Version = ''
    )
    
    Write-Host ''
    Write-UsysInfo "Loading suite: $SuiteName"
    
    # Find suite
    $suites = Find-UsysSuites -Name $SuiteName
    if ($suites.Count -eq 0) {
        Write-UsysErr "Suite not found: $SuiteName"
        return $null
    }
    
    # Handle version selection
    $suite = if ($Version) {
        $suites | Where-Object { $_.Version -eq $Version } | Select-Object -First 1
    } else {
        $suites | Sort-Object { [version]$_.Version } -Descending | Select-Object -First 1
    }
    
    if (-not $suite) {
        Write-UsysErr "Suite version not found: $SuiteName@$Version"
        return $null
    }
    
    Write-UsysOk "Loaded: $($suite.Name) v$($suite.Version)"
    Write-Host ''
    
    # Return suite object for further use
    return $suite
}

# =============================================================================
# COMMAND: help
# =============================================================================
function Show-UsysHelp {
    @"

  UnitedSys (usys) v$($script:UsysVersion) — Phoenix DevOps global command layer
  USys — United Systems | jwl247 | GPL-3.0

  Usage:
    usys <command> [args...]

  Core:
    init                         First-time setup (dirs, config, PATH)
    status                       Repo sectors, engines, env, catalog
    help                         This message
    version                      Print version
    path-register                Add usys to user PATH

  Intake / Clone:
    intake <file>                Sector 4 vault intake (TAV / breach_coms4)
    intake dir <path>            Intake all files in directory
    clone <file> [-Category] [-Tag] [-Destination] [-DryRun]
    open <file>                  Magic extension handler (.lol, .phx)
    download <url>               Download + auto-intake in one command
    download <url> -OutFile <p>  Download to specific path, then intake
    download <url> -NoIntake     Download only, skip intake

  Auto-intake (Downloads\ watcher):
    watch start                  Watch ~/Downloads, prompt on each new file
    watch start -Auto            Watch ~/Downloads, silent auto-intake
    watch start -Path <dir>      Watch a custom directory
    watch stop                   Stop the watcher
    watch pending                Review + intake files caught since last check
    watch status                 Is the watcher running?

  Discovery:
    search <query>               Search clonepool + catalog
    pull <suite>                 Pull suite record from D1 and stage locally

  Distros (Linux VMs via QEMU — no install, no WSL, Phoenix brings the OS):
    distro list                  Show registered distros
    distro fetch-qemu            Instructions to get QEMU binary
    distro intake-qemu           Intake QEMU binary into clone pool
    run debian                   Boot Debian 12 VM (auto accelerator)
    run ubuntu                   Boot Ubuntu 24.04 VM (auto accelerator)
    run debian --accel tcg       Act 1: pure software emulation, no HW required
    run debian --accel hyperv    Act 2: WHPX + Hyper-V enlightenments, near-native speed

  Registry (requires ~/.usys/usys.sh):
    register <file> <name>       Register callable file
    call <name> [args...]        Invoke registered file
    list | info <name> | where <name>
    swap <name> <newfile> | rollback <name> [ver]
    remove <name> | sync <name> <dest>

  Magic extensions:
    .phx  → clone via Sector 2 (package handler pipeline)
    .lol  → intake via Sector 4 (vault pipeline)

  Environment:
    PHOENIX_ROOT, PHOENIX_BASH, PHOENIX_INTAKE, PHOENIX_INTAKE_SECTOR4
    PHOENIX_AUTH, PHOENIX_WORKER_URL, CLONEPOOL_DIR

"@
}

# =============================================================================
# MAIN DISPATCHER — global function exported on dot-source
# =============================================================================
function global:usys {
    [CmdletBinding()]
    param(
        [Parameter(Position = 0)]
        [string]$Command = 'help',

        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]]$Rest
    )

    Test-UsysElevation | Out-Null

    switch ($Command.ToLowerInvariant()) {
        'init'          { Invoke-UsysInit }
        'status'        { Invoke-UsysStatus }
        'help'          { Show-UsysHelp }
        '--help'        { Show-UsysHelp }
        '-h'            { Show-UsysHelp }
        'version'       { Write-Output $script:UsysVersion }
        'path-register' { Register-UsysPath | Out-Null; Write-UsysOk 'PATH registration complete' }

        'intake' {
            if ($Rest.Count -ge 2 -and $Rest[0] -eq 'dir') {
                Invoke-UsysIntake -Path $Rest[1] -Mode 'dir'
            } elseif ($Rest.Count -ge 1 -and $Rest[0] -eq 'status') {
                Invoke-UsysIntake -Path '' -Mode 'status'
            } elseif ($Rest.Count -ge 1) {
                $dry = $Rest -contains '-DryRun' -or $Rest -contains '--dry-run'
                $path = $Rest | Where-Object { $_ -notin '-DryRun', '--dry-run' } | Select-Object -First 1
                Invoke-UsysIntake -Path $path -Mode 'file' -DryRun:$dry
            } else {
                Write-UsysErr 'usage: usys intake <file> | usys intake dir <path> | usys intake status'
            }
        }

        'clone' {
            if ($Rest.Count -lt 1) {
                Write-UsysErr 'usage: usys clone <file> [-Category x] [-Tag y] [-Destination T2] [-DryRun]'
                return
            }
            $dry  = $Rest -contains '-DryRun' -or $Rest -contains '--dry-run'
            $path = $Rest[0]
            $cat  = ''
            $tag  = ''
            $dest = ''
            for ($i = 1; $i -lt $Rest.Count; $i++) {
                switch ($Rest[$i]) {
                    '-Category'    { if ($i + 1 -lt $Rest.Count) { $cat  = $Rest[++$i] } }
                    '-Tag'         { if ($i + 1 -lt $Rest.Count) { $tag  = $Rest[++$i] } }
                    '-Destination' { if ($i + 1 -lt $Rest.Count) { $dest = $Rest[++$i] } }
                }
            }
            Invoke-UsysClone -Path $path -Category $cat -Tag $tag -Destination $dest -DryRun:$dry
        }

        'search' {
            if ($Rest.Count -lt 1) { Write-UsysErr 'usage: usys search <query>'; return }
            Invoke-UsysSearch -Query ($Rest -join ' ')
        }

        'download' {
            if ($Rest.Count -lt 1) { Write-UsysErr 'usage: usys download <url> [-OutFile <path>] [-NoIntake]'; return }
            $url     = $Rest[0]
            $outFile = ''
            $noIntake = $false
            for ($i = 1; $i -lt $Rest.Count; $i++) {
                switch ($Rest[$i]) {
                    '-OutFile'   { if ($i + 1 -lt $Rest.Count) { $outFile = $Rest[++$i] } }
                    '-NoIntake'  { $noIntake = $true }
                }
            }
            $params = @{ Uri = $url }
            if ($outFile)   { $params['OutFile']   = $outFile }
            if ($noIntake)  { $params['NoIntake']  = $true }
            Invoke-UsysDownload @params
        }

        'watch' {
            $sub = if ($Rest.Count -gt 0) { $Rest[0] } else { 'status' }
            switch ($sub) {
                'start' {
                    $auto = $Rest -contains '-Auto' -or $Rest -contains '--auto'
                    $pathArg = ''
                    for ($i = 1; $i -lt $Rest.Count; $i++) {
                        if ($Rest[$i] -eq '-Path' -and $i + 1 -lt $Rest.Count) { $pathArg = $Rest[++$i] }
                    }
                    $p = @{}
                    if ($pathArg)  { $p['Path']       = $pathArg }
                    if ($auto)     { $p['AutoIntake']  = $true }
                    Start-UsysWatcher @p
                }
                'stop'    { Stop-UsysWatcher }
                'pending' { Get-UsysWatcherPending }
                'status'  {
                    $j = if ($script:UsysWatcherJob) { $script:UsysWatcherJob } else {
                        Get-Job -Name 'PhoenixWatcher' -ErrorAction SilentlyContinue | Select-Object -First 1
                    }
                    if ($j) { Write-UsysInfo "Watcher running — job $($j.Id), state: $($j.State)" }
                    else    { Write-UsysInfo 'Watcher not running. Start with: usys watch start' }
                }
                default { Write-UsysErr "usage: usys watch start|stop|pending|status" }
            }
        }

        'open' {
            if ($Rest.Count -lt 1) { Write-UsysErr 'usage: usys open <file>'; return }
            $dry = $Rest -contains '-DryRun'
            $path = $Rest | Where-Object { $_ -notin '-DryRun' } | Select-Object -First 1
            Invoke-UsysOpen -Path $path -DryRun:$dry
        }

        'run' {
            if ($Rest.Count -lt 1) { Write-UsysErr 'usage: usys run <suite> [--accel auto|tcg|whpx|hyperv|kvm] [args...]'; return }
            $dry       = $Rest -contains '-DryRun' -or $Rest -contains '--dry-run'
            $accel     = 'auto'
            $suiteName = $Rest[0]
            $version   = ''

            # Handle suite@version syntax
            if ($suiteName -match '^(.+)@(.+)$') {
                $suiteName = $matches[1]
                $version   = $matches[2]
            }

            # Parse --accel flag
            $filteredRest = [System.Collections.Generic.List[string]]::new()
            $skipNext = $false
            foreach ($token in ($Rest | Select-Object -Skip 1)) {
                if ($skipNext) { $skipNext = $false; continue }
                if ($token -eq '--accel' -or $token -eq '-accel') {
                    # next token is the value — peek by re-iterating with index below
                    $skipNext = $true
                    continue
                }
                $filteredRest.Add($token)
            }
            # Second pass for --accel=value and value-after-flag
            for ($i = 1; $i -lt $Rest.Count; $i++) {
                if ($Rest[$i] -match '^--?accel=(.+)$') {
                    $accel = $matches[1]
                } elseif (($Rest[$i] -eq '--accel' -or $Rest[$i] -eq '-accel') -and $i + 1 -lt $Rest.Count) {
                    $accel = $Rest[$i + 1]
                }
            }

            $passArgs = $filteredRest | Where-Object { $_ -notin '-DryRun', '--dry-run' }
            Invoke-UsysRun -SuiteName $suiteName -Version $version -Accel $accel -DryRun:$dry -Arguments $passArgs
        }

        'pull' {
            if ($Rest.Count -lt 1) { Write-UsysErr 'usage: usys pull <suite>'; return }
            $dry = $Rest -contains '-DryRun' -or $Rest -contains '--dry-run'
            $name = $Rest | Where-Object { $_ -notin '-DryRun','--dry-run' } | Select-Object -First 1
            Invoke-UsysPull -SuiteName $name -DryRun:$dry
        }

        'list-suites' {
            $type = ''
            $runtime = ''
            for ($i = 0; $i -lt $Rest.Count; $i++) {
                if ($Rest[$i] -eq '--type' -and $i + 1 -lt $Rest.Count) { $type = $Rest[++$i] }
                if ($Rest[$i] -eq '--runtime' -and $i + 1 -lt $Rest.Count) { $runtime = $Rest[++$i] }
            }
            Invoke-UsysListSuites -Type $type -Runtime $runtime
        }

        'load' {
            if ($Rest.Count -lt 1) { Write-UsysErr 'usage: usys load <suite> [@version]'; return }
            $suiteName = $Rest[0]
            $version = ''
            
            # Handle suite@version syntax
            if ($suiteName -match '^(.+)@(.+)$') {
                $suiteName = $matches[1]
                $version = $matches[2]
            }
            
            $suite = Invoke-UsysLoad -SuiteName $suiteName -Version $version
            if ($suite) {
                # Return suite object for interactive use
                return $suite
            }
        }

        'distro' {
            $sub = if ($Rest.Count -ge 1) { $Rest[0] } else { 'list' }
            switch ($sub.ToLowerInvariant()) {
                'list' {
                    Write-Host ''
                    Write-UsysInfo 'Phoenix distro registry:'
                    Write-Host ''
                    $distroSuites = Find-UsysSuites -Type 'distro'
                    if ($distroSuites.Count -eq 0) {
                        Write-Host '    No distros registered. Run: usys distro add debian' -ForegroundColor DarkGray
                    } else {
                        $distroSuites | ForEach-Object {
                            $src = if ($_.Manifest.metadata.source) { "  <- $($_.Manifest.metadata.source)" } else { '' }
                            Write-Host "    $($_.Name) " -NoNewline -ForegroundColor Cyan
                            Write-Host "v$($_.Version) " -NoNewline -ForegroundColor Green
                            Write-Host "[$($_.Manifest.metadata.flavor)]$src" -ForegroundColor DarkGray
                        }
                    }
                    Write-Host ''
                    Write-UsysInfo "Run a distro: usys run debian"
                    Write-UsysInfo "QEMU binary : $(if (Get-UsysQemu) { Get-UsysQemu } else { 'NOT FOUND — run: usys distro fetch-qemu' })"
                    Write-Host ''
                }
                'fetch-qemu' {
                    # Download QEMU for Windows into the qemu-system suite directory
                    $qemuSuites = Find-UsysSuites -Name 'qemu-system'
                    if ($qemuSuites.Count -eq 0) {
                        Write-UsysErr 'qemu-system suite not found in clonepool. Clone the suite first.'
                        return
                    }
                    $dest = Join-Path $qemuSuites[0].Path 'qemu-system-x86_64.exe'
                    if (Test-Path $dest) {
                        Write-UsysOk "QEMU already present: $dest"
                        return
                    }
                    Write-UsysInfo 'QEMU is not bundled — download it once from https://qemu.weilnetz.de/w64/'
                    Write-UsysInfo "Place qemu-system-x86_64.exe at: $dest"
                    Write-UsysInfo 'Then run: usys distro intake-qemu'
                    Write-Host ''
                }
                'intake-qemu' {
                    $qemu = Get-UsysQemu
                    if (-not $qemu) { Write-UsysErr 'QEMU binary not found. Run: usys distro fetch-qemu'; return }
                    Write-UsysInfo "Intaking QEMU binary into Phoenix clone pool..."
                    $pythonCmd = if (Get-Command python3 -ErrorAction SilentlyContinue) { 'python3' } else { 'python' }
                    $intakePy = Join-Path (Get-UsysRepoRoot) 'phoenix-core\tools\intake.py'
                    & $pythonCmd $intakePy $qemu
                    Write-Host ''
                }
                default {
                    Write-Host ''
                    Write-Host '  usys distro commands:' -ForegroundColor Cyan
                    Write-Host '    list           — show registered distros'
                    Write-Host '    fetch-qemu     — instructions to get QEMU binary'
                    Write-Host '    intake-qemu    — intake QEMU binary into Phoenix clone pool'
                    Write-Host ''
                    Write-Host '  Run a distro:'
                    Write-Host '    usys run debian'
                    Write-Host '    usys run ubuntu'
                    Write-Host ''
                }
            }
        }

        { $_ -in @('register', 'call', 'swap', 'rollback', 'list', 'info', 'remove', 'where', 'sync') } {
            Invoke-UsysDelegate -SubCommand $Command @Rest
        }

        default {
            Write-UsysErr "unknown command: $Command"
            Show-UsysHelp
        }
    }
}

# =============================================================================
# SHIM ENTRY — when invoked as: pwsh -File usys.ps1 <command> [args]
# Dot-source mode: . usys.ps1  →  usys function available in session
# =============================================================================
Set-Alias -Name phx -Value usys -Scope Global -Force -ErrorAction SilentlyContinue

# =============================================================================
# COMMAND: download — Invoke-WebRequest wrapper that auto-intakes the result
# =============================================================================
function global:Invoke-UsysDownload {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory, Position = 0)][string]$Uri,
        [string]$OutFile,
        [switch]$NoIntake
    )

    # Derive output filename from URI if not given
    if (-not $OutFile) {
        $leaf    = [System.IO.Path]::GetFileName(([uri]$Uri).LocalPath)
        if (-not $leaf) { $leaf = 'download' }
        $OutFile = Join-Path ([System.IO.Path]::GetTempPath()) $leaf
    }

    Write-UsysInfo "Downloading: $Uri"
    Write-UsysInfo "        To : $OutFile"
    Invoke-WebRequest -Uri $Uri -OutFile $OutFile
    Write-UsysOk "Download complete"

    if (-not $NoIntake) {
        Write-UsysInfo "Auto-intaking into Phoenix clonepool..."
        $py = if (Get-Command python3 -ErrorAction SilentlyContinue) { 'python3' } else { 'python' }
        $intakePy = Join-Path (Get-UsysRepoRoot) 'phoenix-core\tools\intake.py'
        & $py $intakePy $OutFile
        Write-UsysOk "Intaked: $OutFile"
    }
}
Set-Alias -Name usys-download -Value Invoke-UsysDownload -Scope Global -Force -ErrorAction SilentlyContinue

# =============================================================================
# COMMAND: watch — filesystem watcher on Downloads\ that auto-intakes new files
# =============================================================================

# Shared state for the watcher job
$script:UsysWatcherJob = $null

function Start-UsysWatcher {
    [CmdletBinding()]
    param(
        [string]$Path     = (Join-Path $HOME 'Downloads'),
        [switch]$AutoIntake   # if set: silent auto-intake; otherwise: prompt
    )

    if ($script:UsysWatcherJob -and $script:UsysWatcherJob.State -eq 'Running') {
        Write-UsysWarn "Watcher already running (job $($script:UsysWatcherJob.Id)). Run: usys watch stop"
        return
    }

    if (-not (Test-Path $Path)) {
        Write-UsysErr "Watch path not found: $Path"
        return
    }

    $repoRoot  = Get-UsysRepoRoot
    $intakePy  = Join-Path $repoRoot 'phoenix-core\tools\intake.py'
    $auto      = $AutoIntake.IsPresent

    $script:UsysWatcherJob = Start-Job -Name 'PhoenixWatcher' -ScriptBlock {
        param($watchPath, $intakePy, $auto)

        $watcher                     = New-Object System.IO.FileSystemWatcher
        $watcher.Path                = $watchPath
        $watcher.Filter              = '*.*'
        $watcher.IncludeSubdirectories = $false
        $watcher.NotifyFilter        = [System.IO.NotifyFilters]::FileName

        $handler = {
            param($src, $ev)
            $file = $ev.FullPath
            # Wait briefly — browser writes in chunks, give it a moment to finish
            Start-Sleep -Seconds 2
            # Skip temp/partial files (Chrome .crdownload, Edge .tmp, etc.)
            if ($file -match '\.(crdownload|tmp|part|download)$') { return }
            if (-not (Test-Path $file)) { return }

            if ($auto) {
                $py = if (Get-Command python3 -ErrorAction SilentlyContinue) { 'python3' } else { 'python' }
                & $py $intakePy $file
            } else {
                # Toast-style prompt via BurntToast if available, else console
                $msg = "Phoenix: Intake '$([System.IO.Path]::GetFileName($file))'?"
                $hasBurnt = Get-Module -ListAvailable -Name BurntToast -ErrorAction SilentlyContinue
                if ($hasBurnt) {
                    Import-Module BurntToast -ErrorAction SilentlyContinue
                    New-BurntToastNotification -Text 'Phoenix Intake', $msg -ErrorAction SilentlyContinue
                }
                # Always write to job output so the parent can show it
                Write-Output "INTAKE_PROMPT:$file"
            }
        }

        Register-ObjectEvent $watcher Created -Action $handler | Out-Null
        $watcher.EnableRaisingEvents = $true

        Write-Output "WATCHER_STARTED:$watchPath"

        # Keep alive — check for stop signal every second
        while ($true) { Start-Sleep -Seconds 1 }
    } -ArgumentList $Path, $intakePy, $auto

    # Poll for startup confirmation (up to 5s)
    $deadline = (Get-Date).AddSeconds(5)
    while ((Get-Date) -lt $deadline) {
        $out = Receive-Job $script:UsysWatcherJob -Keep 2>$null
        if ($out -match 'WATCHER_STARTED') { break }
        Start-Sleep -Milliseconds 200
    }

    Write-UsysOk "Watcher started — monitoring: $Path"
    Write-UsysInfo "Job ID: $($script:UsysWatcherJob.Id)  |  run 'usys watch stop' to stop"
    if (-not $auto) {
        Write-UsysInfo "Mode: prompt — run 'usys watch pending' to see files waiting for intake"
    } else {
        Write-UsysInfo "Mode: auto-intake — every new download is intaked immediately"
    }
}

function Stop-UsysWatcher {
    if (-not $script:UsysWatcherJob) {
        # Try to find it by name if script was reloaded
        $script:UsysWatcherJob = Get-Job -Name 'PhoenixWatcher' -ErrorAction SilentlyContinue | Select-Object -First 1
    }
    if (-not $script:UsysWatcherJob) {
        Write-UsysWarn 'No watcher job found.'
        return
    }
    Stop-Job  $script:UsysWatcherJob
    Remove-Job $script:UsysWatcherJob
    $script:UsysWatcherJob = $null
    Write-UsysOk 'Watcher stopped.'
}

function Get-UsysWatcherPending {
    if (-not $script:UsysWatcherJob) {
        $script:UsysWatcherJob = Get-Job -Name 'PhoenixWatcher' -ErrorAction SilentlyContinue | Select-Object -First 1
    }
    if (-not $script:UsysWatcherJob) { Write-UsysWarn 'Watcher not running.'; return }

    $py       = if (Get-Command python3 -ErrorAction SilentlyContinue) { 'python3' } else { 'python' }
    $intakePy = Join-Path (Get-UsysRepoRoot) 'phoenix-core\tools\intake.py'

    $lines = Receive-Job $script:UsysWatcherJob -Keep 2>$null | Where-Object { $_ -match '^INTAKE_PROMPT:' }
    if (-not $lines) { Write-UsysInfo 'No pending files.'; return }

    foreach ($line in $lines) {
        $file = $line -replace '^INTAKE_PROMPT:', ''
        Write-Host ''
        Write-Host "  New file: $file" -ForegroundColor Yellow
        $choice = Read-Host '  Intake into Phoenix? [Y/n]'
        if ($choice -eq '' -or $choice -match '^[Yy]') {
            & $py $intakePy $file
            Write-UsysOk "Intaked: $([System.IO.Path]::GetFileName($file))"
        } else {
            Write-UsysInfo "Skipped: $([System.IO.Path]::GetFileName($file))"
        }
    }
}

# Back-compat: expose clone as a global function that delegates to usys clone
function global:clone {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory, Position = 0)][string]$Path,
        [string]$Tag = '', [string]$Category = '', [string]$Destination = '', [switch]$DryRun
    )
    Invoke-UsysClone -Path $Path -Tag $Tag -Category $Category -Destination $Destination -DryRun:$DryRun
}
Set-Alias -Name phx-clone -Value clone -Scope Global -Force -ErrorAction SilentlyContinue

# Direct script invocation (shim mode)
if ($MyInvocation.InvocationName -ne '.' -and $MyInvocation.Line -notmatch '^\s*\.\s') {
    $cmd  = $args[0]
    $rest = @()
    if ($args.Count -gt 1) { $rest = $args[1..($args.Count - 1)] }
    if (-not $cmd) { Show-UsysHelp; return }
    usys -Command $cmd -Rest $rest
}