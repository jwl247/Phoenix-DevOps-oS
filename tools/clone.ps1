#Requires -Version 7.0
# ============================================================
# Phoenix Global Clone -- clone.ps1
# USys -- United Systems | jwl247
# Place in: Phoenix-DevOps-oS/tools/clone.ps1
# Activate: Add '. "$HOME\Phoenix\Phoenix-DevOps-oS\tools\clone.ps1"' to $PROFILE
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

    # -- Find intake.sh
    $intakeCandidates = @(
        $env:PHOENIX_INTAKE,
        (Join-Path (Split-Path $PSScriptRoot -Parent) "Phoenix-Package_handler\intake\intake.sh"),
        (Join-Path $HOME "Phoenix\Phoenix-Package_handler\intake\intake.sh"),
        (Join-Path $PSScriptRoot "..\Phoenix-Package_handler\intake\intake.sh")
    ) | Where-Object { $_ -and (Test-Path $_) }

    if (-not $intakeCandidates) {
        Write-Error "clone: intake.sh not found. Set PHOENIX_INTAKE or clone Phoenix-Package_handler next to Phoenix-DevOps-oS."
        return
    }
    $intakeSh = $intakeCandidates[0]

    # -- Find bash
    $bash = (Get-Command bash -ErrorAction SilentlyContinue)?.Source
    if (-not $bash) {
        $bash = @(
            "C:\Program Files\Git\bin\bash.exe",
            "C:\Program Files (x86)\Git\bin\bash.exe"
        ) | Where-Object { Test-Path $_ } | Select-Object -First 1
    }
    if (-not $bash) {
        Write-Error "clone: bash not found. Install Git for Windows or enable WSL."
        return
    }

    # -- Env warnings
    if (-not $env:PHOENIX_AUTH)       { Write-Warning "clone: PHOENIX_AUTH not set -- D1 sync will be skipped" }
    if (-not $env:PHOENIX_WORKER_URL) { Write-Warning "clone: PHOENIX_WORKER_URL not set -- D1 sync will be skipped" }
    if (-not $env:CLONEPOOL_DIR)      { $env:CLONEPOOL_DIR = Join-Path $HOME "Phoenix\clonepool" }

    # -- Convert Windows path to bash path
    function ConvertTo-BashPath([string]$p) {
        $p = $p -replace '\\', '/'
        if ($p -match '^([A-Za-z]):(.*)') {
            return "/mnt/$($Matches[1].ToLower())$($Matches[2])"
        }
        return $p
    }

    $bashFile   = ConvertTo-BashPath $fullPath
    $bashIntake = ConvertTo-BashPath $intakeSh

    # -- Build args
    $intakeArgs = @($bashFile)
    if ($Category) { $intakeArgs += $Category }
    if ($Tag)      { $intakeArgs += "`"$Tag`"" }

    # -- Dry run
    if ($DryRun) {
        Write-Host ""
        Write-Host "  [DRY RUN] Phoenix Clone" -ForegroundColor Cyan
        Write-Host "  File      : $fullPath"           -ForegroundColor White
        Write-Host "  Intake    : $intakeSh"           -ForegroundColor White
        Write-Host "  Bash      : $bash"               -ForegroundColor White
        Write-Host "  Category  : $(if($Category){$Category}else{'(none)'})" -ForegroundColor White
        Write-Host "  Tag       : $(if($Tag){$Tag}else{'(none)'})"        -ForegroundColor White
        Write-Host "  Dest      : $(if($Destination){$Destination}else{'(none)'})" -ForegroundColor White
        Write-Host "  Clonepool : $env:CLONEPOOL_DIR"  -ForegroundColor White
        Write-Host ""
        return
    }

    # -- Execute
    Write-Host ""
    Write-Host "  Phoenix Clone -> $Path" -ForegroundColor Cyan

    $env:PHOENIX_DESTINATION = $Destination

    & $bash $bashIntake @intakeArgs

    if ($LASTEXITCODE -eq 0) {
        Write-Host "  Cloned OK" -ForegroundColor Green
    } else {
        Write-Error "clone: intake.sh exited $LASTEXITCODE"
    }
    Write-Host ""
}

Set-Alias -Name phx-clone -Value clone -Scope Global -Force
