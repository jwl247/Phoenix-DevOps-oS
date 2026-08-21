#Requires -Version 7.0
<#
.SYNOPSIS
    Phoenix intake — PowerShell 7 wrapper for Sector 2 clonepool intake.

.DESCRIPTION
    Modernized intake command for Windows.  Wraps package-handler intake.sh
    (hex identity, sidecar, clonepool, custody, D1 sync).  Keeps what works
    from the bash pipeline; adds PS7 ergonomics: -DryRun, structured errors,
    auto path resolution, and usys integration.

    Sector 4 vault intake remains: usys intake <file>

    Dot-source:
      . "$HOME\Phoenix\Phoenix-DevOps-oS\scripts\intake.ps1"
      intake ./myfile.py

    Shim:
      pwsh -File intake.ps1 ./myfile.py
      pwsh -File intake.ps1 status

.NOTES
    Author  : jwl247 / Phoenix DevOps LLC
    License : GPL v3
    Sector  : 2 (package handler / clonepool)
#>

# =============================================================================
# METADATA
# =============================================================================
$script:IntakeVersion = '1.0.0'
$script:IntakeRoot    = $PSScriptRoot
$script:IntakeRepo    = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

# =============================================================================
# OUTPUT
# =============================================================================
function Write-IntakeInfo([string]$Message) {
    Write-Host "  intake: $Message" -ForegroundColor Cyan
}

function Write-IntakeOk([string]$Message) {
    Write-Host "  intake: $Message" -ForegroundColor Green
}

function Write-IntakeWarn([string]$Message) {
    Write-Warning "intake: $Message"
}

function Write-IntakeErr([string]$Message) {
    Write-Error "intake: $Message"
}

# =============================================================================
# PATH RESOLUTION
# =============================================================================
function Get-IntakeRepoRoot {
    if ($env:PHOENIX_ROOT -and (Test-Path $env:PHOENIX_ROOT)) {
        return (Resolve-Path $env:PHOENIX_ROOT).Path
    }
    return $script:IntakeRepo
}

function Get-IntakeGitBash {
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
    $p = $WindowsPath.Replace([char]92, [char]47)
    if ($p -match '^([A-Za-z]):(.*)') {
        return "/$($Matches[1].ToLower())$($Matches[2])"
    }
    return $p
}

function Get-IntakeSh {
    $repo   = Get-IntakeRepoRoot
    $parent = Split-Path $repo -Parent
    $candidates = @(
        $env:PHOENIX_INTAKE,
        (Join-Path $repo 'sector2\package-handler\intake.sh'),
        (Join-Path $parent 'package-handler\intake\intake.sh'),
        (Join-Path $HOME 'Phoenix\package-handler\intake\intake.sh'),
        (Join-Path $parent 'Phoenix-Package_handler\intake\intake.sh')
    ) | Where-Object { $_ -and (Test-Path $_) }
    return $candidates | Select-Object -First 1
}

function Get-IntakeClonepoolDir {
    if ($env:CLONEPOOL_DIR) { return $env:CLONEPOOL_DIR }
    return (Join-Path $HOME 'Phoenix\clonepool')
}

function Import-PhoenixEnv {
    $envFile = Join-Path $HOME '.phoenix_env.ps1'
    if (Test-Path $envFile) { . $envFile }
}

# =============================================================================
# CORE: invoke bash intake.sh with proper env
# =============================================================================
function Invoke-IntakeEngine {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string[]]$Args,

        [switch]$DryRun
    )

    Import-PhoenixEnv

    $bash   = Get-IntakeGitBash
    $intake = Get-IntakeSh

    if (-not $bash)   { Write-IntakeErr 'Git Bash not found. Install Git for Windows or set PHOENIX_BASH.'; return 1 }
    if (-not $intake) { Write-IntakeErr 'intake.sh not found. Run install.ps1 or set PHOENIX_INTAKE.'; return 1 }

    if (-not $env:PHOENIX_AUTH)       { Write-IntakeWarn 'PHOENIX_AUTH not set — D1 sync skipped' }
    if (-not $env:PHOENIX_WORKER_URL) { Write-IntakeWarn 'PHOENIX_WORKER_URL not set — D1 sync skipped' }
    if (-not $env:CLONEPOOL_DIR)      { $env:CLONEPOOL_DIR = Get-IntakeClonepoolDir }

    $bashIntake = ConvertTo-GitBashPath $intake
    $bashArgs   = $Args | ForEach-Object {
        if ($_ -match '^[A-Za-z]:\\') { ConvertTo-GitBashPath $_ } else { $_ }
    }

    if ($DryRun) {
        Write-Host ''
        Write-Host '  [DRY RUN] Phoenix Intake (Sector 2)' -ForegroundColor Cyan
        Write-Host "  Bash      : $bash"
        Write-Host "  intake.sh : $intake"
        Write-Host "  Args      : $($bashArgs -join ' ')"
        Write-Host "  Clonepool : $env:CLONEPOOL_DIR"
        Write-Host "  Worker    : $($env:PHOENIX_WORKER_URL)"
        Write-Host ''
        return 0
    }

    # Bash env: source .phoenix_env.sh so curl/D1 auth works in Git Bash
    $envSh = ConvertTo-GitBashPath (Join-Path $HOME '.phoenix_env.sh')
    $cmd   = "source '$envSh' 2>/dev/null; bash '$bashIntake' $($bashArgs -join ' ')"

    Write-Host ''
    Write-IntakeInfo "-> $($Args -join ' ')"
    & $bash -lc $cmd | Out-Host
    $code = $LASTEXITCODE
    if ($code -eq 0) { Write-IntakeOk 'complete' } else { Write-IntakeErr "exited $code" }
    Write-Host ''
    return $code
}

# =============================================================================
# COMMANDS
# =============================================================================
function Invoke-IntakeFile {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory, Position = 0)]
        [string]$Path,

        [string]$Backend = 'direct',
        [string]$Notes  = '',
        [switch]$DryRun
    )

    $resolved = Resolve-Path -Path $Path -ErrorAction SilentlyContinue
    if (-not $resolved) {
        Write-IntakeErr "path not found — '$Path'"
        return 1
    }

    $args = @($resolved.Path, $Backend)
    if ($Notes) { $args += $Notes }
    return Invoke-IntakeEngine -Args $args -DryRun:$DryRun
}

function Invoke-IntakeBackend {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory, Position = 0)][string]$PackageName,
        [Parameter(Mandatory, Position = 1)][string]$Backend,
        [Parameter(Mandatory, Position = 2)][string]$Version,
        [string]$InstallPath = '',
        [switch]$DryRun
    )

    $args = @('backend', $PackageName, $Backend, $Version)
    if ($InstallPath) {
        $resolved = Resolve-Path -Path $InstallPath -ErrorAction SilentlyContinue
        if ($resolved) { $args += $resolved.Path }
    }
    return Invoke-IntakeEngine -Args $args -DryRun:$DryRun
}

function Invoke-IntakeStatus {
    [CmdletBinding()]
    param([switch]$DryRun)
    return Invoke-IntakeEngine -Args @('status') -DryRun:$DryRun
}

function Invoke-IntakeClone {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory, Position = 0)]
        [string]$Name,

        [switch]$DryRun
    )

    # intake.sh's intake_clone() looks the target up by hex(name) in the
    # clonepool -- it expects a BARE FILENAME, not a path. Normal `intake
    # <file>` takes a full path, so passing a path here is a natural mistake.
    # Strip it down to the basename rather than failing on a lookup miss.
    $bareName = Split-Path -Path $Name -Leaf
    if ($bareName -ne $Name) {
        Write-IntakeWarn "clone expects a bare filename, not a path -- using '$bareName'"
    }

    return Invoke-IntakeEngine -Args @('clone', $bareName) -DryRun:$DryRun
}

function Show-IntakeHelp {
    @"

  Phoenix Intake v$($script:IntakeVersion) — Sector 2 clonepool wrapper
  USys — United Systems | jwl247 | GPL-3.0

  Usage:
    intake <file> [backend] [notes]       Intake file into clonepool
    intake clone <filename>               Pull a file from clonepool to cwd (local, falls back to R2)
    intake backend <pkg> <be> <ver> [path] Register backend install
    intake status                         Clonepool summary
    intake help                           This message

  Parameters (function mode):
    intake -Path <file> [-Backend] [-Notes] [-DryRun]
    intake -CloneMode -CloneName <filename> [-DryRun]
    intake -Backend ... (see Invoke-IntakeBackend)

  Pipeline:
    file -> hex -> sidecar -> clonepool -> custody -> D1

  Sector 4 vault intake:
    usys intake <file>

  Environment:
    PHOENIX_INTAKE, PHOENIX_AUTH, PHOENIX_WORKER_URL, CLONEPOOL_DIR

"@
}

# =============================================================================
# GLOBAL FUNCTION — primary interface when dot-sourced
# =============================================================================
function global:intake {
    [CmdletBinding(DefaultParameterSetName = 'File')]
    param(
        [Parameter(ParameterSetName = 'File', Mandatory, Position = 0)]
        [string]$Path,

        [Parameter(ParameterSetName = 'Backend', Mandatory)]
        [switch]$BackendMode,

        [Parameter(ParameterSetName = 'Backend', Mandatory, Position = 0)]
        [string]$PackageName,

        [Parameter(ParameterSetName = 'Backend', Mandatory, Position = 1)]
        [string]$Backend,

        [Parameter(ParameterSetName = 'Backend', Mandatory, Position = 2)]
        [string]$Version,

        [Parameter(ParameterSetName = 'Backend', Position = 3)]
        [string]$InstallPath,

        [Parameter(ParameterSetName = 'Status')]
        [switch]$Status,

        [Parameter(ParameterSetName = 'Clone', Mandatory)]
        [switch]$CloneMode,

        [Parameter(ParameterSetName = 'Clone', Mandatory, Position = 0)]
        [string]$CloneName,

        [Parameter(ParameterSetName = 'Help')]
        [switch]$Help,

        [string]$Notes = '',
        [switch]$DryRun
    )

    if ($Help) { Show-IntakeHelp; return }

    if ($Status) {
        Invoke-IntakeStatus -DryRun:$DryRun
        return
    }

    if ($CloneMode) {
        Invoke-IntakeClone -Name $CloneName -DryRun:$DryRun
        return
    }

    if ($BackendMode) {
        Invoke-IntakeBackend -PackageName $PackageName -Backend $Backend `
            -Version $Version -InstallPath $InstallPath -DryRun:$DryRun
        return
    }

    if (-not $Path) {
        Show-IntakeHelp
        return
    }

    switch ($Path.ToLowerInvariant()) {
        'help'   { Show-IntakeHelp; return }
        'status' { Invoke-IntakeStatus -DryRun:$DryRun; return }
        'backend' {
            Write-IntakeErr 'usage: intake backend <pkg> <backend> <version> [path]'
            return
        }
        'clone' {
            Write-IntakeErr 'usage: intake -CloneMode -CloneName <file>  (shim: intake.ps1 clone <file>)'
            return
        }
    }

    Invoke-IntakeFile -Path $Path -Notes $Notes -DryRun:$DryRun
}

Set-Alias -Name phx-intake -Value intake -Scope Global -Force -ErrorAction SilentlyContinue

# =============================================================================
# SHIM ENTRY — pwsh -File intake.ps1 <args>
# =============================================================================
if ($MyInvocation.InvocationName -ne '.' -and $MyInvocation.Line -notmatch '^\s*\.\s') {
    # Use bound parameters when available (pwsh -File intake.ps1 -Path x -DryRun)
    if ($PSBoundParameters.Count -gt 0) {
        intake @PSBoundParameters
        exit $LASTEXITCODE
    }

    $rawArgs = @($args)
    if ($rawArgs.Count -eq 0) {
        Show-IntakeHelp
        exit 0
    }

    $dry     = $rawArgs -contains '-DryRun' -or $rawArgs -contains '--dry-run'
    $filtered = [System.Collections.Generic.List[string]]::new()
    foreach ($a in $rawArgs) {
        if ($a -notin '-DryRun', '--dry-run') { $filtered.Add($a) }
    }

    if ($filtered.Count -eq 0) {
        Show-IntakeHelp
        exit 0
    }

    $cmd = $filtered[0]
    if ($cmd -in 'help', '--help', '-h') {
        Show-IntakeHelp
        exit 0
    }

    switch ($cmd.ToLowerInvariant()) {
        'status' {
            $code = Invoke-IntakeStatus -DryRun:$dry
            exit $(if ($null -eq $code) { 0 } else { $code })
        }
        'backend' {
            if ($filtered.Count -lt 4) {
                Write-IntakeErr 'usage: intake.ps1 backend <pkg> <backend> <version> [path]'
                exit 1
            }
            $code = Invoke-IntakeBackend -PackageName $filtered[1] -Backend $filtered[2] `
                -Version $filtered[3] -InstallPath $(if ($filtered.Count -ge 5) { $filtered[4] } else { '' }) `
                -DryRun:$dry
            exit $(if ($null -eq $code) { 0 } else { $code })
        }
        'clone' {
            if ($filtered.Count -lt 2) {
                Write-IntakeErr 'usage: intake.ps1 clone <filename>'
                exit 1
            }
            # Same backslash-split defense as the default branch below: if a
            # full path got passed instead of a bare filename and pwsh split
            # the drive letter off into its own arg, rejoin before stripping
            # to basename in Invoke-IntakeClone.
            $cloneName = $filtered[1]
            if ($cloneName -match '^[A-Za-z]:$' -and $filtered.Count -ge 3) {
                $cloneName = "$cloneName\$($filtered[2])"
            }
            $code = Invoke-IntakeClone -Name $cloneName -DryRun:$dry
            exit $(if ($null -eq $code) { 0 } else { $code })
        }
        default {
            # Rejoin path segments when pwsh splits on backslashes (e.g. C: + \foo\bar)
            $path = $cmd
            $extraStart = 1
            if ($path -match '^[A-Za-z]:$' -and $filtered.Count -ge 2) {
                $path = "$path\$($filtered[1])"
                $extraStart = 2
            }
            $backend = if ($filtered.Count -gt $extraStart) { $filtered[$extraStart] } else { 'direct' }
            $notes   = if ($filtered.Count -gt ($extraStart + 1)) { $filtered[$extraStart + 1] } else { '' }
            $code = Invoke-IntakeFile -Path $path -Backend $backend -Notes $notes -DryRun:$dry
            exit $(if ($null -eq $code) { 0 } else { $code })
        }
    }
}