#Requires -Version 7.2
# install-genie-cloud.ps1 — set up Phoenix Genie (cloud edition) on your machine, once.
# Phoenix DevOps OS | jwl247 | GPL v3
#
#   Where: your computer, PowerShell 7 (pwsh), in the folder you unzipped:
#     pwsh -File ./install-genie-cloud.ps1
#
# What it does (nothing else):
#   1. copies genie-cloud.ps1 to ~/Phoenix/genie-cloud.ps1
#   2. asks for your Phoenix key (typed hidden, never shown, never in a file you share)
#        Windows: saved as your user environment variable PHOENIX_AUTH
#        Linux/macOS: saved to ~/.config/phoenix/genie.env, readable only by you (0600)
#   3. adds one line to your PowerShell profile so every pwsh window has `genie`
#   4. checks it works: genie doctor
# Re-run it any time (new key, moved file). Undo: delete the profile line + ~/Phoenix/genie-cloud.ps1.
param(
    [string]$InstallDir  = (Join-Path $HOME 'Phoenix'),
    [string]$ProfilePath = $PROFILE.CurrentUserAllHosts,
    [string]$ConfigDir   = (Join-Path $HOME '.config/phoenix'),
    [securestring]$Key,             # testing: pass it instead of being asked
    [switch]$NoUserEnv              # testing: Windows keeps the key in ConfigDir like Linux, user env untouched
)
$ErrorActionPreference = 'Stop'
$src = Join-Path $PSScriptRoot 'genie-cloud.ps1'
if (-not (Test-Path $src)) { throw "genie-cloud.ps1 must sit next to this installer ($PSScriptRoot)" }

$dir  = $InstallDir
$dest = Join-Path $dir 'genie-cloud.ps1'
New-Item -ItemType Directory -Force -Path $dir | Out-Null
Copy-Item $src $dest -Force
Write-Host "  [1/4] genie -> $dest" -ForegroundColor Green

$sec = if ($Key) { $Key } else { Read-Host '  [2/4] Paste your Phoenix key (starts with phx_)' -AsSecureString }
$plain = [Net.NetworkCredential]::new('', $sec).Password.Trim()
if ($plain -notmatch '^phx_[A-Za-z0-9_-]{20,}$') { throw 'That does not look like a Phoenix key (phx_...). Nothing saved.' }
$envFile = $null
if ($IsWindows -and -not $NoUserEnv) {
    [Environment]::SetEnvironmentVariable('PHOENIX_AUTH', $plain, 'User')
    Write-Host '        saved as your user variable PHOENIX_AUTH' -ForegroundColor Green
} else {
    $cfg = $ConfigDir
    New-Item -ItemType Directory -Force -Path $cfg | Out-Null
    if (-not $IsWindows) { & chmod 700 $cfg }
    $envFile = Join-Path $cfg 'genie.env'
    Set-Content -Path $envFile -Value '' -NoNewline
    if (-not $IsWindows) { & chmod 600 $envFile }           # locked BEFORE the key goes in
    Set-Content -Path $envFile -Value "PHOENIX_AUTH=$plain" -NoNewline
    Write-Host "        saved to $envFile (only you can read it)" -ForegroundColor Green
}
$env:PHOENIX_AUTH = $plain

$profilePath = $ProfilePath
if (-not (Test-Path $profilePath)) { New-Item -ItemType File -Force -Path $profilePath | Out-Null }
$body = Get-Content $profilePath -Raw -ErrorAction SilentlyContinue
$lines = @()
if ($envFile) {
    $lines += "if (Test-Path '$envFile') { `$env:PHOENIX_AUTH = ((Get-Content '$envFile' -Raw) -replace '^PHOENIX_AUTH=', '').Trim() }   # Phoenix Genie key"
}
$lines += ". '$dest'   # Phoenix Genie"
if ($body -and $body -match [regex]::Escape('# Phoenix Genie')) {
    $kept = ($body -split "`r?`n") | Where-Object { $_ -notmatch '# Phoenix Genie' }
    Set-Content -Path $profilePath -Value (($kept + $lines) -join [Environment]::NewLine)
} else {
    Add-Content -Path $profilePath -Value ("`n" + ($lines -join [Environment]::NewLine))
}
Write-Host "  [3/4] profile: $profilePath" -ForegroundColor Green

Write-Host '  [4/4] checking...' -ForegroundColor Green
. $dest
genie doctor
Write-Host ''
Write-Host '  Done. Open a NEW PowerShell 7 window, then try:   genie tour' -ForegroundColor Cyan
Write-Host '  To put your own files in:  genie intake setup   (once), then  genie intake <file>' -ForegroundColor Cyan
