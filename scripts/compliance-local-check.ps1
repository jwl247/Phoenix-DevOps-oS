#!/usr/bin/env pwsh
# =============================================================================
# compliance-local-check.ps1 — the local half of the ongoing compliance
# agent. The cloud routine (RemoteTrigger "Phoenix Compliance — Monthly
# Ongoing Assessment") reviews the repo's compliance docs monthly, but it
# runs in an isolated cloud sandbox with zero access to this machine — it
# can never re-run Get-MpComputerStatus. This script is the piece that
# actually can, and does, on a schedule (see
# install-compliance-check-autostart.ps1).
#
# What it checks, matching the specific claims already written into
# docs/compliance/FAR-52.204-21-compliance.md (controls #13-15):
#   - Windows Defender real-time protection enabled
#   - Signatures updated within the last 7 days
#   - On-access / behavior-monitor scanning enabled
#
# Logs every run (pass or fail) to a local JSONL file — never committed to
# the repo, since this is machine-specific security telemetry, not project
# history. Only pops a visible alert when something's actually wrong, so a
# clean weekly run stays silent.
# =============================================================================

$ErrorActionPreference = 'Stop'
$LogDir  = Join-Path $env:USERPROFILE '.unitedsys\logs'
$LogFile = Join-Path $LogDir 'compliance-check.jsonl'
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

function Write-CheckLog {
    param([bool]$Ok, [string[]]$Issues, [hashtable]$Status)
    $entry = [ordered]@{
        at       = (Get-Date).ToString('o')
        ok       = $Ok
        issues   = $Issues
        status   = $Status
    } | ConvertTo-Json -Compress
    Add-Content -Path $LogFile -Value $entry
}

$issues = @()
$status = @{}

try {
    $mp = Get-MpComputerStatus -ErrorAction Stop
    $status.AntivirusEnabled        = $mp.AntivirusEnabled
    $status.RealTimeProtectionEnabled = $mp.RealTimeProtectionEnabled
    $status.BehaviorMonitorEnabled   = $mp.BehaviorMonitorEnabled
    $status.OnAccessProtectionEnabled = $mp.OnAccessProtectionEnabled
    $status.AntivirusSignatureLastUpdated = $mp.AntivirusSignatureLastUpdated.ToString('o')

    if (-not $mp.AntivirusEnabled) { $issues += 'Antivirus is disabled' }
    if (-not $mp.RealTimeProtectionEnabled) { $issues += 'Real-time protection is disabled' }
    if (-not $mp.BehaviorMonitorEnabled) { $issues += 'Behavior monitoring is disabled' }
    if (-not $mp.OnAccessProtectionEnabled) { $issues += 'On-access scanning is disabled' }

    $sigAge = (Get-Date) - $mp.AntivirusSignatureLastUpdated
    $status.SignatureAgeDays = [math]::Round($sigAge.TotalDays, 1)
    if ($sigAge.TotalDays -gt 7) { $issues += "Antivirus signatures are $([math]::Round($sigAge.TotalDays,1)) days old (>7)" }
} catch {
    $issues += "Could not query Get-MpComputerStatus: $($_.Exception.Message)"
}

$ok = ($issues.Count -eq 0)
Write-CheckLog -Ok $ok -Issues $issues -Status $status

if (-not $ok) {
    $msg = "Phoenix compliance check found an issue:`n`n" + ($issues -join "`n") + "`n`nThis matches claims in docs/compliance/FAR-52.204-21-compliance.md — that document may need updating, or this needs fixing on this machine."
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show($msg, 'Phoenix Compliance Check — Action Needed', 'OK', 'Warning') | Out-Null
    exit 1
}

exit 0
