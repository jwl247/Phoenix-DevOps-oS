# push-dashboard.ps1 — Push Phoenix dashboard to Ubuntu over SSH and run installer
# Runs from PowerShell 7 on Windows. No WSL needed.
# Phoenix DevOps OS / jwl247 / GPL v3
#
# Usage:
#   .\push-dashboard.ps1                              # prompts for host/user
#   .\push-dashboard.ps1 -Host 192.168.1.133 -User jerry
#   .\push-dashboard.ps1 -Host 10.0.0.1 -User jerry  # WireGuard IP

param(
    [string]$UbuntuHost = "",
    [string]$UbuntuUser = "",
    [string]$RemoteRoot = "~/Phoenix/Phoenix-DevOps-oS"
)

$ErrorActionPreference = "Stop"

function ok($msg)  { Write-Host "  [OK] $msg" -ForegroundColor Green }
function hdr($msg) { Write-Host "`n-- $msg --" -ForegroundColor Cyan }
function die($msg) { Write-Host "  [FAIL] $msg" -ForegroundColor Red; exit 1 }

# ── Collect host/user if not passed ──────────────────────────────────────────
if (-not $UbuntuHost) { $UbuntuHost = Read-Host "Ubuntu IP (e.g. 192.168.1.133 or WireGuard IP)" }
if (-not $UbuntuUser) { $UbuntuUser = Read-Host "Ubuntu username" }

$Dest       = "${UbuntuUser}@${UbuntuHost}"
$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot   = (Resolve-Path "$ScriptDir\..\.." ).Path
$Dashboard  = "$RepoRoot\dashboard"
$Services   = "$RepoRoot\sector3\services"

hdr "Phoenix Dashboard → Ubuntu ($Dest)"
Write-Host "  Repo:    $RepoRoot"
Write-Host "  Remote:  $RemoteRoot"

# ── SSH check ─────────────────────────────────────────────────────────────────
hdr "SSH check"
$ping = ssh -o ConnectTimeout=8 -o BatchMode=yes $Dest "echo reachable" 2>&1
if ($LASTEXITCODE -ne 0) { die "Cannot reach $Dest — check SSH / WireGuard. Error: $ping" }
ok "SSH reachable"

# ── Scout first — show what's on the machine before touching anything ─────────
hdr "Scouting Ubuntu — inventory all repos and runtime"
$ScoutLocal = "$Services\scout-ubuntu.sh"
scp "$ScoutLocal" "${Dest}:~/scout-ubuntu.sh" | Out-Null
ssh $Dest "bash ~/scout-ubuntu.sh"

Write-Host ""
$confirm = Read-Host "Review the output above. Proceed with push? (y/n)"
if ($confirm -ne 'y') {
    Write-Host "Aborted. Paste the scout output to Claude to plan consolidation first." -ForegroundColor Yellow
    exit 0
}

# ── Create remote dirs ────────────────────────────────────────────────────────
hdr "Remote directories"
ssh $Dest "mkdir -p $RemoteRoot/dashboard $RemoteRoot/sector3/services"
ok "Remote dirs ready"

# ── Copy dashboard (scp -r, then wipe node_modules remotely) ─────────────────
hdr "Copying dashboard"
Write-Host "  Uploading dashboard files (node_modules installs fresh on Ubuntu)..."
scp -r "$Dashboard" "${Dest}:${RemoteRoot}/"
if ($LASTEXITCODE -ne 0) { die "scp failed on dashboard" }
# Remove Windows node_modules — Ubuntu will npm install its own
ssh $Dest "rm -rf $RemoteRoot/dashboard/node_modules"
ok "Dashboard copied"

# ── Copy sector3/services ─────────────────────────────────────────────────────
hdr "Copying services"
scp -r "$Services" "${Dest}:${RemoteRoot}/sector3/"
if ($LASTEXITCODE -ne 0) { die "scp failed on services" }
ssh $Dest "chmod +x $RemoteRoot/sector3/services/deploy-dashboard.sh $RemoteRoot/sector3/services/push-dashboard.sh 2>/dev/null || true"
ok "Services copied"

# ── Run deploy-dashboard.sh on Ubuntu ────────────────────────────────────────
hdr "Running deploy-dashboard.sh on Ubuntu"
Write-Host "  This installs Node, Electron, wires systemd, and starts the dashboard."
ssh -t $Dest "export PHOENIX_ROOT=$RemoteRoot && bash $RemoteRoot/sector3/services/deploy-dashboard.sh"
if ($LASTEXITCODE -ne 0) { die "deploy-dashboard.sh failed — check output above" }

# ── Install Claude Code on Ubuntu ────────────────────────────────────────────
hdr "Installing Claude Code on Ubuntu"
Write-Host "  Installing @anthropic-ai/claude-code so Claude is available system-wide..."
ssh $Dest "sudo npm install -g @anthropic-ai/claude-code 2>&1 | tail -5"
ok "Claude Code installed"

# ── Done ──────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "================================================================" -ForegroundColor Green
Write-Host "  Phoenix dashboard is live on $UbuntuHost" -ForegroundColor Green
Write-Host "================================================================" -ForegroundColor Green
Write-Host ""
Write-Host "  One more step — log Claude in on Ubuntu:"
Write-Host "    ssh $Dest" -ForegroundColor Yellow
Write-Host "    claude login" -ForegroundColor Yellow
Write-Host ""
Write-Host "  Dashboard logs:"
Write-Host "    ssh $Dest 'journalctl --user -u phoenix-dashboard -f'" -ForegroundColor Yellow
Write-Host ""
Write-Host "  Desktop boots via: phoenix-desktop.target (ollama + dashboard)"
Write-Host "  Windows autostart: .\sector3\services\install-dashboard-windows.ps1"
