# radar.Tests.ps1 — the Radar CLI against a stand-in worker fed real-shaped rows.
#   pwsh -NoProfile -File scripts/radar.Tests.ps1
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'radar.ps1')
$ErrorActionPreference = 'Continue'
$p = 0; $f = 0
function ok($c, $m) { if ($c) { $script:p++; Write-Host "  ok   $m" } else { $script:f++; Write-Host "  FAIL $m" -ForegroundColor Red } }

# Rows copied from the live pbm_radar_db (2026-10-03), emails left out.
$sub = [pscustomobject]@{ id = 1; name = 'PBM'; email = 'x'; naics = '["238120","236220","541611"]'; states = '[]'; active = 1; billing = 'beta' }
$match = [pscustomobject]@{ title = 'Z2DA--589A7-23-306 Renovate Bldg. 5 & 5B for Mental Health FY27  NRM'; agency = 'VETERANS AFFAIRS, DEPARTMENT OF'
    response_deadline = '2026-10-19T14:00:00-04:00'; naics = '236220'; set_aside_desc = 'Service-Disabled Veteran-Owned Small Business (SDVOSB) Set-Aside (FAR 19.14)'
    pop_state = 'KS'; pop_city = 'Wichita'; ui_link = 'https://sam.gov/workspace/contract/opp/459138cd774548afa5f8b23e26eed220/view' }
$global:calls = [System.Collections.Generic.List[string]]::new(); $global:deny = $false
$global:PhxRadarHttp = {
    param($Path) $global:calls.Add($Path)
    if ($global:deny) { $r = [Net.Http.HttpResponseMessage]::new([Net.HttpStatusCode]::Unauthorized); throw [Microsoft.PowerShell.Commands.HttpResponseException]::new('401', $r) }
    if ($Path -eq '/subscribers') { return [pscustomobject]@{ ok = $true; subscribers = @($sub) } }
    if ($Path -like '/preview*') { $d = ($Path -split 'date=')[1]; return [pscustomobject]@{ ok = $true; date = $d; matched = 1; matches = @($match) } }
    if ($Path -eq '/runs') { return [pscustomobject]@{ ok = $true; runs = @([pscustomobject]@{ run_date = '2026-10-02'; posted_date = '2026-10-01'; notices_seen = 1000; set_asides_kept = 490; matches_json = '[{"a":1},{"b":2}]'; dry = 0; error = $null }) } }
}

$out = (radar new 6>&1 | Out-String)
ok ($out -match 'Renovate Bldg\. 5' -and $out -match 'due Mon Oct 19' -and $out -match 'Wichita, KS' -and $out -match 'sam\.gov/workspace') 'radar new: title, deadline, place and the SAM link'
$y = (Get-PhxRadarToday).AddDays(-1).ToString('yyyy-MM-dd')
ok ($global:calls -contains "/preview?subscriber=1&date=$y") "radar new asks for yesterday's postings ($y), what this morning's email covered"
$global:calls.Clear(); $null = (radar week pbm 6>&1 | Out-String)
ok (@($global:calls | Where-Object { $_ -like '/preview*' }).Count -eq 7) 'radar week <client>: seven days, matched by name'
$out = (radar new nobody 6>&1 | Out-String)
ok ($out -match "no active client matches 'nobody'") 'an unknown client says so plainly'
$out = (radar clients | Out-String)
ok ($out -match 'PBM' -and $out -match 'active' -and $out -match '238120, 236220, 541611' -and $out -match 'anywhere') 'radar clients: name, status, NAICS, states'
$out = (radar runs | Out-String)
ok ($out -match '2026-10-02' -and $out -match 'notices  1000' -and $out -match 'matches   2') 'radar runs: the daily run and what it found'
$global:deny = $true; $out = (radar clients 3>&1 | Out-String)
ok ($out -match 'refused PHOENIX_AUTH') 'a rejected key is reported in plain words'
Write-Host "`n$p passing, $f failing"; exit ([int]($f -gt 0))
