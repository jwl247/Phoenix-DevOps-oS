# phx-kernel.Tests.ps1 — the universal kernel's decisions, against a stand-in pool.
#   pwsh -NoProfile -File scripts/phx-kernel.Tests.ps1
# Standalone (no Pester), same style as usys-suite-gate.Tests.ps1. No network:
# the kernel's one HTTP seam ($global:PhxKHttp) is replaced by a folder that
# plays R2 (bytes) + D1 (meta rows). Nothing outside a temp folder is touched.

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'phx-kernel.ps1')
$ErrorActionPreference = 'Continue'
$WarningPreference = 'SilentlyContinue'

$root = Join-Path ([IO.Path]::GetTempPath()) ("phxk_" + [guid]::NewGuid().ToString('N').Substring(0, 8))
$global:PhxK.Home = Join-Path $root 'kernel'
$global:PhxK.Cache = Join-Path $global:PhxK.Home 'cache'
$global:PhxK.Approved = Join-Path $global:PhxK.Home 'approved.json'
$global:PhxK.Log = Join-Path $global:PhxK.Home 'log.jsonl'
$pool = Join-Path $root 'pool'; New-Item -ItemType Directory -Path $pool -Force | Out-Null

$p = 0; $f = 0
function ok($cond, $msg) { if ($cond) { $script:p++; Write-Host "  ok   $msg" } else { $script:f++; Write-Host "  FAIL $msg" -ForegroundColor Red } }

# ── the stand-in pool ──────────────────────────────────────────────────────
$global:calls = [Collections.Generic.List[string]]::new()
$global:offline = $false
$global:rows = @{}                                   # hex -> D1 row
function Add-PoolFile([string]$Name, [string]$Body, [string]$RecordedSha3 = '') {
    $hex = ConvertTo-PhxKHex $Name
    $file = Join-Path $pool $hex
    Set-Content -LiteralPath $file -Value $Body -NoNewline -Encoding utf8
    $sha = if ($RecordedSha3) { $RecordedSha3 } else { Get-PhxKSha3 $file }
    $global:rows[$hex] = [pscustomobject]@{ name = $Name; hex_id = $hex; hash_sha3 = $sha; version = 'v3' }
}
function New-Http404 { $r = [Net.Http.HttpResponseMessage]::new([Net.HttpStatusCode]::NotFound); [Microsoft.PowerShell.Commands.HttpResponseException]::new('404', $r) }
$global:PhxKHttp = {
    param([string]$Path, [string]$OutFile)
    $global:calls.Add($Path)
    if ($global:offline) { throw [Net.Http.HttpRequestException]::new('no route to host') }
    if ($Path -notmatch '^/clonepool/([0-9a-f]+)(\?meta=true)?$') { throw (New-Http404) }
    $hex = $Matches[1]
    if (-not $global:rows.ContainsKey($hex)) { throw (New-Http404) }
    if ($Matches[2]) { return [pscustomobject]@{ ok = $true; result = $global:rows[$hex] } }
    Copy-Item -LiteralPath (Join-Path $pool $hex) -Destination $OutFile -Force
}
$global:answer = 'y'
function global:Read-Host { param($Prompt) $global:asked++; return $global:answer }
function Reset-Calls { $global:calls.Clear(); $global:asked = 0 }

# ── 1. identity + fingerprint ──────────────────────────────────────────────
ok ((ConvertTo-PhxKHex 'intake.sh') -eq '696e74616b652e7368') "hex id = intake.sh's to_hex (xxd -p of the name)"

$vecDir = Join-Path $root 'vec'; New-Item -ItemType Directory -Path $vecDir -Force | Out-Null
$rng = [Random]::new(7)
$cases = [ordered]@{ empty = [byte[]]@(); abc = [Text.Encoding]::ASCII.GetBytes('abc'); rate71 = [byte[]]::new(71); rate72 = [byte[]]::new(72); rate73 = [byte[]]::new(73) }
$big = [byte[]]::new(1048583); $rng.NextBytes($big); $cases['1MiB+7'] = $big
$known = @{ empty = 'a69f73cca23a9ac5c8b567dc185a756e97c982164fe25859e0d1dcc1475c80a615b2123af1f5f94c11e3e9402c3ac558f500199d95b6d3e301758586281dcd26'
            abc   = 'b751850b1a57168a5693cd924b6b096e08f621827444f70d884f5d0240d2712e10e116e9192af3c91a7ec57647e3934057340b4cf408d5a56592f8274eec53f0' }
$py = (Get-Command python3, python -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1).Source
foreach ($k in $cases.Keys) {
    $file = Join-Path $vecDir $k; [IO.File]::WriteAllBytes($file, $cases[$k])
    $port = Get-PhxKSha3 $file -Portable
    $want = if ($known[$k]) { $known[$k] } elseif ($py) { & $py -c 'import hashlib,sys;print(hashlib.sha3_512(open(sys.argv[1],"rb").read()).hexdigest())' $file } else { Get-PhxKSha3 $file }
    ok ($port -eq $want) "portable SHA3-512 is correct: $k"
    if ([Security.Cryptography.SHA3_512]::IsSupported) { ok ((Get-PhxKSha3 $file) -eq $port) "native and portable agree: $k" }
}

# ── 2. which names it will even look at ────────────────────────────────────
Reset-Calls
ok ($null -eq (Resolve-PhxKCommand 'meshd' 'Internal')) "a script's missing command is not ours (origin Internal)"
ok ($null -eq (Resolve-PhxKCommand 'get-meshd' 'Runspace')) "PowerShell's own get-<name> probe is skipped"
ok ($null -eq (Resolve-PhxKCommand 'xy' 'Runspace')) 'two-letter names (typos) are skipped'
ok ($null -eq (Resolve-PhxKCommand '..\evil' 'Runspace')) 'names with path characters are refused'
ok ($global:calls.Count -eq 0) 'none of those touched the network'

# ── 3. first run: ask, pull, verify, approve, run ──────────────────────────
Add-PoolFile 'hello-phx.ps1' 'param($Who) "hello $Who from the pool"'
Reset-Calls
$hit = Resolve-PhxKCommand 'hello-phx' 'Runspace'
ok ($hit -and $hit.name -eq 'hello-phx.ps1' -and -not $hit.approved) 'found in the pool by name (hello-phx -> hello-phx.ps1)'
$out = Invoke-PhxKCommand $hit @('Jerry')
ok ($out -eq 'hello Jerry from the pool') "ran it with its arguments: '$out'"
ok ($global:asked -eq 1) 'asked once before the first run'
ok ((Get-PhxKApproved).ContainsKey('hello-phx.ps1')) 'approval recorded with its fingerprint'

# ── 4. second run: cache, no question, no network ──────────────────────────
Reset-Calls; $global:offline = $true
$hit = Resolve-PhxKCommand 'hello-phx' 'Runspace'
$out = Invoke-PhxKCommand $hit @('Laurie')
ok ($out -eq 'hello Laurie from the pool' -and $global:asked -eq 0 -and $global:calls.Count -eq 0) 'second run: from the cache, offline, no prompt'

# ── 5. tampered cache never runs ───────────────────────────────────────────
$cached = Join-Path $global:PhxK.Cache (Join-Path (ConvertTo-PhxKHex 'hello-phx.ps1') 'hello-phx.ps1')
Add-Content -LiteralPath $cached -Value '; "tampered"'
Reset-Calls; $global:offline = $true
ok ($null -eq (Resolve-PhxKCommand 'hello-phx' 'Runspace')) 'edited cache file is not run (offline: nothing at all)'
$global:offline = $false; $global:PhxK.Misses.Clear(); Reset-Calls
$hit = Resolve-PhxKCommand 'hello-phx' 'Runspace'
ok ($hit -and -not $hit.approved) 'online: goes back to the pool and must be approved again'

# ── 6. R2 bytes that don't match D1 custody are refused ────────────────────
Add-PoolFile 'evil-phx.ps1' '"I am not what D1 recorded"' -RecordedSha3 ('0' * 128)
Reset-Calls
$hit = Resolve-PhxKCommand 'evil-phx' 'Runspace'
$out = Invoke-PhxKCommand $hit @()
ok ($null -eq $out -and -not (Get-PhxKApproved).ContainsKey('evil-phx.ps1')) 'mismatched bytes: refused, not approved, not run'
ok (-not (Get-ChildItem -LiteralPath $global:PhxK.Cache -Recurse -File | Where-Object Name -like 'evil-phx*')) 'mismatched bytes: nothing left in the cache'

# ── 7. a "no" means nothing is kept ────────────────────────────────────────
Add-PoolFile 'maybe-phx.ps1' '"ran"'
$global:answer = 'n'; Reset-Calls
$out = Invoke-PhxKCommand (Resolve-PhxKCommand 'maybe-phx' 'Runspace') @()
ok ($null -eq $out -and -not (Get-PhxKApproved).ContainsKey('maybe-phx.ps1')) 'declined: not pulled, not approved'
$global:answer = 'y'

# ── 8. misses + offline stay quiet and cheap ───────────────────────────────
Reset-Calls
ok ($null -eq (Resolve-PhxKCommand 'nosuchtool' 'Runspace')) 'not in the pool: plain PowerShell error'
$n = $global:calls.Count
ok ($null -eq (Resolve-PhxKCommand 'nosuchtool' 'Runspace') -and $global:calls.Count -eq $n) 'a miss is remembered (no second lookup for 10 min)'
$global:offline = $true; Reset-Calls
ok ($null -eq (Resolve-PhxKCommand 'anothertool' 'Runspace') -and $global:calls.Count -eq 1) 'offline: one failed try, then gives up quietly'
$global:offline = $false

# ── 9. runtimes ────────────────────────────────────────────────────────────
Add-PoolFile 'py-phx.py' 'import sys; print("py says", *sys.argv[1:])'
if ($py) {
    Reset-Calls
    $out = Invoke-PhxKCommand (Resolve-PhxKCommand 'py-phx' 'Runspace') @('a', 'b')
    ok ($out -eq 'py says a b') "a .py runs with this machine's Python: '$out'"
}

# ── 10. bingo ──────────────────────────────────────────────────────────────
ok ((Get-Command bingo -ErrorAction SilentlyContinue).CommandType -eq 'Function') 'bingo is the management command'
$listed = bingo list
ok (($listed -join "`n") -match 'hello-phx\.ps1') "bingo list shows what's approved"
bingo forget hello-phx | Out-Null
ok (-not (Get-PhxKApproved).ContainsKey('hello-phx.ps1')) 'bingo forget drops the approval and the cache'

# ── 11. the closet: preload, then nothing is fetched at use time ──────────
$global:offline = $false; $global:PhxK.Misses.Clear()
Add-PoolFile 'suit-a.ps1' '"suit A ready"'
Add-PoolFile 'suit-b.ps1' '"suit B ready"'
Add-PoolFile 'suit-bad.ps1' '"tampered"' -RecordedSha3 ('f' * 128)
Reset-Calls
$r = Invoke-PhxKPreload @('suit-a', 'suit-b', 'suit-bad', 'not-in-pool', 'bingo')
ok ($global:asked -eq 1) 'preload asks once for the whole batch'
ok (($r.pulled -join ',') -eq 'suit-a.ps1,suit-b.ps1') "preload pulled and verified the good ones: $($r.pulled -join ', ')"
ok (($r.refused -join ',') -eq 'suit-bad.ps1' -and -not (Get-PhxKApproved).ContainsKey('suit-bad.ps1')) 'a bad file in the batch is refused and not approved'
ok (($r.missing -join ',') -eq 'not-in-pool' -and ($r.ready -contains 'bingo')) 'reports what the pool lacks and what is already here'
$global:offline = $true; Reset-Calls
$outA = Invoke-PhxKCommand (Resolve-PhxKCommand 'suit-a' 'Runspace') @()
$outB = Invoke-PhxKCommand (Resolve-PhxKCommand 'suit-b' 'Runspace') @()
ok ($outA -eq 'suit A ready' -and $outB -eq 'suit B ready' -and $global:calls.Count -eq 0 -and $global:asked -eq 0) 'after preload: both run offline, no network, no question'
Reset-Calls
$r2 = Invoke-PhxKPreload @('suit-a', 'suit-b')
ok ($global:asked -eq 0 -and $global:calls.Count -eq 0 -and $r2.ready.Count -eq 2) 'preloading again: already in the closet, nothing fetched'
$global:offline = $false

Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue
Write-Host "`n$p passing, $f failing"
exit ([int]($f -gt 0))
