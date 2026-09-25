#Requires -Version 7.3
<#
.SYNOPSIS
    Phoenix: key-based SSH between this Windows PC and the Pavilion (Debian 13).
    jwl247 / Jerry Leftwich — GPL v3

.DESCRIPTION
    Run on WINDOWS after tools/pavilion/pavilion-setup.sh has run on the Pavilion.

    Windows -> Pavilion (always):
      1. Creates ~/.ssh/phoenix_pavilion_ed25519 if it doesn't exist
      2. Installs its public key on the Pavilion (asks for the Debian password ONCE)
      3. Adds a `Host pavilion` block to ~/.ssh/config
      4. Proves key auth works with BatchMode (no password allowed)

    Pavilion -> Windows (-AllowReverse, run from an elevated PS7):
      5. Installs + starts the Windows OpenSSH Server if missing, PS7 as its shell
      6. Pulls the Pavilion's own key and authorizes it here (the
         administrators_authorized_keys file + its required ACL for admin accounts)
      7. Writes a `Host <this-pc>` block into the Pavilion's ~/.ssh/config

.EXAMPLE
    pwsh -File tools\pavilion\connect-from-windows.ps1 -HostName 192.168.1.50 -User jerry
.EXAMPLE
    pwsh -File tools\pavilion\connect-from-windows.ps1 -HostName 192.168.1.50 -User jerry -AllowReverse
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $HostName,
    [Parameter(Mandatory)] [string] $User,
    [string] $Alias = 'pavilion',
    [string] $KeyPath = (Join-Path $HOME '.ssh\phoenix_pavilion_ed25519'),
    [switch] $AllowReverse
)
$ErrorActionPreference = 'Stop'

function Ok($m)   { Write-Host "[ OK ] $m" -ForegroundColor Green }
function Warn($m) { Write-Host "[WARN] $m" -ForegroundColor Yellow }
function Fail($m) { Write-Host "[FAIL] $m" -ForegroundColor Red; exit 1 }
function Step($m) { Write-Host "`n== $m ==" -ForegroundColor Cyan }

# --- 0. preflight -----------------------------------------------------------
Step '0. Preflight'
foreach ($tool in 'ssh', 'ssh-keygen') {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        Fail "$tool not found. Settings > System > Optional features > OpenSSH Client."
    }
}
if (-not (Test-Connection -TargetName $HostName -TcpPort 22 -TimeoutSeconds 5 -Quiet)) {
    Fail "Can't reach $HostName on port 22. Is pavilion-setup.sh done, and are both PCs on the same network?"
}
Ok "$HostName answers on port 22"

$sshDir = Join-Path $HOME '.ssh'
New-Item -ItemType Directory -Force -Path $sshDir | Out-Null

# --- 1. key -----------------------------------------------------------------
Step '1. Windows -> Pavilion key'
if (-not (Test-Path $KeyPath)) {
    & ssh-keygen -q -t ed25519 -N '' -C "$env:USERNAME@$env:COMPUTERNAME-to-$Alias" -f $KeyPath
    if ($LASTEXITCODE) { Fail 'ssh-keygen failed' }
    Ok "created $KeyPath"
} else {
    Ok "key exists: $KeyPath"
}
$pub = (Get-Content "$KeyPath.pub" -Raw).Trim()
if ($pub -match "'") { Fail 'public key contains a quote character — refusing to pass it to a remote shell' }

# --- 2. install on Pavilion -------------------------------------------------
Step '2. Authorize key on the Pavilion'
Write-Host 'On first connect SSH shows the host fingerprint. Compare it to what pavilion-setup.sh printed and only type yes if it matches.'
Write-Host "Then enter the Debian password for $User (this is the only time it's needed)."
$remote = "umask 077; mkdir -p ~/.ssh; touch ~/.ssh/authorized_keys; grep -qxF '$pub' ~/.ssh/authorized_keys || echo '$pub' >> ~/.ssh/authorized_keys"
& ssh -o PubkeyAuthentication=no "$User@$HostName" $remote
if ($LASTEXITCODE) { Fail 'could not install key (wrong password, or password auth already disabled with --harden?)' }
Ok 'key installed in authorized_keys'

# --- 3. ssh config ----------------------------------------------------------
Step '3. ~/.ssh/config'
$cfg = Join-Path $sshDir 'config'
$existing = if (Test-Path $cfg) { Get-Content $cfg -Raw } else { '' }
if ($existing -match "(?im)^\s*Host\s+$([regex]::Escape($Alias))\s*$") {
    Warn "Host $Alias already in $cfg — left as is"
} else {
    $block = @"

Host $Alias
    HostName $HostName
    User $User
    IdentityFile $($KeyPath -replace '\\', '/')
    IdentitiesOnly yes
    ServerAliveInterval 30
"@
    Add-Content -Path $cfg -Value $block -Encoding utf8NoBOM
    Ok "added Host $Alias"
}

# --- 4. prove it ------------------------------------------------------------
Step '4. Key-only test'
$out = & ssh -o BatchMode=yes $Alias 'echo PHOENIX_OK; hostname; . /etc/os-release; echo $PRETTY_NAME'
if ($LASTEXITCODE -or ($out -notcontains 'PHOENIX_OK')) { Fail "key auth failed — try: ssh -v $Alias" }
Ok "ssh $Alias works with no password -> $($out[1]) ($($out[2]))"

if (-not $AllowReverse) {
    Write-Host "`nDone. Now on the Pavilion:  sudo bash pavilion-setup.sh --harden   (turns password SSH off)"
    Write-Host 'To let the Pavilion SSH into this PC too, re-run from an elevated PS7 with -AllowReverse.'
    exit 0
}

# --- 5. Windows OpenSSH server ---------------------------------------------
Step '5. OpenSSH Server on this PC'
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) { Fail '-AllowReverse needs an elevated PS7 (Run as administrator).' }

$cap = Get-WindowsCapability -Online -Name 'OpenSSH.Server*'
if ($cap.State -ne 'Installed') {
    Add-WindowsCapability -Online -Name $cap.Name | Out-Null
    Ok 'installed OpenSSH Server'
}
Set-Service sshd -StartupType Automatic
Start-Service sshd
Ok 'sshd running, starts at boot'
if (-not (Get-NetFirewallRule -Name 'OpenSSH-Server-In-TCP' -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -Name 'OpenSSH-Server-In-TCP' -DisplayName 'OpenSSH Server (sshd)' `
        -Enabled True -Direction Inbound -Protocol TCP -LocalPort 22 -Action Allow -Profile Private, Domain | Out-Null
    Ok 'firewall rule added (Private/Domain profiles)'
}
$pwsh = (Get-Command pwsh).Source
New-ItemProperty -Path 'HKLM:\SOFTWARE\OpenSSH' -Name DefaultShell -Value $pwsh -PropertyType String -Force | Out-Null
Ok "default SSH shell: $pwsh"

# --- 6. authorize the Pavilion's key here ----------------------------------
Step '6. Authorize Pavilion -> Windows'
$revPub = (& ssh -o BatchMode=yes $Alias 'cat ~/.ssh/phoenix_pavilion_to_windows_ed25519.pub' | Out-String).Trim()
if ($LASTEXITCODE -or $revPub -notmatch '^ssh-ed25519 ') { Fail 'Pavilion key missing — re-run pavilion-setup.sh on the Pavilion' }

# Admin accounts ignore ~/.ssh/authorized_keys on Windows; sshd reads this file instead,
# and silently rejects it unless only SYSTEM + Administrators can touch it.
$akFile = Join-Path $env:ProgramData 'ssh\administrators_authorized_keys'
if (-not (Test-Path $akFile)) { New-Item -ItemType File -Path $akFile -Force | Out-Null }
if (-not (Select-String -Path $akFile -SimpleMatch $revPub -Quiet)) {
    Add-Content -Path $akFile -Value $revPub -Encoding utf8NoBOM
}
& icacls.exe $akFile /inheritance:r /grant '*S-1-5-32-544:F' /grant '*S-1-5-18:F' | Out-Null
if ($LASTEXITCODE) { Fail "icacls failed on $akFile" }
Ok "Pavilion key authorized in $akFile"

# --- 7. tell the Pavilion how to reach us ----------------------------------
Step '7. Pavilion ~/.ssh/config'
$route = Get-NetRoute -DestinationPrefix '0.0.0.0/0' | Sort-Object RouteMetric | Select-Object -First 1
$myIp = (Get-NetIPAddress -InterfaceIndex $route.InterfaceIndex -AddressFamily IPv4 | Select-Object -First 1).IPAddress
$winAlias = $env:COMPUTERNAME.ToLower()
$winUser = $env:USERNAME
$remoteCfg = @"
grep -qiE '^Host[[:space:]]+$winAlias\$' ~/.ssh/config 2>/dev/null || { printf '\nHost %s\n    HostName %s\n    User %s\n    IdentityFile ~/.ssh/phoenix_pavilion_to_windows_ed25519\n    IdentitiesOnly yes\n' '$winAlias' '$myIp' '$winUser' >> ~/.ssh/config; chmod 600 ~/.ssh/config; }
"@
& ssh -o BatchMode=yes $Alias $remoteCfg
if ($LASTEXITCODE) { Fail 'could not update the Pavilion ~/.ssh/config' }
Ok "Pavilion now knows 'ssh $winAlias' -> $winUser@$myIp"

Write-Host "`nLast check, from the Pavilion:  ssh $winAlias hostname"
Write-Host 'Then on the Pavilion:          sudo bash pavilion-setup.sh --harden'
