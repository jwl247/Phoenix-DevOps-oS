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
        (Join-Path $repo 'sector2\package-handler\intake\intake.sh')
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

    @($script:UsysHome, $script:UsysBin, $script:UsysLogDir,
      (Join-Path $script:UsysHome 'versions'),
      (Get-UsysClonepoolDir),
      (Join-Path $HOME '.catalog')) | ForEach-Object {
        if (-not (Test-Path $_)) {
            New-Item -ItemType Directory -Path $_ -Force | Out-Null
            Write-UsysOk "created $_"
        }
    }

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
        Write-UsysWarn 'PATH not updated — run: usys path-register'
    }

    Write-Host ''
    Write-UsysInfo 'Next: usys status'
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

  Discovery:
    search <query>               Search clonepool + catalog

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

        'open' {
            if ($Rest.Count -lt 1) { Write-UsysErr 'usage: usys open <file>'; return }
            $dry = $Rest -contains '-DryRun'
            $path = $Rest | Where-Object { $_ -notin '-DryRun' } | Select-Object -First 1
            Invoke-UsysOpen -Path $path -DryRun:$dry
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