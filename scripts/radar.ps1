#Requires -Version 7.0
<#
.SYNOPSIS
    radar.ps1 — Set-Aside Radar from the desktop or the command line.

.DESCRIPTION
    radar new [client]      the bids in this morning's email (yesterday's postings), per client
    radar week [client]     the last 7 days of matches for a client (or every active client)
    radar clients           who is subscribed: NAICS, states, billing
    radar runs              did the daily run go out, and what did it find

    [client] is a subscriber id or part of a name or email. Read-only: nothing here
    sends mail, changes a subscriber or charges anyone.

    Talks to the live Radar worker's admin routes (/subscribers, /preview, /runs) with
    PHOENIX_AUTH, read from the environment (Windows User scope too) or
    ~/.phoenix/kernel.env, same as the universal kernel. Keys never go on a command line.
    RADAR_WORKER_URL overrides the address.

.NOTES
    UnitedSys — United Systems | jwl247 | GPL-3.0 | PBM Consulting Service
#>

$global:PhxRadar = @{ Url = 'https://pbm-radar-worker.phoenix-jwl.workers.dev' }

function global:Get-PhxRadarKey([string]$Name) {
    $v = [Environment]::GetEnvironmentVariable($Name)
    if (-not $v -and $IsWindows) { $v = [Environment]::GetEnvironmentVariable($Name, 'User') }
    if (-not $v) {
        $f = Join-Path $HOME '.phoenix/kernel.env'
        if (Test-Path -LiteralPath $f) {
            foreach ($line in Get-Content -LiteralPath $f) {
                if ($line -match "^\s*$([regex]::Escape($Name))\s*=\s*(.+?)\s*$") { $v = $Matches[1].Trim('"', "'"); break }
            }
        }
    }
    return $v
}

# One seam for every call, so the tests can stand in for the worker.
$global:PhxRadarHttp = {
    param([string]$Path)
    $base = Get-PhxRadarKey 'RADAR_WORKER_URL'; if (-not $base) { $base = $global:PhxRadar.Url }
    $auth = Get-PhxRadarKey 'PHOENIX_AUTH'
    if (-not $auth) { throw 'PHOENIX_AUTH is not set (environment, or ~/.phoenix/kernel.env)' }
    $h = @{ Authorization = "Bearer $auth"; 'User-Agent' = 'phoenix-radar-cli/1' }
    if ($i = Get-PhxRadarKey 'CF_ACCESS_CLIENT_ID')     { $h['CF-Access-Client-Id'] = $i }
    if ($s = Get-PhxRadarKey 'CF_ACCESS_CLIENT_SECRET') { $h['CF-Access-Client-Secret'] = $s }
    Invoke-RestMethod -Uri ($base.TrimEnd('/') + $Path) -Headers $h -TimeoutSec 30 -ErrorAction Stop
}

# Radar runs on Chicago time; its morning email covers the previous day's postings.
function global:Get-PhxRadarToday {
    foreach ($id in 'America/Chicago', 'Central Standard Time') {
        try { return [TimeZoneInfo]::ConvertTime([DateTime]::UtcNow, [TimeZoneInfo]::FindSystemTimeZoneById($id)).Date } catch { }
    }
    return [DateTime]::UtcNow.AddHours(-6).Date
}

function global:Get-PhxRadarClients([string]$Who) {
    $subs = @((& $global:PhxRadarHttp '/subscribers').subscribers)
    if (-not $Who) { return @($subs | Where-Object { $_.active -eq 1 }) }
    if ($Who -match '^\d+$') { return @($subs | Where-Object { $_.id -eq [int]$Who }) }
    return @($subs | Where-Object { "$($_.name) $($_.email)" -like "*$Who*" })
}

function global:Format-PhxRadarList($v) {
    try { $x = if ($v -is [string]) { $v | ConvertFrom-Json } else { $v }; return (@($x) -join ', ') } catch { return "$v" }
}

function global:Show-PhxRadarMatches($Client, [datetime[]]$Days) {
    $label = if ($Client.name) { $Client.name } else { $Client.email }
    $all = foreach ($d in $Days) {
        $r = & $global:PhxRadarHttp "/preview?subscriber=$($Client.id)&date=$($d.ToString('yyyy-MM-dd'))"
        foreach ($m in @($r.matches)) { $m | Add-Member -NotePropertyName posted -NotePropertyValue $r.date -Force -PassThru }
    }
    $all = @($all | Where-Object { $_ })
    Write-Host ''
    Write-Host "  $label  ·  NAICS $(Format-PhxRadarList $Client.naics)  ·  $(if ($Client.states -and (Format-PhxRadarList $Client.states)) { Format-PhxRadarList $Client.states } else { 'anywhere' })" -ForegroundColor Cyan
    if (-not $all.Count) { Write-Host '    nothing new matched' -ForegroundColor DarkGray; return @() }
    foreach ($m in ($all | Sort-Object response_deadline)) {
        $due = if ($m.response_deadline) { ([datetime]$m.response_deadline).ToString('ddd MMM d') } else { 'no deadline given' }
        $where = (@($m.pop_city, $m.pop_state) | Where-Object { $_ }) -join ', '
        Write-Host "    $($m.title)"
        Write-Host "      due $due · $($m.set_aside_desc) · NAICS $($m.naics) · $($m.agency)$(if ($where) { " · $where" })" -ForegroundColor DarkGray
        if ($m.ui_link) { Write-Host "      $($m.ui_link)" -ForegroundColor DarkGray }
    }
    return $all
}

function global:radar {
    $do = if ($args.Count) { "$($args[0])" } else { 'new' }
    $who = if ($args.Count -gt 1) { ($args | Select-Object -Skip 1) -join ' ' } else { '' }
    try {
        switch ($do) {
            { $_ -in 'new', 'today' } {
                $day = (Get-PhxRadarToday).AddDays(-1)
                $clients = Get-PhxRadarClients $who
                if (-not $clients) { Write-Host "  radar: no active client matches '$who' (radar clients)"; return }
                foreach ($c in $clients) { $null = Show-PhxRadarMatches $c @($day) }
            }
            'week' {
                $t = Get-PhxRadarToday; $days = 1..7 | ForEach-Object { $t.AddDays(-$_) }
                $clients = Get-PhxRadarClients $who
                if (-not $clients) { Write-Host "  radar: no active client matches '$who' (radar clients)"; return }
                foreach ($c in $clients) { $null = Show-PhxRadarMatches $c $days }
            }
            'clients' {
                foreach ($s in (& $global:PhxRadarHttp '/subscribers').subscribers) {
                    '{0,4}  {1,-26} {2,-8} {3,-6} NAICS {4}  ·  {5}' -f $s.id, $(if ($s.name) { $s.name } else { $s.email }),
                        $(if ($s.active -eq 1) { 'active' } else { 'stopped' }), $s.billing, (Format-PhxRadarList $s.naics),
                        $(if (Format-PhxRadarList $s.states) { Format-PhxRadarList $s.states } else { 'anywhere' })
                }
            }
            'runs' {
                foreach ($r in @((& $global:PhxRadarHttp '/runs').runs | Select-Object -First 10)) {
                    $n = 0; try { $n = @($r.matches_json | ConvertFrom-Json).Count } catch { }
                    '{0}  covered {1}  notices {2,5}  set-asides {3,4}  matches {4,3}{5}{6}' -f $r.run_date, $r.posted_date, $r.notices_seen,
                        $r.set_asides_kept, $n, $(if ($r.dry -eq 1) { '  (dry)' }), $(if ($r.error) { "  ERROR: $($r.error)" })
                }
            }
            default { Write-Host '  radar [new|week [client]|clients|runs]' }
        }
    } catch {
        $code = $_.Exception.Response.StatusCode.value__
        Write-Warning ("radar: " + $(if ($code -eq 401) { 'the worker refused PHOENIX_AUTH (rotated?)' } elseif ($code) { "the worker answered $code" } else { $_.Exception.Message }))
    }
}

if ($MyInvocation.InvocationName -ne '.') { radar @args }
