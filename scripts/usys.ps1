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

# Shared FS — F: drive canonical root and directory names.
# All phx- wrappers and virtio-9p argument builder reference these; change
# the drive letter here and every sub-system updates automatically.
$script:PhxSharedRoot   = 'F:\Phoenix'
$script:PhxSharedDirs   = @('Desktop', 'Documents', 'Downloads', 'Projects', 'Vault')

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

function Get-UsysWorkerHeaders {
    # Every packages-worker route now sits behind Cloudflare Access (Gap 1
    # fix, 2026-09-21) — a leftover "bypass, everyone" policy was removed, so
    # non-interactive callers need the usys-cli service token on top of
    # PHOENIX_AUTH or they get bounced to the Access HTML login page instead
    # of JSON (silently "not found"/empty-looking responses, not a clean
    # 401). intake.sh already sends both; this is the same pair for every
    # direct PS7 call to the worker. Falls back to User-scope env if the
    # current process env is unset — same pattern as PHOENIX_AUTH.
    [CmdletBinding()]
    param([switch]$Accept)

    $auth = $env:PHOENIX_AUTH
    if (-not $auth) { $auth = [Environment]::GetEnvironmentVariable('PHOENIX_AUTH', 'User') }
    $cfId = $env:CF_ACCESS_CLIENT_ID
    if (-not $cfId) { $cfId = [Environment]::GetEnvironmentVariable('CF_ACCESS_CLIENT_ID', 'User') }
    $cfSecret = $env:CF_ACCESS_CLIENT_SECRET
    if (-not $cfSecret) { $cfSecret = [Environment]::GetEnvironmentVariable('CF_ACCESS_CLIENT_SECRET', 'User') }

    $headers = @{}
    if ($Accept)    { $headers['Accept'] = 'application/json' }
    if ($auth)      { $headers['Authorization'] = "Bearer $auth" }
    if ($cfId)      { $headers['CF-Access-Client-Id'] = $cfId }
    if ($cfSecret)  { $headers['CF-Access-Client-Secret'] = $cfSecret }
    return $headers
}

function ConvertTo-QemuHostPath([string]$WindowsPath) {
    # C:\Users\jerry\Phoenix -> C:/Users/jerry/Phoenix
    # F:\Phoenix\Desktop     -> F:/Phoenix/Desktop
    # Drive letter and colon preserved — QEMU on Windows accepts this form for -virtfs path=
    return $WindowsPath.Replace([char]92, [char]47)
}

function Write-PhxFsBanner {
    # Two-line contract statement — appears at setup, run --share, and phx-ls.
    # No color prose, no ASCII art. States the deal.
    Write-Host "  Phoenix FS  Windows reliable  Debian fast  QEMU bridges" -ForegroundColor Cyan
    Write-Host "  $($script:PhxSharedDirs -join '  ')" -ForegroundColor White
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
    # Canonical in-repo pipeline first: the standalone Phoenix-Package_handler
    # clones lack the CF-Access headers (2026-09-21) and would fail silently.
    $candidates = @(
        $env:PHOENIX_INTAKE,
        (Join-Path $repo 'sector2\package-handler\intake.sh')
        # standalone Phoenix-Package_handler candidates removed (archived
        # 2026-09-13; intake.sh lives at that repo's root) — S34OPS-F41
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
        # This binary runs on the HOST for every qemu-runtime suite, which the
        # execution gate passes as "VM-contained" -- so a clonepool-supplied
        # QEMU is only used when that suite is trust-stamped (usys suite-trust
        # qemu-system). Otherwise fall through to the system install.
        if (Test-Path $candidate) {
            if ((Test-UsysSuiteTrusted -Suite $suites[0]).Trusted) { return $candidate }
            Write-UsysWarn "clonepool qemu-system is not trust-stamped -- ignoring it (run: usys suite-trust qemu-system)"
        }
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
    $legacyEngine = Get-UsysBashUsys
    Write-Host "    usys.sh        : $(if ($legacyEngine) { $legacyEngine } else { 'not shipped (legacy registry verbs disabled)' })"
    Write-Host ''

    Write-Host '  -- Environment --' -ForegroundColor Yellow
    foreach ($var in @('PHOENIX_AUTH', 'PHOENIX_WORKER_URL', 'CLONEPOOL_DIR', 'PHOENIX_INTAKE', 'PHOENIX_ROOT')) {
        $val = [Environment]::GetEnvironmentVariable($var, 'User')
        if (-not $val) { $val = [Environment]::GetEnvironmentVariable($var, 'Process') }
        # Secrets: say whether they're set, never print them (2026-10-07 audit S21/XCUT-S17/CMDWALK-S01)
        if ($val -and $var -eq 'PHOENIX_AUTH') { $val = "set ($($val.Length) chars, hidden)" }
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
# COMMAND: doctor — health/conflict report. Reports only. Fixes nothing.
#
# Checks live state against the facts recorded in CONNECTIONS.md (git drift
# across the repos under Phoenix\, the 3-way package-handler split, deployed
# worker reachability, and a small set of previously-documented known issues)
# so a session doesn't have to re-derive any of it by hand. If a documented
# bug turns out to be gone, that's ALSO reported — it means CONNECTIONS.md
# has drifted from reality and needs a real update, not silent removal.
# =============================================================================
function Test-UsysWorkerHealth([string]$Name, [string]$Url, [switch]$Authed) {
    try {
        $headers = if ($Authed) { Get-UsysWorkerHeaders } else { @{} }
        $resp = Invoke-WebRequest -Uri $Url -Headers $headers -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
        return @{ Name = $Name; Ok = $true; Detail = "$($resp.StatusCode)" }
    } catch {
        return @{ Name = $Name; Ok = $false; Detail = $_.Exception.Message }
    }
}

function Get-UsysRepoGitInfo([string]$Path) {
    if (-not (Test-Path (Join-Path $Path '.git'))) { return $null }
    Push-Location $Path
    try {
        $branch = git rev-parse --abbrev-ref HEAD 2>$null
        $head   = git rev-parse --short HEAD 2>$null
        $dirty  = (git status --porcelain 2>$null)
        $ahead  = git rev-list --count '@{u}..HEAD' 2>$null
        $behind = git rev-list --count 'HEAD..@{u}' 2>$null
        return @{
            Branch = $branch; Head = $head
            Dirty  = [bool]$dirty; DirtyN = ($dirty | Measure-Object).Count
            Ahead  = [int]($ahead  | Select-Object -First 1)
            Behind = [int]($behind | Select-Object -First 1)
        }
    } finally { Pop-Location }
}

function Invoke-UsysDoctor {
    Write-Host ''
    Write-Host '  === Phoenix Doctor ===' -ForegroundColor Cyan
    Write-Host '  Reports problems/conflicts. Fixes nothing automatically.' -ForegroundColor DarkGray
    Write-Host ''

    $problems = @()
    $repo = Get-UsysRepoRoot
    $phoenixRoot = Split-Path $repo -Parent

    Write-Host '  -- Git state (every active repo under Phoenix\) --' -ForegroundColor Yellow
    # Phoenix-Package_handler and package-handler were archived 2026-09-13 to
    # archive/package-handler-consolidation-20260913/ after being confirmed to
    # have zero unique value vs. this repo's own sector2/package-handler/ —
    # see that folder's README.md. Not checked here anymore; if either ever
    # gets revived, add it back.
    foreach ($r in @('Phoenix-DevOps-oS', 'Helix_lightning_kernel')) {
        $info = Get-UsysRepoGitInfo (Join-Path $phoenixRoot $r)
        if (-not $info) { Write-Host "    $r : not a git repo (skipped)" -ForegroundColor DarkGray; continue }
        $flags = @()
        if ($info.Dirty)        { $flags += "$($info.DirtyN) uncommitted" }
        if ($info.Ahead -gt 0)  { $flags += "$($info.Ahead) ahead" }
        if ($info.Behind -gt 0) { $flags += "$($info.Behind) behind" }
        if ($flags.Count -eq 0) {
            Write-Host "    $r : clean, in sync ($($info.Head))" -ForegroundColor Green
        } else {
            $msg = "$r : $($flags -join ', ') ($($info.Head))"
            Write-Host "    $msg" -ForegroundColor Yellow
            $problems += $msg
        }
    }
    Write-Host ''

    Write-Host '  -- Deployed worker health --' -ForegroundColor Yellow
    foreach ($w in @(
        @{ Name = 'packages-worker';      Url = 'https://packages-worker.phoenix-jwl.workers.dev/health'; Authed = $false }
        @{ Name = 'office-notify-worker'; Url = 'https://office-notify-worker.phoenix-jwl.workers.dev/health'; Authed = $false }
        @{ Name = 'phoenix-office-worker'; Url = 'https://phoenix-office-worker.phoenix-jwl.workers.dev/health'; Authed = $false }
        @{ Name = 'pbm-leads-worker';     Url = 'https://pbm-leads-worker.phoenix-jwl.workers.dev/health'; Authed = $false }
    )) {
        $result = Test-UsysWorkerHealth -Name $w.Name -Url $w.Url -Authed:$w.Authed
        if ($result.Ok) {
            Write-Host "    $($w.Name) : reachable (HTTP $($result.Detail))" -ForegroundColor Green
        } else {
            $msg = "$($w.Name) unreachable: $($result.Detail)"
            Write-Host "    $msg" -ForegroundColor Red
            $problems += $msg
        }
    }
    Write-Host ''

    Write-Host '  -- Known issues (checking for regression OR for stale docs) --' -ForegroundColor Yellow
    $s4intake = Join-Path $repo 'sector4\intake\intake.sh'
    if (Test-Path $s4intake) {
        # Code lines only: the 2026-09-21 fix left the old glob text inside
        # an explanatory comment, which made a raw-file grep report the bug
        # as still present (S34OPS-F26 / CONN-F07).
        $s4code = Get-Content $s4intake | Where-Object { $_ -notmatch '^\s*#' }
        if ($s4code -match '\*\(\.\)') {
            $msg = 'sector4/intake/intake.sh : zsh-only **/*(.) glob is back in code (regression of the 2026-09-21 find-based fix)'
            Write-Host "    $msg" -ForegroundColor Red
            $problems += $msg
        } else {
            Write-Host '    sector4/intake/intake.sh : zsh-glob bug fixed (find -print0; 2026-09-21)' -ForegroundColor Green
        }
    }
    $dashMain = Join-Path $repo 'dashboard\main.js'
    if (Test-Path $dashMain) {
        # -CaseSensitive: Select-String ignores case by default, so the fixed
        # lowercase 'sector4' used to match too and this reported the bug forever.
        if (Select-String -Path $dashMain -Pattern "'SECTOR4'" -CaseSensitive -Quiet) {
            $msg = "dashboard/main.js : 'SECTOR4' uppercase is back (regression of the 2026-09-29 casing fix; the directory is sector4/)"
            Write-Host "    $msg" -ForegroundColor Red
            $problems += $msg
        } else {
            Write-Host '    dashboard/main.js : SECTOR4/sector4 casing bug fixed (2026-09-29)' -ForegroundColor Green
        }
    }
    $cloneDir = Get-UsysClonepoolDir
    if (-not (Test-Path $cloneDir)) {
        $msg = "CLONEPOOL_DIR resolves to '$cloneDir' which does not exist"
        Write-Host "    $msg" -ForegroundColor Red
        $problems += $msg
    } else {
        Write-Host "    CLONEPOOL_DIR ($cloneDir) : exists" -ForegroundColor Green
    }
    Write-Host ''

    if ($problems.Count -eq 0) {
        Write-UsysOk 'No problems found.'
    } else {
        Write-UsysWarn "$($problems.Count) problem(s) found — see above. Nothing was changed."
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
# Invoke-UsysClone — internal IN helper: puts a file INTO the pool (used by intake/shared-fs/watch).
# NOT the `clone` command: `usys clone` / `clone` are OUT (Invoke-UsysCloneOut → bin/clone).
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
    if (-not $intake) { Write-UsysErr 'clone intake.sh not found (expected sector2\package-handler\intake.sh in this repo) — or set PHOENIX_INTAKE.'; return }

    if (-not $env:PHOENIX_AUTH)       { Write-UsysWarn 'PHOENIX_AUTH not set — D1 sync skipped' }
    if (-not $env:PHOENIX_WORKER_URL) { Write-UsysWarn 'PHOENIX_WORKER_URL not set — D1 sync skipped' }
    if (-not $env:CLONEPOOL_DIR)      { $env:CLONEPOOL_DIR = Get-UsysClonepoolDir }

    $bashFile   = ConvertTo-GitBashPath $fullPath
    $bashIntake = ConvertTo-GitBashPath $intake
    $intakeArgs = @($bashFile)
    if ($Category) { $intakeArgs += $Category }
    if ($Tag)      { $intakeArgs += $Tag }  # PS 7.3+ passes args verbatim; embedded quotes became part of the tag

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
    # Git-Bash form only for the child; restore afterwards so later PowerShell
    # calls in this session (search, list-suites, watcher) still see a real path.
    $prevPool = $env:CLONEPOOL_DIR
    $env:CLONEPOOL_DIR       = ConvertTo-GitBashPath $env:CLONEPOOL_DIR

    try { & $bash $bashIntake @intakeArgs } finally { $env:CLONEPOOL_DIR = $prevPool }
    if ($LASTEXITCODE -eq 0) { Write-UsysOk 'cloned OK' } else { Write-UsysErr "clone exited $LASTEXITCODE" }
    Write-Host ''
}

# =============================================================================
# Invoke-UsysIntakeFile — shared single-file intake via the CANONICAL pipeline
# (sector2/package-handler/intake.sh: real R2 upload, integrity baseline, QR,
# sensitive-file flagging). Extracted from Invoke-UsysClone's own logic so
# every caller that just needs "get this one file into the pool" — distro
# intake-qemu, usys download, the watch-downloads prompt path — goes through
# the same real pipeline instead of the deprecated phoenix-core/tools/
# intake.py stub (no R2, no integrity baseline, and as of the 2026-09-21
# Cloudflare Access change, its D1 sync silently reports fake success — see
# audit doc T2 #7). Non-interactive: no prompts, just OK/fail. The background
# watcher job (Start-UsysWatcher) can't call this directly — Start-Job runs
# in a separate process with no access to functions defined here — so it
# resolves the same bash/intake.sh paths itself and shells out the same way;
# keep that call site's logic in sync with this one if either changes.
# =============================================================================
function Invoke-UsysIntakeFile {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory, Position = 0)]
        [string]$Path
    )

    $resolved = Resolve-Path -Path $Path -ErrorAction SilentlyContinue
    if (-not $resolved) {
        Write-UsysErr "path not found — '$Path'"
        return $false
    }
    $fullPath = $resolved.Path

    $bash   = Get-UsysGitBash
    $intake = Get-UsysCloneIntakeSh

    if (-not $bash)   { Write-UsysErr 'Git Bash not found. Install Git for Windows or set PHOENIX_BASH.'; return $false }
    if (-not $intake) { Write-UsysErr 'intake.sh not found. Set PHOENIX_INTAKE or check sector2/package-handler.'; return $false }

    if (-not $env:PHOENIX_AUTH)       { Write-UsysWarn 'PHOENIX_AUTH not set — D1 sync skipped' }
    if (-not $env:PHOENIX_WORKER_URL) { Write-UsysWarn 'PHOENIX_WORKER_URL not set — D1 sync skipped' }
    if (-not $env:CLONEPOOL_DIR)      { $env:CLONEPOOL_DIR = Get-UsysClonepoolDir }

    $bashFile   = ConvertTo-GitBashPath $fullPath
    $bashIntake = ConvertTo-GitBashPath $intake
    $prevPool = $env:CLONEPOOL_DIR
    $env:CLONEPOOL_DIR = ConvertTo-GitBashPath $env:CLONEPOOL_DIR

    try { & $bash $bashIntake $bashFile } finally { $env:CLONEPOOL_DIR = $prevPool }
    if ($LASTEXITCODE -eq 0) { return $true }
    Write-UsysErr "intake exited $LASTEXITCODE for '$Path'"
    return $false
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
        $q = $Query.Replace("'", "''")
        $rows = & sqlite3 $db "SELECT name, hex_id FROM packages WHERE name LIKE '%$q%' LIMIT $Limit;" 2>$null
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

    # .lol is an alias, not a rename: the SAME extension means two different
    # things depending on whether the file already exists locally. Existing
    # local file -> unchanged behavior (intake to vault, below). No local
    # file, but its base name (stripped of .lol) is a known pool entry ->
    # clone-to-working-directory instead. Too far along to rename the vault
    # convention that's already live; this just teaches it a second trick.
    if ([System.IO.Path]::GetExtension($Path).ToLowerInvariant() -eq '.lol' -and -not (Test-Path $Path)) {
        $baseName = [System.IO.Path]::GetFileNameWithoutExtension($Path)
        Write-Host ''
        Write-UsysInfo "'$Path' doesn't exist locally — checking the pool for '$baseName'"
        if ($DryRun) {
            Write-Host "  [DRY RUN] would clone-to-workdir '$baseName' from the pool" -ForegroundColor Cyan
            return
        }
        Invoke-UsysPull -SuiteName $baseName -Destination (Get-Location).Path
        return
    }

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
        # Honest answer (S34OPS-F32): nothing in this repo ships usys.sh and
        # `usys init` does not create it, so these verbs are not implemented
        # here. They only work if an external legacy engine is pointed at by
        # USYS_ENGINE (or dropped at ~/.usys/usys.sh).
        Write-UsysErr "usys $SubCommand : not implemented in this repo — the legacy unitedsys registry engine (usys.sh) is not shipped, and 'usys init' does not install it."
        Write-UsysInfo 'Set USYS_ENGINE to an existing usys.sh to use: register, call, swap, rollback, list, info, remove, where, sync'
        Write-UsysInfo "For the clone pool use: usys search / usys list-suites / usys clone / usys pull"
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
# SHA3-512 of a file as lowercase hex (the hash intake.sh records as D1
# hash_sha3). .NET 8+ SHA3 when the OS supports it, else python3 hashlib.
# Returns '' if neither is available — callers must treat that as "cannot verify".
function Get-UsysSha3Hex {
    param([Parameter(Mandatory)][string]$Path)
    try {
        $t = [Type]::GetType('System.Security.Cryptography.SHA3_512')
        if ($t -and [System.Security.Cryptography.SHA3_512]::IsSupported) {
            $bytes = [System.IO.File]::ReadAllBytes($Path)
            return ([Convert]::ToHexString([System.Security.Cryptography.SHA3_512]::HashData($bytes))).ToLowerInvariant()
        }
    } catch { }
    $py = if (Get-Command python3 -EA SilentlyContinue) { 'python3' }
          elseif (Get-Command python -EA SilentlyContinue) { 'python' }
          else { $null }
    if (-not $py) { return '' }
    try {
        $out = & $py -c 'import hashlib,sys; print(hashlib.sha3_512(open(sys.argv[1],"rb").read()).hexdigest())' $Path 2>$null
        if ($LASTEXITCODE -eq 0 -and $out -match '^[0-9a-f]{128}$') { return [string]$out }
    } catch { }
    return ''
}

function Invoke-UsysPull {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory, Position = 0)]
        [string]$SuiteName,
        # Where to write the real bytes once fetched from R2. Default (unset)
        # keeps the original stub-manifest-only behavior for suite staging.
        # Pass a folder to actually pull the file down into it — this is what
        # the .lol clone-to-workdir alias uses.
        [string]$Destination = '',
        [switch]$DryRun
    )

    $workerUrl  = $env:PHOENIX_WORKER_URL

    if (-not $workerUrl) {
        Write-UsysErr 'PHOENIX_WORKER_URL not set — cannot pull from D1'
        return
    }

    Write-Host ''
    Write-UsysInfo "Pulling suite from D1: $SuiteName"

    # Ask D1 for the record
    try {
        $uri = "$($workerUrl.TrimEnd('/'))/clonepool/$([Uri]::EscapeDataString($SuiteName))"
        $headers = Get-UsysWorkerHeaders -Accept
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

    # -Destination given: this is a real pull-to-workdir request (the .lol
    # clone-to-workdir alias), not suite staging. Fetch the actual bytes.
    # phoenix-clonepool-r2 was retired 2026-09-21 (see CLAUDE.md SESSION LOG)
    # in favor of packages-worker's own integrated R2 binding — same
    # GET /clonepool/:id route as the metadata lookup above, just keyed by
    # hex_id instead of name so it hits the R2 object directly.
    if ($Destination) {
        if (-not $resp.hex_id) {
            Write-UsysErr "'$SuiteName' has no hex_id in D1 — can't fetch content."
            return
        }
        $objUri = "$($workerUrl.TrimEnd('/'))/clonepool/$([Uri]::EscapeDataString($resp.hex_id))"
        $headers = Get-UsysWorkerHeaders

        New-Item -ItemType Directory -Path $Destination -Force | Out-Null
        # resp.name comes from D1 -- strip any directory parts so a crafted
        # record can't write outside the destination folder.
        $safeName = [System.IO.Path]::GetFileName([string]$resp.name)
        if (-not $safeName -or $safeName -in '.', '..') { Write-UsysErr "invalid name in D1 record: '$($resp.name)'"; return }
        $outFile = Join-Path $Destination $safeName
        # Download to a side file first; it only becomes $outFile once its
        # SHA3-512 matches the D1 custody record (S34OPS-F24 — same
        # meta-then-verify pattern as portal/server.py pool_fetch).
        $partFile = "$outFile.phx-partial"

        try {
            Invoke-WebRequest -Uri $objUri -Headers $headers -Method GET -OutFile $partFile -ErrorAction Stop | Out-Null
        } catch {
            Remove-Item -LiteralPath $partFile -Force -ErrorAction SilentlyContinue
            $statusCode = $_.Exception.Response.StatusCode.value__
            if ($statusCode -eq 404) {
                Write-UsysErr "'$($resp.name)' is in D1 but not in R2 — it likely predates R2 upload being wired (2026-08-22), or was never uploaded. Nothing to pull down."
            } else {
                Write-UsysErr "R2 fetch failed: $_"
            }
            return
        }

        # Custody baseline: the D1 row by hex_id (?meta=true forces the row,
        # never the R2 bytes).
        $want = ''
        try {
            $metaUri = "$($workerUrl.TrimEnd('/'))/clonepool/$([Uri]::EscapeDataString($resp.hex_id))?meta=true"
            $meta = Invoke-RestMethod -Uri $metaUri -Headers (Get-UsysWorkerHeaders -Accept) -Method GET -ErrorAction Stop
            $row = if ($meta.result) { $meta.result } elseif ($meta.item) { $meta.item } else { $meta }
            $want = ([string]$row.hash_sha3).Trim().ToLowerInvariant()
        } catch {
            $want = ''
        }
        $got = Get-UsysSha3Hex -Path $partFile
        $verdict = if (-not $want) { 'refused-no-baseline' }
                   elseif (-not $got) { 'refused-no-sha3' }
                   elseif ($got -ne $want) { 'refused-mismatch' }
                   else { 'verified' }
        Write-UsysSuiteExecLog @{
            event   = 'pull'
            name    = $safeName
            hex_id  = [string]$resp.hex_id
            verdict = $verdict
            want    = if ($want) { $want.Substring(0, [Math]::Min(16, $want.Length)) } else { '' }
            got     = if ($got)  { $got.Substring(0, [Math]::Min(16, $got.Length)) } else { '' }
        }
        if ($verdict -ne 'verified') {
            Remove-Item -LiteralPath $partFile -Force -ErrorAction SilentlyContinue
            switch ($verdict) {
                'refused-no-baseline' { Write-UsysErr "'$safeName' has no SHA3 custody fingerprint in D1 — refusing unverified bytes. Re-intake it (usys clone) to record one." }
                'refused-no-sha3'     { Write-UsysErr "SHA3-512 unavailable on this machine (needs .NET SHA3 support or python3) — refusing unverified bytes." }
                default               { Write-UsysErr "'$safeName': R2 bytes don't match D1 custody ($($got.Substring(0,12)) vs $($want.Substring(0,12))) — refused, nothing written." }
            }
            return
        }
        Move-Item -LiteralPath $partFile -Destination $outFile -Force

        Write-UsysOk "Cloned to working directory (SHA3-512 verified against D1): $outFile"
        return
    }

    # If pool_path is a local path on the source machine it won't exist here —
    # that is expected on a second machine. We stage from what D1 knows.
    $safeSuite = [System.IO.Path]::GetFileName([string]$resp.name)
    if (-not $safeSuite -or $safeSuite -in '.', '..') { Write-UsysErr "invalid name in D1 record: '$($resp.name)'"; return }
    $suiteDir = Join-Path (Get-UsysClonepoolDir) $safeSuite
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

function ConvertTo-UsysSortVersion([string]$Version) {
    # Suite versions are semver ("11.1.0") or dates ("20261004"). [version] rejects a
    # bare number, so pad it; anything unparseable sorts lowest instead of erroring.
    $v = $Version -replace '^v', ''
    if ($v -match '^\d+$') { $v = "$v.0" }
    $parsed = $null
    if ([version]::TryParse($v, [ref]$parsed)) { return $parsed }
    return [version]'0.0'
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

# =============================================================================
# SUITE EXECUTION GATE — check before execution (security audit T1 #1 + #3)
#
# One mechanism, asked at the top of Invoke-UsysRun, before anything runs:
#
#   #3 provenance — is this suite locally trust-stamped?  `.phoenix-trust` in
#      the suite dir holds an HMAC-SHA256 over the entry file + core manifest
#      fields, keyed by THIS machine's PHOENIX_AUTH. `usys suite-trust <name>`
#      writes it (a future intake.sh will too). Change the entry file and the
#      stamp stops verifying.
#
#   #1 permission — what does the manifest `permissions` array ask for, and is
#      it granted? A trust-stamped suite is granted whatever it declares (you
#      vouched). An UNSTAMPED host-runtime suite that asks for network / broad
#      filesystem:write / process:spawn / env:write is REFUSED unless run with
#      -Unverified or a live "yes".
#
# qemu-runtime suites (debian/ubuntu/…) are already contained by the VM
# boundary — they pass the gate with a log line, not a challenge. The threat
# surface is host-executing runtimes (python/node/bash/powershell/binary).
#
# This is a consent + audit boundary, NOT a kernel sandbox — real write/network
# confinement is audit T1 #2 (Job Objects), still open. Every decision is
# appended to ~/.unitedsys/logs/suite_exec.jsonl. A refusal on an unstamped,
# elevated-ask suite also fires the CoPES Beta guardian (audit T1 #4's last
# wire). Global escape hatch: PHOENIX_SUITE_NO_GATE=1.
# =============================================================================

$script:UsysHostRuntimes = @('python', 'node', 'bash', 'powershell', 'binary')

function Get-UsysSuiteTrustKey {
    $k = $env:PHOENIX_AUTH
    if (-not $k) { $k = [Environment]::GetEnvironmentVariable('PHOENIX_AUTH', 'User') }
    return $k
}

function Get-UsysFileSha256([string]$Path) {
    if (-not (Test-Path $Path -PathType Leaf)) { return $null }
    return (Get-FileHash -Path $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Get-UsysSuiteStampValue {
    param([object]$Manifest, [string]$EntryPath)
    $key = Get-UsysSuiteTrustKey
    if (-not $key) { return $null }
    $entryHash = Get-UsysFileSha256 $EntryPath
    if (-not $entryHash) { return $null }
    # v2: the manifest `environment` block is covered too -- Invoke-UsysRun
    # applies it to the process before launch, so editing it after stamping
    # (e.g. NODE_OPTIONS / PYTHONSTARTUP / PATH) must invalidate the stamp.
    $envJson = if ($Manifest.environment) { $Manifest.environment | ConvertTo-Json -Compress -Depth 5 } else { '' }
    $msg = @(
        'phoenix-suite-trust-v2',
        [string]$Manifest.name,
        [string]$Manifest.version,
        [string]$Manifest.runtime,
        [string]$Manifest.entry,
        $entryHash,
        $envJson
    ) -join "`n"
    $hmac = [System.Security.Cryptography.HMACSHA256]::new([Text.Encoding]::UTF8.GetBytes($key))
    try {
        $bytes = $hmac.ComputeHash([Text.Encoding]::UTF8.GetBytes($msg))
    }
    finally { $hmac.Dispose() }
    return (-join ($bytes | ForEach-Object { $_.ToString('x2') }))
}

function Test-UsysSuiteTrusted {
    param([object]$Suite)
    $stampPath = Join-Path $Suite.Path '.phoenix-trust'
    if (-not (Test-Path $stampPath)) {
        return [pscustomobject]@{ Trusted = $false; Reason = 'not trust-stamped' }
    }
    try { $stamp = Get-Content $stampPath -Raw | ConvertFrom-Json }
    catch { return [pscustomobject]@{ Trusted = $false; Reason = '.phoenix-trust unreadable' } }

    $expected = Get-UsysSuiteStampValue -Manifest $Suite.Manifest -EntryPath (Join-Path $Suite.Path $Suite.Manifest.entry)
    if (-not $expected) {
        return [pscustomobject]@{ Trusted = $false; Reason = 'no PHOENIX_AUTH to verify the stamp against' }
    }
    if ($stamp.stamp -and $stamp.stamp -eq $expected) {
        return [pscustomobject]@{ Trusted = $true; Reason = 'stamp valid' }
    }
    return [pscustomobject]@{ Trusted = $false; Reason = 'stamp mismatch — entry file changed, or stamped on another machine' }
}

function Get-UsysSuitePermissionAsks {
    param([object]$Manifest)
    $perms = @()
    if ($Manifest.permissions) { $perms = @($Manifest.permissions | ForEach-Object { [string]$_ }) }
    $elevated = @()
    foreach ($p in $perms) {
        if ($p -eq 'network') { $elevated += 'network' }
        elseif ($p -eq 'filesystem:write') { $elevated += 'filesystem:write (unscoped)' }
        elseif ($p -eq 'process:spawn') { $elevated += 'process:spawn' }
        elseif ($p -eq 'env:write') { $elevated += 'env:write' }
    }
    return [pscustomobject]@{ Declared = $perms; Elevated = $elevated }
}

function Get-UsysSuiteExecLogPath {
    if ($env:PHOENIX_SUITE_EXEC_LOG) { return $env:PHOENIX_SUITE_EXEC_LOG }
    $home = $env:USERPROFILE
    if (-not $home) { $home = $HOME }
    return (Join-Path $home '.unitedsys\logs\suite_exec.jsonl')
}

function Write-UsysSuiteExecLog {
    param([hashtable]$Entry)
    try {
        $path = Get-UsysSuiteExecLogPath
        New-Item -ItemType Directory -Path (Split-Path $path) -Force -EA SilentlyContinue | Out-Null
        $Entry['ts'] = (Get-Date).ToUniversalTime().ToString('o')
        Add-Content -Path $path -Value ($Entry | ConvertTo-Json -Compress -Depth 5) -Encoding UTF8
    }
    catch { }
}

function Send-UsysGuardianEvent {
    param([string]$Type, [hashtable]$Fields)
    try {
        $sec = Join-Path $script:UsysRepoRoot 'sector1'
        if (-not (Test-Path (Join-Path $sec 'security'))) { return }
        $py = if (Get-Command python3 -EA SilentlyContinue) { 'python3' }
        elseif (Get-Command python -EA SilentlyContinue) { 'python' }
        else { return }
        $payload = (($Fields.Clone()) + @{ type = $Type }) | ConvertTo-Json -Compress
        $b64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($payload))
        $code = "import sys,json,base64; sys.path.insert(0, r'$sec'); " +
        "from security import copes_runtime; " +
        "copes_runtime.dispatch(json.loads(base64.b64decode('$b64')))"
        Start-Job -ScriptBlock { param($p, $c) & $p -c $c 2>$null } -ArgumentList $py, $code |
            Wait-Job -Timeout 6 | Out-Null
    }
    catch { }
}

function Assert-UsysSuiteExecutionAllowed {
    param(
        [object]$Suite,
        [string]$EntryPath,
        [switch]$Unverified,
        [switch]$DryRun
    )
    $manifest = $Suite.Manifest
    $asks = Get-UsysSuitePermissionAsks -Manifest $manifest
    $logBase = @{
        name = [string]$manifest.name; version = [string]$manifest.version
        runtime = [string]$manifest.runtime; entry = [string]$manifest.entry
        entry_sha256 = (Get-UsysFileSha256 $EntryPath)
        permissions = $asks.Declared
    }

    if ($env:PHOENIX_SUITE_NO_GATE -eq '1') {
        Write-UsysWarn 'Suite execution gate BYPASSED (PHOENIX_SUITE_NO_GATE=1)'
        Write-UsysSuiteExecLog ($logBase + @{ decision = 'bypassed'; gated_by = 'PHOENIX_SUITE_NO_GATE' })
        return $true
    }

    # qemu (and anything not a host runtime) is contained by the VM boundary
    if ([string]$manifest.runtime -notin $script:UsysHostRuntimes) {
        Write-UsysInfo "Execution gate: '$($manifest.runtime)' runtime is VM-contained — pass"
        Write-UsysSuiteExecLog ($logBase + @{ decision = 'allow'; gated_by = "vm-contained" })
        return $true
    }

    $trust = Test-UsysSuiteTrusted -Suite $Suite
    $logBase['trusted'] = $trust.Trusted

    if ($trust.Trusted) {
        Write-UsysOk "Execution gate: trust stamp valid — granted $($asks.Declared -join ', ')"
        Write-UsysSuiteExecLog ($logBase + @{ decision = 'allow'; gated_by = 'trust-stamp' })
        return $true
    }

    Write-UsysWarn "Execution gate: $($trust.Reason)"
    if ($asks.Elevated.Count -eq 0) {
        Write-UsysInfo 'No elevated permissions declared — allowing unstamped run'
        Write-UsysSuiteExecLog ($logBase + @{ decision = 'allow'; gated_by = 'no-elevated-asks' })
        return $true
    }

    Write-UsysWarn "Unstamped suite asks for: $($asks.Elevated -join ', ')"
    Send-UsysGuardianEvent -Type 'suite_unrecognized' -Fields @{
        name = [string]$manifest.name; version = [string]$manifest.version
        runtime = [string]$manifest.runtime
        elevated = ($asks.Elevated -join ','); source = 'usys run'
    }

    if ($DryRun) {
        Write-UsysInfo '[DRY RUN] real run would require -Unverified or an interactive "yes"'
        Write-UsysSuiteExecLog ($logBase + @{ decision = 'would-block'; gated_by = 'dry-run' })
        return $true
    }
    if ($Unverified) {
        Write-UsysWarn 'Proceeding on -Unverified — you have accepted the risk'
        Write-UsysSuiteExecLog ($logBase + @{ decision = 'allow'; gated_by = 'unverified-flag' })
        return $true
    }
    if ([Environment]::UserInteractive) {
        try {
            $ans = Read-Host "  Run this unverified suite anyway? type 'yes'"
            if ($ans -eq 'yes') {
                Write-UsysSuiteExecLog ($logBase + @{ decision = 'allow'; gated_by = 'interactive-consent' })
                return $true
            }
        }
        catch {
            # no real console (NonInteractive host) — fall through to refuse
        }
    }

    Write-UsysErr "Refused: unstamped suite with elevated permission asks."
    Write-UsysInfo "  vouch for it:  usys suite-trust $($manifest.name)"
    Write-UsysInfo "  or one-shot:   usys run $($manifest.name) --unverified"
    Write-UsysSuiteExecLog ($logBase + @{ decision = 'refused'; gated_by = 'gate' })
    return $false
}

function Invoke-UsysSuiteTrust {
    param(
        [Parameter(Mandatory)][string]$SuiteName,
        [string]$Version = ''
    )
    $suites = Find-UsysSuites -Name $SuiteName
    if ($suites.Count -eq 0) { Write-UsysErr "Suite not found: $SuiteName"; return }
    $suite = if ($Version) {
        $suites | Where-Object { $_.Version -eq $Version } | Select-Object -First 1
    }
    else {
        $suites | Sort-Object { ConvertTo-UsysSortVersion $_.Version } -Descending | Select-Object -First 1
    }
    if (-not $suite) { Write-UsysErr "Suite version not found: $SuiteName@$Version"; return }

    $entryPath = Join-Path $suite.Path $suite.Manifest.entry
    if (-not (Test-Path $entryPath)) {
        Write-UsysErr "Entry point not found: $($suite.Manifest.entry)"; return
    }
    if (-not (Get-UsysSuiteTrustKey)) {
        Write-UsysErr 'PHOENIX_AUTH not set — cannot stamp. Run: usys init'; return
    }

    $stamp = Get-UsysSuiteStampValue -Manifest $suite.Manifest -EntryPath $entryPath
    $obj = [ordered]@{
        v            = 1
        algo         = 'HMAC-SHA256'
        stamp        = $stamp
        entry        = [string]$suite.Manifest.entry
        entry_sha256 = (Get-UsysFileSha256 $entryPath)
        stamped_at   = (Get-Date).ToUniversalTime().ToString('o')
        stamped_by   = $env:USERNAME
        machine      = $env:COMPUTERNAME
    }
    $stampPath = Join-Path $suite.Path '.phoenix-trust'
    $obj | ConvertTo-Json | Set-Content -Path $stampPath -Encoding UTF8
    Write-UsysOk "Trust-stamped: $($suite.Manifest.name) v$($suite.Manifest.version)"
    Write-UsysInfo "  $stampPath"
    Write-UsysInfo '  (machine-bound — re-run this on any other machine that will execute the suite)'
}

function Invoke-UsysRun {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$SuiteName,

        [string]$Version = '',
        [switch]$DryRun,

        # Accept an unstamped suite that asks for elevated permissions
        # (network / broad filesystem:write / process:spawn / env:write).
        # The explicit "I know this is unverified" flag from the audit.
        [switch]$Unverified,

        # Override accelerator: auto | tcg | whpx | hyperv | kvm
        # 'auto' = Phoenix picks the best available (default)
        # 'tcg'  = pure software, always works, slow
        # 'whpx' = Windows Hypervisor Platform, fast
        # 'hyperv' = WHPX + full Hyper-V enlightenments, fastest on Windows
        # 'kvm'  = Linux KVM, fast on Linux/WSL
        [ValidateSet('auto','tcg','whpx','hyperv','kvm')]
        [string]$Accel = 'auto',

        # -Share: expose F:\Phoenix\{Desktop,Documents,Downloads,Projects,Vault}
        # to Debian via QEMU virtio-9p passthrough.
        # Default off — 'usys run debian' is unchanged without this flag.
        # Requires security_model=mapped-xattr (no elevation needed).
        [switch]$Share,

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
        $suites | Sort-Object { ConvertTo-UsysSortVersion $_.Version } -Descending | Select-Object -First 1
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

    # ── execution gate — check before execution (audit T1 #1 + #3) ────────────
    if (-not (Assert-UsysSuiteExecutionAllowed -Suite $suite -EntryPath $entryPath `
                -Unverified:$Unverified -DryRun:$DryRun)) {
        return
    }

    if ($DryRun) {
        Write-Host ''
        Write-Host '  [DRY RUN] Would execute:' -ForegroundColor Cyan
        Write-Host "    Runtime: $($manifest.runtime)" -ForegroundColor White
        Write-Host "    Entry: $entryPath" -ForegroundColor White
        Write-Host "    Args: $($Arguments -join ' ')" -ForegroundColor White
        Write-Host ''
        return
    }
    
    # Set environment variables from manifest -- host runtimes only (the qemu
    # branch reads PHOENIX_VM_* straight from the manifest, and a VM-contained
    # suite must not be able to rewrite the host's PATH before QEMU is
    # resolved). Previous values are restored after the run so a suite's
    # environment never leaks into the user's shell session.
    $savedEnv = @{}
    if ($manifest.environment -and ([string]$manifest.runtime -in $script:UsysHostRuntimes)) {
        $manifest.environment.PSObject.Properties | ForEach-Object {
            $savedEnv[$_.Name] = [Environment]::GetEnvironmentVariable($_.Name)
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
                        # Get-WindowsOptionalFeature -Online hits DISM and throws a raw
                        # exception ("The requested operation requires elevation.") when
                        # not run as admin — -ErrorAction does NOT suppress it. USys is
                        # user-scope by design (see Test-UsysElevation above), so a failed
                        # probe must fall back to 'tcg' exactly like "feature not enabled"
                        # does, not abort the whole run.
                        try {
                            $hvFeature = Get-WindowsOptionalFeature -Online -FeatureName 'HypervisorPlatform' -ErrorAction SilentlyContinue
                        } catch {
                            $hvFeature = $null
                        }
                        if ($hvFeature -and $hvFeature.State -eq 'Enabled') {
                            $resolvedAccel = 'whpx'
                        } else {
                            # Without admin the DISM probe always fails, which used to mean
                            # TCG every time. Let QEMU decide instead: it tries WHPX first
                            # and drops to TCG only if WHPX is really unavailable.
                            $resolvedAccel = 'whpx-or-tcg'
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
                    'whpx-or-tcg' { Write-UsysInfo 'Accelerator: WHPX if available, else TCG (QEMU picks)' }
                }
                if ($resolvedAccel -eq 'tcg' -and ($IsWindows -or $env:OS -eq 'Windows_NT')) {
                    Write-UsysInfo '  → For full speed run: usys run debian --accel hyperv'
                }

                # ── Cloud-init seed (convention: a 'seed/user-data' dir next to
                #    the suite's disk image) — no ISO tooling needed. Serves the
                #    seed over HTTP on loopback; QEMU's user-mode network maps
                #    that to 10.0.2.2 on the Debian side. See PHOENIX_MANUAL.md
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
                    # hostfwd bound to loopback: an empty host address makes QEMU listen on
                    # 0.0.0.0, exposing the VM's phoenix/phoenix password SSH (NOPASSWD sudo)
                    # to the whole LAN. Local SSH (ssh -p 2222 phoenix@127.0.0.1) is unchanged.
                    $netArgs = @('-net', "user,hostfwd=tcp:127.0.0.1:2222-:22", '-net', 'nic,model=virtio')
                    $smbiosArg = @('-smbios', "type=1,serial=ds=nocloud-net;s=http://10.0.2.2:$seedPort/")
                    Write-UsysInfo "Cloud-init: user 'phoenix' / password 'phoenix' (sudo, no key needed) — SSH: ssh -p 2222 phoenix@127.0.0.1"
                }

                # ── Shared FS virtio-9p arguments ─────────────────────────
                # Only appended when -Share is passed. Each directory becomes
                # a separate -virtfs tag. security_model=mapped-xattr works
                # without QEMU running as admin (passthrough needs admin).
                $virtfsArgs = @()
                if ($Share) {
                    Write-PhxFsBanner
                    Write-Host ''
                    $mountedDirs = @()
                    foreach ($dir in $script:PhxSharedDirs) {
                        $winPath = Join-Path $script:PhxSharedRoot $dir
                        if (Test-Path $winPath) {
                            $qemuPath = ConvertTo-QemuHostPath $winPath
                            $tag      = "phoenix-$($dir.ToLower())"
                            $virtfsArgs += @('-virtfs',
                                "local,path=$qemuPath,mount_tag=$tag,security_model=mapped-xattr,readonly=off")
                            $mountedDirs += $dir
                        } else {
                            Write-UsysWarn "Shared dir not found on host, skipping: $winPath"
                        }
                    }
                    if ($mountedDirs.Count -gt 0) {
                        Write-UsysInfo "Shared dirs mounted: $($mountedDirs -join ', ')"
                        Write-UsysInfo "Mount tags: phoenix-<dir> — see /phoenix/ inside Debian"
                    }
                    Write-Host ''
                }

                # ── Build QEMU argument list ──────────────────────────────
                # An .iso entry boots as a live CD; anything else is the VM's disk.
                $bootArgs = if ($entryPath -like '*.iso') {
                    @('-cdrom', $entryPath, '-boot', 'd')
                } else {
                    @('-drive', "file=$($entryPath.Replace(',', ',,')),format=$(if ($entryPath -like '*.img') { 'raw' } else { 'qcow2' }),if=virtio")
                }
                $qemuArgs = @(
                    '-m',       $ram,
                    '-smp',     $cpus,
                    '-display', $display
                ) + $bootArgs + $netArgs

                # UEFI-only images (e.g. Gentoo's di-* cloud images) set
                # PHOENIX_VM_FIRMWARE=uefi. The firmware must go in as a read-only
                # pflash drive; `-bios <edk2 code.fd>` refuses to load it.
                if ($manifest.environment.PHOENIX_VM_FIRMWARE -eq 'uefi') {
                    $qemuDir = Split-Path $qemu
                    $edk2 = @(
                        (Join-Path $qemuDir 'share\edk2-x86_64-code.fd'),
                        (Join-Path $qemuDir '../share/qemu/edk2-x86_64-code.fd'),
                        '/usr/share/qemu/edk2-x86_64-code.fd',
                        '/usr/share/OVMF/OVMF_CODE.fd'
                    ) | Where-Object { Test-Path $_ } | Select-Object -First 1
                    if (-not $edk2) {
                        Write-UsysErr 'Suite needs UEFI firmware (edk2-x86_64-code.fd) and none was found next to QEMU.'
                        return
                    }
                    Write-UsysInfo "Firmware: UEFI ($edk2)"
                    $qemuArgs += @('-drive', "if=pflash,format=raw,readonly=on,file=$($edk2.Replace(',', ',,'))")
                }
                if ($smbiosArg)         { $qemuArgs += $smbiosArg }
                if ($virtfsArgs.Count)  { $qemuArgs += $virtfsArgs }

                # Accelerator args — hyperv gets the full enlightenment set
                # These tell the Debian kernel to use Hyper-V hypercalls instead of
                # emulated hardware for timers, spinlocks, APIC, etc.
                # Result: boot time drops from minutes to seconds.
                if ($resolvedAccel -eq 'hyperv') {
                    $qemuArgs += @('-accel', 'whpx')
                    $qemuArgs += @('-cpu', 'host,hv_relaxed,hv_spinlocks=0x1fff,hv_vapic,hv_time,hv_crash,hv_reset,hv_vpindex,hv_runtime,hv_synic,hv_stimer,hv_tlbflush,hv_ipi')
                } elseif ($resolvedAccel -eq 'kvm') {
                    $qemuArgs += @('-accel', 'kvm')
                    $qemuArgs += @('-cpu', 'host')
                } elseif ($resolvedAccel -eq 'whpx-or-tcg') {
                    $qemuArgs += @('-accel', 'whpx', '-accel', 'tcg')
                } else {
                    $qemuArgs += @('-accel', $resolvedAccel)
                }
                if ($snapshot) { $qemuArgs += $snapshot }

                # Pass any extra user args through (e.g. -cdrom seed.iso for cloud-init)
                # Strip internal Phoenix switches that must not reach QEMU
                $extraArgs = $Arguments | Where-Object { $_ -notin '-Persist', '--share', '-Share' }
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
    } finally {
        foreach ($k in $savedEnv.Keys) {
            [Environment]::SetEnvironmentVariable($k, $savedEnv[$k])
        }
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
    
    $suites | Sort-Object Name, { ConvertTo-UsysSortVersion $_.Version } | ForEach-Object {
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

# =============================================================================
# SUITE PROMOTE — wrap any intaked file as a runnable suite
# =============================================================================
function Get-UsysRuntimeForExt {
    # Maps file extension to runtime string — mirrors detect_filetype() in intake.sh
    param([string]$Filename)
    $ext = [System.IO.Path]::GetExtension($Filename).ToLowerInvariant().TrimStart('.')
    switch ($ext) {
        'py'    { return 'python' }
        'sh'    { return 'bash' }
        'bash'  { return 'bash' }
        'zsh'   { return 'bash' }
        'ps1'   { return 'powershell' }
        'js'    { return 'node' }
        'mjs'   { return 'node' }
        'cjs'   { return 'node' }
        'qcow2' { return 'qemu' }
        'img'   { return 'qemu' }
        default { return 'binary' }
    }
}

function Invoke-UsysSuitePromote {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory, Position = 0)]
        [string]$Name,

        [string]$Desc = ''
    )

    $clonepoolDir = Get-UsysClonepoolDir

    # Find the latest versioned file matching this name in the clonepool
    $target = $null
    $targetVersion = 'v1'
    Get-ChildItem -Path $clonepoolDir -Directory -ErrorAction SilentlyContinue | ForEach-Object {
        $candidate = Get-ChildItem -Path $_.FullName -File -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -match '^v\d+_' -and $_.BaseName -replace '^v\d+_','' -eq $Name } |
            Sort-Object { [int]($_.Name -replace '^v(\d+)_.*','$1') } |
            Select-Object -Last 1
        if ($candidate -and (-not $target -or [int]($candidate.Name -replace '^v(\d+)_.*','$1') -gt [int]($target.Name -replace '^v(\d+)_.*','$1'))) {
            $target = $candidate
        }
    }

    if (-not $target) {
        Write-UsysErr "No intaked file named '$Name' found in clonepool"
        Write-UsysInfo "Intake it first: usys clone <file> or usys intake <file>"
        return
    }

    $entryFilename  = $target.Name -replace '^v\d+_',''
    $targetVersion  = $target.Name -replace '^(v\d+)_.*','$1'
    $runtime        = Get-UsysRuntimeForExt -Filename $entryFilename
    $hexId          = Split-Path $target.DirectoryName -Leaf
    $description    = if ($Desc) { $Desc } else { "Phoenix suite — promoted from $entryFilename" }

    $manifest = [ordered]@{
        name         = $Name
        version      = $targetVersion
        description  = $description
        author       = 'phoenix'
        type         = 'script'
        entry        = $entryFilename
        runtime      = $runtime
        dependencies = @()
        environment  = @{}
        permissions  = @('filesystem:read')
        metadata     = [ordered]@{
            category = 'promoted'
            tags     = @('promoted', 'no-install', 'phoenix')
            hex_id   = $hexId
        }
    }

    # Write to temp, then intake through Invoke-UsysClone so it gets
    # hex identity, QR strings, hash baseline, D1 record, R2 upload.
    # The .suite.json auto-registration hook in intake.sh then fires
    # and places it at clonepool/<name>/.suite.json automatically.
    $tmpDir  = Join-Path ([System.IO.Path]::GetTempPath()) "phoenix-promote-$Name"
    $tmpFile = Join-Path $tmpDir "$Name.suite.json"
    New-Item -ItemType Directory -Path $tmpDir -Force | Out-Null
    $manifest | ConvertTo-Json -Depth 6 | Set-Content $tmpFile -Encoding UTF8

    Write-Host ''
    Write-UsysInfo "Promoting '$Name' ($entryFilename) as runtime: $runtime"
    Write-UsysInfo "Intaking generated manifest through Phoenix pipeline..."
    Write-Host ''

    Invoke-UsysClone -Path $tmpFile

    # Clean up temp
    Remove-Item $tmpDir -Recurse -Force -ErrorAction SilentlyContinue

    Write-Host ''
    Write-UsysOk "Suite promoted: $Name v$targetVersion — runnable: usys run $Name"
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
        $suites | Sort-Object { ConvertTo-UsysSortVersion $_.Version } -Descending | Select-Object -First 1
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
# SHARED FS — enforcement boundary between Windows host and Debian (QEMU peer)
# =============================================================================

function Test-PhxSharedPath([string]$Path) {
    # Returns true only if Path resolves under $script:PhxSharedRoot.
    # Called by every phx- wrapper before acting — no raw FS access bypasses this.
    if ([string]::IsNullOrWhiteSpace($Path)) { return $false }
    $norm = $Path.TrimEnd('\', '/')
    $root = $script:PhxSharedRoot.TrimEnd('\', '/')
    return $norm.StartsWith($root, [System.StringComparison]::OrdinalIgnoreCase)
}

function Invoke-PhxImport {
    # phx-import <path>
    # Direction: shared FS → clonepool
    # Validates path is inside PhxSharedRoot, then calls Invoke-UsysClone
    # so the file gets hex ID, QR, hash baseline, D1 record.
    [CmdletBinding()]
    param(
        [Parameter(Mandatory, Position = 0)]
        [string]$Path,
        [switch]$DryRun
    )

    if (-not (Test-PhxSharedPath $Path)) {
        Write-UsysErr "phx-import: path must be inside $script:PhxSharedRoot — got: $Path"
        return
    }
    if (-not (Test-Path $Path)) {
        Write-UsysErr "phx-import: path not found: $Path"
        return
    }

    Write-UsysInfo "phx-import: $Path → clonepool"
    Invoke-UsysClone -Path $Path -Category 'shared-fs' -DryRun:$DryRun
}
Set-Alias -Name phx-import -Value Invoke-PhxImport -Scope Global -Force -ErrorAction SilentlyContinue

function Invoke-PhxExport {
    # phx-export <hex-or-name> <destination-dir>
    # Direction: clonepool → shared FS
    # Copies the latest versioned file from the pool into a named shared directory.
    [CmdletBinding()]
    param(
        [Parameter(Mandatory, Position = 0)]
        [string]$NameOrHex,

        [Parameter(Mandatory, Position = 1)]
        [string]$DestDir,

        [switch]$DryRun
    )

    if (-not (Test-PhxSharedPath $DestDir)) {
        Write-UsysErr "phx-export: destination must be inside $script:PhxSharedRoot — got: $DestDir"
        return
    }

    $pool = Get-UsysClonepoolDir
    # Find the named suite directory first
    $suiteDir = Join-Path $pool $NameOrHex
    $sourceFile = $null

    if (Test-Path $suiteDir) {
        # Named suite — find the latest versioned payload file (not .suite.json sidecar)
        $sourceFile = Get-ChildItem -Path $suiteDir -File -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -notlike '.suite.json' -and $_.Name -notlike '*.sidecar.json' } |
            Sort-Object Name -Descending | Select-Object -First 1
    }

    if (-not $sourceFile) {
        # Fall back: search hex bucket directories
        Get-ChildItem -Path $pool -Directory -ErrorAction SilentlyContinue | ForEach-Object {
            if (-not $sourceFile) {
                $f = Get-ChildItem -Path $_.FullName -File -ErrorAction SilentlyContinue |
                    Where-Object { $_.BaseName -replace '^v\d+_','' -eq $NameOrHex } |
                    Sort-Object Name -Descending | Select-Object -First 1
                if ($f) { $sourceFile = $f }
            }
        }
    }

    if (-not $sourceFile) {
        Write-UsysErr "phx-export: '$NameOrHex' not found in clonepool"
        return
    }

    if (-not (Test-Path $DestDir)) {
        if ($DryRun) {
            Write-Host "  [DRY RUN] Would create: $DestDir" -ForegroundColor Cyan
        } else {
            New-Item -ItemType Directory -Path $DestDir -Force | Out-Null
        }
    }

    $destPath = Join-Path $DestDir $sourceFile.Name
    Write-UsysInfo "phx-export: $($sourceFile.FullName) → $destPath"

    if ($DryRun) {
        Write-Host "  [DRY RUN] Would copy: $($sourceFile.FullName)" -ForegroundColor Cyan
        Write-Host "         → $destPath" -ForegroundColor Cyan
    } else {
        Copy-Item -Path $sourceFile.FullName -Destination $destPath -Force
        Write-UsysOk "Exported to: $destPath"
    }
}
Set-Alias -Name phx-export -Value Invoke-PhxExport -Scope Global -Force -ErrorAction SilentlyContinue

function Invoke-PhxSync {
    # phx-sync <dir>
    # Direction: shared FS dir → clonepool (import only, never destructive)
    # Walks every file in the named shared dir; imports anything not yet in the pool.
    # Checks by calling Invoke-PhxImport — idempotent (intake.sh duplicate-detection
    # skips files already registered).
    [CmdletBinding()]
    param(
        [Parameter(Mandatory, Position = 0)]
        [string]$Dir,

        [switch]$DryRun
    )

    # Accept short name ("Desktop") or full path ("F:\Phoenix\Desktop")
    $fullPath = if (Test-PhxSharedPath $Dir) {
        $Dir
    } else {
        Join-Path $script:PhxSharedRoot $Dir
    }

    if (-not (Test-PhxSharedPath $fullPath)) {
        Write-UsysErr "phx-sync: path must be inside $script:PhxSharedRoot — got: $fullPath"
        return
    }
    if (-not (Test-Path $fullPath)) {
        Write-UsysErr "phx-sync: directory not found: $fullPath"
        return
    }

    Write-UsysInfo "phx-sync: scanning $fullPath"
    $files = Get-ChildItem -Path $fullPath -File -Recurse -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -notlike '_PHOENIX_DIR.txt' }

    if ($files.Count -eq 0) {
        Write-UsysInfo "phx-sync: directory is empty — nothing to import"
        return
    }

    Write-UsysInfo "phx-sync: found $($files.Count) file(s)"
    $imported = 0
    foreach ($f in $files) {
        Write-UsysInfo "  → $($f.FullName)"
        if (-not $DryRun) {
            Invoke-PhxImport -Path $f.FullName
            $imported++
        }
    }
    if ($DryRun) {
        Write-Host "  [DRY RUN] Would import $($files.Count) file(s)" -ForegroundColor Cyan
    } else {
        Write-UsysOk "phx-sync complete: $imported file(s) processed"
    }
}
Set-Alias -Name phx-sync -Value Invoke-PhxSync -Scope Global -Force -ErrorAction SilentlyContinue

function Invoke-PhxLs {
    # phx-ls [dir]
    # Read-only: lists shared FS directories and their clonepool registration status.
    [CmdletBinding()]
    param(
        [Parameter(Position = 0)]
        [string]$Dir = ''
    )

    Write-Host ''
    Write-PhxFsBanner
    Write-Host ''

    $workerUrl  = $env:PHOENIX_WORKER_URL
    $workerAuth = $env:PHOENIX_AUTH
    $pool       = Get-UsysClonepoolDir

    $dirsToList = if ($Dir) { @($Dir) } else { $script:PhxSharedDirs }

    foreach ($d in $dirsToList) {
        $fullPath = if (Test-PhxSharedPath $d) { $d } else { Join-Path $script:PhxSharedRoot $d }
        $exists   = Test-Path $fullPath
        $label    = if ($exists) { $d } else { "$d (missing)" }
        Write-Host "  $label" -ForegroundColor $(if ($exists) { 'Cyan' } else { 'DarkGray' })

        if ($exists) {
            $files = Get-ChildItem -Path $fullPath -File -ErrorAction SilentlyContinue |
                Where-Object { $_.Name -notlike '_PHOENIX_DIR.txt' }
            if ($files.Count -eq 0) {
                Write-Host "    (empty)" -ForegroundColor DarkGray
            } else {
                foreach ($f in $files) {
                    # Check whether this file has a matching entry in the local clonepool.
                    # We detect by looking for any versioned file with the same name in any hex bucket.
                    $registered = $false
                    Get-ChildItem -Path $pool -Directory -ErrorAction SilentlyContinue | ForEach-Object {
                        if (-not $registered) {
                            $hit = Get-ChildItem -Path $_.FullName -File -ErrorAction SilentlyContinue |
                                Where-Object { $_.Name -replace '^v\d+_','' -eq $f.Name } |
                                Select-Object -First 1
                            if ($hit) { $registered = $true }
                        }
                    }
                    $status = if ($registered) { '[pool]' } else { '[new] ' }
                    $color  = if ($registered) { 'Green' } else { 'Yellow' }
                    Write-Host "    $status  $($f.Name)" -ForegroundColor $color
                }
            }
        }
        Write-Host ''
    }
    Write-Host "  Shared root : $script:PhxSharedRoot"
    Write-Host "  Clonepool   : $pool"
    Write-Host "  Import new  : phx-import <path>   Sync all: phx-sync <dir>" -ForegroundColor DarkGray
    Write-Host ''
}
Set-Alias -Name phx-ls -Value Invoke-PhxLs -Scope Global -Force -ErrorAction SilentlyContinue

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
    clone <name> [vN] [folder]   OUT of the clone pool into a folder (default: here)
                                 (global `clone` is the same; IN = global `intake <file>`)
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
    console                      Open the Phoenix Console (machines, links, hands) with its key
    search <query>               Search clonepool + catalog
    pull <suite>                 Pull suite record from D1 and stage locally
    pull <name> -Destination <d> Pull the real bytes into folder <d>, SHA3-checked

  Distros (Linux VMs via QEMU — no install, no WSL, Phoenix brings the OS):
    distro list                  Show registered distros
    distro fetch-qemu            Instructions to get QEMU binary
    distro intake-qemu           Intake QEMU binary into clone pool
    run debian                   Boot Debian 12 VM (auto accelerator)
    run ubuntu                   Boot Ubuntu 24.04 VM (auto accelerator)
    run debian --accel tcg       Act 1: pure software emulation, no HW required
    run debian --accel hyperv    Act 2: WHPX + Hyper-V enlightenments, near-native speed
    run debian --share           Boot with shared FS (F:\Phoenix\* → /phoenix/*)
    run debian --accel hyperv --share   Full speed + shared FS

  Shared FS (Windows hosts F:\Phoenix\*, Debian mounts /phoenix/* via QEMU):
    usys fs-init                 One-time setup: create F:\Phoenix\{dirs}, wire profile
    usys fs-ls [dir]             List shared dirs + pool registration status
    usys fs-import <path>        Import a shared-FS file into the clonepool
    usys fs-export <name> <dir>  Export a pool item into a shared dir
    usys fs-sync <dir>           Sync all files in a shared dir into the pool

    phx-import <path>            Same as usys fs-import (profile alias)
    phx-export <name> <dir>      Same as usys fs-export (profile alias)
    phx-sync <dir>               Same as usys fs-sync (profile alias)
    phx-ls [dir]                 Same as usys fs-ls (profile alias)

    Rule: ALL operations against F:\Phoenix\ go through these wrappers.
          No raw path access. No bypass. The profile enforces this.

  Suites:
    suite-promote <name>             Wrap an intaked file as a runnable suite
    suite-promote <name> -Desc "x"  Same with a custom description
    suite-list                       List all runnable suites in clonepool
    list-suites                      Alias for suite-list
    suite-trust <name>[@ver]         Trust-stamp a suite for execution on THIS machine
    run <name> --unverified          Run an unstamped elevated-ask suite anyway

  Suite execution gate (audit T1 #1+#3): a host-runtime suite (python/node/
    bash/powershell/binary) that is not trust-stamped and declares network /
    filesystem:write / process:spawn / env:write is refused by 'usys run'
    until you 'usys suite-trust' it or pass --unverified. qemu suites are
    VM-contained and pass freely. Bypass all of it: PHOENIX_SUITE_NO_GATE=1.
    Decisions log to ~/.unitedsys/logs/suite_exec.jsonl.

  Legacy registry — NOT SHIPPED (only works with an external usys.sh via
  USYS_ENGINE; 'usys init' does not install one):
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
    PHOENIX_AUTH, PHOENIX_WORKER_URL, CLONEPOOL_DIR, PHOENIX_SUITE_NO_GATE

"@
}

# =============================================================================
# MAIN DISPATCHER. On dot-source (the profile) it is exported as `usys`; as a
# PATH script it is called directly. It is never left behind as a global function
# whose script-scope helpers are gone: that broke every second `usys` in a window
# opened without the profile (2026-10-07 audit XCUT-F35).
# =============================================================================
function Invoke-UsysMain {
    [CmdletBinding()]
    param(
        [Parameter(Position = 0)]
        [string]$Command = 'help',

        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]]$Rest
    )

    Test-UsysElevation | Out-Null
    # Paths in any form (F:\x, F:/x, /f/x, ~/x) work the same (Jerry 10/7, scripts\phoenix-paths.ps1)
    if ($Rest -and (Get-Command Resolve-PhoenixArgs -ErrorAction SilentlyContinue)) { $Rest = Resolve-PhoenixArgs $Rest }

    switch ($Command.ToLowerInvariant()) {
        'init'          { Invoke-UsysInit }
        'status'        { Invoke-UsysStatus }
        'doctor'        { Invoke-UsysDoctor }
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
            # OUT of the pool (2026-10-02; it used to put files IN — that is
            # `usys intake`/`intake` now). Same engine as the global `clone`.
            Invoke-UsysCloneOut -CloneArgs $Rest
        }

        'console' {
            # The Console needs its key on every /api call (S34OPS-S24). It goes in the URL fragment,
            # which the browser never sends to a server or a log.
            $tokFile = Join-Path $HOME '.phoenix\console.token'
            $port = if ($env:PHOENIX_CONSOLE_PORT) { $env:PHOENIX_CONSOLE_PORT } else { '8470' }
            try { $null = Invoke-WebRequest "http://127.0.0.1:$port/" -TimeoutSec 3 -UseBasicParsing }
            catch { Write-UsysErr "the Console isn't running on 127.0.0.1:$port (start it: schtasks /Run /TN PhoenixPortal)"; return }
            if (-not (Test-Path $tokFile)) { Write-UsysErr "no console key at $tokFile (the Console makes it when it starts)"; return }
            $tok = (Get-Content -Raw $tokFile).Trim()
            Start-Process "http://127.0.0.1:$port/#k=$tok"
            Write-Host "  Console opened in your browser (http://127.0.0.1:$port/)"
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
            if ($Rest.Count -lt 1) { Write-UsysErr 'usage: usys run <suite> [--accel auto|tcg|whpx|hyperv|kvm] [--share] [--unverified] [args...]'; return }
            $dry        = $Rest -contains '-DryRun' -or $Rest -contains '--dry-run'
            $share      = $Rest -contains '--share' -or $Rest -contains '-Share'
            $unverified = $Rest -contains '--unverified' -or $Rest -contains '-Unverified'
            $accel      = 'auto'
            $suiteName  = $Rest[0]
            $version    = ''

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
                    $skipNext = $true
                    continue
                }
                if ($token -in '--share', '-Share', '--unverified', '-Unverified') { continue }
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
            Invoke-UsysRun -SuiteName $suiteName -Version $version -Accel $accel -Share:$share -Unverified:$unverified -DryRun:$dry -Arguments $passArgs
        }

        'suite-trust' {
            if ($Rest.Count -lt 1) { Write-UsysErr 'usage: usys suite-trust <suite> [@version]'; return }
            $sn = $Rest[0]; $sv = ''
            if ($sn -match '^(.+)@(.+)$') { $sn = $matches[1]; $sv = $matches[2] }
            Invoke-UsysSuiteTrust -SuiteName $sn -Version $sv
        }

        'pull' {
            if ($Rest.Count -lt 1) { Write-UsysErr 'usage: usys pull <suite> [-Destination <folder>]'; return }
            $dry = $Rest -contains '-DryRun' -or $Rest -contains '--dry-run'
            # -Destination was documented but never parsed here, so a pull into
            # a folder only staged a stub (2026-10-02).
            $dest = ''
            $i = [array]::IndexOf([string[]]$Rest, '-Destination')
            if ($i -ge 0 -and $i + 1 -lt $Rest.Count) { $dest = $Rest[$i + 1] }
            $name = $Rest | Where-Object { $_ -notin '-DryRun','--dry-run','-Destination' -and $_ -ne $dest } | Select-Object -First 1
            if ($dest) { New-Item -ItemType Directory -Force -Path $dest | Out-Null; $dest = (Resolve-Path $dest).Path }
            Invoke-UsysPull -SuiteName $name -Destination $dest -DryRun:$dry
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

        'suite-list' {
            Invoke-UsysListSuites
        }

        'suite-promote' {
            if ($Rest.Count -lt 1) { Write-UsysErr 'usage: usys suite-promote <name> [-Desc "description"]'; return }
            $name = $Rest[0]
            $desc = ''
            for ($i = 1; $i -lt $Rest.Count; $i++) {
                if ($Rest[$i] -in '-Desc','--desc' -and $i + 1 -lt $Rest.Count) { $desc = $Rest[++$i] }
            }
            Invoke-UsysSuitePromote -Name $name -Desc $desc
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
                    if (Invoke-UsysIntakeFile -Path $qemu) { Write-UsysOk "Intaked: $qemu" }
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

        'fs-init' {
            # Bootstrap the shared directories (delegate to setup-shared-fs logic inline)
            $repoRoot = Get-UsysRepoRoot
            $setupScript = Join-Path $repoRoot 'tools\poc\setup-shared-fs.ps1'
            if (Test-Path $setupScript) {
                & pwsh -NoProfile -ExecutionPolicy Bypass -File $setupScript
            } else {
                Write-UsysErr "setup-shared-fs.ps1 not found. Expected at: $setupScript"
                Write-UsysInfo "Run: pwsh tools\poc\setup-shared-fs.ps1 directly from the repo root"
            }
        }

        'fs-ls' {
            $dir = if ($Rest.Count -ge 1) { $Rest[0] } else { '' }
            Invoke-PhxLs -Dir $dir
        }

        'fs-import' {
            if ($Rest.Count -lt 1) { Write-UsysErr 'usage: usys fs-import <path>'; return }
            $dry = $Rest -contains '-DryRun' -or $Rest -contains '--dry-run'
            $path = $Rest | Where-Object { $_ -notin '-DryRun','--dry-run' } | Select-Object -First 1
            Invoke-PhxImport -Path $path -DryRun:$dry
        }

        'fs-export' {
            if ($Rest.Count -lt 2) { Write-UsysErr 'usage: usys fs-export <name-or-hex> <dest-dir>'; return }
            $dry = $Rest -contains '-DryRun' -or $Rest -contains '--dry-run'
            Invoke-PhxExport -NameOrHex $Rest[0] -DestDir $Rest[1] -DryRun:$dry
        }

        'fs-sync' {
            if ($Rest.Count -lt 1) { Write-UsysErr 'usage: usys fs-sync <dir>'; return }
            $dry = $Rest -contains '-DryRun' -or $Rest -contains '--dry-run'
            $dir = $Rest | Where-Object { $_ -notin '-DryRun','--dry-run' } | Select-Object -First 1
            Invoke-PhxSync -Dir $dir -DryRun:$dry
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
function Invoke-UsysDownload {
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
        if (Invoke-UsysIntakeFile -Path $OutFile) { Write-UsysOk "Intaked: $OutFile" }
    }
}


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

    $auto = $AutoIntake.IsPresent

    # Resolve the CANONICAL intake pipeline (sector2/package-handler/intake.sh)
    # here in the parent, where Get-UsysGitBash/Get-UsysCloneIntakeSh/
    # ConvertTo-GitBashPath already exist — Start-Job's scriptblock runs in a
    # separate process with none of this script's functions loaded, so the
    # resolved paths are handed in as arguments instead. Was calling the
    # deprecated phoenix-core/tools/intake.py stub (no R2, no integrity
    # baseline, and its D1 sync now silently reports fake success under
    # Cloudflare Access — see Invoke-UsysIntakeFile's comment / audit T2 #7).
    $bash       = Get-UsysGitBash
    $intakeSh   = Get-UsysCloneIntakeSh
    if (-not $bash)     { Write-UsysErr 'Git Bash not found. Install Git for Windows or set PHOENIX_BASH.'; return }
    if (-not $intakeSh) { Write-UsysErr 'intake.sh not found. Set PHOENIX_INTAKE or check sector2/package-handler.'; return }
    if (-not $env:CLONEPOOL_DIR) { $env:CLONEPOOL_DIR = Get-UsysClonepoolDir }
    $bashIntake = ConvertTo-GitBashPath $intakeSh
    $bashPool   = ConvertTo-GitBashPath $env:CLONEPOOL_DIR

    $script:UsysWatcherJob = Start-Job -Name 'PhoenixWatcher' -ScriptBlock {
        param($watchPath, $bash, $bashIntake, $bashPool, $auto)

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
                $env:CLONEPOOL_DIR = $bashPool
                $p = $file.Replace([char]92, [char]47)
                if ($p -match '^([A-Za-z]):(.*)') { $p = "/$($Matches[1].ToLower())$($Matches[2])" }
                & $bash $bashIntake $p
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
    } -ArgumentList $Path, $bash, $bashIntake, $bashPool, $auto

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

    $lines = Receive-Job $script:UsysWatcherJob -Keep 2>$null | Where-Object { $_ -match '^INTAKE_PROMPT:' }
    if (-not $lines) { Write-UsysInfo 'No pending files.'; return }

    foreach ($line in $lines) {
        $file = $line -replace '^INTAKE_PROMPT:', ''
        Write-Host ''
        Write-Host "  New file: $file" -ForegroundColor Yellow
        $choice = Read-Host '  Intake into Phoenix? [Y/n]'
        if ($choice -eq '' -or $choice -match '^[Yy]') {
            if (Invoke-UsysIntakeFile -Path $file) { Write-UsysOk "Intaked: $([System.IO.Path]::GetFileName($file))" }
        } else {
            Write-UsysInfo "Skipped: $([System.IO.Path]::GetFileName($file))"
        }
    }
}

# `clone` = OUT of the pool, wherever usys.ps1 is dot-sourced — the same
# engine as bin\clone.cmd and `usys clone`: clone <name> [vN] [folder] [--force]
function Invoke-UsysCloneOut {
    param([string[]]$CloneArgs = @())
    $bash = Get-UsysGitBash
    if (-not $bash) { Write-UsysErr 'Git Bash not found. Install Git for Windows or set PHOENIX_BASH.'; return }
    $cloneSh = Join-Path (Get-UsysRepoRoot) 'bin\clone'
    if (-not (Test-Path $cloneSh)) { Write-UsysErr "bin\clone not found under $(Get-UsysRepoRoot)"; return }
    if (-not $env:CLONEPOOL_DIR) { $env:CLONEPOOL_DIR = Get-UsysClonepoolDir }
    $prevPool = $env:CLONEPOOL_DIR
    $env:CLONEPOOL_DIR = ConvertTo-GitBashPath $env:CLONEPOOL_DIR
    try { & $bash (ConvertTo-GitBashPath $cloneSh) @CloneArgs } finally { $env:CLONEPOOL_DIR = $prevPool }
}
function Invoke-UsysCloneCmd { Invoke-UsysCloneOut -CloneArgs $args }

$__usysDotSourced = ($MyInvocation.InvocationName -eq '.' -or $MyInvocation.Line -match '^\s*\.\s')
if ($__usysDotSourced) {
    # Profile load: everything above now lives in the caller's (global) scope.
    Set-Alias -Name usys          -Value Invoke-UsysMain     -Scope Global -Force
    Set-Alias -Name usys-download -Value Invoke-UsysDownload -Scope Global -Force -ErrorAction SilentlyContinue
    Set-Alias -Name clone         -Value Invoke-UsysCloneCmd -Scope Global -Force -ErrorAction SilentlyContinue
    Set-Alias -Name phx-clone     -Value Invoke-UsysCloneCmd -Scope Global -Force -ErrorAction SilentlyContinue
    # rotate-key: PHOENIX_AUTH rotation in one command (scripts\phoenix-rotate.ps1)
    $__rot = Join-Path $PSScriptRoot 'phoenix-rotate.ps1'
    if (Test-Path $__rot) { . $__rot }
    Remove-Variable __rot -ErrorAction SilentlyContinue
    # slash-insensitive paths (scripts\phoenix-paths.ps1): ConvertTo-PhoenixPath, px - loaded first, g uses it
    $__paths = Join-Path $PSScriptRoot 'phoenix-paths.ps1'
    if (Test-Path $__paths) { . $__paths }
    Remove-Variable __paths -ErrorAction SilentlyContinue
    # g: highlight a path on screen, type g, you're there (scripts\phoenix-goto.ps1)
    $__goto = Join-Path $PSScriptRoot 'phoenix-goto.ps1'
    if (Test-Path $__goto) { . $__goto }
    Remove-Variable __goto -ErrorAction SilentlyContinue
    # short commands: .. repo snap pb3 aws1 box pulse glog gst here pool (scripts\phoenix-aliases.ps1)
    $__al = Join-Path $PSScriptRoot 'phoenix-aliases.ps1'
    if (Test-Path $__al) { . $__al }
    Remove-Variable __al -ErrorAction SilentlyContinue
} else {
    # Direct script invocation (shim mode): run once, define nothing global.
    $cmd  = $args[0]
    $rest = @()
    if ($args.Count -gt 1) { $rest = $args[1..($args.Count - 1)] }
    if (-not $cmd) { Show-UsysHelp; return }
    Invoke-UsysMain -Command $cmd -Rest $rest
}
Remove-Variable __usysDotSourced -ErrorAction SilentlyContinue