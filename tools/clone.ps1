#Requires -Version 7.0
# ============================================================
# Phoenix Global Clone -- clone.ps1
# USys -- United Systems | jwl247
# Place in: Phoenix-DevOps-oS/tools/clone.ps1
# Activate: Add '. "$HOME\Phoenix\Phoenix-DevOps-oS\tools\clone.ps1"' to $PROFILE
#
# Platform: Windows 10/11 with Git Bash (no WSL required)
# Git Bash path style: /c/Users/... (NOT /mnt/c/)
# ============================================================

function global:clone {
    <#
    .SYNOPSIS
        Phoenix global clone. Clones any file into the Phoenix clonepool
        via the Sector 2 intake pipeline. Available from any directory in PS7.
    .EXAMPLE
        clone ./franken.py
        clone ./nginx.conf -Tag "production config" -Category configs
        clone ./franken.py -Destination T2
        clone ./myfile.sh -DryRun
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory, Position = 0)]
        [string]$Path,
        [string]$Tag         = "",
        [string]$Category    = "",
        [string]$Destination = "",
        [switch]$DryRun
    )

    # -- Resolve path
    $resolved = Resolve-Path -Path $Path -ErrorAction SilentlyContinue
    if (-not $resolved) {
        Write-Error "clone: path not found -- '$Path'"
        return
    }
    $fullPath = $resolved.Path

    # -- Find Git Bash
    $bashCandidates = @(
        $env:PHOENIX_BASH,
        "C:\Program Files\Git\bin\bash.exe",
        "C:\Program Files (x86)\Git\bin\bash.exe",
        "$env:ProgramFiles\Git\bin\bash.exe",
        "$env:LOCALAPPDATA\Programs\Git\bin\bash.exe"
    ) | Where-Object { $_ -and (Test-Path $_) }

    $bash = $bashCandidates | Select-Object -First 1

    if (-not $bash) {
        $found = Get-Command bash -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -First 1
        if ($found -and $found -notmatch 'wsl') { $bash = $found }
    }

    if (-not $bash) {
        Write-Error "clone: Git Bash not found. Install Git for Windows or set PHOENIX_BASH."
        return
    }

    # -- Find intake.sh
    $intakeCandidates = @(
        $env:PHOENIX_INTAKE,
        (Join-Path (Split-Path $PSScriptRoot -Parent) "sector2\package-handler\intake.sh")
    ) | Where-Object { $_ -and (Test-Path $_) }
    # (standalone Phoenix-Package_handler candidates removed — archived
    #  2026-09-13, intake.sh lives at that repo's root; S34OPS-F41)

    if (-not $intakeCandidates) {
        Write-Error "clone: intake.sh not found. Set PHOENIX_INTAKE or run from a Phoenix-DevOps-oS checkout (sector2\package-handler\intake.sh)."
        return
    }
    # @() — a single surviving candidate is a scalar string, and [0] on a
    # string is its first character ("F"), not the path.
    $intakeSh = @($intakeCandidates)[0]

    # -- Env warnings
    if (-not $env:PHOENIX_AUTH)       { Write-Warning "clone: PHOENIX_AUTH not set -- D1 sync will be skipped" }
    if (-not $env:PHOENIX_WORKER_URL) { Write-Warning "clone: PHOENIX_WORKER_URL not set -- D1 sync will be skipped" }
    if (-not $env:CLONEPOOL_DIR)      { $env:CLONEPOOL_DIR = Join-Path $HOME "Phoenix\clonepool" }

    # -- Convert Windows path to Git Bash path
    # Uses [char]92 (backslash) to avoid any editor/encoding issues
    # Git Bash: C:Usersoo -> /c/Users/foo
    function ConvertTo-GitBashPath([string]$p) {
        $bsChar = [char]92
        $p = $p.Replace($bsChar, [char]47)
        if ($p -match '^([A-Za-z]):(.*)') {
            return "/$($Matches[1].ToLower())$($Matches[2])"
        }
        return $p
    }

    $bashFile   = ConvertTo-GitBashPath $fullPath
    $bashIntake = ConvertTo-GitBashPath $intakeSh

    # -- Build args
    $intakeArgs = @($bashFile)
    if ($Category) { $intakeArgs += $Category }
    # Passed verbatim: PowerShell quotes array elements for the native call;
    # wrapping in literal quotes stored them in the tag (fixed in usys.ps1 as F09).
    if ($Tag)      { $intakeArgs += $Tag }

    # -- Dry run
    if ($DryRun) {
        Write-Host ""
        Write-Host "  [DRY RUN] Phoenix Clone" -ForegroundColor Cyan
        Write-Host "  File      : $fullPath"           -ForegroundColor White
        Write-Host "  Bash      : $bash"               -ForegroundColor White
        Write-Host "  Intake    : $intakeSh"           -ForegroundColor White
        Write-Host "  Bash file : $bashFile"           -ForegroundColor White
        Write-Host "  Bash intk : $bashIntake"         -ForegroundColor White
        Write-Host "  Category  : $(if($Category){$Category}else{'(none)'})" -ForegroundColor White
        Write-Host "  Tag       : $(if($Tag){$Tag}else{'(none)'})"           -ForegroundColor White
        Write-Host "  Dest      : $(if($Destination){$Destination}else{'(none)'})" -ForegroundColor White
        Write-Host "  Clonepool : $env:CLONEPOOL_DIR"  -ForegroundColor White
        Write-Host ""
        return
    }

    # -- Execute
    Write-Host ""
    Write-Host "  Phoenix Clone -> $Path" -ForegroundColor Cyan

    $env:PHOENIX_DESTINATION = $Destination

    # -- Convert CLONEPOOL_DIR to bash path so JSON sidecar has no Windows backslashes
    #    (restored afterwards — it used to stay rewritten for the whole session)
    $savedPool = $env:CLONEPOOL_DIR
    try {
        $env:CLONEPOOL_DIR = ConvertTo-GitBashPath $env:CLONEPOOL_DIR
        & $bash $bashIntake @intakeArgs
    } finally {
        $env:CLONEPOOL_DIR = $savedPool
    }

    if ($LASTEXITCODE -eq 0) {
        Write-Host "  Cloned OK" -ForegroundColor Green
    } else {
        Write-Error "clone: intake.sh exited $LASTEXITCODE"
    }
    Write-Host ""
}

Set-Alias -Name phx-clone -Value clone -Scope Global -Force
