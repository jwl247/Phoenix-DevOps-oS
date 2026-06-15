# wireguard-windows-setup.ps1 — Phoenix WireGuard Windows setup
# Run as Administrator in PowerShell
# =============================================================================

$ErrorActionPreference = "Stop"

Write-Host "`n[Phoenix WireGuard] Windows setup`n" -ForegroundColor Cyan

# ── 1. Firewall rule — allow WireGuard inbound UDP 51820 ─────────────────────
Write-Host "[1] Firewall rule..." -ForegroundColor Yellow

$ruleName = "Phoenix-WireGuard-UDP-51820"
$existing = Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue

if ($existing) {
    Write-Host "    Already exists — removing and re-adding clean" -ForegroundColor Gray
    Remove-NetFirewallRule -Name $ruleName
}

New-NetFirewallRule `
    -Name        $ruleName `
    -DisplayName "Phoenix WireGuard (UDP 51820)" `
    -Description "Self-hosted WireGuard mesh for Phoenix DevOps" `
    -Protocol    UDP `
    -LocalPort   51820 `
    -Direction   Inbound `
    -Action      Allow `
    -Profile     Any | Out-Null

Write-Host "    [OK] Firewall rule created" -ForegroundColor Green

# ── 2. Check if WireGuard service is running ──────────────────────────────────
Write-Host "[2] WireGuard service..." -ForegroundColor Yellow

$wgSvc = Get-Service -Name "WireGuardTunnel*" -ErrorAction SilentlyContinue
if ($wgSvc) {
    Write-Host "    [OK] WireGuard tunnel service found: $($wgSvc.Name)" -ForegroundColor Green
} else {
    Write-Host "    [!!] No WireGuard tunnel service — is the tunnel activated in the WireGuard app?" -ForegroundColor Red
}

# ── 3. Check WireGuard adapter ────────────────────────────────────────────────
Write-Host "[3] WireGuard adapter..." -ForegroundColor Yellow

$wgAdapter = Get-NetAdapter | Where-Object { $_.InterfaceDescription -like "*WireGuard*" }
if ($wgAdapter) {
    Write-Host "    [OK] Adapter: $($wgAdapter.Name) — Status: $($wgAdapter.Status)" -ForegroundColor Green
} else {
    Write-Host "    [!!] No WireGuard adapter found — activate the tunnel in the WireGuard app first" -ForegroundColor Red
}

# ── 4. Surfshark conflict check ───────────────────────────────────────────────
Write-Host "[4] Surfshark conflict check..." -ForegroundColor Yellow

$ssAdapter = Get-NetAdapter | Where-Object { $_.InterfaceDescription -like "*Surfshark*" -or $_.Name -like "*Surfshark*" }
if ($ssAdapter -and $ssAdapter.Status -eq "Up") {
    Write-Host "    [!!] Surfshark is UP — may conflict with WireGuard routing" -ForegroundColor Red
    Write-Host "         Option A: Disconnect Surfshark while testing WireGuard" -ForegroundColor Yellow
    Write-Host "         Option B: Enable Surfshark split-tunnel, exclude 10.77.0.0/24" -ForegroundColor Yellow
} else {
    Write-Host "    [OK] Surfshark not interfering" -ForegroundColor Green
}

# ── 5. Route check ────────────────────────────────────────────────────────────
Write-Host "[5] Route to 10.77.0.0/24..." -ForegroundColor Yellow

$route = Get-NetRoute -DestinationPrefix "10.77.0.0/24" -ErrorAction SilentlyContinue
if ($route) {
    Write-Host "    [OK] Route exists via $($route.NextHop) on $($route.InterfaceAlias)" -ForegroundColor Green
} else {
    Write-Host "    [!!] No route to 10.77.0.0/24 — tunnel may not be active" -ForegroundColor Red
}

# ── 6. Ping self on VPN ───────────────────────────────────────────────────────
Write-Host "[6] Ping 10.77.0.1 (self on VPN)..." -ForegroundColor Yellow

$ping = Test-Connection -ComputerName 10.77.0.1 -Count 2 -Quiet -ErrorAction SilentlyContinue
if ($ping) {
    Write-Host "    [OK] 10.77.0.1 responds" -ForegroundColor Green
} else {
    Write-Host "    [!!] 10.77.0.1 not responding — tunnel not active or adapter missing" -ForegroundColor Red
}

# ── Summary ───────────────────────────────────────────────────────────────────
Write-Host "`n[Phoenix WireGuard] Done.`n" -ForegroundColor Cyan
Write-Host "If tunnel still won't connect after this script:" -ForegroundColor White
Write-Host "  1. Open WireGuard app → click Activate on wg0" -ForegroundColor Gray
Write-Host "  2. Disconnect Surfshark, test WireGuard alone" -ForegroundColor Gray
Write-Host "  3. Check router — forward UDP 51820 → 192.168.1.100" -ForegroundColor Gray
Write-Host "  4. Run: wg show   (in cmd/PS after tunnel activates)" -ForegroundColor Gray
