# usys-suite-gate.Tests.ps1 — execution gate (security audit T1 #1 + #3)
#   pwsh -File scripts/usys-suite-gate.Tests.ps1
# Standalone (no Pester). Dot-sources usys.ps1 and drives the gate functions
# against synthetic suites in a temp clonepool.

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'usys.ps1')
# usys.ps1's Write-UsysErr calls Write-Error; the gate returns $false and
# callers check that. Don't let a non-terminating error abort the harness.
$ErrorActionPreference = 'Continue'

$env:PHOENIX_AUTH = 'test-key-do-not-use'
Remove-Item Env:\PHOENIX_SUITE_NO_GATE -ErrorAction SilentlyContinue

$root = Join-Path ([IO.Path]::GetTempPath()) ("usysgate_" + [guid]::NewGuid().ToString('N').Substring(0, 8))
New-Item -ItemType Directory -Path $root -Force | Out-Null
$logf = Join-Path $root 'suite_exec.jsonl'
$env:PHOENIX_SUITE_EXEC_LOG = $logf

$p = 0; $f = 0
function ok($cond, $msg) {
    if ($cond) { $script:p++; Write-Host "  ok   $msg" }
    else { $script:f++; Write-Host "  FAIL $msg" -ForegroundColor Red }
}

function New-FakeSuite {
    param([string]$Name, [string]$Runtime, [string[]]$Perms, [string]$EntryBody = "print('hi')")
    $dir = Join-Path $root $Name
    New-Item -ItemType Directory -Path $dir -Force | Out-Null
    $entry = 'main.py'
    Set-Content -Path (Join-Path $dir $entry) -Value $EntryBody -Encoding UTF8 -NoNewline
    $manifest = [pscustomobject]@{
        name = $Name; version = '1.0.0'; type = 'script'
        entry = $entry; runtime = $Runtime; permissions = $Perms
    }
    [pscustomobject]@{ Name = $Name; Version = '1.0.0'; Runtime = $Runtime; Path = $dir; Manifest = $manifest }
}

function GateAllows { param($Suite, [switch]$Unverified)
    $ep = Join-Path $Suite.Path $Suite.Manifest.entry
    Assert-UsysSuiteExecutionAllowed -Suite $Suite -EntryPath $ep -Unverified:$Unverified 6>$null 2>$null
}

# 1. qemu runtime is VM-contained — passes with no stamp, even asking for network
$qemu = New-FakeSuite -Name 'vm1' -Runtime 'qemu' -Perms @('network', 'filesystem:write')
ok (GateAllows $qemu) 'qemu suite passes (VM-contained) unstamped'

# 2. host runtime, no elevated perms → allowed unstamped
$plain = New-FakeSuite -Name 'plain1' -Runtime 'python' -Perms @('filesystem:read')
ok (GateAllows $plain) 'host suite with only filesystem:read passes unstamped'

# 3. host runtime, declares network, unstamped, non-interactive, no -Unverified → REFUSED
$net = New-FakeSuite -Name 'net1' -Runtime 'python' -Perms @('network')
ok (-not (GateAllows $net)) 'unstamped host suite asking for network is REFUSED'

# 4. same suite with -Unverified → allowed
ok (GateAllows $net -Unverified) '-Unverified overrides the refusal'

# 5. trust-stamp it, then it passes without -Unverified
$stamp = Get-UsysSuiteStampValue -Manifest $net.Manifest -EntryPath (Join-Path $net.Path 'main.py')
ok ($stamp -and $stamp.Length -eq 64) 'stamp value is a 64-hex HMAC'
([ordered]@{ v = 1; algo = 'HMAC-SHA256'; stamp = $stamp } | ConvertTo-Json) |
    Set-Content (Join-Path $net.Path '.phoenix-trust') -Encoding UTF8
ok ((Test-UsysSuiteTrusted -Suite $net).Trusted) 'Test-UsysSuiteTrusted: valid stamp recognised'
ok (GateAllows $net) 'trust-stamped suite passes the gate'

# 6. tamper the entry file → stamp no longer verifies → refused
Add-Content -Path (Join-Path $net.Path 'main.py') -Value "`nimport os; os.system('curl evil')" -Encoding UTF8
ok (-not (Test-UsysSuiteTrusted -Suite $net).Trusted) 'tampered entry file invalidates the stamp'
ok (-not (GateAllows $net)) 'gate refuses after entry-file tamper'

# 7. global bypass
$env:PHOENIX_SUITE_NO_GATE = '1'
ok (GateAllows $net) 'PHOENIX_SUITE_NO_GATE=1 bypasses the gate'
Remove-Item Env:\PHOENIX_SUITE_NO_GATE

# 8. wrong PHOENIX_AUTH cannot verify a stamp made with the right one
$net2 = New-FakeSuite -Name 'net2' -Runtime 'binary' -Perms @('network', 'process:spawn')
$good = Get-UsysSuiteStampValue -Manifest $net2.Manifest -EntryPath (Join-Path $net2.Path 'main.py')
([ordered]@{ v = 1; stamp = $good } | ConvertTo-Json) | Set-Content (Join-Path $net2.Path '.phoenix-trust') -Encoding UTF8
$saved = $env:PHOENIX_AUTH; $env:PHOENIX_AUTH = 'a-different-key'
ok (-not (Test-UsysSuiteTrusted -Suite $net2).Trusted) 'stamp from a different PHOENIX_AUTH does not verify'
$env:PHOENIX_AUTH = $saved

# 9. audit log written
ok (Test-Path $logf) 'suite_exec.jsonl created'
$rows = Get-Content $logf | Where-Object { $_.Trim() } | ForEach-Object { $_ | ConvertFrom-Json }
ok ($rows.Count -ge 6) "audit log has decisions ($($rows.Count) rows)"
ok (($rows | Where-Object { $_.decision -eq 'refused' }).Count -ge 2) 'refusals are logged'
ok (($rows | Where-Object { $_.gated_by -eq 'trust-stamp' }).Count -ge 1) 'trust-stamp allows are logged'
ok (($rows | Where-Object { $_.gated_by -eq 'vm-contained' }).Count -ge 1) 'vm-contained passes are logged'

Write-Host ""
Write-Host "$p passed, $f failed" -ForegroundColor $(if ($f) { 'Red' } else { 'Green' })
Remove-Item Env:\PHOENIX_SUITE_EXEC_LOG -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force $root -ErrorAction SilentlyContinue
exit ($(if ($f) { 1 } else { 0 }))
