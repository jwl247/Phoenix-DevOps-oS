#Requires -Version 7.2
# =============================================================================
# genie-cloud.ps1 — Phoenix Genie, cloud edition: R2 + D1 only.
# Phoenix DevOps OS | jwl247 | GPL v3
#
# Needs: PowerShell 7.2+, PHOENIX_AUTH (+ CF_ACCESS_CLIENT_ID/SECRET when
# packages-worker is behind Cloudflare Access). Nothing else: no kernel, no
# Python, no repo checkout. Works on any machine that can reach packages-worker.
#
#   . <path>\genie-cloud.ps1            then   genie help
#
# Everything goes through packages-worker (D1 phoenix_dev_db + R2 phoenix-clonepool),
# so the worker's auth, custody and version rules apply exactly as they do for intake.
#
# The full Genie (genie.ps1, kernel + closet + Helix) dot-sources THIS file for
# its cloud half, so there is one copy of the clone/verify/custody code.
#
# Rules it keeps
#   - Clone = OUT. Genie never writes to R2 or D1 (intake does that).
#   - A file whose bytes don't match its SHA3-512 custody baseline is never written.
#   - Keys come from the environment, go out as headers only: never printed,
#     never on a command line, never in a URL.
# =============================================================================

Set-StrictMode -Version Latest

$script:GenieWorker = if ($env:PHOENIX_WORKER_URL) { $env:PHOENIX_WORKER_URL.TrimEnd('/') } else { 'https://packages-worker.phoenix-jwl.workers.dev' }
$script:GenieHome   = if ($env:PHOENIX_GENIE_HOME) { $env:PHOENIX_GENIE_HOME } else { Join-Path $HOME '.phoenix/genie' }
$script:GenieCloset = Join-Path $script:GenieHome 'closet'
$script:GeniePoolCache = $null

function G-Ok   ([string]$m) { Write-Host "  [genie] $m" -ForegroundColor Green }
function G-Info ([string]$m) { Write-Host "  [genie] $m" -ForegroundColor Cyan }
function G-Warn ([string]$m) { Write-Host "  [genie] $m" -ForegroundColor Yellow }
function G-Err  ([string]$m) { Write-Host "  [genie] $m" -ForegroundColor Red }

# ── SHA3-512: OS crypto when it has it, otherwise a compiled Keccak (no Python) ──
if (-not ('Phoenix.GenieKeccak' -as [type])) {
    Add-Type -Language CSharp -TypeDefinition @'
namespace Phoenix {
  public static class GenieKeccak {
    static readonly ulong[] RC = {
      0x0000000000000001UL,0x0000000000008082UL,0x800000000000808AUL,0x8000000080008000UL,0x000000000000808BUL,0x0000000080000001UL,
      0x8000000080008081UL,0x8000000000008009UL,0x000000000000008AUL,0x0000000000000088UL,0x0000000080008009UL,0x000000008000000AUL,
      0x000000008000808BUL,0x800000000000008BUL,0x8000000000008089UL,0x8000000000008003UL,0x8000000000008002UL,0x8000000000000080UL,
      0x000000000000800AUL,0x800000008000000AUL,0x8000000080008081UL,0x8000000000008080UL,0x0000000080000001UL,0x8000000080008008UL };
    static readonly int[] ROT = { 0,1,62,28,27, 36,44,6,55,20, 3,10,43,25,39, 41,45,15,21,8, 18,2,61,56,14 };
    static ulong Rol(ulong v, int n) { return n == 0 ? v : (v << n) | (v >> (64 - n)); }
    static void F(ulong[] a) {
      ulong[] c = new ulong[5], b = new ulong[25];
      for (int r = 0; r < 24; r++) {
        for (int x = 0; x < 5; x++) c[x] = a[x] ^ a[x+5] ^ a[x+10] ^ a[x+15] ^ a[x+20];
        for (int x = 0; x < 5; x++) { ulong d = c[(x+4)%5] ^ Rol(c[(x+1)%5], 1); for (int y = 0; y < 25; y += 5) a[y+x] ^= d; }
        for (int x = 0; x < 5; x++) for (int y = 0; y < 5; y++) b[y + 5*((2*x + 3*y) % 5)] = Rol(a[x + 5*y], ROT[x + 5*y]);
        for (int y = 0; y < 25; y += 5) for (int x = 0; x < 5; x++) a[y+x] = b[y+x] ^ (~b[y+(x+1)%5] & b[y+(x+2)%5]);
        a[0] ^= RC[r];
      }
    }
    public static byte[] Sha3_512(byte[] data) {
      const int rate = 72; ulong[] a = new ulong[25];
      int off = 0;
      for (; off + rate <= data.Length; off += rate) { for (int i = 0; i < 9; i++) a[i] ^= System.BitConverter.ToUInt64(data, off + 8*i); F(a); }
      byte[] last = new byte[rate];
      System.Array.Copy(data, off, last, 0, data.Length - off);
      last[data.Length - off] ^= 0x06; last[rate - 1] ^= 0x80;
      for (int i = 0; i < 9; i++) a[i] ^= System.BitConverter.ToUInt64(last, 8*i);
      F(a);
      byte[] o = new byte[64];
      for (int i = 0; i < 8; i++) System.BitConverter.GetBytes(a[i]).CopyTo(o, 8*i);
      return o;
    }
  }
}
'@
}

function Get-GenieSha3([byte[]]$Bytes) {
    $h = if ([System.Security.Cryptography.SHA3_512]::IsSupported) { [System.Security.Cryptography.SHA3_512]::HashData($Bytes) }
         else { [Phoenix.GenieKeccak]::Sha3_512($Bytes) }      # BitConverter is little-endian on every PS7 platform
    return ([System.Convert]::ToHexString($h)).ToLowerInvariant()
}

# ── packages-worker ──────────────────────────────────────────────────────────
function Get-GenieHeaders {
    if (-not $env:PHOENIX_AUTH) { throw 'PHOENIX_AUTH is not set in this shell.' }
    $h = @{ Authorization = "Bearer $($env:PHOENIX_AUTH)" }
    if ($env:CF_ACCESS_CLIENT_ID -and $env:CF_ACCESS_CLIENT_SECRET) {
        $h['CF-Access-Client-Id']     = $env:CF_ACCESS_CLIENT_ID
        $h['CF-Access-Client-Secret'] = $env:CF_ACCESS_CLIENT_SECRET
    }
    return $h
}

function Invoke-GenieWorker([string]$PathAndQuery) {
    $r = Invoke-WebRequest -Uri ($script:GenieWorker + $PathAndQuery) -Headers (Get-GenieHeaders) `
             -SkipHttpErrorCheck -MaximumRedirection 0 -TimeoutSec 60 -ErrorAction Stop
    $ctype = [string]($r.Headers['Content-Type'] | Select-Object -First 1)
    if ($r.StatusCode -in 301, 302, 303, 307, 308 -or $ctype -match 'text/html') {
        throw "Cloudflare Access refused the request (HTTP $($r.StatusCode)) — check CF_ACCESS_CLIENT_ID / CF_ACCESS_CLIENT_SECRET."
    }
    if ($r.StatusCode -eq 401) { throw 'packages-worker said 401 unauthorized — PHOENIX_AUTH in this shell is wrong or stale.' }
    if ($r.StatusCode -ge 500) { throw "packages-worker error HTTP $($r.StatusCode)" }
    return $r
}

function Invoke-GenieWorkerPost([string]$Path, $Body) {
    $p = @{ Uri = $script:GenieWorker + $Path; Method = 'POST'; Headers = (Get-GenieHeaders); SkipHttpErrorCheck = $true
            MaximumRedirection = 0; TimeoutSec = 60; ErrorAction = 'Stop'; StatusCodeVariable = 'sc' }
    if ($null -ne $Body) { $p.Body = ($Body | ConvertTo-Json -Compress); $p.ContentType = 'application/json' }
    $r = Invoke-RestMethod @p
    if ($sc -eq 401) { throw 'packages-worker said 401 unauthorized — PHOENIX_AUTH in this shell is wrong or stale.' }
    if ($sc -ge 400) { throw "packages-worker refused (HTTP $sc): $(Get-GenieProp $r 'error')" }
    return $r
}

function Invoke-GenieJson([string]$PathAndQuery) {
    $r = Invoke-GenieWorker $PathAndQuery
    if ($r.StatusCode -eq 404) { return $null }
    $text = [System.Text.Encoding]::UTF8.GetString($r.RawContentStream.ToArray())
    if ($r.StatusCode -ge 400) {
        $why = try { ($text | ConvertFrom-Json).error } catch { $null }
        throw "packages-worker refused (HTTP $($r.StatusCode))$(if ($why) { ": $why" } else { " for $PathAndQuery" })"
    }
    return ($text | ConvertFrom-Json)
}

function Get-GeniePool([switch]$Refresh) {
    # GET /clonepool defaults to 100 rows — ask for all of them.
    if ($Refresh -or $null -eq $script:GeniePoolCache) {
        $script:GeniePoolCache = @((Invoke-GenieJson '/clonepool?limit=1000000').clonepool)
    }
    return $script:GeniePoolCache
}

function Get-GenieProp($Obj, [string]$Name) {
    if ($Obj -and $Obj.PSObject.Properties[$Name]) { return $Obj.$Name } else { return $null }
}

function Resolve-GenieRow([string]$Id) {
    # An exact hex_id is unambiguous. A name must name exactly one live row
    # (superseded rows are history); otherwise say which hex_ids to pick from.
    $pool = Get-GeniePool
    $hex = @($pool | Where-Object { $_.hex_id -eq $Id })
    if ($hex.Count -eq 1) { return $hex[0] }
    $byName = @($pool | Where-Object { $_.name -eq $Id })
    $live = @($byName | Where-Object { -not (Get-GenieProp $_ 'superseded_by') })
    $pick = @(if ($live.Count) { $live } else { $byName })
    if ($pick.Count -eq 1) { return $pick[0] }
    if ($pick.Count -gt 1) {
        throw ("'$Id' names $($pick.Count) rows — use a hex_id: " + (($pick | ForEach-Object {
            "$($_.hex_id) (v$(([string](Get-GenieProp $_ 'version')).TrimStart('v')), $(Get-GenieProp $_ 'source_path'))" }) -join '; '))
    }
    $near = @($pool | Where-Object { $_.name -like "*$Id*" } | Select-Object -First 8 | ForEach-Object name)
    throw ("'$Id' is not in the clonepool." + $(if ($near) { ' Did you mean: ' + ($near -join ', ') } else { '' }))
}

function Get-GenieBytes($Row) {
    $r = Invoke-GenieWorker "/clonepool/$([uri]::EscapeDataString($Row.hex_id))"
    $ctype = [string]($r.Headers['Content-Type'] | Select-Object -First 1)
    # The worker answers with the D1 row as JSON when R2 has no object for this hex.
    if ($r.StatusCode -ne 200 -or $ctype -notmatch 'octet-stream') { return $null }
    return [byte[]]$r.RawContentStream.ToArray()
}

function Invoke-GenieClone([string]$Id, [string]$To, [switch]$Force) {
    $row = Resolve-GenieRow $Id
    if (Get-GenieProp $row 'superseded_by') { G-Warn "$($row.name) ($($row.hex_id)) is superseded by $($row.superseded_by) — cloning the old one because you named it" }
    $bytes = Get-GenieBytes $row
    if ($null -eq $bytes) { throw "$($row.name): no bytes in R2 (catalog row only). Re-intake it from the machine that has it." }
    $sha3 = Get-GenieSha3 $bytes
    $want = [string](Get-GenieProp $row 'hash_sha3')
    if ($want) { $want = $want.ToLowerInvariant() }
    if ($want -and $sha3 -ne $want) {
        throw "$($row.name): SHA3-512 MISMATCH — R2 bytes do not match custody. Not written.`n    custody $($want.Substring(0,16))…  got $($sha3.Substring(0,16))…"
    }
    if (-not $want -and -not $Force) {
        throw "$($row.name): D1 has no SHA3 baseline, so the bytes can't be verified. Not written. Use -Force to accept unverified bytes."
    }
    $destDir = if ($To) { $To } else { $script:GenieCloset }
    New-Item -ItemType Directory -Force -Path $destDir | Out-Null
    $dest = Join-Path $destDir $row.name
    $part = "$dest.genie-part"
    [System.IO.File]::WriteAllBytes($part, $bytes)
    Move-Item -LiteralPath $part -Destination $dest -Force       # atomic swap, never a half file
    $state = if ($want) { 'verified' } else { 'UNVERIFIED (-Force)' }
    G-Ok ("cloned {0}  v{1}  {2:N1} KB  sha3 {3}  -> {4}" -f $row.name, ([string](Get-GenieProp $row 'version')).TrimStart('v'), ($bytes.Length / 1KB), $state, $dest)
    return [pscustomobject]@{ Name = $row.name; HexId = $row.hex_id; Sha3 = $sha3; Verified = [bool]$want; Path = $dest }
}

# ── Read-only views ──────────────────────────────────────────────────────────
function Show-GenieFind([string]$Term) {
    $s = Invoke-GenieJson "/search?q=$([uri]::EscapeDataString($Term))"
    $pool = Get-GeniePool
    $rows = @($pool | Where-Object { $_.name -like "*$Term*" -or $_.hex_id -like "*$Term*" })   # all of them, not the search route's 20
    if ($rows.Count) {
        $w = [Math]::Max(4, ($rows | ForEach-Object { ([string]$_.name).Length } | Measure-Object -Maximum).Maximum)
        Write-Host ("  {0}  {1,-5} {2,-4} {3,-6} {4,-8} {5}" -f 'name'.PadRight($w), 'ver', 'tier', 'sha3', 'state', 'hex_id') -ForegroundColor DarkCyan
        foreach ($x in $rows | Sort-Object name) {
            $ver  = if (Get-GenieProp $x 'version') { 'v' + ([string]$x.version).TrimStart('v') } else { '' }
            $sha  = if (Get-GenieProp $x 'hash_sha3') { 'yes' } else { 'NONE' }
            $old  = if (Get-GenieProp $x 'superseded_by') { '  (superseded)' } else { '' }
            Write-Host ("  {0}  {1,-5} {2,-4} {3,-6} {4,-8} {5}{6}" -f ([string]$x.name).PadRight($w), $ver, $x.tier, $sha, $x.state, $x.hex_id, $old) `
                -ForegroundColor $(if ($old) { 'DarkGray' } elseif ($sha -eq 'NONE') { 'Yellow' } else { 'Gray' })
        }
    }
    $g = @(Get-GenieProp $s 'glossary')
    if ($g.Count) {
        Write-Host "  glossary:" -ForegroundColor DarkCyan
        foreach ($x in $g) { Write-Host ("    {0} — {1}" -f $x.name, ([string](Get-GenieProp $x 'description')).Split("`n")[0]) }
    }
    if (-not $rows.Count -and -not $g.Count) { G-Info 'no matches' }
}

function Show-GenieInfo([string]$Id) {
    $row = Resolve-GenieRow $Id
    Write-Host ''
    Write-Host "  $($row.name)" -ForegroundColor Magenta
    foreach ($f in 'hex_id', 'version', 'tier', 'state', 'size', 'source_path', 'pool_path', 'intaked_at', 'updated_at', 'verified_at', 'hash_alg', 'superseded_by', 'sensitive') {
        $v = Get-GenieProp $row $f
        if ($null -ne $v -and "$v" -ne '') { Write-Host ("  {0,-12} {1}" -f $f, $v) }
    }
    $sha = Get-GenieProp $row 'hash_sha3'
    Write-Host ("  {0,-12} {1}" -f 'sha3-512', $(if ($sha) { $sha } else { 'NONE — no custody baseline (genie custody)' })) -ForegroundColor $(if ($sha) { 'Gray' } else { 'Yellow' })
    $v = Invoke-GenieJson "/versions?package=$([uri]::EscapeDataString($row.name))&limit=50"
    $vers = @(Get-GenieProp $v 'versions')
    Write-Host "  version ledger ($($vers.Count)):" -ForegroundColor DarkCyan
    foreach ($x in $vers) { Write-Host ("    v{0,-4} {1}  sha3 {2}  {3}" -f ([string]$x.version).TrimStart('v'), $x.created_at, $(if ($x.hash_sha3) { $x.hash_sha3.Substring(0, 16) + '…' } else { '-' }), $x.note) }
    $c = Invoke-GenieJson "/custody?hex=$([uri]::EscapeDataString($row.hex_id))&limit=20"
    $rec = @(Get-GenieProp $c 'custody')
    Write-Host "  custody receipts ($($rec.Count)):" -ForegroundColor DarkCyan
    foreach ($x in $rec) { Write-Host ("    {0}  {1,-10} {2}  validated {3}" -f $x.intaked_at, $x.action, $x.actor, $x.validated) }
    Write-Host ''
}

function Show-GenieCode([string]$Id, [switch]$Force) {
    # Print the stored code with line numbers — verified against custody first.
    $row = Resolve-GenieRow $Id
    $bytes = Get-GenieBytes $row
    if ($null -eq $bytes) { throw "$($row.name): no bytes in R2." }
    $want = [string](Get-GenieProp $row 'hash_sha3')
    $sha3 = Get-GenieSha3 $bytes
    if ($want -and $sha3 -ne $want.ToLowerInvariant()) { throw "$($row.name): SHA3-512 MISMATCH — not shown." }
    if (-not $want -and -not $Force) { throw "$($row.name): no SHA3 baseline — use -Force to view unverified bytes." }
    if ([Array]::IndexOf($bytes, [byte]0) -ge 0) { throw "$($row.name) is binary ($($bytes.Length) bytes) — genie clone it instead." }
    $text = [System.Text.Encoding]::UTF8.GetString($bytes)
    $n = 0
    Write-Host ("  ── {0}  v{1}  {2}" -f $row.name, ([string](Get-GenieProp $row 'version')).TrimStart('v'), $(if ($want) { 'sha3 verified' } else { 'UNVERIFIED' })) -ForegroundColor DarkCyan
    foreach ($line in $text -split "`r?`n") { $n++; Write-Host ("{0,5}  {1}" -f $n, $line) }
}

function Test-GenieLocal([string]$Path, [string]$Id) {
    # Is this local file byte-identical to custody?
    $full = (Resolve-Path -LiteralPath $Path -ErrorAction Stop).Path
    $name = if ($Id) { $Id } else { Split-Path $full -Leaf }
    $sha3 = Get-GenieSha3 ([System.IO.File]::ReadAllBytes($full))
    $pool = Get-GeniePool
    $same = @($pool | Where-Object { (Get-GenieProp $_ 'hash_sha3') -eq $sha3 })
    if ($same.Count) {
        foreach ($x in $same) { G-Ok ("MATCH  {0} == {1} v{2} ({3})" -f $full, $x.name, ([string](Get-GenieProp $x 'version')).TrimStart('v'), $x.hex_id) }
        return
    }
    try { $row = Resolve-GenieRow $name } catch { G-Warn "NOT IN CUSTODY  $full  (sha3 $($sha3.Substring(0,16))…) — $($_.Exception.Message)"; return }
    if (Get-GenieProp $row 'hash_sha3') { G-Err ("DIFFERS  {0} is not {1} v{2} — intake it to record a new version" -f $full, $row.name, ([string](Get-GenieProp $row 'version')).TrimStart('v')) }
    else { G-Warn "UNVERIFIABLE  $($row.name) has no SHA3 baseline in D1" }
}

# ── Custody audit: rows with no SHA3 baseline (read-only) ───────────────────
function ConvertTo-GenieLocalPath([string]$p) {
    if (-not $p) { return $null }
    if ($IsWindows) {
        if ($p -match '^/([a-zA-Z])/(.*)$') { return "$($Matches[1].ToUpper()):\$($Matches[2] -replace '/', '\')" }
        if ($p -match '^[A-Za-z]:[\\/]')    { return ($p -replace '/', '\') }
        return $null                          # /home/... = old WSL/Linux pool, not on this disk
    }
    if ($p -match '^[A-Za-z]:[\\/]') { return $null }
    return $p
}

function Invoke-GenieCustodyAudit([string]$Root) {
    $all  = @(Get-GeniePool -Refresh)
    $rows = @($all | Where-Object { -not (Get-GenieProp $_ 'hash_sha3') })
    G-Info "$($all.Count) clonepool rows, $($rows.Count) without a SHA3 baseline — checking each (read-only)"
    $byName = @{}; $repoFiles = @()
    if ($Root) {
        $skip = '[\\/](\.git|node_modules|__pycache__|\.venv|venv|dist|build|\.wrangler)[\\/]'
        $repoFiles = @(Get-ChildItem -LiteralPath $Root -Recurse -File -ErrorAction SilentlyContinue | Where-Object { $_.FullName -notmatch $skip })
        foreach ($f in $repoFiles) { if (-not $byName.ContainsKey($f.Name)) { $byName[$f.Name] = @() }; $byName[$f.Name] += $f.FullName }
        G-Info "looking for local copies under $Root ($($repoFiles.Count) files)"
    } else {
        G-Warn 'no -Root given: only each row''s own pool_path is checked for a local copy'
    }

    $report = foreach ($r in $rows) {
        $rec = [ordered]@{ name = $r.name; hex_id = $r.hex_id; version = [string](Get-GenieProp $r 'version'); verdict = ''; r2_sha3 = ''; local = ''; action = '' }
        if (Get-GenieProp $r 'superseded_by') {
            # An old version: baselining it from today's local file would be wrong.
            $rec.verdict = 'SUPERSEDED'; $rec.action = "history — replaced by $($r.superseded_by); nothing to do"; [pscustomobject]$rec; continue
        }
        try { $r2 = Get-GenieBytes $r } catch { $rec.verdict = 'ERROR'; $rec.action = $_.Exception.Message; [pscustomobject]$rec; continue }
        $r2sha = if ($null -ne $r2) { Get-GenieSha3 $r2 } else { $null }
        if ($r2sha) { $rec.r2_sha3 = $r2sha.Substring(0, 16) }
        $cands = @()
        $lp = ConvertTo-GenieLocalPath ([string](Get-GenieProp $r 'pool_path'))
        if ($lp -and (Test-Path -LiteralPath $lp -PathType Leaf)) { $cands += (Resolve-Path -LiteralPath $lp).Path }
        if ($byName.ContainsKey($r.name)) { $cands += $byName[$r.name] }
        $isDir = ($lp -and (Test-Path -LiteralPath $lp -PathType Container)) -or
                 ($repoFiles.Count -and -not $byName.ContainsKey($r.name) -and @($repoFiles | Where-Object { $_.Directory.Name -eq $r.name } | Select-Object -First 1).Count)
        $match = $null; $firstLocal = $null
        foreach ($c in ($cands | Select-Object -Unique)) {
            if (-not $firstLocal) { $firstLocal = $c }
            if ($r2sha -and ((Get-GenieSha3 ([System.IO.File]::ReadAllBytes($c))) -eq $r2sha)) { $match = $c; break }
        }
        if ($isDir -and $null -eq $r2) { $rec.verdict = 'DIRECTORY'; $rec.action = 'directory snapshot — re-intake the folder to give it a manifest baseline' }
        elseif ($match)                { $rec.verdict = 'MATCH';      $rec.local = $match;      $rec.action = 're-intake: local copy is byte-identical to R2' }
        elseif ($r2sha -and $firstLocal) { $rec.verdict = 'DIFFERS';  $rec.local = $firstLocal; $rec.action = 'local differs from R2 — re-intake makes a NEW version; R2 bytes stay unverified history' }
        elseif ($r2sha)                { $rec.verdict = 'R2-ONLY';    $rec.action = 'no local copy — only way to baseline is to trust the R2 bytes as-is (your call)' }
        elseif ($firstLocal)           { $rec.verdict = 'LOCAL-ONLY'; $rec.local = $firstLocal; $rec.action = 're-intake: R2 has no bytes, local copy exists' }
        else                           { $rec.verdict = 'LOST';       $rec.action = 'no R2 bytes, no local copy — catalog row only' }
        [pscustomobject]$rec
    }
    $report = @($report)
    $stamp = (Get-Date).ToString('yyyyMMdd-HHmmss')
    New-Item -ItemType Directory -Force -Path $script:GenieHome | Out-Null
    $csv = Join-Path $script:GenieHome "custody-audit-$stamp.csv"
    $ps1 = Join-Path $script:GenieHome "custody-reintake-$stamp.ps1"
    $report | Export-Csv -LiteralPath $csv -NoTypeInformation -Encoding utf8
    $lines = @("# Generated by genie custody $stamp — review, then run in PS7.",
               '# Only files with a trustworthy source are active. Others are commented with the reason.', '')
    foreach ($x in $report) {
        $q = if ($x.local) { "'" + ($x.local -replace "'", "''") + "'" } else { '' }
        switch ($x.verdict) {
            'MATCH'      { $lines += "intake $q   # $($x.name): local == R2" }
            'LOCAL-ONLY' { $lines += "intake $q   # $($x.name): R2 had no bytes" }
            'DIFFERS'    { $lines += "# intake $q   # $($x.name): DIFFERS from R2 — becomes a new version; decide" }
            default      { $lines += "# $($x.name): $($x.verdict) — $($x.action)" }
        }
    }
    Set-Content -LiteralPath $ps1 -Value $lines -Encoding utf8
    Write-Host ''
    $report | Group-Object verdict | Sort-Object Count -Descending | ForEach-Object {
        Write-Host ("  {0,-11} {1,3}" -f $_.Name, $_.Count) -ForegroundColor $(switch ($_.Name) { 'MATCH' { 'Green' } 'LOCAL-ONLY' { 'Green' } 'LOST' { 'Red' } 'ERROR' { 'Red' } 'SUPERSEDED' { 'DarkGray' } default { 'Yellow' } })
    }
    Write-Host ''
    G-Ok "report  : $csv"
    G-Ok "script  : $ps1   (review it, then:  & '$ps1')"
}

function Invoke-GenieCloudDoctor {
    G-Info "worker   $($script:GenieWorker)"
    if ([System.Security.Cryptography.SHA3_512]::IsSupported) { G-Ok 'sha3     native (OS)' } else { G-Ok 'sha3     built-in Keccak (OS has no SHA3)' }
    $probe = Get-GenieSha3 ([System.Text.Encoding]::ASCII.GetBytes('abc'))
    if ($probe.StartsWith('b751850b1a57168a')) { G-Ok 'sha3     self-test passed' } else { G-Err 'sha3     SELF-TEST FAILED — do not trust clones from this machine' }
    if ($env:PHOENIX_AUTH) { G-Ok 'auth     PHOENIX_AUTH set' } else { G-Err 'auth     PHOENIX_AUTH not set' }
    if ($env:CF_ACCESS_CLIENT_ID -and $env:CF_ACCESS_CLIENT_SECRET) { G-Ok 'access   CF Access token set' } else { G-Warn 'access   CF_ACCESS_CLIENT_ID/SECRET not set' }
    try {
        $w = Invoke-GenieWorker '/whoami'
        if ($w.StatusCode -eq 200) {
            $wi = [System.Text.Encoding]::UTF8.GetString($w.RawContentStream.ToArray()) | ConvertFrom-Json
            $who = Get-GenieProp $wi 'who'
            G-Ok ("worker   auth OK ({0}){1}" -f $wi.version, $(if ($who) { "  signed in as: $who  [$(Get-GenieProp $wi 'scopes')]" } else { '' }))
        }
        else { G-Err "worker   HTTP $($w.StatusCode)" }
        $pool = Get-GeniePool -Refresh
        $noHash = @($pool | Where-Object { -not (Get-GenieProp $_ 'hash_sha3') }).Count
        G-Ok ("D1       {0} clonepool rows ({1} without a SHA3 baseline)" -f $pool.Count, $noHash)
    } catch { G-Err "worker   $($_.Exception.Message)" }
}

# ── Intake (IN) — runs the package handler's intake.sh; Genie itself still never writes ──
# intake.sh comes out of the clonepool like any other file (SHA3-verified), so
# every machine runs the exact intake Phoenix has in custody. Your key goes to
# intake through the environment, never on its command line.
$script:GenieIntakeSh = Join-Path $script:GenieHome 'bin/intake.sh'

function Get-GenieBash {
    if ($IsWindows) {
        # Git for Windows' bash. NOT C:\Windows\System32\bash.exe — that is WSL, a different machine.
        foreach ($c in @("$env:ProgramFiles\Git\bin\bash.exe", "${env:ProgramFiles(x86)}\Git\bin\bash.exe", "$env:LOCALAPPDATA\Programs\Git\bin\bash.exe")) {
            if ($c -and (Test-Path -LiteralPath $c)) { return $c }
        }
        $g = Get-Command git -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($g) { $b = Join-Path (Split-Path (Split-Path $g.Source)) 'bin\bash.exe'; if (Test-Path -LiteralPath $b) { return $b } }
        return $null
    }
    foreach ($c in '/bin/bash', '/usr/bin/bash', '/opt/homebrew/bin/bash', '/usr/local/bin/bash') { if (Test-Path -LiteralPath $c) { return $c } }
    return $null
}

function Invoke-GenieIntake([string[]]$Paths) {
    if ($Paths -and $Paths[0] -eq 'setup') {
        $c = Invoke-GenieClone -Id 'intake.sh' -To (Split-Path $script:GenieIntakeSh)
        G-Ok "intake ready: $($c.Path)"
        if (-not (Get-GenieBash)) { G-Warn $(if ($IsWindows) { 'bash not found — install Git for Windows:  winget install Git.Git' } else { 'bash not found — install bash' }) }
        return
    }
    if (-not $Paths) { throw 'usage: genie intake <file or folder> [...]     (first time: genie intake setup)' }
    if (-not (Test-Path -LiteralPath $script:GenieIntakeSh)) { throw 'intake is not set up on this machine — run:  genie intake setup' }
    $bash = Get-GenieBash
    if (-not $bash) { throw $(if ($IsWindows) { 'bash not found — install Git for Windows:  winget install Git.Git' } else { 'bash not found' }) }
    if (-not $env:PHOENIX_AUTH) { throw 'PHOENIX_AUTH is not set in this shell.' }
    # Re-verify the local intake.sh against custody every run: it executes with your key.
    $row = Resolve-GenieRow 'intake.sh'
    $have = Get-GenieSha3 ([System.IO.File]::ReadAllBytes($script:GenieIntakeSh))
    if ((Get-GenieProp $row 'hash_sha3') -and $have -ne ([string]$row.hash_sha3).ToLowerInvariant()) {
        throw 'your intake.sh differs from the one in Phoenix custody (updated, or changed) — run:  genie intake setup'
    }
    if (-not $env:PHOENIX_WORKER_URL) { $env:PHOENIX_WORKER_URL = $script:GenieWorker }
    # intake.sh takes ONE file or folder per run (anything after it is backend/notes),
    # so each path is its own run. Each path is passed as a single argument —
    # never splatted (splatting a lone string hands bash one character per argument).
    $old = [Console]::OutputEncoding
    try {
        [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
        foreach ($p in $Paths) {
            $item = Get-Item -LiteralPath $p -ErrorAction Stop
            $arg = if ($item.PSIsContainer) { $item.FullName.TrimEnd('\', '/') + '/' } else { $item.FullName }
            & $bash $script:GenieIntakeSh $arg
            if ($LASTEXITCODE) { G-Warn "intake exited $LASTEXITCODE for $p" }
        }
    } finally {
        [Console]::OutputEncoding = $old
        $script:GeniePoolCache = $null      # the pool just changed: next lookup reads it fresh
    }
}

# ── Keys (owner only): one key per person, cut off without touching yours ──
function Invoke-GenieKey([string[]]$KeyArgs, [string]$Scopes) {
    $verb = if ($KeyArgs) { $KeyArgs[0] } else { 'list' }
    switch ($verb) {
        'list' {
            $k = Invoke-GenieJson '/keys'
            if (-not $k) { throw 'this worker has no /keys (needs packages-worker 3.9.0)' }
            Write-Host ("  {0,-16} {1,-12} {2,-20} {3,-20} {4}" -f 'who', 'scopes', 'created', 'last used', 'revoked') -ForegroundColor DarkCyan
            foreach ($x in @($k.keys)) {
                Write-Host ("  {0,-16} {1,-12} {2,-20} {3,-20} {4}" -f $x.who, $x.scopes, $x.created_at, $x.last_used_at, $x.revoked_at) -ForegroundColor $(if ($x.revoked_at) { 'DarkGray' } else { 'Gray' })
            }
        }
        'new' {
            if ($KeyArgs.Count -lt 2) { throw 'usage: genie key new <who> [-Scopes read|read,intake]' }
            $body = @{ who = $KeyArgs[1] }; if ($Scopes) { $body.scopes = $Scopes }
            $r = Invoke-GenieWorkerPost '/keys' $body
            Write-Host ''
            G-Ok "key for $($r.who)  [$($r.scopes)]"
            Write-Host "     $($r.key)" -ForegroundColor White
            G-Warn 'Shown once — Phoenix keeps only its hash. Give it to them over something private (Signal, in person),'
            G-Warn 'not email or a group chat. They set it as PHOENIX_AUTH (see the cloud Genie README).'
            Write-Host ''
        }
        'revoke' {
            if ($KeyArgs.Count -lt 2) { throw 'usage: genie key revoke <who>' }
            $r = Invoke-GenieWorkerPost "/keys/$([uri]::EscapeDataString($KeyArgs[1]))/revoke" $null
            G-Ok "revoked: $($r.revoked) — that key stops working on the next request"
        }
        default { throw 'usage: genie key list | new <who> [-Scopes read] | revoke <who>' }
    }
}

# ── Guided tour: real calls against the real pool, read-only, explained ─────
function Invoke-GenieTour([switch]$NoPause) {
    $step = 0
    $next = {
        param([string]$Title, [string]$Why)
        $script:tourStep++
        Write-Host ''
        Write-Host ("  ── step {0}: {1}" -f $script:tourStep, $Title) -ForegroundColor Magenta
        foreach ($l in $Why -split "`n") { Write-Host "     $l" -ForegroundColor DarkGray }
        if (-not $NoPause) { [void](Read-Host '     press Enter to run it') }
    }
    $script:tourStep = $step
    Write-Host ''
    Write-Host '  PHOENIX GENIE — guided tour' -ForegroundColor Magenta
    Write-Host '  Everything below is a real call to the real clonepool. Nothing is written to R2 or D1.' -ForegroundColor DarkGray
    Write-Host '  The only thing written is one file in a scratch folder, which is deleted at the end.' -ForegroundColor DarkGray

    & $next 'is everything connected?' "Phoenix keeps every file twice: the BYTES in R2 (storage) and the RECORD in D1 (database).`nThe record holds a SHA3-512 fingerprint taken when the file came in. Genie talks to both through packages-worker."
    Invoke-GenieCloudDoctor

    # Pick a real, small, verifiable text file to look at.
    $cands = @(Get-GeniePool | Where-Object { (Get-GenieProp $_ 'hash_sha3') -and -not (Get-GenieProp $_ 'superseded_by') -and $_.name -match '\.(py|ps1|sh|js|mjs|md|txt|json|toml|yaml|yml)$' } |
               Sort-Object { [long](Get-GenieProp $_ 'size') })
    $pick = $null; $bytes = $null
    foreach ($c in $cands | Select-Object -First 40) {
        try { $b = Get-GenieBytes $c } catch { continue }
        if ($null -ne $b -and $b.Length -gt 0 -and $b.Length -le 65536 -and [Array]::IndexOf($b, [byte]0) -lt 0 -and (Get-GenieSha3 $b) -eq ([string]$c.hash_sha3).ToLowerInvariant()) { $pick = $c; $bytes = $b; break }
    }
    if (-not $pick) { G-Err 'no small verified text file found in the pool to tour with — intake one first'; return }
    $name = $pick.name

    & $next "find something" "``genie find <word>`` searches every record. Each row has a name, a version, a tier, whether it has a fingerprint, and a hex_id —`nthe hex_id is the file's permanent identity. Two files can share a name; they never share a hex_id."
    Show-GenieFind $name

    & $next "look at its record: genie info $name" "The custody record: where it came from, its fingerprint, every version in the ledger, and every receipt`n(who took it in, when). This is the paper trail."
    Show-GenieInfo $pick.hex_id

    & $next "read the code: genie cat $name" "Genie downloads the bytes, re-computes the fingerprint, and only shows the code if it matches the record.`nIf someone changed the stored bytes, you'd get a MISMATCH instead of the code."
    Show-GenieCode $pick.hex_id

    $tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("genie-tour-" + [guid]::NewGuid().ToString('n').Substring(0, 8))
    try {
        & $next "take a copy: genie clone $name" "Clone is OUT: R2 -> your disk. The fingerprint is checked BEFORE the file is written,`nso a bad file never lands. (Tour copy goes to a scratch folder.)"
        $c = Invoke-GenieClone -Id $pick.hex_id -To $tmp

        & $next "prove your copy is the real one: genie verify" "Anyone can check any file on their disk against Phoenix custody."
        Test-GenieLocal $c.Path $pick.hex_id

        & $next "now change ONE byte and check again" "This is the whole point of custody: the smallest change gives a completely different fingerprint."
        $raw = [System.IO.File]::ReadAllBytes($c.Path); $raw[0] = $raw[0] -bxor 1; [System.IO.File]::WriteAllBytes($c.Path, $raw)
        Write-Host ("     original : {0}…" -f $c.Sha3.Substring(0, 32)) -ForegroundColor DarkGray
        Write-Host ("     changed  : {0}…" -f (Get-GenieSha3 $raw).Substring(0, 32)) -ForegroundColor DarkGray
        Test-GenieLocal $c.Path $pick.hex_id
    } finally { Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue }

    Write-Host ''
    Write-Host '  ── what you did' -ForegroundColor Magenta
    Write-Host '     find -> info -> cat -> clone -> verify. That is OUT: getting files from Phoenix, proven genuine.' -ForegroundColor Gray
    Write-Host '     IN is intake: `intake <file>` fingerprints your file, records it in D1 and stores it in R2,' -ForegroundColor Gray
    Write-Host '     as the next version if that name is already yours. A name someone else owns is refused —' -ForegroundColor Gray
    Write-Host '     rename your file. Once it is in, anyone with Genie can clone it.' -ForegroundColor Gray
    Write-Host '     Next: genie help' -ForegroundColor Gray
    Write-Host ''
}

# Cloud verbs. genie.ps1 calls this for the verbs it shares, so both editions behave the same.
function Invoke-GenieCloudCommand([string]$Command, [string[]]$Args2, [string]$To, [string]$Root, [string]$Scopes, [switch]$Force) {
    switch ($Command) {
        'find'    { if (-not $Args2) { throw 'usage: genie find <term>' }; Show-GenieFind ($Args2 -join ' ') }
        'info'    { if (-not $Args2) { throw 'usage: genie info <name|hex_id>' }; Show-GenieInfo $Args2[0] }
        'cat'     { if (-not $Args2) { throw 'usage: genie cat <name|hex_id> [-Force]' }; Show-GenieCode $Args2[0] -Force:$Force }
        'verify'  { if (-not $Args2) { throw 'usage: genie verify <local file> [name|hex_id]' }; Test-GenieLocal $Args2[0] $(if ($Args2.Count -gt 1) { $Args2[1] }) }
        'clone'   {
            if (-not $Args2) { throw 'usage: genie clone <name|hex_id> [...] [-To <dir>] [-Force]' }
            foreach ($id in $Args2) { try { [void](Invoke-GenieClone -Id $id -To $To -Force:$Force) } catch { G-Err $_.Exception.Message } }
        }
        'custody' { Invoke-GenieCustodyAudit -Root $Root }
        'doctor'  { Invoke-GenieCloudDoctor }
        'tour'    { Invoke-GenieTour -NoPause:$Force }
        'key'     { Invoke-GenieKey -KeyArgs $Args2 -Scopes $Scopes }
        'intake'  { Invoke-GenieIntake -Paths $Args2 }
        default   { throw "unknown cloud command: $Command" }
    }
}

$script:GenieCloudHelp = @'
  genie tour [-Force]                guided walk-through on real files (-Force = no pauses)
  genie doctor                       auth, worker, D1 row count, SHA3 self-test
  genie find <term>                  search the clonepool (every row, not just 20) + glossary
  genie info <name|hex>              custody row, version ledger, custody receipts
  genie cat <name|hex> [-Force]      show the stored code with line numbers (SHA3-verified first)
  genie clone <name|hex> [-To d]     pull from R2, SHA3-512 verified before anything is written
  genie verify <file> [name|hex]     is this local file byte-identical to custody?
  genie intake setup                 first time: fetch the package handler's intake.sh (SHA3-verified)
  genie intake <file|folder> [...]   IN: put your file into Phoenix (D1 record + R2 bytes)
  genie custody [-Root dir]          audit rows with no SHA3 baseline; writes a reviewed re-intake script
  genie key list | new <who> [-Scopes read] | revoke <who>
                                     owner only: one key per person (read + intake their own files)
'@

# Cloud edition's own command. genie.ps1 (full edition) replaces this with one
# that adds the kernel verbs and calls Invoke-GenieCloudCommand for these.
function genie {
    [CmdletBinding()]
    param(
        [Parameter(Position = 0)]
        [ValidateSet('tour', 'doctor', 'find', 'info', 'cat', 'clone', 'verify', 'intake', 'custody', 'key', 'help')]
        [string]$Command = 'help',
        [Parameter(Position = 1, ValueFromRemainingArguments)]
        [string[]]$Args2,
        [string]$To,
        [string]$Root,
        [string]$Scopes,
        [switch]$Force
    )
    try {
        if ($Command -eq 'help') { Write-Host '  Phoenix Genie — cloud edition (R2 + D1 via packages-worker)' -ForegroundColor Magenta; $script:GenieCloudHelp | Write-Host; return }
        Invoke-GenieCloudCommand -Command $Command -Args2 $Args2 -To $To -Root $Root -Scopes $Scopes -Force:$Force
    } catch { G-Err $_.Exception.Message }
}
