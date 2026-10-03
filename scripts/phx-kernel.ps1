#Requires -Version 7.0
<#
.SYNOPSIS
    phx-kernel.ps1 — the Phoenix universal kernel for a PowerShell 7 profile.

.DESCRIPTION
    Type a command this machine doesn't have. If Phoenix's clone pool has it,
    the kernel pulls it from R2, proves the bytes against the D1 custody
    fingerprint (SHA3-512), asks you once, caches it and runs it. After that it
    runs from the cache without asking, offline, for as long as the cached
    bytes still hash to what you approved.

    One file, no repo, no usys, no Python needed: PowerShell 7 + the four
    Phoenix keys is the whole requirement (super-lite Windows, a Chromebook's
    Linux container, a fresh box). usys itself is just another thing it pulls.

    Rules it keeps:
      - only commands YOU type at the prompt (never a script's typo),
      - nothing runs unless SHA3-512 matches D1 custody,
      - the first run of anything asks (the "deviation" tier), every run logged,
      - no listener, no port, nothing touches the network until a command is missing.

    Install (copies this file next to your profile and adds one line):
      pwsh -File phx-kernel.ps1 install
    Keys: environment (PHOENIX_WORKER_URL, PHOENIX_AUTH, CF_ACCESS_CLIENT_ID,
    CF_ACCESS_CLIENT_SECRET; Windows User scope is read too) or a KEY=VALUE file
    at ~/.phoenix/kernel.env (chmod 600 on Linux).

    bingo                  status        bingo list           what's cached + approved
    bingo forget <name>    drop it       bingo refresh <name> re-pull (asks again if it changed)
    bingo log              audit trail   bingo update         pull a new phx-kernel.ps1 from the pool
    bingo preload [names]  pull + verify ahead of time (the closet); with the genie loaded, its whole library

.NOTES
    UnitedSys — United Systems | jwl247 | GPL-3.0 | Sector 2 (clone pool, consumer side)
#>

$PhxKNew = @{
    Home     = Join-Path $HOME '.phoenix/kernel'
    MissTtl  = 600                                   # a name the pool didn't have: don't ask again for 10 min
    Timeout  = 5
    Misses   = @{}
    Exts     = if ($IsWindows) { @('ps1', 'exe', 'py', 'js', 'sh') } else { @('ps1', 'sh', 'py', 'js') }
    Self     = $PSCommandPath
    Previous = if ($global:PhxK -and $global:PhxK.ContainsKey('Previous')) { $global:PhxK.Previous }
               else { $ExecutionContext.InvokeCommand.CommandNotFoundAction }
}
$global:PhxK = $PhxKNew; Remove-Variable PhxKNew
$global:PhxK.Cache    = Join-Path $global:PhxK.Home 'cache'
$global:PhxK.Approved = Join-Path $global:PhxK.Home 'approved.json'
$global:PhxK.Log      = Join-Path $global:PhxK.Home 'log.jsonl'

# ── keys ────────────────────────────────────────────────────────────────────
function global:Get-PhxKKey([string]$Name) {
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

function global:Get-PhxKHeaders {
    $h = @{ 'User-Agent' = 'phoenix-kernel/1' }      # Python/default agents get Cloudflare 1010 (pentest A2-N7)
    if ($a = Get-PhxKKey 'PHOENIX_AUTH')            { $h['Authorization'] = "Bearer $a" }
    if ($i = Get-PhxKKey 'CF_ACCESS_CLIENT_ID')     { $h['CF-Access-Client-Id'] = $i }
    if ($s = Get-PhxKKey 'CF_ACCESS_CLIENT_SECRET') { $h['CF-Access-Client-Secret'] = $s }
    return $h
}

# One seam for every network call, so the tests can stand in for the worker.
$global:PhxKHttp = {
    param([string]$Path, [string]$OutFile)
    $base = (Get-PhxKKey 'PHOENIX_WORKER_URL')
    if (-not $base) { throw 'PHOENIX_WORKER_URL not set' }
    $uri = $base.TrimEnd('/') + $Path
    if ($OutFile) {
        Invoke-WebRequest -Uri $uri -Headers (Get-PhxKHeaders) -OutFile $OutFile -TimeoutSec 300 -ErrorAction Stop | Out-Null
    } else {
        Invoke-RestMethod -Uri $uri -Headers (Get-PhxKHeaders) -TimeoutSec $global:PhxK.Timeout -ErrorAction Stop
    }
}

# ── identity + fingerprint ─────────────────────────────────────────────────
# intake.sh's hex id is to_hex(basename): the file name's bytes as hex.
function global:ConvertTo-PhxKHex([string]$Name) {
    [Convert]::ToHexString([Text.Encoding]::UTF8.GetBytes($Name)).ToLowerInvariant()
}

# SHA3-512 for machines whose OS crypto lacks it (older/lite Windows builds):
# Keccak-f[1600], rate 72, compiled once on first use. Checked against
# hashlib in phx-kernel.Tests.ps1.
$global:PhxKKeccak = @'
using System; using System.IO;
public static class PhxKeccak {
  static readonly ulong[] RC = {0x1UL,0x8082UL,0x800000000000808AUL,0x8000000080008000UL,0x808BUL,0x80000001UL,
    0x8000000080008081UL,0x8000000000008009UL,0x8AUL,0x88UL,0x80008009UL,0x8000000AUL,0x8000808BUL,
    0x800000000000008BUL,0x8000000000008089UL,0x8000000000008003UL,0x8000000000008002UL,0x8000000000000080UL,
    0x800AUL,0x800000008000000AUL,0x8000000080008081UL,0x8000000000008080UL,0x80000001UL,0x8000000080008008UL};
  static readonly int[] R = {0,1,62,28,27,36,44,6,55,20,3,10,43,25,39,41,45,15,21,8,18,2,61,56,14};
  static ulong Rol(ulong x, int n) { return n == 0 ? x : (x << n) | (x >> (64 - n)); }
  static void F(ulong[] A) {
    ulong[] C = new ulong[5], B = new ulong[25];
    for (int r = 0; r < 24; r++) {
      for (int x = 0; x < 5; x++) C[x] = A[x] ^ A[x+5] ^ A[x+10] ^ A[x+15] ^ A[x+20];
      for (int x = 0; x < 5; x++) { ulong d = C[(x+4)%5] ^ Rol(C[(x+1)%5], 1); for (int y = 0; y < 25; y += 5) A[y+x] ^= d; }
      for (int x = 0; x < 5; x++) for (int y = 0; y < 5; y++) B[y + 5*((2*x + 3*y) % 5)] = Rol(A[x+5*y], R[x+5*y]);
      for (int x = 0; x < 5; x++) for (int y = 0; y < 5; y++) A[x+5*y] = B[x+5*y] ^ (~B[(x+1)%5 + 5*y] & B[(x+2)%5 + 5*y]);
      A[0] ^= RC[r];
    }
  }
  static void Absorb(ulong[] A, byte[] b, int off) { for (int i = 0; i < 9; i++) A[i] ^= BitConverter.ToUInt64(b, off + 8*i); F(A); }
  public static string Sha3_512(Stream s) {
    const int rate = 72; ulong[] A = new ulong[25]; byte[] buf = new byte[rate * 1024]; int have = 0, n;
    while ((n = s.Read(buf, have, buf.Length - have)) > 0) {
      have += n; int full = have - have % rate;
      for (int o = 0; o < full; o += rate) Absorb(A, buf, o);
      Array.Copy(buf, full, buf, 0, have - full); have -= full;
    }
    byte[] last = new byte[rate]; Array.Copy(buf, last, have); last[have] ^= 0x06; last[rate-1] ^= 0x80; Absorb(A, last, 0);
    var hex = new System.Text.StringBuilder(128);
    for (int i = 0; i < 8; i++) foreach (byte x in BitConverter.GetBytes(A[i])) hex.Append(x.ToString("x2"));
    return hex.ToString();
  }
}
'@

function global:Get-PhxKSha3([string]$Path, [switch]$Portable) {
    $fs = [IO.File]::OpenRead($Path)
    try {
        if (-not $Portable -and [Security.Cryptography.SHA3_512]::IsSupported) {
            return [Convert]::ToHexString([Security.Cryptography.SHA3_512]::HashData($fs)).ToLowerInvariant()
        }
        if (-not ('PhxKeccak' -as [type])) { Add-Type -TypeDefinition $global:PhxKKeccak -Language CSharp }
        return [PhxKeccak]::Sha3_512($fs)
    } finally { $fs.Dispose() }
}

# ── state ───────────────────────────────────────────────────────────────────
function global:Write-PhxKLog([hashtable]$Entry) {
    try {
        New-Item -ItemType Directory -Path $global:PhxK.Home -Force | Out-Null
        $Entry['ts'] = [DateTime]::UtcNow.ToString('o'); $Entry['host'] = [Environment]::MachineName
        Add-Content -LiteralPath $global:PhxK.Log -Value ($Entry | ConvertTo-Json -Compress) -Encoding utf8
    } catch { }
}

function global:Get-PhxKApproved {
    try { $j = Get-Content -LiteralPath $global:PhxK.Approved -Raw -ErrorAction Stop | ConvertFrom-Json -AsHashtable; if ($j) { return $j } } catch { }
    return @{}
}

function global:Save-PhxKApproved([hashtable]$Map) {
    New-Item -ItemType Directory -Path $global:PhxK.Home -Force | Out-Null
    $tmp = "$($global:PhxK.Approved).tmp"
    $Map | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $tmp -Encoding utf8
    Move-Item -LiteralPath $tmp -Destination $global:PhxK.Approved -Force
}

# ── finding a command ──────────────────────────────────────────────────────
# Cached + approved + bytes still hash to what was approved. No network.
function global:Find-PhxKCached([string]$Command) {
    $approved = Get-PhxKApproved
    foreach ($ext in $global:PhxK.Exts) {
        $name = "$Command.$ext"; $a = $approved[$name]
        if (-not $a) { continue }
        $file = Join-Path $global:PhxK.Cache (Join-Path $a.hex $name)
        if ((Test-Path -LiteralPath $file) -and (Get-PhxKSha3 $file) -eq $a.sha3) {
            return @{ name = $name; hex = $a.hex; sha3 = $a.sha3; file = $file; approved = $true }
        }
        Write-PhxKLog @{ event = 'cache_mismatch'; name = $name }   # changed on disk: never run it, re-pull + re-ask
    }
    return $null
}

# Ask D1 for <command>.<ext> by hex id. $null = the pool doesn't have it.
function global:Find-PhxKRemote([string]$Command) {
    foreach ($ext in $global:PhxK.Exts) {
        $name = "$Command.$ext"; $hex = ConvertTo-PhxKHex $name
        try { $r = & $global:PhxKHttp "/clonepool/$hex`?meta=true" } catch {
            $code = $_.Exception.Response.StatusCode.value__
            if ($code -eq 404) { continue }
            return $null                                    # offline / auth / timeout: stay quiet, behave like plain PowerShell
        }
        $row = if ($r.result) { $r.result } elseif ($r.item) { $r.item } else { $r }
        $sha = ([string]$row.hash_sha3).Trim().ToLowerInvariant()
        if ($row.name -eq $name -and $sha -match '^[0-9a-f]{128}$') {
            return @{ name = $name; hex = $hex; sha3 = $sha; version = $row.version; approved = $false }
        }
    }
    return $null
}

# R2 bytes -> side file -> SHA3 against custody -> cache. Returns the cache path or $null.
function global:Save-PhxKFromPool([hashtable]$Hit) {
    $safe = [IO.Path]::GetFileName($Hit.name)
    if (-not $safe -or $safe -ne $Hit.name) { Write-Warning "phx: refusing odd name '$($Hit.name)'"; return $null }
    $dir = Join-Path $global:PhxK.Cache $Hit.hex
    New-Item -ItemType Directory -Path $dir -Force | Out-Null
    $out = Join-Path $dir $safe; $part = "$out.phx-partial"
    try { & $global:PhxKHttp "/clonepool/$($Hit.hex)" $part } catch {
        Remove-Item -LiteralPath $part -Force -ErrorAction SilentlyContinue
        Write-Warning "phx: couldn't pull $safe from the pool: $($_.Exception.Message)"; return $null
    }
    $got = Get-PhxKSha3 $part
    if ($got -ne $Hit.sha3) {
        Remove-Item -LiteralPath $part -Force -ErrorAction SilentlyContinue
        Write-PhxKLog @{ event = 'refused_mismatch'; name = $safe; want = $Hit.sha3.Substring(0, 16); got = $got.Substring(0, 16) }
        Write-Warning "phx: $safe from R2 does NOT match its D1 fingerprint. Refused, nothing kept."
        return $null
    }
    Move-Item -LiteralPath $part -Destination $out -Force
    if (-not $IsWindows -and $safe -match '\.(sh)$') { chmod 700 $out 2>$null }
    Write-PhxKLog @{ event = 'pulled'; name = $safe; sha3 = $got.Substring(0, 16) }
    return $out
}

# ── running it ─────────────────────────────────────────────────────────────
function global:Get-PhxKRunner([string]$File) {
    switch ([IO.Path]::GetExtension($File).ToLowerInvariant()) {
        '.ps1' { return @{ exe = $null } }
        '.exe' { return @{ exe = $File; pre = @() } }
        '.py'  { $p = (Get-Command python3, python -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1).Source; return @{ exe = $p; pre = @($File); need = 'Python' } }
        '.js'  { $p = (Get-Command node -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1).Source; return @{ exe = $p; pre = @($File); need = 'Node' } }
        '.sh'  {
            $p = if ($IsWindows) { @("$env:ProgramFiles\Git\bin\bash.exe", "$env:LOCALAPPDATA\Programs\Git\bin\bash.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1 }
                 else { (Get-Command bash -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1).Source }
            return @{ exe = $p; pre = @($File); need = 'bash' }
        }
    }
    return @{ exe = $null; need = 'a runtime' }
}

function global:Add-PhxKApproval([hashtable]$Hit) {
    $a = Get-PhxKApproved; $a[$Hit.name] = @{ hex = $Hit.hex; sha3 = $Hit.sha3; version = $Hit.version; at = [DateTime]::UtcNow.ToString('o') }
    Save-PhxKApproved $a
    Write-PhxKLog @{ event = 'approved'; name = $Hit.name; sha3 = $Hit.sha3.Substring(0, 16) }
}

# The closet (the original H.L.K Process Library: "pre-loaded ... nothing fetched at
# runtime ... the suit is already there"). Pull and verify everything named NOW, with
# one yes for the whole batch, so using any of it later fetches nothing, even offline.
# -> @{ ready; pulled; refused; missing } (names)
function global:Invoke-PhxKPreload([string[]]$Names) {
    $r = @{ ready = @(); pulled = @(); refused = @(); missing = @() }
    $want = @()
    foreach ($n in @($Names | Where-Object { $_ } | Select-Object -Unique)) {
        if (Get-Command $n -CommandType Function, Cmdlet, Alias, Application -ErrorAction SilentlyContinue) { $r.ready += $n; continue }
        if (Find-PhxKCached $n) { $r.ready += $n; continue }
        $global:PhxK.Misses.Remove($n)
        $h = Find-PhxKRemote $n
        if ($h) { $want += $h } else { $r.missing += $n }
    }
    if ($r.ready)   { Write-Host "  already in the closet: $($r.ready -join ', ')" -ForegroundColor DarkGray }
    if ($r.missing) { Write-Host "  not in the clone pool: $($r.missing -join ', ')" -ForegroundColor Yellow }
    if (-not $want) { return $r }
    Write-Host "  to pull and verify now:"
    foreach ($h in $want) { Write-Host ("    {0,-28} {1,-5} SHA3 {2}..." -f $h.name, $h.version, $h.sha3.Substring(0, 12)) }
    if ((Read-Host "  Pull, verify and keep all $($want.Count)? [y/N]") -notmatch '^[Yy]') { Write-PhxKLog @{ event = 'preload_declined'; count = $want.Count }; return $r }
    foreach ($h in $want) {
        if (Save-PhxKFromPool $h) { Add-PhxKApproval $h; $r.pulled += $h.name } else { $r.refused += $h.name }
    }
    Write-PhxKLog @{ event = 'preload'; pulled = $r.pulled.Count; refused = $r.refused.Count; missing = $r.missing.Count }
    Write-Host "  closet: $($r.pulled.Count) pulled, $($r.refused.Count) refused, $($r.missing.Count) not in the pool"
    return $r
}

function global:Invoke-PhxKCommand([hashtable]$Hit, [object[]]$Arguments) {
    if (-not $Hit.approved) {
        Write-Host "  phx: Phoenix has " -NoNewline; Write-Host $Hit.name -ForegroundColor Cyan -NoNewline
        Write-Host " ($($Hit.version), SHA3 $($Hit.sha3.Substring(0, 12))...)." -ForegroundColor DarkGray
        if ((Read-Host '  Pull, verify and run it? [y/N]') -notmatch '^[Yy]') { Write-PhxKLog @{ event = 'declined'; name = $Hit.name }; return }
        $file = Save-PhxKFromPool $Hit
        if (-not $file) { return }
        Add-PhxKApproval $Hit
        $Hit.file = $file
    }
    $run = Get-PhxKRunner $Hit.file
    Write-PhxKLog @{ event = 'run'; name = $Hit.name; args = $Arguments.Count }
    if ($Hit.file -like '*.ps1') { & $Hit.file @Arguments; return }
    if (-not $run.exe) { Write-Warning "phx: $($Hit.name) is verified and cached, but this machine has no $($run.need) to run it."; return }
    & $run.exe @($run.pre) @Arguments
}

# ── the hook ───────────────────────────────────────────────────────────────
function global:Resolve-PhxKCommand([string]$Name, [string]$Origin) {
    if ($Origin -ne 'Runspace') { return $null }                       # typed by you, not called by a script
    if ($Name -like 'get-*' -or $Name -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$') { return $null }
    $miss = $global:PhxK.Misses[$Name]
    if ($miss -and ([DateTime]::UtcNow - $miss).TotalSeconds -lt $global:PhxK.MissTtl) { return $null }
    $hit = Find-PhxKCached $Name
    if (-not $hit) { $hit = Find-PhxKRemote $Name }
    if (-not $hit) { $global:PhxK.Misses[$Name] = [DateTime]::UtcNow }
    return $hit
}

$ExecutionContext.InvokeCommand.CommandNotFoundAction = {
    param([string]$Name, [System.Management.Automation.CommandLookupEventArgs]$e)
    $hit = $null
    try { $hit = Resolve-PhxKCommand $Name ([string]$e.CommandOrigin) } catch { }
    if ($hit) {
        $e.CommandScriptBlock = { Invoke-PhxKCommand $hit $args }.GetNewClosure()
        $e.StopSearch = $true
    } elseif ($global:PhxK.Previous) {
        & $global:PhxK.Previous $Name $e                                 # keep whatever handler was here before us
    }
}

# ── bingo: look after it ────────────────────────────────────────────────────
function global:bingo {
    param([Parameter(Position = 0)][string]$Do = 'status', [Parameter(Position = 1)][string]$Name,
          [Parameter(Position = 2, ValueFromRemainingArguments)][string[]]$More)
    switch ($Do) {
        'status' {
            $url = Get-PhxKKey 'PHOENIX_WORKER_URL'
            Write-Host "  phx kernel: $($global:PhxK.Self)"
            Write-Host "  pool      : $(if ($url) { $url } else { 'NOT SET (PHOENIX_WORKER_URL)' })"
            Write-Host "  keys      : $(if ((Get-PhxKHeaders).Count -ge 4) { 'all present' } else { 'MISSING (see the header of this file)' })"
            Write-Host "  sha3      : $(if ([Security.Cryptography.SHA3_512]::IsSupported) { 'native' } else { 'built-in (portable)' })"
            Write-Host "  approved  : $((Get-PhxKApproved).Count) command(s)   cache: $($global:PhxK.Cache)"
        }
        'list'    { (Get-PhxKApproved).GetEnumerator() | Sort-Object Key | ForEach-Object { '{0,-28} {1,-5} {2}...' -f $_.Key, $_.Value.version, $_.Value.sha3.Substring(0, 16) } }
        'forget'  {
            $a = Get-PhxKApproved
            foreach ($k in @($a.Keys | Where-Object { $_ -eq $Name -or $_ -like "$Name.*" })) {
                Remove-Item -LiteralPath (Join-Path $global:PhxK.Cache $a[$k].hex) -Recurse -Force -ErrorAction SilentlyContinue
                $a.Remove($k); Write-PhxKLog @{ event = 'forgot'; name = $k }; Write-Host "  forgot $k"
            }
            Save-PhxKApproved $a
        }
        'refresh' { bingo forget $Name; $global:PhxK.Misses.Remove($Name); $h = Find-PhxKRemote $Name; if ($h) { Invoke-PhxKCommand $h @() } else { Write-Host "  the pool has no $Name" } }
        'log'     { if (Test-Path -LiteralPath $global:PhxK.Log) { Get-Content -LiteralPath $global:PhxK.Log -Tail 30 } }
        'preload' {
            $names = @(@($Name) + @($More) | Where-Object { $_ })
            if (-not $names -and (Get-Command Get-PhxGenieLibrary -ErrorAction SilentlyContinue)) {
                $lib = Get-PhxGenieLibrary; $names = @($lib.Keys | ForEach-Object { $lib[$_].command })
            }
            if (-not $names) { Write-Host '  bingo preload <name> [name ...]   (with the genie loaded: its whole library)'; return }
            $null = Invoke-PhxKPreload $names
        }
        'update'  {
            $h = Find-PhxKRemote 'phx-kernel'
            if (-not $h -or $h.name -ne 'phx-kernel.ps1') { Write-Host '  phx-kernel.ps1 is not in the pool yet (intake it first)'; return }
            if ($h.sha3 -eq (Get-PhxKSha3 $global:PhxK.Self)) { Write-Host '  already current'; return }
            $f = Save-PhxKFromPool $h
            if (-not $f) { return }
            $errs = $null; [void][Management.Automation.Language.Parser]::ParseFile($f, [ref]$null, [ref]$errs)
            if ($errs) { Write-Warning 'phx: the new kernel does not parse; kept the old one.'; return }
            Copy-Item -LiteralPath $f -Destination "$($global:PhxK.Self).new" -Force
            Move-Item -LiteralPath "$($global:PhxK.Self).new" -Destination $global:PhxK.Self -Force
            Write-PhxKLog @{ event = 'self_update'; sha3 = $h.sha3.Substring(0, 16) }
            Write-Host '  updated; open a new terminal to use it'
        }
        default   { Write-Host '  bingo [status|list|preload [names]|forget <name>|refresh <name>|log|update]' }
    }
}

# pwsh -File phx-kernel.ps1 install  →  copy next to the profile, one line in it.
if ($MyInvocation.InvocationName -ne '.' -and $args[0] -eq 'install') {
    $profilePath = $PROFILE.CurrentUserAllHosts
    $dest = Join-Path (Split-Path $profilePath) 'phx-kernel.ps1'
    New-Item -ItemType Directory -Path (Split-Path $profilePath) -Force | Out-Null
    if ($PSCommandPath -ne $dest) { Copy-Item -LiteralPath $PSCommandPath -Destination $dest -Force }
    $line = ". `"$dest`"   # Phoenix universal kernel"
    $cur = if (Test-Path -LiteralPath $profilePath) { Get-Content -LiteralPath $profilePath -Raw } else { '' }
    if ($cur -notmatch 'Phoenix universal kernel') { Add-Content -LiteralPath $profilePath -Value "`n$line" }
    Write-Host "  installed: $dest"
    Write-Host "  profile  : $profilePath"
    Write-Host '  open a new terminal, then: bingo'
}
